# Changelog

## App 0.3.10

- Playlists: a new page on the rail and in the Search menu with your playlists (Liked videos and the ones you
  made or saved), each with its first video's picture and its video count. A playlist opens as its videos; one
  played goes on through the rest of the playlist. Members-only videos are left out unless the setting is on, as
  in Watch later. Needs service 0.3.10: an older one says so on the page.
- A video played from a grid (Watch later, search results, a playlist) goes on through the whole grid, not just
  the rest of its row of four.

## Service 0.3.10

- Playlists: `playlists` lists the account's playlists from the TV app's Playlists page, or from the Save to
  playlist list when that page refuses or lists none; `playlist` gives one playlist's videos.

- A live video (or a premiere, or a live that just ended) now fails at once with "Live videos can't be played yet",
  with no retries. Before, it failed after two retries with yt-dlp's "m3u8 download detected but ffmpeg could not be found" (#2). YouTube offers those only as
  HLS, which needs ffmpeg, and the head unit has none.
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
