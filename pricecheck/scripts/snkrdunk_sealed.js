// Name and picture of sealed products (boxes, sets, packs) from their SNKRDUNK pages, in ONE javascript
// call. Run it on any https://snkrdunk.com page with SEALED filled in (scripts/sealed_info.py --js prints
// the whole script ready to paste). Each product page opens in a hidden same-origin iframe, one after
// another, with a pause (the same page a person would open, in the user's browser; no fetch/XHR).
// Returns at once; poll with
//   await (async()=>{for(let i=0;i<90&&!window.__sq.done;i++)await window.__wsleep(500);const q=window.__sq;return q.done?q.lines.join('\n'):`running ${q.i}/${q.n}`})()
// Lines (decoded by scripts/sealed_info.py):
//   SP <sealed id> <uri product name> <uri image url|->
//   SE <sealed id> <uri reason>
(() => {
  const SEALED = [/* ["s51", "https://snkrdunk.com/apparels/881421"], … */];
  if (window.__sq && !window.__sq.done) return `already running ${window.__sq.i}/${window.__sq.n}`;
  const q = window.__sq = { n: SEALED.length, i: 0, lines: [], done: false };
  const sleep = window.__wsleep || (window.__wsleep = (() => {
    const P = {}; let n = 0, w = null;
    try { w = new Worker(URL.createObjectURL(new Blob(['onmessage=e=>setTimeout(()=>postMessage(e.data[0]),e.data[1])'], { type: 'text/javascript' }))); w.onmessage = (e) => { const r = P[e.data]; delete P[e.data]; if (r) r(); }; } catch (e) { w = null; }
    return (ms) => new Promise((r) => { if (w) { P[++n] = r; w.postMessage([n, ms]); } setTimeout(r, ms); });
  })());
  (async () => {
    for (const [sid, url] of SEALED) {
      const f = document.createElement('iframe');
      f.style.cssText = 'position:fixed;left:0;top:0;width:1200px;height:900px;border:0;opacity:0;pointer-events:none;z-index:-1';
      f.src = new URL(url).pathname;
      document.body.appendChild(f);
      let name = null, img = null;
      const path = new URL(url).pathname;
      for (let i = 0; i < 40 && !(name && img); i++) {
        await sleep(300);
        const d = f.contentDocument;
        if (!d || !d.body || d.location.pathname.replace(/\/$/, '') !== path.replace(/\/$/, '')) continue;
        const t = (d.title || '').replace(/(通販|｜|\|).*$/, '').trim();
        if (t && !/スニーカーダンク|スニダン/.test(t)) name = t;
        // the product's own picture is the big one at the top (related cards below are small)
        const big = [...d.images].filter((x) => /cdn\.snkrdunk\.com\/upload/.test(x.currentSrc || x.src))
          .map((x) => { const b = x.getBoundingClientRect(); return { s: x.currentSrc || x.src, a: b.width * b.height, top: b.top }; })
          .filter((x) => x.a >= 250 * 250 && x.top < 900).sort((a, b) => b.a - a.a)[0];
        if (big) img = big.s.replace(/size=\w+/, 'size=l');
      }
      f.remove();
      q.lines.push(name ? `SP ${sid} ${encodeURIComponent(name)} ${img ? encodeURIComponent(img) : '-'}` : `SE ${sid} ${encodeURIComponent('page did not load or has no product name')}`);
      q.i++;
      await sleep(1000);
    }
    q.done = true;
  })();
  return `started ${SEALED.length} products`;
})();
