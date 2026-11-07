#!/usr/bin/env python3
"""Fork (2026-11-08). Live check of ytfetch.py --stream against YouTube (the check video, 3:33 at 720p), on a computer:
a streamed fetch into a tmpfs with a small window and simulated playback (SPEED x real time, a forward jump),
then a whole fetch of the same video, compared: the same index, the same bytes past the punched part, zeros before.

    python3 -I test/live_stream.py $PWD/ytfetch.py $PWD/build/ytdlp.pyz [--speed 4] [--ahead 20000] [--behind 8000]

Needs the network, Node.js, /dev/shm (a tmpfs) and the yt-dlp zipapp (absolute paths: ytfetch runs in /).
It ends with LIVE STREAM CHECK: PASS or FAIL.
"""
import argparse, json, os, shutil, struct, subprocess, sys, threading, time

ID = 'dQw4w9WgXcQ'


def du(d):
    n = 0
    for x in os.listdir(d):
        try:
            n += os.lstat(os.path.join(d, x)).st_blocks * 512
        except OSError:
            pass
    return n


def fetch(ytfetch, pyz, out, cache, lease, extra, on_event=None, stdin=None):
    p = subprocess.Popen([sys.executable, '-I', ytfetch, 'fetch', ID, out, '--cache-dir', cache, '--pyz', pyz,
                          '--node', shutil.which('node'), '--lease', lease] + extra,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd='/')
    errs = []
    threading.Thread(target=lambda: errs.extend(p.stderr), daemon=True).start()
    evs = []
    for line in p.stdout:
        e = json.loads(line)
        evs.append(e)
        if on_event:
            on_event(e, p)
    p.wait()
    return p.returncode, evs, ''.join(errs)


