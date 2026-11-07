#!/usr/bin/env python3
"""Fork (2026-11-07): ytfetch.py's streaming into RAM, offline: PacedReader against a local Range server (byte for
byte, paced by the window), Trimmer punching what has played, the stream-or-spill decision. No ffmpeg, yt-dlp or car.
    python3 -I test/test_stream.py"""
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ytfetch  # noqa: E402

DATA = bytes((i * 7 + (i >> 9)) & 255 for i in range(600_000))


class Range(http.server.BaseHTTPRequestHandler):
    hits = []

    def do_GET(self):  # noqa: N802
        r = self.headers.get('Range', '')
        s, e = (int(x) for x in r[len('bytes='):].split('-'))
        Range.hits.append((s, e))
        body = DATA[s:e + 1]
        self.send_response(206)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def events(fn):
    """fn() with ytfetch's events captured: [(dict)]"""
    out, old = io.StringIO(), ytfetch._out
    ytfetch._out = out
    try:
        fn()
    finally:
        ytfetch._out = old
    return [json.loads(x) for x in out.getvalue().splitlines()]


class Stream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Range)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = 'http://127.0.0.1:%d/v' % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_reader_is_byte_identical(self):
        w = ytfetch.Window(10 ** 9, 0)
        r = ytfetch.PacedReader(self.url, {}, len(DATA), None, w, lambda: True, chunk=65536)
        got = bytearray()
        while True:
            b = r.read(5000)
            if not b:
                break
            got += b
        self.assertEqual(bytes(got), DATA)
        self.assertEqual(r.bytes, len(DATA))

    def test_reader_waits_for_room_then_goes_on(self):
        Range.hits.clear()
        w = ytfetch.Window(1000, 0)           # 1 s ahead at most
        r = ytfetch.PacedReader(self.url, {}, len(DATA), None, w, lambda: True, chunk=65536)
        first = r.read(1000)                  # one chunk
        self.assertEqual(first, DATA[:1000])
        w.fetched = 5000                      # the demuxer is 5 s in, playback at 0: no room
        done = threading.Event()
        threading.Thread(target=lambda: (r.read(100000), done.set()), daemon=True).start()
        time.sleep(0.4)
        self.assertFalse(done.is_set(), 'waits while 4 s past the window')
        self.assertEqual(len(Range.hits), 1)
        with w.cv:                            # what the "pos" line does
            w.play = 4500
            w.cv.notify_all()
        self.assertTrue(done.wait(3), 'goes on once playback catches up')
        self.assertGreater(w.waited, 0.3)

    def test_reader_waits_while_ram_is_short(self):
        w = ytfetch.Window(10 ** 9, 0)
        free = {'ok': False}
        r = ytfetch.PacedReader(self.url, {}, len(DATA), None, w, lambda: free['ok'], chunk=65536)
        done = threading.Event()
        threading.Thread(target=lambda: (r.read(10), done.set()), daemon=True).start()
        time.sleep(0.3)
        self.assertFalse(done.is_set())
        free['ok'] = True                     # (polled once a second)
        self.assertTrue(done.wait(3))

    def test_listen_reads_pos_lines(self):
        w = ytfetch.Window(1, 1)
        rfd, wfd = os.pipe()
        w.listen(os.fdopen(rfd, 'r'))
        with os.fdopen(wfd, 'w') as f:
            f.write('pos 1200\nnonsense\npos -5\npos 3400\n')
        for _ in range(50):
            if w.play == 3400:
                break
            time.sleep(0.02)
        self.assertEqual(w.play, 3400)


