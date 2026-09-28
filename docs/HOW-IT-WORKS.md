# How the PSA10 Tracker works

A guide to the code, written so you can understand, change and fix the site yourself.
It describes the state of the repo on 2026-09-27 (commit `893210c`). Function names are
given instead of line numbers, because line numbers move with every edit. Search for
the name in your editor (Cmd+F, or Cmd+Shift+F across the project in VS Code).

Contents

1. The big picture
2. Building blocks in two minutes each
3. Map of the repo
4. The data files
5. How new data reaches the site
6. The page skeleton: index.html
7. A tour of app.js
8. Feature by feature
9. Styling: style.css
10. The GitHub Actions workflows
11. The Python scripts
12. The iPad/iPhone widget
13. Working on it yourself
14. Troubleshooting

---

## 1. The big picture

The tracker has three parts that never talk to each other directly. They only
share **JSON files in the `data/` folder**.

```
 ┌────────────────────────┐     writes JSON      ┌───────────────┐   git push   ┌──────────────┐
 │ Price checks & evals   │ ───────────────────▶ │  data/*.json  │ ───────────▶ │   GitHub     │
 │ (Claude + Python       │   scripts/*.py       │  in the repo  │              │   repo       │
 │  scripts on your Mac)  │                      └───────────────┘              └──────┬───────┘
 └────────────────────────┘                                                            │ Action
                                                                                        ▼ "deploy"
 ┌────────────────────────┐    issue forms       ┌───────────────┐              ┌──────────────┐
 │ You, on the site:      │ ───────────────────▶ │ GitHub Action │ ──commit───▶ │ GitHub Pages │
 │ Bought it / limits /   │   (GitHub issues)    │ + Python      │              │ (the website)│
 │ Add card               │                      └───────────────┘              └──────┬───────┘
 └────────────────────────┘                                                            │
                                                                                        ▼
                                                 ┌──────────────────────────────────────────────┐
                                                 │ Your browser: index.html + app.js fetch the   │
                                                 │ JSON and build every page from it             │
                                                 └──────────────────────────────────────────────┘
```

Three things follow from this design, and they explain most of the code:

- **There is no server and no database.** GitHub Pages only serves files. Anything
  the site "saves" either lives in your browser (localStorage) or goes through a
  GitHub issue form. A GitHub Action then turns the issue into a commit.
- **Raw data in, everything else computed in the browser.** Snapshots hold what was
  measured (prices, listings, sales) plus human judgment (tiers, verdict text).
  Anything that can be calculated, such as off-peak %, zones, DIY cost, heat and
  signals, is calculated in `app.js` each time the page renders. `docs/schema.md`
  states this rule: storing a number that could be computed counts as a bug.
- **Publishing = committing to `main`.** Every push to `main` triggers
  `.github/workflows/deploy.yml`, which republishes the whole repo as the website in
  about a minute.

---

## 2. Building blocks in two minutes each

These are the patterns the code uses again and again. Skip any you already know.

**Static site.** `index.html` is the page, `assets/style.css` makes it look right, and
`assets/app.js` makes it do things. The browser downloads all three, and then
`app.js` downloads the JSON in `data/`. There is no build step: the files in the repo
are exactly what the browser gets.

**JSON.** A text format for data: `{"key": value}` objects, `[a, b]` lists, strings,
numbers, `true/false/null`. Python reads it with `json.load`, JavaScript with
`response.json()` or `JSON.parse`.

**fetch, promises, async/await.** `fetch('data/manifest.json')` asks the server for a
file and returns a *promise*, a placeholder for a result that arrives later.
Inside an `async function`, `await somePromise` pauses that function until the
result is there, without freezing the page. `Promise.all([p1, p2, p3])` waits for
several promises at once. That's how the site loads all its files in parallel
(see `loadFreshBundle`). `.catch(() => null)` turns a failed request into `null`
so one missing file doesn't break the page.

**Building HTML from strings.** Most render functions build one long HTML string
with *template literals* (backtick strings where `${expression}` is inserted) and
put it on the page with `element.innerHTML = html`. Example from `tagChip`:

```js
return `<span class="vtag ${tag}">${escapeHtml(tagLabel(tag))}</span>`;
```

Any text that comes from data goes through `escapeHtml()` (or `escapeAttr()` inside
attributes). That stops a card name containing `<` from breaking the page. If you
add new output, keep doing this.

**Event listeners.** `button.addEventListener('click', () => { ... })` runs code when
something happens. Because `innerHTML` replaces elements, listeners must be attached
again after each render. That's why render functions end with a block of
`querySelectorAll(...).forEach(b => b.addEventListener(...))`.

**localStorage.** A small key-value store inside your browser, per website and per
device. The site wraps it in `store.get(key, default)` / `store.set(key, value)`,
which never throw errors (private browsing can block storage). All keys start
with `psa10.`, listed in section 13.

**Hash routing.** Everything after `#` in the address (`#/card/455596`) never
reaches the server, and changing it doesn't reload the page. The browser fires a
`hashchange` event instead, and `applyRoute()` shows the right section. That's how
one HTML file behaves like a multi-page app with a working back button.

**CSS variables and media queries.** `:root { --accent: #ffd23f; }` defines a
colour once. Everything else uses `var(--accent)`. `@media (max-width: 899px) { ... }`
applies rules only on narrow screens. That's how the same HTML becomes the sidebar
layout on a computer and the tab-bar layout on a phone.

**git, GitHub Pages, GitHub Actions.** git records changes as commits. `git push`
sends them to GitHub. GitHub Pages hosts the repo as a website. GitHub Actions
runs scripts on GitHub's servers when something happens: a push, a new issue, or
a manual trigger. The recipes live in `.github/workflows/*.yml`.

**Issue forms.** `.github/ISSUE_TEMPLATE/*.yml` define structured forms for new
GitHub issues. The site builds links like
`.../issues/new?template=bought.yml&url=...&price=...` so the form opens pre-filled.

