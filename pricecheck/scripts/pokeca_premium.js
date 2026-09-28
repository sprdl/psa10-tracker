// Slab premium (PSA10 ÷ raw 美品) per tracked card from pokeca-chart's own card pages, in ONE
// javascript call. Run it on any https://pokeca-chart.com/ page (step 4 runs it right after
// pokeca_both.js) with PREM filled in from `python3 pricecheck/plan.py` ("PREM = [...]" line).
// Each card page opens in a hidden same-origin iframe, one after another; the script reads the
// price chart's own data (React props: item_status 0 = 美品 raw, 2 = PSA10). No fetch/XHR.
// Returns at once; poll window.__pj like snkrdunk_full.js. About 2 s per card.
// Line: PREM <snkrdunk id> d<yymmdd latest> r<raw> p<PSA10> m<6-month norm ratio|-> n<points> s<yymmdd:ratio,...>
//       PREM <snkrdunk id> !<uri-encoded error>
// The norm is the median premium of the points 30–210 days before the latest one (needs 4+);
// the series covers the last 18 months. Decoded by scripts/full_update.py into data/premium.json.
(() => {
  const PREM = [/* ["455596","sv8a-217-187"], … */];
  if (window.__pj && !window.__pj.done) return `already running ${window.__pj.i}/${window.__pj.n}`;
  const q = window.__pj = { n: PREM.length, i: 0, lines: [], done: false };
  const sleep = window.__wsleep || (window.__wsleep = (() => { // timers from a Web Worker: a hidden tab throttles page timers to 1/s, then 1/min
    const P = {}; let n = 0, w = null;
    try { w = new Worker(URL.createObjectURL(new Blob(['onmessage=e=>setTimeout(()=>postMessage(e.data[0]),e.data[1])'], { type: 'text/javascript' }))); w.onmessage = (e) => { const r = P[e.data]; delete P[e.data]; if (r) r(); }; } catch (e) { w = null; }
    return (ms) => new Promise((r) => { if (w) { P[++n] = r; w.postMessage([n, ms]); } setTimeout(r, ms); }); // page timer too, in case the worker is blocked
  })());
  const ymd = (s) => s.slice(2, 4) + s.slice(5, 7) + s.slice(8, 10);
  (async () => {
    for (const [sid, slug] of PREM) {
      const f = document.createElement('iframe');
      f.style.cssText = 'position:fixed;left:-3000px;top:0;width:1200px;height:900px;border:0';
      f.src = '/gr/' + slug + '/';
      document.body.appendChild(f);
      let rows = null, notFound = false;
      for (let i = 0; i < 40 && !rows && !notFound; i++) {
        await sleep(300);
        const d = f.contentDocument; if (!d || !d.body) continue;
        if (i > 12 && !d.title.includes('[')) notFound = true;   // generic title: no such card page
        for (const c of d.querySelectorAll('canvas')) {
          let el = c;
          for (let k = 0; k < 12 && el && !rows; k++, el = el.parentElement) {
            const fk = Object.keys(el).find((x) => x.startsWith('__reactFiber')); if (!fk) continue;
            let fb = el[fk];
            for (let u = 0; u < 30 && fb; u++, fb = fb.return) { const p = fb.memoizedProps; if (p && Array.isArray(p.data) && p.data.length && 'item_status' in p.data[0]) { rows = p.data; break; } }
          }
          if (rows) break;
        }
      }
      f.remove();
      if (!rows) { q.lines.push(`PREM ${sid} !` + encodeURIComponent(notFound ? `no pokeca-chart page at /gr/${slug}/` : 'price chart data not found')); q.i++; continue; }
      const by = {};
      for (const r of rows) { if (!(r.price > 0)) continue; const e = by[r.date] = by[r.date] || [null, null]; if (r.item_status === 0) e[0] = r.price; if (r.item_status === 2) e[1] = r.price; }
      const pts = Object.entries(by).filter(([, v]) => v[0] && v[1]).sort(([a], [b]) => (a < b ? -1 : 1)).map(([d, v]) => ({ d, t: Date.parse(d) / 864e5, raw: v[0], psa: v[1], k: v[1] / v[0] }));
      if (!pts.length) { q.lines.push(`PREM ${sid} !` + encodeURIComponent('no dates with both a raw and a PSA10 price')); q.i++; continue; }
      const last = pts[pts.length - 1];
      const hist = pts.filter((p) => last.t - p.t >= 30 && last.t - p.t <= 210).map((p) => p.k).sort((a, b) => a - b);
      const norm = hist.length >= 4 ? (hist.length % 2 ? hist[hist.length >> 1] : (hist[hist.length / 2 - 1] + hist[hist.length / 2]) / 2) : null;
      const series = pts.filter((p) => last.t - p.t <= 548).map((p) => ymd(p.d) + ':' + p.k.toFixed(2)).join(',');
      q.lines.push(`PREM ${sid} d${ymd(last.d)} r${last.raw} p${last.psa} m${norm ? norm.toFixed(3) : '-'} n${pts.length} s${series}`);
      q.i++;
      await sleep(250);
    }
    q.done = true;
  })();
  return `started ${PREM.length} cards`;
})()
