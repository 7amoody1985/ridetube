'use strict';
/**
 * The phone remote page (cap remote, service 0.4.1): a passenger's phone on the car's own Wi-Fi hotspot scans the QR
 * code shown here, opens the page the car serves and sends a YouTube link or a search. The service hands each phone
 * action to the app (remote_do); main.js carries it out as a tap would (the parked rule and the screen stay the app's).
 * Off by default; Turn on / Turn off here (where the HMI runs the screen, the menu entry pressed again). The QR code (the
 * URL with the access code in its fragment) shows only while the remote is on.
 *
 *   const remote = require('./remote')({ model, send, changed, lang, say, fit, t, message, C, QR, focus, X0, TOP, H, W, OFF, OFF2 });
 *   remote.onDo = ({do, q|id}) => ...   main.js: a checked phone action, only while the remote is on
 *   remote.onMsg(m)     every daemon event: hello (a service with the cap: its remote's state asked; a new connection may
 *                       find it on), remote, remote_do
 *   remote.refresh()    asks the service for the state (the page opened)
 *   remote.toggle()     on / off
 *   remote.down()       the service went away: off
 *   remote.draw(cv)     from render, mode 'remote'
 */
const VID_RE = /^[\w-]{11}$/, Q_MAX = 200;
const URL_RE = /^http:\/\/(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})\/#[0-9a-f]{32}$/;

module.exports = function remotePage(o) {
    const { model, t, C, QR, H, W } = o;   // t: translate; o.message: a sentence with {values}; o.X0 per frame (fill)
    const LIT = { literal: true }, LITB = { literal: true, font: 'bold' };
    const st = { on: false, url: null, expires: 0, at: 0, error: null, asking: false };
    const page = {
        onDo: null,
        state: st,
        onMsg(m) {
            if (m.ev === 'hello') {
                if (Array.isArray(m.caps) && m.caps.indexOf('remote') >= 0) o.send({ cmd: 'remote' });
            } else if (m.ev === 'remote') {
                st.on = m.on === true;
                st.url = st.on && typeof m.url === 'string' && URL_RE.test(m.url) ? m.url : null;
                st.expires = typeof m.expires === 'number' && m.expires > 0 ? m.expires : 0;
                st.at = Date.now();
                st.error = !st.on && typeof m.error === 'string' ? m.error.slice(0, 120) : null;
                st.asking = false;
            } else if (m.ev === 'remote_do' && st.on && page.onDo) {
                // checked again here: only a search of words or a video id, as a tap would send
                if (m.do === 'search' && typeof m.q === 'string' && m.q.trim() && m.q.length <= Q_MAX) page.onDo({ do: 'search', q: m.q.trim() });
                else if (m.do === 'play' && typeof m.id === 'string' && VID_RE.test(m.id)) page.onDo({ do: 'play', id: m.id });
            }
        },
        refresh() { if (model.can('remote')) o.send({ cmd: 'remote' }); },
        toggle() {
            if (!model.can('remote') || st.asking) return false;
            st.asking = true; st.error = null;
            if (o.send({ cmd: 'remote', on: !st.on, lang: o.lang() })) { o.changed(); return true; }   // (the phone page in the app's language)
            st.asking = false;
            return false;
        },
        down() { st.on = false; st.url = null; st.asking = false; },
        draw(cv) {
            const X0 = o.X0, TOP = o.TOP;
            if (!model.connected) return o.say(cv, o.OFF, o.OFF2);
            const bottom = H + (cv.own ? cv.extra : 0);
            const tw = cv.text(t('Phone remote'), X0, TOP + 44, 30, '#ffffff', LITB);
            const head = st.asking ? t('Please wait...') : st.on ? t('Switched on') : t('Switched off');
            cv.text(o.fit(cv, head, 22, 600, LIT), X0 + tw + 18, TOP + 44, 22, st.on ? '#35d07f' : C.dim, LIT);
            let y = TOP + 100;
            const line = (s, size, color, bold) => { cv.text(o.fit(cv, s, size, W - X0 - 40, bold ? LITB : LIT), X0, y, size, color, bold ? LITB : LIT); y += size + 18; };
            if (st.on && st.url) {
                // the code on the left, as big as the page allows; the steps right of it
                const n = (() => { try { return QR.encode(st.url).length; } catch (e) { return 0; } })();
                const mod = n ? Math.max(4, Math.min(12, Math.floor((bottom - TOP - 40) / (n + 8)))) : 0, side = (n + 8) * mod;
                let x = X0;
                if (n) { QR.draw(cv, st.url, X0, TOP + 70, mod); x = X0 + side + 48; }
                const m = URL_RE.exec(st.url), left = Math.max(1, Math.ceil((st.expires * 1000 - (Date.now() - st.at)) / 60000));
                y = TOP + 120;
                const step = (s, size, color, bold) => { cv.text(o.fit(cv, s, size, W - x - 40, bold ? LITB : LIT), x, y, size, color, bold ? LITB : LIT); y += size + 20; };
                step(t('1. Connect the phone to the car\'s Wi-Fi hotspot'), 32, C.text);
                step(t('2. Scan this code with its camera'), 32, C.text);
                step(t('3. Paste a YouTube link or type a search, then send'), 32, C.text);
                if (!n) step(m[1] + ':' + m[2], 24, C.amber, true);
                step(o.message('Address {address} · turns off by itself in {minutes} min', { address: m[1] + ':' + m[2], minutes: left }), 22, C.dim);
                step(t('Anyone with this code can send videos while it is on'), 22, C.dim);
                button(cv, x, bottom, t('Turn off'));
                return undefined;
            }
            if (st.on) {
                line(t('Waiting for the car\'s Wi-Fi hotspot'), 30, C.text, true);
                line(t('Turn on the car\'s Wi-Fi hotspot, then the code shows here'), 24, C.dim);
                button(cv, X0, bottom, t('Turn off'));
                return undefined;
            }
            line(t('A passenger\'s phone sends videos and searches to RideTube'), 30, C.text, true);
            t('The phone joins the car\'s Wi-Fi hotspot and scans a code shown here; the page comes from the car itself.').replace(/([;；])\s*/, '$1\n').split('\n').forEach((s) => line(s, 24, C.dim));
            // (the service's own words, in English: not in the catalogs)
            if (st.error) line(o.message('Could not turn it on: {error}', { error: st.error }), 24, '#ffb3b3');
            button(cv, X0, bottom, t('Turn on'));
            return undefined;
        }
    };
    // Turn on / Turn off where the kit runs the screen; where the HMI does, the menu entry pressed again
    function button(cv, x, bottom, label) {
        const btnH = 76, by = bottom - btnH - 20;
        if (!cv.own) { cv.text(t('To switch it, press Phone remote in the menu again'), x, by + 48, 24, C.dim, LIT); return; }
        if (st.asking) return;
        const bw = Math.max(300, cv.textWidth(label, 30, LITB) + 80), f = o.focus() === 'remote:toggle';
        cv.roundRect(x, by, bw, btnH, 38, f ? '#ffffff' : C.red);
        cv.text(label, x + bw / 2, by + 49, 30, f ? '#0f0f0f' : '#ffffff', { literal: true, font: 'bold', align: 'center' });
        cv.target(x, by, bw, btnH, () => page.toggle(), 'remote:toggle', 38);
    }
    return page;
};
