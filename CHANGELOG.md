# Changelog

## Service 0.4.2 and app 0.4.5

- yt-dlp updates on the car, contributed by Alex Arghir (PR #15). When a YouTube change breaks yt-dlp, a fixed
  yt-dlp release usually comes out within days, and until now the car waited for the next RideTube service. The
  service now looks for the newest yt-dlp release itself: 2 minutes after it starts, then daily, and after a play
  fails past its retries. It checks the download against the release's `SHA2-256SUMS`, repacks and precompiles it
  as `build_pyz.sh` does, imports it once, and then fetches with it. The service's own `ytdlp.pyz` stays the
  fallback. All of it runs as the fetch user, never as root.
- App: the setting "Update yt-dlp by itself", on by default. Off, the service uses only its own yt-dlp. With an
  older service the setting does nothing.
- If an updated yt-dlp file is damaged (a power cut during an update, say) or does not import, the fetcher falls
  back to the service's own yt-dlp, so plays keep working. A release that fails its checks is tried again the next
  day, and a look that hangs is stopped after 15 minutes.
- Service: `ytfetch.py update`, the `ytdlp` command and event.

## What's new since the first release

The first public release was app 0.3.6 with service 0.3.7, on 4 November 2026. This is what came after it, in
short. Each version's own section below has the details.

### Watching

- History and Playlists pages: the videos you watched, Liked videos, and the playlists you made or saved. A video
  played from a grid or a playlist goes on through the rest of it. (0.3.10, 0.4.0)
- Watch next: when a list runs out, the first related video plays after a 5 s countdown. (0.4.0)
- A video you come back to starts where you left it, with Start over for 5 s. (0.4.0)
- Lists hold up to 100 videos. Shorts show only with the new Show Shorts setting, and live streams carry a LIVE
  tag. (0.4.0)
- Close ends a video at once and gives the speakers back to the car. (0.3.9)

### Controls

- Full screen: the car's title bar and left column are gone, so RideTube gets all 1920 × 720 pixels. (0.4.0)
- The steering wheel's next and previous buttons skip videos, and held they seek. Next also skips a SponsorBlock
  segment or goes to the next chapter. (0.3.13, 0.4.0)
- Drag the progress bar to seek, or double tap the left or right third of the video for 10 s back or forward.
  (0.3.13)
- The car's media screen and the cluster show the video's title, channel and picture. (service 0.3.12)

### Languages

- The app can show in French, Dutch, German, Spanish, Italian, Portuguese, Russian or Simplified Chinese (中文),
  from the same package. The Language setting's Auto follows the car. (0.4.0, 0.4.2)
- YouTube's language and country follow the car's iDrive setting. (0.4.1)
- Titles in Cyrillic, Romanian (ș ț) and Vietnamese keep their letters. (0.3.11, 0.3.14)

### Fewer failures

- Playback recovers by itself after a sound dropout, a failed audio start or a download that dies mid-video, and
  quick taps while a video starts no longer lose it. (service 0.4.0)
- Videos play on a head unit whose clock is wrong, with a one-time security warning. (0.4.0)
- Sound on 2021 head unit software (I_21w12, J18_21w42): the service now builds the audio descriptions those cars
  lack. Not confirmed on those cars yet. (service 0.4.0)
- Fixed: videos that would not play (`ITEM_UNPLAYABLE`), the Search menu closing by itself, live videos failing
  only after two retries, and Previous not going back to 0:00. (0.3.8 to 0.3.13)
- The download stops when the head unit has less than 256 MiB free. (0.3.7)
- yt-dlp updates itself on the car (a setting, on by default), so a fix for a YouTube change no longer waits for a
  RideTube release. Contributed by Alex Arghir. (service 0.4.2)

### Help and safety

- Send logs: one button sends a cleaned-up log and shows a code to add to your GitHub issue. Health check runs
  12 checks on the car and shows which one fails. (0.3.12, 0.4.0)
- Video while driving only turns on when you switch it on while parked, and only after you agree to its
  disclaimer. (0.3.7, 0.4.2)
- Only RideTube itself can talk to its service now; before, any app on the head unit could. (service 0.4.0)

Thanks to @marilykinson-glitch, whose fork brought the History and Liked feeds, related videos, the Shorts
handling, the dropout recovery and the command-sequence tests, and to 小白151 (JackieZ123430) for the Chinese
translation.

## App 0.4.4

- YouTube's dark greys: a #0f0f0f background with grey cards. In fill mode the pages use the whole screen: they
  start at the top, and four wider tiles reach the right edge, with a shelf's next arrow over the fourth tile.
- The rail sits at the screen's left edge, over the strip where the car's back arrow usually is, and the tiles get
  wider. That needs both renderers to give the app taps there, which Full-width touch (below) does. RideTube
  reads each renderer's touch area at start; where one keeps that strip for the car (its default today), the
  rail stays right of it, as in 0.4.3, so a tap meant for RideTube never lands on the hidden back arrow and closes
  the app.
- Health check has a width row: whether taps reach the left edge, and if not, that Full-width touch gives the full
  width.
- The player is grey when no video shows, and the phone remote's QR code is bigger.

## Full-width touch 1.4.0 (`mgu-render-id7-touch`, new Store tool)

- Optional, iDrive 7. It gives both renderers (the Store's `mgu-render` and the kit's `idrive7-renderd`) the
  whole screen as the area apps may claim, 0,0,1920,720 instead of 84,0,1836,720. Apps claim only what they
  draw, so the others still leave the back column to the car and keep its back arrow. Leave a full-screen app with
  the BACK or MENU button.
- Install restarts a renderer only when it runs without that area. Removal puts the renderers' settings back; the
  running renderers keep the area until the head unit's next start.
- The same default is proposed to the renderers themselves (robertnisipeanu/mgu-store and
  cauliflowermossgrape/idrive7-apps). Once it ships, the tool can be removed.

## App 0.4.3

- Search page on the rail: Type a search (typing works only while parked), your last 10 searches as tiles that
  run again with one press, a Clear tile, then the results. A Menu tile opens the car's RideTube menu (account,
  settings, logs). The search page idea comes from @marilykinson-glitch's fork.