---

## 3. Map of the repo

```
index.html                     the page skeleton: sidebar, tab bar, one <section> per view
assets/app.js                  all browser logic (~2,500 lines, one file)
assets/style.css               all styling (~730 lines)
assets/*.png, favicon.ico      icons

data/manifest.json             list of snapshots (file name, time, full/quick)
data/snapshots/*.json          one file per price check (the core data)
data/history.json              compact per-card price + trading-rate series   (generated)
data/calls.json                track record: scored calls and stated odds       (generated)
data/custom_index.json         My-tier index: definition + daily levels
data/events.json               release calendar for the event rule
data/limits.json               limit prices saved "to all devices"
data/holdings.json             your purchases
data/odds_model.json           parameters of the limit-odds model
data/odds_log.json             the model's logged forecasts, for scoring        (generated)
data/tracked_cards.json        cards added via "+ Add card"
data/incoming/                 drop folder for price-check output (gitignored)

scripts/*.py                   publishing and maintenance scripts (section 11)
pricecheck/                    the price-check skill's machinery: in-page scripts, assemble.py,
                               card list, FULL-CHECK.md (full-check procedure)
scripts/odds_model_builder.js  in-browser helper to rebuild the odds model
.github/workflows/*.yml        deploy, log purchase, set limit (section 10)
.github/ISSUE_TEMPLATE/*.yml   Add card, Bought it, Remove purchase, Set limit forms
widgets/psa10-widget.js        Scriptable widget for iPhone/iPad (section 12)
docs/schema.md                 exact shape of a snapshot and holdings.json
docs/HOW-IT-WORKS.md           this guide
```

---

## 4. The data files

| File | Written by | Read by | What's inside |
|---|---|---|---|
| `manifest.json` | `add_snapshot.py` | site, scripts | `{"snapshots": [{"file", "collected_at_jst", "check_mode"}]}`, oldest first |
| `snapshots/YYYYMMDD-HHMM.json` | `add_snapshot.py`, `quick_update.py`, `apply_analysis.py`, `email_price_alert.py` | site | `collected_at_jst`, `notes`, `cards[]`, `pokeca_chart_index`, optional `banners`, `market_context` |
| `history.json` | `build_history.py` (called by the publish scripts) | site (price history, 7D/30D, heat trend, tier review) | per snapshot: `d` time, `m` mode, `i` pokeca index, `p {url: [price, confirmed]}`, `h {url: [PSA10/day, raw/day]}`; plus `tiers {url: {since, i}}` |
| `calls.json` | `build_calls.py` (via `build_history.py`) | Track record page | `summary`, `calls[]`, `predictions[]`, `model_odds` |
| `custom_index.json` | `add_custom_index.py` | Market page, correction rule, tier review | `meta` (constituents, base prices) + `series[]` of daily `{d, level, prices, pokeca_psa10}` |
| `events.json` | `events.py` | event rule, calendar | `window_days`, `events[] {d, name, major, scope}` |
| `limits.json` | `set_limit.py` (Action) | site, widget | `{"limits": {url: {price, set, issue}}}` |
| `holdings.json` | `log_purchase.py` (Action), `add_holding.py` | site | `{"holdings": [{id, card_url, purchase_price_jpy, ...}]}` |
| `odds_model.json` | `save_odds_model.py` | site (limit odds), `odds_model.py` | per-card volatilities, pooled z-curves, calibration factors |
| `tracked_cards.json` | `card_requests.py` | price-check skill | extra cards beyond the skill's built-in list |
| `insights.json` | `set_insight.py` (full check step 7b) | card page "What stands out" | written analyses for cards that stand out |

**One card inside a snapshot** looks like this, trimmed. The full version is in
`docs/schema.md`:

```jsonc
{
  "card_name_ja": "ブラッキーex SAR [SV8a 217/187](ハイクラスパック「テラスタルフェスex」)",
  "url": "https://snkrdunk.com/apparels/455596",   // ← the card's identity everywhere
  "image_url": "https://cdn.snkrdunk.com/...webp",
  "favorite_count": 5321,
  "psa10_population": 9123, "psa10_gem_rate_pct": 71.2,
  "grades": {
    "psa10":       { "lowest_price": 69000, "top20_cheapest_listings": [...],
                     "count_within_15pct": 6, "recent_completed_sales": [{"price", "when"}] },
    "raw_a_grade": { ...same shape... }
  },
  "analysis": {                                     // human judgment; optional
    "representative_price": 67500, "price_source": "sales_confirmed",
    "peak": { "price": 111000, "when": "Apr 2026" },
    "tiers": { "definitely_buy": 58000, "buy_upper": 68500, "ceiling": 77500 },
    "verdict": { "tag": "buy", "label": "...", "reasoning": "...", "predictions": [...] },
    "grading_fee_jpy": 9980, "raw_tiers": {...}
  }
}
```

**The card's `url` is its ID.** Limits, holdings, history and calls all match cards by
`url`. The site's addresses use the number at the end of it (`#/card/455596`, see
`cardId()`). If a SNKRDUNK URL ever changed shape, every lookup would break at once.

**Card names carry their metadata.** `parseCardName()` splits
`名前 [SET 000/000](パック名)` into `short`, `code` and `pack`. The set code is also
used to scope events (`M6a`) and to look up odds-model data. Keep that bracket
format when adding cards by hand.

---

## 5. How new data reaches the site

**Full price check.** `pricecheck/plan.py` decides what today's run reads (which cards get their
listings pages, which altema pages are due, the Monday and monthly extras). Claude then runs one
in-page script per site in your browser (`pricecheck/scripts/snkrdunk_full.js`, `altema_batch.js`,
`pokeca_both.js`, plus the My-tier extractor); each opens the site's own pages in hidden same-origin
iframes and returns compact lines. `python3 scripts/full_update.py -` takes all the lines on stdin,
decodes them into the raw JSON below, runs `pricecheck/scripts/assemble.py` against the live snapshot
and hands over to `add_snapshot.py` and `add_custom_index.py`. The older description below still
describes what happens inside those scripts:

