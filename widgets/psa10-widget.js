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
};

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
function pill(stack, label, color, filled) {
  const p = stack.addStack();
  p.setPadding(2, 6, 2, 6); p.cornerRadius = 4; p.borderWidth = 1; p.borderColor = color;
  if (filled) p.backgroundColor = color;
  const t = p.addText(label); t.font = Font.boldSystemFont(10); t.textColor = filled ? C.bg : color;
  return p;
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

  if (!pool.length) {
    const top = w.addStack(); top.centerAlignContent();
    txt(top, 'NO BUY SIGNALS', 11, C.muted, true);
    w.addSpacer(6);
    const x = m.closest[0];
    if (x) {
      txt(w, 'Closest', 10, C.muted);
      txt(w, x.name.short, 14, C.text, true, 2);
      txt(w, yen(x.ask), 20, C.text, true);
      const g = m.gap(x);
      txt(w, isFinite(g) ? `${(g * 100).toFixed(0)}% above ${x.lim != null ? 'your limit' : 'Buy'}` : '', 10, C.soft);
      w.url = BASE + '#/card/' + x.id;
    }
    footer(w, m);
    return;
  }
  const x = pool[slot % pool.length];
  w.url = BASE + '#/card/' + x.id;
  const top = w.addStack(); top.centerAlignContent();
  if (x.limitHit) pill(top, 'LIMIT HIT', C.accent, true);
  else if (TAG[x.tag]) pill(top, ...TAG[x.tag]);
  top.addSpacer();
  if (pool.length > 1) txt(top, `${(slot % pool.length) + 1}/${pool.length}`, 10, C.muted);
  w.addSpacer(6);
  const row = w.addStack(); row.topAlignContent();
  const img = await cardImage(x.c.image_url);
  if (img) { const i = row.addImage(img); i.imageSize = new Size(34, 48); i.cornerRadius = 3; row.addSpacer(6); }
  const col = row.addStack(); col.layoutVertically();
  txt(col, x.name.short, 13, C.text, true, 2);
  txt(col, x.name.code, 9, C.muted, false, 1);
  w.addSpacer(4);
  txt(w, yen(x.ask), 22, x.limitHit ? C.accent : C.text, true);
  const sub = w.addStack(); sub.centerAlignContent();
  if (x.lim != null) txt(sub, 'limit ' + yen(x.lim), 10, C.soft);
  else if (x.tiers) txt(sub, 'buy ≤ ' + yen(x.tiers.buy_upper), 10, C.soft);
  sub.addSpacer(6);
  txt(sub, '7d ' + pct(x.chg7), 10, pctColor(x.chg7));
  footer(w, m);
}

// ---------------------------------------------------------------- medium: signals + index
async function medium(w, m) {
  w.url = BASE + '#/overview';
  const head = w.addStack(); head.centerAlignContent();
  txt(head, 'PSA10 TRACKER', 12, C.accent, true);
  head.addSpacer();
  if (m.corr.level != null) txt(head, `My tier ${m.corr.level.toFixed(1)} · 30d ${pct(m.corr.pct)}`, 10, pctColor(m.corr.pct));
  w.addSpacer(6);
  const sig = m.limitHits.concat(m.buys);
  const rows = sig.length ? sig.slice(0, 3) : m.closest.slice(0, 3);
  if (!sig.length) txt(w, 'No buy signals · closest to a buy:', 10, C.muted);
  for (const x of rows) {
    const r = w.addStack(); r.centerAlignContent();
    const nm = r.addStack(); nm.layoutVertically(); nm.size = new Size(150, 0);
    txt(nm, x.name.short, 12, C.text, true, 1);
    r.addSpacer();
    txt(r, yen(x.ask), 13, x.limitHit ? C.accent : C.text, true);
    r.addSpacer(8);
    if (x.limitHit) pill(r, 'LIMIT', C.accent, true);
    else if (sig.length && TAG[x.tag]) pill(r, ...TAG[x.tag]);
    else { const g = m.gap(x); txt(r, isFinite(g) ? `+${(g * 100).toFixed(0)}%` : '', 11, C.soft); }
    w.addSpacer(4);
  }
  footer(w, m, m.corr.on ? 'correction rule on' : '');
}

// ---------------------------------------------------------------- large: overview list
async function large(w, m) {
  w.url = BASE + '#/overview';
  const head = w.addStack(); head.centerAlignContent();
  txt(head, 'PSA10 TRACKER', 13, C.accent, true);
  head.addSpacer();
  if (m.corr.level != null) txt(head, `My tier ${m.corr.level.toFixed(1)} · 30d ${pct(m.corr.pct)}`, 10, pctColor(m.corr.pct));
  w.addSpacer(8);
  const list = m.limitHits.concat(m.buys, m.cards.filter((x) => !m.limitHits.includes(x) && !m.buys.includes(x)));
  for (const x of list.slice(0, 10)) {
    const r = w.addStack(); r.centerAlignContent();
    const nm = r.addStack(); nm.size = new Size(125, 0);
    txt(nm, x.name.short, 11, C.text, true, 1);
    r.addSpacer();
    txt(r, yen(x.ask), 12, x.limitHit ? C.accent : C.text, true);
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
w.backgroundColor = C.bg;
w.setPadding(12, 12, 10, 12);
try {
  const m = buildModel(await loadData());
  const fam = config.widgetFamily || 'medium';
  if (fam === 'small') await small(w, m);
  else if (fam === 'large' || fam === 'extraLarge') await large(w, m);
  else await medium(w, m);
} catch (e) {
  txt(w, 'PSA10 Tracker', 12, C.accent, true);
  txt(w, "Couldn't load the tracker data: " + e.message, 10, C.soft, false, 4);
}
if (config.runsInWidget) Script.setWidget(w);
else await (config.widgetFamily === 'small' ? w.presentSmall() : w.presentMedium());
Script.complete();