class Trim(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.punch = ytfetch.punch_fn()

    def test_probe(self):
        self.assertIsNotNone(self.punch, 'ctypes + fallocate')
        self.assertTrue(ytfetch.can_punch(self.d, self.punch), 'this file system frees punched blocks')
        self.assertFalse(os.path.exists(os.path.join(self.d, '.punch')))
        self.assertFalse(ytfetch.can_punch(self.d, None))

    def test_punches_to_the_keyframe_behind(self):
        p = os.path.join(self.d, 'video.h264.part')
        fd = os.open(p, os.O_RDWR | os.O_CREAT, 0o644)
        mib = 1 << 20
        os.write(fd, os.urandom(8 * mib))
        os.fsync(fd)
        w = ytfetch.Window(0, 10000)          # 10 s behind
        t = ytfetch.Trimmer(w, self.punch)
        for k in range(8):                    # a keyframe every 2 s, 1 MiB apart
            t.key(k * 2000, k * mib)
        w.play = 9000                         # cut at -1 s: nothing played that far back
        self.assertEqual(events(lambda: t.after_write(fd)), [])
        w.play = 19000                        # cut at 9 s: the keyframe at 8 s (4 MiB)
        ev = events(lambda: t.after_write(fd))
        self.assertEqual(ev, [{'ev': 'trim', 'ms': 8000, 'bytes': 4 * mib}])
        st = os.fstat(fd)
        self.assertLessEqual(st.st_blocks * 512, 4 * mib + 65536, 'the first 4 MiB freed')
        self.assertEqual(st.st_size, 8 * mib, 'offsets kept')
        self.assertEqual(os.pread(fd, 16, 4 * mib - 16), b'\0' * 16)
        self.assertNotEqual(os.pread(fd, 16, 4 * mib), b'\0' * 16, 'the keyframe itself kept')
        w.play = 19500                        # less than TRIM_MIN more: not yet
        self.assertEqual(events(lambda: t.after_write(fd)), [])
        self.assertEqual(t.keys[0], (8000, 4 * mib))
        os.close(fd)


class Plan(unittest.TestCase):
    def ydl(self, f):
        return types.SimpleNamespace(process_ie_result=lambda info, download: dict(f))

    def args(self, d, spill, budget=0):
        return types.SimpleNamespace(stream=(120000, 45000), dir=d, spill_dir=spill, budget=budget)

    def setUp(self):
        self.ram, self.flash = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.v = {'protocol': 'https', 'url': 'https://x/v', 'filesize': 300 << 20}   # 10 min at 4 Mbit/s
        self.a = {'filesize': 10 << 20}
        self.info = {'duration': 600}
        self.stdin = sys.stdin
        sys.stdin = io.StringIO('')

    def tearDown(self):
        sys.stdin = self.stdin

    def test_streams_when_it_fits(self):
        a = self.args(self.ram, self.flash, budget=256 << 20)
        ev = []
        r = None

        def go():
            nonlocal r
            r = ytfetch.plan_stream(a, self.ydl(self.a), self.ydl(self.v), self.info)
        ev = events(go)
        self.assertIsNotNone(r)
        self.assertEqual(ev[0]['ev'], 'stream')
        self.assertLess(ev[0]['need'], 256 << 20)
        self.assertEqual(a.dir, self.ram)

    def test_spills_past_the_budget(self):
        a = self.args(self.ram, self.flash, budget=64 << 20)
        ev = events(lambda: self.assertIsNone(ytfetch.plan_stream(a, self.ydl(self.a), self.ydl(self.v), self.info)))
        self.assertEqual(ev[0]['ev'], 'spill')
        self.assertIn('MiB of RAM', ev[0]['why'])
        self.assertEqual(ev[0]['dir'], self.flash)
        self.assertEqual(a.dir, self.flash)

    def test_spills_without_ranges_or_size(self):
        for v, why in (({'protocol': 'm3u8_native', 'url': 'u', 'filesize': 1}, 'ranges'), ({'protocol': 'https', 'url': 'u'}, 'ranges')):
            a = self.args(self.ram, self.flash)
            ev = events(lambda: ytfetch.plan_stream(a, self.ydl(self.a), self.ydl(v), self.info))
            self.assertEqual(ev[0]['ev'], 'spill')
            self.assertIn(why, ev[0]['why'])


if __name__ == '__main__':
    unittest.main()