Claude reads SNKRDUNK, altema and pokeca-chart in your browser.
The price-check skill assembles one JSON file, which is copied to
`data/incoming/latest-run.json`. Then `python3 scripts/add_snapshot.py data/incoming/latest-run.json`:

1. normalizes field names and warns about a stale timestamp or a changed card list;
2. refuses byte-identical duplicates;
3. **carries forward** each card's `analysis` (tiers, peak, verdict, DIY fields)
   and population from the previous snapshot, so a routine check never wipes an
   evaluation (`carry_forward_analysis`, `carry_forward_population`);
4. saves `data/snapshots/<YYYYMMDD-HHMM>.json` and appends it to `manifest.json`;
5. logs limit-odds forecasts (`odds_model.log_for_snapshot`) and rebuilds
   `history.json` + `calls.json` (`build_history.build`);
6. commits and pushes. The deploy Action publishes the site.

**Quick check.** `pricecheck/scripts/snkrdunk_quick.js` runs once in a SNKRDUNK tab: it opens every
card's product page in a hidden same-origin iframe, one after another, and returns one compact line
per card (`<id> f<favorites> p<PSA10 ask> a<A ask> P<sales> A<sales>`, codes in the script's header).
Those lines go straight to `python3 scripts/quick_update.py -` on stdin; its `decode_compact()` turns
them back into the raw JSON shape. `quick_update.py` then starts from the latest snapshot and replaces only
what a quick run measures (lowest asks, recent sales, favorites). Everything else
is carried and stamped `listings_as_of` / `population_as_of` / `as_of`. The site shows
those stamps as small "as of 9/26 15:15" labels (`asOfHtml`). It then hands off to
`add_snapshot.py`.

**Evaluation.** `apply_analysis.py` merges new tiers, peak and verdict into the
**latest** snapshot (matched by URL, name or set code, and it refuses to guess on
ambiguous names). It validates `predictions`, rebuilds history and calls, then
commits and pushes.

**From the site (through GitHub issues):**

| Button on the site | Issue form | What processes it | Result |
|---|---|---|---|
| ✓ Bought it / Remove | `bought.yml` / `remove-purchase.yml` | Action `purchases.yml` → `log_purchase.py` | `holdings.json` updated, site redeployed, issue closed |
| Save to all devices (limit) | `set-limit.yml` | Action `limits.yml` → `set_limit.py` | `limits.json` updated, redeployed, closed |
| + Add card | `add-card.yml` | the **next price check** → `card_requests.py` | added to `tracked_cards.json`, issue closed |

One detail worth knowing: a push made *by* an Action with its built-in token does not
trigger other workflows. That's a GitHub rule to prevent endless loops. So
`log_purchase.py` and `set_limit.py` explicitly start `deploy.yml` through the GitHub
API (`/actions/workflows/deploy.yml/dispatches`) after pushing.

---

## 6. The page skeleton: index.html

`index.html` holds almost no content, only empty containers that `app.js` fills.

- **`<aside class="sidebar">`**: logo, `<nav id="nav">` with one link per view, and the
  snapshot picker `#snapshot-select` plus "+ Add card". Each nav link has
  `data-view="..."` (used to highlight the current one) and an empty
  `<em data-count="...">` badge filled by `updateCounts()`.
- **`<header class="mobile-bar">`**: the phone header with its own picker
  `#snapshot-select-m`. The two pickers are kept in sync.
- **`<main>`**: `#page-title` / `#page-sub` (set by `applyRoute`), `#back-link`, then
  **one `<section class="view" data-view="...">` per page**: overview, collection,
  watching, holdings, planner, record, market, tables, more, card, compare and duel. Only one is
  visible at a time.
- **`<nav class="tabbar">`**: the phone bottom bar.
- At the end: `<script src="assets/app.js?v=20260927">`. The `?v=` part is a cache
  buster, see section 13.

When you look for where something appears, find its container `id` here (for example
`id="planner"`), then search `app.js` for `getElementById('planner')` to find the
function that fills it (`renderPlanner`).

---

## 7. A tour of app.js

The whole file is wrapped in `(function () { 'use strict'; ... })();`, an
*immediately invoked function*. Its variables stay private and don't leak into the
browser's global scope. As a side effect, you can't type `state` in the DevTools
console; section 13 has workarounds.

The file is divided by comment headers like `// ---------- data loading ----------`.
In order:

| Section (comment header) | Key functions | Purpose |
|---|---|---|
| top | `state`, `els`, `parseCardName`, `verdictHeadline` | global app state and shortcuts to page elements |
| formatting helpers | `fmtYen`, `fmtPct`, `fmtDateJST`, `escapeHtml`, `dirClass` | turning numbers into display text |
| data loading | `fetchJSON`, `loadFreshBundle`, `showBundle`, `init`, `loadIndex` | fetching, caching, startup |
| derived-value helpers | `getRep`, `depthInfo`, `computeDiyEconomics`, `computeGauge`, `zoneOf`, `liveTagOf`, `displayTagFor` | the core calculations |
| event rule | `upcomingEvents`, `activeEvents`, `eventFor`, `heldByEvent`, `renderEvents` | release-calendar logic |
| (correction rule) | `correctionState`, `heldByCorrection` | market-correction logic |
| my limit prices + buy signals | `store`, `getLimit`, `setLimit`, `reconcileLimits`, `limitFormUrl` | limits |
| odds of a listing reaching a price | `touchOdds`, `zShare`, `limitOddsHtml` | limit-odds model |
| purchases | `holdingCost`, `boughtFormUrl`, `removeFormUrl`, `computeSignals`, `renderSignals` | holdings links and the Buy-signals strip |
| render: market strip / My-tier index | `renderMarketStrip`, `customIndexStats`, `renderCustomIndex`, `drawIndexChart` | Market page |
| tier review status + card vs market | `tierReview`, `vsMarketHtml`, `marketMove` | "Review due" and "Vs. the market" |
| render: banners | `computeAutoFlags`, `renderBanners` | alerts on the overview |
| app shell: views + routing | `VIEWS`, `parseRoute`, `applyRoute`, `openCard`, `updateCounts` | navigation |
| card photos | `measureTrim`, `applyTrim`, `trimImages` | making cards fill their frames |
| render | `render()` | redraws everything |
| sorting | `SORTS`, `sortCardsBy`, `setSort`, `TABLE_SORTS`, `setTableSort` | sortable columns |
| render: key numbers / portfolio | `renderKpis`, `renderPortfolio` | KPI tiles, Holdings |
| overview list + drawer | `zoneBarHtml`, `renderOverviewList`, `renderDrawer`, `renderCardPage` | Overview |
| trading activity ("heat") | `salesPerDay`, `heatOf`, `heatChip`, `renderHeat` | Activity labels |
| display case | `renderCollection`, `renderWatchPanel` | Collection, Watching |
| card detail | `buildCardDetail`, `wireCardDetail` | card page and drawer |
| budget planner | `plannerState`, `renderPlanner` | Planner |
| track record | `renderTrackRecord` | Track record |
| limit controls | `wireLimitControls`, `openLimitEditor`, `limitSyncHtml` | editing and dragging limits |
| price history | `getCardPriceHistory`, `buildPriceHistoryHtml`, `buildGradeDetail` | History and Listings tabs |
| interactive charts | `chartSlot`, `mountCharts`, `drawLineChart`, `drawBarChart`, `wireHover` | SVG charts |
| render: tables | `renderTables`, `buildDiyTable`, `buildComparisonTable` | Tables page |
| head to head / budget duel | `renderCompare`, `tapeHtml`, `raceHtml`, `ladderHtml`, `renderDuel`, `drawMultiChart` | comparing cards |
| end | `loadCardRequests`, `init()` | pending-issue notices, start |

### Startup, step by step

1. The browser loads the HTML and CSS, then runs `app.js`. The last lines call
   `init()` and `loadCardRequests()`.
2. `init()` registers the `hashchange` listener, then **immediately starts**
   `loadFreshBundle()` (network) without waiting for it.
3. Meanwhile it checks localStorage for `psa10.cache.v1`, the complete data from your
   last visit. If found, `showBundle(cached, false)` draws the site right away and
   the body gets the class `is-updating`, which shows the thin yellow bar at the top.
4. `loadFreshBundle()` fetches `manifest.json` **and** all optional files
   (`OPTIONAL_DATA`: holdings, calls, custom index, events, history, limits, odds model)
   in parallel. When the manifest arrives, it fetches the latest and the previous
   snapshot in parallel. Each fetch uses `{cache: 'no-cache'}`: the browser asks
   GitHub "has this changed?" and gets a tiny "304 Not Modified" answer if not.
5. When fresh data arrives, `init()` compares it with what's shown. If anything
   changed, and you haven't picked a different snapshot in the meantime, it calls
   `showBundle(fresh, true)` and saves the fresh bundle as the new cache.
6. `showBundle()` copies each file into `state`, fills both snapshot pickers and sets
   up sorting (once), then calls `render()`.

### render(): the heart of the app

```js
function render() {
  renderMarketStrip(data); renderCustomIndex(); renderEvents(); renderHeat();
  renderKpis(data); renderSignals(cards); renderBanners(data, state.previousData);
  renderPortfolio(...); renderOverviewList(cards); renderDrawer(); renderCollection(cards);
  renderWatchPanel(...); renderPlanner(cards); renderTrackRecord(); renderTables(...);
  updateCounts(); applyRoute(); trimImages(document);
}
```

**Every view is re-rendered from `state` every time.** Hidden views are rendered too,
so switching pages is instant. When something changes (a new limit, a different
snapshot), the code updates `state` or localStorage and calls `render()` again. It's
simple and hard to get out of sync. With about 20 cards it's also fast enough.
Some small interactions redraw only their own piece: `renderPlanner` after ticking a
checkbox, and `setSort` redraws just the list and the collection.

### Routing

`parseRoute()` reads `location.hash` → `{view, arg}` (unknown views fall back to
`overview`). `applyRoute()` then:

- hides every `.view` section except the matching one;
- highlights the nav link (for a card page, the view it was opened from, stored in
  `state.cardFrom`, which also drives the "Back" link);
- for `#/card/<id>`, finds the card with `findCardById()` and draws it with
  `renderCardPage()`;
- sets the page title, subtitle (`viewSubtitle`) and browser tab title.

`openCard(card)` decides what clicking a card does. On a wide screen (≥1200px,
`DESKTOP` media query) on the Overview, it fills the side drawer. Everywhere else,
it navigates to `#/card/<id>`.

**Snapshot picker.** Choosing an older check calls `loadIndex(i)`, which fetches that
snapshot and the one before it (for "since last check" comparisons), then `render()`.

---

## 8. Feature by feature

### Which price is "the price"?

`getRep(card)` returns `analysis.representative_price` if an evaluation set one
(usually sales-confirmed), otherwise the lowest PSA10 ask. Zones, verdict pills,
off-peak %, P&L and history use it. **Limits and signals use `lowestAsk(card)`
instead**, because a limit means "a listing I could buy right now is at or below my
number". If a number looks "wrong" on the site, first check which of the two it uses.

### Verdict pill (Buy / Watch / …)

`displayTagFor(card)` decides the pill. The rules, in order:

1. No `analysis` → no pill ("No tiers").
2. A written `verdict.tag` of `defer` always wins (a deliberate "hold regardless").
3. Otherwise the **live zone** from `liveTagOf(tiers, getRep(card))`:
   ≤ definitely_buy → Definitely buy, ≤ buy_upper → Buy, ≤ ceiling → Watch, above → Don't buy.
4. A live **Buy** is shown as **Watch** while the correction rule or an event rule is on.
   Definitely-buy is never downgraded.

So the pill updates with every price check without a new evaluation. Only the
written reasoning needs Claude. When the live zone and the written tag disagree,
`buildCardDetail` shows a yellow "worth a fresh look" note (`verdict-stale`).

### Correction rule and event rule

- `correctionState()` compares the My-tier index today with 30 days ago
  (falling back to pokeca-chart's month change if the series is too short). At
  −10% or worse (`CORRECTION_PCT = 10`), the rule is on. The result is cached per
  snapshot.
- `activeEvents()` lists dated, major events from `events.json` that are 0–3 days away
  (`window_days`). `eventApplies()` checks the scope: `"all"` or a list of set codes
  matched against the card's code.
- Both feed `displayTagFor` and produce banners (`renderBanners`) and card notes
  (`heldByEvent`, `heldByCorrection`). The evaluation skill applies the same rules,
  so the site and the written verdicts agree.

### Zone bar and gauge

- The **zone bar** in lists (`zoneBarHtml`) is four coloured `<i>` segments whose widths
  are percentages of a scale (the peak or ceiling × 1.08). A white tick marks the price
  and a gold tick marks your limit.
- The **gauge** on the card page (`computeGauge` + the `gaugeHtml` block in
  `buildCardDetail`) is one CSS `linear-gradient` with hard colour stops at each
  tier, plus absolutely positioned markers for the price, the peak and your limit.
  The limit marker can be dragged (`wireLimitControls`: pointer events convert the
  x position back to yen, rounded to ¥500).

### Limits: local first, then synced

There are two stores:

- `limits` in localStorage (`psa10.limits`): edits made in *this* browser. A value
  of 0 means "cleared here".
- `state.syncedLimits` from `data/limits.json`: limits saved to all devices.

`getLimit(card)` prefers the local edit, otherwise the synced value.
`limitSync(card)` says which one applies, and `limitSyncHtml` shows "Only on this
device · Save to all devices ↗". That link (`limitFormUrl`) opens the pre-filled
`set-limit` issue. Once the Action has updated `limits.json` and the site reloads,
`reconcileLimits()` sees that the local and synced values agree and deletes the
local copy. It only runs against fresh data, never against the cached copy.

### Limit odds

`touchOdds(card, price)` answers "what's the chance a listing reaches ≤¥X within
30/90 days?". It computes the log-distance from today's lowest ask, divides by the
card's own volatility from `odds_model.json` (or the pooled value for cards without
history), looks that up in empirical curves (`zShare`) and applies calibration
factors. `scripts/odds_model.py` does the same maths in Python, so logged forecasts
match what the site showed. `limitOddsHtml` also shows the evaluation's own stated
odds for a nearby price, as a cross-check.

### Buy signals strip

`computeSignals(cards)` collects cards whose lowest ask ≤ your limit (rank 0),
Definitely-buy (1) and Buy (2). `renderSignals` shows them. Signals not seen on your
previous visit get a **NEW** label (their keys are remembered in
`psa10.seenSignals`, and only while viewing the latest snapshot).

### Banners ("Automatically detected…")

`renderBanners` stacks the event rule banner (or a "Coming up" note within 14 days),
the correction rule banner, any hand-written `banners` from the snapshot JSON, and
`computeAutoFlags()`. Those flags compare with the previous snapshot: depth down
30%+, a zone crossing, or favorites ±5%.

### Tier review and "Vs. the market"

- `tierReview(card)` reads `history.json → tiers[url].since` (when the tiers were last
  set or re-confirmed). It flags **Review due** after 30 days or a 10% market move
  since then.
- `vsMarketHtml` compares the card's 7- and 30-day change with the market's
  (My-tier index, or pokeca-chart) to tell a card-specific drop from a market-wide one.

### What stands out (insights)

`insightsFor(card)` (section "insights" in `app.js`) looks for numbers that stand out: the card
moving 8+ points differently from the market over 7 days (12+ over 30), the lowest ask 8%+ away from
the median of the last week's sales, an 8%+ jump since the last check, trading up or down 50%+ on a
week ago, or the ask within 5% of your limit. Each finding cross-checks the other evidence (sales,
trading, depth) before saying what it probably means, and the list is shown on the card page, with
an "Insight" chip on the overview for strong ones. `scripts/outliers.py` applies the same rules in
Python; the full check (step 7b) writes a short analysis for its top cards with
`scripts/set_insight.py` into `data/insights.json`, shown at the top of the panel. The thresholds
are in `INSIGHT` (JavaScript) and `T` (Python); change both together.

### Trading activity ("heat")

`salesPerDay(sales)` turns SNKRDUNK's "when" strings (`3時間前`, `2日前`,
`2026/09/14`) into ages in days (`saleAgeDays`). It then divides the number of
sales by the age of the oldest. `HEAT_LEVELS` maps that rate to Hot ≥5, Active ≥3,
Slow ≥1.2 and Cold per day; raw A-rank uses `HEAT_LEVELS_RAW` (40/15/5).
`build_history.py` stores the same rate per snapshot, so the site can show
"a week ago". The icons are small inline SVGs (`HEAT_ICON`).

