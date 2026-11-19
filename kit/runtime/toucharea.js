'use strict';
/**
 * Can an app's claims reach the screen's left edge? The renderers (the Store's mgu-render, and idrive7-renderd, the
 * same program) divert a tap to the app only inside their touch_area; its default on iDrive 7 ("auto") leaves the
 * HMI's back column (x < 84) to the HMI, which closes the app when touched there. No message says the area, so it
 * is read the way the renderer reads it: -c FILE and -s key=value in order; the local conf, read last by some builds
 * only, may narrow it but never widens it. Every renderer that
 * routes touch must give the whole width; one unknown or unreadable counts as not (the app then keeps out of x < 84).
 */
const fs = require('fs');

const LOCAL = '/var/opt/mgu-render/mgu-render.local.conf';
const NAMES = ['mgu-render', 'mgu-renderd'];

/** A conf file's text -> { touch_area, touch, local_conf } as written (the last line of each wins). */
function confKeys(text) {
    const o = {};
    String(text).split('\n').forEach((l) => {
        const m = /^\s*(touch_area|touch|local_conf)\s*=\s*(.*?)\s*$/.exec(l);
        if (m) o[m[1]] = m[2];
    });
    return o;
}

/** "0,0,1920,720" -> [0, 0, 1920, 720]; "auto" or anything else -> null. */
function rect(v) {
    const m = /^(-?\d+),(-?\d+),(\d+),(\d+)$/.exec(String(v || '').replace(/\s/g, ''));
    return m ? m.slice(1).map(Number) : null;
}

/**
 * One renderer's command line (argv) -> 'full' (its area reaches x 0 across the width), 'off' (it routes no touch)
 * or 'clipped' (auto, part of the width, or not readable). read(path) returns a file's text, or null.
 */
function rendererArea(argv, width, read) {
    let area = 'auto', touch = '1', local = LOCAL, bad = false;
    const apply = (o) => {
        if (o.touch_area !== undefined) area = o.touch_area;
        if (o.touch !== undefined) touch = o.touch;
        if (o.local_conf !== undefined) local = o.local_conf;
    };
    for (let i = 1; i < argv.length; i++) {
        if (argv[i] === '-c' && i + 1 < argv.length) { const t = read(argv[++i]); if (t === null) bad = true; else apply(confKeys(t)); }
        else if (argv[i] === '-s' && i + 1 < argv.length) { const kv = argv[++i], k = kv.split('=')[0]; const o = {}; o[k] = kv.slice(k.length + 1); apply(o); }
    }
    // the local conf comes last in the renderers that read it (not every build does: then it must not narrow the area either)
    const lt = local ? read(local) : null;
    const lk = lt === null ? {} : confKeys(lt);
    // off only when no reading turns it on (touch = 0 there, and the local conf, if it says, agrees)
    if (Number(touch) === 0 && (lk.touch === undefined || Number(lk.touch) === 0)) return 'off';
    if (bad) return 'clipped';
    const full = (v) => { const r = rect(v); return !!r && r[0] <= 0 && r[0] + r[2] >= width; };
    if (!full(area)) return 'clipped';
    if (lk.touch_area !== undefined && !full(lk.touch_area)) return 'clipped';
    return 'full';
}

/** The running renderers' command lines, from /proc. */
function renderers() {
    const out = [];
    let pids = [];
    try { pids = fs.readdirSync('/proc').filter((p) => /^\d+$/.test(p)); } catch (e) { return out; }
    pids.forEach((p) => {
        let a;
        try { a = fs.readFileSync('/proc/' + p + '/cmdline', 'utf8').split('\0').filter((x, i, all) => x || i < all.length - 1); } catch (e) { return; }
        if (a.length && NAMES.indexOf(a[0].split('/').pop()) >= 0) out.push(a);
    });
    return out;
}

/**
 * { full, why }: full when at least one renderer routes touch and every one that does reaches the left edge.
 * (list, read: tests.)
 */
function leftEdge(width, list, read) {
    read = read || ((f) => { try { return fs.readFileSync(f, 'utf8'); } catch (e) { return null; } });
    const rs = (list || renderers)();
    const seen = {};
    const res = rs.filter((a) => { const k = a.join(' '); if (seen[k]) return false; seen[k] = 1; return true; })   // (a renderer's threads)
        .map((a) => [a[0].split('/').pop(), rendererArea(a, width, read)]);
    const routing = res.filter((r) => r[1] !== 'off');
    return { full: routing.length > 0 && routing.every((r) => r[1] === 'full'), why: res.map((r) => r.join(' ')).join(', ') || 'no renderer seen' };
}

module.exports = { leftEdge, rendererArea, confKeys };
