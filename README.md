# PSA10 Tracker

A small personal, non-commercial web app for tracking JPY prices of PSA10 and raw
A-rank Japanese Pokémon TCG cards from SNKRDUNK. Static site, deployed to GitHub
Pages via GitHub Actions on every push to `main`.

## One-time setup

1. Push this repo to GitHub (already done if you're reading this from the repo).
2. In the repo on GitHub: **Settings → Pages → Build and deployment → Source** →
   select **"GitHub Actions"**.
3. Push to `main` once (or re-run the "Deploy to GitHub Pages" workflow from the
   Actions tab) — the Actions tab will then show your site's URL, and it'll also
   appear under Settings → Pages.

The site's URL is not listed anywhere or linked from elsewhere, but note that on
GitHub's free/Pro/Team plans a Pages URL is still publicly reachable by anyone who
has it (true access-restricted Pages requires GitHub Enterprise). This is fine for
a personal, low-stakes tracker — just don't post the link publicly.

## Adding a new price check

Every time you run a price check and get a JSON output:

```bash
# from anywhere inside the repo, with the JSON copied to your clipboard:
python3 scripts/add_snapshot.py

# or, if you saved it to a file instead:
python3 scripts/add_snapshot.py path/to/output.json
```

That one command:
1. Saves the JSON to `data/snapshots/<timestamp>.json`
2. Updates `data/manifest.json` so the app knows it exists
3. Commits and pushes — GitHub Actions redeploys the site automatically within a
   minute or two

Add `--no-push` if you want to commit locally without pushing yet.

## Quick vs. full price checks

The price-check skill has two modes and picks one automatically
(`python3 scripts/check_status.py` shows which it would pick):

- **Full** (first run of each JST day, or when you ask for one): listing depth,
  top-20 asks, PSA10 population and the pokeca-chart index, as before.
- **Quick** (any later run that day, or when you ask for a quick check): one page
  per card, giving the lowest ask from the grade tiles plus recent completed sales.
  `scripts/quick_update.py` builds the snapshot from the latest one and publishes
  it. Depth, population and the index are carried over and labeled "as of" their
  real time on the site. Quick snapshots are marked "· quick" in the dropdown.

## Adding a card

Tap **+ Add card** on the site (under the snapshot picker) and paste the card's
SNKRDUNK product URL into the form. That files a GitHub issue labeled
`add-card`. The next price check sees it, reads the card's name from SNKRDUNK,
adds it to `data/tracked_cards.json` (cards tracked beyond the skill's own
list), and closes the issue with a confirmation. `scripts/card_requests.py`
does the work; run it without arguments for its commands.

## Applying a new evaluation (tiers, peak, verdict)

When an evaluation gives you a JSON block for one or more cards, copy it and run:

```bash
python3 scripts/apply_analysis.py              # reads the clipboard
python3 scripts/apply_analysis.py --dry-run    # preview first, writes nothing
```

It pulls the latest repo state, matches each card in the latest snapshot (by
SNKRDUNK url, name, or the set code in brackets like `[SV5a 090/066]`), merges the
new analysis over the old one, prints what changed (including the live price zone),
then commits and pushes. It refuses to guess when a name is ambiguous or missing.
If the JSON is a single bare block with no card name, add
`--card "SV5a 090/066"`. Pushing uses the credential file configured for this repo,
so no token is needed.

## Using the app

Open the Pages URL on your computer or phone (bookmark it or add it to your home screen). The snapshot dropdown (bottom of the sidebar, top bar on phones) switches between every run you've pushed.

The app has one section per job, reached from the sidebar on a computer and the bottom tab bar on a phone (Watching, Track record, Market & notes and Tables sit under **More**). Every section has its own address (`#/overview`, `#/collection`, `#/card/<snkrdunk id>` …), so links and the back button work.

- **Overview:** index, budget and track-record tiles, buy signals, alerts, and the list of cards with a PSA10 market (limit hits and Buy zones first). On a wide screen, clicking a card opens its details in the side panel. On narrower screens and phones it opens the card page.
- **Collection:** the same cards as a display case of PSA slabs.
- **Card page / side panel:** price, off-peak, change since the last check, the price gauge with your limit, the verdict and stats. Tabs show the full price **History**, the **Listings** (spread, 15% cutoff, recent sales for PSA10 and raw A) and the **DIY** grading comparison. **✓ Bought it** and the SNKRDUNK link sit alongside.
- **Watching:** cards with no PSA10 market yet (raw A price, favorites).
- **Holdings**, **Budget planner**, **Track record** and **Tables:** see the sections below.
- **Market & notes:** both pokeca-chart indices, volume notes and the check's methodology notes.

Cards without an evaluation are labeled "tiers not yet established" rather than guessing. Alerts on the overview show your own `banners` from the JSON plus flags the app computes by comparing with the previous snapshot (depth drops, favorite-count swings, a price crossing a tier boundary).

## My limits and buy signals

Each tracked card has a **+ Set my limit** button under its price bar. Type the
price you're willing to pay, then fine-tune it by dragging the gold handle on
the bar. When the lowest PSA10 ask is at or below your limit, the card gets a
gold outline and moves to the top.

The **Buy signals** strip at the top lists every card that's at your limit or in
a Buy / Definitely-buy zone. Items new since your last visit are marked NEW, and
tapping one opens that card. Limits are saved in the browser you set them in, so
they're per device.

## Budget planner

Below the cards, tick the cards you want to buy and set your budget (default ¥200,000). The planner adds up the selection, shows what's left or how far over you are, and marks unticked cards that would still fit ("fits").

The **Today's prices / My limits** switch changes which price each card uses:
- **Today's prices**: the current lowest PSA10 ask.
- **My limits**: your limit for the card (set with the limit marker on the card). Cards without a limit fall back to today's price, and a note says how many. The summary also shows how much buying at your limits would save compared with buying today.

Like limits, the selection, budget and switch position are saved in this browser only.

## Logging purchases

Each card has a **✓ Bought it** button. It opens a GitHub form pre-filled with the card, today's lowest ask and today's date (JST). Correct the price if you paid something else, pick "Raw" if you're grading it yourself, and submit. A GitHub Action (`.github/workflows/purchases.yml` → `scripts/log_purchase.py`) adds it to `data/holdings.json`, redeploys the site and closes the issue, usually within a minute or two. It works from your phone, and nothing runs on your Mac.

- **Your holdings** shows cost, current value and P&L. The card shows "✓ Owned", and the budget planner subtracts what you've spent from your budget.
- **Mistakes:** each purchase has a **Remove** link (same flow, `remove-purchase` form). You can also edit a purchase issue before it's processed.
- If a form can't be read (e.g. the price isn't a number), the Action comments what's wrong and leaves the issue open. The site links to it. Edit the issue and it retries.
- Only issues you open are processed. `scripts/add_holding.py` still works for bulk entry from the Mac.

