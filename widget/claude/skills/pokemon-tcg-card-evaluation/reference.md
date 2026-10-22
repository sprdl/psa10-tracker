# Reference: prompt template and evaluated cards

(Part of the `pokemon-tcg-card-evaluation` skill; SKILL.md says when to read this. Split out of SKILL.md on 2026-10-23 so runs that don't need it don't read it; the claude.ai copy of the skill still has it inline.)

## Reusable prompt template

Copy this, fill in the brackets, and use it (with web search / browsing available) whenever evaluating a card outside a price check.

```
Analyze [CARD NAME] — [set code + number], [Japanese set name] (【set name】),
released [date if known], illustrator [name if known] — for my PSA10 Japanese
Pokémon TCG collection. [I'm watching it / I own it: bought [date] for ¥[price]
([slab / raw, sent to PSA])].

CRITERIA: only PSA10 graded copies (raw/A-rank for reference only). Only
modern full-art cards of any rarity (AR, SAR, SR, CSR, SA, MA, …) — no
regular-frame commons/rares, no vintage. Goal is display (magnetic UV case,
office) plus investment. Today's date is [date]. [Optional: budget context /
other cards being weighed against this / how much this card is wanted and why.]

RESEARCH — use Japanese-market sources (SNKRDUNK, pokeca-chart.com/gr, card
shop buyback trackers, note.com market commentary) and PSA's pop report
(psacard.com/pop) for population, read in my browser. Gather:
1. Current PSA10 market price — recent transaction prints over stated averages;
   flag outlier prints
2. PSA10 population and gem rate, release date, backlog check; DIY replacement
   cost = (raw A-rank + ¥12,430) ÷ gem rate (Standard to ¥150,000; Priority
   +¥2,000 to ¥250,000; Express above), where
   raw A-rank = median of the last 5 one-copy A sales in 30 days, never
   below the lowest ask (fewer than 3 sales: the lowest ask)
3. Raw/A-rank price (rule above) and 1-month trend, cross-checked against real trades
4. Longest reliable price range and average (state the window), the pre-hype
   level, and the most recent peak (peak-month median) with % drawdown
5. Demand drivers, cannibalization/reprint risk, in-print status
6. Market regime: My-tier index 30-day change, pokeca-chart index, events in
   the next 3 days, the card's age and hype exposure
7. Selling cost on SNKRDUNK (9.5% + ¥300 + ~¥1,000 shipping) and, if owned,
   my break-even sale price

OUTPUT — two parts:

PART A (prose): if watching, the buy part (Don't-buy ceiling, Watch, Buy,
Definitely buy, timing, odds with deadlines checked against the limit-odds
model, downside risk); if owned, the sell part (Hold / Take profit from ¥X /
Sell from ¥Y, net result after fees today, anchors, odds with deadlines,
market regime). Be honest about data quality; correct my assumptions when the
data disagrees.

PART B: the JSON block from the pokemon-tcg-card-evaluation skill (tiers +
verdict for a buy evaluation, sell_tiers + sell_verdict for an owned card,
every stated probability as {text,p,type,price,by}).
```

---

## Card reference (evaluated cards)

Starting data for cards already evaluated with this skill. Use it for step 1 (identification) and as a prior baseline. Always re-pull live data: the tracker's latest snapshot and the card page are the current source, and these figures go stale within days.