### Overview list and sorting

`renderOverviewList` draws one `<a class="wl-row">` per card with a PSA10 market. It
uses `display: grid` in CSS, so each `<span>` is a column. Sorting uses `SORTS`:
each entry has a `label`, a default direction `dir` and a function `v(card)` giving
the value to sort by. `sortCardsBy` puts cards without a value last and breaks ties
with the "signals first" rank. Header buttons (`.wl-head [data-sort]`) and the
phone's Sort menu both call `setSort`. A third click on the same column returns to
the default. The choice is saved in `psa10.sort`.

**To add a sortable column:** add an entry to `SORTS`, a
`<button data-sort="yourkey">` in the `.wl-head` in `index.html`, a matching cell in
`renderOverviewList`, and a width in the `.wl-row, .wl-head` `grid-template-columns`
rules in `style.css`.

### Card page and drawer

`buildCardDetail(card, prevCard, mode)` returns the whole detail as one HTML string.
`mode` is `'drawer'` (side panel) or `'page'` (full card page). Inside: the hero
(slab picture, price, off-peak, change since the last check, tags), four tabs and
four `.cd-panel` blocks: Overview (gauge, tier review, limit row, vs-market,
verdict, stats), History, Listings and DIY. `wireCardDetail` attaches the tab
switching (remembered in `state.cardTab`), the limit controls and the charts.
**The History tab loads lazily**: `renderPriceHistoryInto` only runs the first
time you open it.