- Phone remote (needs service 0.4.1): Phone remote in the menu shows a QR code. A passenger on the car's Wi-Fi
  hotspot scans it, then pastes a YouTube link or types a search on the phone. A link plays as if tapped, with the
  same parked rule; a search gets its results ready in RideTube. The phone page shows in the app's language.
- The iDrive controller reaches every tile on every page by turning, keeps its place when the page changes, and
  push left goes back on the logs, disclaimer and clock pages.

## Service 0.4.1

- The phone remote: a small web page served only while the remote is on, on the car's hotspot address, by a
  process under its own user. Each time it is turned on it gets a new 128-bit key, carried in the QR code. The
  phone can only search, play and ask what is playing; it never reaches the account, the feeds or the logs. At
  most one action a second. It turns off after an hour with no phone action, when RideTube closes, and when the
  service stops. One firewall rule opens the port while it is on, and is removed at off, at exit and at start.
- Fixed: no video would start ("lease DNS" error) when the car's network lease gives its DNS server with a
  port, such as `127.0.0.1:5354`. The fetcher now uses that port instead of 53.

## App 0.4.2

- Video while driving now asks first. Switched on, it shows a disclaimer: only for passengers in a car coded for
  video in motion, follow the law where you drive, and RideTube's authors are not responsible for any misuse,
  accident, fine or damage. The setting counts only once you press I agree; Cancel, or leaving the page, turns
  it off again. A car where it was already on keeps it.
- Six more languages for the app's menus, pages and settings: French, Dutch (also for Flemish), German, Spanish,
  Italian and Portuguese. On Auto, RideTube follows the car's iDrive language; the Language setting can also pick
  one. A car in a language RideTube does not have (Swedish, say) keeps the app in English, while YouTube still
  follows the car. The car's own menu for RideTube shows in the same languages. Texts the service sends (health
  check rows, its error messages) stay in English.

## App 0.4.1

- YouTube's language and country now follow the car's iDrive language setting (de_DE: German, Germany;
  en_GB: English, United Kingdom). The country always comes from the car. The language does on Auto; a language
  picked in Language is used as it is. The app's own text stays in English unless the car is set to Russian or
  Chinese. 0.4.0 sent Russia or China as the country for Russian or Chinese, wherever the car was.
