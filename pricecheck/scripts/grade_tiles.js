// Grade tiles on https://snkrdunk.com/apparels/<id>: SNKRDUNK's own "¥X~" lowest ask per grade. 出品待ち = no listings.
await (async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
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
