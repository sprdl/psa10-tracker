# How Ghost Bid works

*Ghost Bid is the app's name since 2026-10-18 (before: PSA10 Tracker). Only the name and mark changed: the repo, the site address,
file names (`psa10-widget.js`, `PSA10Bar`) and the `psa10.*` browser storage keys keep their old names on purpose.
The mark is `assets/logo.svg` (header); `favicon.ico`, `assets/favicon-16/32.png`, `assets/apple-touch-icon.png` and
`assets/logo-mark.png` (widget header) are renders of it. The menu-bar icon is 👻 (rebuilt by `widget/install.sh`).*

A guide to the code, written so you can understand, change and fix the site yourself.
It describes the repo as of 2026-10-17 (after the audit fixes, the speed and data-growth work and the widget loader). Function names are
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
 ┌────────────────────────────┐   compact lines    ┌───────────────┐   git push   ┌──────────────┐
 │ Price checks & evaluations │ ─────────────────▶ │  data/*.json  │ ───────────▶ │   GitHub     │
 │ (Claude runs in-page       │  scripts/*.py on   │  in the repo  │              │   repo       │
 │  scripts in your browser:  │  your Mac          └───────────────┘              └──────┬───────┘
 │  SNKRDUNK, pokeca-chart,   │                                                          │ Action
 │  PSA pop)                  │                                                          ▼ "deploy"
 └────────────────────────────┘                                                   ┌──────────────┐
 ┌────────────────────────────┐    issue forms     ┌───────────────┐  commit      │ GitHub Pages │
 │ You, on the site: Bought / │ ─────────────────▶ │ GitHub Action │ ───────────▶ │ (the website)│
 │ Sold / limits / targets /  │  (GitHub issues)   │ + Python      │              └──────┬───────┘
 │ sealed / pulls / answers…  │                    └───────────────┘                     │
 └────────────────────────────┘                                                          ▼
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
  Anything that can be calculated, such as off-peak %, zones, DIY cost, heat,
  signals, sell verdicts and P&L, is calculated in `app.js` each time the page renders.
  `docs/schema.md` states this rule: storing a number that could be computed counts as a bug.
  The exceptions are slow computations that need the whole archive (`history.json`,
  `calls.json`) or other sites' history (`odds_model.json`, `value_model.json`, `hype.json`,
  `premium.json`, `scout.json`): those are built by Python scripts and stored.
- **Publishing = committing to `main`.** Every push to `main` triggers
  `.github/workflows/deploy.yml`, which republishes the website in about a minute. It doesn't
  upload the whole repo: `scripts/site_bundle.py` builds a `_site/` folder with the site files and
  the last 30 days of snapshots (section 10).

The price checks never use an HTTP client. Claude opens the sites' own pages in hidden
same-origin iframes of a tab in your browser (the same pages a person would open), only when
you ask for a check. The in-page scripts in `pricecheck/scripts/` return short text lines, and
the Python scripts decode them.

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
`querySelectorAll(...).forEach(b => b.addEventListener(...))`. A few buttons that appear
in many places (Bought it, Remove card, Undo, Restore) use one listener on `document`
instead, which checks `e.target.closest('[data-bought]')` and similar.

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
GitHub re-applies prefilled values over what you type, so where you have to enter
something (a purchase price, a date), the site asks first in its own dialog
(`openBoughtDialog`) and opens the form with exactly those values.

---

## 3. Map of the repo

```
index.html                     the page skeleton: sidebar, tab bar, one <section> per view
assets/app.js                  all browser logic (~6,000 lines, one file)
assets/style.css               all styling (~1,600 lines)
assets/*.png, favicon.ico      icons

data/manifest.json             list of snapshots (file name, time, full/quick)
data/snapshots/*.json          one file per price check (the core data)
data/*.json                    everything else: see the table in section 4
data/incoming/                 drop folder for price-check output, run clock, history cache (gitignored)

scripts/*.py                   publishing, Action and maintenance scripts (section 11)
scripts/odds_model_builder.js  in-browser helper to rebuild the odds model and hype pool (monthly)
scripts/value_model_builder.js in-browser helper to rebuild the value model (monthly)
pricecheck/start.py            the price check's one setup call: mode, procedure, plan and browser calls
pricecheck/plan.py             what today's full check reads
pricecheck/jsrun.py            ready-to-paste browser calls with a hash-checked script cache (see below)
pricecheck/scripts/*.js        in-page scripts the price checks run in your browser
pricecheck/scripts/assemble.py turns the decoded reads into a snapshot
pricecheck/FULL-CHECK.md       the full-check procedure the price-check skill follows (core steps 0–7)
pricecheck/QUICK-CHECK.md      the quick-check procedure
pricecheck/steps/*.md          full-check steps only some runs need (1b, 1c, 5b, 6, 7b, 8b–8j), read on demand
pricecheck/references/         the skill's card list (cards.json), PSA tier state, manual fallback, snapshot shape

.github/workflows/*.yml        deploy + the Actions behind the site's forms (section 10)
.github/ISSUE_TEMPLATE/*.yml   the 13 issue forms the site opens
widgets/psa10-widget.js        Scriptable widget for iPhone/iPad (section 12)
widgets/psa10-loader.js        the loader pasted into Scriptable; downloads psa10-widget.js from the site
tests/rules.mjs, test_rules.py check that the site, the widget and the Python scripts apply the same rules (section 13)
tests/test_jsrun.py, test_psa_backlog.py, test_start.py, test_pipeline.py   the price-check tooling, its decoders and plan, the PSA backlog parser
docs/schema.md                 exact shape of a snapshot, holdings.json and the other files
docs/HOW-IT-WORKS.md           this guide
```

---

## 4. The data files

Files marked *generated* are rebuilt by a script; never edit them by hand.

| File | Written by | Read by | What's inside |
|---|---|---|---|
| `manifest.json` | `add_snapshot.py` | site, scripts, widget | `{"snapshots": [{"file", "collected_at_jst", "check_mode"}]}`, oldest first |
| `snapshots/YYYYMMDD-HHMM.json` (compact JSON, one line) | `add_snapshot.py` (via `full_update.py` / `quick_update.py`), `apply_analysis.py`, `psa_pop.py` | site (last 30 days), widget, every script | `collected_at_jst`, `check_mode`, `notes`, `cards[]`, `pokeca_chart_index`, optional `banners`, `market_context` |
| `history.json` *generated* | `build_history.py` (on every publish) | site: price history, 7D/30D, heat trend, tier review, slab premium line, value chart, holding timing, supply & demand charts; widget; `predict.py`, `outliers.py`, `review_due.py` | per snapshot: `d` time, `m` mode, `i` pokeca index, `p {url: [price, confirmed]}`, `h {url: [PSA10/day, raw/day]}`, `r {url: [PSA10 ask, raw ask, PSA10 sales median, raw sales median, raw A-rank price]}`, `f {url: favorites}` (once a day, when changed), `q {url: [cheap listings, listings read]}` (fresh listing reads), `n {url: [population, gem rate]}` (fresh readings, when changed); plus `tiers {url: {since, i}}` and `tier_log {url: [[since, db, bu, ceil], …]}`. Entries older than 30 days keep one check per JST day |
| `sales.json` *generated* | `build_history.py` | History tab (loaded when opened) | every PSA10 one-copy sale the checks saw, once each: `{url: [[hour, price], …]}` |
| `calls.json` *generated* | `build_calls.py` (via `build_history.py`) | Track record, Scored calls | `summary` (closed-window score, early decisions, baseline, return vs the market, Brier scores), `calls[]`, `predictions[]`, `model_odds[]` |
| `custom_index.json` | `add_custom_index.py` | Market page, overview index strip, correction rule, tier review, widget | `meta` (constituents, base prices) + `series[]` of daily `{d, level, prices, pokeca_psa10}` |
| `events.json` | `events.py` | event rule, release calendar, widget | `window_days`, `events[] {d, name, major, scope}` |
| `psa_backlog.json` | `psa_backlog.py` | Market page panel, Submissions line | `readings[] {d, m, note}` (PSA's backlog in millions of units), `check {last_checked, result}`, `threshold_m` (5.0), `tiers[]`, `value_prices`, `projection` (3 scenarios, written by the script) |
| `limits.json` | `set_limit.py` (Action); `log_purchase.py` removes a card's entry once you own it | site, widget, `predict.py` | `{"limits": {url: {price, set, issue}}}` |
| `sell_targets.json` | `set_limit.py` (Action) | sell signals | `{"targets": {url: {price, set, issue}}}` |
| `holdings.json` | `log_purchase.py` (Action) | Holdings, owned views, budget | `holdings[]` (singles), `sealed[]` (with `pulls[]`), `sold[]` |
| `holdings_prices.json` | `holdings_prices.py` (full check) | Holdings | latest SNKRDUNK price per bought untracked card / unopened sealed product |
| `portfolio_history.json` | `holdings_prices.py` (full check) | Holdings value chart | daily readings of the same, one entry per day |
| `binder.json` | `binder.py` (full check, Mondays only) | Binder | the raw cards from the physical binder with their A-rank raw price, the previous price (for ▲/▼) and the SNKRDUNK id |
| `odds_model.json` | `save_odds_model.py` (monthly) | limit odds, tier check, predictions, `odds_model.py` | per-card volatilities, pooled z-curves, calibration factors |
| `odds_log.json` | `odds_model.py` (via `add_snapshot.py`, full checks) | `build_calls.py` | the model's logged forecasts, for scoring |
| `value_model.json` | `save_value_model.py` (monthly) | Upside tab, Hold value, combination finder, tier review | 12/24-month market and card-part outcome samples, swing per card, age curve, release months |
| `hype.json` | `hype.py` (reference monthly) + `premium.py` (daily readings) | Hype exposure panel, "High hype" chip | per card: gain rank, trade rank, exposure score and level |
| `premium.json` | `premium.py` (full check) | DIY tab slab premium, insights, `outliers.py` | per card: pokeca-chart PSA10 ÷ raw premium, its 6-month norm, deviation, 18-month series |
| `insights.json` | `set_insight.py` (full check step 7b) | card page "What stands out", drawer | written analyses for cards that stand out (dropped after 30 days) |
| `stories.json` | `set_story.py` (full check step 8c) | Story tab, Stories page | researched write-up of each card's artwork, with sources |
| `predict.json` | `predict.py` (via `build_history.py`), `set_predictions.py` (Action) | You vs the model | `weeks {monday: {questions, answers, results, close}}` |
| `scout.json` | `scout.py` (full check, about every 2 days) | Scout page | candidate pool, ranked list, daily picks two weeks ahead |
| `tracked_cards.json` | `card_requests.py` | price-check skill | cards added with "+ Add card", beyond the skill's own `pricecheck/references/cards.json` |
| `eval_queue.json` | `card_requests.py`, `remove_card.py` (restore); emptied by `apply_analysis.py` | `eval_queue.py`, `check_status.py`, both update scripts | cards added or restored that the same price check must evaluate (EVALUATE NOW) |
| `recaps.json` | `recap.py save` (full check step 8j, Mondays) | Weekly recap page and Overview card | written note per week: `{"weeks": {monday: {headline, takeaway, happened[], ahead[], written}}}` |
| `focus.json` | `focus.py add/remove` | `focus.py` | the Focus watch cards: `{"cards": {url: {since, until, note}}}` |
| `focus_report.json` *generated* | `focus.py` (via `build_history.py`, on every publish) | Overview "Focus watch" panel; the update scripts' `FOCUS WATCH` block | per focus card: ask now / previous check / 24 h / 7 d, sales since the previous check, 24 h and 7 d, the cheap end of the book (asks within 3%, previous read), target (limit, else Buy tier), status, flags. Absent when no card is in focus |
| `grails.json` | by hand | Grails page; left out of every list and signal on the site and the widget | `{"grails": {snkrdunk id: {added, note}}}`; target = the card's limit, else its Buy tier |
| `removed_cards.json` | `remove_card.py` (Action) | site, `plan.py`, `assemble.py`, `add_snapshot.py` | `{"removed": {snkrdunk_id: {name, at}}}` |

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
    "verdict": { "tag": "buy", "label": "...", "reasoning": "...", "written": "...", "predictions": [...] },
    "sell_tiers": {...}, "sell_verdict": {...},     // only for cards you own
    "grading_fee_jpy": 9980, "raw_tiers": {...}
  }
}
```

**The card's `url` is its ID.** Limits, sell targets, holdings, history, calls, insights,
stories, premium and hype all match cards by `url`. The site's addresses and the removed-card
list use the number at the end of it (`#/card/455596`, see `cardId()`). If a SNKRDUNK URL ever
changed shape, every lookup would break at once.

**Card names carry their metadata.** `parseCardName()` splits
`名前 [SET 000/000](パック名)` into `short`, `code` and `pack`. The set code is also
used to scope events (`M6a`), to look up odds-model and value-model data, to find the cards
of a sealed product's set, and to tell whether two cards are "one bet" (`relation`). Keep that
bracket format when adding cards by hand.

---

## 5. How new data reaches the site

### Full price check (first run of each JST day)

The procedure is in `pricecheck/FULL-CHECK.md`; this is the outline.

0. `pricecheck/start.py` is the one setup call: it runs the status and mode check, lists card
   requests, starts the run clock (`scripts/runclock.py`, local timings in `data/incoming/`), and prints
   the procedure plus today's plan and browser calls.
1. `pricecheck/plan.py` decides what today's run reads: which cards get their listings pages,
   which PSA pop-report set pages are due (young cards daily, mature ones on Mondays), which bought
   items need a price (`HELD`), the slab-premium cards (`PREM`), whether Scout runs (`SCOUT`), and the
   Monday and monthly extras.
2. Claude runs one in-page script per site in your browser:
   `snkrdunk_full.js` (product pages and listings), `snkrdunk_held.js` (bought cards and unopened
   sealed items that aren't tracked), `psa_pop.js` (PSA10 population and gem rate from PSA's own pop report, signed in),
   `pokeca_both.js` (both pokeca-chart indices), the My-tier extractor
   (`add_custom_index.py --print-js`), `pokeca_premium.js` (slab premium and the hype reading) and
   `pokeca_scout.js` (Scout candidates). Each returns compact lines. The three sites run at the same
   time in separate tabs; each site still reads its own pages one after another.
   Since 2026-10-20 the procedures cut Claude's round trips (each costs several seconds and re-reads the
   whole context): independent calls go in one message (the Skill, `start.py` and the tool search; a
   Write and the command that reads it), and predictable browser steps go in one `browser_batch` call
   (start SNKRDUNK and create the other tabs; everything on the PSA and pokeca-chart tabs up to the
   premium poll; a RUN with its first POLL). `start.py` removes the last run's `data/incoming/*-in.txt`
   files first, so a Write never has to overwrite an unread file, and a command sent with a failed Write
   finds no file instead of the last run's lines.
   The scripts reach the page through `pricecheck/jsrun.py` (since 2026-10-13): each site's
   `localStorage` keeps a copy of the script text (`pc:js:<name>`), and a short RUN call checks that
   copy's SHA-256 against the repo, fills in today's arguments (built by Python from the plan), checks
   the SHA-256 of the filled-in script, and only then runs it. A missing or outdated copy runs nothing
   and asks for the STORE call, which checks its own pasted text before saving. If a site blocks it,
   `jsrun.py inline <name>` prints the filled-in script to paste directly, as before.
   `tests/test_jsrun.py` checks in Node that what runs is byte-for-byte the filled-in script.
   Since 2026-10-20 the runner doing those checks (`pricecheck/runner.js`) is cached as well (`pc:run`,
   `jsrun.py store runner` once per site and version, answered by `NEED_RUNNER`), so a RUN call is a short
   prefix that checks the runner's SHA-256 plus today's argument values, hashes go as 16 hex digits, and
   the POLL is `await globalThis.__pcpoll('<global>')`. For `snkrdunk_quick` / `snkrdunk_full` the POLL
   sends each card's sales and listing lists as a diff against the previous run's lines (runs of entries
   that stand in the previous list become `<start>.<count>`), ending with `#B <mode> <base> <hash>`:
   `scripts/salesdiff.py` rebuilds the exact lines inside `quick_update.py` / `full_update.py`, checks
   them against that hash and keeps the base in `data/incoming/snk-base.json` (the page keeps the same
   in `pc:base`; jsrun.py passes the file's hash, so the page only diffs when both match, and anything
   that doesn't add up makes the next run send whole lines and start over). A diff that can't be rebuilt
   publishes nothing; `jsrun.py poll <name> --full` then returns the lines undiffed. On the last 16 runs
   the diffed lines were about 31% of the whole ones, the text Claude retypes into the publish step.
   `tests/test_salesdiff.py` runs the page side in Node against real data and checks the round trip.
   `snkrdunk_full.js` waits for two identical sorted, unsold readings instead of fixed pauses. It skips a card's
   A-rank listings page when the A tile still shows the lowest ask of the last list read (`plan.py`'s
   `a_carry_price`, the fourth field of a plan line; never on Mondays, never when that list is 3+ days old):
   the card returns an `Rc` token and `full_update.py` carries the old list, stamped `listings_as_of`.
3. `python3 scripts/full_update.py -` takes all the lines on stdin. It refuses the run when a planned
   step left no lines (the completeness guard), decodes the lines into the raw JSON shape,
   runs `pricecheck/scripts/assemble.py` against the live snapshot (printing warnings and changes),
   then publishes: `add_snapshot.py`, `add_custom_index.py`, `premium.py` (which also updates
   `hype.json`), `scout.py`, `holdings_prices.py` (which also appends to `portfolio_history.json`).
   Each of those commits on its own; `full_update.py` pushes them all once at the end. The follow-ups
   after it (`apply_analysis.py`, `set_insight.py`, `set_story.py`, `hype.py`) only commit while the run
   clock is running (`scripts/deferpush.py`); `runclock.py end` pushes them in one go, so the site
   redeploys once. `widget/run-check.sh` pushes leftovers when a menu-bar run stops early.
4. `full_update.py` ends with three blocks: data that has gone stale (`freshness.py --stale`), the
   **FOLLOW-UPS** (step 8 of FULL-CHECK.md: evaluate new cards, write sell tiers for owned cards,
   stories for new cards, re-evaluate cards whose tiers are due, refresh written verdicts the price has
   moved 5%+ from, read sealed-product names, look at PSA's backlog page when `psa_backlog.py due` says so: from the
   day after an update is expected, daily until it's there).
5. Step 7b writes a short analysis for the cards `outliers.py` flags (`set_insight.py`). `full_update.py`
   prints that list itself after publishing (`CARDS THAT STAND OUT`, and `7b` in the FOLLOW-UPS line).
6. Monthly (step 5b): rebuild the odds model, the value model and the hype reference pool in the
   pokeca-chart tab (`odds_model_builder.js`, `value_model_builder.js`). Weekly on Mondays (step 6b):
   look for newly announced releases and add them with `events.py`.

`add_snapshot.py` is the common publishing step for every check:

1. normalizes field names and warns about a stale timestamp or a changed card list;
2. refuses byte-identical duplicates and leaves out cards in `removed_cards.json`;
3. **carries forward** each card's `analysis` (tiers, peak, verdict, sell tiers, DIY fields) and
   population from the previous snapshot, so a routine check never wipes an evaluation
   (`carry_forward_analysis`, `carry_forward_population`);
4. saves `data/snapshots/<YYYYMMDD-HHMM>.json` and appends it to `manifest.json`;
5. logs limit-odds forecasts on full checks (`odds_model.log_for_snapshot`) and rebuilds
   `history.json` and `sales.json`, which in turn updates `predict.json` (`predict.update`) and `calls.json`
   (`build_calls.build`). `build_history.py` caches each snapshot's contribution in
   `data/incoming/history-cache.json` (keyed by file size and mtime, `CACHE_VERSION`), and `build_calls.py`
   reads the same cache, so a rebuild takes about half a second however many snapshots there are. It refuses a `collected_at_jst` without a time and adds `+09:00` when the offset is
   missing (a date-only timestamp is read as midnight by Python and 09:00 JST by browsers);
6. commits and pushes. The deploy Action publishes the site.

### Quick check (any later run that day)

`pricecheck/scripts/snkrdunk_quick.js` runs once in a SNKRDUNK tab: it opens every card's product
page in a hidden iframe and returns one compact line per card
(`<id> f<favorites> p<PSA10 ask> a<A ask> P<sales> A<sales>`, codes in the script's header).
`python3 scripts/quick_update.py -` decodes them (`decode_compact`), starts from the latest snapshot
and replaces only what a quick run measures (lowest asks, recent sales, favorites). Everything else
is carried and stamped `listings_as_of` / `population_as_of` / `as_of`; the site shows those stamps as
small "as of 9/26 15:15" labels (`asOfHtml`). A card whose page didn't load gets a `quick_note`. Then it
hands off to `add_snapshot.py`, and ends with the follow-ups (evaluations, sealed info).
`scripts/check_status.py` says which mode the next check should be.

### Other ways data changes

- **Evaluation.** `apply_analysis.py` merges new tiers, peak, verdict and sell tiers into the
  **latest** snapshot (matched by URL, name or set code; it refuses to guess on ambiguous names). It
  stamps `verdict.written`, validates `predictions`, rebuilds history and calls, then commits and pushes
  (during a price-check run it leaves the push to `runclock.py end`). It warns when a reasoning text states a
  chance ("24% for a listing at …") that isn't also a prediction.
- **Stories, insights, events, models:** their own scripts (section 11), all called from the full check.

### From the site (through GitHub issues)

| Button on the site | Issue form (label) | What processes it | Result |
|---|---|---|---|
| ✓ Bought it / + Bought another | `bought.yml` (`bought`) | Action `purchases.yml` → `log_purchase.py` | holding `p<issue#>` in `holdings.json` |
| ✓ Sold it | `sold.yml` (`sold`) | same | item moved to `sold[]` as `x<issue#>` |
| Remove / Undo sale | `remove-purchase.yml` (`remove-purchase`) | same | `p…`, `s…`, `u…` removed; `x…` put back |
| + Add sealed product | `sealed.yml` (`sealed`) | same | product `s<issue#>` in `sealed[]` |
| Pulled one of these? / + Add pull | `pull.yml` (`pull`) | same | pull `u<issue#>` under its product |
| Add / Change SNKRDUNK link | `sealed-link.yml` (`sealed-link`) | same | product's `url` set |
| Grading info / Mark N as sent (PSA submission planner) | `grading-info.yml` (`grading-info`) | same | `sent`, `registered` (PSA's registration date: return dates count from it, else ~1 week after `sent` is assumed, `PSA_REG_LAG`), `tier`, `gem_rate_pct` (and a pull's status), for one card or several |
| Save to all devices (limit) | `set-limit.yml` (`set-limit`) | Action `limits.yml` → `set_limit.py` | `limits.json` |
| Save to all devices (sell target) | `set-sell-target.yml` (`set-sell-target`) | same | `sell_targets.json` |
| Save to all devices (You vs model) | `predict.yml` (`predict`) | Action `predictions.yml` → `set_predictions.py` | answers in `predict.json` |
| Remove card / Restore | `remove-card.yml` / `restore-card.yml` | Action `cards.yml` → `remove_card.py` | `removed_cards.json` |
| + Add card / + Track it (Scout) | `add-card.yml` (`add-card`) | the **next price check**, quick or full → `card_requests.py`, then the evaluation in the same run | added to `tracked_cards.json` and `eval_queue.json`, issue closed; tiers and verdict applied by that run |

Every Action script redeploys the site, then comments on and closes the issue. If a form can't be
read, it comments the reason and leaves the issue open; editing the issue re-runs it. Only issues
opened by the repo owner are processed.

Two details worth knowing:

- A push made *by* an Action with its built-in token does not trigger other workflows (a GitHub rule
  against endless loops). So the Action scripts start `deploy.yml` themselves through the GitHub API
  (`/actions/workflows/deploy.yml/dispatches`) after pushing.
- GitHub silently drops a form's label if that label doesn't exist in the repo, and the workflow then
  never runs. So the workflows also match the title the site fills in ("Limit: …", "Sold: …"), the
  scripts infer the label from the title (`issue_labels.labels_of`), and `labels.yml` creates every
  label the forms use and processes any unlabeled issue still open.

---

## 6. The page skeleton: index.html

`index.html` holds almost no content, only empty containers that `app.js` fills.

- **`<aside class="sidebar">`**: logo, `<nav id="nav">` with one link per main view in three
  `.nav-group`s: Buy (Overview, Watching, Scout, Budget planner), Own (Holdings, Collection,
  Submissions = `#/submit`) and Learn (Market & notes, Track record, You vs model, Stories, Tables),
  and the snapshot picker `#snapshot-select` plus "+ Add card". Each nav
  link has `data-view="..."` (used to highlight the current one) and an empty
  `<em data-count="...">` badge filled by `updateCounts()`.
- **`<header class="mobile-bar">`**: the phone header with its own picker
  `#snapshot-select-m`. The two pickers are kept in sync.
- **`<main>`**: `#page-title` / `#page-sub` (set by `applyRoute`), `#back-link`, `#page-aside`
  (the Holdings totals), then **one `<section class="view" data-view="...">` per page**: overview,
  collection, watching, holdings, planner, record, scored, scout, predict, stories, market, tables,
  more, compare, duel, combos, rate, submit and card. Only one is visible at a time.
- **`<nav class="tabbar">`**: the phone bottom bar (Overview, Collection, Holdings, Planner, More).
  The **More** view lists Scout, Stories, You vs model, Watching, Track record, Market & notes, Tables
  and + Add card.
- At the end: `<script src="assets/app.js?v=20261009v11">`. The `?v=` part is a cache
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
| formatting helpers | `fmtYen`, `fmtYenShort`, `fmtPct`, `fmtDateJST`, `asOfHtml`, `escapeHtml`, `dirClass` | turning numbers into display text |
| data loading | `fetchJSON`, `OPTIONAL_DATA`, `idb`, `cacheRead`, `cacheWrite`, `loadFreshBundle`, `showBundle`, `init`, `loadIndex` | fetching, the IndexedDB cache, startup |
| removing cards from the tracker | `withoutRemoved`, `reconcileRemovals`, `removeBtnHtml`, `removedListHtml` | Remove card / Undo / Restore |
| derived-value helpers | `getRep`, `depthInfo`, `rawPrice` (raw A-rank price; `scripts/raw_price.py` is the Python twin), `computeDiyEconomics`, `computeGauge`, `zoneOf`, `liveTagOf`, `displayTagFor` | the core calculations |
| event rule | `upcomingEvents`, `activeEvents`, `eventFor`, `heldByEvent`, `renderEvents` | release-calendar logic |
| PSA grading backlog | `psaBacklog`, `renderPsaBacklog`, `psaBacklogLine` | Market page panel and the one-line status on Submissions; display only, the projection comes from the data file |
| (correction rule) | `correctionState`, `heldByCorrection` | market-correction logic |
| (rally rule, index breadth) | `rallyState`, `indexBreadth` | rally flag; how broad the My-tier index's move is |
| my limit prices + buy signals | `store`, `getLimit`, `setLimit`, `reconcileLimits`, `limitFormUrl` | limits |
| sell targets and sell signals | `getTarget`, `setTarget`, `reconcileTargets`, `suggestedTarget`, `sellRowHtml` | sell targets for cards you own |
| owned cards: position, sell tiers, sell verdict | `ownedOf`, `breakEven`, `sellState`, `sellChip`, `sellGaugeHtml`, `positionStats`, `ownedVerdict`, `sellBarHtml` | the sell view |
| odds of a listing reaching a price | `touchOdds`, `zShare`, `fmtOdds`, `limitOddsHtml`, `lowestAsk`, `limitHit` | limit-odds model |
| purchases | `holdingCost`, `heldPrice`, `holdingsFor`, `boughtFormUrl`, `openBoughtDialog`, `removeFormUrl` | the Bought it dialog and links |
| hype exposure | `hypeOf`, `hypeHtml` | the Hype exposure panel |
| today's call | `liveVerdict` | the verdict headline computed from the shown snapshot |
| render: market strip | `volTrendOf`, `renderMarketStrip` | pokeca-chart cells on the Market page |
| render: My-tier index | `customIndexStats`, `renderCustomIndex`, `drawIndexChart` | Market page index chart |
| tier review status + card vs market | `tierReview`, `tierReviewHtml`, `cardPriceAt`, `marketMove`, `vsMarketHtml` | "Review due" and "Vs. the market" |
| insights | `INSIGHT`, `marketGap`, `insightsFor`, `writtenInsight`, `quietChecks`, `hasInsight` | "What stands out" |
| Stories | `storyOf`, `storyHtml`, `renderStories` | Story tab and Stories page |
| You vs the model | `predWeeks`, `predScore`, `predQuestionHtml`, `renderPredict` | weekly prediction game |
| picture viewer | `openLightbox`, `closeLightbox` | tap a picture to see it big |
| Scout | `scoutList`, `scoutPicks`, `scoutCardHtml`, `renderScout` | Scout page |
| slab premium | `premiumOf`, `snkrPremium`, `premiumHtml`, `insightsHtml` | DIY tab premium panel |
| render: market today | `computeAutoFlags`, `todayItems`, `renderToday` | Market today chips on the overview |
| app shell: views + routing | `VIEWS`, `cardId`, `hasMarket`, `parseRoute`, `applyRoute`, `viewSubtitle`, `openCard`, `updateCounts` | navigation |
| page transition | `heroTransitionFor`, `onHashChange` | collection ⇄ card page animation |
| card photos | `measureTrim`, `applyTrim`, `trimImages` | making cards fill their frames |
| render | `render()`, `renderLazy`, `scheduleLazy` | redraws everything |
| sorting | `SORTS`, `sortCardsBy`, `setSort`, `TABLE_SORTS`, `setTableSort` | sortable columns |
| render: key numbers | `renderKpis`, `renderMoney` | index strip and Your money on the overview |
| should I grade this? | `GRADE_TIERS`, `gradeCopies`, `gradeCalc`, `gradeLineHtml`, `gradePanelHtml` | grading calculator for raw copies |
| PSA submission planner | `rawCopies`, `submitCalc`, `submitFormUrl`, `renderSubmit` | #/submit |
| sealed product | `pullValue`, `sealedValue`, `sealedHtml`, `holdingsTotals`, `renderHoldingsAside` | Sealed section and Holdings totals |
| sold items | `soldFormUrl`, `soldPrefill`, `soldTotals`, `soldHtml` | Sold section |
| portfolio value over time | `basisV`, `markPsa`, `markRaw`, `portfolioSeries`, `drawPortfolioChart`, `rawHoldingCols`, `renderHoldTabs`, `nextStepHtml`, `renderPortfolio` | Holdings chart (with the My-tier benchmark), the Singles / Sealed / Sold tabs (`psa10.holdTab`) with a link to the submission planner, and the singles list with each one's next step (its sell signal, or grade / at PSA for a raw copy) |
| how your bought cards move | `histPoints`, `tiersOn`, `holdingTiming`, `holdingTimingHtml`, `timingSummary` | vs the market since purchase, entry timing |
| overview list + drawer | `zoneBarHtml`, `renderOverviewList`, `renderDrawer`, `drawerHtml`, `cardNavHtml`, `renderCardPage` | Overview and card page |
| trading activity ("heat") | `saleAgeDays`, `salesPerDay`, `heatOf`, `heatChip`, `renderHeat` | Activity labels |
| (cost basis helpers) | `priceChangeAgo`, `priceChangeLast`, `limitGap`, `rawCopyBasis`, `holdingValue`, `holdingPaid`, `boughtGap` | Limit column, owned positions |
| display case | `ownsCard`, `rawOnlyStats`, `renderCollection`, `renderWatchPanel` | Collection, Watching |
| card detail | `buildCardDetail`, `wireCardDetail` | card page and drawer |
| budget planner | `plannerState`, `renderPlanner` | Planner |
| upside and tier check | `sellNet`, `cardAgeMonths`, `upsideDist`, `profitOdds`, `upsideHtml`, `tierCheckHtml` | value model |
| combination finder | `CB_CATS`, `cbSimPrep`, `cbComboUpside`, `comboSearch`, `renderCombos` | #/combos |
| rate my portfolio | `renderRate`, `rtKeepHtml` | #/rate |
| track record | `renderTrackRecord`, `renderScored` | Track record, Scored calls |
| limit controls | `wireLimitControls`, `openLimitEditor`, `limitSyncHtml` | editing and dragging limits |
| price history | `getCardPriceHistory`, `loadSales`, `salesRolling`, `buildPriceHistoryHtml`, `supplyDemandHtml`, `buildGradeDetail`, `buildDistribution` | History tab (prices, sales, supply & demand) and Listings tab |
| interactive charts | `chartSlot`, `mountCharts`, `drawLineChart`, `drawBarChart`, `wireHover` | SVG charts |
| head to head / budget duel | `relation`, `renderCompareBar`, `renderCompare`, `tapeHtml`, `raceHtml`, `ladderHtml`, `renderDuel`, `drawMultiChart` | comparing cards |
| render: tables | `renderTables`, `buildDiyTable`, `buildComparisonTable` | Tables page |
| end | the test hook, `loadCardRequests`, `init()` | tests, pending-issue notices, start |

### Startup, step by step

1. The browser loads the HTML and CSS, then runs `app.js`. The last lines call
   `init()` and `loadCardRequests()`.
2. `init()` registers the `hashchange` listener, reads the cached bundle (`cacheRead`: the complete data from
   your last visit, kept in IndexedDB under `psa10.cache.v2`; localStorage only where IndexedDB isn't available)
   and **immediately starts** `loadFreshBundle(cached)` (network) without waiting for it. The bundle is about
   0.7 MB and grows with every check, which is why it moved out of localStorage (about 5 MB on Safari).
3. If a cached bundle was found, `showBundle(cached, false)` draws the site right away and
   the body gets the class `is-updating`, which shows the thin yellow bar at the top.
4. `loadFreshBundle()` fetches `manifest.json`, all optional files (`OPTIONAL_DATA`: holdings,
   holdings prices, portfolio history, sell targets, calls, custom index, events, history, limits,
   odds model, insights, premium, scout, predict, stories, value model, removed cards, hype; `sales.json`
   is not part of it, it loads when a History tab opens)
   **and** the two snapshots the cached manifest names, all in parallel. Only if the fresh manifest
   names newer snapshots are those fetched afterwards. Each fetch uses `{cache: 'no-cache'}`: the
   browser asks GitHub "has this changed?" and gets a tiny "304 Not Modified" answer if not.
5. When fresh data arrives, `init()` compares it with what's shown. If anything changed, and you
   haven't picked a different snapshot in the meantime, it calls `showBundle(fresh, true)` and saves
   the fresh bundle as the new cache (`cacheWrite`, which also removes the old localStorage copies).
6. `showBundle()` copies each file into `state`, fills both snapshot pickers, sets up sorting
   (once), drops removed cards (`withoutRemoved`), and calls `render()`. Only with fresh data does it
   reconcile local limits, sell targets and pending removals against the synced files.

### render(): the heart of the app

```js
function render() {
  renderMarketStrip(data); renderCustomIndex(); renderEvents(); renderHeat();
  renderKpis(data); renderToday(data, state.previousData); renderInbox(cards);
  renderRecapCard(); renderInbox(cards); renderOverviewList(cards); renderDrawer();
  lazyPending = { holdings, collection, watching, planner, grails,
                  record, scout, predict, stories, tables };   // built when opened or when idle
  updateCounts(); applyRoute(); trimImages(document); scheduleLazy();
}
```

**Every view is re-rendered from `state` every time.** When something changes (a new limit, a
different snapshot), the code updates `state` or localStorage and calls `render()` again. It's
simple and hard to get out of sync. The pages that aren't on screen at first (Holdings, Collection,
Watching, Budget planner, Grails, Track record, Scout, You vs model, Stories, Tables) are built when first opened (`renderLazy`, called from `applyRoute`)
or in the background once the browser is idle (`scheduleLazy`), so the first paint doesn't wait for
them. Some small interactions redraw only their own piece: `renderPlanner` after ticking a checkbox,
`setSort` the list and the collection, `renderPredict` after locking in an answer.

Heavier computations are memoized per **data epoch**: `setShownData` bumps `dataEpoch` whenever different data is
shown, and `portfolioSeries`, `recapData`, `insightsFor`, `heatOf`, `marketGap` and the My-tier lookups keep their
result until it changes. `history.json` lookups use pre-parsed times and a binary search. The Holdings chart isn't
drawn while Holdings is hidden, and charts in closed card-page tabs aren't measured (both would force a layout).
If you add a computation that depends on data, key its cache on `dataEpoch` too.

### Routing

`parseRoute()` reads `location.hash` → `{view, arg}` (unknown views fall back to
`overview`). `applyRoute()` then:

- hides every `.view` section except the matching one and builds it if it's still lazy;
- highlights the nav link. For a card page that's the view it was opened from (`state.cardFrom`,
  which also drives the "Back" link). Sub-pages have a parent (`PARENT`: compare → collection;
  duel, combos and rate → planner; scored → record) and get a Back link to it;
- for `#/card/<id>`, finds the card with `findCardById()` and draws it with `renderCardPage()`;
  for a sub-page, calls `renderCompare`, `renderDuel`, `renderCombos`, `renderRate` or `renderScored`,
  which return the title and subtitle;
- sets the page title, subtitle (`viewSubtitle`), the Holdings totals (`renderHoldingsAside`) and the
  browser tab title.

`openCard(card)` decides what clicking a card does. On a wide screen (≥1200px,
`DESKTOP` media query) on the Overview, it fills the side drawer. Everywhere else,
it navigates to `#/card/<id>`. Going from the Collection to a card page and back animates the slab
with the browser's View Transitions API (`onHashChange`, `heroTransitionFor`); browsers without it,
and Reduce Motion, switch instantly.

**Snapshot picker.** Choosing an older check calls `loadIndex(i)`, which fetches that
snapshot and the one before it (for "since last check" comparisons), then `render()`.

---

## 8. Feature by feature

### Which price is "the price"?

`getRep(card)` returns `analysis.representative_price` if an evaluation set one
(usually sales-confirmed), otherwise the lowest PSA10 ask. Zones, verdict pills,
off-peak %, owned positions and history use it. **Limits, signals, the odds model and the
combination finder use `lowestAsk(card)` instead**, because a limit means "a listing I could buy
right now is at or below my number". If a number looks "wrong" on the site, first check which of
the two it uses.

**Raw A-rank price** (`rawPrice`, since 2026-10-08): the median of the last 5 one-copy A-rank sales
from the past 30 days, never below the lowest A-rank ask; with fewer than 3 such sales, the lowest
ask. The cheapest raw listing is often a copy that won't grade and doesn't sell. It's used for the
DIY cost, the grading calculator, raw pulls and raw singles, the "raw A" line under every price and
the Watching page. `scripts/raw_price.py` is the same rule in Python (history.json's `r[4]`,
`holdings_prices.json`).

### Verdict pill (Buy / Watch / …)

`displayTagFor(card)` decides the pill. The rules, in order:

1. No `analysis` → no pill ("No tiers").
2. A written `verdict.tag` of `defer` always wins (a deliberate "hold regardless").
3. Otherwise the **live zone** from `liveTagOf(tiers, getRep(card))`:
   ≤ definitely_buy → Definitely buy, ≤ buy_upper → Buy, ≤ ceiling → Watch, above → Don't buy.
4. A live **Buy** is shown as **Watch** while the correction rule or an event rule is on.
   Definitely-buy is never downgraded.

So the pill updates with every price check without a new evaluation. The verdict box on the card
page leads with **today's call** (`liveVerdict`): a headline and a few lines computed from the shown
snapshot (zone, change since the last check and over 7 days, the last week's sales, the tiers, your
limit and its odds). The written analysis sits below it, folded, dated (`verdict.written`) and at the
price it was written for. When the price has moved 5%+ from that price, a note says the next full
check rewrites it (`review_due.py --text`, FULL-CHECK step 8g).

### Correction rule and event rule

- `correctionState()` compares the My-tier index today with 30 days ago
  (falling back to pokeca-chart's month change if the series is too short). At
  −10% or worse (`CORRECTION_PCT = 10`), the rule is on. The result is cached per
  snapshot.
- `activeEvents()` lists dated, major events from `events.json` that are 0–3 days away
  (`window_days`). `eventApplies()` checks the scope: `"all"` or a list of set codes
  matched against the card's code.
- Both feed `displayTagFor` and produce Market today chips (`renderToday`) and card notes
  (`heldByEvent`, `heldByCorrection`). The evaluation skill applies the same rules,
  so the site and the written verdicts agree. `scripts/event_study.py` measures on the
  tracker's own checks whether prices really dip around releases.
- **Rally rule** (`rallyState`): the counterpart for a fast rise, on while the My-tier index is up
  `RALLY_PCT` (10%) or more over `RALLY_DAYS` (7). It's a flag only: a banner (with the index's breadth: how
  many of its cards rose and how much of the move the top 3 made), a "Rally rule on" chip on the Market page,
  and a reason on owned cards near their Take-profit zone. Limits set before a rally are less likely to fill
  soon (the odds assume no trend), and a card still in its Buy zone is lagging. No pill or signal changes.

### Zone bar and gauge

- The **zone bar** in lists (`zoneBarHtml`) is four coloured `<i>` segments whose widths
  are percentages of a scale (the peak or ceiling × 1.08). A white tick marks the price
  and a gold tick marks your limit. For a card you own it's the sell bar instead (`sellBarHtml`):
  your cost, the price, your sell target and the sell zones.
- The **gauge** on the card page (`computeGauge` + the `gaugeHtml` block in
  `buildCardDetail`) is one CSS `linear-gradient` with hard colour stops at each
  tier, plus absolutely positioned markers for the price, the peak and your limit.
  The limit marker can be dragged (`wireLimitControls`: pointer events convert the
  x position back to yen, rounded to ¥500). Owned cards get `sellGaugeHtml`.

### Limits and sell targets: local first, then synced

Both work the same way. There are two stores:

- localStorage (`psa10.limits`, `psa10.sell`): edits made in *this* browser. A value
  of 0 means "cleared here".
- `state.syncedLimits` / `state.syncedTargets` from `data/limits.json` / `data/sell_targets.json`:
  values saved to all devices.

`getLimit(card)` prefers the local edit, otherwise the synced value.
`limitSync(card)` says which one applies, and `limitSyncHtml` shows "Only on this
device · Save to all devices ↗". That link (`limitFormUrl`) opens the pre-filled
`set-limit` issue. Once the Action has updated `limits.json` and the site reloads,
`reconcileLimits()` sees that the local and synced values agree and deletes the
local copy. It only runs against fresh data, never against the cached copy. It also deletes this
browser's local limit for every card you own, because `log_purchase.py` removes the synced one when a
purchase is logged (`prune_owned_limits`).
A limit stops counting once you own the card (`limitHit` checks `ownsCard`: singles from `holdingsFor`, which
leaves out copies that came back below a 10, plus pulls from `pullsFor` with status raw, grading or PSA10); the
sell target takes over. A pull counts as a raw copy you own everywhere: the site (Needs you, the lists,
Collection, card page, recap, compare views and Tables) and the scripts (`review_due.py`, `outliers.py`, `recap.py`,
`eval_context.py` all use `log_purchase.owned_urls`). It gets no sell math, because it has no purchase price. `suggestedTarget` offers a starting target: just under the peak, or +25% on what you paid.

### Limit odds

`touchOdds(card, price)` answers "what's the chance a listing reaches ≤¥X within
30/90 days?". It computes the log-distance from today's lowest ask, divides by the
card's own volatility from `odds_model.json` (or the pooled value for cards without
history), looks that up in empirical curves (`zShare`) and applies calibration
factors. No trend is assumed. `scripts/odds_model.py` does the same maths in Python, so logged
forecasts match what the site showed. `limitOddsHtml` also shows the evaluation's own stated
odds for a nearby price, as a cross-check. The same odds appear in the limit editor while you type,
in the Tier check, the drawer, the budget duel, the combination finder and You vs the model.

### Needs you (buy signals, sell signals, reviews)

`computeSignals(cards)` collects, in order: a lowest ask at or below your limit (0), Definitely-buy (1) and Buy (2). Cards you
own (`ownsCard`, pulls included) never give limit or Buy signals; `tests/test_rules.py` checks that on every snapshot. `inboxItems` puts those first, then every owned card whose `sellState`
isn't Hold (strongest first), then watched cards whose `tierReview` is due. `renderInbox` shows them;
`onDeck` lists the cards closest to their next signal (gap from the lowest ask down to your limit, or
without a limit to its Buy line; owned cards: gap up to Take profit). Buy signals not seen on your previous visit get a **NEW** label (their keys
are remembered in `psa10.seenSignals`, and only while viewing the latest snapshot).

### Market today chips ("Automatically detected…")

`todayItems` makes one chip each for the event rule (or a "Coming up" note within 14 days), the
correction rule, the rally rule, any hand-written `banners` from the snapshot JSON, and
`computeAutoFlags()`. Those flags compare with the previous snapshot: depth down 30%+, a zone
crossing, or favorites ±5%. `renderToday` draws the chips; clicking one shows its full text
underneath (`state.todayOpen`, one at a time).

### Focus watch (added 2026-10-18)

For a card whose buy window you don't want to miss. `python3 scripts/focus.py add <id> --until YYYY-MM-DD --note "…"`
puts it in `data/focus.json`; `focus.py remove <id>` takes it out. On every publish `build_history.py` calls
`focus.build()`, which writes `data/focus_report.json` from `history.json`, `sales.json`, the latest snapshot's
listings and `limits.json`. `full_update.py` and `quick_update.py` print it as a `FOCUS WATCH` block after
publishing, and the procedures put those lines in the run's chat message, so every check reports the card. Quick checks also re-read a focus card's PSA10 listings (`jsrun.py` writes its id as `<id>:L` in the `snkrdunk_quick` call; `quick_update.py` saves the `L=` token as a fresh listings read), so its book depth updates on every check, not only on full checks.

Status, first that applies (thresholds at the top of `focus.py`): **Buy window** (lowest ask ≤ target; target =
your limit, else the Buy tier) · **Near limit** (ask within 2% of the target, or a sale at/under it in the last
24 h) · **Turning** (ask ≥3% above its 7-day low and the 24 h sales median ≥ the prior week's) · **Drifting down**
(ask ≥2% under its level 7 days ago) · **Flat**. Flags: sales at/under the target, the cheap end thinning (asks within
3% of the lowest down ≥40% vs the previous fresh listings read), a deep wall (≥10 within 3%), the event-rule window
for the card's set, the focus ending. The Overview panel (`renderFocus`) sits above Needs you and leads with **book depth** (`focusDepthHtml`,
added 2026-10-18 evening): the count of the 20 cheapest asks within 3% of the lowest, its change vs the previous
fresh listings read, a deep (≥10) / normal / thin (≤4) reading, a ladder of the 20 asks in 0.5% steps with the 3% zone
and the target, and the count across the last 8 reads (`depth.trend`). It always shows the
latest check, draws the last 10 days of lowest asks against the target, and marks a status that changed since your
last visit NEW (localStorage `psa10.focusSeen`). It's a heads-up, not a forecast: verdicts and the odds model stay
the judges of price.

### Overview list: Owned and Watchlist

`renderOverviewList` sorts the cards with a market once (`sortedMarketCards`, the shared sort) and
splits them by `holdingsFor`: **Owned** (columns: price with raw A underneath, sell zones, vs cost,
7D with 30D underneath, sell signal with activity) and **Watchlist** (price, buy zones, limit and
the gap to it, 7D, verdict with activity). The All / Owned / Watchlist tabs are remembered in
`psa10.ovFilter`; each section draws its own column heads (`wlHeadHtml`), which sort both sections.

### Tier review, tier check and "Vs. the market"

- `tierReview(card)` reads `history.json → tiers[url].since` (when the tiers were last set or
  re-confirmed). It flags **Review due** after 30 days, a 10% market move since then, a Definitely-buy
  line that's a long shot (under 10% in 90 days, tiers at least 7 days old), or a young card (under
  9 months, tiers at least 14 days old). `scripts/review_due.py` applies the same rules for the full
  check.
- `tierCheckHtml(card)` shows the odds of a listing reaching the Definitely-buy and Buy lines in 30
  and 90 days, with a warning for young cards (the value model's age curve).
- `vsMarketHtml` compares the card's 7- and 30-day change with the market's
  (My-tier index, or pokeca-chart) to tell a card-specific drop from a market-wide one.

### What stands out (insights)

`insightsFor(card)` looks for numbers that stand out: the card moving 8+ points differently from the
market over 7 days (12+ over 30), the lowest ask 8%+ away from the median of the last week's sales,
an 8%+ jump since the last check, trading up or down 50%+ on a week ago, the ask within 5% of your
limit, or the slab premium 20%+ from its norm. Each finding cross-checks the other evidence (sales,
trading, depth) before saying what it probably means, and owners get seller wording. When nothing
fires, `quietChecks` lists the same checks with today's values ("Nothing unusual"). Strong findings
(score ≥ 1.5) put an "Insight" star on the overview row. `scripts/outliers.py` applies the same rules
in Python; the full check (step 7b) writes a short analysis for its top cards with
`scripts/set_insight.py` into `data/insights.json`, which replaces the computed findings on the card
page (not for cards you own, which `outliers.py` therefore leaves out). The thresholds are in `INSIGHT` / `PREM_FLAG` (JavaScript) and `T`
(Python); change both together.

### Hype exposure

`hypeHtml(card)` reads `data/hype.json`: how much of a 12-month hype run the card still carries
(its change minus the market's) and how actively it trades, each ranked against about 250 modern
PSA10s, combined into Low / Medium / High. The text says what that has meant in past rising and
falling markets (from `hype.evidence`, the crash-resilience backtest). It describes how hard a card
swings *with* the market, not whether it's a buy. High cards get a "High hype" chip on the overview.

### Slab premium (DIY tab)

`premiumHtml(card)` shows how many times the raw A-rank price a PSA10 costs. Three readings:
SNKRDUNK's lowest asks and recent sales (`snkrPremium`, from the card itself; the per-check line
comes from `history.json`'s `"r"` field), and pokeca-chart's 18-month history with the card's own
6-month norm (`premiumOf`, from `data/premium.json`). When the pokeca premium is 20%+ from its norm
(`PREM_FLAG`, same threshold in `scripts/outliers.py`), "What stands out" adds a stretched/compressed
finding. Its score is capped at 1.2 because the tested effect is small (project doc
`raw-vs-psa10-leadlag-2026-09-28`): it never shows the overview's Insight star on its own.

### Upside (value model)

`upsideHtml(card)` shows a weak / typical / strong price in 12 and 24 months and the chance of
selling at a profit after SNKRDUNK's fees (`sellNet`: 9.5%, ¥200/¥300 fixed fee, ¥1,000 shipping).
`upsideDist` combines every 2022–26 market move with every card-vs-market move from
`value_model.json`, centred so the typical outcome is no change (`vmShift`), scaled lightly by the
card's own swing and adjusted by the age curve for cards under 12 months. A second figure shows the
odds if the market repeats 2022–26. For a card you own it starts from today's ask and is measured
against your cost. The drawer's "Hold value" tile is the 24-month chance of a profit.

### Trading activity ("heat")

`salesPerDay(sales)` turns SNKRDUNK's "when" strings (`3時間前`, `2日前`,
`2026/09/14`) into ages in days (`saleAgeDays`). It then divides the number of
sales by the age of the oldest. `HEAT_LEVELS` maps that rate to Hot ≥5, Active ≥3,
Slow ≥1.2 and Cold per day; raw A-rank uses `HEAT_LEVELS_RAW` (40/15/5).
`build_history.py` stores the same rate per snapshot, so the site can show
"a week ago". `renderHeat` builds the table on the Market page, including how many days of sales
the cheap listings would cover.

### Overview list and sorting

`renderOverviewList` draws one `<a class="wl-row">` (`wlRowHtml`) per card with a PSA10 market, in
the Owned or the Watchlist section: slab, name (with Insight and High hype chips), price (with the
raw A-rank price under it for a card you own), zone bar, Limit / Vs cost, 7D with 30D under it
(`trendCell`; the change since the last check is in its tooltip and the Sort menu), and the verdict
(or sell chip, plus the Limit chip) with the activity chip under it. Tier reviews moved to
Needs you. It uses `display: grid` in CSS, so each `<span>` is a column.

The **Limit** column depends on the card: for a card you watch it's your limit with the distance to
the lowest ask (`limitGap`); for a card you own it's the PSA10 price against your cost basis
(`boughtGap`): the price paid for a slab, or for a raw copy its DIY cost with the price you paid,
(raw paid + grading & shipping) ÷ gem rate (`rawCopyBasis`).

Sorting uses `SORTS`: each entry has a `label`, a default direction `dir`, a function `v(card)`
giving the value to sort by and optionally a `group`. `sortCardsBy` puts cards without a value last,
keeps groups apart (Limit: cards you watch first, then cards you own) and breaks ties with the
"signals first" rank. Header buttons (`.wl-head [data-sort]`) and the phone's Sort menu both call
`setSort`. A third click on the same column returns to the default. The choice is saved in
`psa10.sort` and also orders the Collection and the card page's Previous / Next links.

**To add a sortable column:** add an entry to `SORTS`, a
`<button data-sort="yourkey">` in the `.wl-head` in `index.html`, a matching cell in
`renderOverviewList`, and a width in the `.wl-row, .wl-head` `grid-template-columns`
rules in `style.css`.

### Card page and drawer

`buildCardDetail(card, prevCard, mode)` returns the whole detail as one HTML string.
`mode` is `'drawer'` (side panel) or `'page'` (full card page).

- **Card page:** the hero (slab picture, price, off-peak, change since the last check, tags, actions:
  Bought it / Bought another, Sold it, SNKRDUNK, Remove card) and up to six tabs:
  - *Overview*, decision first. The **Decision** box (`.cd-decide`) holds the verdict with its
    pill (for a card you own, the sell verdict from `ownedVerdict`), the gauge, and the limit row with
    its odds (a card you own: the sell-target row). Then, for a card you own, your
    position (`positionHtml`: paid, worth, after selling costs, break-even); the grading panel for raw
    copies; "What stands out"; the **Facts** (the stat tiles). Last come folded sections
    (`foldHtml`, a `<details>`): *Buy tiers* (tier review and tier check; opens by itself when a
    review is due; not shown for a card you own), *Vs. the market* and *Hype exposure*.
  - *Story* (when `stories.json` has one), *History* (loads lazily on first open:
    `renderPriceHistoryInto`, see "Price history, sales and supply & demand" below), *Listings*
    (distribution, sales sparkline and list for PSA10 and raw A),
    *DIY* (buy the slab vs grade it yourself, plus the slab premium; hidden when you own a slab) and
    *Upside*.
  - `cardNavHtml` adds Previous / Next links (← → keys) in the overview's sort order.
- **Drawer** (`drawerHtml`, Overview on wide screens): only what's needed to decide "act or wait":
  the verdict line, a review-due note, the gauge, an insight link, four stat tiles (your limit or
  your position, moves, off peak, hold value) and the actions.

`wireCardDetail` attaches the tab switching (remembered in `state.cardTab`), the limit and sell
controls, the lightbox and the charts.

### Price history, sales and supply & demand (History tab)

- The price line is the PSA10 price at each check (`history.json` `p`). Over it, `buildPriceHistoryHtml` draws
  every one-copy sale from `data/sales.json` as a small dot and their rolling median (`salesRolling`: at the end
  of each day, the median of the sales in the `SALES_MED_DAYS` (7) days before, with at least 3) as a dashed
  line: steadier than the lowest ask, which jumps when one listing appears or sells. `sales.json` is built by
  `build_history.py`: each check shows the last 20 sales, oldest first; consecutive lists overlap, so a new list
  is aligned with the previous one (same prices in order, at times both timestamps allow) and only the sales
  after the overlap are added. Single sales outside the price line's range are left out so one odd sale can't
  squash the chart.
- `supplyDemandHtml` adds four small charts and a stat row from `history.json`: PSA10 population (`n`; supply,
  a fast rise = a wave of new slabs), SNKRDUNK favorites (`f`; demand), cheap listings (`q`: within 15% of the
  lowest ask, of the 20 cheapest read on full checks) and how many days of sales they would cover (`q` ÷ `h`).
  `f` and `n` are stored only when they change, so `histSeries` carries the last value forward (`growth` gives
  the 7- or 30-day change). The card's population tile shows "+N in 7 days" (`popGrowthTxt`). SNKRDUNK's total
  listing count isn't read, only the 20 cheapest.

### Charts

All charts are hand-drawn SVG, with no chart library:

- While building HTML, `chartSlot(cfg)` stores the chart's configuration in a map and
  returns an empty `<div data-chart="ch12">`.
- After the HTML is on the page, `mountCharts(root)` draws each slot at its real pixel
  width (`drawLineChart`, `drawBarChart` or `drawMultiChart`). A `ResizeObserver` redraws it when
  the width changes, for example when a hidden tab is opened. `drawLineChart` takes `overlays`: extra series on
  the same axes, as a line (counted in the y range, shown in the tooltip) or as dots (not counted).
- `wireHover` adds the crosshair and tooltip for mouse, touch and arrow keys.
- The My-tier index chart (`drawIndexChart`) and the Holdings value chart (`drawPortfolioChart`) have
  their own, similar drawing code.

### Card photos that fill the frame

SNKRDUNK's cut-out photos have different amounts of transparent margin.
`measureTrim(url)` loads each image once into a small off-screen `<canvas>` and finds
the bounding box of non-transparent pixels. `applyTrim` then sets three CSS
variables on the `<img>` (`--h`, `--cx`, `--cy`), which the `.card-img` rule in
`style.css` uses to zoom and centre the card. Results are cached in
`psa10.imgTrim.v1`. If the CDN refuses CORS three times, measuring stops for a week
(`psa10.imgTrim.fail`) and images keep a default zoom.

### Collection and Watching

- `renderCollection`: the same sorted cards as tiles with a PSA-slab frame (`slabHtml`), chips,
  7d/30d change, and for cards you own the gain against what you paid (or against your DIY cost for a
  raw-only card, with the raw A-rank line from `rawOnlyStats`). The **Only cards I own** checkbox
  (`psa10.ownedOnly`) filters to singles and pulls you hold. "⇄ Compare two cards" starts the head to
  head pick mode. Below the tiles: "+ Add a card" and the removed-cards list (Undo / Restore).
- `renderWatchPanel`: cards *without* a PSA10 market (raw A-rank price, raw heat, favorites). A card
  moves to the Overview automatically once a PSA10 listing appears, because `hasMarket(card)` becomes
  true.

### Removing a card

"Remove card" on the card page (two clicks to confirm) opens the pre-filled `remove-card` form and
hides the card in this browser at once (`psa10.removing`, expires after 3 days if the form is never
submitted). The Action adds the id to `data/removed_cards.json`; from then on the site hides it,
price checks skip it and `add_snapshot.py` leaves it out. History and analysis stay in old
snapshots, so **Restore** brings it straight back. A card you bought or pulled can't be removed.

### Holdings

The Holdings page has five parts, all valued with today's snapshot:

- **Totals** (`holdingsTotals`, shown in `#page-aside`): total spent (purchase prices, sealed prices),
  worth now, +/− and realized profit from sales. Unpriced sealed products count at cost.
- **Show values** switch (`psa10.basis`): **Lowest ask** (a raw copy at the raw A-rank price), **Recent sales**
  (`markPsa` / `markRaw`: the median of recent one-copy sales, the last week's or the last 5; sealed products and
  cards without sales stay at the ask; the chart uses `history.json`'s sales medians `r[2]` / `r[3]`) or **After
  selling costs** (the ask, `basisV` → `sellNet`). It changes the totals, the lists and the chart together.
- **Value over time** (`portfolioSeries`, `drawPortfolioChart`): worth vs. money spent, with a
  result strip and purchase markers, by Total / Singles / Sealed / Pulls and 30 / 90 days / All
  (`psa10.pfh`). A dotted blue line is the **benchmark**: the same money put into the My-tier index on each
  purchase day (and taken out on a sale day), so "you +¥X" in the header line says whether your picks beat
  simply holding the tier. Tracked cards are valued from `history.json`, untracked cards and sealed products from
  `portfolio_history.json` (at cost before their first reading). Sold items count as the cash received
  from their sale date on.
- **Singles** (`renderPortfolio`): each holding matched to the snapshot by `card_url`. A slab is worth
  the PSA10 price; a raw card (`raw_to_grade`) the raw A-rank price (`holdingValue`), against what was
  paid without grading (`holdingPaid`). A raw single shows three figures (`rawHoldingCols`): raw A-rank
  vs paid, your DIY cost, and the PSA10 ask vs that DIY cost, plus its grading dates (`gradeMetaHtml`).
  Under each single, `holdingTimingHtml` (`holdingTiming`, from `history.json`) shows:
  - **Since you bought:** the card's price change since the purchase day (PSA10 price for a slab, raw A-rank
    price for a raw copy) against the My-tier index over the same days, and the difference in points;
  - **Entry:** where the price you paid sat between the low (0%) and high (100%) of the card's 30 days before
    the purchase (needs 3 checks in that window);
  - for a slab, the **zone it was in that day** by the tiers it had then (`history.json` `tier_log`, `tiersOn`).
  Two summary tiles average them: **Vs. the market** (and how many beat it) and **Entry timing** (and how many
  slabs were bought in a Buy zone). The owned card page shows the same line under its position.
- A **PSA submission planner** link sits under the switch when there are raw copies (see below).
- **Sealed** (`sealedHtml`): boxes, sets and packs. An unopened product is worth its lowest SNKRDUNK
  ask × quantity (`sealedValue`, from `holdings_prices.json`); once a pull is logged it counts as
  opened and only its pulls are valued (`pullValue`: PSA10 price, raw A-rank price or your estimate).
  Chips under each product offer the tracked cards of its set as one-tap "Pulled one of these?".
- **Sold** (`soldHtml`): each sale with cost, price, fees and profit, plus a yearly summary.

The budget (Your money on the overview, planner) counts singles at `holdingCost`: price **plus** grading and shipping
for a raw copy.

### Should I grade this?

For every raw copy of a card (a raw single, or a pull with status raw / grading), `gradeCalc`
compares selling raw now with grading: the expected result is gem rate × net PSA10 price + (1 − gem
rate) × net raw price, minus the grading cost of the chosen PSA tier (`GRADE_TIERS`, built from the one fee
table `PSA_FEES` / `PSA_STD` / `PSA_PRIO` / `PSA_EXP`: Standard ¥9,980 / 100 business days / declared value up to
¥150,000, Priority ¥11,980 / 80 / up to ¥250,000, Express ¥29,980 / 25, each plus ¥2,450 shipping and
handling; `scripts/log_purchase.py`'s `GRADE_FEES` / `PSA_EXTRAS` hold the same values for Python). A copy not
sent yet defaults to the cheapest service whose cap covers its PSA10 price (`psaTierFor`). The gem rate is the card's population rate unless you gave your own on the Grading info
form. "Grade it" when your chance is 10+ points above break-even, "Don't grade" 10+ below, else
"Close call". Once a copy is sent (or was bought to grade), the fee is spent: it only shows the
expected result and the return date (`addBusinessDays`). It warns when the PSA10 price is above
Standard's ¥150,000 declared-value limit.

The grading fee counts as money spent once a copy is sent (or was bought to grade), at the fee of the
service it was sent at, on the site, the widget, sold records and `eval_context.py`. When a copy comes back,
the Grading info form's status records it: **Came back PSA10** sets `condition: psa10`, `graded_from_raw` and
`graded_on` (the copy keeps its grading cost, is valued as a slab from that day and charted as raw before it);
**Came back lower than 10** sets `graded_other` (with the same two fields), and the copy gets no PSA10 position or
sell math. A pull's status changes the same way (`psa10` / `graded_other`). Slabs bought graded refuse grading info.

### PSA submission planner (#/submit)

`renderSubmit` lists every raw copy not sent yet (`rawCopies`: singles bought raw without a send date, pulls
with status raw) with its chance of a 10, PSA10 price (= its declared value), raw A-rank price, the expected
result graded vs sold raw (`submitCalc`, the same sums as `gradeCalc`) and the card page's verdict for sending it
on its own. Tick the cards to send together (by default every priced card that isn't "Don't grade"):

- **Service:** one order uses one service, so **Auto** picks the cheapest whose declared-value cap
  (`GRADE_TIERS[...].cap`: Standard ¥150,000, Priority ¥250,000, Express no known cap) covers the most
  valuable card. A manual choice warns when a card is over the cap.
- **Cost:** grading fee × cards + shipping, insurance and handling **once per order** (an editable estimate,
  ¥2,450 from a 1-card Standard order; the per-order amount for several cards isn't known yet).
- **Back around:** the send date + the service's business days. The date is typed and shown as `YYYY/MM/DD` (a plain text field: browsers show date pickers in their own locale's format); it is stored and sent to the form as `YYYY-MM-DD`. **Expected 10s** and **grading vs selling raw**
  (expected, after selling costs and the order's cost).
- **Mark N as sent** opens one `grading-info` form for all ticked cards (`id` = "p73, p74, u52", the date, the
  service and "Sending it to PSA"); `log_purchase.py` applies it to each (with several ids an empty chance keeps
  each card's own estimate).
- **At PSA now** lists the copies already sent with their return dates.

Ticks, service, date and shipping are kept in this browser (`psa10.submit`). The card page's Grade it? panel
and the Holdings page link here.

### Budget planner, combination finder, rate my portfolio

- `plannerState()` reads `psa10.planner` (budget, price mode, ticked cards, pins, left-out cards,
  finder category). `renderPlanner` prices each card at today's lowest ask or at your limit
  (`mode === 'limits'`), subtracts what's been spent (from holdings) and marks cards that still fit.
  Every change calls `save()`, which stores the new state and re-renders the planner and the overview strip and Your money.
- **Combination finder** (`#/combos`, `comboSearch`): tries every mix of the cards in play (📌 pinned
  ones always in, ✕ left-out and owned ones skipped) and keeps those spending 90–120% of what's left
  of the budget, with no room for one more card. Categories: best overall, best use of budget, most
  cards, best value (below the Buy lines), fewer bigger pieces, biggest upside, most likely to gain,
  and most likely at my limits. The two upside categories run a 2,000-draw simulation per card
  (`cbSimPrep`) with one shared market move per draw, cached in `psa10.cbUp.v2`.
- **Rate my portfolio** (`#/rate/<id>,…`, `renderRate`): the ticked cards scored with the same
  measures and ranked against every combination for the same budget; "Find best match" suggests what
  to add while keeping every ticked card.

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
- **Budget duel:** the planner shows "⇄ Compare N cards" when 2–8 cards are ticked
  (`CMP_MAX_DUEL`). It links to `#/duel/<id>,<id>,…`, drawn by `renderDuel`: today's ask
  and your limit with what's left of the budget, `touchOdds` for your limit, Definitely-buy
  and the Buy line, the DIY comparison, and totals for buying all of them.
- **Colours:** card A/B (and C… in a duel) use `CMP_COLORS`.

### Track record and scored calls

`renderTrackRecord` only *displays* `calls.json`. All scoring (30-day windows,
per-card noise thresholds, two-reading confirmation, Brier scores for the evaluations' stated odds
and for the limit-odds model's logged forecasts) happens in `scripts/build_calls.py` when a check is
published. To change how calls are judged, edit the Python, not the JavaScript. Which cards you
expanded is remembered in `psa10.trOpen`. Since 2026-10-09:

- **Only finished windows are scored.** A Watch can be proven right early (the dip came) but wrong only at the end
  of its 30 days, a Buy the other way round, so counting calls as they're decided would favour one kind. The
  "Buy / Watch calls" tile counts calls whose window is over (`summary.closed`); calls decided early show their
  outcome with "counts <date>" and join the score later (`summary.early`). Each call carries `final`.
- **Stated odds and the model's odds are scored after their deadline** (`final`): "happened" can be known early,
  "didn't happen" only at the deadline. The model's 30-day and 90-day forecasts are scored separately
  (`model_odds.h30` / `h90`), so a logged price counts once in each.
- **Vs. a call on every day** (`summary.baseline`): the same rules applied to a Buy and a Watch call on every day
  for the same cards. In a rising market almost every Buy is "right"; the calls only show skill where they beat it.
- **Return vs. the market:** for each closed call, the card's 30-day change minus the My-tier index's
  (`rel_pts`; `edge_pts` is signed so a good call is positive), averaged per kind next to the same measure for
  any day.

`renderScored` (`#/scored`, from the "Buy / Watch calls" tile) lists the scored right / wrong calls and, separately,
the ones decided early.

### Weekly recap (#/recap and the Overview card)

`recapData(W)` (memoized; `recapDataCalc` does the work) builds any Mon–Sun JST week from `history.json`: each
card's PSA10 price from the last check before the week to its last check in it, the week's low and high, flags
(dipped into the Buy zone by the tiers it had then, at your limit, rose above the ceiling, reached a sell tier),
the three indices, your purchases and the releases in `events.json`. A single reading more than 15% below both
of its neighbours is left out first (`dropLoneLows`, `RECAP_OUTLIER`; the same rule as `OUTLIER` in
`build_calls.py` and `scripts/recap.py`), so one mispriced listing can't produce a "+400%" move. The written part
(headline, what happened, what's ahead) comes from `data/recaps.json`, which the first full check on a Monday
writes for the week that just ended (`recap.py facts` prints the same numbers, `recap.py save`).
`renderRecapCard` shows the latest week on the Overview. Cards you own (bought or pulled, `ownsCard`) are listed under
"Your cards"; the yen figure counts bought copies only, since a pull has no purchase price.

### Stories (#/stories and the card page's Story tab)

`data/stories.json` holds a researched write-up per card (illustrator, what the art shows, its connections, set context, trivia, English release, sources), keyed by SNKRDUNK URL. New cards get theirs in the full check after they're added (FULL-CHECK.md step 8c): `scripts/set_story.py --missing` lists cards without a story, Claude researches them and saves each with `scripts/set_story.py <id>`, which checks the fields and pushes. `storyHtml(card)` renders the Story tab (tap the picture for the big version, `openLightbox`), `renderStories()` the gallery page; tiles open the card on its Story tab.

### You vs the model (#/predict)

Up to ten questions a week about your own cards ("Will a listing drop to ¥X by Friday?"), your odds against the limit-odds model's. `scripts/predict.py` writes them into `data/predict.json` the first time a snapshot is published in a week (it's called from `build_history.py`, so price checks, email alerts and evaluations all trigger it), keeps only questions the model gives 15–85%, freezes the model's odds and resolves questions from the week's snapshots; its docstring has the rules. Answers close Wednesday 23:59 JST, 48 hours before the questions resolve on Friday 23:59 JST. On the page (`renderPredict`) you set a slider and "Lock in": the answer is kept in this browser (`psa10.predict.local`) and the model's odds appear. "Save to all devices" opens the `predict.yml` issue form with your locked answers; `.github/workflows/predictions.yml` runs `scripts/set_predictions.py`, which writes them into `predict.json` (first answer is final; answers after the cutoff or after a question resolved are refused). Scores are Brier scores computed in the browser.

### Scout (#/scout)

Cards you don't track yet that fit your criteria and look cheap. Full checks run `pricecheck/scripts/pokeca_scout.js` on pokeca-chart's card list (about every other day): it keeps modern secret rares (card number above the set size, released 2021+, PSA10 ¥5k–150k; the floor was ¥15k until 2026-10-13) that aren't on the tracker, sends today's list price for all of them (`SCP` line) and reads 20 of their card pages, or enough to re-read the whole list about every 9 runs, at most 40 (`SC` lines, oldest reading first). `scripts/scout.py` (called by `full_update.py`) merges that into `data/scout.json`, ranks the candidates and plans 3 picks per day two weeks ahead (`daily`), so a card isn't shown again for 30 days while unseen ones are left; its docstring has the filters and the score. Young cards with no pre-hype price (released after mid-2025) are compared with the DIY replacement cost instead (gem rate 75%+, at least 3 months old, at or below DIY cost, with an age-curve penalty), and cards 10–25% above their pre-hype price go to a separate "Close to cheap" list (`near`), never into the daily picks. The page (`renderScout`) shows today's picks with "+ Track it" (the Add card form with the SNKRDUNK page filled in) and "Not for me" (hidden in this browser via `psa10.scout.dismissed`). Cards without an ex/V/VMAX/VSTAR/GX name (trainers, mostly) only show with the "Include trainers" switch.

### Market page and Tables

- `renderMarketStrip`: the pokeca-chart index cells, with the trading-volume trend recomputed from
  the index's volume note (`volTrendOf`).
- `renderCustomIndex`: My-tier stats, the **breadth** block (`indexBreadth`: cards up and down over 7 days,
  the median card, the middle half of the moves, the top 3 cards' share of the index's move, and a chart of the
  share of cards up over 7 days), the range buttons (3M/1Y/All, remembered in `psa10.ciRange`), the chart and
  the constituents table.
- `renderHeat`, `renderEvents`, plus the snapshot's `notes`.
- `renderPsaBacklog` (**PSA grading backlog**): PSA's backlog against the 5M line below which its tracker shows the
  Value tiers as open, a chart of the readings, three scenarios for the next fortnightly drops and the first update
  on which each gets under the line, which tiers are open or paused, and PSA Japan's pre-pause price chart next to
  Standard. The projection is arithmetic on PSA's own figures (average of the last three drops, the latest drop,
  and the drop shrinking at its recent rate), not a forecast; `scripts/psa_backlog.py` computes it and the site only
  displays it. The panel warns when the last reading is over 16 days old. `psaBacklogLine` puts a one-line status at
  the top of the Submissions page.
- `renderTables`: cards become *columns* and statistics *rows*. Rows with a
  `sortableLabel()` button sort the columns (`TABLE_SORTS`, saved in `psa10.tableSort`).

### Pending-request notices

`loadCardRequests()` asks GitHub's public API for open issues. It shows
"N card requests waiting…", "Recording a purchase…", or a link if a purchase issue
has been stuck for over 5 minutes (meaning the Action commented an error). If GitHub
is unreachable, nothing is shown.

---

## 9. Styling: style.css

*Ghost Bid theme (2026-10-18): the colour tokens at the top of `style.css` are the violet palette (`--bg #100c18`,
`--panel`, `--band`, `--ghost #7c5cc4`, `--holo`, `--holo-line`); `--display` is now Barlow Condensed (numbers, titles, labels;
only weight 600 is loaded) and `--logo` is Bebas Neue for the wordmark. The block at the end of the file restyles the sidebar (brand-coloured group labels, a holo
right edge), adds the panel header bands, keeps the holo finish for the
strongest signals. Phones keep the mobile bar and bottom tab bar.*

- **Tokens first.** The `:root` block at the top defines every colour, both fonts and
  the corner radius. To change the accent colour, change `--accent` (and `--accent-2`
  for hover) there. `widgets/psa10-widget.js` has its own copy of the colours in `C`.
- **Fonts.** `--display` (Bebas Neue) for numbers, headings and card names; `--sans`
  (Montserrat) for body text. Noto Sans JP is the fallback for Japanese characters,
  which Bebas Neue lacks. They're loaded from Google Fonts in `index.html`.
- **Sections** are marked with comments (`/* ---------- overview: list + drawer ---------- */`).
  The first part follows the order of `app.js` (shell, key numbers, signals, verdict tags, slab, zone
  bars, overview, card detail, collection, watching, holdings, planner, market, phones); the features
  added later (head to head, scored calls, insights, Scout, Stories, You vs the model, combination
  finder, rate my portfolio, owned cards, grading, value over time) each have their own block after it.
- **Three layouts** via media queries:
  - ≥1200px: sidebar + overview list + detail drawer (the list drops its zone bars when the list
    itself is narrower than 640px, a container query);
  - 900–1199px (`@media (max-width: 1199px)`): no drawer; rows open the card page;
  - <900px (`@media (max-width: 899px)`): phone layout with the top bar and bottom tab bar.
  Several feature blocks add their own narrower breakpoints (640–800px).
- **Verdict colours** come from classes like `.vtag.buy`, `.vtag.watch` (and `.vtag.sell-…`,
  `.vtag.gr-…` for sell and grading verdicts); heat from `.heat-chip.heat-hot` etc.; up/down numbers
  from `.pos` / `.neg` (added by `dirClass()`).
- **Refresh bar:** `body.is-updating::before`. **Card page transition:** the
  `::view-transition-…(card-hero)` rules and `body.cd-entering`. Both respect Reduce Motion.

A good way to explore: right-click an element on the site → **Inspect**. DevTools shows
the HTML and every CSS rule that applies, with the file and line. You can edit values
live to try things before changing the file.

---

## 10. The GitHub Actions workflows

- **`deploy.yml`**: on every push to `main` (or when triggered manually), runs `scripts/site_bundle.py`
  and uploads its `_site/` folder to GitHub Pages: `index.html`, `assets/`, `widgets/`, `data/` with only the
  snapshots of the last 30 days (`SITE_DAYS`, plus one day so the oldest offered check has its predecessor),
  and nothing from `scripts/`, `docs/` or `tests/`. Keep `SITE_DAYS` equal in `site_bundle.py` and `app.js`
  (the check picker). `concurrency: pages` cancels an older deploy if a newer one starts.
- **`purchases.yml`** → `log_purchase.py`: issues labeled `bought`, `sold`, `remove-purchase`,
  `sealed`, `pull`, `sealed-link` or `grading-info` (or with the matching title prefix).
- **`limits.yml`** → `set_limit.py`: `set-limit` and `set-sell-target`.
- **`predictions.yml`** → `set_predictions.py`: `predict`.
- **`cards.yml`** → `remove_card.py`: `remove-card` and `restore-card`.
- **`labels.yml`** → `issue_labels.py --sync`: on a push that changes an issue form (or by hand),
  creates the labels the forms use and processes open issues that arrived unlabeled.
- **`tests.yml`** → `tests/test_rules.py`, `test_jsrun.py`, `test_psa_backlog.py`, `test_start.py`, `test_pipeline.py`: on a push or
  pull request that changes `assets/app.js`, the widget, `scripts/`, `pricecheck/` or `tests/`, checks on every
  snapshot that the site, the widget and the Python scripts apply the same rules (section 13), that the browser
  calls run only the stored scripts, the PSA backlog parser, that local runs get the procedures without the
  repo-finding prefix, and the price-check pipeline on fixtures (the in-page scripts' time codes and compact
  lines → decoders → `assemble.py`, and `plan.py`'s rules). Price checks don't trigger it.

The issue-driven workflows run when an issue is opened or edited, only if it's open and was opened
by you (`github.repository_owner`). Each uses one concurrency group per issue, so several forms
submitted together all run. `"$GITHUB_EVENT_PATH"` is the event file with the whole issue, including
the form's answers.

The Python scripts parse the form's Markdown body (`### Price` headings followed by
the answer), validate it, update the JSON, commit as `github-actions[bot]`, push
(retrying with `pull --rebase`, in case a price check pushed at the
same moment), trigger the deploy, then comment and close the issue. If the form can't
be read, they comment the reason and leave the issue open. Editing the issue re-runs them.

