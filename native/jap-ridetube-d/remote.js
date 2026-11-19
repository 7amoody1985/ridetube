'use strict';
// SPDX-License-Identifier: GPL-3.0-or-later
/**
 * remote.js - the phone remote (0.5.0, cap remote): a passenger's phone on the car's own Wi-Fi hotspot opens a page
 * served by the car and sends a YouTube link (played) or a search to the RideTube app. Nothing is hosted outside the
 * car. Node 8. The design follows the MGU Store's phone page (mgu-updater js/web.js, GPL-3.0-or-later), reimplemented.
 *
 * In the daemon (root):  const rc = new Remote(opts, hooks)
 *   rc.set(true)   a new 128-bit token; remote.sock (<web uid>:root 0600); the HTTP child as the web uid; the firewall
 *                  rule. While on, `remote` is said again whenever the URL or the time left changes.
 *   rc.set(false)  the child stopped, remote.sock removed, the rule removed. rc.set(<not a bool>): only says the state.
 *   rc.off(why)    the same, from the daemon: the app went away, the time ran out, the child died
 *   rc.cleanup()   at start: a rule an earlier run left is removed.    rc.close(): at exit, as off, the rule removed
 *   hooks: log(line), emit(ev) (to the app), hasApp(), shared() (ctl.sock open to every app), uid() (the web uid,
 *   throws when there is none), status() ({state, id, title, elapsed, total}), idRe (ytd.js's ID_RE)
 *   The app gets {"ev":"remote","on","url","expires"} (url: http://<hotspot address>:<port>/#<token>, null while the
 *   hotspot has no address; expires: seconds left; "error" when it could not be turned on) and, per phone action,
 *   {"ev":"remote_do","do":"search","q"} or {"ev":"remote_do","do":"play","id"}: the app carries it out itself.
 *
 * remote.sock (the child is its only client): JSON lines, at most 4 KiB each.
 *   child -> root: {"rid":n,"cmd":"search","q"} | {"rid":n,"cmd":"play","id"} | {"rid":n,"cmd":"status"}
 *   root -> child: {"rid":n,"ok":true} | {"rid":n,"error"} | {"rid":n,"status":{state,id,title,elapsed,total}}
 *   Those three only: root checks the id (ID_RE) and the query again, and nothing else reaches it (never ctl.sock's
 *   commands: auth, sign_out, feed, positions, send_logs...).
 *
 * The child: `node remote.js serve` as the web uid (no groups, env {}, cwd /), exits when its stdin closes.
 *   stdin:  {"token","port","sock","page"} first, then {"addr":"<ipv4>"|null} when the hotspot's address changes
 *   stdout: {"listening":["127.0.0.1",..],"error"} and {"log":"<line>"}
 *   It listens on 127.0.0.1 and on the hotspot interface's (wlan_bridge) IPv4 address while there is one.
 *   GET / is the page (remote.html, no external assets). With "Authorization: Bearer <token>" (constant-time compare):
 *     GET  /api/status          {state, id, title, elapsed, total}
 *     POST /api/send {"text"}   JSON only, 16 KiB at most: a YouTube video link -> play its id; another link -> 400;
 *                               any other text -> a search (at most 200 characters)
 *   An address with 10 wrong tokens gets 429 until the remote is turned off (the next one has a new token anyway).
 *
 * Firewall: the unit's input chain (table ip filter) drops what it does not accept. While on, one rule at its top accepts
 * the port from the hotspot interface, tagged with a comment; every on, off, start and exit removes tagged rules first,
 * and it is checked every 30 s (a ruleset reload removes it). Replies leave through the output chain's established
 * accept. `nft`, as the Store's phone page on the same units.
 */
const fs = require('fs');
const os = require('os');
const net = require('net');
const url = require('url');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const cp = require('child_process');

const TAG = 'jap-ridetube-d-remote';
const ID_RE = /^[A-Za-z0-9_-]{11}$/;   // ytd.js's ID_RE (root checks again with that one)
const TOKEN_RE = /^Bearer ([0-9a-f]{32})$/;
const IFACE_RE = /^[A-Za-z0-9_.-]{1,15}$/;
const Q_MAX = 200, TEXT_MAX = 2048, BODY_MAX = 16 * 1024, LINE_MAX = 4096, FAIL_MAX = 10;
const ASK_MS = 5000;
// the hosts a pasted link may name, and the paths that carry a video id
const HOSTS = ['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be', 'www.youtube-nocookie.com', 'youtube-nocookie.com'];
const ID_PATHS = ['shorts', 'live', 'embed', 'v'];

