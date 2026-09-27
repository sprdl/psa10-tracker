// Quick price check, in ONE javascript call. Run it on any https://snkrdunk.com page with IDS
// filled in. It opens each card's own product page in a hidden same-origin iframe, one after
// another (the same pages a person would open, in the user's own browser; no fetch/XHR), reads
// favorites, the grade tiles and 売買履歴 exactly like snkrdunk_base.js + the grade-tile
// snippet did, and keeps one compact line per card in window.__pq. It returns at once; poll with
//   await (async()=>{for(let i=0;i<75&&!window.__pq.done;i++)await (window.__wsleep||(m=>new Promise(r=>setTimeout(r,m))))(500);const q=window.__pq;return q.done?q.lines.join('\n'):`running ${q.i}/${q.n}${document.hidden?' (tab hidden)':''}`})()
// Line format (decoded by scripts/quick_update.py):  <id> f<fav|?> p<tile> a<tile> P<sales> A<sales>
//   tile:  <yen> | - (出品待ち) | ? (no price on tile) | x (tile not found) | ! (no grade tiles)
//   sales: =<list> | ~<n>=<list> (n rows discarded) | 0 (no sales in period) | !n (pill not found) | !a (pill didn't activate)
//   list:  price@when,… oldest first; when = 3h / 49m / 2d / 1w / 1M (ヶ月) / 1K (か月) / 12s / n (たった今) / 260421 (2026/04/21) / ~<uri-encoded raw>
//   a card whose page fails: <id> E<uri-encoded reason>
(() => {
  const IDS = [/* '455596', '138599', … */];
  if (window.__pq && !window.__pq.done) return `already running ${window.__pq.i}/${window.__pq.n}`;
  const q = window.__pq = { n: IDS.length, i: 0, lines: [], done: false, started: new Date().toISOString() };
  const sleep = window.__wsleep || (window.__wsleep = (() => { // timers from a Web Worker: a hidden tab throttles page timers to 1/s, then 1/min
    const P = {}; let n = 0, w = null;
    try { w = new Worker(URL.createObjectURL(new Blob(['onmessage=e=>setTimeout(()=>postMessage(e.data[0]),e.data[1])'], { type: 'text/javascript' }))); w.onmessage = (e) => { const r = P[e.data]; delete P[e.data]; if (r) r(); }; } catch (e) { w = null; }
    return (ms) => new Promise((r) => { if (w) { P[++n] = r; w.postMessage([n, ms]); } setTimeout(r, ms); }); // page timer too, in case the worker is blocked
  })());
  const U = { '秒': 's', '分': 'm', '時間': 'h', '日': 'd', '週間': 'w', 'ヶ月': 'M', 'か月': 'K' };
  const enc = (w) => {
    w = String(w || '').trim(); let m;
    if (w === 'たった今') return 'n';
    if ((m = w.match(/^(\d+)(秒|分|時間|日|週間|ヶ月|か月)前$/))) return m[1] + U[m[2]];
    if ((m = w.match(/^20(\d\d)\/(\d\d)\/(\d\d)$/))) return m[1] + m[2] + m[3];
    return '~' + encodeURIComponent(w);
  };
  async function readCard(id) {
    const f = document.createElement('iframe');
    f.style.cssText = 'position:fixed;left:-3000px;top:0;width:1200px;height:2400px;border:0';
    f.src = '/apparels/' + id;
    document.body.appendChild(f);
    try {
      let d = null;
      for (let i = 0; i < 50; i++) {
        await sleep(300);
        d = f.contentDocument;
        if (d && d.body && d.location.pathname.replace(/\/$/, '').endsWith('/' + id) && d.body.innerText.includes('売買履歴')) break;
        d = null;
      }
      if (!d) return `${id} E${encodeURIComponent('page did not finish loading (売買履歴 not found)')}`;
      await sleep(300);
      const t = d.body.innerText;
      const fm = t.match(/¥\s*\n\s*[\d,]+~\s*\n\s*([\d,]+)\s*\n/);
      const out = [id, 'f' + (fm ? Number(fm[1].replace(/,/g, '')) : '?')];
      // grade tiles: SNKRDUNK's own "¥X~" lowest ask per grade
      const chips = [...d.querySelectorAll('button[class*="__chip"]')];
      for (const [g, k] of [['PSA10', 'p'], ['A', 'a']]) {
        if (!chips.length) { out.push(k + '!'); continue; }
        const b = chips.find((x) => x.innerText.split('\n')[0].trim() === g);
        if (!b) { out.push(k + 'x'); continue; }
        const m = b.innerText.match(/[¥￥]\s*([\d,]+)/);
        out.push(k + (m ? Number(m[1].replace(/,/g, '')) : b.innerText.includes('出品待ち') ? '-' : '?'));
      }
      // 売買履歴: one-copy sales per grade (same rules as snkrdunk_base.js)
      const readRows = () => [...d.querySelectorAll('tr')].map((r) => ({
        when: r.querySelector('[class*="__soldAt"]')?.innerText.trim(),
        grade: r.querySelector('[class*="__variant"]')?.innerText.trim(),
        qty: r.querySelector('[class*="__condition"]')?.innerText.trim(),
        price: Number((r.querySelector('[class*="__price"]')?.innerText || '').replace(/[^\d]/g, '')),
      })).filter((r) => r.when && r.price);
      for (const [g, k] of [['PSA10', 'P'], ['A', 'A']]) {
        const btn = [...d.querySelectorAll('li > button')].find((b) => b.innerText.trim() === g && b.closest('ul')?.innerText.includes('すべて'));
        if (!btn) { out.push(k + '!n'); continue; }
        let rows = [];
        for (let attempt = 0; attempt < 3; attempt++) {
          if (!/__active/.test(btn.className)) btn.click();
          for (let w = 0; w < 12; w++) {
            await sleep(400);
            rows = readRows();
            if (w >= 3 && !rows.length && /__active/.test(btn.className) && d.body.innerText.includes('この期間内に取引がありません')) break;
            // wait until the table really shows this grade only (a mostly-PSA10 "すべて" table used to pass early)
            if (w >= 1 && rows.length && rows.every((r) => r.grade === g)) break;
          }
          if (/__active/.test(btn.className)) break;
        }
        if (!/__active/.test(btn.className)) { out.push(k + '!a'); continue; }
        const noSales = d.body.innerText.includes('この期間内に取引がありません');
        const match = rows.filter((r) => r.grade === g && r.qty === '1枚');
        const list = match.slice(0, 20).reverse().map((r) => r.price + '@' + enc(r.when)).join(',');
        const discarded = rows.length - match.length;
        out.push(noSales && !match.length ? k + '0' : discarded ? `${k}~${discarded}=${list}` : `${k}=${list}`);
      }
      return out.join(' ');
    } catch (e) {
      return `${id} E${encodeURIComponent(String(e && e.message || e))}`;
    } finally {
      f.remove();
    }
  }
  (async () => {
    for (const id of IDS) { q.lines.push(await readCard(String(id))); q.i++; await sleep(400); }
    q.done = true; q.finished = new Date().toISOString();
  })();
  return `started ${IDS.length} cards`;
})()
