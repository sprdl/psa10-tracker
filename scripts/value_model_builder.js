// Builds data/value_model.json (upside ranges + tier checks). Run in the browser on any
// https://pokeca-chart.com/ page AFTER the odds-model rebuild's 'list' and 'grab' steps
// (scripts/odds_model_builder.js), which leave each card's PSA10 history in this browser's
// localStorage (ci_h:<code>) and the card list in ci_cards. Reads only that; no network calls.
//   paste this file, set window.__valueCodes to the tracked cards' codes (printed by
//   scripts/save_value_model.py --codes), then:  await __valueBuilder()   -> JSON for scripts/save_value_model.py
//
// Method (see "about" in the output):
//  - monthly price per card = median of that month's PSA10 points
//  - "mature market" = equal-weighted average monthly log change of cards at least 9 months old
//  - age curve = average monthly change vs the mature market, by card age
//  - 12/24-month outcome = mature-market move (every historical start month) + the card's own
//    part (card vs market, pooled over cards 9+ months old), combined pair by pair
window.__valueBuilder = async () => {
  const LS = localStorage, g = (k) => JSON.parse(LS.getItem(k));
  const cards = g('ci_cards') || {};
  const mk = (d) => +d.slice(0, 4) * 12 + (+d.slice(5, 7) - 1);
  const lab = (t) => `${Math.floor(t / 12)}-${String(t % 12 + 1).padStart(2, '0')}`;
  const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
  const sd = (a) => { const m = mean(a); return Math.sqrt(mean(a.map((x) => (x - m) ** 2))); };
  const qs = (a, n) => { const s = [...a].sort((x, y) => x - y); return Array.from({ length: n + 1 }, (_, i) => +s[Math.round((i / n) * (s.length - 1))].toFixed(4)); };
  const ser = {};
  for (const k of Object.keys(LS).filter((k) => k.startsWith('ci_h:'))) {
    const code = k.slice(5), by = {};
    for (const [d, p] of g(k)) if (p > 0) (by[mk(d)] = by[mk(d)] || []).push(Math.log(p));
    const m = {};
    for (const [t, a] of Object.entries(by)) { a.sort((x, y) => x - y); m[t] = a[Math.floor(a.length / 2)]; }
    const rel = cards[code] && cards[code].date ? mk(cards[code].date + '-01') : Math.min(...Object.keys(m).map(Number));
    ser[code] = { m, rel };
  }
  const codes = Object.keys(ser);
  if (codes.length < 50) return 'not enough card histories in this browser: run the odds-model list and grab steps first';
  const T = [...new Set(codes.flatMap((c) => Object.keys(ser[c].m).map(Number)))].sort((a, b) => a - b);
  // mature market
  const Mm = {}; let lv = 0;
  T.forEach((t, i) => {
    if (i === 0) { Mm[t] = 0; return; }
    const ch = codes.filter((c) => t - 1 - ser[c].rel >= 9).map((c) => (ser[c].m[t] != null && ser[c].m[t - 1] != null ? ser[c].m[t] - ser[c].m[t - 1] : null)).filter((x) => x != null);
    lv += ch.length >= 5 ? mean(ch) : 0; Mm[t] = lv;
  });
  // age curve vs mature market
  const AGE = [[0, 3], [3, 6], [6, 9], [9, 12], [12, 24], [24, 999]];
  const ageAcc = AGE.map(() => []);
  for (const { m, rel } of Object.values(ser)) for (const t of Object.keys(m).map(Number)) {
    if (m[t + 1] == null || Mm[t + 1] == null) continue;
    const i = AGE.findIndex(([lo, hi]) => t - rel >= lo && t - rel < hi);
    if (i >= 0) ageAcc[i].push((m[t + 1] - m[t]) - (Mm[t + 1] - Mm[t]));
  }
  const ageCurve = AGE.map(([lo, hi], i) => ({ from: lo, to: hi, monthly: +mean(ageAcc[i]).toFixed(4), n: ageAcc[i].length }));
  // market moves over 12/24 months, every start month
  const mkt = (h) => T.filter((t) => Mm[t + h] != null).map((t) => Mm[t + h] - Mm[t]);
  // the card's own part over 12/24 months (cards 9+ months old at the start), scaled by the card's own monthly swing
  const idio = (h) => {
    const out = [];
    for (const { m, rel } of Object.values(ser)) for (const t of Object.keys(m).map(Number)) {
      if (t - rel < 9 || m[t + h] == null || Mm[t + h] == null) continue;
      out.push((m[t + h] - m[t]) - (Mm[t + h] - Mm[t]));
    }
    return out;
  };
  const combine = (a, b) => { const out = []; for (const x of a) for (const y of b) out.push(x + y); return out; };
  const res = {};
  for (const h of [12, 24]) {
    const a = mkt(h), b = idio(h), bm = mean(b);
    const bc = b.map((x) => x - bm);    // centre the card part: the market part carries the level
    const sub = bc.filter((_, i) => i % Math.max(1, Math.floor(bc.length / 400)) === 0);
    res[h] = { market: qs(a, 20), market_n: a.length, card_part: qs(bc, 20), card_part_n: b.length, card_part_mean: +bm.toFixed(4), combined: qs(combine(a, sub), 50) };
  }
  // per-card monthly swing (for scaling the card part): sd of monthly changes vs market, last 18 months
  const swing = {}, allSw = [];
  for (const [c, { m }] of Object.entries(ser)) {
    const ch = []; const last = Math.max(...Object.keys(m).map(Number));
    for (let t = last - 18; t < last; t++) if (m[t] != null && m[t + 1] != null && Mm[t + 1] != null) ch.push((m[t + 1] - m[t]) - (Mm[t + 1] - Mm[t]));
    if (ch.length >= 6) { swing[c.toLowerCase()] = +sd(ch).toFixed(4); allSw.push(sd(ch)); }
  }
  const want = (window.__valueCodes || []).map((x) => x.toLowerCase());
  const keep = (o) => (want.length ? Object.fromEntries(Object.entries(o).filter(([k]) => want.includes(k))) : o);
  const mktPath = Object.fromEntries(T.map((t) => [lab(t), +Math.exp(Mm[t]).toFixed(3)]));
  const rel = Object.fromEntries(Object.entries(cards).filter(([, v]) => v && v.date).map(([k, v]) => [k.toLowerCase(), v.date]));
  return JSON.stringify({
    built: lab(T[T.length - 1]), source: `pokeca-chart PSA10 price history, ${codes.length} modern cards, ${lab(T[0])} to ${lab(T[T.length - 1])}`,
    horizons: res, age_curve: ageCurve, swing_pool: +(allSw.sort((x, y) => x - y)[Math.floor(allSw.length / 2)]).toFixed(4), swing: keep(swing),
    market_path: mktPath, release: keep(rel),
  });
};
'ready';