def records(path):
    with open(path, 'rb') as f:
        b = f.read()
    n = struct.unpack_from('<I', b, 16)[0]
    return [struct.unpack_from('<IQIB', b, 32 + i * 17) for i in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ytfetch')
    ap.add_argument('pyz')
    ap.add_argument('--speed', type=float, default=4)
    ap.add_argument('--ahead', type=int, default=20000)
    ap.add_argument('--behind', type=int, default=8000)
    ap.add_argument('--jump', type=int, default=60000, help='forward jump (ms) when playback reaches 40 s')
    a = ap.parse_args()
    base = '/dev/shm/rt-live'
    shutil.rmtree(base, ignore_errors=True)
    ram, spill, whole, cache = (os.path.join(base, x) for x in ('ram', 'spill', 'whole', 'cache'))
    for d in (ram, spill, whole, cache):
        os.makedirs(d)
    lease = os.path.join(base, 'lease.json')
    with open(lease, 'w') as f:
        json.dump({'dns': ['1.1.1.1']}, f)

    st = {'play': 0.0, 'started': None, 'fetched': 0, 'peak': 0, 'trims': [], 'max_ahead': 0, 'jumped': False,
          'samples': []}
    lock = threading.Lock()

    def on_event(e, p):
        with lock:
            if e['ev'] == 'video':
                st['fetched'] = e['ms']
                if st['started'] is None and e['ms'] >= 6000:
                    st['started'] = time.monotonic()      # playback starts at 6 s fetched, as ytd.js does
                    threading.Thread(target=clock, args=(p,), daemon=True).start()
                if st['started'] is not None:
                    st['max_ahead'] = max(st['max_ahead'], e['ms'] - st['play'])
            elif e['ev'] == 'trim':
                st['trims'].append((e['ms'], e['bytes']))

    def clock(p):
        try:
            run_clock(p)
        except Exception as e:  # noqa: BLE001 - said, not silent
            print('CLOCK THREAD DIED: %r' % e, flush=True)
            raise

    def run_clock(p):
        last, said = time.monotonic(), 0
        while p.poll() is None:
            if time.monotonic() - said > 2:
                said = time.monotonic()
                print('  t=%.0fs play=%.1fs fetched=%.1fs ram=%.1fMB' % (said - t0, st['play'] / 1000, st['fetched'] / 1000,
                                                                     du(ram) / 1e6), flush=True)
            time.sleep(0.25)
            now = time.monotonic()
            with lock:
                st['play'] += (now - last) * 1000 * a.speed
                if not st['jumped'] and st['play'] >= 40000:
                    st['play'] += a.jump
                    st['jumped'] = True
                if st['play'] > st['fetched']:            # buffering: playback waits for the video, as the player does
                    st['play'] = st['fetched']
                play = int(st['play'])
                used = du(ram)
                st['peak'] = max(st['peak'], used)
                st['samples'].append((round(play / 1000), round(st['fetched'] / 1000), round(used / 1048576, 1)))
            last = now
            try:
                p.stdin.write('pos %d\n' % play)
                p.stdin.flush()
            except (BrokenPipeError, ValueError):
                return

    t0 = time.monotonic()
    rc, evs, err = fetch(a.ytfetch, a.pyz, ram, cache, lease,
                         ['--stream', '%d,%d' % (a.ahead, a.behind), '--spill-dir', spill], on_event)
    t_stream = time.monotonic() - t0
    kinds = [e['ev'] for e in evs]
    print('streamed fetch: exit %d in %.0f s, events %s' % (rc, t_stream, {k: kinds.count(k) for k in dict.fromkeys(kinds)}))
    if rc != 0:
        print(err[-3000:])
        print([e for e in evs if e['ev'] == 'error'])
        sys.exit(1)
    s = next(e for e in evs if e['ev'] in ('stream', 'spill'))
    print('decision:', s)
    last_v = [e for e in evs if e['ev'] == 'video'][-1]
    print('video: %d ms, %d frames, %.1f MB demuxed, %.1f MB downloaded, waited %s s for room' % (
        last_v['ms'], last_v['frames'], last_v['bytes'] / 1e6, last_v.get('dl', 0) / 1e6, last_v.get('waited')))
    print('RAM folder peak: %.1f MB (whole video would be %.1f MB); trims: %d, last at %s' % (
        st['peak'] / 1e6, last_v['bytes'] / 1e6, len(st['trims']), st['trims'][-1] if st['trims'] else None))
    print('most fetched ahead of playback: %.1f s (window %.0f s + one 2 MiB chunk)' % (st['max_ahead'] / 1000, a.ahead / 1000))
    print('samples (play s, fetched s, RAM MB):', st['samples'][::max(1, len(st['samples']) // 12)])
    print('files:', sorted(os.listdir(ram)), 'spill folder empty:', os.listdir(spill) == [])

    rc2, evs2, err2 = fetch(a.ytfetch, a.pyz, whole, cache, lease, [])
    print('whole fetch: exit %d' % rc2)
    if rc2 != 0:
        print(err2[-2000:])
        sys.exit(1)
    ra, rb = records(os.path.join(ram, 'index.bin')), records(os.path.join(whole, 'index.bin'))
    print('index: %d records streamed, %d whole, identical: %s' % (len(ra), len(rb), ra == rb))
    cut = st['trims'][-1][1] if st['trims'] else 0
    with open(os.path.join(ram, 'video.h264'), 'rb') as f1, open(os.path.join(whole, 'video.h264'), 'rb') as f2:
        b1, b2 = f1.read(), f2.read()
    print('video.h264: %d bytes streamed, %d whole; past the punched %d: identical %s; punched part all zeros: %s' % (
        len(b1), len(b2), cut, b1[cut:] == b2[cut:], b1[:cut].count(0) == cut))
    with open(os.path.join(ram, 'audio.m4a'), 'rb') as f1, open(os.path.join(whole, 'audio.m4a'), 'rb') as f2:
        print('audio.m4a identical:', f1.read() == f2.read())
    keys = [r for r in ra if r[3]]
    ok_cut = any(r[1] == cut for r in keys) if cut else True
    print('the cut is at a keyframe:', ok_cut)
    shutil.rmtree(base, ignore_errors=True)
    good = ra == rb and b1[cut:] == b2[cut:] and ok_cut and st['peak'] < last_v['bytes']
    print('LIVE STREAM CHECK:', 'PASS' if good else 'FAIL')
    sys.exit(0 if good else 1)


if __name__ == '__main__':
    main()