function defaults(o) {
    return {
        remoteSock: '/run/jap-ridetube-d/remote.sock',
        remotePort: 8471,                 // (the Store's phone page has 8470)
        remoteIface: 'wlan_bridge',       // the car's own hotspot
        remoteMs: 30 * 60000,             // off by itself this long after it was turned on or last used
        remotePollMs: 5000,               // the hotspot's address looked at this often
        remoteRuleMs: 30000,              // the firewall rule checked this often
        nft: ['nft'],
        remoteCmd: [process.execPath, __filename, 'serve'],
        remotePage: path.join(__dirname, 'remote.html'),
        interfaces: () => os.networkInterfaces()
    };
}

// a search as typed: control characters and runs of spaces made one space; null when empty or too long
function cleanQuery(q) {
    if (typeof q !== 'string') return null;
    const s = q.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim();
    return s && s.length <= Q_MAX ? s : null;
}
// what a pasted text is: undefined (no web link: a search), null (a link, but to no YouTube video) or the video id.
// The first http(s) link in the text counts (a phone's share text may put words around it); a YouTube host typed
// without the scheme too
function parseLink(text) {
    const s = String(text || '').trim();
    const m = /https?:\/\/\S+/i.exec(s);
    const bare = /^((www|m|music)\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)(\/|$)/i.test(s) ? 'https://' + s.split(/\s/)[0] : null;
    if (!m && !bare) return undefined;   // words (another scheme too: only searched for, never opened)
    let u;
    try { u = url.parse(m ? m[0] : bare, true); } catch (e) { return null; }
    const host = String(u.hostname || '').toLowerCase(), p = String(u.pathname || '').split('/').filter(Boolean);
    if (HOSTS.indexOf(host) < 0) return null;
    const id = host === 'youtu.be' ? p[0] : p[0] === 'watch' ? u.query.v : ID_PATHS.indexOf(p[0]) >= 0 ? p[1] : undefined;
    return typeof id === 'string' && ID_RE.test(id) ? id : null;
}
// one line of a less trusted process for root's log: printable, short
const clip = (s) => String(s).replace(/[^\x20-\x7e]/g, '?').slice(0, 200);

/* ---- in the daemon (root) ----------------------------------------------------------------------------------- */

function Remote(o, hooks) {
    this.o = Object.assign(defaults(), o || {});
    this.h = hooks;
    this.run = null;
    this.q = Promise.resolve();   // firewall changes, one at a time, in the order asked
    this.lastError = null;
}
Remote.prototype.nft = function (args) {
    const cmd = this.o.nft;
    return new Promise((resolve, reject) => {
        // 2 s: removal must fit in the daemon's 4 s exit
        cp.execFile(cmd[0], cmd.slice(1).concat(args), { timeout: 2000, maxBuffer: 1 << 20, env: {} }, (err, out, errout) => {
            if (err) reject(new Error('nft ' + args.join(' ') + ': ' + String(errout || err.message).trim()));
            else resolve(String(out));
        });
    });
};
// the handles of our tagged rules in ip filter input; null when that chain cannot be listed (no unit firewall here)
Remote.prototype.handles = function () {
    return this.nft(['-a', 'list', 'chain', 'ip', 'filter', 'input']).then((out) => out.split('\n')
        .filter((l) => l.indexOf('comment "' + TAG + '"') >= 0)
        .map((l) => /# handle (\d+)\s*$/.exec(l)).filter(Boolean).map((m) => m[1]), (e) => {
        if (e.message !== this.listError) this.h.log('remote: ' + e.message + ' (no rule needed or possible)');
        this.listError = e.message;
        return null;
    });
};
Remote.prototype.removeRules = function () {
    return this.handles().then((hs) => (hs || []).reduce((p, h) =>
        p.then(() => this.nft(['delete', 'rule', 'ip', 'filter', 'input', 'handle', h])), Promise.resolve()));
};
Remote.prototype.ensureRule = function (iface, port) {
    return this.handles().then((hs) => {
        if (!hs || hs.length) return undefined;   // no unit firewall here, or the rule is in
        return this.nft(['insert', 'rule', 'ip', 'filter', 'input', 'iifname', '"' + iface + '"',
            'tcp', 'dport', String(port), 'accept', 'comment', '"' + TAG + '"']);
    });
};
Remote.prototype.queued = function (fn) {
    this.q = this.q.then(fn, fn).catch((e) => this.h.log('remote: ' + e.message));
    return this.q;
};
// the interface's IPv4 address (Node 18.0-18.3 says family 4), null without one
Remote.prototype.addr = function (iface) {
    let list = [];
    try { list = this.o.interfaces()[iface] || []; } catch (e) { /* none */ }
    const a = list.filter((x) => (x.family === 'IPv4' || x.family === 4) && !x.internal)[0];
    return a ? a.address : null;
};
// {ev:'remote', on, url, expires}: url only once the child listens on the hotspot address root itself sees
Remote.prototype.state = function () {
    const r = this.run;
    if (!r) return Object.assign({ ev: 'remote', on: false, url: null, expires: 0 }, this.lastError ? { error: this.lastError } : {});
    const served = r.addr && r.listening.indexOf(r.addr) >= 0;
    return { ev: 'remote', on: true, url: served ? 'http://' + r.addr + ':' + r.port + '/#' + r.token : null,
        expires: Math.max(0, Math.round((r.until - Date.now()) / 1000)) };
};
Remote.prototype.say = function () { this.h.emit(this.state()); };