### Charts

All charts are hand-drawn SVG, with no chart library:

- While building HTML, `chartSlot(cfg)` stores the chart's configuration in a map and
  returns an empty `<div data-chart="ch12">`.
- After the HTML is on the page, `mountCharts(root)` draws each slot at its real pixel
  width (`drawLineChart` or `drawBarChart`). A `ResizeObserver` redraws it when the
  width changes, for example when a hidden tab is opened.
- `wireHover` adds the crosshair and tooltip for mouse, touch and arrow keys.
- The My-tier index chart on the Market page has its own, similar `drawIndexChart`.

### Card photos that fill the frame

SNKRDUNK's cut-out photos have different amounts of transparent margin.
`measureTrim(url)` loads each image once into a small off-screen `<canvas>` and finds
the bounding box of non-transparent pixels. `applyTrim` then sets three CSS
variables on the `<img>` (`--h`, `--cx`, `--cy`), which the `.card-img` rule in
`style.css` uses to zoom and centre the card. Results are cached in
`psa10.imgTrim.v1`. If the CDN ever stops allowing this (CORS), images fall back to
a default zoom.

### Collection, Watching, Holdings

- `renderCollection`: the same sorted cards as tiles with a PSA-slab frame
  (`slabHtml`), plus a "+ Add a card" tile.
