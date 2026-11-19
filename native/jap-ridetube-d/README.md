# jap-ridetube-d

The car-side daemon of RideTube (`ytd.js`, Node 8, root, `jap-ridetube-d.service`), packaged as an
mgu-deploy tool with the video decoder `ytdec` (built in `../ytdec`). yt-dlp, search and thumbnails all
run on the car; nothing is downloaded for keeps: the cache holds the last few videos played.

- audio: BMW MediaPlayer over SOME/IP (`/usr/lib/someip.node`), source 1046 → sink 1024,
  `playFile` on `cache/<id>/audio.m4a`. The two services' descriptions (`CommandControl` for the connection,
  `MediaPlayer` for the player), each from the first source that has it, found once at start:
  1. MainApp's `/usr/lib/oap-mainapp/src-gen/` (made from MainApp's own manifest when it was built; 2021 MainApps
     do not list these two);
  2. the unit's catalog `/etc/oap/someip/someip-interfaces.json`, through the firmware's own generator (loaded
     from MainApp's `AppManagement.js` by `kit/tools/oapgen/gen.js`, shipped as `oapgen.js`; nothing of BMW's
     ships). A child (`ytd.js --someip-gen`) does it, into the root-only `state/someip.json`, at each start;
  3. a built-in description of our P18_23w44 unit's two services, limited to what `ytd.js` uses.

  Logged once: `someip: CommandControl from MainApp|catalog|built-in`, MainApp's version and, when the catalog was
  read, its entries for services 0xB020 and 0xB042 (name, version, instances), then per service what goes to
  `buildProxy` (`someip: in use <service> <id> <version> <instance>=<id>`, plus `lacks ...` for a member `ytd.js`
  uses that is not there: a src-gen file is used unchecked). With a built-in description and
  no answer, the log, the health check's `audio` row and the play error say `This car's software (<os-release
  VERSION>) does not offer the audio connection RideTube uses`, logged again only when the reason changes.
- video: `ytdec --dir cache/<id> --rect WxH [--fill] --log /var/opt/jap-ridetube-d/log/ytdec.log`, which
  writes `/dev/shm/mgu-video-ridetube` for mgu-render; paced by `clock <elapsed_ms> <mono_ms>` lines.
- media: `/var/opt/jap-ridetube-d/cache/<id>/` {meta.json, thumb.rgba, audio.m4a, index.bin, video.h264, and
  `audio.head.m4a` while the rest of the audio downloads}, written on the car by the fetcher (below).

## Architecture

Every internet request runs as the daemon's fetch uid (below, "Internet: the fetch uid"), never root:

- `ytfetch.py` in mgu-python (`/var/opt/mgu-python/current/bin/python3 -I`), with yt-dlp from
  `ytdlp.pyz` on its `sys.path`, fetches the playing video straight into its cache dir
  (`cache/<id>/`); yt-dlp's own cache is `/var/opt/jap-ridetube-d/cache/ytdlp`.
- Playable gate: a play starts once enough of the files is on disk to play, not when the download
  ends; until then the state is `preparing` and `pct` is the download progress towards playable.
- Audio (0.2.1): `playFile` needs a complete file, so the fetcher downloads the audio format yt-dlp picked
  itself, 4 parallel `Range` requests (1 MB, then 2 MB chunks, handed out in file order; googlevideo
  paces each connection), into `audio.src.m4a`; yt-dlp's own download is the fallback (no `filesize`,
  not https, or a range failing 3 times). Once the gap-free prefix holds max(60 s, 1.5 x the rest's
  estimated download time) of samples, it writes `audio.head.m4a`, a plain MP4 of just those, and says
  `audio_head {ms}`. The daemon starts on `audio_head` (or `audio_ready`) + 10 s of video, playing the head.
- Track info: BMW's MediaPlayer takes only a path (`playFile`, `setTime`: no title or artist), so the car shows
  what the file says. Both files carry iTunes tags in `moov/udta/meta/ilst`: the title (`©nam`), the channel
  (`©ART`) and the video's `mqdefault.jpg` thumbnail (`covr`), fetched alongside the audio (playback never
  waits for it; the head has it if it came in time, `audio.m4a` waits up to 5 s). No picture: no cover, no failure.
  Newer firmware's MediaPlayer reports what it read (`currentItemMetadata`, read-only: it has no setter): the daemon
  logs text values by their length only, so no title reaches a log report: `player metadata: TITLE(42 chars) ARTIST(12 chars) COVER_FILE(30 chars)` (`journalctl -u jap-ridetube-d | grep "player metadata"`).
- Head -> full: on `audio_ready` the daemon calls `playFile(audio.m4a)` on the live connection, then
  `setTime` at the clock (extrapolated from the last tick: ytdec keeps running) and deletes the head; the
  player's times and states between the two are ignored, and its times below the target for 3 s after.
  Paused at that moment: `resume` does it (as after a STOP mid-file). Within 1.5 s of the head's end, or a
  seek past it, before `audio_ready`: the player and ytdec pause there, the state is `playing` with
  `buffering: true` (never `ended`), and `audio_ready` resumes there. The fetcher dying with only the
  head: fetched again, twice at most (below, "Rules"), then `error`. A cached video (audio.m4a there) plays it at
  once, as before. The switch itself (a restart of the file, then the seek) may be audible: not measured on the car
  yet.
- Buffering: if playback catches up with the download, the `state` event says `buffering: true`
  until enough data is there again.
- Search: InnerTube (`/youtubei/v1/search`) from the daemon, through the same fetch helper.
- Thumbnails: `thumb.js` in jap-node22 fetches `i.ytimg.com/vi/<id>/mqdefault.jpg` (8 s, no
  redirects, ≤ 2 MB, any status but 200 fails: private videos get a 404 placeholder), decodes it
  with the vendored jpeg-js decoder (baseline and progressive; the car has no image library),
  resamples to 320x180 if needed and writes 230400 bytes RGBA on stdout. DNS: the uplink lease's
  servers (`--lease`, default `/run/mgu-uplink/lease.json`), else the system resolver.

## Updating yt-dlp

`ytdlp.pyz` is built from the official yt-dlp zipapp of a pinned GitHub release
(`https://github.com/yt-dlp/yt-dlp/releases`, Unlicense), checked by sha256; no yt-dlp code is kept here.

