# Changelog

## Service 0.4.1 (fork by 7amoody1985, 2026-11-08)

- Streaming: the fetcher says how far it has fetched before it waits for room. Its progress events are throttled
  (2 a second), so the last one could be up to a chunk behind while it waited: the service could show buffering
  (and the debug report an old `fetched_s`) with the video there. Found by a live check against YouTube.
- Tests: `test/mgyi.py` takes ffprobe from PATH (it named Homebrew's only); the ffmpeg and online tests of
  `test_ytfetch.py` now run on Linux. `test/live_stream.py`: a live check that streams the check video (3:33,
  720p) into /dev/shm with simulated playback and a jump, then compares it with a whole fetch; it passed 3 of 3,
  with at most 11 MB in RAM (26.4 MB whole), the index, the audio and every byte past the punched part identical.
- `test_ytd.js` "zoom while playing": waits for ytdec's seek line before checking it (it raced the fake's log and
  failed now and then, on the original code too).

## App 0.3.9, service 0.4.0 (fork by 7amoody1985, 2026-11-07)

- Service: the playing video streams in RAM instead of being written whole to the head unit's flash. A 256 MB
  tmpfs at `/run/jap-ridetube-media`; the video fetched at most 120 s past playback in Range requests and
  hole-punched 45 s behind it; a seek back past that fetches the play again from there. A video that cannot
  stream that way goes to flash as before. Thumbs (60 at most) and prefetched lookups in RAM too; the resume
  point saved every 60 s, not 15 s.
- Service: a debug report: `/run/jap-ridetube-d/status.json` (RAM, every 10 s in use), one line a play in
  `log/sessions.jsonl`, `{"cmd":"debug"}` on the socket. No video ids or titles in either.
- App: the browsing pages redraw every 2 s when nothing changed, not 4 times a second.
- `tools/patch_service.py`: the service's package from a published one, without Docker (ytdec and yt-dlp kept).

## App 0.3.8 (fork by 7amoody1985, 2026-11-07)

- The Search menu (and the settings in it) stays open: the drawn page no longer comes back over it a moment
  after it opens. The HMI's stack keeps the drawn screen listed under the menu, so the kit now goes by which
  of the app's screens came to the front last.
- `tools/patch_package.py`: the app's package from a published one, without BMW's SDK (javascript changes only).

## App 0.3.7, service 0.3.8

- Video while driving takes effect only once switched on while the car is parked.
- The download stops when less than 256 MiB is left free on the head unit.
- README: data use, tested on, uninstall.

## App 0.3.6, service 0.3.7

First public release.