- Needs nothing new on the service: 0.4.0 already takes a language and a country.

## App 0.4.0

- Full screen: RideTube now covers the whole screen. The car's title bar and left column are gone, so the rail,
  the tiles and the player get all 1920 × 720 pixels. Touch works as before. The rail sits just right of the
  car's back-arrow strip at the left edge, because a tap there still goes to the car and closes the app. The
  tiles are a little narrower so four still fit in a row.
- Error messages no longer start with "fetch:".
- A wrong head unit clock: while the service skips the certificate date check (see Service 0.4.0), a security
  warning shows once, until you press OK, and the menu's info line starts with "Wrong clock" until the clock is
  set. An older service sends nothing, so nothing shows.
- History: a new page on the rail and in the menu with the videos you watched, as YouTube lists them on your
  account. It needs you signed in, like Subscriptions.
- Health check: a new menu entry that runs the service's checks on the car and shows one row per check, ok or
  failed, with Run again. A result the service reports as unknown shows a grey dash and does not count as a
  failure.
- Watch next: when the list runs out, the first related video plays after the usual 5 s countdown. The related
  list comes from YouTube's own watch-next answer.
- The steering wheel's next picks the first that applies: skip the SponsorBlock segment you are in (one set to show
  a Skip button), the next video in the list, the next chapter, then the first related video. Held, it still seeks.
- A video that starts where you left it says "Resumed at 12:34 · Start over" for 5 s. Start over goes back to the
  start.
- Lists hold up to 100 videos. Feeds used to stop at 20 and a playlist at 50.
- Shorts show only when the new Show Shorts setting is on (it is off by default), and they never count toward a
  list's 100.
- Live streams and upcoming premieres show a red LIVE tag where the length goes. They can't be played yet, so a
  tap says so instead of trying.
- Russian: the app, its menus and its settings can now show in Russian, from the same package as English. A new
  Language setting offers Auto, English, Русский and 中文. Auto follows the car's language and falls back to
  English. Texts the service sends (health check rows, its error messages) stay in English. Russian YouTube feeds
  (Russian titles and shelves) need service 0.4.0; an older service keeps sending the feeds it sent before.
- Simplified Chinese (中文) comes in the same package: the rail, search, account, playback controls, settings,
  History, the health check and the log report. Chinese titles outside the UI font draw from a GB2312 title
  font. The package grows from about 2.5 MB to 3.2 MB.
- These need service 0.4.0. With an older service the new menu entries stay hidden and the app works as before.

## Service 0.4.0

- A wrong head unit clock. A Send logs report showed every video failing with a TLS error. The head unit's clock
  was 5 weeks behind, so YouTube's certificate looked not yet valid. When the clock reads a date before this
  release's day (`BUILT` in `ytd.js`), the clock is wrong for sure, and the service now skips one TLS check: the
  certificate's validity dates (OpenSSL's `X509_V_FLAG_NO_CHECK_TIME`). The certificate must still chain to a
  trusted CA and match the host name. This covers yt-dlp, the fetcher's own downloads, the health check and the
  service's other requests (feeds, search, SponsorBlock, Send logs). Those go through `ytfetch.py request` while
  the clock is wrong, because Node 8 cannot skip only the dates. Sign-in never skips the dates: with a wrong clock
  it fails with the clock error and you stay signed in, so signed-in feeds stop within about an hour until the
  clock is set. The skip only starts once the app has said `hello`, so the warning can show. The risk: someone
  who holds a certificate ever issued for one of these hosts by a trusted CA, expired or not, with its private
  key, could pose as that host.
  `hello` carries `clock` (the wrong date) and a `clock` event follows any change, so the app can warn the driver.
  The health check's TLS line says when the dates are skipped. A clock ahead of real time cannot be proven wrong:
  its error still says "Wrong head unit clock (date): set the car's date and time" and the video is not retried.
  Thumbnails keep the full check, so they do not show while the clock is wrong.
- `hello`: the app and the service say which version they are and what the service can do, so a new app knows
  what an older service lacks. The service README lists every command and event, and a test keeps that table in
  step with the code.
