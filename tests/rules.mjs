// Runs the rules the site (assets/app.js) and the Home Screen widget (widgets/psa10-widget.js) apply on the repo's own
// data, for the last N snapshots, and prints the results as JSON. tests/test_rules.py compares them with the Python
// scripts that apply the same rules (raw price, trading rate, insights, tier review, odds, event rule) and the
// site with the widget (verdict pills, limit hits, sell signals, correction / rally / event rules).
//
//   node tests/rules.mjs [N]        N = how many of the latest snapshots (default 3)
//
// Both files are loaded in a sandbox with a stand-in DOM / Scriptable API and a frozen clock (the snapshot's time),
// through their test hooks (window.__PSA10_TEST__ / globalThis.__PSA10_TEST__), which hand over the rule functions
// and start nothing.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const N = Number(process.argv[2] || 3);
const J = (p, d = null) => { try { return JSON.parse(fs.readFileSync(path.join(root, p), 'utf8')); } catch (e) { return d; } };

const clock = { now: 0 };
const RealDate = Date;
class FrozenDate extends RealDate {
  constructor(...a) { if (a.length) super(...a); else super(clock.now); }
  static now() { return clock.now; }
}
// A stand-in for any DOM object: every property is itself, calling it returns itself.
function anything() {
  const f = function () { return p; };
  const p = new Proxy(f, { get: (t, k) => (k === Symbol.toPrimitive ? () => '' : k === 'then' ? undefined : p), set: () => true, apply: () => p });
  return p;
}
const base = () => ({ console, Intl, Math, JSON, Promise, Map, Set, WeakMap, Array, Object, Number, String, Boolean, RegExp, Error, Symbol,
  Float64Array, Uint8Array, parseInt, parseFloat, isNaN, isFinite, encodeURIComponent, decodeURIComponent, URLSearchParams,
  Date: FrozenDate, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {} });

// ---- the site
let app = null;
const mem = new Map();
const win = { innerHeight: 900, visualViewport: null, addEventListener() {}, matchMedia: () => ({ matches: false, addEventListener() {} }),
  __PSA10_TEST__: (api) => { app = api; } };
const appCtx = Object.assign(base(), { window: win, document: anything(), navigator: {}, location: { hash: '' },
  localStorage: { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) } });
vm.createContext(appCtx);
vm.runInContext(fs.readFileSync(path.join(root, 'assets/app.js'), 'utf8'), appCtx, { filename: 'assets/app.js' });
if (!app) throw new Error('assets/app.js did not call its test hook');

// ---- the widget
let wid = null;
class Color { constructor(h) { this.hex = h; } }
const widCtx = Object.assign(base(), {
  Color, Font: class { static boldSystemFont() { return {}; } static systemFont() { return {}; } },
  FileManager: { local: () => ({ joinPath: (a, b) => a + '/' + b, cacheDirectory: () => '/tmp', fileExists: () => false, createDirectory() {} }) },
  Device: { isPad: () => true, screenSize: () => ({ width: 1024, height: 768 }) },
  config: { runsInApp: false, runsInWidget: false, widgetFamily: 'medium' }, args: { queryParameters: {}, widgetParameter: '' },
  Script: { name: () => 'test', complete() {}, setWidget() {} },
  __PSA10_TEST__: (api) => { wid = api; },
});
vm.createContext(widCtx);
await vm.runInContext(`(async () => {\n${fs.readFileSync(path.join(root, 'widgets/psa10-widget.js'), 'utf8')}\n})()`, widCtx, { filename: 'widgets/psa10-widget.js' });
if (!wid) throw new Error('widgets/psa10-widget.js did not call its test hook');

// ---- data
const manifest = J('data/manifest.json');
const snaps = manifest.snapshots.slice().sort((a, b) => a.collected_at_jst.localeCompare(b.collected_at_jst));
const hist = J('data/history.json'), ci = J('data/custom_index.json'), events = J('data/events.json'), hold = J('data/holdings.json', {});
const limits = (J('data/limits.json', {}) || {}).limits || {}, targets = (J('data/sell_targets.json', {}) || {}).targets || {};
const removed = Object.keys((J('data/removed_cards.json', {}) || {}).removed || {});
const id = (c) => (c.url || '').replace(/\/+$/, '').split('/').pop();
const r3 = (x) => (x == null ? null : Math.round(x * 1000) / 1000);

const out = [];
for (let k = Math.max(0, snaps.length - N); k < snaps.length; k++) {
  const snap = J('data/snapshots/' + snaps[k].file), prev = k ? J('data/snapshots/' + snaps[k - 1].file) : null;
  const keep = (d) => d && Object.assign({}, d, { cards: (d.cards || []).filter((c) => !removed.includes(id(c))) });
  clock.now = RealDate.parse(snap.collected_at_jst);
  Object.assign(app.state, {
    currentData: keep(snap), previousData: keep(prev), hist, customIndex: ci, events, holdings: hold.holdings || [], sealed: hold.sealed || [],
    sold: hold.sold || [], syncedLimits: limits, syncedTargets: targets, oddsModel: J('data/odds_model.json'), valueModel: J('data/value_model.json'),
    premium: J('data/premium.json'), insights: J('data/insights.json'), hype: J('data/hype.json'), mercari: null, heldPrices: {},
  });
  const cs = app.state.currentData.cards;
  const d = { snap: app.state.currentData, limits, hist, ci, events, holdings: hold.holdings || [], targets };
  const m = wid.buildModel(d);
  const cards = cs.map((c) => {
    const g = c.grades || {}, t = (c.analysis || {}).tiers, ask = app.lowestAsk(c), lim = (limits[c.url] || {}).price;
    const rp = app.rawPrice(c), ps = app.salesPerDay((g.psa10 || {}).recent_completed_sales, snap.collected_at_jst), rs = app.salesPerDay((g.raw_a_grade || {}).recent_completed_sales, snap.collected_at_jst);
    const tr = app.tierReview(c), st = app.sellState(c), wx = m.cards.find((x) => x.c.url === c.url), ev = app.eventFor(c), wev = wid.eventFor(d, c);
    const prices = [t && t.definitely_buy, t && t.buy_upper, lim, ask && Math.round(ask * 0.9 / 500) * 500].filter(Boolean);
    return {
      url: c.url, name: c.card_name_ja, ask: ask ?? null, raw: rp ? rp.v : null, heat: [ps ? ps.rate : null, rs ? rs.rate : null],
      insights: app.insightsFor(c).map((x) => [x.key, r3(x.score)]),
      tier_due: tr ? tr.due : null, tier_reasons: tr ? tr.reasons : [],
      odds: prices.map((p) => { const o = app.touchOdds(c, p); return [p, o ? (o.reached ? 'reached' : [r3(o.p30), r3(o.p90)]) : null]; }),
      tag: app.displayTagFor(c), sell: st ? st.tag : null, limit_hit: app.limitHit(c), event: ev ? ev.name : null,
      widget: wx ? { tag: wx.tag, limit_hit: wx.limitHit, sell: wx.own ? wx.own.tag : null } : null, widget_event: wev ? wev.name : null,
    };
  });
  const cs0 = app.correctionState(), rl = app.rallyState();
  out.push({ file: snaps[k].file, at: snap.collected_at_jst, cards,
    correction: { active: cs0.active, pct: r3(cs0.pct) }, widget_correction: { active: m.corr.on, pct: r3(m.corr.pct) },
    rally: { active: rl.active, pct: r3(rl.pct) }, widget_rally: { active: m.rally.on, pct: r3(m.rally.pct) },
    events: app.activeEvents().map((e) => e.name) });
}
process.stdout.write(JSON.stringify(out));