### ゲッコウガex SAR [SV5a 090/066] (Greninja ex SAR)
- **Identity:** 強化拡張パック「クリムゾンヘイズ」 (Crimson Haze), released 2024-03-22, illus. akagi. SNKRDUNK https://snkrdunk.com/apparels/224087 · PSA pop: Pokemon Japanese Sv5a-Crimson Haze, no. 090. Don't confuse it with Mega Greninja (M4), the overseas promo SA, or other Greninja prints.
- **Supply:** mature population, 15,446 PSA10 of 18,269 graded, 84.5% gem rate (PSA pop report, 2026-10-12). The sealed box trades at about 2× retail, which suggests it's likely out of print (not formally verified).
- **PSA10 phases (SNKRDUNK monthly medians):** 2024: ¥12k post-release trough in May → ¥25.5k by Dec. 2025: ¥41–48k H1 → ¥47–49k Jul–Aug → ¥58–62k Sep–Dec. 2026: peak ¥79–83k Jan–Feb (high ¥85.5k on 2/13, before the anniversary announcement) → ¥64–75k Mar–Aug → ¥42.75k on 2026-09-25.
- **Tiers (2026-09-25):** Definitely buy ≤¥38,000 · Buy ≤¥43,000 · Ceiling ¥49,000.
- **Watch for:** the PSA10 premium over raw A-rank collapsed to about 13% (usually about 45%). The card fell 31% year on year while the index rose 5%; likely cause is cannibalization by M4 Mega Greninja (hypothesis, not proven). Raw A-rank trades only 1–3 times a month.
- **Useful as an analog:** how a popular-character SAR behaves after release, from trough to about 7× over 21 months in a rising market.

### ゲンガーVMAX SA [SGG 020/019] (Gengar VMAX, Special Art) — restored to the tracker 2026-10-10
- **Identity:** ハイクラスデッキ「ゲンガーVMAX」 (High Class Deck Gengar VMAX). SNKRDUNK https://snkrdunk.com/apparels/91178.
- **Price levels:** pre-hype ¥238–247k in Q4 2025, about ¥270k in Feb 2026, peak-month median ¥457.7k (Aug 2026). On 2026-10-10 the lowest ask was ¥378k with sales at ¥385–400k, up ~35% in a week during the rally.
- **Tiers (2026-10-10):** Definitely buy ≤¥265,000 · Buy ≤¥295,000 · Ceiling ¥335,000 (Don't buy at ¥378k). The user's saved limit was ¥150,000. Above PSA Priority's ¥250,000 declared-value cap (only Express), and above the whole singles budget on its own.

### メガゲッコウガex SAR [M4 114/083] (Mega Greninja ex SAR) — removed from the tracker 2026-10-06
- **Identity:** 拡張パック「ニンジャスピナー」 (Ninja Spinner), released 2026-03-13, illus. Susumu Maeya. SNKRDUNK https://snkrdunk.com/apparels/776365. The MUR print (M4 120/083) is a separate card.
- **Useful as an analog:** a card that launched into a bubble with no pre-hype baseline: median ¥118k (Apr 2026) → ¥28k (2026-09-25), raw ¥55k → ¥17k, PSA10 ending at DIY cost (94.7% gem rate, in print).

### メガリザードンXex MA [M2a 223/193] (Mega Charizard X ex, Mega Attack Rare) — owned
- **Identity:** ハイクラスパック「MEGAドリームex」 (MEGA Dream ex), released 2025-11-28, illus. Saboteri. SNKRDUNK https://snkrdunk.com/apparels/722239. Full art (American-comic style, INFERNO X in large letters). MA cards are numbered 223–232. Texture-error copies (Traditional Chinese texture) trade separately at about 7–10×.
- **Supply:** 66,963 PSA10 at a 91.2% gem rate (2026-10-03): very common. Raw A-rank about ¥3.5–4k, so there's no DIY floor.
- **PSA10 phases (monthly medians):** ¥27–28k Dec 2025–Jan 2026 → ¥21.6k Mar → peak ¥38.7k Apr → ¥33.5k May → ¥26.9k Jun → ¥20.3k Jul → ¥14.7k Aug → ¥12.7k Sep → ¥10.7k on 2026-10-03.
- **Buy tiers (2026-10-03):** Definitely buy ≤¥8,500 · Buy ≤¥9,500 · Ceiling ¥11,500. Bought 2026-10-07 for ¥10,800 (slab).

---