- `renderWatchPanel`: cards *without* a PSA10 market (raw price, favorites, raw heat).
  A card moves to the Overview automatically once a PSA10 listing appears,
  because `hasMarket(card)` becomes true.
- `renderPortfolio`: each holding is matched to the current snapshot by `card_url`.
  Value = `getRep`, cost = `holdingCost` (price plus grading and shipping for raw
  purchases), and P&L is computed. Each purchase has a Remove link.

### Budget planner

`plannerState()` reads `psa10.planner` (budget, mode, ticked cards).
`renderPlanner` prices each card at today's lowest ask or at your limit
(`mode === 'limits'`), subtracts `spent` (from holdings) and marks cards that
still fit. Every change calls `save()`, which stores the new state and re-renders
the planner and the KPI tiles.

### Track record

`renderTrackRecord` only *displays* `calls.json`. All scoring (30-day windows,
per-card noise thresholds, two-reading confirmation, Brier scores) happens in
`scripts/build_calls.py` when a check is published. To change how calls are judged,
edit the Python, not the JavaScript. Which cards you expanded is remembered in
`psa10.trOpen`.

### Market page and Tables

- `renderMarketStrip`: the pokeca-chart index cells.
- `renderCustomIndex`: My-tier stats, the range buttons (3M/1Y/All, remembered in
  `psa10.ciRange`), the chart and the constituents table.
- `renderHeat`, `renderEvents`, plus the snapshot's `notes`.
- `renderTables`: cards become *columns* and statistics *rows*. Rows with a
  `sortableLabel()` button sort the columns (`TABLE_SORTS`, saved in `psa10.tableSort`).

### Head to head and budget duel

Both live in the section `// ---------- head to head (#/compare/…) and budget duel (#/duel/…) ----------`
of `app.js`. Nothing new is stored; every number comes from functions described above.

- **Picking cards:** "⇄ Compare two cards" on the Collection page sets `state.cmpMode`.
  While it's on, `renderCollection` makes each tile toggle its URL in `state.cmpPick`
  (`togglePick`) instead of opening the card, and `renderCompareBar` shows the sticky bar.
  "Head to head" goes to `#/compare/<idA>,<idB>`. Leaving the Collection cancels the mode.
- **Head to head page:** `applyRoute` calls `renderCompare(arg)`. It has two tabs:
  - *Tale of the tape* (`tapeHtml`): each row is `[label, hint, value function, format,
    better]`, where `better` is `'low'`, `'high'` or `null` (context only). The card closer
    to a good buy on a row gets the bright bar; each group's chip names the card that leads
    all of its scored rows, or says "Split". Rows where neither card has a value are hidden.
  - *Price race* (`raceHtml` + `drawMultiChart`): both cards' prices from `history.json`
    (last check per day), indexed to 100 on the first day both have a price, or as % below
    peak; the My-tier index is added in indexed mode. Scale and range are remembered in
    `psa10.race`. Below it, `ladderHtml` draws each card's zones scaled to its own Buy line.
  - `relation(a, b)` compares set codes and the character name (the leading katakana/kanji
    of the card name, without メガ) to say whether the two are one bet or separate bets.
- **Budget duel:** the planner shows "⇄ Compare N cards" when 2–4 cards are ticked
  (`CMP_MAX_DUEL`). It links to `#/duel/<id>,<id>,…`, drawn by `renderDuel`: today's ask
  and your limit with what's left of the budget, `touchOdds` for your limit, Definitely-buy
  and the Buy line, the DIY comparison, and totals for buying all of them.
- **Colours:** card A/B (and C/D in a duel) use `CMP_COLORS`.

### Scout (#/scout)