1. Set `YTDLP_VERSION` and `YTDLP_SHA256` in `tools/build_pyz.sh` (the release's `SHA2-256SUMS`, file `yt-dlp`).
2. `./build.sh` (rebuilds `build/ytdlp.pyz`, runs the tests, packs).
3. Bump `version` in `component.json`.
4. Install the new artifact through the Store; its `check` (`check.sh`) rolls back a pyz that does not load.

### On the car, between releases

YouTube changes break yt-dlp now and then, and a fixed yt-dlp is usually out within days. While the app's setting
"Update yt-dlp by itself" is on (the default; the daemon keeps it in `state/ytdlp.json`), the daemon runs
`ytfetch.py update --cache-dir cache/ytdlp` as the fetch uid, 2 minutes after its start, then daily (an hour after a
look that failed), and after a play fails past its retries (not a refused video) once an hour has passed since the
last look; only with the uplink's lease and not while a play is preparing. `update`:

1. reads the newest release's tag from where `https://github.com/yt-dlp/yt-dlp/releases/latest` redirects, and stops
   when it is not newer than both `ytdlp.pyz` and the last update;
2. downloads that release's `SHA2-256SUMS` and its `yt-dlp` zipapp (at most 32 MiB) and checks the zipapp's sha256
   against the `yt-dlp` line, and that the zipapp says that version;
3. repacks it as `tools/build_pyz.sh` does (`yt_dlp`, `yt_dlp_ejs` and `__main__.py` only, no native code, every
   module precompiled), at nice 10;
4. imports it in a fresh mgu-python (as `check.sh` does), then names it in `cache/ytdlp/pyz/current.json`
   (`{version, pyz, sha256}`) and removes older updates.

`fetch`, `extract` and the spare `serve` then get `--pyz cache/ytdlp/pyz/<version>/ytdlp.pyz` (only a file inside
that folder); the setting off, or no update, `ytdlp.pyz` as before. The update only ever runs as the fetch uid, never
as root, and `check.sh` still checks the shipped `ytdlp.pyz`. The `ytdlp` command (cap `ytdlp`, `{auto}`) sets it, and the
`ytdlp` event (`{auto, version, bundled, checking}`) answers it and follows each look. To go back by hand (root):

    rm -rf /var/opt/jap-ridetube-d/cache/ytdlp/pyz

## Self-check on the car (root)

    /var/opt/mgu-python/current/bin/python3 -I /var/opt/jap-ridetube-d/current/ytfetch.py check --cache-dir /var/opt/jap-ridetube-d/cache/ytdlp
    U=$(sed 's/.*"fetch":\([0-9]*\).*/\1/' /var/opt/jap-ridetube-d/state/uids.json); /var/opt/mgu-python/current/bin/python3 -I -c "import os,sys;u=int(sys.argv[1]);os.setgroups([]);os.setgid(u);os.setuid(u);os.execv('/var/opt/jap-node22/current/bin/node',['node','/var/opt/jap-ridetube-d/current/thumb.js','dQw4w9WgXcQ'])" $U | wc -c    # 230400
    sh /var/opt/jap-ridetube-d/current/check.sh    # offline; exit 0

The first two need the internet, which the uplink gives the fetch uid, never root: `ytfetch.py check`
drops to that uid itself (from `state/uids.json`); `thumb.js` does not, so the second line runs it
as that uid. `check.sh` is the install `check`: yt-dlp (and `yt_dlp_ejs`) import from
`ytdlp.pyz` in mgu-python, and node22 loads the JPEG decoder and `thumb.js`.

## Control socket `/run/jap-ridetube-d/ctl.sock` (`<app uid>:root` 0600, below "Security notes"), JSON lines

The audio head is internal: `time.total` is the video's length, not the head's.

App → daemon (every `case` of `onLine` in `ytd.js`, no more, no fewer: `test_ytd.js` checks the two match):

| cmd | |
|---|---|
| `{"cmd":"hello","app":"0.4.0","lang":"ru","region":"RU"}` | → `hello` `{service, caps, clock?}`. `lang` (`^[a-z]{2}$`) and `region` (`^[A-Z]{2}$`) are optional; one that does not match is dropped (logged), never refused. Both hold for this connection only, kept for the `hl` / `gl` of its feed, search and related requests. `caps` lists only what this build really answers, from the frozen names `health`, `related`, `hist`, `ytdlp`, `remote`, `proxy`, `stream`; this build: `related`, `hist`, `health`, `ytdlp`. A service older than 0.4.0 answers `error` `unknown cmd hello`: the app reads that as no caps |
| `{"cmd":"status"}` | → `state` (and `time` when known) |
| `{"cmd":"search","q":".."}` | → `results` (InnerTube), or `error` `empty search` / `search offline` |
| `{"cmd":"thumb","id":".."}` | → `thumb` (cache `thumb.rgba` first, else `thumb.js` on the car; nothing if neither works, or if the length is neither 57600 nor 230400) |
| `{"cmd":"prefetch","id":".."}` | the stream lookup (`ytfetch.py extract`) ahead of a likely play, while the controller rests on a tile; nothing is answered. Skipped when cached, being prepared or looked up in the last 25 min; one at a time (the last one asked waits) |
| `{"cmd":"play","id":"..","rect":"WxH","fill":bool,"at":ms,"quality":q,"skip":[cat]}` | cached and ready: plays; else fetches with `ytfetch.py` (`preparing` + pct, `retry` between tries), plays once playable. `at`: YouTube's own resume point (the tile's `start_s`), used when this car has no position for the video; `quality`: `360`, `480`, `720`, else auto (720 on Wi-Fi or no uplink known, 480 on phone data); `skip`: the SponsorBlock categories skipped (default `sponsor`, `selfpromo`, `interaction`, `intro`). Starts where it was left (`positions`) unless finished |
| `{"cmd":"pause"}` / `{"cmd":"resume"}` | `sendButtonEvent PAUSE/PLAY` + ytdec `pause`/`resume` |
| `{"cmd":"seek","ms":N}` | absolute; `setTime` + ytdec `seek N` |
| `{"cmd":"video","on":bool}` | ytdec `video 1/0` (audio unaffected) |
| `{"cmd":"fill","on":bool}` | zoom while playing: ytdec again at the clock with `--fill` or without; the sound plays on; the same mode: nothing |
| `{"cmd":"quality","quality":q}` | while playing, at another height (as `play`): the video fetched again from where it is (in the first 10 s too), paused if it was; the same height: nothing. A pause, resume, seek, stop or play sent during that restart is applied or cancels it |
| `{"cmd":"stop"}` | STOP, disconnect, ytdec `quit` (SIGKILL after 1 s) |
| `{"cmd":"positions"}` | → `positions` |
| `{"cmd":"auth_status"}` | → `auth` |
| `{"cmd":"auth"}` | signed in, or a code still valid: → that `auth` again; else a new device code → `auth` `code`, then polled until `signed_in`, `signed_out` (expired, denied) or `error` |
| `{"cmd":"sign_out"}` | deletes the account → `auth` `signed_out` |
| `{"cmd":"feed","which":"home\|subs\|wl\|hist\|liked"}` | → `feed` (items, or error `signed out` / `feed offline` / `unknown feed`). `hist` (`FEhistory`, the watch history) and `liked` (`VLLL`) are new in 0.4.0, cap `hist`; an older service answers them `unknown feed` |
| `{"cmd":"channels"}` | → `channels` (every subscription; kept 10 min), or its error as `feed` |
| `{"cmd":"channel","id":"UC.."}` | → `channel` (its page), or its error as `feed`, or `bad channel` |
| `{"cmd":"playlists"}` | → `playlists` (the account's playlists, or error as `feed`) |
| `{"cmd":"playlist","id":".."}` | → `playlist` (its videos, or error as `feed`, or `bad playlist`) |
| `{"cmd":"send_logs","app":"0.4.0"}` | the recent log and the health check's lines, redacted, to the log relay (below, "Log reports") → `logs_sent` or `logs_error`; a second one while one is on its way is ignored |
| `{"cmd":"health"}` | 0.4.0, cap `health`: → one `{"ev":"health","key","ok","text"}` per check as each one ends, then `{"ev":"health","done":true}`, all within about 8 s. The 12 keys: `service`, `node`, `node22`, `python`, `ytdlp`, `uid`, `lease`, `dns`, `tls`, `free`, `audio`, `socket` (`ytdlp`, `dns` and `tls` from `ytfetch.py check --json`, run as the fetch uid). Every key is answered; a check that could not run says `not checked: <why>`. `text` is one short line with no address (IP, MAC), video id or title |
| `{"cmd":"related","id":".."}` | 0.4.0, cap `related`: → `{"ev":"related","id","items":[item]}` (the TVHTML5 watch-next tiles, the video itself left out, ≤ 100; kept 10 min per video and language) or `{"ev":"related","id","error"}` (`bad id`, `related offline`) |
| `{"cmd":"ytdlp","auto":bool}` | 0.4.1, cap `ytdlp` (WP6): `auto` optional (sets the self-update on or off, kept in `state/ytdlp.json`) → `{"ev":"ytdlp","auto","version","bundled","checking"}`, also after each look for a newer yt-dlp (above, "On the car, between releases"). `version`: the yt-dlp fetches use; `bundled`: `ytdlp.pyz`'s, known after the first look |
| `{"cmd":"remote","on":bool,"lang"?}` | 0.4.1, cap `remote` (WP9): the phone remote on or off (below, "Phone remote"); `lang` the app's language for the phone page (`en fr nl de es it pt ru zh-CN`, anything else: `en`) → `{"ev":"remote","on","url","expires"}`: `url` `http://<hotspot address>:8471/#<token>` while on and the hotspot has an address, else null; `expires` the seconds left; `error` (with `on` false) when it could not be turned on. `on` not a bool: only that event. Off by default; off again after 1 hour with no phone action, when the app goes away, when its server stops and at exit |
| `{"cmd":"proxy","mode":"off\|wireproxy\|tailscale"}` | later, not yet implemented, cap `proxy` (WP11): → `{"ev":"net","proxy","ok"}`; until then `error` `not implemented proxy` |

A command not in this table: `{"ev":"error","msg":"unknown cmd <cmd>"}`. A command of the table whose package has not
landed: `{"ev":"error","cmd":"<cmd>","msg":"not implemented <cmd>"}`; the app sends none of them unless `hello` listed its cap.

Daemon → app:

- `{"ev":"hello","service":"0.4.0","caps":[..]}`: the answer to `hello` (above). `"clock":"2026-10-13"` is added
  only while the head unit's clock is wrong (below, "Security notes"): the date the head unit shows. The app then warns
  the driver.
- `{"ev":"clock","clock":"2026-10-13"|null}`: the clock went wrong, or right again (`null`), after `hello`. Checked at
  each fetch, lookup, request and health check.
- `{"ev":"state","state":"idle|preparing|playing|paused|ended|error","pct","id","title","buffering"}`; later (not yet
  implemented, cap `stream`) adds `"stored":"ram|flash"`: where the playing video is held.
- `{"ev":"time","elapsed","total"}` (ms, ≤ 4/s).
- `{"ev":"results","q","items":[item]}` (`meta: ["12K views"]` when there is a view count).
- `{"ev":"thumb","id","w","h","rgba":"<base64 w*h*4 bytes>"}` (320x180; 160x90 from caches older than 0.1.6; the size comes
  from the length; a 320x180 line is ~307 kB).
- `{"ev":"error","msg"}` (with `cmd` for a command not implemented yet).
- `{"ev":"retry","id","n","msg"}`: the fetch of the video being prepared failed (the network, not the video), tried again
  after a wait; `n` counts from 1.
- `{"ev":"extras","id","chapters":[[ms,title]],"segments":[[ms,ms,category]]}`: the playing video's chapters (yt-dlp's)
  and SponsorBlock segments (`sponsor`, `selfpromo`, `interaction`, `intro`, `outro`, `music_offtopic`), at the play and
  again when the segments come in.
