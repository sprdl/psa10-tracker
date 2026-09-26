// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: yellow; icon-glyph: chart-line;

// PSA10 Tracker widget for Scriptable (iPhone / iPad Home Screen)
// Reads the public data of https://sprdl.github.io/psa10-tracker/ (published by the price checks).
//
// Small:  rotates through cards at your personal limit (they always come first),
//         otherwise through cards in a Buy / Definitely-buy zone.
//         Widget parameter = a SNKRDUNK id (e.g. 455596) pins one card instead.
// Medium: buy signals list + My-tier index.
// Large:  compact overview of every tracked card.
//
// Limits: uses the limits saved "to all devices" (data/limits.json). A limit only changed on
// one device's browser isn't visible to the widget until it's saved to all devices.

const BASE = 'https://sprdl.github.io/psa10-tracker/';
const ROTATE_MINUTES = 15; // one card per slot; iOS decides the exact refresh time

const C = {
  bg: new Color('#0b0b0d'), panel: new Color('#16161a'), line: new Color('#26262b'),
  text: new Color('#f4f4f5'), soft: new Color('#d4d4d8'), muted: new Color('#8e8e96'),
  accent: new Color('#ffd23f'), green: new Color('#45d483'), greenStrong: new Color('#1f9d61'),
  amber: new Color('#f5a524'), red: new Color('#ff6b63'), ice: new Color('#8fd3ff'),
  zoneRed: new Color('#f0524d'), slab: new Color('#e9e9ec'), psaRed: new Color('#b8322c'), white: new Color('#ffffff'),
};
// The web app uses Bebas Neue for display type; DIN Condensed (built into iOS) is the closest match.
const display = (size) => new Font('DINCondensed-Bold', size);

// ---------------------------------------------------------------- data
const fm = FileManager.local();
const cacheDir = fm.joinPath(fm.cacheDirectory(), 'psa10-widget');
if (!fm.fileExists(cacheDir)) fm.createDirectory(cacheDir, true);