You can watch every run under the repo's **Actions** tab on GitHub, including the full
log of any that failed.

---

## 11. The Python scripts

All scripts are run from the repo root (`python3 scripts/<name>.py`), and each starts
with a docstring explaining its usage. Open the file and read the top.

**Publishing a check**

| Script | You'd run it when… |
|---|---|
| `check_status.py` | seeing the latest snapshot, whether today's full check ran and the suggested mode |
| `../pricecheck/plan.py` | seeing what today's full check will read (also prints the in-page script inputs) |
| `full_update.py` | publishing a full check from the compact lines (the skill does it; `--dry-run` to preview, `--skip` only for a step that really failed) |
| `quick_update.py` | publishing a quick check |
| `add_snapshot.py` | publishing an assembled snapshot (called by the two above) |
| `freshness.py` | listing which data sources are older than their cadence |
| `runclock.py` | the run clock: `start`, `end` (prints the run time and pushes the follow-ups; `quick_update.py` calls it itself when no follow-ups or retries are left, and a repeated `end` repeats the line), `history` |
| `salesdiff.py` | (library) rebuilds the SNKRDUNK lines the POLL sends as a diff against the previous run, checks them, keeps the base (`data/incoming/snk-base.json`) |
| `deferpush.py` | (library) commit without pushing while a run clock is running; `runclock.py end` pushes |
| `site_bundle.py` | building `_site/` for the deploy (run by `deploy.yml`; `python3 scripts/site_bundle.py` to try it) |

