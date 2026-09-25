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

Open the Pages URL on your phone/tablet (bookmark it or add it to your home
screen). The snapshot dropdown at the top switches between every run you've ever
pushed.

A snapshot with just the raw price-check data renders honestly on its own: market
strip, per-card price/depth/favorites, and — tap a card to expand it — the full
listing spread, the 15%-cutoff split, recent completed sales with a labeled trend
chart (dates and prices), and the raw A-grade comparison. Cards without an
evaluation yet are labeled "tiers not yet established" rather than guessing.

Once you layer on an **analysis overlay** (see `docs/schema.md`) — representative
price, peak, tiers, verdict — a card also gets the colored price gauge, an
off-peak %, a verdict tag with reasoning, and rows in the two comparison tables at
the bottom of the page. Banners at the top surface both your own written notes
(`banners` in the JSON) and small auto-detected flags the app computes itself by
diffing against the previous snapshot (depth drops, favorite-count swings, a price
crossing a tier boundary).

## My limits and buy signals

Each tracked card has a **+ Set my limit** button under its price bar. Type the
price you're willing to pay, then fine-tune it by dragging the gold handle on
the bar. When the lowest PSA10 ask is at or below your limit, the card gets a
gold outline and moves to the top.

The **Buy signals** strip at the top lists every card that's at your limit or in
a Buy / Definitely-buy zone. Items new since your last visit are marked NEW, and
tapping one opens that card. Limits are saved in the browser you set them in, so
they're per device.

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
