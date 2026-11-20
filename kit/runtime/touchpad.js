'use strict';
/**
 * touchpad.js - the iDrive controller's touchpad (ControllerElements.ZBETouchFrontSide): a pointer and two-finger scrolling.
 *
 * The pad reports fingers only in touch mode, which the HMI turns on in its speller (FrontCCU.ccsControlTouchCCU
 * = TOUCH_AKTIV): statusSystemMode 3, finger 1 at X1/Y1, finger 2 at touchCcoordinatesX2FrontSide (sic, the
 * schema's name) / Y2, 0 / 0 = no finger, about 0..470 each way, Y grows upwards, ~50 Hz, each sample twice;
 * Z1 = 2 = no finger on the pad though the coordinates are not 0 (measured by Moonride, 03/11).
 *
 *   const pad = new Touchpad((dy) => ctx.scroll(dy), (dx, dy) => ctx.pointer.move(dx, dy), () => ctx.pointer.tap());
 *   signals.watch('de.bmw.infotainment.ControllerElements', '1', { ZBETouchFrontSide: (v) => pad.feed(v) });
 *   const mode = new TouchMode(signals, log); mode.want(shown);  // touch mode while the app shows, off after
 *
 * Two fingers moved up: the content goes up with them (natural scrolling, as on an iPhone). One finger moves the
 * pointer (display.js: what is under it gets the controller), a short tap presses what it is on.
 */
const MODE = 3;
const START = 6;     // pad units the two fingers go before a scroll starts (a resting hand's wobble is no scroll)
const PX = 2.5;      // page px per pad unit of two-finger travel: a whole pad ~ 1100 px, two screens of tiles
const TAP_MS = 220, TAP_MOVE = 12;                     // a tap: one finger, this short, moved less (pad units)
const G_MIN = 1.6, G_MAX = 7, V_LO = 0.08, V_HI = 0.9;  // pointer px per pad unit: G_MIN at <= V_LO units/ms, G_MAX at >= V_HI
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/**
 * One finger = the pointer, with acceleration (slow = fine, a flick crosses the screen): move(dx, dy) screen px;
 * a short still touch = tap(). Two fingers = scroll(dy) page px. Which it is stays fixed until every finger lifts.
 */