- `{"ev":"skipped","category","ms"}`: a SponsorBlock segment of a `skip` category was skipped (`ms`: its length).
- `{"ev":"positions","items":[{id,ms,total,done,at,title,channel,duration_s}]}`: where each video played on this car was
  left, newest first (`at`: when, epoch ms; `done`: within 5 % or 5 s of its end), at most 300.
- `{"ev":"auth","state":"signed_out|code|signed_in|error","code","url","expires" (s left, with code),"msg" (with error)}`.
- `{"ev":"feed","which","items":[item],"shelves":[{title,items:[item]}]}` or `{"ev":"feed","which","error"}` (feed thumbs:
  `thumb`).
- `{"ev":"channels","items":[{id,title,handle}]}` or `{"ev":"channels","error"}`: the subscriptions, A-Z.
- `{"ev":"channel","id","items":[item],"shelves":[..]}` or `{"ev":"channel","id","error"}`: a channel's page (Videos,
  Popular...), as `feed`.
- `{"ev":"playlists",..}`, `{"ev":"playlist",..}`, `{"ev":"logs_sent",..}`, `{"ev":"logs_error",..}`: below.
- 0.4.0 / 0.4.1, cap-gated: `{"ev":"health",..}`, `{"ev":"related",..}`, `{"ev":"ytdlp",..}` (shapes in the table).
- 0.4.1: `{"ev":"remote","on","url","expires"}` (above); `{"ev":"remote_do","do":"search|play","q"|"id"}`: a phone action
  the app carries out itself (the parked rule and the screen stay the app's): `q` a search (≤ 200 characters), `id` a
  video id (`ID_RE`), both checked again by root. Not yet implemented: `{"ev":"net","proxy","ok"}`.

An item is `{id,title,channel,duration_s,meta}`, plus `watched_pct` (the account's progress on the tile), `start_s` (its
resume point) and `members: true` (a members-only badge) when the tile has them; `meta` = the texts of the tile's second
line as YouTube writes them, without
the `•` and the badges (`["125K views","1 day ago"]`, `[]` when none), `short: true` for a Short (the app decides
whether it shows them), and `live: true` for a live stream or an upcoming premiere (`duration_s` null; not playable yet,
the app shows a LIVE tag and does not ask to play it). `items`: every video tile once, page order, ≤ 100.
`shelves`: YouTube's rows in page order (≤ 8, ≤ 12 tiles each, video tiles and Shorts only, deduped per row, empty rows
dropped); `title` is the row header, else the channel when all its tiles share one (Subscriptions' per-channel rows), else `""`.
Watch later is a playlist with no rows: `shelves: []`, use `items`.
`{"ev":"playlists","items":[{id,title,count,meta,thumb}]}` or `{"ev":"playlists","error"}`: the library page's playlists, page
order, each once, Watch later left out (`feed` `wl` has it). `count` is the tile's "N videos" (null when it shows none), `meta`
its other texts (`["Private","Updated today"]`), `thumb` the video whose picture the tile shows (ask it with `thumb`; null when
none). `{"ev":"playlist","id","title","items":[item]}` or `{"ev":"playlist","id","error"}`: a playlist's videos (≤ 100), `title`
its name (`""` when the page has none).
`{"ev":"logs_sent","id":"ABC123"}`: the relay took the report, `id` is the code the user quotes in a GitHub issue.
`{"ev":"logs_error","msg":"closed|busy|offline|failed"}`: reporting switched off at the relay (410), too many reports
(429), no answer (no network, no internet uid, the relay down), anything else; never the relay's own text.

`state` carries `buffering` (bool; true while playback waits for the fetch), and `preparing`'s `pct`
is the fetch's progress to playable (0-100).

One client at a time; a new connection replaces the old one. The client going away stops
playback at once.

## Account

The car signs in itself with the TV device sign-in: the client id and secret are scraped from `https://www.youtube.com/tv` (Tizen user agent) at run time, never shipped
(once a process; again once when the device-code request is refused);
`/o/oauth2/device/code` gives the code the user enters at google.com/device; `/o/oauth2/token`
is polled, then refreshes the token when less than 5 min is left (`invalid_grant` = signed out).
Feeds: `POST /youtubei/v1/browse` as `TVHTML5`, `FEwhat_to_watch` (home), `FEsubscriptions`
(subs), `VLWL` (wl), `FEhistory` (hist), `VLLL` (liked); their video tiles, each id once (Shorts marked `short: true`; no
channels or playlists), at most 100.
Playlists: the TV Playlists page `FEplaylist_aggregation`, its playlist tiles (when it refuses: the Save to playlist list,
`playlist/get_add_to_playlist`, without counts or pictures); a playlist: `VL` + its id, as Watch later.
The account (tokens and the scraped secret) is `/var/opt/jap-ridetube-d/state/account.json`, 0600 in the
0700 state dir, written atomically; nothing secret goes on the socket or into the log (and a log report is
redacted again before it leaves, below). `sign_out` wins
over work in flight: a refresh, device-code request or poll started before it saves, shows and
re-arms nothing. Asks for a feed while its browse is in flight share that browse.

### Internet: the fetch uid

`mgu-uplink` lets out only the uids it lists, never root. Every youtube.com request runs in a child,
`node --max-http-header-size=65536 ytd.js --fetch`, spawned as the daemon's own fetch uid (gid the same
number, empty env, cwd `/`). The request, with the secret, tokens and body, goes on the child's stdin
(never argv or env: `ps` shows those); `{status, body}` or `{error}` comes back on its stdout. 10 s
timeout (a log report: 30 s; the child is killed 1 s after), 8 MiB body. Plain `http:` only to 127.0.0.1 or
localhost (the tests' fake relay); any other URL goes out over TLS. The child never touches the account file.
While the head unit's clock is wrong (below, "Security notes") the child is `ytfetch.py request --no-cert-time`
instead, with the same stdin and stdout.

The uid is picked as mgu-updater's `js/uids.js` picks its own, at start and on first need:

- kept from `state/uids.json` (`{"fetch": N}`) while nothing else holds it (running processes do not
  count: they may be our own helpers);
- else the lowest number above MainApp's app uid ranges (`usableUidsAndGids` and
  `usableUidsAndGidsRse` in the `config/base.json` of `/usr/lib/oap-mainapp` or `oap-mainapp21`;
  both there: the one whose HMI, `HmiMain3D` or `Hmi8`, runs), at most 60000, inside none of them and
  not taken: a uid or gid in `/etc/passwd` or `/etc/group`, an `oap_<uid>` folder, MainApp's app
  registry and `uids.txt`, `mainAppUids`, another component's `mgu-uplink/uids.d` entry,
  mgu-updater's `state/uids.json`, a running process's uid or gid;
