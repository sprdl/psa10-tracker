// altema PSA10 population for several cards, in ONE javascript call. Run it on any
// https://altema.jp/pokemoncard/ page with ALTEMA filled in from `python3 pricecheck/plan.py`
// ("ALTEMA = [...]" line). Opens each card page in a hidden same-origin iframe, one after another,
// and reads it like altema_population.js. Returns at once; poll window.__pj like snkrdunk_full.js:
//   await (async()=>{for(let i=0;i<75&&!window.__pj.done;i++)await (window.__wsleep||(m=>new Promise(r=>setTimeout(r,m))))(500);const q=window.__pj;return q.done?q.lines.join('\n'):`running ${q.i}/${q.n}${document.hidden?' (tab hidden)':''}`})()
// Line: ALT <snkrdunk id> n<population|-> r<gem rate %|-> c<uri 型番> [!<uri error>]
(() => {
  const ALTEMA = [/* ["224087","https://altema.jp/pokemoncard/card/26372","due"], … */];
  if (window.__pj && !window.__pj.done) return `already running ${window.__pj.i}/${window.__pj.n}`;
  const q = window.__pj = { n: ALTEMA.length, i: 0, lines: [], done: false };
  const sleep = window.__wsleep || (window.__wsleep = (() => { // timers from a Web Worker: a hidden tab throttles page timers to 1/s, then 1/min
    const P = {}; let n = 0, w = null;
    try { w = new Worker(URL.createObjectURL(new Blob(['onmessage=e=>setTimeout(()=>postMessage(e.data[0]),e.data[1])'], { type: 'text/javascript' }))); w.onmessage = (e) => { const r = P[e.data]; delete P[e.data]; if (r) r(); }; } catch (e) { w = null; }
    return (ms) => new Promise((r) => { if (w) { P[++n] = r; w.postMessage([n, ms]); } setTimeout(r, ms); }); // page timer too, in case the worker is blocked
  })());
  (async () => {
    for (const [id, url] of ALTEMA) {
      const path = new URL(url).pathname;
      const f = document.createElement('iframe');
      f.style.cssText = 'position:fixed;left:-3000px;top:0;width:1200px;height:2400px;border:0';
      f.src = path;
      document.body.appendChild(f);
      let t = '';
      try {
        for (let i = 0; i < 40; i++) {
          await sleep(300);
          const d = f.contentDocument;
          t = d && d.body ? d.body.innerText : '';
          if (d && d.location.pathname === path && /型番|PSA10総枚数/.test(t)) break;
        }
        await sleep(300);
        t = f.contentDocument.body.innerText;
      } catch (e) { t = ''; }
      f.remove();
      const g = (re) => (t.match(re) || [])[1] || null;
      const pop = g(/PSA10総枚数\s*([\d,]+)\s*枚/), rate = g(/PSA10取得率\s*([\d.]+)\s*%/), num = g(/型番\s*([^\s\n]+)/);
      let line = `ALT ${id} n${pop ? Number(pop.replace(/,/g, '')) : '-'} r${rate ? Number(rate) : '-'} c${encodeURIComponent(num || '')}`;
      if (!/型番|PSA10|買取/.test(t)) line += ' !' + encodeURIComponent('altema page did not load or structure changed');
      else if (!pop) line += ' !' + encodeURIComponent('no PSA10 population section on page yet');
      q.lines.push(line); q.i++;
      await sleep(400);
    }
    q.done = true;
  })();
  return `started ${ALTEMA.length} altema pages`;
})()
