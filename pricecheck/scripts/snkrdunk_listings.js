// SNKRDUNK listings extractor. Run on https://snkrdunk.com/apparels/<id>/used?conditionIds=<22 for PSA10 | 18 for A>.
// Applies 安い順 (Vue-safe native setter) + 販売中のみ, verifies no SOLD tiles and ascending order,
// and returns the top-20 cheapest prices plus the derived 15% stats.
await (async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  for (let i = 0; i < 25 && !(document.querySelector('select') && document.querySelector('input[type=checkbox]')); i++) await sleep(400);
  const sel = document.querySelector('select'), cb = document.querySelector('input[type=checkbox]');
  if (!sel || !cb) return { error: 'listings page controls (sort select / 販売中のみ) not found' };
  const lm = document.body.innerText.match(/中古一覧\s*\n+\s*([^\n]+)/);
  const filter_label = lm ? lm[1].trim() : null;           // e.g. "PSA10" or "A（きれいな状態）" — confirms the grade filter
  if (sel.value !== 'price') {                                 // sort FIRST, then the checkbox
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(sel, 'price');
    sel.dispatchEvent(new Event('input', { bubbles: true }));
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    await sleep(1200);
  }
  if (!cb.checked) { cb.click(); await sleep(1200); }
  const read = () => [...document.querySelectorAll('.item-list')].map(li => ({
    sold: li.classList.contains('sold'),
    price: Number((li.querySelector('.item-price')?.childNodes[0]?.textContent || '').replace(/[^\d]/g, '')),
    grade: li.querySelector('.item-price span:last-child')?.innerText.trim(),
  })).filter(x => x.price);
  let items = [], ok = false;
  for (let w = 0; w < 15; w++) {                               // wait for re-render to settle
    items = read();
    const asc = items.every((x, i) => i === 0 || x.price >= items[i - 1].price);
    if (!items.some(x => x.sold) && asc) { ok = true; if (w >= 1 && (items.length || w >= 5)) break; }
    else if (w === 7 && !cb.checked) cb.click();              // re-click checkbox once if SOLD tiles remain
    await sleep(400);
  }
  const out = { filter_label, sort: sel.value, for_sale_only: cb.checked };
  if (!items.length) { out.error = 'no for-sale listings found for this grade'; return out; }
  if (!ok) {                                                   // fallback: sort in code, drop sold tiles
    out.sort_note = 'on-page order/sold filter not confirmed; sorted and filtered in script';
    items = items.filter(x => !x.sold).sort((a, b) => a.price - b.price);
  }
  const wrongGrade = items.filter(x => filter_label && x.grade && !filter_label.startsWith(x.grade)).length;
  if (wrongGrade) out.grade_warning = `${wrongGrade} tile(s) show a grade different from the filter label`;
  const top = items.slice(0, 20).map(x => x.price);
  const lowest = top[0], thr = Math.round(lowest * 1.15), within = top.filter(p => p <= thr);
  Object.assign(out, {
    lowest_price: lowest, threshold_115pct_of_lowest: thr,
    top20_cheapest_listings: top, listings_within_15pct_of_lowest: within,
    count_within_15pct: within.length, count_excluded_over_15pct: top.length - within.length,
  });
  return out;
})()
