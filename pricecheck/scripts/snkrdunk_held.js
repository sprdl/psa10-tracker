// Prices of what you bought but don't track (FULL check only, step 2b), in ONE javascript call. Run it on
// any https://snkrdunk.com page with HELD filled in from `python3 pricecheck/plan.py` (its "HELD = [...]" line).
// Each product page opens in a hidden same-origin iframe, one after another, with a pause (the same page a
// person would open, in the user's own browser; no fetch/XHR). Returns at once; poll with
//   await (async()=>{for(let i=0;i<75&&!window.__hq.done;i++)await (window.__wsleep||(m=>new Promise(r=>setTimeout(r,m))))(500);const q=window.__hq;return q.done?q.lines.join('\n'):`running ${q.i}/${q.n}`})()
// Lines (decoded by scripts/holdings_prices.py):
//   H <id> card   <yen|-> <sales>   raw A-rank lowest ask: the "A" grade tile (same rule as snkrdunk_full.js); - = 出品待ち
//                  sales = the newest one-copy A-rank sales from the last 30 days, newest first, "p1,p2,…" (up to 5), or -
//                  scripts/raw_price.py turns ask + sales into the raw A-rank price (median of the sales, never below the ask)
//   H <id> sealed <yen|->   sealed product: the lowest ask shown at the top of the product page (before 売買履歴)
//   HE <id> <uri reason>    the page failed or no price could be found
(() => {
  const HELD = [/* ["881421","sealed"], ["896992","card"], … */];
  if (window.__hq && !window.__hq.done) return `already running ${window.__hq.i}/${window.__hq.n}`;
  const q = window.__hq = { n: HELD.length, i: 0, lines: [], done: false };
  const sleep = window.__wsleep || (window.__wsleep = (() => {
    const P = {}; let n = 0, w = null;
    try { w = new Worker(URL.createObjectURL(new Blob(['onmessage=e=>setTimeout(()=>postMessage(e.data[0]),e.data[1])'], { type: 'text/javascript' }))); w.onmessage = (e) => { const r = P[e.data]; delete P[e.data]; if (r) r(); }; } catch (e) { w = null; }
    return (ms) => new Promise((r) => { if (w) { P[++n] = r; w.postMessage([n, ms]); } setTimeout(r, ms); });
  })());
  const yen = (s) => Number(String(s).replace(/,/g, ''));
  // 売買履歴 → A pill → one-copy rows from the last 30 days, newest first (same table rules as snkrdunk_quick.js).
  const ageDays = (w) => {
    w = String(w || '').trim(); let m;
    if (w === 'たった今') return 0;
    if ((m = w.match(/^(\d+)(秒|分|時間|日|週間|ヶ月|か月)前$/))) return Number(m[1]) * { '秒': 1 / 86400, '分': 1 / 1440, '時間': 1 / 24, '日': 1, '週間': 7, 'ヶ月': 30, 'か月': 30 }[m[2]];
    if ((m = w.match(/^(\d{4})\/(\d{2})\/(\d{2})$/))) return (Date.now() - Date.parse(`${m[1]}-${m[2]}-${m[3]}T12:00:00+09:00`)) / 864e5;
    return null;
  };
  async function aSales(d) {
    const btn = [...d.querySelectorAll('li > button')].find((b) => b.innerText.trim() === 'A' && b.closest('ul')?.innerText.includes('すべて'));
    if (!btn) return '-';
    const readRows = () => [...d.querySelectorAll('tr')].map((r) => ({
      when: r.querySelector('[class*="__soldAt"]')?.innerText.trim(),
      grade: r.querySelector('[class*="__variant"]')?.innerText.trim(),
      qty: r.querySelector('[class*="__condition"]')?.innerText.trim(),
      price: Number((r.querySelector('[class*="__price"]')?.innerText || '').replace(/[^\d]/g, '')),
    })).filter((r) => r.when && r.price);
    let rows = [];
    for (let attempt = 0; attempt < 3 && !/__active/.test(btn.className); attempt++) btn.click(), await sleep(400);
    for (let w = 0; w < 12; w++) {
      await sleep(400);
      rows = readRows();
      if (w >= 1 && rows.length && rows.every((r) => r.grade === 'A')) break;
      if (w >= 3 && d.body.innerText.includes('この期間内に取引がありません')) break;
    }
    const ok = rows.filter((r) => r.grade === 'A' && r.qty === '1枚' && (ageDays(r.when) ?? 99) <= 30).slice(0, 5);
    return ok.length ? ok.map((r) => r.price).join(',') : '-';
  }
  async function read(id, kind) {
    const f = document.createElement('iframe');
    f.style.cssText = 'position:fixed;left:-3000px;top:0;width:1200px;height:2400px;border:0';
    f.src = '/apparels/' + id;
    document.body.appendChild(f);
    try {
      let d = null;
      for (let i = 0; i < 50; i++) {
        await sleep(300);
        const x = f.contentDocument;
        if (x && x.body && x.location.pathname.replace(/\/$/, '').endsWith('/' + id) && x.body.innerText.includes('売買履歴')) { d = x; break; }
      }
      if (!d) return `HE ${id} ${encodeURIComponent('page did not finish loading (売買履歴 not found)')}`;
      await sleep(300);
      if (kind === 'card') {
        const chips = [...d.querySelectorAll('button[class*="__chip"]')];
        if (!chips.length) return `HE ${id} ${encodeURIComponent('grade tiles not found')}`;
        const b = chips.find((x) => x.innerText.split('\n')[0].trim() === 'A');
        if (!b) return `HE ${id} ${encodeURIComponent('A grade tile not found')}`;
        const m = b.innerText.match(/[¥￥]\s*([\d,]+)/);
        if (!m && !b.innerText.includes('出品待ち')) return `HE ${id} ${encodeURIComponent('no price on the A tile')}`;
        return `H ${id} card ${m ? yen(m[1]) : '-'} ${await aSales(d)}`;
      }
      // sealed: the first yen amount in the page's top part (before the sales history); a "~" marks a lowest ask
      const top = d.body.innerText.split('売買履歴')[0];
      const m = top.match(/[¥￥]\s*\n?\s*([\d,]{3,})\s*~/) || top.match(/[¥￥]\s*\n?\s*([\d,]{3,})/);
      if (m) return `H ${id} sealed ${yen(m[1])}`;
      return /出品待ち|在庫なし|売り切れ/.test(top) ? `H ${id} sealed -` : `HE ${id} ${encodeURIComponent('no price found at the top of the product page')}`;
    } catch (e) {
      return `HE ${id} ${encodeURIComponent(String((e && e.message) || e))}`;
    } finally { f.remove(); }
  }
  (async () => {
    for (const [id, kind] of HELD) { q.lines.push(await read(String(id), kind)); q.i++; await sleep(1000); }
    q.done = true;
  })();
  return `started ${HELD.length} items`;
})();
