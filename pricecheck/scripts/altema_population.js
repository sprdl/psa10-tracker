// altema.jp/pokemoncard card-page extractor. Run on https://altema.jp/pokemoncard/card/<id>.
// Waits for the article body, then returns PSA10 population / gem rate plus the page's 型番 and 封入パック
// so the card identity can be sanity-checked against the tracked card.
await (async () => {
  const sleep = window.__wsleep || (window.__wsleep = (() => { // timers from a Web Worker: a hidden tab throttles page timers to 1/s, then 1/min
    const P = {}; let n = 0, w = null;
    try { w = new Worker(URL.createObjectURL(new Blob(['onmessage=e=>setTimeout(()=>postMessage(e.data[0]),e.data[1])'], { type: 'text/javascript' }))); w.onmessage = (e) => { const r = P[e.data]; delete P[e.data]; if (r) r(); }; } catch (e) { w = null; }
    return (ms) => new Promise((r) => { if (w) { P[++n] = r; w.postMessage([n, ms]); } setTimeout(r, ms); }); // page timer too, in case the worker is blocked
  })());
  for (let i = 0; i < 25 && !/型番|PSA10総枚数/.test(document.body.innerText); i++) await sleep(400);
  const t = document.body.innerText;
  const g = re => (t.match(re) || [])[1] || null;
  const pop = g(/PSA10総枚数\s*([\d,]+)\s*枚/), rate = g(/PSA10取得率\s*([\d.]+)\s*%/);
  const out = {
    title: document.title.replace(/ - ポケカチ$/, ''),
    card_number: g(/型番\s*([^\s\n]+)/), pack: g(/封入パック\s*([^\n]+)/),
    psa10_population: pop ? Number(pop.replace(/,/g, '')) : null,
    psa10_gem_rate_pct: rate ? Number(rate) : null,
    psa10_price_date_note: g(/※(PSA10価格は[^\n]+)/),
  };
  if (!/型番|PSA10|買取/.test(t)) out.error = 'altema page did not load or structure changed';
  else if (out.psa10_population == null) out.error = 'no PSA10 population section on page yet';
  return out;
})()