**Evaluations and written content**

| Script | You'd run it when… |
|---|---|
| `apply_analysis.py` | applying an evaluation (tiers, peak, verdict, sell tiers; `--dry-run` to preview) |
| `review_due.py` | listing cards due for re-evaluation (`--text`: written verdicts the price has moved away from) |
| `outliers.py` / `set_insight.py` | finding cards that stand out (cards you own are left out) / saving the written analysis for one |
| `set_story.py` | listing cards without a story (`--missing`) / saving one |
| `events.py` | managing the release calendar: `list`, `add`, `date`, `remove`, `window` |
| `psa_backlog.py` | PSA grading backlog (full check step 8i): `due` (is a look due today?), `from-page -` (saves the newest update from text copied off PSA's page, with sanity checks), `add 2026-10-20 7.4` (by hand), `status`, `recompute`; `print_due` is called by `full_update.py` |
| `event_study.py` | checking whether prices really dip around releases |
| `recap.py` | the weekly recap note (FULL-CHECK step 8j): `due`, `facts [MONDAY]`, `save -` |

**Market data and models**

| Script | You'd run it when… |
|---|---|
| `add_custom_index.py` | updating or backfilling the My-tier index |
| `premium.py` | saving the slab premium (normally via `full_update.py`) |
| `hype.py` | rebuilding the hype reference pool (monthly) or showing readings |
| `scout.py` | saving / re-ranking Scout candidates |
| `holdings_prices.py` | listing / saving prices of bought items that aren't tracked |
| `binder.py` | the Binder: Monday gate, saving prices with the previous reading, `set-id` for SNKRDUNK ids |
| `sealed_info.py` | reading names and pictures of sealed products from SNKRDUNK |
| `odds_model.py` / `save_odds_model.py` | printing today's odds / saving a rebuilt odds model |
| `save_value_model.py` | saving a rebuilt value model |
| `raw_price.py` | (library) the raw A-rank price rule |

**Archive and track record**

| Script | You'd run it when… |
|---|---|
| `build_history.py` | rebuilding `history.json`, `sales.json`, `predict.json` and `calls.json` by hand (normally automatic) |
| `build_calls.py` | rebuilding only the track record (`build(root, now=…)` scores as of another time, for tests) |
| `predict.py` | generating / resolving this week's You vs the model questions by hand |

**Run by Actions, or for maintenance**

| Script | You'd run it when… |
|---|---|
| `log_purchase.py`, `set_limit.py`, `set_predictions.py`, `remove_card.py` | run by Actions; `--dry-run event.json` to test locally |
| `issue_labels.py` | `--check` lists the form labels; `--sync` runs in Actions |
| `card_requests.py` | handling Add-card issues: `list`, `add`, `set`, `reject` |
| `eval_queue.py` | the EVALUATE NOW list (new/restored cards first); `add <id> "why"` / `drop <id>` by hand |
| `eval_context.py` | everything the repo knows about one card for an evaluation (`--odds <prices>` for limit-odds) |
| `../tests/test_rules.py` | checking that the site, the widget and the scripts still apply the same rules (needs Node) |

Scripts that push use the credential file configured for the repo. **Never put a
token in a script or a command, and never commit one.** `.git-credentials` is in
`.gitignore` for that reason.

---

## 12. The iPad/iPhone widget

**Installing and updating.** You paste `widgets/psa10-loader.js` into Scriptable once. Each run it downloads
`https://sprdl.github.io/psa10-tracker/widgets/psa10-widget.js` (at most once an hour, through a `?t=<hour>` query),
checks that the text is the widget (its first comment line, "PSA10 Tracker widget for Scriptable"; a test checks
that marker stays), saves it as `psa10-widget-code.js` in Scriptable's local documents and runs it. Offline, it
runs the saved copy. So a widget change ships with the next deploy; don't rename that first comment line.

`widgets/psa10-widget.js` runs in the Scriptable app. It fetches the public files from
`https://sprdl.github.io/psa10-tracker/data/...` directly (manifest, the latest
snapshot, limits, history, custom index, events), keeps the last good copy for offline use,
and re-implements a small part of the site's logic: zones, the correction, rally and event rules, signals,
limit hits, the 7-day change and heat, drawn with Scriptable's widget API. Only limits and sell targets saved to
all devices are visible to it. It also reads `holdings.json` and `sell_targets.json`: like the site, a card you
own (pulls included) never gives a limit or Buy signal, and grails (`grails.json`) are left out; a card you own gets the site's sell signal instead (`sellState`: Sell / Take profit /
Reassess from the sell tiers, your sell target, Near peak, Rich ask), shown with its gain on what you paid (a raw
copy against its DIY cost). Actionable sell signals rank after limit hits and before Buy signals in every size;
the large widget marks owned rows with their gain. If you change a rule in `app.js` (say, the
correction threshold), change the widget's copy too: `tests/test_rules.py` compares them on every snapshot.

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
git pull                     # always start from the latest (price checks and Actions push often)
# ...edit and test...
git add assets/app.js        # or whatever you changed
git commit -m "Describe the change"
git push                     # the site updates in ~1 minute
```

### Bump the version after changing app.js or style.css

Browsers keep `app.js` and `style.css` for up to 10 minutes. To make everyone get the
new file immediately, change the `?v=20261017a` in **both** places in `index.html`
(the `<link>` for style.css and the `<script>` for app.js) to today's date, adding a letter
for a second change on the same day (`?v=20261010`, `?v=20261010b`, …). Data files don't need
this; they're always revalidated.

### If you change the shape of the data

The site shows the cached copy first. If you rename or restructure a field, bump `CACHE_KEY` in `app.js`
(`'psa10.cache.v2'` → `'psa10.cache.v3'`) and add the old key to `CACHE_OLD`, so an old cached bundle in the
previous shape is never rendered by the new code. If you add a new data file, add it to `OPTIONAL_DATA` and copy
it into `state` in `showBundle` (or load it lazily like `sales.json`, if it's big and only one page needs it).

### Rules that exist twice: run the tests

Several rules live in more than one place, and they must agree:

| Rule | Site (`assets/app.js`) | Twin |
|---|---|---|
| raw A-rank price | `rawPrice` | `scripts/raw_price.py` (via `build_history.py`) |
| trading rate | `salesPerDay` | `build_history.sales_per_day` |
| "What stands out" | `insightsFor` | `outliers.findings` |
| tier review due | `tierReview` | `review_due.compute` |
| limit odds | `touchOdds` | `odds_model.odds` |
| event rule | `activeEvents` / `eventFor` | `events.active`, the widget's `eventFor` |
| verdict pill, limit hit, sell signal, correction and rally rules | `displayTagFor`, `limitHit`, `sellState`, `correctionState`, `rallyState` | the widget |

`python3 tests/test_rules.py` runs both sides on the repo's own data (the latest 3 snapshots; `RULES_N=100 python3
tests/test_rules.py` for more: with 3, the tier-review, event and owned-card checks often only compare empty lists,
so CI runs every snapshot) with the clock frozen at each snapshot's time, and fails on any difference.
`tests/rules.mjs` loads `app.js` and the widget in Node through their test hooks (`window.__PSA10_TEST__` /
`globalThis.__PSA10_TEST__`, never set in a browser or in Scriptable). GitHub Actions runs it on every push that
changes code (`tests.yml`). It needs Node 18+ on your Mac (`brew install node`). When you change one side of a rule,
change the other, and run the test before pushing. The first full run (2026-10-09) found three real differences,
now fixed: card names without a pack name or with a note after it weren't parsed by the site (so their odds used
the pooled model), one snapshot's date-only timestamp was read as two different times, and `outliers.py` crashed
on it.

### Debugging in the browser

Open DevTools with **Cmd+Option+I**.

- **Console** tab: red errors show the file and line. Click to jump to the code.
- **Network** tab: each JSON file, whether it loaded (200/304) or failed (404).
- **Application → Local Storage**: the `psa10.*` keys. Deleting one resets that feature
  on that device:

  | Key | Holds |
  |---|---|
  | `psa10.cache.v2` | last loaded data, for instant start: in **IndexedDB** (database `psa10`, store `kv`; Application → IndexedDB), in Local Storage only where IndexedDB is unavailable |
  | `psa10.limits` | limits changed on this device only |
  | `psa10.sell` | sell targets changed on this device only |
  | `psa10.planner` | budget, price mode, ticked cards, pins, left-out cards, finder category |
  | `psa10.sort`, `psa10.tableSort` | sort orders |
  | `psa10.seenSignals` | which buy signals are no longer NEW |
  | `psa10.ownedOnly` | Collection's "Only cards I own" |
  | `psa10.basis` | Holdings values: `ask`, `sales` or `net` |
  | `psa10.submit` | PSA submission planner: ticked cards, service, send date, shipping per order |
  | `psa10.pfh` | Holdings chart range and part |
  | `psa10.ciRange` | My-tier chart range |
  | `psa10.race` | head to head price race mode and range |
  | `psa10.trOpen` | expanded cards on the Track record |
  | `psa10.predict.local` | You vs the model answers locked on this device |
  | `psa10.scout.dismissed`, `psa10.scout.other`, `psa10.scout.seen` | Scout: hidden cards, trainers switch, day last opened |
  | `psa10.removing`, `psa10.restoring` | removals / restores waiting for their GitHub form |
  | `psa10.cb.poolOpen`, `psa10.cbUp.v2` | combination finder: pool panel open, cached simulations |
  | `psa10.imgTrim.v1`, `psa10.imgTrim.fail` | measured photo margins, CORS refusal |

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
  `CORRECTION_PCT`, `RALLY_PCT` / `RALLY_DAYS`, `TIER_MAX_AGE_DAYS`, `TIER_MAX_INDEX_MOVE`, `HEAT_LEVELS`, `LIMIT_STEP`,
  `RAW_SALES_N` / `RAW_SALES_DAYS` / `RAW_SALES_MIN`, `PSA_STD`, `GRADE_TIERS`, `GRADE_MARGIN`,
  `SELL_FEE` / `SELL_SHIP`, `SELL_NEAR_PEAK`, `INSIGHT`, `PREM_FLAG`, `MERC_FRESH_H` /
  `MERC_ENDING_MIN`, `CB_MIN` / `CB_MAX`, `SALES_MED_DAYS`, `HISTORY_MAX_SNAPSHOTS`. The event window lives in
  `data/events.json` → `window_days`. Scoring constants are at the top of
  `scripts/build_calls.py`; how long `history.json` keeps every check is `FULL_DAYS` in `scripts/build_history.py`. For rules a Python script also applies (insights in `outliers.py`, the raw
  price in `raw_price.py`, tier review in `review_due.py`, odds in `odds_model.py`) or the evaluation
  skill applies, change those too, so the site, the scripts and written verdicts stay consistent.
- **Change the default budget.** `plannerState()` → `200000`.
- **Fix a wrong number in one snapshot.** Edit the JSON in `data/snapshots/`, then
  `python3 scripts/build_history.py` so `history.json` and the track record pick it up,
  and commit all changed files.
- **Stop tracking a card.** Use "Remove card" on its page (reversible with Restore). To drop it for
  good, also remove it from `data/tracked_cards.json` (or from the price-check skill's own list).
  Old snapshots keep it, which is fine.
- **Add a new view.** Add a `<section class="view" data-view="x">` and nav links in
  `index.html`, add `x: 'Title'` to `VIEWS`, a case in `viewSubtitle`, a
  `renderX()` function, and call it from `render()` (or add it to `lazyPending` if it isn't needed
  for the first paint).
- **Add a new issue form.** Add the `.yml` under `.github/ISSUE_TEMPLATE/` with a label and a title
  prefix, match both in a workflow, handle it in a script, and add the prefix to
  `scripts/issue_labels.py` so an unlabeled issue still runs.

---

## 14. Troubleshooting

| Symptom | Likely cause | Where to look |
|---|---|---|
| "Couldn't load data/manifest.json" | manifest missing or invalid JSON after a manual edit | validate with `python3 -m json.tool data/manifest.json` |
| Site shows old data after a check | deploy still running or failed | repo → Actions tab; the yellow bar means a refresh is in progress |
| New code doesn't appear | browser cached app.js | bump `?v=` (section 13), or hard-reload |
| One section is empty, the rest works | a JavaScript error in that section's render function | DevTools Console |
| A form (purchase, limit, sale…) did nothing | issue not opened by you, missing label and wrong title, or form error | the issue's comments; Actions tab log; run the "Issue labels" workflow by hand |
| `git push` rejected | a price check or Action pushed first | `git pull --rebase` then `git push` |
| Push fails with an auth error | the token in the credential file expired | create a new token on GitHub and update the credential file (never paste it into a chat or commit) |
| A card shows "No tiers" after a check | it was never evaluated, or the URL changed so carry-forward missed it | compare `url` with the previous snapshot; `python3 scripts/eval_queue.py` lists what the next check will evaluate (`add <id>` queues one) |
| Limit or sell target shows "Only on this device" forever | the issue wasn't processed | check the issue; `data/limits.json` / `data/sell_targets.json` |
| `full_update.py` refuses the run | a planned step left no lines (completeness guard) | run the missing step; `--skip <name>` only if the site really failed |
| A sealed product has no picture or price | no SNKRDUNK link yet, or no full check since | "Add SNKRDUNK link" on Holdings; the next full check reads it (`sealed_info.py`, `holdings_prices.py`) |
| A removed card is back | the Remove card form was never submitted (local hide expired after 3 days) | submit the form, or check `data/removed_cards.json` |
| Card photos too small or offset | trim measurement cached from a bad load | delete `psa10.imgTrim.v1` in Local Storage |
| The "Rules tests" workflow fails | a rule was changed on one side only (site, widget or script) | run `python3 tests/test_rules.py`; the failure names the snapshot, the card and both values |
| The site shows data in an old shape after an update | an old cached bundle | bump `CACHE_KEY` (section 13); to clear it by hand: DevTools → Application → IndexedDB → `psa10` → delete |


## The Binder (added 2026-10-18)

`data/binder.json` lists the raw cards from Philipp's physical binder (scanned once from photos; no weekly scanning).
Each entry has name, set, number, rarity (`null` for older cards reprinted in the 30th set), `qty`, the SNKRDUNK id
and, after a reading, `price` (per copy), `basis`, `ask`, `sales`, `date` and the reading before it (`prev_price`,
`prev_date`). The price is the A-rank raw price (`raw_price.py`, same rule as everywhere).

- **Weekly reading, Mondays only (JST), inside the full check.** `plan.py` adds the binder's ids to `HELD` on Mondays,
  so the existing step 2b reads them with `snkrdunk_held.js` (H lines); `full_update.py` hands the same lines to
  `binder.save()`. On other days nothing is read. A failed read keeps the last price.
- **SNKRDUNK ids** are looked up once in the browser (`pricecheck/steps/2c-binder-ids.md`, `binder.py set-id`).
  Until then FOLLOW-UPS lists `2c`.
- **Site:** the Binder page (Own group) shows the binder value, the ▲/▼ change since the last reading, and one row
  per card. Binder cards are owned: no limit, no Buy signal, no sell tiers, and they are not part of the Holdings value.
- **Not included:** a "Remove" form like Holdings has; edit `data/binder.json` instead.