- no readable MainApp config and no kept uid: none. The log says why; `auth` and `feed` answer with
  the error `no internet uid on the car (see the log)`.

It is written to `state/internet-uids` (component.json `"internet": true, "uids":
"state/internet-uids"`: the deploy tool copies it into `/var/opt/mgu-uplink/uids.d/jap-ridetube-d`) and,
while the uplink is installed, straight into that drop-in (the uplink rescans every 5 s). The unit
starts node with `--max-http-header-size=65536`: the TV page's headers pass 8 kB.

## Log reports (`send_logs`)

The user taps "Send logs to the developer" in the app (its menu, or the playback error screen) and confirms; the
daemon then posts one report and the app shows the code the relay answers. Nothing is sent otherwise.

- Where: `POST <REPORT_URL>/v1/report`, JSON, as the fetch uid. `REPORT_URL` is one constant in `ytd.js`;
  `MGU_YT_REPORT_URL` or the `reportUrl` option override it. 30 s timeout.
- What: `{"app","service","os","log"}`: the app's version (as the app sends it, digits and dots, else
  `unknown`), the service's, the first 5 lines of `/etc/os-release` (≤ 2 KB), and a log (≤ 200 KB, the newest
  lines kept): the last 300 lines of `ytdec.log`, then the daemon's last 1500 log lines (a ring in memory fed by
  every log line, so nothing extra is written to disk), then where the audio services' descriptions came from
  (`--- someip`, the lines above, under "audio"), then the health check's lines (`--- health`, one
  `health <key> ok|FAIL <text>` per check; the report waits up to 8 s for them). The `audio` row adds the sources
  and MainApp's version.
