// pokeca-chart.com index extractor. Run on https://pokeca-chart.com/gr/chart-index/ (PSA10)
// or https://pokeca-chart.com/chart-index/ (raw/美品). Returns compact JSON.
// Volume comes from the chart's own React props (allData: [{date,value,volume,...}]),
// so no toggling, zooming, screenshots, or ad-modal handling is needed.
await (async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const findData = () => {
    for (const c of document.querySelectorAll('canvas')) {
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
  const t = document.body.innerText;
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
  else if (aPrior && a14 > aPrior * 1.15) trend = 'rising';
  else if (aPrior && a14 < aPrior * 0.85) trend = 'falling';
  out.volume_stats = {
    last_date: data[data.length - 1].date,
    avg_last7: a7, avg_last14: a14, avg_prior30: aPrior,
    peak_last14: { date: peak.date, volume: peak.volume, value: peak.value },
    last14_daily: last14.map(d => [d.date.slice(5), d.volume, d.value]),
  };
  out.volume_trend_suggested = trend; // rule: spiking if a day >2x prior-30 avg, else rising/falling if 14d avg is ±15% vs prior 30d
  return out;
})()