Cards you don't track yet that fit your criteria and look cheap. Full checks run `pricecheck/scripts/pokeca_scout.js` on pokeca-chart's card list: it keeps modern secret rares (card number above the set size, released 2021+, PSA10 ¥15k–150k) that aren't on the tracker, sends today's list price for all of them (`SCP` line) and reads up to 20 of their card pages (`SC` lines, oldest reading first). `scripts/scout.py` (called by `full_update.py`) merges that into `data/scout.json` and ranks the candidates; its docstring has the filters and the score. The page (`renderScout`) shows 3–5 of the ranked list per JST day, stepping through it so each day brings different cards, with "+ Track it" (the Add card form with the SNKRDUNK page filled in) and "Not for me" (hidden in this browser via localStorage). Cards without an ex/V/VMAX/VSTAR/GX name (trainers, mostly) only show with the "Include trainers" switch.

### Slab premium (DIY tab)

`premiumHtml(card)` shows how many times the raw A-rank price a PSA10 costs. Three readings: SNKRDUNK's lowest asks and recent sales (`snkrPremium`, from the card itself; the per-check line comes from `history.json`'s `"r"` field, written by `build_history.py`), and pokeca-chart's 18-month history with the card's own 6-month norm (`premiumOf`, from `data/premium.json`). Full checks refresh `premium.json`: `pricecheck/scripts/pokeca_premium.js` reads each card's pokeca-chart page, `full_update.py` hands the `PREM` lines to `scripts/premium.py`. When the pokeca premium is 20%+ from its norm (`PREM_FLAG`, same threshold in `scripts/outliers.py`), "What stands out" adds a stretched/compressed finding. Its score is capped at 1.2 because the tested effect is small (project doc `raw-vs-psa10-leadlag-2026-09-28`): it never shows the overview's Insight star on its own.

### Pending-request notices

`loadCardRequests()` asks GitHub's public API for open issues. It shows
"N card requests waiting…", "Recording a purchase…", or a link if a purchase issue
has been stuck for over 5 minutes (meaning the Action commented an error). If GitHub
is unreachable, nothing is shown.

---

## 9. Styling: style.css

- **Tokens first.** The `:root` block at the top defines every colour, both fonts and
  the corner radius. To change the accent colour, change `--accent` (and `--accent-2`
  for hover) there. `widgets/psa10-widget.js` has its own copy of the colours in `C`.
- **Fonts.** `--display` (Bebas Neue) for numbers, headings and card names; `--sans`
  (Montserrat) for body text. Noto Sans JP is the fallback for Japanese characters,
  which Bebas Neue lacks. They're loaded from Google Fonts in `index.html`.
- **Sections** are marked with comments (`/* ---------- overview: list + drawer ---------- */`)
  in roughly the same order as `app.js`.
- **Three layouts** via media queries:
  - ≥1200px: sidebar + overview list + detail drawer;
  - 900–1199px (`@media (max-width: 1199px)`): no drawer; rows open the card page;
  - <900px (`@media (max-width: 899px)`): phone layout with the top bar and bottom tab bar.
- **Verdict colours** come from classes like `.vtag.buy`, `.vtag.watch`; heat from
  `.heat-chip.heat-hot` etc.; up/down numbers from `.pos` / `.neg` (added by `dirClass()`).
- **Refresh bar:** `body.is-updating::before` at the very end.

A good way to explore: right-click an element on the site → **Inspect**. DevTools shows
the HTML and every CSS rule that applies, with the file and line. You can edit values
live to try things before changing the file.

---

## 10. The GitHub Actions workflows

- **`deploy.yml`**: on every push to `main` (or when triggered manually), uploads the
  whole repo to GitHub Pages. `concurrency: pages` cancels an older deploy if a newer
  one starts.
- **`purchases.yml`**: when an issue is opened or edited, it runs only if the issue is
  open, was opened by you (`github.repository_owner`) and has the `bought` or
  `remove-purchase` label. Then `python3 scripts/log_purchase.py "$GITHUB_EVENT_PATH"`.
  The event file contains the whole issue, including the form's answers.
- **`limits.yml`**: the same pattern for the `set-limit` label → `set_limit.py`.

Both Python scripts parse the form's Markdown body (`### Price` headings followed by
the answer), validate it, update the JSON, commit as `github-actions[bot]`, push
(retrying up to three times with `pull --rebase`, in case a price check pushed at the
same moment), trigger the deploy, then comment and close the issue. If the form can't
be read, they comment the reason and leave the issue open. Editing the issue re-runs them.

You can watch every run under the repo's **Actions** tab on GitHub, including the full
log of any that failed.

---

## 11. The Python scripts

All scripts are run from the repo root (`python3 scripts/<name>.py`), and each starts
with a docstring explaining its usage. Open the file and read the top.

| Script | You'd run it when… |
|---|---|
| `full_update.py` | publishing a full price check from the compact lines (the skill does it; `--dry-run` to preview) |
| `../pricecheck/plan.py` | seeing what today's full check will read |
| `add_snapshot.py` | publishing an assembled snapshot (called by `full_update.py` / `quick_update.py`) |
| `quick_update.py` | publishing a quick check |
| `apply_analysis.py` | applying an evaluation (`--dry-run` to preview) |
| `check_status.py` | seeing the latest snapshot, whether today's full check ran, and the ids a quick check reads |
| `card_requests.py` | handling Add-card issues: `list`, `add`, `set`, `reject` |
| `build_history.py` | rebuilding `history.json` + `calls.json` by hand (normally automatic) |
| `build_calls.py` | rebuilding only the track record |
| `add_custom_index.py` | updating or backfilling the My-tier index |
| `events.py` | managing the release calendar: `list`, `add`, `date`, `remove`, `window` |
| `odds_model.py` / `save_odds_model.py` | printing today's odds / saving a rebuilt model |
| `add_holding.py` | bulk-entering purchases from the Mac |
| `email_price_alert.py` | applying one lower price from a SNKRDUNK email alert |
| `log_purchase.py`, `set_limit.py` | run by Actions; `--dry-run event.json` to test locally |

