# Manual fallback (only if an extractor script fails)

Use this only for the specific page/step whose script returned an error indicating the page structure changed (e.g. "controls not found", "pill not found", "allData not found"). Do the step by hand, then at the end of the run propose a fix to the script via the skill-creator / propose_skills flow so the next run is automatic again. Prefer `find` / `read_page` refs over remembered coordinates; always re-screenshot before clicking after any scroll.

## SNKRDUNK listings (per grade)
1. Open `<url>/used?conditionIds=22` (PSA10) or `=18` (A). If those IDs stop working, open the base page, click the grade tile near the top (NOT the pills under 売買履歴), then the teal 出品一覧を見る button.
2. Set sort to 安い順 first. The select is Vue-controlled; if form_input doesn't take, run:
   `const s=document.querySelector('select');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(s,'price');s.dispatchEvent(new Event('input',{bubbles:true}));s.dispatchEvent(new Event('change',{bubbles:true}));`
3. Tick 販売中のみ. Confirm no tiles have the `sold` class / SOLD overlay.
4. Listings render as `<price> / <grade>` blocks. Take the 20 lowest (fewer is fine). If on-page order can't be confirmed, scroll until the text is stable and sort in code.

## SNKRDUNK base page
- Favorite count: the number right after the headline price (`¥\n45,000~\n3,921` → 3,921).
- 売買履歴: click the grade pill in the 状態 row (leave 枚数 on 1枚). The first click often doesn't register — re-read and confirm rows show the intended grade. Keep the last 15–20 rows of that grade, oldest→newest, as `{price, when}`. Discard rows of other grades and note how many. "この期間内に取引がありません" → empty array + `sales_note`.
- Image (only if cards.json has no image_url): the main product photo, a `cdn.snkrdunk.com/upload_bg_removed/...` URL; prefer `?size=l`.

## pokeca-chart.com
- Header fields: 最新価格, 前日比, 月間変動, 年間変動 (value + %), and the date range under 指数チャート（PSA10 / 美品）.
- Volume: enable the 取引件数 toggle near 平均価格 and judge the last 1–2 weeks of bars vs the preceding month from one screenshot at the 3M view → rising / falling / flat / spiking. Dismiss ad modals via their × first.

## altema.jp
- PSA10総枚数 and PSA10取得率 in the PSA10 price table. Absent section → population error, not a guess.