async function getJSON(path, optional) {
  const file = fm.joinPath(cacheDir, path.replace(/\//g, '_'));
  try {
    const req = new Request(BASE + path + '?t=' + Math.floor(Date.now() / 300000));
    req.timeoutInterval = 20;
    const json = await req.loadJSON();
    fm.writeString(file, JSON.stringify(json));
    return json;
  } catch (e) {
    if (fm.fileExists(file)) return JSON.parse(fm.readString(file)); // offline: last good copy
    if (optional) return null;
    throw e;
  }
}

async function loadData() {
  const manifest = await getJSON('data/manifest.json');
  const latest = manifest.snapshots.slice().sort((a, b) => a.collected_at_jst.localeCompare(b.collected_at_jst)).pop();
  const [snap, limits, hist, ci, events] = await Promise.all([
    getJSON('data/snapshots/' + latest.file),
    getJSON('data/limits.json', true),
    getJSON('data/history.json', true),
    getJSON('data/custom_index.json', true),
    getJSON('data/events.json', true),
  ]);
  return { snap, limits: (limits && limits.limits) || {}, hist, ci, events };
}

// ---------------------------------------------------------------- same rules as the site
function parseName(name) {
  const m = (name || '').match(/^(.*?)\s*\[([^\]]+)\]\s*\(([^)]+)\)\s*$/);
  return m ? { short: m[1].trim(), code: m[2].trim() } : { short: name || '', code: '' };
}
const cardId = (c) => (c.url || '').replace(/\/+$/, '').split('/').pop();
const lowestAsk = (c) => ((c.grades || {}).psa10 || {}).lowest_price ?? null;
function repPrice(c) {
  const a = c.analysis;
  if (a && a.representative_price != null) return a.representative_price;
  return lowestAsk(c);
}
function liveTag(tiers, p) {
  if (!tiers || p == null) return null;
  if (p <= tiers.definitely_buy) return 'definitely_buy';
  if (p <= tiers.buy_upper) return 'buy';
  if (p <= tiers.ceiling) return 'watch';
  return 'dont_buy';
}
function correctionOn(d) {
  const ser = (d.ci && d.ci.series) || [];
  const ref = d.snap.collected_at_jst.slice(0, 10);
  const past = new Date(Date.parse(ref + 'T00:00:00Z') - 30 * 864e5).toISOString().slice(0, 10);
  let now = null, then = null;
  for (const e of ser) { if (e.d <= ref) now = e; if (e.d <= past) then = e; }
  if (now && then) return { on: (now.level / then.level - 1) * 100 <= -10, pct: (now.level / then.level - 1) * 100, level: now.level };
  const m = ((d.snap.pokeca_chart_index || {}).psa10 || {}).month_change_pct;
  return { on: m != null && m <= -10, pct: m, level: now ? now.level : null };
}
function eventFor(d, card) {
  const evs = (d.events && d.events.events) || [], win = (d.events && d.events.window_days) || 3;
  const today = new Date(Date.now() + 9 * 36e5).toISOString().slice(0, 10);
  const set = (parseName(card.card_name_ja).code.split(/\s+/)[0] || '').toLowerCase();
  return evs.find((e) => {
    if (!e.d || e.major === false) return false;
    const days = Math.round((Date.parse(e.d) - Date.parse(today)) / 864e5);
    if (days < 0 || days > win) return false;
    return !e.scope || e.scope === 'all' || e.scope.some((x) => String(x).toLowerCase() === set);
  }) || null;
}
function displayTag(d, card, corr) {
  const a = card.analysis;
  if (!a) return null;
  if (a.verdict && a.verdict.tag === 'defer') return 'defer';
  const live = liveTag(a.tiers, repPrice(card));
  if (live === 'buy' && (corr.on || eventFor(d, card))) return 'watch';
  return live || (a.verdict && a.verdict.tag) || null;
}
const limitOf = (d, card) => { const e = d.limits[card.url]; return e && typeof e.price === 'number' ? e.price : null; };
function change7d(d, card) {
  const snaps = (d.hist && d.hist.snapshots) || [];
  const cut = Date.parse(d.snap.collected_at_jst) - 7 * 864e5;
  let old = null;
  for (const e of snaps) if (Date.parse(e.d) <= cut && e.p && e.p[card.url]) old = e.p[card.url][0];
  const now = repPrice(card);
  return old && now != null ? (now / old - 1) * 100 : null;
}
function salesPerDay(sales, refIso) {
  const ref = Date.parse(refIso), REL = { '秒': 1 / 86400, '分': 1 / 1440, '時間': 1 / 24, '日': 1, '週間': 7 };
  const ages = (sales || []).map((s) => {
    const w = String(s.when || '');
    let m = w.match(/^(\d+)\s*(秒|分|時間|日|週間)前/);
    if (m) return (Number(m[1]) + 0.5) * REL[m[2]];
    m = w.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})/);
    if (m) return Math.max(0, (ref - Date.parse(`${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}T12:00:00+09:00`)) / 864e5);
    return null;
  }).filter((a) => a != null);
  return ages.length < 2 ? null : ages.length / Math.max(Math.max(...ages), 0.25);
}
function heat(d, card) {
  const r = salesPerDay(((card.grades || {}).psa10 || {}).recent_completed_sales, d.snap.collected_at_jst);
  if (r == null) return null;
  return r >= 5 ? ['HOT', C.red] : r >= 3 ? ['ACTIVE', C.green] : r >= 1.2 ? ['SLOW', C.ice] : ['COLD', C.muted];
}

function buildModel(d) {
  const corr = correctionOn(d);
  const cards = (d.snap.cards || []).filter((c) => lowestAsk(c) != null).map((c) => {
    const lim = limitOf(d, c), ask = lowestAsk(c), tag = displayTag(d, c, corr);
    return { c, id: cardId(c), name: parseName(c.card_name_ja), price: repPrice(c), ask, lim, tag,
      limitHit: lim != null && ask <= lim, chg7: change7d(d, c), heat: heat(d, c), tiers: (c.analysis || {}).tiers };
  });
  const limitHits = cards.filter((x) => x.limitHit);
  const buys = cards.filter((x) => !x.limitHit && (x.tag === 'buy' || x.tag === 'definitely_buy'))
    .sort((a, b) => (a.tag === 'definitely_buy' ? 0 : 1) - (b.tag === 'definitely_buy' ? 0 : 1));
  // closest to a buy: % above your limit, or above the Buy line when there's no limit
  const gap = (x) => x.lim != null ? x.ask / x.lim - 1 : x.tiers ? x.price / x.tiers.buy_upper - 1 : Infinity;
  const closest = cards.filter((x) => !x.limitHit && x.tag !== 'buy' && x.tag !== 'definitely_buy').sort((a, b) => gap(a) - gap(b));
  return { cards, limitHits, buys, closest, gap, corr, when: d.snap.collected_at_jst };
}

