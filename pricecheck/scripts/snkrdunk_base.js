// SNKRDUNK base-page extractor. Run on https://snkrdunk.com/apparels/<id>.
// Returns favorite_count + recent completed sales (売買履歴) for PSA10 and A, as compact JSON.
// Edit GRADES inside if you only need one grade. Sales-history pills are real <button>s inside <li>;
// the table rows are <tr> with CSS-module classes ending in __soldAt / __variant / __condition / __price.
await (async () => {
  const GRADES = ['PSA10', 'A'];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  for (let i = 0; i < 25 && !document.body.innerText.includes('売買履歴'); i++) await sleep(400);
  const t = document.body.innerText;
  if (!t.includes('売買履歴')) return { error: 'base page did not finish loading (売買履歴 not found)' };
  // Headline block renders as "¥\n45,000~\n3,921" — the number after the price is the ♥ favorite count.
  const fm = t.match(/¥\s*\n\s*[\d,]+~\s*\n\s*([\d,]+)\s*\n/);
  const out = { title: document.title.split('通販')[0], favorite_count: fm ? Number(fm[1].replace(/,/g, '')) : null, sales: {} };
  if (!fm) out.favorite_error = 'favorite count pattern not found';
  const readRows = () => [...document.querySelectorAll('tr')].map(r => ({
    when: r.querySelector('[class*="__soldAt"]')?.innerText.trim(),
    grade: r.querySelector('[class*="__variant"]')?.innerText.trim(),
    qty: r.querySelector('[class*="__condition"]')?.innerText.trim(),
    price: Number((r.querySelector('[class*="__price"]')?.innerText || '').replace(/[^\d]/g, '')),
  })).filter(r => r.when && r.price);
  for (const grade of GRADES) {
    const btn = [...document.querySelectorAll('li > button')]
      .find(b => b.innerText.trim() === grade && b.closest('ul')?.innerText.includes('すべて'));
    if (!btn) { out.sales[grade] = { error: 'sales-history grade pill not found' }; continue; }
    let rows = [];
    for (let attempt = 0; attempt < 3; attempt++) {           // first click often doesn't register → retry
      if (!/__active/.test(btn.className)) btn.click();
      for (let w = 0; w < 12; w++) {
        await sleep(400);
        rows = readRows();
        if (w >= 3 && !rows.length && /__active/.test(btn.className) && document.body.innerText.includes('この期間内に取引がありません')) break;
        // wait until the table shows this grade only (a mostly-PSA10 "すべて" table used to pass early and cut rows)
        if (w >= 1 && rows.length && rows.every(r => r.grade === grade)) break;
      }
      if (/__active/.test(btn.className)) break;
    }
    const noSales = document.body.innerText.includes('この期間内に取引がありません');
    const match = rows.filter(r => r.grade === grade && r.qty === '1枚');
    const res = {
      pill_active: /__active/.test(btn.className),
      recent_completed_sales: match.slice(0, 20).reverse().map(r => ({ price: r.price, when: r.when })), // oldest → newest
    };
    const discarded = rows.length - match.length;
    if (!res.pill_active) res.error = 'grade pill did not activate after 3 clicks';
    else if (noSales && !match.length) res.sales_note = 'no completed sales in period (この期間内に取引がありません)';
    else if (discarded) res.sales_note = `${discarded} row(s) discarded: grade/quantity did not match ${grade}/1枚`;
    out.sales[grade] = res;
  }
  return out;
})()
