# Changelog

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