// ---------------------------------------------------------------- drawing helpers
const yen = (n) => n == null ? '—' : '¥' + Math.round(n).toLocaleString('en-US');
const pct = (v) => v == null ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '±') + Math.abs(v).toFixed(1) + '%';
const pctColor = (v) => v == null ? C.muted : v > 0 ? C.green : v < 0 ? C.red : C.muted;
const TAG = { definitely_buy: ['DEF. BUY', C.greenStrong, true], buy: ['BUY', C.green, true], watch: ['WATCH', C.amber, false],
  dont_buy: ["DON'T BUY", C.red, false], defer: ['DEFER', C.muted, false] };

function txt(stack, s, size, color, bold, lines) {
  const t = stack.addText(String(s));
  t.font = bold ? Font.boldSystemFont(size) : Font.systemFont(size);
  t.textColor = color || C.text;
  if (lines) t.lineLimit = lines;
  t.minimumScaleFactor = 0.7;
  return t;
}
function pill(stack, label, color, filled, size) {
  const f = size || 10, p = stack.addStack();
  p.setPadding(f > 9 ? 2 : 1, f > 9 ? 6 : 4, f > 9 ? 2 : 1, f > 9 ? 6 : 4); p.cornerRadius = 3; p.borderWidth = 1; p.borderColor = color;
  if (filled) p.backgroundColor = color;
  const t = p.addText(label); t.font = Font.boldSystemFont(f); t.textColor = filled ? C.bg : color; t.lineLimit = 1;
  return p;
}

// Sizes for the medium widget. Widgets are laid out at a fixed size in points and iPadOS then
// scales the whole widget down to fit its Home Screen grid, so the iPad uses the ~348 pt layout.
// On iPhone the medium widget's width depends on the screen width.
function mediumWidth() {
  if (Device.isPad()) return 348;
  const sw = Math.min(Device.screenSize().width, Device.screenSize().height);
  return sw >= 428 ? 364 : sw >= 414 ? 360 : sw >= 390 ? 338 : sw >= 375 ? 329 : 292;
}
const COMPACT = false;
const MZ = (() => {
  const W = mediumWidth(), pad = 12, gap = 8;
  const tileW = Math.floor((W - 2 * (pad + 2) - 2 * gap) / 3);
  const slabW = Math.round(tileW * 0.33);
  return { pad, tileW, gap, slabW, slabH: Math.round(slabW * 1.45), price: tileW >= 100 ? 20 : 18, name: 9, small: 8.5, logo: 15, spark: [46, 16], bar: 9, pill: 8 };
})();

function tagPill(stack, x, short, size) {
  if (x.limitHit) return pill(stack, short ? 'LIMIT' : 'LIMIT HIT', C.accent, true, size);
  if (TAG[x.tag]) return pill(stack, TAG[x.tag][0], TAG[x.tag][1], TAG[x.tag][2], size);
  return null;
}
function dtxt(stack, s, size, color) {
  const t = stack.addText(String(s)); t.font = display(size); t.textColor = color || C.text; t.lineLimit = 1; t.minimumScaleFactor = 0.6;
  return t;
}

// PSA slab like the app's: light grey case, white label with a red top edge, card art below.
function slabImage(art, w, h) {
  const d = new DrawContext(); d.size = new Size(w, h); d.opaque = false; d.respectScreenScale = true;
  const all = new Path(); all.addRoundedRect(new Rect(0, 0, w, h), 3, 3); d.addPath(all); d.setFillColor(C.slab); d.fillPath();
  const lh = Math.round(h * 0.13);
  d.setFillColor(C.white); d.fillRect(new Rect(2, 2, w - 4, lh));
  d.setFillColor(C.psaRed); d.fillRect(new Rect(2, 2, w - 4, 1.2));
  const ay = 2 + lh + 2, aw = w - 4, ah = h - ay - 2;
  d.setFillColor(new Color('#26262b')); d.fillRect(new Rect(2, ay, aw, ah));
  if (art) {
    const r = Math.min(aw / art.size.width, ah / art.size.height);
    const iw = art.size.width * r, ih = art.size.height * r;
    d.drawImageInRect(art, new Rect(2 + (aw - iw) / 2, ay + (ah - ih) / 2, iw, ih));
  }
  return d.getImage();
}

