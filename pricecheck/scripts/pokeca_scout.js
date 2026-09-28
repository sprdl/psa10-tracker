// Scout: candidate cards you don't track yet, from pokeca-chart, in ONE javascript call. Run it on
// https://pokeca-chart.com/gr/all-card/?sort=newest (step 4, after the My-tier extractor) with SCOUT
// filled in from `python3 pricecheck/plan.py` ("SCOUT = {...}" line). It reads the card list on the
// page, keeps modern secret rares (card number above the set size, released 2021 or later, PSA10
// ¥15k–150k) that aren't tracked or dismissed, then opens up to SCOUT.n of their card pages in hidden
// same-origin iframes (the ones never read or read longest ago) and reads each price chart's own data
// (React props) plus the PSA population and the SNKRDUNK link on the page. No fetch/XHR.
// Returns at once; poll window.__pj like snkrdunk_full.js. About 2.5 s per card page.
// Lines (decoded by scripts/scout.py into data/scout.json):
//   SCP <slug>:<PSA10 list price>,...        every candidate on the list today
//   SC {json}                                 one per card page read (metrics below)
//   SC! <slug> <uri-encoded error>
(() => {
  const SCOUT = { skip: [], read: {}, n: 20 };
  if (window.__pj && !window.__pj.done) return `already running ${window.__pj.i}/${window.__pj.n}`;
  const q = window.__pj = { n: 0, i: 0, lines: [], done: false };
  const sleep = window.__wsleep || (window.__wsleep = (() => { // timers from a Web Worker: a hidden tab throttles page timers to 1/s, then 1/min
    const P = {}; let n = 0, w = null;
    try { w = new Worker(URL.createObjectURL(new Blob(['onmessage=e=>setTimeout(()=>postMessage(e.data[0]),e.data[1])'], { type: 'text/javascript' }))); w.onmessage = (e) => { const r = P[e.data]; delete P[e.data]; if (r) r(); }; } catch (e) { w = null; }
    return (ms) => new Promise((r) => { if (w) { P[++n] = r; w.postMessage([n, ms]); } setTimeout(r, ms); }); // page timer too, in case the worker is blocked
  })());
  const med = (a) => { const s = a.slice().sort((x, y) => x - y), n = s.length; return n ? (n % 2 ? s[n >> 1] : (s[n / 2 - 1] + s[n / 2]) / 2) : null; };
  (async () => {
    // 1) the list: the page renders progressively, so scroll through it (scroll events keep it rendering in a hidden tab)
    for (let i = 0; i < 30 && !/PSA10価格/.test(document.querySelector('main')?.innerText || ''); i++) await sleep(300);
    const seen = {};
    let prevH = 0;
    for (let i = 0; i < 20; i++) { const h = document.body.scrollHeight; if (h > 5000 && h === prevH) break; prevH = h; await sleep(300); }
    for (let y = 0; y <= document.body.scrollHeight + 1200; y += 700) {
      window.scrollTo(0, y); window.dispatchEvent(new Event('scroll')); document.dispatchEvent(new Event('scroll')); await sleep(150);
      for (const a of document.querySelectorAll('main a[href*="/gr/"]')) {
        const m = a.innerText.match(/\n?([^\n]+\[([^\]]+)\])\n\n([^\n]*)\n\nPSA10価格\n\n([^\n]+)\n\n(\d{4}-\d{2})/);
        const slug = (a.getAttribute('href').match(/\/gr\/([^/]+)\//) || [])[1];
        if (m && slug) seen[slug] = { name: m[1], code: m[2], set: m[3], price: Number(m[4].replace(/[^\d]/g, '')) || null, rel: m[5] };
      }
    }
    window.scrollTo(0, 0);
    const skip = new Set(SCOUT.skip);
    const cand = Object.entries(seen).filter(([slug, c]) => {
      const mm = c.code.match(/^(\S+)\s+(\d+)\/(\d+)$/);
      return mm && !/-p$/i.test(mm[1]) && +mm[2] > +mm[3] && c.rel >= '2021-01' && c.price >= 15000 && c.price <= 150000 && !skip.has(slug);
    });
    q.lines.push('SCP ' + cand.map(([slug, c]) => `${slug}:${c.price}`).join(','));
    // 2) card pages: never read first, then the longest ago
    const todo = cand.map(([slug, c]) => ({ slug, c, r: SCOUT.read[slug] || '' })).sort((a, b) => (a.r < b.r ? -1 : a.r > b.r ? 1 : 0)).slice(0, SCOUT.n);
    q.n = todo.length;
    for (const { slug, c } of todo) {
      const f = document.createElement('iframe');
      f.style.cssText = 'position:fixed;left:-3000px;top:0;width:1200px;height:900px;border:0';
      f.src = '/gr/' + slug + '/';
      document.body.appendChild(f);
      let rows = null, d = null;
      for (let i = 0; i < 40 && !rows; i++) {
        await sleep(300);
        d = f.contentDocument; if (!d || !d.body) continue;
        for (const cv of d.querySelectorAll('canvas')) {
          let el = cv;
          for (let k = 0; k < 12 && el && !rows; k++, el = el.parentElement) {
            const fk = Object.keys(el).find((x) => x.startsWith('__reactFiber')); if (!fk) continue;
            let fb = el[fk];
            for (let u = 0; u < 30 && fb; u++, fb = fb.return) { const p = fb.memoizedProps; if (p && Array.isArray(p.data) && p.data.length && 'item_status' in p.data[0]) { rows = p.data; break; } }
          }
          if (rows) break;
        }
      }
      if (rows) await sleep(500); // population block renders just after the chart
      let out;
      try {
        if (!rows) throw new Error('price chart data not found');
        const t = d.body.innerText;
        const pop = t.match(/PSA 10\n([\d,]+)枚\n([\d.]+)%/);
        const snk = [...d.querySelectorAll('a[href*="snkrdunk.com/apparels/"]')].map((a) => (a.href.match(/apparels\/(\d+)/) || [])[1]).find(Boolean);
        const P = rows.filter((r) => r.item_status === 2 && r.price > 0).sort((a, b) => (a.date < b.date ? -1 : 1));
        const R = {}; rows.filter((r) => r.item_status === 0 && r.price > 0).forEach((r) => { R[r.date] = r.price; });
        if (!P.length) throw new Error('no PSA10 prices');
        const last = P[P.length - 1], lt = Date.parse(last.date) / 864e5;
        const pre = med(P.filter((r) => r.date >= '2025-07-01' && r.date <= '2025-12-31').map((r) => r.price));
        const peakRow = P.filter((r) => r.date >= '2026-01-01').reduce((m, r) => (!m || r.price > m.price ? r : m), null);
        const ago30 = P.filter((r) => lt - Date.parse(r.date) / 864e5 >= 25).pop();
        const both = P.filter((r) => R[r.date]).map((r) => ({ t: Date.parse(r.date) / 864e5, k: r.price / R[r.date] }));
        const bl = both[both.length - 1];
        const norm = bl ? med(both.filter((b) => bl.t - b.t >= 30 && bl.t - b.t <= 210).map((b) => b.k)) : null;
        const vol = P.filter((r) => lt - Date.parse(r.date) / 864e5 < 30).reduce((s, r) => s + (r.volume || 0), 0);
        const months = {}; P.forEach((r) => { if (lt - Date.parse(r.date) / 864e5 <= 548) months[r.date.slice(2, 4) + r.date.slice(5, 7)] = r.price; });
        out = 'SC ' + JSON.stringify({ s: slug, nm: (d.querySelector('h1')?.innerText || c.name).trim(), set: c.set, rel: c.rel, sid: snk || null,
          pop: pop ? Number(pop[1].replace(/,/g, '')) : null, gem: pop ? Number(pop[2]) : null, now: last.price, nd: last.date,
          pre, peak: peakRow ? peakRow.price : null, pk: peakRow ? peakRow.date.slice(0, 7) : null, p30: ago30 ? ago30.price : null,
          prem: bl ? +bl.k.toFixed(3) : null, norm: norm ? +norm.toFixed(3) : null, vol,
          ser: Object.entries(months).map(([m, p]) => m + ':' + Math.round(p / 100) / 10).join(',') });
      } catch (e) { out = `SC! ${slug} ` + encodeURIComponent(String(e.message || e)); }
      f.remove();
      q.lines.push(out); q.i++;
      await sleep(250);
    }
    q.done = true;
  })();
  return 'started (list + card pages)';
})()
