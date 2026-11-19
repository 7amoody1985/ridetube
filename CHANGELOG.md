# Changelog

## Unreleased

- Simplified Chinese: an optional zh-CN RideTube build with the rail, search, account and playback controls,
  the native settings and the common status messages in Chinese. Chinese titles outside the UI font draw from a
  GB2312 title font baked at 14 and 52 px, so large titles stay sharp. The English build is unchanged.
- Service: playback recovers instead of stopping. A buffer underrun from the car's player starts the sound again
  where it was (up to 3 times a minute), a failed audio start is tried once more, and a download that dies
  mid-video is fetched again (twice) while the sound plays on. A quality change keeps the place, even in the
  first 10 s, and a paused video stays paused. Quick taps (stop, quality, pause, seek) during a start no longer
  restart or lose the video. The underrun handling and the command-sequence tests (`tools/test_sequences.js`)
  come from @marilykinson-glitch's fork.

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