// Zone bar like the app's: green (definitely buy) / light green (buy) / amber (watch) / red, white tick = price, yellow dot = your limit.
function zoneBarImage(x, w, hh) {
  const h = hh || 10, d = new DrawContext(); d.size = new Size(w, h); d.opaque = false; d.respectScreenScale = true;
  const t = x.tiers;
  if (!t) return null;
  const peak = (x.c.analysis && x.c.analysis.peak && x.c.analysis.peak.price) || 0;
  const scale = Math.round(Math.max(peak, t.ceiling) * 1.08 / 1000) * 1000 || t.ceiling;
  const X = (v) => Math.max(0, Math.min(w, (v / scale) * w));
  const th = Math.max(3, Math.round(h * 0.4)), y = (h - th) / 2;
  const seg = (a, b, col) => { d.setFillColor(col); d.fillRect(new Rect(X(a), y, Math.max(0, X(b) - X(a)), th)); };
  seg(0, t.definitely_buy, C.greenStrong); seg(t.definitely_buy, t.buy_upper, C.green); seg(t.buy_upper, t.ceiling, C.amber); seg(t.ceiling, scale, C.zoneRed);
  if (x.lim != null) { const r = h * 0.35; d.setFillColor(C.accent); d.fillEllipse(new Rect(X(x.lim) - r, h / 2 - r, 2 * r, 2 * r)); }
  d.setFillColor(C.text); d.fillRect(new Rect(X(x.price) - 1, 0, 2, h));
  return d.getImage();
}

// My-tier index sparkline (last 120 days of data/custom_index.json).
function sparkImage(ci, w, h) {
  const ser = ((ci && ci.series) || []);
  if (ser.length < 2) return null;
  const end = Date.parse(ser[ser.length - 1].d), pts = ser.filter((e) => Date.parse(e.d) >= end - 120 * 864e5);
  const vals = pts.map((e) => e.level), lo = Math.min(...vals), hi = Math.max(...vals), t0 = Date.parse(pts[0].d);
  const d = new DrawContext(); d.size = new Size(w, h); d.opaque = false; d.respectScreenScale = true;
  const path = new Path();
  pts.forEach((e, i) => {
    const px = ((Date.parse(e.d) - t0) / (end - t0 || 1)) * (w - 2) + 1, py = h - 1 - ((e.level - lo) / (hi - lo || 1)) * (h - 2);
    i ? path.addLine(new Point(px, py)) : path.move(new Point(px, py));
  });
  d.addPath(path); d.setStrokeColor(C.accent); d.setLineWidth(1.5); d.strokePath();
  return d.getImage();
}

function header(w, m, ci, z) {
  z = z || MZ;
  const head = w.addStack(); head.centerAlignContent();
  const logo = head.addStack(); logo.backgroundColor = C.accent; logo.cornerRadius = 3; logo.setPadding(1, 4, 0, 4);
  dtxt(logo, 'PSA10', z.logo, C.bg);
  head.addSpacer(4);
  dtxt(head, 'TRACKER', z.logo, C.text);
  head.addSpacer();
  if (m.corr.level != null) {
    const sp = sparkImage(ci, z.spark[0], z.spark[1]);
    if (sp) { const i = head.addImage(sp); i.imageSize = new Size(z.spark[0], z.spark[1]); head.addSpacer(5); }
    txt(head, 'MY TIER ', z.small, C.muted, true);
    dtxt(head, m.corr.level.toFixed(1), z.logo, C.text); head.addSpacer(3); dtxt(head, pct(m.corr.pct), z.logo - 2, pctColor(m.corr.pct));
  }
}