Remote.prototype.set = function (on) {
    if (on !== true && on !== false) { this.say(); return this.q; }
    this.lastError = null;
    if (!on) {
        if (this.run) this.h.log('remote: off');
        this.stop();
        this.say();
        return this.queued(() => this.removeRules());
    }
    return this.start();
};
Remote.prototype.off = function (why) {
    if (!this.run) return this.q;
    this.h.log('remote: off (' + why + ')');
    this.stop();
    this.say();
    return this.queued(() => this.removeRules());
};
Remote.prototype.cleanup = function () { return this.queued(() => this.removeRules()); };
Remote.prototype.close = function () { this.stop(); return this.queued(() => this.removeRules()); };

Remote.prototype.start = function () {
    this.stop();   // on again: a new token, the old one dead
    const o = this.o, port = Number(o.remotePort), iface = String(o.remoteIface);
    const fail = (msg) => {
        this.h.log('remote: not on: ' + msg);
        this.lastError = msg;
        this.say();
        return this.queued(() => this.removeRules());
    };
    if (this.h.shared()) return fail('the control socket is open to every app');
    if (!IFACE_RE.test(iface) || !(port > 1023 && port < 65536)) return fail('bad interface or port');
    let uid;
    try { uid = this.h.uid(); } catch (e) { return fail(e.message); }
    if (!(uid > 0)) return fail('no web uid');
    const r = { token: crypto.randomBytes(16).toString('hex'), uid, port, iface, addr: null, listening: [], child: null,
        server: null, client: null, timers: [], expiry: null, until: 0 };
    this.run = r;
    try { this.listenSock(r); } catch (e) { this.stop(); return fail('remote.sock: ' + e.message); }
    r.addr = this.addr(iface);
    if (!this.spawn(r)) return this.q;
    r.timers.push(setInterval(() => {
        const a = this.addr(iface);
        if (a === r.addr) return;
        r.addr = a;
        this.send(r, { addr: a });
        this.say();
    }, o.remotePollMs));
    r.timers.push(setInterval(() => this.queued(() => (this.run === r ? this.ensureRule(iface, port) : undefined)), o.remoteRuleMs));
    this.touch(r);
    this.h.log('remote: on, port ' + port + ' on ' + iface + (r.addr ? '' : ' (no address yet)'));
    return this.queued(() => this.removeRules()).then(() => this.queued(() => (this.run === r ? this.ensureRule(iface, port) : undefined)));
};
// the time left starts again (turned on, a phone action)
Remote.prototype.touch = function (r) {
    clearTimeout(r.expiry);
    r.until = Date.now() + this.o.remoteMs;
    r.expiry = setTimeout(() => this.off('time is up'), this.o.remoteMs);
    this.say();
};
Remote.prototype.stop = function () {
    const r = this.run;
    this.run = null;
    if (!r) return;
    r.timers.forEach(clearInterval);
    clearTimeout(r.expiry);
    if (r.child) { try { r.child.stdin.end(); r.child.kill('SIGTERM'); } catch (e) { /* gone */ } }
    if (r.client) r.client.destroy();
    if (r.server) r.server.close();
    try { fs.unlinkSync(this.o.remoteSock); } catch (e) { /* none */ }
};