- Redacted first, the whole of it (`redactLog`, tested in `test_ytd.js`):
  - every value in the account file, and of a sign-in under way (client id and secret, tokens, device and user
    codes): `[secret]`; `Bearer` / `OAuth` tokens, `access_token`, `refresh_token`, `device_code`,
    `user_code`, `client_secret`, cookies: `[secret]`;
  - video ids: `v#` and 4 hex of sha256(salt + id), playlists `p#`, channels `c#`, with a new salt per report:
    one id keeps one tag through a report, and two reports can't be matched. Ids are found by what the daemon
    knows (the ids the app sent, the playing and preparing video, the cache, `positions.json`, thumbs, yt-dlp's
    info files) and by context (`v=`, `watch/`, `/vi/`, `youtu.be/`, `list=`, `[youtube] <id>`, `fetch <id>`,
    `thumb <id>`, `lru removed a,b`, paths under the cache dir as ytdec's `--dir` and `dir=`), never as any
    11-character word;
  - titles and channel names the daemon knows (the cache's `meta.json`, `positions.json`, the playing video):
    `[title]`;
  - URLs cut to `scheme://host`, a path with a query but no scheme (`with url: /videoplayback?...`) to
    `/[path]`, any `ip=` value to `[ip]`; e-mail addresses `[email]`; 17-character VIN-like strings `[vin]`; public
    IP addresses `[ip]` (IPv4 but 127/8, 10/8, 172.16/12, 192.168/16; IPv6 but fe80, fc, fd).
- Known values shorter than 6 characters are not replaced word for word (they would shred ordinary words);
  the patterns above still apply.

## Rules

- Every exit path releases audio (STOP + `disconnect`): stop, end of file, playback error, app
  gone, SIGTERM, uncaught exception. At start it disconnects every connection with sourceID 1046
  left over (no other) before any play.
- ytdec dies while playing → restarted once at the current clock; a second death → `error`
  `video failed, audio only`, the state stays `playing` and audio continues. No change in
  `stats.decoded` for 5 s while playing with video on → the child is killed (counts as a death).
- A buffer underrun from the player (`ITEM_BUFFER_UNDERRUN`) keeps the video: the player starts again at the clock
  after a short wait, 3 times in a rolling minute, then `error` `audio underrun: 3 recoveries in a minute, stopped`.
  On the head it waits for `audio.m4a`; during the head -> full switch, a recovery or a pause it is ignored.
- The audio start (connect + `playFile`) is tried once more after 1 s, in play, resume and recovery.
- The fetcher dying mid-play (not a refusal, not a full disk) runs again into the same folder, twice a video at
  most, while the sound plays on; ytdec restarts on the new index. Then as before: `video incomplete`, or `error`
  with only the head.
- Cache: `keep` played ids by dir mtime (default 0: a video is deleted once played), never the
  playing or preparing one. ytfetch stops a download when less than 256 MiB is left free.
- Never exits on its own; uncaught errors → log, release audio, idle.
- Unit: `Restart=on-failure`, `RestartSec=3`, `TimeoutStopSec=5`, `LimitCORE=1`; `recmgr`
  and `crashNames` in `component.json` (recmgr's list counts from the next boot; the unit is
  safe before that: it starts idle and stays active).

## Security notes

- The head unit's clock. TLS checks that a certificate's dates hold for the head unit's own date, so a clock that is
  weeks behind makes every certificate look not yet valid, and nothing plays. When the clock reads a date before this
  build's release day (`BUILT` in `ytd.js`), the clock must be wrong. Only then does every TLS connection the
  service makes skip the certificate's validity dates (OpenSSL's `X509_V_FLAG_NO_CHECK_TIME`, through
  `ytfetch.py --no-cert-time`). The certificate must still chain to a trusted CA and match the host name. This covers
  every host the service talks to: YouTube and googlevideo (yt-dlp and ytfetch.py), the sign-in and the feeds,
  SponsorBlock and the log relay (in `ytfetch.py request`, since Node 8 cannot skip only the dates). The risk: someone
  who holds an old, expired certificate of one of these hosts, with its private key, and can reach the car's traffic
  could pose as that host. The app says so on screen while it lasts (`hello` `clock`), and the health check's TLS line
  says the dates are skipped. A clock ahead of real time cannot be proven wrong: its errors stay ("Wrong head unit
  clock"). Thumbnails (`thumb.js`, Node 22) keep the full check, so they do not show while the clock is wrong.
- The daemon runs as root: it talks SOME/IP to BMW's MediaPlayer. Every internet request runs as the fetch uid
  instead (above).
- ytdec also runs as root (accepted risk, not verified otherwise on the car). It opens the GPU's render node
  `/dev/dri/renderD128` for the Intel Media SDK and writes the frames to `/dev/shm/mgu-video-ridetube` for
  mgu-render, and running it under another uid was not tested on a head unit. It reads only the video folder
  the daemon names (`--dir`) and takes commands only from the daemon's pipe. It opens no socket and fetches
  nothing.
- `/run/jap-ridetube-d/ctl.sock` belongs to RideTube's app alone: the daemon reads the app's uid (`userId`) from
  MainApp's registry (`/var/opt/public/oap/oap_12201/data/apps/jap_ridetube.json`) and makes the socket
  `<uid>:root` 0600, checked again every 5 s (a reinstall can change the uid). The uid must be an integer, inside
  MainApp's app uid ranges when those can be read, and never the fetch uid. The last good uid is kept in `state/app-uid.json`: if the
  registry later cannot be read, the socket stays locked to that uid, across restarts too. If the entry is gone from
  the registry (the app was uninstalled), the socket is root only (0600) until it comes back, because MainApp may give
  the old uid to another app. When the owner changes,
  the connected client is dropped and the app reconnects under the new owner. Only when no uid was ever known (a
  fresh install whose registry cannot be read) is the socket 0660 root:`tm_oap_app`, logged: then every app on the
  head unit shares that group, so any installed app can drive the daemon (play, search, read the feeds and the
  watch history, sign the account in or out).
- Root does not walk, chown or write below a folder the fetch uid owns (a symlink planted there could point root
  anywhere): SponsorBlock answers sit in root's `cache/.sb/` (0700), yt-dlp's `ytdlp/info/` is made and pruned by
  the fetcher itself, and a video's folder is emptied by its owner (`rm -rf` as that uid; rm never runs as root, and a
  folder owned by an app's uid is refused) before root removes the empty folder. Root still touches these folders in a few places:
  - it reads `meta.json` and `thumb.rgba` there, only as regular files that are not symlinks, size-capped, opened
    non-blocking (a FIFO or a link to `/dev/zero` counts as missing);
  - it unlinks `audio.head.m4a` once the full audio is ready (unlink does not follow a symlink in the last component);
  - ytdec, as root, reads `index.bin` and `video.h264` there: a known remaining surface;
  - a retried play extracts again without `--info`, so root never unlinks anything in `ytdlp/info/`.
- `cache/` itself must be a real folder owned by root: the daemon refuses to start otherwise (systemd then retries
  every 3 s), and puts it back to 0711 (logged) if it was group or other writable. To recover from a refusal, remove
  the folder as root (`rm -rf /var/opt/jap-ridetube-d/cache`) and restart the service; it only holds cached videos and
  saved positions.
- The cache (`/var/opt/jap-ridetube-d/cache`) is 0711: the fetch uid reaches its own folders, and nobody else can
  list what was watched. Each video's folder is 0711: BMW's media engine (its own uid) opens the audio in it by
  name, and nobody can list it. The thumbnail folder is 0700 and `positions.json` (where each video was left, the
  watch history) 0600. The account tokens live in `state/` (0700).

## Phone remote (`remote.js`, `remote.html`, `remote-strings.json`)

A passenger's phone on the car's own Wi-Fi hotspot opens a page the car serves and sends a YouTube link (played) or a
search; nothing is hosted outside the car. The design follows the MGU Store's phone page (mgu-updater `js/web.js`).
`remote.js` has the protocol details in its header. The page and every word it shows (the server's errors too) are in
the app's language: the app sends its language (its Language setting; Auto: the car's) with `on`, root keeps it only
if it is one of RideTube's nine, and the server puts that language's words (`remote-strings.json`, English keys) in a
JSON block of the page that its script reads. The trust boundaries:

- **The hotspot to the HTTP server.** The server is a child (`node remote.js serve`) under its own **web uid**
  (`state/uids.json` `web`, picked from 60000 down, never the fetch uid nor an app's, never written for the uplink: it
  has no internet), no supplementary groups, `env {}`, cwd `/`. It listens on 127.0.0.1 and on `wlan_bridge`'s IPv4
  address only, port 8471, only while the remote is on. The unit's firewall gets one rule (`nft insert rule ip filter
  input iifname "wlan_bridge" tcp dport 8471 accept comment "jap-ridetube-d-remote"`) only while the child holds the
  port on the hotspot address; tagged rules are removed at off, at start and at exit (a failed removal, nft busy or
  timed out, is tried again every 5 s), and the rule is put back every 30 s if a ruleset load dropped it.
- **The phone to the API.** `GET /` is a static page (no external assets, CSP with its script's hash, no-store, no
  referrer). Every API call needs `Authorization: Bearer <token>`: 128 random bits, new at each on, carried in the
  QR code's URL fragment (never sent in a request line, never logged), compared in constant time (sha256 of both). The
  right token always passes; an address with 10 wrong tokens gets 429 for wrong or missing ones until the remote is off. Bodies: JSON only, 16 KiB at most; the text 2 KiB,
  a search 200 characters; a link must be a YouTube video link (parsed to its id), any other link is refused.
- **The web uid to root.** The child reaches the daemon only through `/run/jap-ridetube-d/remote.sock` (made 0600
  under umask, then `<web uid>:root`), separate from `ctl.sock` and handled by its own three-command allowlist:
  `search`, `play`, `status`. Root checks the id (`ID_RE`) and the query again; nothing else (auth, sign_out, feed,
  positions, send_logs, stop...) is answered. `status` gives the state, id, title and times only. A phone action less
  than 1 s after the last one is refused (each search costs a fetch). Queries lose control characters, zero-width and
  direction marks (they end up in the HMI's recent-search labels).
- **Root to the app.** A phone action reaches the app as `remote_do`; the app checks it again (only while on, the id,
  200 characters) and carries it out as a tap would (the parked rule, the screen).
  The remote cannot be turned on while `ctl.sock` is shared with every app (else any app could open the port).

## Build and test

    node test/test_ytd.js           # fake someip, fake ytdec, fake fetcher, fake youtube.com, fake nft (the phone remote)
    node test/test_thumb.js         # Node 22+: ffmpeg-made JPEGs (baseline, resampled, progressive via jpegtran); online part skipped offline
    python3.12 -I test/test_ytfetch.py   # ffmpeg fixtures, local Range server (head MP4, ranged == one stream); online part skipped offline
    MGU_STORE=... ./build.sh [path/to/ytdec]   # → dist/jap-ridetube-d@<version>.tgz (default ../ytdec/build/target/ytdec)

`build.sh`: checks ytdec is an x86-64 ELF, runs `tools/build_pyz.sh` (→ `build/ytdlp.pyz`),
`tools/vendor_jpeg.sh` when `vendor/jpeg-js/` is missing, the three tests, copies ytdec into `build/`,
then packs with the MGU Store's `deploy/hu artifact` (`MGU_STORE`; `SOURCE_DATE_EPOCH`: the last commit).
`tools/vendor_jpeg.sh` fetches the pinned jpeg-js tarball (BSD-3-Clause) from the npm registry,
checks its sha512 and keeps only `lib/decoder.js` and `LICENSE`.

Requires (catalog `requires`, installed first): mgu-deploy 0.7.0, mgu-python 1.0.2, jap-node22 22.23.4,
mgu-render 0.6.11 (the video layer).

Overrides (tests): `MGU_YT_SOMEIP`, `MGU_YT_SRCGEN`, `MGU_YT_YTDEC`, `MGU_YT_CACHE`,
`MGU_YT_LOGDIR`, `MGU_YT_SOCK`, `MGU_YT_STATE`, `MGU_YT_ACCOUNT`, `MGU_YT_REPORT_URL`, or the `Daemon` constructor options.
