'use strict';
/**
 * The Search page (the rail's Search; the page idea after marilykinson-glitch's fork, written anew): a row of
 * tiles - Type a search (the HMI's speller, parked only: driving, the tile says why and main.js's type() opens nothing),
 * Menu (the HMI menu: the account, Settings, Send logs; the rail's Search opened it before), the recent searches
 * (newest first, a press runs one again), Clear recent searches - then the last search's results as a grid, or
 * what became of it.
 * The service has no suggestions, so none are shown here (the HMI menu keeps its fixed ones).
 * The recent searches live in the app's settings (key "recent", at most 10; the HMI menu shows the first ones).
 *
 *   const page = require('./search')({ settings, legacy, model, t, whole, message, moving, type, run, menu, flash, changed, glyphs });
 *   page.add(q); page.clear(); page.list()       // the recent searches
 *   drawPage(cv, page.sections(shown))           // from main.js's results page
 */
const fs = require('fs');

const MAX = 10;

module.exports = function searchPage(o) {
    const { settings, model, t } = o;
    const clean = (a) => (Array.isArray(a) ? a.filter((s) => typeof s === 'string' && s.trim()).slice(0, MAX) : null);
    // first run with this version: the list 0.4 kept in recent.json (data dir), once
    let list = clean(settings.get('recent'));
    if (!list) {
        try { list = clean(JSON.parse(fs.readFileSync(o.legacy, 'utf8'))); } catch (e) { list = null; }
        list = list || [];
        if (list.length) settings.set('recent', list);
        try { fs.unlinkSync(o.legacy); } catch (e) { /* none */ }   // (no old searches left behind a Clear)
    }
    const save = () => settings.set('recent', list.slice());
    function add(q) {
        list = [q].concat(list.filter((s) => s.toLowerCase() !== q.toLowerCase())).slice(0, MAX);
        save();
    }
    function clear() { list = []; save(); }

    // a magnifier, big enough for a tile's picture
    const LENS = (cv, cx, cy, c) => { cv.arc(cx - 10, cy - 10, 26, 34, 0, 360, c); cv.line(cx + 12, cy + 12, cx + 36, cy + 36, 9, c); };
    function sections(shown) {
        const moving = o.moving(), g = o.glyphs();
        const type = { id: '::type', title: t('Type a search'), sub: moving ? t('Typing works only while parked') : t('Opens the keyboard'), glyph: g.KEYS,
            act: o.type };                                    // (type: parked only, else the note why)
        const recents = list.map((q, i) => ({ id: '::recent' + i, title: q, glyph: LENS, act: () => o.run(q) }));
        const clr = list.length ? [{ id: '::clear', title: t('Clear recent searches'), glyph: g.X, act: () => { clear(); o.changed(); } }] : [];
        const menu = { id: '::menu', title: t('Menu'), sub: t('Account, settings, logs'), glyph: g.ALL, act: o.menu };
        const out = [{ title: t('Search'), items: [type, menu].concat(recents, clr), chan: true }];
        // the last search: its results, or a line saying what became of it (no row of tiles under it)
        const q = model.q;
        if (model.searching) out.push({ title: o.message('Searching "{query}"...', { query: q }), items: [] });
        else if (model.searchError) out.push({ title: t('Search: ') + o.whole(model.searchError), sub: t('Try again from Search'), items: [] });
        else if (q && !model.results.length) out.push({ title: o.message('Nothing found for "{query}"', { query: q }), sub: t('Try other words'), items: [] });
        else if (q) out.push({ title: o.message('Results for “{query}”', { query: q }), items: shown(model.results), grid: true });
        return out;
    }
    return { add, clear, sections, list: () => list, MAX };
};