Scripts that push use the credential file configured for the repo. **Never put a
token in a script or a command, and never commit one.** `.git-credentials` is in
`.gitignore` for that reason.

---

## 12. The iPad/iPhone widget

`widgets/psa10-widget.js` runs in the Scriptable app. It fetches the public files from
`https://sprdl.github.io/psa10-tracker/data/...` directly (manifest, the latest
snapshot, limits, custom index, events) and re-implements a small part of the site's
logic: zones, signals and limit hits, drawn with Scriptable's widget API. Only limits
saved to all devices are visible to it. If you change a rule in `app.js` (say, the
correction threshold), check whether the widget has its own copy of that rule.

---

## 13. Working on it yourself

### Run the site on your Mac

Opening `index.html` by double-clicking won't work, because browsers block `fetch()`
from `file://` pages. Start a tiny local server from the repo folder instead:

```bash
cd ~/Documents/My\ JavaScript\ Projects/psa10-tracker
python3 -m http.server 8000
```

Then open <http://localhost:8000>. Stop it with Ctrl+C. Edit a file, save, and reload
the page. Use **Cmd+Shift+R** (hard reload) if a change doesn't show.

### Publish a change

```bash
git pull                     # always start from the latest (price checks push often)
# ...edit and test...
git add assets/app.js        # or whatever you changed
git commit -m "Describe the change"
git push                     # the site updates in ~1 minute
```

### Bump the version after changing app.js or style.css

Browsers keep `app.js` and `style.css` for up to 10 minutes. To make everyone get the
new file immediately, change the `?v=20260927` in **both** places in `index.html`
(the `<link>` for style.css and the `<script>` for app.js) to today's date, e.g.
`?v=20261003`. Data files don't need this; they're always revalidated.

### If you change the shape of the data

The site shows the cached copy from localStorage first. If you rename or restructure
a field, bump `CACHE_KEY` in `app.js` (`'psa10.cache.v1'` → `'psa10.cache.v2'`), so an
old cached bundle in the previous shape is never rendered by the new code.

### Debugging in the browser

Open DevTools with **Cmd+Option+I**.

- **Console** tab: red errors show the file and line. Click to jump to the code.
- **Network** tab: each JSON file, whether it loaded (200/304) or failed (404).
- **Application → Local Storage**: the `psa10.*` keys. Deleting one resets that feature
  on that device:

  | Key | Holds |
  |---|---|
  | `psa10.cache.v1` | last loaded data (for instant start) |
  | `psa10.limits` | limits changed on this device only |
  | `psa10.planner` | budget, price mode, ticked cards |
  | `psa10.sort`, `psa10.tableSort` | sort orders |
  | `psa10.seenSignals` | which buy signals are no longer NEW |
  | `psa10.ciRange` | My-tier chart range |
  | `psa10.trOpen` | expanded cards on the Track record |
  | `psa10.imgTrim.v1` | measured photo margins |

- Because `state` is private, quick inspection is easiest by fetching the data:
  `await (await fetch('data/limits.json')).json()` in the console. To poke at internal
  state while testing locally, temporarily add `window.dbg = state;` inside the file,
  and don't commit it.
- Put `debugger;` on a line in `app.js` to pause there with DevTools open, then hover
  over variables to see their values.

### Recipes

- **Change a label or text on the page.** Search `app.js` for the visible text (for
  example `Buy signals`) and edit the string.
- **Change a threshold.** Constants are named in capitals near their feature:
  `CORRECTION_PCT`, `TIER_MAX_AGE_DAYS`, `TIER_MAX_INDEX_MOVE`, `HEAT_LEVELS`,
  `LIMIT_STEP`, `HISTORY_MAX_SNAPSHOTS`. The event window lives in
  `data/events.json` → `window_days`. Scoring constants are at the top of
  `scripts/build_calls.py`. For rules the evaluation skill also applies, change the
  skill too, so the site and written verdicts stay consistent.
- **Change the default budget.** `plannerState()` → `200000`.
- **Fix a wrong number in one snapshot.** Edit the JSON in `data/snapshots/`, then
  `python3 scripts/build_history.py` so `history.json` and the track record pick it up,
  and commit all changed files.
- **Remove a card from tracking.** Remove it from `data/tracked_cards.json` (or from the
  price-check skill's own list). Old snapshots keep it, which is fine.
- **Add a new view.** Add a `<section class="view" data-view="x">` and nav links in
  `index.html`, add `x: 'Title'` to `VIEWS`, a case in `viewSubtitle`, a
  `renderX()` function, and call it from `render()`.

---

## 14. Troubleshooting

| Symptom | Likely cause | Where to look |
|---|---|---|
| "Couldn't load data/manifest.json" | manifest missing or invalid JSON after a manual edit | validate with `python3 -m json.tool data/manifest.json` |
| Site shows old data after a check | deploy still running or failed | repo → Actions tab; the yellow bar means a refresh is in progress |
| New code doesn't appear | browser cached app.js | bump `?v=` (section 13), or hard-reload |
| One section is empty, the rest works | a JavaScript error in that section's render function | DevTools Console |
| A purchase or limit form did nothing | issue not opened by you, missing label, or form error | the issue's comments; Actions tab log |
| `git push` rejected | a price check or Action pushed first | `git pull --rebase` then `git push` |
| Push fails with an auth error | the token in the credential file expired | create a new token on GitHub and update the credential file (never paste it into a chat or commit) |
| A card shows "No tiers" after a check | it was never evaluated, or the URL changed so carry-forward missed it | compare `url` with the previous snapshot |
| Limit shows "Only on this device" forever | the set-limit issue wasn't processed | check the issue; `data/limits.json` |
| Card photos too small or offset | trim measurement cached from a bad load | delete `psa10.imgTrim.v1` in Local Storage |
