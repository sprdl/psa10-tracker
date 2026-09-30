# Reference state and lookup tips

Read this file only when the step that needs it comes up (Monday PSA check, a new/broken altema URL, a card-list change).

## PSA Japan tier status — last known state (for the Monday check)

Standard ¥9,980 / 100 business days · Priority (renamed from Regular/レギュラー, effective 2026-09-15) ¥11,980 / 80 business days (up from 60) · Express ¥29,980 / 25 business days (up from ¥22,980, effective 2026-09-10) · Value tier paused, resumption 未定 (undetermined).

Standard, 1 card, full cost (PSA Japan order screen, 2026-09-30, tax incl.): grading ¥9,980 + 保険・送料 (insurance & shipping) ¥1,900 + 事務手数料 (handling) ¥550 = ¥12,430. Declared value limit ¥150,000 per card on Standard. The tracker uses grading_fee_jpy 9980 + shipping_insurance_jpy 2450.

psacard.com/ja-JP has been Cloudflare-blocked to browser automation. If direct access fails, web-search for a recent source that explicitly cites PSA Japan's own announcement (a trading-card shop blog quoting PSA Japan is fine; prefer the most recently updated). If nothing changed, say so plainly in `notes`, but always call out tier renames or new effective dates even when prices match. After a run finds a change, update this section via the skill-creator / propose_skills flow.

`psa_tier_status` shape: `{ "checked": true, "value_tier_paused": bool, "resumption_date_stated": "<text or 'undetermined'>", "standard_price_jpy": n, "standard_turnaround_business_days": n, "notes": "..." }`

## altema.jp lookup tips (only when adding a card or a URL breaks)

- Use altema's own search (`https://altema.jp/pokemoncard/searchresults?q=<query>`) with simple one- or two-word Japanese queries, or tag links like `#ブラッキー`. Multi-word AND queries often 404; card-number-only searches ("217/187") return nothing.
- Similar names collide (reprints in anniversary products, older promo prints). The altema extractor returns `card_number` and `pack` — confirm both match the tracked card before trusting its population. If in doubt, compare with the SNKRDUNK page's 発売日 / 管理番号.

## New-release (M6a "30th CELEBRATION") cards

Released 2026-09-16. Expect few or zero PSA10 listings/sales and no altema population until PSA grading catches up (weeks). That is a valid result, not a failure. Their altema pages are the permanent `/pokemoncard/card/<id>` URLs in cards.json. When one gains population data, `assemble.py` prints a reminder to switch that card's `altema_mode` to `daily`.

## Changing the tracked-card list

If the user adds/removes SNKRDUNK favorites, ask for the new card's SNKRDUNK URL (or name + set/number), find its altema URL, and update `references/cards.json` via the skill-creator / propose_skills flow. Leave `image_url` empty for a new card; the run fills it (see SKILL.md) and the file is updated afterwards.
