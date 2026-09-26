// Monthly rebuild of data/odds_model.json. Run in the browser on any https://pokeca-chart.com/ page
// (it reads rendered pages only, via same-origin iframes and the charts' own React props; no API calls).
// Call it repeatedly with the step shown, pasting this file then one of:
//   await __oddsBuilder('list')    -> picks the pool (modern Pokémon ex/V/VMAX/VSTAR/GX, 2021 to 6+ months ago, PSA10 ¥10k–300k)
//   await __oddsBuilder('grab')    -> fetches up to 35 cards' PSA10 history per call; repeat until it says done
//   await __oddsBuilder('build')   -> returns the model JSON; save it with scripts/save_odds_model.py
window.__oddsBuilder = async (step) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const LS = localStorage;
  if (step === 'list') {
    if (!location.pathname.startsWith('/gr/all-card')) { location.href = '/gr/all-card/?sort=newest'; return 'navigating to the card list; run list again once it has loaded'; }
    await sleep(1500);
    const seen = {};
    for (let y = 0; y <= document.body.scrollHeight + 1200; y += 600) {
      window.scrollTo(0, y); window.dispatchEvent(new Event('scroll')); document.dispatchEvent(new Event('scroll')); await sleep(200);
      for (const a of document.querySelectorAll('main a[href*="/gr/"]')) {
        const m = a.innerText.match(/\n?([^\n]+\[([^\]]+)\])\n\n([^\n]*)\n\nPSA10価格\n\n([^\n]+)\n\n(\d{4}-\d{2})/);
        if (m) seen[m[2]] = { name: m[1], set: m[3], price: Number(m[4].replace(/[^\d]/g, '')) || null, date: m[5], href: a.getAttribute('href') };
      }
    }
    window.scrollTo(0, 0);
    const cutoff = new Date(Date.now() - 183 * 864e5).toISOString().slice(0, 7);
    const pool = Object.entries(seen).filter(([code, c]) => c.price && c.price >= 10000 && c.price <= 300000 && +c.date.slice(0, 4) >= 2021 && c.date <= cutoff
      && /(ex|VMAX|VSTAR|V|GX) \[/.test(c.name) && !/-P\]|-P |EN |WCS|-G /i.test(c.name)
      && !/プロモ|ANNIVERSARY|記念|スタートデッキ/.test(c.set) && !/の[^\s\[]+ex/.test(c.name.replace('ロケット団の', '')));
    const extra = (window.__oddsExtra || ['098/SV-P', 'SGG 020/019']).filter(e => seen[e]);
    const list = [...new Set([...pool.map(p => p[0]), ...extra])].map(c => seen[c].href);
    LS.setItem('om_list', JSON.stringify(list)); LS.setItem('om_started', String(Date.now()));
    return `pool: ${list.length} cards`;
  }
  if (step === 'grab') {
    const list = JSON.parse(LS.getItem('om_list') || '[]'), started = +LS.getItem('om_started');
    const todo = list.filter(h => +(LS.getItem('om_t:' + h) || 0) < started && +(LS.getItem('om_f:' + h + ':' + started) || 0) < 2).slice(0, 35);
    if (!todo.length) { const got = list.filter(h => +(LS.getItem('om_t:' + h) || 0) >= started).length; return `done: ${got}/${list.length} cards read`; }
    let ok = 0;
    for (const h of todo) {
      const fr = document.createElement('iframe'); fr.style.cssText = 'position:fixed;left:-3000px;top:0;width:1200px;height:900px'; fr.src = h; document.body.appendChild(fr);
      let rows = null, code = null;
      for (let i = 0; i < 50 && !rows; i++) {
        await sleep(300); const d = fr.contentDocument; if (!d) continue; code = (d.title.match(/\[([^\]]+)\]/) || [])[1];
        for (const c of d.querySelectorAll('canvas')) { let el = c; for (let k = 0; k < 12 && el && !rows; k++, el = el.parentElement) { const fk = Object.keys(el).find(x => x.startsWith('__reactFiber')); if (!fk) continue; let f = el[fk]; for (let u = 0; u < 30 && f; u++, f = f.return) { const p = f.memoizedProps; if (p && Array.isArray(p.data) && p.data.length && 'item_status' in p.data[0]) { rows = p.data; break; } } } if (rows) break; }
      }
      if (rows && code) { LS.setItem('ci_h:' + code, JSON.stringify(rows.filter(r => r.item_status === 2 && r.price > 0).map(r => [r.date, r.price, r.volume || 0]))); LS.setItem('om_t:' + h, String(Date.now())); ok++; }
      else { const fk = 'om_f:' + h + ':' + started; LS.setItem(fk, String(+(LS.getItem(fk) || 0) + 1)); }
      fr.remove();
    }
    return `grabbed ${ok}/${todo.length}; run grab again`;
  }
  if (step === 'build') {
    const day = s => Date.parse(s) / 864e5;
    const series = {};
    for (const k of Object.keys(LS).filter(k => k.startsWith('ci_h:'))) { const ps = JSON.parse(LS.getItem(k)).map(([d, p]) => [day(d), Math.log(p)]); if (ps.length >= 8) series[k.slice(5)] = ps; }
    const end = Math.max(...Object.values(series).map(ps => ps[ps.length - 1][0]));
    const near = (ps, t, tol) => { let best = null, bd = 1e9; for (const q of ps) { const d = Math.abs(q[0] - t); if (d < bd) { bd = d; best = q; } } return bd <= tol ? best : null; };
    let obs = [];
    for (const [code, ps] of Object.entries(series)) {
      const t0 = ps[0][0];
      for (const p of ps) {
        if (p[0] - t0 < 60) continue;
        const prev = near(ps, p[0] - 30, 6); if (!prev || prev[0] >= p[0]) continue;
        const f30 = near(ps, p[0] + 30, 6), f90 = near(ps, p[0] + 90, 10);
        obs.push({ code, t: p[0], r30: f30 && f30[0] > p[0] ? f30[1] - p[1] : null, r90: f90 && f90[0] > p[0] ? f90[1] - p[1] : null });
      }
    }
    const seen = new Set();
    obs = obs.filter(o => { const k = o.code + '|' + Math.floor(o.t / 14); if (seen.has(k)) return false; seen.add(k); return true; }).sort((a, b) => a.t - b.t);
    const sd = a => { const m = a.reduce((x, y) => x + y, 0) / a.length; return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / a.length); };
    const sigmaAt = (H, h, code, t) => {
      const past = obs.filter(q => q[H] != null && q.t + h <= t); if (past.length < 300) return null;
      const recent = past.filter(q => q.t + h > t - 180);
      const own = past.filter(q => q.code === code).slice(-8);
      const sRec = recent.length > 50 ? sd(recent.map(q => q[H])) : sd(past.map(q => q[H]));
      const sOwn = own.length >= 4 ? sd(own.map(q => q[H])) : sRec, w = own.length / (own.length + 6);
      return { s: Math.sqrt(w * sOwn ** 2 + (1 - w) * sRec ** 2), sRec, nOwn: own.length };
    };
    const from = end - 1000;  // ~2.7 years of forecasts for the z-curves
    const z90 = [], z30 = [];
    for (const o of obs) {
      if (o.t < from) continue;
      if (o.r90 != null && o.t + 90 <= end) { const S = sigmaAt('r90', 90, o.code, o.t); const ps = series[o.code]; const p0 = ps.find(q => q[0] === o.t); const path = ps.filter(q => q[0] > o.t && q[0] <= o.t + 90); if (S && p0 && path.length >= 2) z90.push((Math.min(...path.map(q => q[1])) - p0[1]) / S.s); }
      if (o.r30 != null && o.t + 30 <= end) { const S = sigmaAt('r30', 30, o.code, o.t); if (S) z30.push(o.r30 / S.s); }
    }
    const q = (a, n) => { const s = [...a].sort((x, y) => x - y); return Array.from({ length: n + 1 }, (_, i) => +s[Math.min(s.length - 1, Math.round(i / n * (s.length - 1)))].toFixed(3)); };
    const cards = {};
    for (const code of Object.keys(series)) { const a = sigmaAt('r30', 30, code, end + 1), b = sigmaAt('r90', 90, code, end + 1); if (a && b) cards[code.toLowerCase()] = [+a.s.toFixed(4), +b.s.toFixed(4), a.nOwn]; }
    const p30 = sigmaAt('r30', 30, '__pool__', end + 1).sRec, p90 = sigmaAt('r90', 90, '__pool__', end + 1).sRec;
    return JSON.stringify({ built: new Date(end * 864e5).toISOString().slice(0, 10), source: `pokeca-chart PSA10 price history, ${Object.keys(series).length} modern cards`,
      pool_sigma: [+p30.toFixed(4), +p90.toFixed(4)], z_end30: q(z30, 100), z_touch90: q(z90, 100), n: [z30.length, z90.length], cards });
  }
  return 'step must be list, grab or build';
};
'ready';
