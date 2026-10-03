// Mercari check for cards near your limit, in ONE javascript call. Run it on any https://jp.mercari.com
// page with CARDS filled in (scripts/mercari.py --due prints the line). For each card it opens Mercari's
// own search page (for sale, cheapest first) in a hidden same-origin iframe, keeps listings whose title
// says PSA10 for this card, then opens up to 3 of the cheapest matches (the same item pages a person
// would open, in the user's own browser; no fetch/XHR) to read: price, auction end time, whether
// あんしん鑑定 can be used and its fee, and the listing's own grade field. One compact line per listing
// in window.__mq. It returns at once; poll with
//   await (async()=>{for(let i=0;i<75&&!window.__mq.done;i++)await (window.__wsleep||(m=>new Promise(r=>setTimeout(r,m))))(500);const q=window.__mq;return q.done?q.lines.join('\n'):`running ${q.i}/${q.n}`})()
// Lines (decoded by scripts/mercari.py):
//   MC <id> <seen> <matched> <cheapest price|->            one per card (search page)
//   MI <id> <item> <price> <A|F> <ends epoch-min|-> <anshin fee|-|n> <grade ok 1|0> <number 1|0|-> <uri title>
//      number: the item page names this card's number (1), only other numbers (0, likely another card), or none (-)
//      A = auction (price = current bid), F = fixed price; anshin: fee in yen, "0" free, "n" not offered
//   ME <id> <uri reason>                                    the card's search failed
(() => {
  const CARDS = [/* {id:'455596', q:'ブラッキーex SAR 217/187 PSA10', num:'217/187', lim:63000}, … */];
  if (window.__mq && !window.__mq.done) return `already running ${window.__mq.i}/${window.__mq.n}`;
  const q = window.__mq = { n: CARDS.length, i: 0, lines: [], done: false };
  const sleep = window.__wsleep || (window.__wsleep = (() => {
    const P = {}; let n = 0, w = null;
    try { w = new Worker(URL.createObjectURL(new Blob(['onmessage=e=>setTimeout(()=>postMessage(e.data[0]),e.data[1])'], { type: 'text/javascript' }))); w.onmessage = (e) => { const r = P[e.data]; delete P[e.data]; if (r) r(); }; } catch (e) { w = null; }
    return (ms) => new Promise((r) => { if (w) { P[++n] = r; w.postMessage([n, ms]); } setTimeout(r, ms); });
  })());
  const norm = (s) => String(s || '').normalize('NFKC');
  const fee = (p) => (p >= 100000 ? 0 : 1700);
  // A title is a match when it says PSA10 (and no other grade/grader), isn't a lot, and doesn't name a different card number.
  const matches = (title, num) => {
    const t = norm(title).toUpperCase().replace(/\s+/g, ' ');
    if (!/PSA ?10(?!\d)/.test(t)) return false;
    if (/PSA ?[1-9](?![0-9])/.test(t.replace(/PSA ?10/g, ''))) return false;
    if (/BGS|ARS|CGC|まとめ|セット|連番|\d ?枚|[2-9] ?点|おまとめ|オリパ|空ケース|ケースのみ/.test(t)) return false;
    // raw cards sold as "PSA10 candidates", and accessories (frames, sleeves, loaders)
    if (/候補|狙い|相当|PSA10級|未鑑定|鑑定前|鑑定用|フレーム|ディスプレイ|スリーブ|ローダー|スタンド/.test(t)) return false;
    const nums = t.match(/\d{2,3}\/\d{2,3}/g) || [];
    if (num && nums.length && !nums.includes(num)) return false;
    return true;
  };
  async function load(path, ready) {
    const f = document.createElement('iframe');
    // on screen but invisible: Mercari renders result cells only where they intersect the visible viewport
    f.style.cssText = 'position:fixed;left:0;top:0;width:1200px;height:900px;border:0;opacity:0;pointer-events:none;z-index:-1';
    f.src = path;
    document.body.appendChild(f);
    for (let i = 0; i < 60; i++) {
      await sleep(300);
      const d = f.contentDocument;
      if (d && d.body && ready(d)) { await sleep(400); return { f, d }; }
    }
    return { f, d: null };
  }
  async function searchCard(c) {
    // price_min skips the accessories and raw "candidates" that sort first; a real slab under half the limit is not plausible
    const path = '/search?' + new URLSearchParams({ keyword: c.q, status: 'on_sale', sort: 'price', order: 'asc', price_min: String(Math.round(c.lim * 0.5)) });
    const empty = (d) => /該当する商品が見つかりません|出品された商品がありません|検索結果はありません/.test(d.body.innerText);
    const { f, d } = await load(path, (d) => d.querySelector('li[data-testid="item-cell"] a[href^="/item/"]') || empty(d));
    if (!d) { f.remove(); return { err: 'search page did not load' }; }
    // The list is virtualised: cells render only while on screen, so scroll the frame like a reader would and collect.
    const seen = new Map();
    const w = f.contentWindow;
    for (let step = 0, idle = 0; step < 12 && idle < 2 && seen.size < 40; step++) {
      const before = seen.size;
      for (const cell of d.querySelectorAll('li[data-testid="item-cell"]')) {
        const a = cell.querySelector('a[href^="/item/"]');
        if (!a) continue;
        const href = a.getAttribute('href');
        if (seen.has(href)) continue;
        const lab = (a.getAttribute('aria-labelledby') || '').split(' ').map((i) => (d.getElementById(i) || {}).innerText || '').join(' ') || cell.innerText;
        const img = cell.querySelector('img[alt]');
        const p = ((lab.match(/[¥￥]\s*([\d,]{3,})/) || cell.innerText.match(/[¥￥]\s*([\d,]{3,})/) || [])[1] || '').replace(/,/g, '');
        seen.set(href, { href, title: (img ? img.alt : cell.innerText.split('\n').pop() || '').replace(/のサムネイル$/, ''), price: p ? Number(p) : null, auction: /現在/.test(lab) });
      }
      idle = seen.size === before ? idle + 1 : 0;
      w.scrollBy(0, 700);
      await sleep(450);
    }
    const items = [...seen.values()].filter((x) => x.title && x.price);
    f.remove();
    return { items, ok: items.filter((x) => matches(x.title, c.num)).sort((a, b) => a.price - b.price) };
  }
  async function readItem(href, num) {
    const { f, d } = await load(href, (d) => /商品の説明|商品の情報/.test(d.body.innerText));
    if (!d) { f.remove(); return null; }
    const t = d.body.innerText;
    f.remove();
    const pm = t.match(/(現在\s*)?¥\s*([\d,]+)\s*\n\s*\(税込\)/);
    const em = t.match(/終了予定時刻\s*:\s*\n?\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})/);
    const ends = em ? Math.round(Date.UTC(+em[1], +em[2] - 1, +em[3], +em[4] - 9, +em[5]) / 60000) : null;  // JST → epoch minutes
    const am = t.match(/あんしん鑑定\s*\n?\s*を\s*¥\s*([\d,]+)\s*で利用できます/);
    const anshin = am ? Number(am[1].replace(/,/g, '')) : /あんしん鑑定を利用できます/.test(t) ? (/鑑定手数料.{0,10}0円|無料/.test(t) ? 0 : -1) : null;
    const grade = /グレード:\s*PSA10\b/.test(norm(t)) ? 1 : 0;
    const sold = /売り切れ/.test(t.slice(0, 600));
    // card number in the title/description: 1 = ours, 0 = only other numbers (another card), - = none given
    const desc = norm(t.split(/この出品者の商品|関連する商品|この商品を見ている人/)[0]);
    const nums = desc.match(/\d{2,3}\/\d{2,3}/g) || [];
    const numok = !num || !nums.length ? '-' : nums.includes(num) ? '1' : '0';
    return { price: pm ? Number(pm[2].replace(/,/g, '')) : null, auction: !!(pm && pm[1]) || !!em, ends, anshin, grade, sold, numok };
  }
  (async () => {
    for (const c of CARDS) {
      try {
        const s = await searchCard(c);
        if (s.err) { q.lines.push(`ME ${c.id} ${encodeURIComponent(s.err)}`); continue; }
        const cheapest = s.ok.length ? Math.min(...s.ok.map((x) => x.price)) : null;
        q.lines.push(`MC ${c.id} ${s.items.length} ${s.ok.length} ${cheapest == null ? '-' : cheapest}`);
        // open the cheapest matches: everything within 5% of the limit (fee included), and always the cheapest
        // genuine one; an item whose page names another card number doesn't count. At most 3 kept, 5 opened.
        let kept = 0, opened = 0;
        for (const x of s.ok) {
          if (kept >= 3 || opened >= 5 || (kept > 0 && x.price + fee(x.price) > c.lim * 1.05)) break;
          const r = await readItem(x.href, c.num);
          opened++;
          await sleep(800);
          if (!r || r.sold || !r.price) continue;
          const an = r.anshin == null ? 'n' : r.anshin < 0 ? '-' : String(r.anshin);
          q.lines.push(`MI ${c.id} ${x.href.split('/').pop()} ${r.price} ${r.auction ? 'A' : 'F'} ${r.ends == null ? '-' : r.ends} ${an} ${r.grade} ${r.numok} ${encodeURIComponent(x.title.slice(0, 80))}`);
          if (r.numok !== '0' && r.grade) kept++;
        }
      } catch (e) {
        q.lines.push(`ME ${c.id} ${encodeURIComponent(String(e && e.message || e).slice(0, 120))}`);
      }
      q.i++;
      await sleep(1200);
    }
    q.done = true;
  })();
  return `started ${CARDS.length} cards`;
})();
