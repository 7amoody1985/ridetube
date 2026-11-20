'use strict';
/**
 * news.js - What's new: one page at the first open after an update that starts a new series (0.4 -> 0.5), with
 * the series' notes below. A first install shows nothing (nothing is new to them); a series without notes neither.
 * The notes are catalog keys (kit/runtime/locales): each one a line on the page, so keep them short.
 */
const NOTES = {
    '0.5': [
        'Playlists and Watch later show all their videos, not just the first 15',
        'Hold -10 s or +10 s and it turns into previous or next video',
        'Two fingers on the controller\'s touchpad scroll the page, as on a phone',
        'One finger on the touchpad moves a pointer: tap, or press the knob, to play the video under it',
        'Turning the volume shows the level, and whether it goes up or down',
        'The knob goes straight from video to video',
        'With Video while driving agreed to, you can type a search while driving',
    ],
};
const TITLE = 'What\'s new in RideTube {version}';

const series = (v) => String(v).split('.').slice(0, 2).join('.');
/**
 * What to show at this start: { show: series with notes, or null; seen: the series to remember }. seen: the series
 * remembered last time (undefined: none yet); existed: the app had saved settings before this start (an update).
 */
function due(seen, existed, version) {
    const now = series(version);
    if (seen === now || (seen === undefined && !existed)) return { show: null, seen: now };
    // shortcut: an update from before 0.5 with no saved setting at all counts as a first install; fine, it is rare
    return { show: NOTES[now] ? now : null, seen: now };
}

module.exports = { NOTES, TITLE, series, due };