async function cardImage(url) {
  if (!url) return null;
  const file = fm.joinPath(cacheDir, 'img_' + url.replace(/[^a-z0-9]/gi, '').slice(-60));
  if (fm.fileExists(file)) return fm.readImage(file);
  try { const img = await new Request(url).loadImage(); fm.writeImage(file, img); return img; } catch (e) { return null; }
}
function footer(w, m, extra) {
  w.addSpacer();
  const f = w.addStack(); f.centerAlignContent();
  txt(f, (extra ? extra + ' · ' : '') + 'checked ' + m.when.slice(5, 16).replace('-', '/').replace('T', ' '), 9, C.muted);
}

// ---------------------------------------------------------------- small: rotating signal card
async function small(w, m) {
  const pin = (args.widgetParameter || '').trim();
  let pool = m.limitHits.length ? m.limitHits : m.buys, kind = m.limitHits.length ? 'limit' : 'buy';
  if (pin) { const x = m.cards.find((x) => x.id === pin); if (x) { pool = [x]; kind = x.limitHit ? 'limit' : 'pin'; } }
  const slot = Math.floor(Date.now() / (ROTATE_MINUTES * 6e4));
  w.refreshAfterDate = new Date((slot + 1) * ROTATE_MINUTES * 6e4);

  const closest = !pool.length;
  if (closest) {
    if (!m.closest.length) { txt(w, 'No tracked cards with a PSA10 market yet.', 10, C.muted, false, 3); footer(w, m); return; }
    pool = [m.closest[0]];
  }
  const x = pool[slot % pool.length];
  w.url = BASE + '#/card/' + x.id;
  const top = w.addStack(); top.centerAlignContent();
  if (closest) txt(top, 'NO SIGNALS · CLOSEST', 9, C.muted, true); else tagPill(top, x);
  top.addSpacer();
  if (pool.length > 1) txt(top, `${(slot % pool.length) + 1}/${pool.length}`, 10, C.muted);
  w.addSpacer(6);
  const row = w.addStack(); row.topAlignContent();
  const i = row.addImage(slabImage(await cardImage(x.c.image_url), 34, 49)); i.imageSize = new Size(34, 49); row.addSpacer(6);
  const col = row.addStack(); col.layoutVertically();
  txt(col, x.name.short, 13, C.text, true, 2);
  txt(col, x.name.code, 9, C.muted, false, 1);
  w.addSpacer(4);
  dtxt(w, yen(x.ask), 26, x.limitHit ? C.accent : C.text);
  const zb = zoneBarImage(x, 130);
  if (zb) { const zi = w.addImage(zb); zi.imageSize = new Size(130, 10); }
  const sub = w.addStack(); sub.centerAlignContent();
  if (closest) { const g = m.gap(x); txt(sub, isFinite(g) ? `+${(g * 100).toFixed(0)}% to ${x.lim != null ? 'limit' : 'Buy'}` : '', 10, C.ice, true); }
  else if (x.lim != null) txt(sub, 'limit ' + yen(x.lim), 10, C.soft);
  else if (x.tiers) txt(sub, 'buy ≤ ' + yen(x.tiers.buy_upper), 10, C.soft);
  sub.addSpacer(6);
  txt(sub, '7d ' + pct(x.chg7), 10, pctColor(x.chg7));
  footer(w, m);
}

