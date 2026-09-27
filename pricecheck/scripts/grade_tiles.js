// Grade tiles on https://snkrdunk.com/apparels/<id>: SNKRDUNK's own "¥X~" lowest ask per grade. 出品待ち = no listings.
await (async () => {
  const sleep = window.__wsleep || (window.__wsleep = (() => { // timers from a Web Worker: a hidden tab throttles page timers to 1/s, then 1/min
    const P = {}; let n = 0, w = null;
    try { w = new Worker(URL.createObjectURL(new Blob(['onmessage=e=>setTimeout(()=>postMessage(e.data[0]),e.data[1])'], { type: 'text/javascript' }))); w.onmessage = (e) => { const r = P[e.data]; delete P[e.data]; if (r) r(); }; } catch (e) { w = null; }
    return (ms) => new Promise((r) => { if (w) { P[++n] = r; w.postMessage([n, ms]); } setTimeout(r, ms); }); // page timer too, in case the worker is blocked
  })());
  for (let i = 0; i < 20 && !document.querySelector('button[class*="__chip"]'); i++) await sleep(300);
  const chips = [...document.querySelectorAll('button[class*="__chip"]')];
  if (!chips.length) return { error: 'grade tiles not found' };
  const out = {};
  for (const g of ['PSA10', 'A']) {
    const b = chips.find(x => x.innerText.split('\n')[0].trim() === g);
    if (!b) { out[g] = { error: 'tile not found' }; continue; }
    const m = b.innerText.match(/[¥￥]\s*([\d,]+)/);
    out[g] = m ? { lowest_ask: Number(m[1].replace(/,/g, '')) }
               : { lowest_ask: null, note: b.innerText.includes('出品待ち') ? 'no listings (出品待ち)' : 'no price on tile' };
  }
  return out;
})()
