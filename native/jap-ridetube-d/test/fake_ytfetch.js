#!/usr/bin/env node
'use strict';
// stands in for ytfetch.py in test_ytd.js: argv = [ctl, 'fetch', '--cache-dir', c, ('--info', f,) '--', id, dir]. Logs its argv, env,
// cwd, uid to <ctl>.log, writes the files as ytfetch.py does, then waits for <ctl> to say done or error.
// <ctl> at start: "fail" = an error before audio is ready ("gone": a refused video); "head" = audio_head (60 s) before the video, audio_ready
// after it; "hold" = audio_head, audio_ready only once <ctl> says "full" or "done"; "dead" = an error before audio is ready, and
// one running dies at it too ("error": only one running); else audio_ready, no head.
// serve: says warm, then runs the argv list read as the FIRST LINE of stdin (logged with served: true; stdin may stay open after it). extract: makes <dir>'s folder (as ytfetch.py does), writes <dir> = info.json.
// update: logs its argv to <ctl>.update.log; <ctl>.update says what it finds: "new:<version>" (writes pyz/<version>/ytdlp.pyz
// and pyz/current.json in its --cache-dir, as ytfetch.py does), "same" (nothing newer) or "fail".
// WP8 --stream A,B: says {ev:stream, from_ms (--start-ms or 0), fragment, fragments...} after meta, or, when <ctl> says "spill" at start,
// {ev:spill, dir: --spill-dir} and writes its files there. Its video events' ms start at from_ms (+5000, +12000). --video-only: no audio
// steps or files. Every stdin line after the job (the daemon's "pos <ms>") is appended to <ctl>.stdin (emptied when a job starts).
// <ctl> "trim" while running: one {ev:trim, ms:30000, bytes:1048576}. A done ends the process even with stdin open.
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const ctl = process.argv[2];
const say = (o) => process.stdout.write(JSON.stringify(o) + '\n');
if (process.argv[3] === 'serve') {
    say({ ev: 'warm' });
    let first = true;
    readline.createInterface({ input: process.stdin }).on('line', (l) => {
        if (first) { first = false; if (l.trim()) run(JSON.parse(l), true); } else stdinLine(l);
    });
} else run(process.argv.slice(3), false);
function stdinLine(l) { fs.appendFileSync(ctl + '.stdin', l + '\n'); }