class Touchpad {
    constructor(scroll, move, tap) { Object.assign(this, { scroll, move: move || null, tap: tap || null }); this.reset(); }
    reset() { this.d = null; this.last = null; this.acc = 0; this.rx = 0; this.ry = 0; this.v = 0; this.mt = 0; }
    lift(now) {
        const d = this.d;
        if (d && d.n === 1 && this.tap && now - d.t <= TAP_MS && d.moved <= TAP_MOVE) { try { this.tap(); } catch (e) { /* the page's */ } }
        this.reset();
    }
    feed(v, now) {
        now = now || Date.now();
        const x1 = v ? v.touchCoordinatesX1FrontSide | 0 : 0, y1 = v ? v.touchCoordinatesY1FrontSide | 0 : 0;
        const x2 = v ? (v.touchCcoordinatesX2FrontSide || v.touchCoordinatesX2FrontSide) | 0 : 0, y2 = v ? v.touchCoordinatesY2FrontSide | 0 : 0;
        const f1 = !!(x1 || y1), f2 = !!(x2 || y2), n = (f1 ? 1 : 0) + (f2 ? 1 : 0);
        if (!v || v.statusSystemModeFrontSide !== MODE || !n || (v.touchCoordinatesZ1FrontSide | 0) === 2) { if (this.d) this.lift(now); else this.reset(); return; }
        const pt = n === 2 ? { n, x: (x1 + x2) / 2, y: (y1 + y2) / 2 } : f1 ? { n, x: x1, y: y1 } : { n, x: x2, y: y2 };
        if (!this.d) this.d = { t: now, n, moved: 0, x0: pt.x, y0: pt.y, on: false };
        const d = this.d, l = this.last;
        d.n = Math.max(d.n, n);
        if (l && l.x === pt.x && l.y === pt.y && l.n === pt.n) return;          // the doubled sample
        this.last = { n: pt.n, x: pt.x, y: pt.y, t: now };
        if (!l || l.n !== pt.n) { d.x0 = pt.x; d.y0 = pt.y; return; }          // a finger landed or lifted: no jump
        const dx = pt.x - l.x, dy = pt.y - l.y;
        d.moved = Math.max(d.moved, Math.abs(pt.x - d.x0) + Math.abs(pt.y - d.y0));
        if (d.n === 2) {                                                        // scroll
            if (n !== 2) return;
            if (!d.on && Math.abs(pt.y - d.y0) < START) return;
            d.on = true;
            this.acc += dy * PX;                                                // fingers up (pad Y+) = further down the page (+)
            const k = Math.trunc(this.acc);
            if (k) { this.acc -= k; try { this.scroll(k); } catch (e) { /* the page's */ } }
            return;
        }
        if (!this.move || (now - d.t < TAP_MS && d.moved <= TAP_MOVE)) return;   // still a possible tap: the pointer holds still
        let ex = dx, ey = dy, dt = clamp(now - l.t, 10, 100);
        if (!d.on) { d.on = true; ex = pt.x - d.x0; ey = pt.y - d.y0; dt = Math.max(10, now - d.t); }   // what was held back
        const sp = Math.hypot(ex, ey) / dt;
        this.v = this.mt && now - this.mt <= 100 ? 0.6 * sp + 0.4 * this.v : sp;
        this.mt = now;
        const g = G_MIN + (G_MAX - G_MIN) * clamp((this.v - V_LO) / (V_HI - V_LO), 0, 1);
        this.rx += ex * g; this.ry -= ey * g;                                    // the pad's Y grows upwards, the screen's down
        const mx = Math.trunc(this.rx), my = Math.trunc(this.ry);
        if (mx || my) { this.rx -= mx; this.ry -= my; try { this.move(mx, my); } catch (e) { /* the page's */ } }
    }
}

/**
 * Touch mode on the controller (FrontCCU.ccsControlTouchCCU, as Moonride and the HMI's speller set it): want(true)
 * while the app shows, want(false) when it hides or stops. Written only on a change; the HMI turning it off under
 * us (its speller closed) is answered by want(true) again, 5 writes a show at most: never a fight with the HMI.
 */
const IFACE = 'de.bmw.infotainment.controlelements.FrontCCU';
class TouchMode {
    constructor(signals, log) {
        Object.assign(this, { signals, log, p: null, on: false, writes: 0, alive: 0, t: 0 });
        this.ready = Promise.resolve().then(() => signals.proxy(IFACE, '1')).then((p) => { this.p = p; return this.write(false); },
            (e) => log.warn('touch mode: ' + e));
    }
    want(on) {
        on = !!on;
        if (on === this.on) return Promise.resolve();
        if (on && this.writes >= 5) return Promise.resolve();
        if (!on) this.writes = 0;
        this.on = on;
        return this.ready.then(() => this.write(on));
    }
    /** the pad said it left touch mode while we want it: ask once more (counted) */
    lost() { if (this.on && Date.now() - this.t > 1500) { this.on = false; this.want(true); } }
    write(on) {
        if (!this.p) return Promise.resolve();
        if (on) this.writes++;
        this.t = Date.now();
        const v = { aliveControlTouchZBEFrontSide: this.alive = (this.alive + 1) % 15,
            controlTouchActiveFrontSide: on ? 'TOUCH_AKTIV' : 'TOUCH_NICHT_AKTIV', controlIcon: 15 };
        return this.signals.set(this.p, 'ccsControlTouchCCU', v).then(() => this.log.info('touch mode ' + v.controlTouchActiveFrontSide),
            (e) => this.log.warn('touch mode ' + v.controlTouchActiveFrontSide + ': ' + e));
    }
}

module.exports = { Touchpad, TouchMode, MODE };
