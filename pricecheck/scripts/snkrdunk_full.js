// Full-check SNKRDUNK reads, in ONE javascript call. Run it on any https://snkrdunk.com page with PLAN
// filled in from `python3 pricecheck/plan.py` (its "PLAN = [...]" line). For each card it opens, in a
// hidden same-origin iframe, one after another (the same pages a person would open, in the user's own
// browser; no fetch/XHR):
//   - the product page: favorites, grade tiles, 売買履歴 one-copy sales for PSA10 and A
//     (same rules as snkrdunk_base.js + grade_tiles.js), plus the card photo URL when asked;
//   - mode "full", or mode "tile" when the PSA10 tile shows a price (a market is forming):
//     the listings pages ?conditionIds=22 (PSA10) and =18 (A) with 安い順 + 販売中のみ, top 20
//     (same rules as snkrdunk_listings.js).
// It returns at once and keeps one compact line per card in window.__pj; poll with
//   await (async()=>{for(let i=0;i<75&&!window.__pj.done;i++)await new Promise(r=>setTimeout(r,500));const q=window.__pj;return q.done?q.lines.join('\n'):`running ${q.i}/${q.n}`})()
// Line: <id> f.. p.. a.. P.. A.. [L..] [R..] [I..]   (decoded by scripts/full_update.py)
//   f/p/a/P/A: exactly as in snkrdunk_quick.js (favorites, PSA10 tile, A tile, PSA10 sales, A sales)
//   L / R (PSA10 / A listings): L=<top-20 prices ascending>  with optional flags before '=':
//        s = order/sold filter not confirmed on the page (sorted in script), g<n> = n tiles show another
//        grade, f = filter label didn't match the grade;  or  L!<uri-encoded error>
//   I<uri-encoded photo url>  when the plan asked for the photo (third PLAN field = 1)
//   <id> E<reason>  when the product page failed (listings are still attempted for mode "full")
(() => {
  const PLAN = [/* ["455596","full",0], ["896992","tile",0], … */];
  if (window.__pj && !window.__pj.done) return `already running ${window.__pj.i}/${window.__pj.n}`;
  const q = window.__pj = { n: PLAN.length, i: 0, lines: [], done: false, started: new Date().toISOString() };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const U = { '秒': 's', '分': 'm', '時間': 'h', '日': 'd', '週間': 'w', 'ヶ月': 'M', 'か月': 'K' };
  const enc = (w) => {
    w = String(w || '').trim(); let m;
    if (w === 'たった今') return 'n';
    if ((m = w.match(/^(\d+)(秒|分|時間|日|週間|ヶ月|か月)前$/))) return m[1] + U[m[2]];
    if ((m = w.match(/^20(\d\d)\/(\d\d)\/(\d\d)$/))) return m[1] + m[2] + m[3];
    return '~' + encodeURIComponent(w);
  };
  async function openFrame(path, ready) {
    const f = document.createElement('iframe');
    f.style.cssText = 'position:fixed;left:-3000px;top:0;width:1200px;height:2400px;border:0';
    f.src = path;
    document.body.appendChild(f);
    for (let i = 0; i < 50; i++) {
      await sleep(300);
      const d = f.contentDocument;
      try { if (d && d.body && ready(d)) return { f, d, w: f.contentWindow }; } catch (e) { /* not ready */ }
    }
    return { f, d: null };
  }
  async function readBase(id, wantImage) {
    const { f, d } = await openFrame('/apparels/' + id, (d) => d.location.pathname.replace(/\/$/, '').endsWith('/' + id) && d.body.innerText.includes('売買履歴'));
    try {
      if (!d) return { toks: ['E' + encodeURIComponent('base page did not finish loading (売買履歴 not found)')], psaTile: false };
      await sleep(300);
      const t = d.body.innerText;
      const fm = t.match(/¥\s*\n\s*[\d,]+~\s*\n\s*([\d,]+)\s*\n/);
      const toks = ['f' + (fm ? Number(fm[1].replace(/,/g, '')) : '?')];
      let psaTile = false;
      const chips = [...d.querySelectorAll('button[class*="__chip"]')];
      for (const [g, k] of [['PSA10', 'p'], ['A', 'a']]) {
        if (!chips.length) { toks.push(k + '!'); continue; }
        const b = chips.find((x) => x.innerText.split('\n')[0].trim() === g);
        if (!b) { toks.push(k + 'x'); continue; }
        const m = b.innerText.match(/[¥￥]\s*([\d,]+)/);
        if (m && g === 'PSA10') psaTile = true;
        toks.push(k + (m ? Number(m[1].replace(/,/g, '')) : b.innerText.includes('出品待ち') ? '-' : '?'));
      }
      const readRows = () => [...d.querySelectorAll('tr')].map((r) => ({
        when: r.querySelector('[class*="__soldAt"]')?.innerText.trim(),
        grade: r.querySelector('[class*="__variant"]')?.innerText.trim(),
        qty: r.querySelector('[class*="__condition"]')?.innerText.trim(),
        price: Number((r.querySelector('[class*="__price"]')?.innerText || '').replace(/[^\d]/g, '')),
      })).filter((r) => r.when && r.price);
      for (const [g, k] of [['PSA10', 'P'], ['A', 'A']]) {
        const btn = [...d.querySelectorAll('li > button')].find((b) => b.innerText.trim() === g && b.closest('ul')?.innerText.includes('すべて'));
        if (!btn) { toks.push(k + '!n'); continue; }
        let rows = [];
        for (let attempt = 0; attempt < 3; attempt++) {
          if (!/__active/.test(btn.className)) btn.click();
          for (let w = 0; w < 12; w++) {
            await sleep(400);
            rows = readRows();
            if (w >= 3 && !rows.length && /__active/.test(btn.className) && d.body.innerText.includes('この期間内に取引がありません')) break;
            if (w >= 1 && rows.length && rows.every((r) => r.grade === g)) break;
          }
          if (/__active/.test(btn.className)) break;
        }
        if (!/__active/.test(btn.className)) { toks.push(k + '!a'); continue; }
        const noSales = d.body.innerText.includes('この期間内に取引がありません');
        const match = rows.filter((r) => r.grade === g && r.qty === '1枚');
        const list = match.slice(0, 20).reverse().map((r) => r.price + '@' + enc(r.when)).join(',');
        const discarded = rows.length - match.length;
        toks.push(noSales && !match.length ? k + '0' : discarded ? `${k}~${discarded}=${list}` : `${k}=${list}`);
      }
      if (wantImage) {
        const img = [...d.images].map((i) => i.currentSrc || i.src).find((s) => s.includes('upload_bg_removed'));
        if (img) toks.push('I' + encodeURIComponent(img));
      }
      return { toks, psaTile };
    } catch (e) {
      return { toks: ['E' + encodeURIComponent(String(e && e.message || e))], psaTile: false };
    } finally { f.remove(); }
  }
  async function readListings(id, cond, k) {
    const expect = cond === 22 ? 'PSA10' : 'A';
    const { f, d, w } = await openFrame(`/apparels/${id}/used?conditionIds=${cond}`, (d) => d.location.pathname.includes('/used') && d.querySelector('select') && d.querySelector('input[type=checkbox]'));
    try {
      if (!d) return k + '!' + encodeURIComponent('listings page controls (sort select / 販売中のみ) not found');
      const sel = d.querySelector('select'), cb = d.querySelector('input[type=checkbox]');
      const lm = d.body.innerText.match(/中古一覧\s*\n+\s*([^\n]+)/);
      const label = lm ? lm[1].trim() : null;
      if (sel.value !== 'price') {                                   // sort FIRST, then the checkbox
        Object.getOwnPropertyDescriptor(w.HTMLSelectElement.prototype, 'value').set.call(sel, 'price');
        sel.dispatchEvent(new w.Event('input', { bubbles: true }));
        sel.dispatchEvent(new w.Event('change', { bubbles: true }));
        await sleep(1200);
      }
      if (!cb.checked) { cb.click(); await sleep(1200); }
      const read = () => [...d.querySelectorAll('.item-list')].map((li) => ({
        sold: li.classList.contains('sold'),
        price: Number((li.querySelector('.item-price')?.childNodes[0]?.textContent || '').replace(/[^\d]/g, '')),
        grade: li.querySelector('.item-price span:last-child')?.innerText.trim(),
      })).filter((x) => x.price);
      let items = [], ok = false;
      for (let t = 0; t < 15; t++) {                                  // wait for the re-render to settle
        items = read();
        const asc = items.every((x, i) => i === 0 || x.price >= items[i - 1].price);
        if (!items.some((x) => x.sold) && asc) { ok = true; if (t >= 1 && (items.length || t >= 5)) break; }
        else if (t === 7 && !cb.checked) cb.click();
        await sleep(400);
      }
      if (!items.length) return k + '!' + encodeURIComponent('no for-sale listings found for this grade');
      let flags = '';
      if (!ok) { flags += 's'; items = items.filter((x) => !x.sold).sort((a, b) => a.price - b.price); }
      const wrong = items.filter((x) => label && x.grade && !label.startsWith(x.grade)).length;
      if (wrong) flags += 'g' + wrong;
      if (!label || !label.startsWith(expect)) flags += 'f';
      return `${k}${flags}=${items.slice(0, 20).map((x) => x.price).join(',')}`;
    } catch (e) {
      return k + '!' + encodeURIComponent(String(e && e.message || e));
    } finally { f.remove(); }
  }
  (async () => {
    for (const [id0, mode, img] of PLAN) {
      const id = String(id0);
      const b = await readBase(id, !!img);
      const toks = [id, ...b.toks];
      if (mode === 'full' || (mode === 'tile' && b.psaTile)) {
        await sleep(300); toks.push(await readListings(id, 22, 'L'));
        await sleep(300); toks.push(await readListings(id, 18, 'R'));
      }
      q.lines.push(toks.join(' ')); q.i++;
      await sleep(400);
    }
    q.done = true; q.finished = new Date().toISOString();
  })();
  return `started ${PLAN.length} cards`;
})()
