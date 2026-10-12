# Reference state and lookup tips

Read this file only when the step that needs it comes up (Monday PSA check, a new/broken PSA pop page, a card-list change).

## PSA Japan tier status — last known state (for the Monday check)

Standard ¥9,980 / 100 business days · Priority (renamed from Regular/レギュラー, effective 2026-09-15) ¥11,980 / 80 business days (up from 60) · Express ¥29,980 / 25 business days (up from ¥22,980, effective 2026-09-10) · Value tier paused, resumption 未定 (undetermined).

Standard, 1 card, full cost (PSA Japan order screen, 2026-09-30, tax incl.): grading ¥9,980 + 保険・送料 (insurance & shipping) ¥1,900 + 事務手数料 (handling) ¥550 = ¥12,430. Declared value limit ¥150,000 per card on Standard. The tracker uses grading_fee_jpy 9980 + shipping_insurance_jpy 2450.

psacard.com/ja-JP has been Cloudflare-blocked to browser automation. If direct access fails, web-search for a recent source that explicitly cites PSA Japan's own announcement (a trading-card shop blog quoting PSA Japan is fine; prefer the most recently updated). If nothing changed, say so plainly in `notes`, but always call out tier renames or new effective dates even when prices match. After a run finds a change, update this section via the skill-creator / propose_skills flow.

`psa_tier_status` shape: `{ "checked": true, "value_tier_paused": bool, "resumption_date_stated": "<text or 'undetermined'>", "standard_price_jpy": n, "standard_turnaround_business_days": n, "notes": "..." }`

## PSA pop report lookup tips (only when adding a card or a page breaks)

- The pop report needs a signed-in PSA account (the browser pane keeps the login). Years: `https://www.psacard.com/pop/tcg-cards/156940`; a year page lists its sets (Show 250, page through). Japanese sets are named "Pokemon Japanese <code>-<English set name>" (SV/Mega era) or "Pokemon Japanese Sword & Shield <name>" (S era); English promos "Pokemon Svp EN-SV Black Star Promo".
- On the set page, the card number is written as PSA does ("090", "217"). A number can have several rows (rarity annotations like "Special Art Rare", error or stamp variants): `psa_pop.js` takes the row without extra variety text, else the biggest total; set `psa_pop_name` (English name fragment) when two different cards share a number.
- Gem rate = PSA 10 ÷ total graded on that row.

## New-release (M6a "30th CELEBRATION") cards

Released 2026-09-16. Expect few or zero PSA10 listings/sales and no PSA population until PSA grading catches up (weeks). That is a valid result, not a failure. They get a PSA pop page (step 1c) once they have regular PSA10 sales; Monday checks list Defer cards with a PSA10 ask so the first PSA rows are caught.

## Changing the tracked-card list

If the user adds/removes SNKRDUNK favorites, ask for the new card's SNKRDUNK URL (or name + set/number), find its PSA pop page, and update `references/cards.json` via the skill-creator / propose_skills flow. Leave `image_url` empty for a new card; the run fills it (see SKILL.md) and the file is updated afterwards.
