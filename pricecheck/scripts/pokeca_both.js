// Both pokeca-chart indices in ONE javascript call. Run it on https://pokeca-chart.com/gr/chart-index/
// (the PSA10 index page). It reads that page like pokeca_index.js, then opens /chart-index/ (raw/美品)
// in a hidden same-origin iframe and reads it the same way. Returns two lines for full_update.py:
//   IDX psa10 {json}      IDX raw {json}      (pokeca_index.js result without last14_daily)
await (async () => {
  const read = async (doc) => {
  const sleep = window.__wsleep || (window.__wsleep = (() => { // timers from a Web Worker: a hidden tab throttles page timers to 1/s, then 1/min
    const P = {}; let n = 0, w = null;
    try { w = new Worker(URL.createObjectURL(new Blob(['onmessage=e=>setTimeout(()=>postMessage(e.data[0]),e.data[1])'], { type: 'text/javascript' }))); w.onmessage = (e) => { const r = P[e.data]; delete P[e.data]; if (r) r(); }; } catch (e) { w = null; }
    return (ms) => new Promise((r) => { if (w) { P[++n] = r; w.postMessage([n, ms]); } setTimeout(r, ms); }); // page timer too, in case the worker is blocked
  })());
  const findData = () => {
    for (const c of doc.querySelectorAll('canvas')) {
      let el = c;
      for (let d = 0; d < 12 && el; d++, el = el.parentElement) {
        const fk = Object.keys(el).find(k => k.startsWith('__reactFiber'));
        if (!fk) continue;
        let f = el[fk];
        for (let u = 0; u < 30 && f; u++, f = f.return) {
          const p = f.memoizedProps;
          if (p && Array.isArray(p.allData) && p.allData.length && 'volume' in p.allData[0]) return p.allData;
        }
      }
    }
    return null;
  };
  let data = null;
  for (let i = 0; i < 25 && !(data = findData()); i++) await sleep(400);
  const t = doc.body.innerText;
  const after = (label, n = 2) => {
    const i = t.indexOf('\n' + label + '\n');
    if (i < 0) return null;
    return t.slice(i + label.length + 2).split('\n').filter(s => s.trim()).slice(0, n);
  };
  const num = s => s == null ? null : Number(String(s).replace(/[^\d.\-+]/g, ''));
  const rangeM = t.match(/指数チャート（(PSA10|美品)）\s*\n+\s*(\d{4}\/\d{2}\/\d{2}\s*〜\s*\d{4}\/\d{2}\/\d{2})/);
  const latest = after('最新価格', 1), day = after('前日比'), mon = after('月間変動'), yr = after('年間変動');
  const out = {
    page: rangeM ? rangeM[1] : null,
    data_range: rangeM ? rangeM[2].replace(/\s+/g, ' ') : null,
    latest_index_value_jpy: latest ? num(latest[0]) : null,
    day_change_jpy: day ? num(day[0]) : null, day_change_pct: day ? num(day[1]) : null,
    month_change_jpy: mon ? num(mon[0]) : null, month_change_pct: mon ? num(mon[1]) : null,
    year_change_jpy: yr ? num(yr[0]) : null, year_change_pct: yr ? num(yr[1]) : null,
  };
  if (!data) { out.volume_error = 'chart data (allData) not found in React props'; return out; }
  const vols = data.map(d => d.volume ?? 0);
  const avg = a => a.length ? Math.round(a.reduce((x, y) => x + y, 0) / a.length * 10) / 10 : null;
  const last14 = data.slice(-14), prior30 = vols.slice(-44, -14);
  const a14 = avg(last14.map(d => d.volume)), a7 = avg(vols.slice(-7)), aPrior = avg(prior30);
  const peak = last14.reduce((m, d) => (d.volume > m.volume ? d : m), last14[0]);
  let trend = 'flat';
  if (aPrior && peak.volume > aPrior * 2) trend = 'spiking';
  // rising/falling when the last 7 days are 15%+ off the prior 30 days, or the last 14 days 10%+
  // (2026-10-08: the 14-day-only ±15% rule called +29% over 7 days "flat")
  else if (aPrior && (a7 >= aPrior * 1.15 || a14 >= aPrior * 1.10)) trend = 'rising';
  else if (aPrior && (a7 <= aPrior * 0.87 || a14 <= aPrior * 0.91)) trend = 'falling';
  out.volume_stats = {
    last_date: data[data.length - 1].date,
    avg_last7: a7, avg_last14: a14, avg_prior30: aPrior,
    peak_last14: { date: peak.date, volume: peak.volume, value: peak.value },
      };
  out.volume_trend_suggested = trend; // rule: spiking if a day >2x prior-30 avg, else rising/falling if the 7d avg is ±15% or the 14d avg ±10% vs prior 30d
  return out;
  };
  const psa10 = await read(document);
  const f = document.createElement('iframe');
  f.style.cssText = 'position:fixed;left:-3000px;top:0;width:1200px;height:2400px;border:0';
  f.src = '/chart-index/';
  document.body.appendChild(f);
  for (let i = 0; i < 40 && !(f.contentDocument && f.contentDocument.location.pathname === '/chart-index/' && f.contentDocument.querySelector('canvas')); i++) await window.__wsleep(300);
  const raw = await read(f.contentDocument);
  f.remove();
  return 'IDX psa10 ' + JSON.stringify(psa10) + '\nIDX raw ' + JSON.stringify(raw);
})()