// remote.sock: created 0600 (umask: the bind itself is synchronous, so no other uid can connect in between), then
// handed to the web uid, as ctl.sock is to the app's
Remote.prototype.listenSock = function (r) {
    const sock = this.o.remoteSock;
    try { fs.unlinkSync(sock); } catch (e) { /* none */ }
    const server = net.createServer((c) => this.onPhone(r, c));
    server.on('error', (e) => { if (this.run === r) this.off('remote.sock: ' + e.message); });
    const old = process.umask(0o177);
    try { server.listen(sock); } finally { process.umask(old); }
    r.server = server;
    fs.chmodSync(sock, 0o600);
    fs.chownSync(sock, r.uid, 0);
};
Remote.prototype.onPhone = function (r, c) {
    if (this.run !== r) { c.destroy(); return; }
    if (r.client) r.client.destroy();   // one client: the child
    r.client = c;
    c.setEncoding('utf8');
    let buf = '';
    c.on('data', (d) => {
        buf += d;
        if (buf.length > LINE_MAX) { this.h.log('remote: remote.sock line too long'); c.destroy(); return; }
        let i;
        while ((i = buf.indexOf('\n')) >= 0) {
            const line = buf.slice(0, i);
            buf = buf.slice(i + 1);
            if (this.run !== r) return;
            try { this.onLine(r, c, line); } catch (e) { this.h.log('remote: ' + e.message); }
        }
    });
    c.on('error', () => { /* close follows */ });
    c.on('close', () => { if (r.client === c) r.client = null; });
};
// the allowlist: search, play, status, nothing else
Remote.prototype.onLine = function (r, c, line) {
    let m = null;
    try { m = JSON.parse(line); } catch (e) { /* bad: answered below */ }
    const rid = m && typeof m.rid === 'number' && m.rid >= 0 && m.rid === Math.floor(m.rid) ? m.rid : null;
    const reply = (x) => c.write(JSON.stringify(Object.assign({ rid }, x)) + '\n');
    if (!m || typeof m !== 'object') return reply({ error: 'bad request' });
    const idRe = this.h.idRe || ID_RE;
    switch (m.cmd) {
    case 'search': {
        const q = cleanQuery(m.q);
        return q ? this.act(r, reply, { ev: 'remote_do', do: 'search', q }) : reply({ error: 'bad search' });
    }
    case 'play':
        return typeof m.id === 'string' && idRe.test(m.id) ? this.act(r, reply, { ev: 'remote_do', do: 'play', id: m.id }) : reply({ error: 'bad id' });
    case 'status': {
        const s = this.h.status();
        return reply({ status: { state: s.state, id: s.id || null, title: s.title || null, elapsed: s.elapsed || 0, total: s.total || 0 } });
    }
    default:
        this.h.log('remote: refused ' + (/^\w{1,20}$/.test(String(m.cmd)) ? m.cmd : '?'));
        return reply({ error: 'not allowed' });
    }
};
Remote.prototype.act = function (r, reply, ev) {
    if (!this.h.hasApp()) return reply({ error: 'RideTube is not open on the car' });
    this.h.log('remote: phone ' + ev.do);   // (never the query or the id)
    this.h.emit(ev);
    this.touch(r);
    return reply({ ok: true });
};

Remote.prototype.send = function (r, msg) {
    if (r.child && r.child.stdin.writable) r.child.stdin.write(JSON.stringify(msg) + '\n');
};
// the child as the web uid; it dying turns the remote off (the app says so; turning it on again starts a new one)
Remote.prototype.spawn = function (r) {
    const cmd = this.o.remoteCmd, ids = this.o.noSetuid ? {} : { uid: r.uid, gid: r.uid };
    let child;
    try { child = cp.spawn(cmd[0], cmd.slice(1), Object.assign(ids, { cwd: '/', env: {}, stdio: ['pipe', 'pipe', 'ignore'] })); } catch (e) {
        this.lastError = 'the server did not start';
        this.off('server: ' + e.message);
        return false;
    }
    r.child = child;
    child.stdin.on('error', () => { /* gone: exit follows */ });
    child.stdout.setEncoding('utf8');
    let buf = '';
    child.stdout.on('data', (d) => {
        buf += d;
        if (buf.length > 65536) { try { child.kill('SIGKILL'); } catch (e) { /* gone */ } return; }
        let i;
        while ((i = buf.indexOf('\n')) >= 0) {
            const line = buf.slice(0, i);
            buf = buf.slice(i + 1);
            let m;
            try { m = JSON.parse(line); } catch (e) { continue; }
            if (!m || typeof m !== 'object') continue;
            if (typeof m.log === 'string') this.h.log('remote: web: ' + clip(m.log));
            else if (Array.isArray(m.listening) && this.run === r) {
                const before = JSON.stringify(this.state());
                r.listening = m.listening.filter((a) => typeof a === 'string');
                if (JSON.stringify(this.state()) !== before) this.say();
            }
        }
    });
    const gone = (why) => {
        if (r.child !== child) return;
        r.child = null;
        if (this.run !== r) return;
        this.lastError = 'the server stopped';
        this.off('the server stopped (' + why + ')');
    };
    child.on('error', (e) => gone(e.message));
    child.on('exit', (code, sig) => gone(sig || 'exit ' + code));
    this.send(r, { token: r.token, port: r.port, sock: this.o.remoteSock, page: this.o.remotePage });
    this.send(r, { addr: r.addr });
    return true;
};