## Track record (how the calls turned out)

The collapsible **Track record** section scores the tracker's own advice against what prices did afterwards. `scripts/build_calls.py` writes it to `data/calls.json`; `build_history.py` runs it on every published check, so nothing needs doing by hand.

- **Calls:** each change of verdict tag (Buy ↔ Watch …) is one call. Rewrites with the same tag count as "reaffirmed". A call is measured on the lowest PSA10 ask over the next 30 days:
  - A **Buy** is wrong once the ask drops more than 5% below the call price, and right if that never happens.
  - A **Watch** is right once it drops more than 5%. It's wrong if the window ends more than 5% higher with no dip, and neutral otherwise.
  - A lone reading more than 15% below both neighbours counts as a mispriced listing and is ignored.
- **Stated odds:** evaluations include `verdict.predictions`, e.g. `{"text": "Reaches Buy (≤¥70k) within 3 months", "p": 0.45, "type": "touch_below", "price": 70000, "by": "2026-12-25"}`. Each resolves as happened, didn't happen (deadline passed) or void (already true when made). The Brier score shows how well the odds are calibrated (0 = perfect, 0.25 = always saying 50%). `apply_analysis.py` validates predictions and warns when a reasoning text states odds without them.

## Project layout

```
index.html                     the whole app shell
assets/style.css                styling
assets/app.js                   all client-side logic (fetches data/, renders cards, tables, gauges)
data/manifest.json              list of snapshots, in chronological order
data/snapshots/*.json           one file per run — see docs/schema.md for the shape
scripts/add_snapshot.py         the one-command "publish a new run" script
scripts/apply_analysis.py       apply evaluation JSON (tiers/peak/verdict) to the latest snapshot
scripts/quick_update.py         publish a quick price check (lowest asks + sales, rest carried)
scripts/check_status.py         latest snapshot + whether today's full check has run
scripts/card_requests.py        "Add card" requests (GitHub issues) and data/tracked_cards.json
scripts/build_history.py        rebuilds data/history.json, the compact index the price-history charts read
data/tracked_cards.json         cards tracked in addition to the price-check skill's own list
data/history.json               per-card price series across all snapshots (auto-rebuilt on every publish)
docs/schema.md                  the full snapshot JSON schema, raw fields + optional analysis overlay
.github/workflows/deploy.yml    GitHub Actions: deploy to Pages on push
```

No build step, no dependencies, no backend — it's a static site that reads its own
`data/` folder at request time.

## My-tier index

`data/custom_index.json` holds a daily, equal-weighted PSA10 index of 22 cards in
the tier being bought (modern alt-art/SAR, ¥15k–150k at the 2026-09-26 base = 100),
shown on the Market page and under the PSA10 index tile. The price check updates it
once a day with the full check:

```bash
python3 scripts/add_custom_index.py --print-js          # extractor to run on pokeca-chart.com/gr/all-card/
python3 scripts/add_custom_index.py result.json --pokeca 105124
```

Constituents and base prices live in the file's `meta`; review them quarterly
(see the script's docstring for keeping the level continuous).

## Limit prices on every device

A limit you set on a card page is kept in that browser first ("Only on this
device"). Click **Save to all devices** to open a prefilled GitHub issue form
(label `set-limit`); submitting it runs `.github/workflows/limits.yml`, which
calls `scripts/set_limit.py` to update `data/limits.json`, commits, redeploys the
site and closes the issue. A limit of 0 removes it. Only issues you open are
processed.

Under each limit the card page shows a rough chance that a listing reaches it
within 30 and 90 days (random-walk model on the card's own daily prices, no trend
assumed; needs 6+ days of history), next to the evaluation's own stated odds for
a nearby price when there are any.