// ---------------------------------------------------------------- medium: signals + index
async function medium(w, m, ci) {
  const z = MZ;
  w.setPadding(z.pad, z.pad + 2, z.pad - 2, z.pad + 2);
  w.url = BASE + '#/overview';
  header(w, m, ci, z);
  w.addSpacer(5);
  const sig = m.limitHits.concat(m.buys);
  // signals first; free slots are filled with the cards closest to a buy
  const list = sig.slice(0, 3).concat(m.closest.slice(0, Math.max(0, 3 - sig.length)));
  const sub = w.addStack(); sub.centerAlignContent();
  txt(sub, m.limitHits.length ? 'AT YOUR LIMIT' : sig.length ? 'BUY SIGNALS' : 'NO SIGNALS · CLOSEST', z.small, m.limitHits.length ? C.accent : C.muted, true);
  if (sig.length > 3) { sub.addSpacer(4); txt(sub, `+${sig.length - 3} more`, z.small, C.muted); }
  sub.addSpacer();
  if (m.corr.on) { txt(sub, 'CORRECTION', z.small, C.amber, true); sub.addSpacer(4); }
  txt(sub, m.when.slice(5, 16).replace('-', '/').replace('T', ' '), z.small, C.muted);
  w.addSpacer();
  const row = w.addStack(); row.topAlignContent();
  for (let k = 0; k < list.length; k++) {
    const x = list[k], isSig = sig.includes(x);
    if (k) row.addSpacer(z.gap);
    const tile = row.addStack(); tile.layoutVertically(); tile.size = new Size(z.tileW, 0);
    tile.url = BASE + '#/card/' + x.id;
    // top block has a fixed height so the bars of all three tiles line up
    const top = tile.addStack(); top.topAlignContent(); top.size = new Size(z.tileW, z.slabH);
    const slab = top.addImage(slabImage(await cardImage(x.c.image_url), z.slabW, z.slabH)); slab.imageSize = new Size(z.slabW, z.slabH);
    top.addSpacer(4);
    const col = top.addStack(); col.layoutVertically();
    dtxt(col, yen(x.ask), z.price, x.limitHit ? C.accent : C.text);
    txt(col, x.name.short, z.name, C.soft, true, 1);
    col.addSpacer();
    if (isSig) tagPill(col, x, true, z.pill);
    else { const g = m.gap(x); txt(col, isFinite(g) ? `+${(g * 100).toFixed(0)}% ${x.lim != null ? 'to limit' : 'to Buy'}` : '', z.small, C.ice, true, 1); }
    tile.addSpacer(3);
    const zb = zoneBarImage(x, z.tileW, z.bar);
    if (zb) { const i = tile.addImage(zb); i.imageSize = new Size(z.tileW, z.bar); }
    tile.addSpacer(1);
    const ch = tile.addStack(); ch.size = new Size(z.tileW, 0); ch.centerAlignContent();
    txt(ch, '7d ' + pct(x.chg7), z.small, pctColor(x.chg7), false, 1);
    ch.addSpacer();
    if (x.heat) txt(ch, x.heat[0], z.small, x.heat[1], true, 1);
  }
  if (!list.length) txt(w, 'No tracked cards with a PSA10 market yet.', 10, C.muted);
  w.addSpacer();
}

// ---------------------------------------------------------------- large: overview list
async function large(w, m, ci) {
  w.url = BASE + '#/overview';
  header(w, m, ci);
  w.addSpacer(8);
  const list = m.limitHits.concat(m.buys, m.cards.filter((x) => !m.limitHits.includes(x) && !m.buys.includes(x)));
  for (const x of list.slice(0, 10)) {
    const r = w.addStack(); r.centerAlignContent();
    const nm = r.addStack(); nm.size = new Size(125, 0);
    txt(nm, x.name.short, 11, C.text, true, 1);
    r.addSpacer();
    dtxt(r, yen(x.ask), 15, x.limitHit ? C.accent : C.text);
    r.addSpacer(6);
    const ch = r.addStack(); ch.size = new Size(44, 0);
    txt(ch, pct(x.chg7), 10, pctColor(x.chg7));
    r.addSpacer(4);
    if (x.limitHit) pill(r, 'LIMIT', C.accent, true); else if (TAG[x.tag]) pill(r, ...TAG[x.tag]);
    if (x.heat) { r.addSpacer(4); pill(r, x.heat[0], x.heat[1], false); }
    w.addSpacer(5);
  }
  footer(w, m, m.corr.on ? 'correction rule on · 7d change' : '7d change');
}

// ---------------------------------------------------------------- main
const w = new ListWidget();
const bgGrad = new LinearGradient(); bgGrad.colors = [new Color('#141417'), C.bg]; bgGrad.locations = [0, 1];
w.backgroundGradient = bgGrad;
w.setPadding(12, 12, 10, 12);
try {
  const data = await loadData();
  const m = buildModel(data);
  const fam = config.widgetFamily || 'medium';
  if (fam === 'small') await small(w, m);
  else if (fam === 'large' || fam === 'extraLarge') await large(w, m, data.ci);
  else await medium(w, m, data.ci);
} catch (e) {
  txt(w, 'PSA10 Tracker', 12, C.accent, true);
  txt(w, "Couldn't load the tracker data: " + e.message, 10, C.soft, false, 4);
}
if (config.runsInWidget) Script.setWidget(w);
else await (config.widgetFamily === 'small' ? w.presentSmall() : w.presentMedium());
Script.complete();