/* ---- the server (child, the web uid) ------------------------------------------------------------------------ */

function serve() {
    const emit = (o) => process.stdout.write(JSON.stringify(o) + '\n');
    const say = (l) => emit({ log: l });
    const hash = (s) => crypto.createHash('sha256').update(String(s)).digest();
    let cfg = null, tokenHash = null, page = '', csp = '';

    /* -- remote.sock: one connection, replies by rid -- */
    let sock = null, rid = 0;
    const pending = new Map();
    const connect = () => {
        const s = net.connect(cfg.sock);
        let buf = '';
        s.setEncoding('utf8');
        s.on('connect', () => { sock = s; });
        s.on('data', (d) => {
            buf += d;
            if (buf.length > 65536) { s.destroy(); return; }
            let i;
            while ((i = buf.indexOf('\n')) >= 0) {
                const line = buf.slice(0, i);
                buf = buf.slice(i + 1);
                let m;
                try { m = JSON.parse(line); } catch (e) { continue; }
                const p = m && pending.get(m.rid);
                if (p) { pending.delete(m.rid); clearTimeout(p.timer); p.resolve(m); }
            }
        });
        s.on('error', () => { /* close follows */ });
        s.on('close', () => {
            if (sock === s) sock = null;
            pending.forEach((p) => { clearTimeout(p.timer); p.reject(new Error('the car did not answer')); });
            pending.clear();
            setTimeout(connect, 1000);
        });
    };
    const ask = (req) => new Promise((resolve, reject) => {
        if (!sock) { reject(new Error('the car did not answer')); return; }
        const id = ++rid;
        const timer = setTimeout(() => { pending.delete(id); reject(new Error('the car did not answer')); }, ASK_MS);
        pending.set(id, { resolve, reject, timer });
        sock.write(JSON.stringify(Object.assign({}, req, { rid: id })) + '\n');
    });

    /* -- HTTP -- */
    const fails = new Map();   // address -> wrong tokens (this run: a new token is a new run)
    const lockedOut = (ip) => (fails.get(fails.has(ip) || fails.size < 256 ? ip : '*') || 0) >= FAIL_MAX;
    const failed = (ip) => { const k = fails.has(ip) || fails.size < 256 ? ip : '*'; fails.set(k, (fails.get(k) || 0) + 1); };
    const authorised = (req) => {
        const m = TOKEN_RE.exec(req.headers.authorization || '');
        return !!m && crypto.timingSafeEqual(hash(m[1]), tokenHash);
    };
    const reply = (res, code, type, body, extra) => {
        res.writeHead(code, Object.assign({
            'Content-Type': type, 'Content-Length': Buffer.byteLength(body), 'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer'
        }, extra || {}));
        res.end(body);
    };
    const json = (res, code, obj) => reply(res, code, 'application/json; charset=utf-8', JSON.stringify(obj));
    const readBody = (req, cb) => {
        let size = 0, done = false;
        const parts = [];
        req.on('data', (c) => {
            if (done) return;
            size += c.length;
            if (size > BODY_MAX) { done = true; cb(new Error('too large')); req.pause(); return; }
            parts.push(c);
        });
        req.on('end', () => { if (!done) { done = true; cb(null, Buffer.concat(parts).toString('utf8')); } });
        req.on('error', () => { if (!done) { done = true; cb(new Error('aborted')); } });
    };
    const handle = (req, res) => {
        const p = String(req.url || '').split('?')[0];
        if (p === '/' && (req.method === 'GET' || req.method === 'HEAD')) {
            reply(res, 200, 'text/html; charset=utf-8', page, { 'Content-Security-Policy': csp });
            return;
        }
        if (p !== '/api/status' && p !== '/api/send') { json(res, 404, { error: 'not found' }); return; }
        const ip = String(req.socket.remoteAddress);
        if (lockedOut(ip)) { json(res, 429, { error: 'too many wrong codes: turn the phone remote off and on in the car' }); return; }
        if (!authorised(req)) {
            if (req.headers.authorization) failed(ip);   // a wrong token; a request without one guesses nothing
            json(res, 401, { error: 'scan the code on the car\'s screen' });
            return;
        }
        const fail = (e) => json(res, 503, { error: e.message });
        if (p === '/api/status' && req.method === 'GET') {
            ask({ cmd: 'status' }).then((m) => (m.status ? json(res, 200, m.status) : json(res, 502, { error: 'no status' })), fail);
        } else if (p === '/api/send' && req.method === 'POST') {
            if (!/^application\/json\b/.test(req.headers['content-type'] || '')) { json(res, 415, { error: 'JSON only' }); return; }
            readBody(req, (err, text) => {
                if (err) { json(res, 413, { error: 'too large' }); return; }
                let b = null;
                try { b = JSON.parse(text); } catch (e) { /* below */ }
                const t = b && typeof b === 'object' && typeof b.text === 'string' && b.text.length <= TEXT_MAX ? b.text : null;
                if (t === null) { json(res, 400, { error: 'send {"text"}' }); return; }
                const id = parseLink(t), q = id === undefined ? cleanQuery(t) : null;
                if (id === null) { json(res, 400, { error: 'not a YouTube video link' }); return; }
                if (id === undefined && !q) { json(res, 400, { error: 'type a search (at most ' + Q_MAX + ' characters)' }); return; }
                const req2 = id ? { cmd: 'play', id } : { cmd: 'search', q };
                ask(req2).then((m) => (m.ok ? json(res, 200, { ok: true, did: req2.cmd }) : json(res, 422, { error: String(m.error || 'refused') })), fail);
            });
        } else json(res, 405, { error: 'method not allowed' });
    };

    /* -- listening: 127.0.0.1 always, the hotspot address while there is one -- */
    const servers = new Map();   // host -> {server, up}
    let want = ['127.0.0.1'];
    const report = () => emit({ listening: want.filter((h) => servers.has(h) && servers.get(h).up), error: null });
    const sync = () => {
        servers.forEach((s, host) => { if (want.indexOf(host) < 0) { servers.delete(host); s.server.close(); } });
        want.forEach((host) => {
            if (servers.has(host)) return;
            const server = http.createServer(handle), entry = { server, up: false };
            servers.set(host, entry);
            server.maxConnections = 32;
            server.keepAliveTimeout = 5000;
            server.setTimeout(30000);
            server.on('clientError', (e, s) => s.destroy());
            server.on('error', (e) => {
                if (servers.get(host) === entry) servers.delete(host);
                say('cannot listen on ' + host + ':' + cfg.port + ': ' + (e.code || e.message));
                report();
                setTimeout(() => { if (want.indexOf(host) >= 0 && !servers.has(host)) sync(); }, 5000);
            });
            server.listen({ host, port: cfg.port }, () => { entry.up = true; say('listening on ' + host + ':' + cfg.port); report(); });
        });
        report();
    };

    let input = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (d) => {
        input += d;
        let i;
        while ((i = input.indexOf('\n')) >= 0) {
            const line = input.slice(0, i);
            input = input.slice(i + 1);
            let m;
            try { m = JSON.parse(line); } catch (e) { continue; }
            if (!cfg) {
                cfg = m;
                tokenHash = hash(cfg.token);
                try { page = fs.readFileSync(cfg.page, 'utf8'); } catch (e) { page = '<!doctype html><title>RideTube</title><p>The page is missing.'; say('page: ' + e.message); }
                const script = (/<script>([\s\S]*?)<\/script>/.exec(page) || [null, ''])[1];
                csp = "default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-" + crypto.createHash('sha256').update(script).digest('base64') +
                    "'; connect-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";
                connect();
                sync();
            } else if (m.addr !== undefined) {
                want = ['127.0.0.1'].concat(typeof m.addr === 'string' && net.isIPv4(m.addr) ? [m.addr] : []);
                sync();
            }
        }
    });
    process.stdin.on('end', () => process.exit(0));
}

module.exports = { Remote, parseLink, cleanQuery, TAG, Q_MAX };

if (require.main === module && process.argv[2] === 'serve') serve();