function run(args, served) {
if (args[0] === 'update') return update(args);
const id = args[args.length - 2];
let dir = args[args.length - 1];
if (args[0] === 'extract') {
    fs.writeFileSync(ctl + '.extract', JSON.stringify({ argv: args, served: served }));
    setTimeout(() => { fs.mkdirSync(path.dirname(dir), { recursive: true }); fs.writeFileSync(dir, JSON.stringify({ id: id })); say({ ev: 'info', id: id }); }, 150);
    return;
}
const mode = () => { try { return fs.readFileSync(ctl, 'utf8').trim(); } catch (e) { return ''; } };
const argOf = (n) => (args.indexOf(n) >= 0 ? args[args.indexOf(n) + 1] : undefined);
const stream = args.indexOf('--stream') >= 0, videoOnly = args.indexOf('--video-only') >= 0, fromMs = Number(argOf('--start-ms')) || 0;
const start = mode(), withHead = (start === 'head' || start === 'hold') && !videoOnly, spill = stream && start === 'spill';
fs.writeFileSync(ctl + '.log', JSON.stringify({ argv: [ctl].concat(args), served: served, env: Object.keys(process.env), cwd: process.cwd(), uid: process.getuid(), pid: process.pid }));
fs.writeFileSync(ctl + '.stdin', '');
if (spill) { dir = argOf('--spill-dir'); say({ ev: 'spill', why: 'test', dir: dir }); }
if (stream && !served) readline.createInterface({ input: process.stdin }).on('line', stdinLine);   // (serve mode reads them already)
let full = videoOnly, trimmed = false;
const audioReady = () => { full = true; fs.renameSync(path.join(dir, 'audio.m4a.part'), path.join(dir, 'audio.m4a')); say({ ev: 'audio_ready', bytes: 1 }); };
const failStart = () => { if (start === 'fail') { say({ ev: 'error', msg: 'boom' }); process.exit(1); } if (start === 'dead') { say({ ev: 'error', msg: 'HTTP 403' }); process.exit(1); } if (start === 'gone') { say({ ev: 'error', msg: 'Video unavailable' }); process.exit(1); } };
const steps = [
    () => { fs.writeFileSync(path.join(dir, 'meta.json'), JSON.stringify({ id: id, title: 'Fetched ' + id, channel: 'C', duration_s: 600 })); say({ ev: 'meta', title: 'Fetched ' + id, duration_s: 600 }); }
];
if (stream && !spill) steps.push(() => { failStart(); say({ ev: 'stream', ahead_ms: 120000, behind_ms: 45000, need: 5000000, video_bytes: 20000000, from_ms: fromMs, fragment: Math.floor(fromMs / 4000) + 1, fragments: 150 }); });
if (!videoOnly) steps.push(
    () => { failStart(); fs.writeFileSync(path.join(dir, 'audio.m4a.part'), 'a'); say({ ev: 'audio', pct: 50 }); },
    () => { if (withHead) { fs.writeFileSync(path.join(dir, 'audio.head.m4a'), 'h'); say({ ev: 'audio_head', ms: 60000, bytes: 1 }); } else audioReady(); });
else steps.push(failStart);
steps.push(
    () => { fs.writeFileSync(path.join(dir, 'index.bin'), 'i'); fs.writeFileSync(path.join(dir, 'video.h264.part'), 'v'); say({ ev: 'video', ms: fromMs + 5000, frames: 150, bytes: 1, pct: 8 }); },
    () => say({ ev: 'video', ms: fromMs + 12000, frames: 360, bytes: 2, pct: 20 }));
let i = 0;
const t = setInterval(() => {
    if (i < steps.length) return steps[i++]();
    const m = mode();
    if (!full && (start === 'head' || m === 'full' || m === 'done')) audioReady();
    if (m === 'trim' && !trimmed) { trimmed = true; say({ ev: 'trim', ms: 30000, bytes: 1048576 }); }
    if (m === 'done') { fs.renameSync(path.join(dir, 'video.h264.part'), path.join(dir, 'video.h264')); say({ ev: 'done' }); clearInterval(t); process.stdin.destroy(); }
    if (m === 'error' || m === 'dead') { say({ ev: 'error', msg: 'HTTP 403' }); process.exit(1); }
    return undefined;
}, 60);
}

function update(args) {
    fs.writeFileSync(ctl + '.update.log', JSON.stringify({ argv: [ctl].concat(args), env: Object.keys(process.env), uid: process.getuid() }));
    let what = '';
    try { what = fs.readFileSync(ctl + '.update', 'utf8').trim(); } catch (e) { /* none */ }
    const root = path.join(args[args.indexOf('--cache-dir') + 1], 'pyz');
    if (what.indexOf('new:') === 0) {
        const v = what.slice(4), pyz = path.join(root, v, 'ytdlp.pyz');
        fs.mkdirSync(path.dirname(pyz), { recursive: true });
        fs.writeFileSync(pyz, 'zip');
        fs.writeFileSync(path.join(root, 'current.json'), JSON.stringify({ version: v, pyz: pyz, sha256: '00' }));
        return say({ ev: 'ytdlp', state: 'updated', version: v, bundled: '2026.10.26' });
    }
    if (what === 'same') return say({ ev: 'ytdlp', state: 'current', version: '2026.10.26', bundled: '2026.10.26' });
    say({ ev: 'error', msg: 'yt-dlp releases: offline' });
    return process.exit(1);
}
