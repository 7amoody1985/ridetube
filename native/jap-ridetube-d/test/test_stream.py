#!/usr/bin/env python3
"""ytfetch.py's "stream the video through RAM" tests (WP8), offline: python3 -I test/test_stream.py [-v]

Window (the position feed), Source (Range requests that retry and refresh the URL), PacedReader, Prefixed,
parse_sidx, stream_layout + demux_video from a fragment (a real ffmpeg fMP4 with a sidx inserted), Trimmer
(hole punching) and plan_stream. Only the ffmpeg tests are skipped without ffmpeg; the punching ones without a
file system that frees blocks.
"""
import http.server
import io
import json
import os
import random
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]
import ytfetch  # noqa: E402

FF = shutil.which('ffmpeg')
TMP = tempfile.gettempdir()
FRAG = ['-movflags', 'frag_keyframe+empty_moov+default_base_moof']
WAIT = 10  # s: an upper bound for things that must happen, never slept for


def events(fn):
    out, old = io.StringIO(), ytfetch._out
    ytfetch._out = out
    try:
        fn()
    finally:
        ytfetch._out = old
    return [json.loads(x) for x in out.getvalue().splitlines()]


def in_thread(fn):
    """Run fn in a thread: (thread, result list holding ('ok', value) or ('err', exception))."""
    res = []

    def run():
        try:
            res.append(('ok', fn()))
        except BaseException as e:  # noqa: BLE001
            res.append(('err', e))
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, res


def poke(w, **kw):
    """set Window attributes and wake whoever waits"""
    with w.cv:
        for k, v in kw.items():
            setattr(w, k, v)
        w.cv.notify_all()


# ---------------------------------------------------------------- Window

class WindowTests(unittest.TestCase):
    def test_listen_reads_pos_lines_and_ignores_junk(self):
        r, wfd = os.pipe()
        rf, wf = os.fdopen(r, 'r'), os.fdopen(wfd, 'w')
        self.addCleanup(rf.close)
        w = ytfetch.Window(1000, 1000)
        w.listen(rf)
        wf.write('pos 700\n')
        wf.flush()
        with w.cv:
            self.assertTrue(w.cv.wait_for(lambda: w.play == 700, WAIT))
        self.assertFalse(w.gone, 'the pipe is still open')
        # junk after the last good line must change nothing
        wf.write('\nhello\npos\npos abc\npos -5\npos 1 2\nposx 9\npos 1.5\nseek 9\n')
        wf.flush()
        wf.close()  # the feed closes: ytd.js is gone
        with w.cv:
            self.assertTrue(w.cv.wait_for(lambda: w.gone, WAIT))
        self.assertEqual(w.play, 700)
        with self.assertRaises(OSError):
            w.wait_room(lambda: True)
        with self.assertRaises(OSError):  # even while full
            w.wait_room(lambda: False)

    def test_wait_room_blocks_while_ahead_is_full_then_returns(self):
        w = ytfetch.Window(500, 100)
        w.fetched = 1000          # 1000 past play 0 > ahead 500
        t, res = in_thread(lambda: w.wait_room(lambda: True))
        t.join(0.4)
        self.assertTrue(t.is_alive(), 'must wait while fetched - play > ahead')
        poke(w, play=400)         # 600 > 500: still full
        t.join(0.3)
        self.assertTrue(t.is_alive())
        poke(w, play=500)         # exactly ahead: room
        t.join(WAIT)
        self.assertFalse(t.is_alive())
        self.assertEqual(res, [('ok', None)])
        self.assertGreater(w.waited, 0.3)

    def test_wait_room_blocks_while_ram_is_short(self):
        w = ytfetch.Window(500, 100)
        free = [False]
        t, res = in_thread(lambda: w.wait_room(lambda: free[0]))
        t.join(0.4)
        self.assertTrue(t.is_alive(), 'must wait while free_ok() is False')
        free[0] = True
        poke(w)
        t.join(WAIT)
        self.assertEqual(res, [('ok', None)])

    def test_no_wait_when_there_is_room(self):
        w = ytfetch.Window(500, 100, play=2000)
        self.assertEqual((w.play, w.fetched), (2000, 2000))
        w.wait_room(lambda: True)
        self.assertLess(w.waited, 0.5)


# ---------------------------------------------------------------- a Range server

class RangeServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, *a):
        pass


class _H(http.server.BaseHTTPRequestHandler):
    """GET + Range -> 206. server.script: one entry per request, popped first: 'reset' (hang up without an answer),
    an int (that HTTP error) or None (serve). server.dead: paths that always answer 403."""

    def do_GET(self):  # noqa: N802
        srv = self.server
        srv.seen.append((self.path, self.headers.get('Range'), self.headers.get('X-T')))
        step = srv.script.pop(0) if srv.script else None
        if self.path in srv.dead:
            step = 403
        if step == 'reset':
            self.close_connection = True
            return
        if step:
            self.send_error(step)
            return
        s, e = (int(x) for x in self.headers['Range'].split('=')[1].split('-'))
        body = srv.data[s:e + 1]
        self.send_response(206)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except ConnectionError:
            pass

    def log_message(self, *a):
        pass


DATA = random.Random(7).randbytes(60000)