- New feeds `hist` (your watch history) and `liked` (your Liked videos), and a new `related` command with what
  YouTube plays after a video, kept 10 minutes. Feeds, search and related use the app's language and region.
- Shorts are no longer dropped: they come with `short: true` and the app decides whether to show them.
- Live streams and upcoming premieres come with `live: true` and no length.
- Lists go up to 100 videos (they stopped at 50).
- The History and Liked feed ids, the related videos and the Shorts handling come from @marilykinson-glitch's fork.
- Playback recovers instead of stopping. A buffer underrun from the car's player starts the sound again where it
  was (up to 3 times a minute), a failed audio start is tried once more, and a download that dies mid-video is
  fetched again (twice) while the sound plays on. A quality change keeps the place, even in the first 10 s, and a
  paused video stays paused. Quick taps (stop, quality, pause, seek) during a start no longer restart or lose the
  video. The underrun handling and the command-sequence tests (`tools/test_sequences.js`) come from
  @marilykinson-glitch's fork.
- Sound that does not start (#10): the audio start is now tried a second time, and the health check shows
  whether the car's audio service answers. This is not confirmed fixed yet: a log report from a car where it
  happens still helps.
- `health`: 12 checks (the service, Node, jap-node22, mgu-python, yt-dlp, the internet uid, the uplink lease,
  DNS, TLS to youtube.com, free space, the car's audio service, the control socket). A log report now ends with
  the same lines, redacted like the rest of the log.
- Security: the control socket is now open only to the RideTube app's own user. Before, every app on the head
  unit could use it. The service remembers that user across restarts, and makes the socket root only once
  RideTube is uninstalled. The service also no longer acts as root inside the folders the downloader writes to:
  it reads files there only as plain files and leaves deleting them to the downloader's user. It refuses to start
  if its cache folder is not root's own. Every app on the head unit can write the folder above MainApp's app
  registry, so the service trusts the registry only when MainApp (or root) owns each part of its path, with no
  symlink and nothing world-writable.
- Releases now ship `jap-node22` in RideTube's own catalog, the same file as mgu-apps publishes.
- Sound on 2021 head unit software (seen on `I_21w12` and `J18_21w42`): two Send logs reports showed the service
  never reaching the car's audio, because MainApp on those cars does not carry the description files the service
  read. The service now makes them itself from the head unit's own SOME/IP catalog, with the generator in the head
  unit's firmware, and falls back to a built-in description of what our car uses. This is not confirmed on those
  cars yet. When none of it works, the log and the health check say the car's software does not offer the audio
  connection RideTube uses, once, instead of the same error every minute. A Send logs report also says where each
  description came from, MainApp's version and what the catalog lists for the two audio services.

## App 0.3.14

- Romanian titles and channel names keep every letter. The fonts have the cedilla ş ţ Ş Ţ but not the comma-below
  ș ț Ș Ț that Romanian is written with, so "Știri și Țara" drew as "tiri i ara". A letter an atlas lacks now
  draws as the closest one it has: ș ț Ș Ț as ş ţ Ş Ţ, and an accented Latin letter outside the baked ranges
  (Vietnamese ạ ở, Latin Extended-B and Additional) as its base letter. The atlases are unchanged; an emoji or
  another script is still left out.

## App 0.3.13, service 0.3.12

- The progress bar follows a finger, in the player and in the podcast view while driving: dragged, the bar, the
  time and a bubble with the time it goes to (and its chapter) follow it, and the video goes there when it lets
  go; a tap on the bar jumps there. Pressing the controller on the bar still plays or pauses, and turning it still
  seeks 10 s a detent.
- A double tap on the left or right third of the video goes back or forward 10 s, each further quick tap 10 s
  more ("« 20 s"), as one seek once the taps stop. A single tap still shows or hides the controls, and a tap on a
  control is the control's. The podcast view while driving keeps its big buttons only.
- Service: the car's media player (the cluster, the media screen) can show the video's title, channel and
  thumbnail instead of "unknown title" and "unknown artist". BMW's media player is given only the audio file,
  so the service now writes them into it as standard MP4 tags. Videos already in the car's cache get them
  when they are fetched again.
- The steering wheel's next / previous buttons skip videos: next plays the next one in the row, shelf or playlist
  it came from, previous goes back to the start after 3 s, else to the one before it. Held, they seek instead
  (10 s a step, faster after 3 s), with one seek when let go. While browsing, a skip plays without bringing up the
  player. The car's media player never passes these buttons to an app, so the app reads
  the steering wheel's skip rocker itself (SteeringWheelPushButton), only while its own video is on. A car without
  that interface installs RideTube without it.
- Service: going back to the very start (Previous, or -10 s in the first 10 s) stays there. The car's player
  ignored a seek to 0:00, so the sound played on where it was and the picture jumped back to it a second later.
- Service: the `player metadata:` log line shows text values by their length only, so a log report never
  carries a title or a channel name.

## App 0.3.12, service 0.3.11

- Send logs to the developer: a new menu entry, and a button next to Try again when a video fails. It asks
  first, then sends the service's recent log and shows a short code to add to your GitHub issue (#10). Account
  details and the videos you watched are removed before anything leaves the car. If reporting is closed, busy or
  offline, it says so, and an older service says it needs an update.
- Service: `send_logs` sends the last 1500 lines of the service log (kept in memory) and the end of ytdec's log to
  the developer's log relay, only when the app asks. Account values (tokens, client id and secret, sign-in codes),
  e-mail addresses, VINs, public IP addresses, video titles and channel names are removed, URLs are cut to their
  host, and video, playlist and channel ids become tags (`v#1a2b`) that change with every report.

## App 0.3.11

- Cyrillic titles and channel names show every letter. The fonts the app draws with had only Latin letters, so
  "Поправка a B58" lost all its Cyrillic. Text with Cyrillic now draws from a companion font of the same weight
  and size, which also has every Latin letter the main fonts have, so mixed titles ("Café — Кофе",
  "Đorđe / Ђорђе") keep their accents. It covers Russian, Ukrainian, Belarusian, Bulgarian, Serbian, Macedonian
  and Kazakh. Latin-only text draws as before. The app grows by about 1 MiB (the companion fonts).

## App 0.3.10

- Playlists: a new page on the rail and in the Search menu with your playlists (Liked videos and the ones you
  made or saved), each with its first video's picture and its video count. A playlist opens as its videos; one
  played goes on through the rest of the playlist. Members-only videos are left out unless the setting is on, as
  in Watch later. Needs service 0.3.10: an older one says so on the page.
- A video played from a grid (Watch later, search results, a playlist) goes on through the whole grid, not just
  the rest of its row of four.

## App 0.3.9

- Close: the player's overlay (middle left), the podcast view while driving (after the controls) and the HMI menu
  (Close video) end the video at once: the service stops the sound, gives the speakers back and ends the decoder,
  nothing plays next, and the list it came from shows again. The service is unchanged (its `stop` command).

## Service 0.3.10

- Playlists: `playlists` lists the account's playlists from the TV app's Playlists page, or from the Save to
  playlist list when that page refuses or lists none; `playlist` gives one playlist's videos.
- A live video (or a premiere, or a live that just ended) now fails at once with "Live videos can't be played
  yet", with no retries. Before, it failed after two retries with yt-dlp's "m3u8 download detected but ffmpeg
  could not be found" (#2). YouTube offers those only as HLS, which needs ffmpeg, and the head unit has none.
- The video is picked from the plain https formats only, so an HLS format is never chosen for a normal video.

## Service 0.3.9

- Videos play again: each video's folder was 0700, so BMW's media engine (its own uid) could not open the audio
  and the car answered `ITEM_UNPLAYABLE`. The folders are now 0711: the engine opens the audio by name, and
  nobody can list them. Folders cached by 0.3.8 are fixed when they are played.

## App 0.3.8

- Search: the menu opened from the rail's Search stays open. Before, the video page came back over it about a
  second later, because the head unit keeps that page listed under the menu. The kit now shows the page only
  while it is the screen of ours that came to the front last.

## App 0.3.7, service 0.3.8

- Video while driving takes effect only once switched on while the car is parked.
- The download stops when less than 256 MiB is left free on the head unit.
- README: data use, tested on, uninstall.

## App 0.3.6, service 0.3.7

First public release.
