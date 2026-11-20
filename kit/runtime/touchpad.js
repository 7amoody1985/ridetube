'use strict';
/**
 * touchpad.js - the iDrive controller's touchpad (ControllerElements.ZBETouchFrontSide) as two-finger scrolling.
 *
 * The pad reports fingers only in touch mode, which the HMI turns on in its speller (FrontCCU.ccsControlTouchCCU
 * = TOUCH_AKTIV): statusSystemMode 3, finger 1 at X1/Y1, finger 2 at touchCcoordinatesX2FrontSide (sic, the
 * schema's name) / Y2, 0 / 0 = no finger, about 0..470 each way, Y grows upwards, ~50 Hz, each sample twice;
 * Z1 = 2 = no finger on the pad though the coordinates are not 0 (measured by Moonride, 03/11).
 *
 *   const pad = new TwoFingerScroll((dy) => ctx.scroll(dy));   // dy page px, + = further down
 *   signals.watch('de.bmw.infotainment.ControllerElements', '1', { ZBETouchFrontSide: (v) => pad.feed(v) });
 *   const mode = new TouchMode(signals, log); mode.want(shown);  // touch mode while the app shows, off after
 *
 * Two fingers moved up: the content goes up with them (natural scrolling, as on an iPhone). One finger: nothing.
 */
const MODE = 3;
const START = 6;     // pad units the two fingers go before a scroll starts (a resting hand's wobble is no scroll)
const PX = 2.5;      // page px per pad unit: a whole pad's travel ~ 1100 px, two screens of tiles

class TwoFingerScroll {
    constructor(scroll) { this.scroll = scroll; this.reset(); }
    reset() { this.last = null; this.y0 = 0; this.acc = 0; this.on = false; }
    feed(v) {
        if (!v) { this.reset(); return; }
        const x1 = v.touchCoordinatesX1FrontSide | 0, y1 = v.touchCoordinatesY1FrontSide | 0;
        const x2 = (v.touchCcoordinatesX2FrontSide || v.touchCoordinatesX2FrontSide) | 0, y2 = v.touchCoordinatesY2FrontSide | 0;
        const two = v.statusSystemModeFrontSide === MODE && (x1 || y1) && (x2 || y2) && (v.touchCoordinatesZ1FrontSide | 0) !== 2;
        if (!two) { this.reset(); return; }
        const y = (y1 + y2) / 2;
        if (this.last === null) { this.last = this.y0 = y; return; }
        const dy = y - this.last;
        this.last = y;
        if (!this.on && Math.abs(y - this.y0) < START) return;
        this.on = true;
        this.acc += dy * PX;                         // fingers up (pad Y+) = further down the page (+)
        const n = Math.trunc(this.acc);
        if (n) { this.acc -= n; try { this.scroll(n); } catch (e) { /* the page's */ } }
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

module.exports = { TwoFingerScroll, TouchMode, MODE };