class Served(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = RangeServer(('127.0.0.1', 0), _H)
        cls.srv.data = DATA
        cls.base = f'http://127.0.0.1:{cls.srv.server_address[1]}'
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.srv.seen, self.srv.script, self.srv.dead = [], [], set()
        self.addCleanup(setattr, ytfetch, 'NET_BACKOFF', ytfetch.NET_BACKOFF)
        ytfetch.NET_BACKOFF = (0.01,)
        self.w = ytfetch.Window(10 ** 9, 0)

    def source(self, path='/v', refresh=None, **kw):
        return ytfetch.Source(dict({'url': self.base + path, 'filesize': len(DATA), 'format_id': '137',
                                    'http_headers': {'X-T': 'old'}}, **kw), self.w, refresh, timeout=5)


class SourceTests(Served):
    def test_ranges_are_byte_identical(self):
        src = self.source()
        n = len(DATA)
        for s, e in ((0, 1), (0, 8), (10, 5000), (777, 59999), (n - 100, n), (0, n), (n - 1, n)):
            self.assertEqual(src.get(s, e), DATA[s:e], (s, e))
        self.assertEqual(self.srv.seen[1][1], 'bytes=0-7', 'bytes=s-(e-1)')
        self.assertEqual(self.srv.seen[0][2], 'old', 'the format\'s headers go along')
        self.assertEqual(events(lambda: src.get(0, 10)), [], 'a link that works says nothing')

    def test_retries_until_it_works_with_one_event_down_and_one_up(self):
        for mode in ('reset', 500):
            for n in (1, 3):
                with self.subTest(mode=mode, tries=n):
                    self.srv.script[:] = [mode] * n
                    self.srv.seen.clear()
                    src = self.source()
                    got = []
                    evs = events(lambda: got.append(src.get(100, 2100)))
                    self.assertEqual(got, [DATA[100:2100]])
                    self.assertEqual(len(self.srv.seen), n + 1)
                    self.assertEqual(len(evs), 2, evs)
                    self.assertEqual((evs[0]['ev'], evs[0]['ok']), ('net', False))
                    self.assertTrue(evs[0]['msg'] and isinstance(evs[0]['msg'], str))
                    self.assertEqual(evs[1], {'ev': 'net', 'ok': True, 'tries': n})
                    self.assertEqual(src.down, 0)
                    # healthy again: silent
                    self.assertEqual(events(lambda: src.get(0, 5)), [])

    def test_http_500_message_names_the_status(self):
        self.srv.script[:] = [500]
        evs = events(lambda: self.source().get(0, 10))
        self.assertIn('500', evs[0]['msg'])

    def test_backoff_steps_up_and_stays_on_the_last(self):
        waits = []
        ytfetch.NET_BACKOFF = (0.01, 0.02, 0.03)
        src = self.source()
        cv = self.w.cv

        class CV:
            def __enter__(s):
                return cv.__enter__()

            def __exit__(s, *a):
                return cv.__exit__(*a)

            def wait(s, t):
                waits.append(t)
                return True
        self.w.cv = CV()
        self.srv.script[:] = [500] * 5
        events(lambda: src.get(0, 10))
        self.assertEqual(waits, [0.01, 0.02, 0.03, 0.03, 0.03])

    def test_403_looks_the_url_up_again_and_carries_on(self):
        self.srv.dead = {'/old'}
        calls = []

        def refresh(fid):
            calls.append(fid)
            return {'url': self.base + '/new', 'filesize': len(DATA), 'http_headers': {'X-T': 'new'}}
        src = self.source('/old', refresh)
        got = []
        evs = events(lambda: got.append(src.get(5, 905)))
        self.assertEqual(got, [DATA[5:905]])
        self.assertEqual(calls, ['137'])
        self.assertEqual((src.url, src.headers['X-T'], src.refreshed), (self.base + '/new', 'new', 1))
        self.assertEqual([p for p, _, _ in self.srv.seen], ['/old', '/new'], 'at once with the new URL')
        self.assertEqual(evs, [], 'a refresh is not a down link')
        self.assertEqual(events(lambda: src.get(0, 10)), [])
        self.assertEqual(self.srv.seen[-1][0], '/new', 'and it stays on the new one')

    def test_refresh_without_filesize_or_headers_keeps_what_it_had(self):
        self.srv.dead = {'/old'}
        src = self.source('/old', lambda fid: {'url': self.base + '/new'})
        self.assertEqual(src.get(0, 10), DATA[:10])
        self.assertEqual((src.url, src.headers, src.size), (self.base + '/new', {'X-T': 'old'}, len(DATA)))

    def test_refresh_finding_another_size_does_not_switch(self):
        self.srv.dead = {'/old'}
        calls = []

        def refresh(fid):
            calls.append(fid)
            if len(calls) == 2:
                poke(self.w, gone=True)   # ytd.js leaves while the lookup keeps failing
            return {'url': self.base + '/new', 'filesize': len(DATA) + 1}
        src = self.source('/old', refresh)
        evs, err = [], []

        def run():
            try:
                src.get(0, 10)
            except OSError as e:
                err.append(e)
        evs = events(run)
        self.assertEqual(len(err), 1)
        self.assertEqual((src.url, src.refreshed), (self.base + '/old', 0), 'no switch')
        self.assertEqual(len(calls), 2)
        self.assertNotIn('/new', [p for p, _, _ in self.srv.seen])
        self.assertEqual(len(evs), 1, evs)
        self.assertIn('format changed size', evs[0]['msg'])

    def test_refresh_that_fails_is_tried_again_with_the_link(self):
        self.srv.dead = {'/old'}
        calls = []

        def refresh(fid):
            calls.append(1)
            if len(calls) < 3:
                raise OSError('lookup: no link')
            return {'url': self.base + '/new', 'filesize': len(DATA)}
        src = self.source('/old', refresh)
        got = []
        evs = events(lambda: got.append(src.get(0, 10)))
        self.assertEqual(got, [DATA[:10]])
        self.assertEqual(len(calls), 3)
        self.assertEqual([e['ok'] for e in evs], [False, True])
        self.assertIn('lookup: no link', evs[0]['msg'])
        self.assertEqual(evs[1]['tries'], 2)

    def test_403_without_a_refresh_function_is_just_a_failed_try(self):
        self.srv.script[:] = [403, 403]
        src = self.source()
        got = []
        evs = events(lambda: got.append(src.get(0, 10)))
        self.assertEqual(got, [DATA[:10]])
        self.assertEqual([e['ok'] for e in evs], [False, True])
        self.assertEqual(src.refreshed, 0)

    def test_gone_window_ends_the_retry_loop(self):
        poke(self.w, gone=True)
        self.srv.script[:] = [500] * 1000
        src = self.source()
        err = []

        def run():
            with self.assertRaises(OSError) as c:
                src.get(0, 10)
            err.append(c.exception)
        evs = events(run)
        self.assertEqual(len(err), 1)
        self.assertEqual(evs, [], 'no event: it did not even count as down')
        self.assertEqual(len(self.srv.seen), 1)

    def test_window_closing_while_the_link_is_down_stops_it(self):
        ytfetch.NET_BACKOFF = (0.2,)
        self.srv.script[:] = [500] * 10000
        src = self.source()
        out, old = io.StringIO(), ytfetch._out
        ytfetch._out = out
        try:
            t, res = in_thread(lambda: src.get(0, 10))
            for _ in range(WAIT * 100):
                if out.getvalue():
                    break
                threading.Event().wait(0.01)
            self.assertTrue(out.getvalue(), 'it said the link is down')
            poke(self.w, gone=True)
            t.join(WAIT)
        finally:
            ytfetch._out = old
        self.assertFalse(t.is_alive())
        self.assertEqual([r[0] for r in res], ['err'])
        self.assertIsInstance(res[0][1], OSError)

    def test_short_body_is_a_failed_try(self):
        class Short(_H):
            def do_GET(self):  # noqa: N802
                self.server.n += 1
                if self.server.n == 1:
                    body = DATA[:5]
                    self.send_response(206)
                    self.send_header('Content-Length', '10')   # promises 10, sends 5
                    self.end_headers()
                    self.wfile.write(body)
                    self.close_connection = True
                    return
                _H.do_GET(self)
        srv = RangeServer(('127.0.0.1', 0), Short)
        srv.data, srv.seen, srv.script, srv.dead, srv.n = DATA, [], [], set(), 0
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        src = ytfetch.Source({'url': f'http://127.0.0.1:{srv.server_address[1]}/', 'filesize': len(DATA)}, self.w, timeout=5)
        got = []
        evs = events(lambda: got.append(src.get(0, 10)))
        self.assertEqual(got, [DATA[:10]])
        self.assertEqual([e['ok'] for e in evs], [False, True])


# ---------------------------------------------------------------- PacedReader

class PacedReaderTests(Served):
    def test_from_a_nonzero_start_it_returns_exactly_the_tail(self):
        start = 12345
        src = self.source()
        rd = ytfetch.PacedReader(src, start, self.w, lambda: True, chunk=4096)
        out = bytearray()
        while True:
            b = rd.read(1000)
            if not b:
                break
            out += b
        self.assertEqual(bytes(out), DATA[start:])
        self.assertEqual(rd.bytes, len(DATA) - start)
        self.assertEqual(self.srv.seen[0][1], f'bytes={start}-{start + 4095}')
        self.assertEqual(self.srv.seen[-1][1], f'bytes={start + 4096 * ((len(DATA) - start - 1) // 4096)}-{len(DATA) - 1}',
                         'the last range ends at the file\'s end')
        self.assertEqual(rd.read(10), b'', 'and stays at EOF')

    def test_reads_larger_than_a_chunk_and_exact_boundaries(self):
        rd = ytfetch.PacedReader(self.source(), 0, self.w, lambda: True, chunk=1000)
        got = rd.read(2500) + rd.read(500) + rd.read(1) + rd.read(10 ** 6)
        self.assertEqual(got, DATA)

    def test_waits_for_room_without_a_new_request_and_says_so_once(self):
        w = self.w = ytfetch.Window(500, 0)
        said, saying = [], threading.Event()

        def before():
            said.append(len(self.srv.seen))
            saying.set()
        rd = ytfetch.PacedReader(self.source(), 300, w, lambda: True, chunk=1000, before_wait=before)
        self.assertEqual(rd.read(10), DATA[300:310])
        self.assertEqual((len(self.srv.seen), said), (1, []), 'room: no wait, no word')
        w.fetched = 1000                       # 1000 past the play position 0: full
        self.assertEqual(rd.read(990), DATA[310:1300], 'the buffer needs no request, so no wait either')
        self.assertEqual((len(self.srv.seen), said), (1, []))
        t, res = in_thread(lambda: rd.read(10))
        self.assertTrue(saying.wait(WAIT), 'before_wait is called when it must wait')
        t.join(0.4)
        self.assertTrue(t.is_alive(), 'waiting for room')
        self.assertEqual(len(self.srv.seen), 1, 'no new Range request while full')
        poke(w, play=900)                      # 100 ahead of play: room
        t.join(WAIT)
        self.assertEqual(res, [('ok', DATA[1300:1310])])
        self.assertEqual(len(self.srv.seen), 2)
        self.assertEqual(said, [1], 'once, before the one wait')

    def test_free_ram_gates_it_too(self):
        free, said = [False], threading.Event()
        rd = ytfetch.PacedReader(self.source(), 0, self.w, lambda: free[0], chunk=1000, before_wait=said.set)
        t, res = in_thread(lambda: rd.read(10))
        self.assertTrue(said.wait(WAIT))
        t.join(0.3)
        self.assertTrue(t.is_alive())
        self.assertEqual(self.srv.seen, [])
        free[0] = True
        poke(self.w)
        t.join(WAIT)
        self.assertEqual(res, [('ok', DATA[:10])])

    def test_window_gone_while_waiting_raises(self):
        w = self.w = ytfetch.Window(500, 0)
        w.fetched = 10 ** 6
        rd = ytfetch.PacedReader(self.source(), 0, w, lambda: True, chunk=1000)
        t, res = in_thread(lambda: rd.read(10))
        t.join(0.3)
        poke(w, gone=True)
        t.join(WAIT)
        self.assertEqual([r[0] for r in res], ['err'])
        self.assertIsInstance(res[0][1], OSError)


# ---------------------------------------------------------------- Prefixed

class PrefixedTests(unittest.TestCase):
    def test_prefix_then_inner_across_boundaries(self):
        prefix, body = b'abcdefg', bytes(range(100, 150))
        for n in (1, 2, 3, 6, 7, 8, 9, 13, 57, 58, 1000):
            with self.subTest(n=n):
                p = ytfetch.Prefixed(prefix, io.BytesIO(body))
                out, first = bytearray(), p.read(n)
                self.assertEqual(first, (prefix + body)[:n], 'the first read straddles the boundary when n > 7')
                out += first
                while True:
                    b = p.read(n)
                    if not b:
                        break
                    self.assertLessEqual(len(b), n)
                    out += b
                self.assertEqual(bytes(out), prefix + body)
                self.assertEqual(p.read(n), b'')

    def test_empty_prefix_and_empty_inner(self):
        self.assertEqual(ytfetch.Prefixed(b'', io.BytesIO(b'xyz')).read(10), b'xyz')
        p = ytfetch.Prefixed(b'ab', io.BytesIO(b''))
        self.assertEqual((p.read(1), p.read(5), p.read(5)), (b'a', b'b', b''))

    def test_demux_style_box_reads(self):
        """read_box on a Prefixed: a box header split across the prefix and the stream"""
        moov = struct.pack('>I4s', 12, b'moov') + b'ABCD'
        mdat = struct.pack('>I4s', 11, b'mdat') + b'xyz'
        p = ytfetch.Prefixed(moov[:3] + b'', io.BytesIO(moov[3:] + mdat))
        self.assertEqual(ytfetch.read_box(p), (b'moov', moov))
        self.assertEqual(ytfetch.read_box(p), (b'mdat', mdat))
        self.assertIsNone(ytfetch.read_box(p))


# ---------------------------------------------------------------- parse_sidx

def sidx_box(version, ts, ept, first, refs):
    """refs: [(reference_type, size, duration, starts_with_sap, sap_type)]"""
    body = struct.pack('>II', 1, ts)
    body += struct.pack('>QQ' if version else '>II', ept, first)
    body += struct.pack('>HH', 0, len(refs))
    for rt, size, dur, sap, st in refs:
        body += struct.pack('>III', rt << 31 | size, dur, sap << 31 | st << 28)
    return ytfetch.full(b'sidx', version << 24, body)


class SidxTests(unittest.TestCase):
    REFS = [(0, 1000, 90000, 1, 1), (0, 2500, 45000, 1, 1), (0, 70000, 123456, 0, 0), (0, 0x7fffffff, 1, 1, 2)]
    WANT = [(1000, 90000, 1), (2500, 45000, 1), (70000, 123456, 0), (0x7fffffff, 1, 1)]

    def test_version_0(self):
        b = sidx_box(0, 90000, 12345, 678, self.REFS)
        self.assertEqual(ytfetch.parse_sidx(b), (90000, 12345, 678, self.WANT))

    def test_version_1_with_64_bit_fields(self):
        b = sidx_box(1, 12800, 5 << 33, 1 << 33, self.REFS)
        self.assertEqual(ytfetch.parse_sidx(b), (12800, 5 << 33, 1 << 33, self.WANT))

    def test_no_references(self):
        self.assertEqual(ytfetch.parse_sidx(sidx_box(0, 1000, 0, 0, [])), (1000, 0, 0, []))

    def test_a_hierarchical_index_is_refused(self):
        b = sidx_box(0, 1000, 0, 0, [(0, 10, 1, 1, 1), (1, 10, 1, 1, 1)])
        with self.assertRaises(ValueError):
            ytfetch.parse_sidx(b)


# ---------------------------------------------------------------- a real fMP4 with a sidx

def ff(*args):
    subprocess.run([FF, '-v', 'error', '-y', *args], check=True)


def read_index(path):
    """(header bytes, [(pts_ms, pos, size, key)]) of an index.bin"""
    with open(path, 'rb') as f:
        b = f.read()
    n = struct.unpack_from('<I', b, 16)[0]
    return b[:ytfetch.HDR.size], [ytfetch.REC.unpack_from(b, ytfetch.HDR.size + i * ytfetch.REC.size) for i in range(n)]


def streamable(data):
    """ffmpeg's fragmented MP4 has no sidx: rebuild it as ftyp, moov, a version-0 sidx (one reference per
    moof+mdat, SAP type 1), then the fragments. Returns (file, info): info has moov, ts, firsts (each
    fragment's first dts), counts (samples per fragment), base (min dts+cto of the first fragment), offsets
    (each moof's position in file)."""
    tops = [(t, s - 8, e) for t, s, e in ytfetch.boxes(data)]
    moov_at, moov_end = next((s, e) for t, s, e in tops if t == b'moov')
    moov = data[moov_at:moov_end]
    tk = ytfetch.trak_info(moov)
    frags = []         # (moof start, moof end, mdat end)
    for i, (t, s, e) in enumerate(tops):
        if t == b'moof':
            assert tops[i + 1][0] == b'mdat' and tops[i + 1][1] == e
            frags.append((s, e, tops[i + 1][2]))
    firsts, counts, dts, base = [], [], 0, None
    for s, e, _ in frags:
        samples, dts_end = ytfetch.parse_moof(data[s:e], dts, tk['trex'])
        if base is None:
            base = min(x[2] + x[3] for x in samples)
        firsts.append(samples[0][2])
        counts.append(len(samples))
        dts = dts_end
    durs = [b - a for a, b in zip(firsts, firsts[1:] + [dts])]
    sizes = [m - s for s, _, m in frags]
    refs = b''.join(struct.pack('>III', sz, d, 1 << 31 | 1 << 28) for sz, d in zip(sizes, durs))
    sidx = ytfetch.full(b'sidx', 0, struct.pack('>IIIIHH', 1, tk['ts'], firsts[0], 0, 0, len(frags)), refs)
    head = data[:moov_end] + sidx
    out = head + data[frags[0][0]:frags[-1][2]]
    offsets = [len(head) + s - frags[0][0] for s, _, _ in frags]
    return out, dict(moov=moov, ts=tk['ts'], firsts=firsts, counts=counts, base=base, offsets=offsets)


@unittest.skipUnless(FF, 'needs ffmpeg')
class Fragmented(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir=TMP)
        src, v = os.path.join(cls.tmp, 'src.mp4'), os.path.join(cls.tmp, 'v.mp4')
        ff('-f', 'lavfi', '-i', 'testsrc2=size=426x240:rate=30', '-frames:v', '600', '-c:v', 'libx264',
           '-preset', 'veryfast', '-bf', '2', '-g', '30', '-pix_fmt', 'yuv420p', '-an', *FRAG, v)
        with open(v, 'rb') as f:
            raw = f.read()
        cls.raw_boxes = [t for t, _, _ in ytfetch.boxes(raw)]
        cls.file, cls.info = streamable(raw)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def sub(self):
        return tempfile.mkdtemp(dir=self.tmp)

    def layout(self):
        return ytfetch.stream_layout(lambda s, e: self.file[s:e])

    def test_fixture_shape(self):
        self.assertEqual(self.raw_boxes[:2], [b'ftyp', b'moov'])
        self.assertNotIn(b'sidx', self.raw_boxes, 'ffmpeg writes none: that is why the test builds one')
        self.assertEqual(len(self.info['offsets']), 20)
        self.assertEqual(set(self.info['counts']), {30})

    def test_stream_layout(self):
        lay, info = self.layout(), self.info
        self.assertEqual(lay['moov'], info['moov'])
        self.assertEqual(lay['end'], len(self.file))
        self.assertEqual(lay['base'], info['base'])
        self.assertEqual([o for o, _ in lay['frags']], info['offsets'])
        ms = [m for _, m in lay['frags']]
        self.assertEqual(ms[0], 0)
        self.assertTrue(all(a < b for a, b in zip(ms, ms[1:])), ms)
        self.assertEqual(ms, [max(0, round((d - info['base']) * 1000 / info['ts'])) for d in info['firsts']])
        for o, _ in lay['frags']:
            self.assertEqual(self.file[o + 4:o + 8], b'moof')

    def test_stream_layout_with_a_small_head_window_and_a_tiny_get(self):
        """the boxes straddle the first read: it asks for more"""
        with mock.patch.object(ytfetch, 'HEAD_BYTES', 300):
            lay = self.layout()
        self.assertEqual((lay['moov'], lay['end']), (self.info['moov'], len(self.file)))
        self.assertEqual([o for o, _ in lay['frags']], self.info['offsets'])

    def test_stream_layout_none_without_a_sidx_or_with_a_wrong_one(self):
        info = self.info
        sidx_at = self.file.index(b'sidx') - 4
        moof_at = info['offsets'][0]
        nosidx = self.file[:sidx_at] + self.file[moof_at:]
        self.assertIsNone(ytfetch.stream_layout(lambda s, e: nosidx[s:e]))
        # a reference that does not start with a SAP: not a place to start from
        bad = bytearray(self.file)
        bad[sidx_at + 32 + 8] &= 0x7f   # the first reference's SAP bit
        self.assertIsNone(ytfetch.stream_layout(lambda s, e: bytes(bad[s:e])))
        # a timescale that is not the track's
        bad = bytearray(self.file)
        struct.pack_into('>I', bad, sidx_at + 16, info['ts'] + 1)
        self.assertIsNone(ytfetch.stream_layout(lambda s, e: bytes(bad[s:e])))

    def demux(self, f, base=None):
        d = self.sub()
        seen = []
        r = ytfetch.demux_video(f, d, None, lambda *x: seen.append(x), base=base)
        hdr, recs = read_index(os.path.join(d, 'index.bin'))
        with open(os.path.join(d, 'video.h264'), 'rb') as g:
            return r, hdr, recs, g.read(), seen

    def test_demux_from_a_fragment_matches_the_tail_of_the_whole(self):
        lay, info = self.layout(), self.info
        (n1, size1, ms1), hdr1, r1, v1, _ = self.demux(io.BytesIO(self.file))
        self.assertEqual((n1, len(r1), size1, len(v1)), (600, 600, len(v1), len(v1)))
        for k in (0, 1, 9, len(lay['frags']) // 2, len(lay['frags']) - 1):
            with self.subTest(fragment=k):
                off = lay['frags'][k][0]
                f = ytfetch.Prefixed(lay['moov'], io.BytesIO(self.file[off:]))
                (n2, size2, _), hdr2, r2, v2, seen = self.demux(f, base=lay['base'])
                j = sum(info['counts'][:k])
                self.assertEqual(n2, len(r2))
                self.assertEqual(n2, len(r1) - j)
                self.assertTrue(r2[0][3], 'starts on a keyframe')
                self.assertEqual(r2[0][1], 0)
                self.assertEqual(r2[0][0], r1[j][0], 'the same ms as from 0')
                self.assertEqual([(m, s, key) for m, _, s, key in r2], [(m, s, key) for m, _, s, key in r1[j:]])
                shift = r1[j][1]
                self.assertEqual([p + shift for _, p, _, _ in r2], [p for _, p, _, _ in r1[j:]], 'pos differs by a constant')
                self.assertEqual(v2, v1[shift:], 'the same bytes from that record on')
                self.assertEqual(hdr2[:16] + hdr2[20:], hdr1[:16] + hdr1[20:], 'the same header but the frame count')
                self.assertEqual(seen[-1], (max(m for m, _, _, _ in r2), n2, size2))

    def test_demux_from_the_first_fragment_equals_from_zero(self):
        lay = self.layout()
        _, hdr1, r1, v1, _ = self.demux(io.BytesIO(self.file))
        off = lay['frags'][0][0]
        _, hdr2, r2, v2, _ = self.demux(ytfetch.Prefixed(lay['moov'], io.BytesIO(self.file[off:])), base=lay['base'])
        self.assertEqual((hdr2, r2, v2), (hdr1, r1, v1))

    def test_layout_base_is_what_demux_takes_from_zero(self):
        """the first record's ms is 0 from 0, so base is the first fragment's earliest pts; without base a
        stream starting at fragment k would number its frames from 0 instead"""
        lay = self.layout()
        _, _, r1, _, _ = self.demux(io.BytesIO(self.file))
        self.assertEqual(min(r[0] for r in r1), 0)
        k = 5
        off = lay['frags'][k][0]
        _, _, r_nobase, _, _ = self.demux(ytfetch.Prefixed(lay['moov'], io.BytesIO(self.file[off:])))
        self.assertEqual(r_nobase[0][0], 0)
        self.assertNotEqual(r1[sum(self.info['counts'][:k])][0], 0)


# ---------------------------------------------------------------- Trimmer

PUNCH = ytfetch.punch_fn()


@unittest.skipUnless(PUNCH, 'no fallocate through libc here')
class TrimmerTests(unittest.TestCase):
    KEY = 512 << 10      # bytes between keyframes
    N = 16               # keyframes, 1 s apart: 8 MiB

    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=TMP)
        self.addCleanup(shutil.rmtree, self.tmp)
        if not ytfetch.can_punch(self.tmp, PUNCH):
            self.skipTest('this file system does not free punched blocks')
        self.path = os.path.join(self.tmp, 'video.h264')
        self.data = random.Random(3).randbytes(self.N * self.KEY)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        self.addCleanup(os.close, self.fd)
        os.write(self.fd, self.data)
        os.fsync(self.fd)

    def trimmer(self, behind=2000, play=0):
        w = ytfetch.Window(60000, behind, play)
        t = ytfetch.Trimmer(w, PUNCH)
        for i in range(self.N):
            t.key(i * 1000, i * self.KEY)
        return w, t

    def used(self):
        os.fsync(self.fd)
        return os.fstat(self.fd).st_blocks * 512

    def test_punches_up_to_the_last_keyframe_behind_the_play_position(self):
        w, t = self.trimmer(behind=2000)
        before = self.used()
        self.assertEqual(os.fstat(self.fd).st_size, self.N * self.KEY)
        w.play = 10000      # cut = 8000 ms: the keyframe at 8000 ms is the last at or before it
        evs = events(lambda: t.after_write(self.fd))
        self.assertEqual(evs, [{'ev': 'trim', 'ms': 8000, 'bytes': 8 * self.KEY}])
        self.assertEqual((t.done, t.ms), (8 * self.KEY, 8000))
        self.assertEqual(t.keys[0], (8000, 8 * self.KEY), 'keys before it are forgotten')
        self.assertEqual(os.fstat(self.fd).st_size, self.N * self.KEY, 'offsets stay')
        after = self.used()
        self.assertLess(after, before)
        self.assertLessEqual(after, before - 8 * self.KEY + (64 << 10), 'the 4 MiB behind are freed')
        self.assertEqual(os.pread(self.fd, 4096, 0), bytes(4096), 'a hole reads as zeros')
        self.assertEqual(os.pread(self.fd, 8 * self.KEY, 0), bytes(8 * self.KEY))
        self.assertEqual(os.pread(self.fd, 4 * self.KEY, 8 * self.KEY), self.data[8 * self.KEY:12 * self.KEY],
                         'and what is at and past the keyframe is intact')

    def test_does_nothing_below_trim_min_or_before_the_first_keyframe_is_behind(self):
        w, t = self.trimmer(behind=2000)
        before = self.used()
        for play in (0, 1500, 2000, 2999):          # cut <= 999: the keyframe at 0 is no distance from 0
            w.play = play
            self.assertEqual(events(lambda: t.after_write(self.fd)), [], play)
        w.play = 3000                               # cut 1000: key at 1000 is 512 KiB < TRIM_MIN
        self.assertEqual(events(lambda: t.after_write(self.fd)), [])
        self.assertLess(self.KEY, ytfetch.TRIM_MIN)
        self.assertEqual((t.done, t.ms), (0, 0))
        self.assertEqual(self.used(), before)
        w.play = 4000                               # cut 2000: key at 2000 is exactly TRIM_MIN from 0: punch
        self.assertEqual(events(lambda: t.after_write(self.fd)), [{'ev': 'trim', 'ms': 2000, 'bytes': 1 << 20}])
        self.assertEqual(self.KEY * 2, ytfetch.TRIM_MIN)

    def test_next_punch_waits_for_trim_min_more(self):
        w, t = self.trimmer(behind=2000)
        w.play = 10000
        events(lambda: t.after_write(self.fd))      # done = 4 MiB at 8000 ms
        w.play = 11000                              # cut 9000: 512 KiB past done
        self.assertEqual(events(lambda: t.after_write(self.fd)), [])
        w.play = 12000                              # cut 10000: 1 MiB past done
        self.assertEqual(events(lambda: t.after_write(self.fd)), [{'ev': 'trim', 'ms': 10000, 'bytes': 10 * self.KEY}])
        self.assertEqual(os.pread(self.fd, 10 * self.KEY, 0), bytes(10 * self.KEY))
        self.assertEqual(os.pread(self.fd, self.KEY, 10 * self.KEY), self.data[10 * self.KEY:11 * self.KEY])
        w.play = 12000                              # again with nothing new: silent
        self.assertEqual(events(lambda: t.after_write(self.fd)), [])

    def test_no_keys_yet_is_a_noop_and_the_play_position_ahead_of_the_keys_uses_the_last(self):
        w = ytfetch.Window(60000, 2000, 99999)
        t = ytfetch.Trimmer(w, PUNCH)
        self.assertEqual(events(lambda: t.after_write(self.fd)), [])
        w2, t2 = self.trimmer(behind=0)
        w2.play = 10 ** 6                            # far past the last key (15000 ms at 7.5 MiB)
        evs = events(lambda: t2.after_write(self.fd))
        self.assertEqual(evs, [{'ev': 'trim', 'ms': 15000, 'bytes': 15 * self.KEY}])


# ---------------------------------------------------------------- plan_stream

MiB = 1 << 20


class FakeYt:
    """a yt-dlp format selector: process_ie_result(info, download) -> a dict"""

    def __init__(self, fmt, wrap=False):
        self.fmt, self.wrap, self.calls = fmt, wrap, []

    def process_ie_result(self, info, download):
        assert download is False
        self.calls.append(info)
        if isinstance(self.fmt, Exception):
            raise self.fmt
        f = dict(self.fmt)
        return {'requested_downloads': [f]} if self.wrap else f


class PlanTests(unittest.TestCase):
    AHEAD, BEHIND, DUR = 30000, 10000, 100

    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=TMP)
        self.addCleanup(shutil.rmtree, self.tmp)
        self.spill = os.path.join(self.tmp, 'spill')
        os.mkdir(self.spill)
        self.ram = os.path.join(self.tmp, 'ram')
        os.mkdir(self.ram)
        if not (PUNCH and ytfetch.can_punch(self.ram, PUNCH)):
            self.skipTest('this file system does not free punched blocks')
        if ytfetch.ram_free(self.ram) < 256 * MiB:
            self.skipTest('too little free space here')
        self.info = {'id': 'x', 'duration': self.DUR, 'formats': []}

    def args(self, **kw):
        return types.SimpleNamespace(**dict(dict(stream=(self.AHEAD, self.BEHIND), dir=self.ram, spill_dir=self.spill,
                                                 budget=64 * MiB, start_ms=0, video_only=False), **kw))

    def vfmt(self, **kw):
        return dict({'format_id': '137', 'protocol': 'https', 'url': 'https://v/x', 'filesize': 10 * MiB}, **kw)

    def afmt(self, **kw):
        return dict({'format_id': '140', 'protocol': 'https', 'url': 'https://a/x', 'filesize': 1 * MiB}, **kw)

    def plan(self, a, fv=None, fa=None, wrap=False, stdin='pos 5\n'):
        yv, ya = FakeYt(fv or self.vfmt(), wrap), FakeYt(fa or self.afmt(), wrap)
        res = []
        with mock.patch.object(sys, 'stdin', io.StringIO(stdin)):
            evs = events(lambda: res.append(ytfetch.plan_stream(a, ya, yv, self.info)))
        return res[0], evs, yv, ya

    def need(self, vsize=10 * MiB, asize=1 * MiB):
        return int(2 * asize + vsize / self.DUR * (self.AHEAD + self.BEHIND) / 1000 + 3 * ytfetch.VIDEO_CHUNK
                   + ytfetch.RAM_FLOOR)

    def assertSpills(self, a, res, evs, why):
        self.assertIsNone(res)
        self.assertEqual(len(evs), 1, evs)
        self.assertEqual((evs[0]['ev'], evs[0]['dir']), ('spill', self.spill))
        self.assertTrue(evs[0]['why'].startswith(why), evs[0]['why'])
        self.assertEqual(a.dir, self.spill, 'the files go to flash now')

    def test_streams_when_it_fits(self):
        for wrap in (False, True):
            with self.subTest(requested_downloads=wrap):
                a = self.args()
                res, evs, yv, ya = self.plan(a, wrap=wrap)
                self.assertEqual(evs, [], 'plan_stream says nothing when it streams (fetch_stream does)')
                self.assertIsInstance(res, tuple)
                w, fv, punch, need = res
                self.assertIsInstance(w, ytfetch.Window)
                self.assertEqual((w.ahead, w.behind, w.fetched), (self.AHEAD, self.BEHIND, 0))
                self.assertEqual(fv['format_id'], '137')
                self.assertTrue(callable(punch))
                self.assertEqual(need, self.need())
                self.assertEqual(a.dir, self.ram, 'unchanged')
                self.assertEqual((len(yv.calls), len(ya.calls)), (1, 1))
                self.assertIsNot(yv.calls[0], self.info, 'works on a copy')
                with w.cv:
                    self.assertTrue(w.cv.wait_for(lambda: w.gone, WAIT), 'listening to stdin')
                self.assertEqual(w.play, 5)

    def test_start_ms_is_the_windows_start(self):
        a = self.args(start_ms=42000)
        res, _, _, _ = self.plan(a, stdin='')
        self.assertEqual((res[0].play, res[0].fetched), (42000, 42000))

    def test_spills_past_the_budget(self):
        a = self.args(budget=self.need() - 1)
        res, evs, _, _ = self.plan(a)
        self.assertSpills(a, res, evs, 'needs ')
        self.assertIn('MiB of RAM', evs[0]['why'])
        a = self.args(budget=self.need())               # exactly: fits
        self.assertIsInstance(self.plan(a)[0], tuple)

    def test_a_bigger_window_or_video_needs_more(self):
        a = self.args(stream=(10 * self.AHEAD, 10 * self.BEHIND), budget=self.need() + MiB)
        res, evs, _, _ = self.plan(a)
        self.assertSpills(a, res, evs, 'needs ')

    def test_spills_without_ranges_or_url_or_filesize_or_duration(self):
        cases = [('protocol', self.vfmt(protocol='m3u8_native'), 'video not fetchable in ranges'),
                 ('filesize', self.vfmt(filesize=None), 'video not fetchable in ranges'),
                 ('url', self.vfmt(url=None), 'video not fetchable in ranges')]
        for name, fv, why in cases:
            with self.subTest(name):
                a = self.args()
                res, evs, _, _ = self.plan(a, fv=fv)
                self.assertSpills(a, res, evs, why)
        a = self.args()
        self.info['duration'] = None
        res, evs, _, _ = self.plan(a)
        self.assertSpills(a, res, evs, 'no duration')

    def test_http_counts_as_ranged(self):
        self.assertIsInstance(self.plan(self.args(), fv=self.vfmt(protocol='http'))[0], tuple)

    def test_format_lookup_failing_spills_with_the_reason(self):
        a = self.args()
        res, evs, _, _ = self.plan(a, fv=ValueError('no such format'))
        self.assertSpills(a, res, evs, 'formats: ')
        self.assertIn('no such format', evs[0]['why'])

    def test_no_hole_punching_spills(self):
        a = self.args()
        with mock.patch.object(ytfetch, 'punch_fn', lambda: None):
            res, evs, _, _ = self.plan(a)
        self.assertSpills(a, res, evs, 'no hole punching on ' + self.ram)

    def test_spill_without_a_spill_dir_stays_where_it_is(self):
        a = self.args(spill_dir=None, budget=1 * MiB)
        res, evs, _, _ = self.plan(a)
        self.assertIsNone(res)
        self.assertEqual([(e['ev'], e['dir']) for e in evs], [('spill', self.ram)])
        self.assertEqual(a.dir, self.ram)

    def test_video_only_does_not_count_the_audio(self):
        fa = self.afmt(filesize=200 * MiB)
        a = self.args()
        res, evs, _, ya = self.plan(a, fa=fa)
        self.assertSpills(a, res, evs, 'needs ')
        a = self.args(video_only=True)
        res, evs, _, _ = self.plan(a, fa=fa)
        self.assertEqual(evs, [])
        self.assertEqual(res[3], self.need(asize=0))
        self.assertEqual(a.dir, self.ram)

    def test_audio_size_falls_back_to_the_approximate_one(self):
        fa = self.afmt(filesize=None, filesize_approx=3 * MiB)
        res, _, _, _ = self.plan(self.args(), fa=fa)
        self.assertEqual(res[3], self.need(asize=3 * MiB))
        fa = self.afmt(filesize=None)
        res, _, _, _ = self.plan(self.args(), fa=fa)
        self.assertEqual(res[3], self.need(asize=0))

    def test_no_budget_means_the_free_space_decides(self):
        a = self.args(budget=0)
        with mock.patch.object(ytfetch, 'ram_free', lambda d: self.need() - 1):
            res, evs, _, _ = self.plan(a)
        self.assertSpills(a, res, evs, 'needs ')
        a = self.args(budget=0)
        with mock.patch.object(ytfetch, 'ram_free', lambda d: self.need()):
            self.assertIsInstance(self.plan(a)[0], tuple)

    def test_ram_free_of_a_missing_dir_is_zero(self):
        self.assertEqual(ytfetch.ram_free(os.path.join(self.tmp, 'nope')), 0)
        self.assertGreater(ytfetch.ram_free(self.tmp), 0)


if __name__ == '__main__':
    unittest.main()
