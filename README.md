# PSA10 Tracker

A small personal, non-commercial web app for tracking JPY prices of PSA10 and raw
A-rank Japanese Pokémon TCG cards on SNKRDUNK, deciding when to buy, and following what
you bought (singles, sealed product, pulls, grading and sales). Static site, deployed to
GitHub Pages via GitHub Actions on every push to `main`.

**How the code works:** see [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md), a guide to every part of
the site, the data files, the scripts and the GitHub Actions, with recipes for common changes.
**Data shapes:** see [docs/schema.md](docs/schema.md).

## One-time setup

1. Push this repo to GitHub (already done if you're reading this from the repo).
2. In the repo on GitHub: **Settings → Pages → Build and deployment → Source** →
   select **"GitHub Actions"**.
3. Push to `main` once (or re-run the "Deploy to GitHub Pages" workflow from the
   Actions tab) — the Actions tab will then show your site's URL, and it'll also
   appear under Settings → Pages.
4. If an issue form ever does nothing, run the **Issue labels** workflow once from the Actions
   tab: it creates the labels the forms need and processes any issue that arrived without one.

The site's URL is not listed anywhere or linked from elsewhere, but note that on
GitHub's free/Pro/Team plans a Pages URL is still publicly reachable by anyone who
has it (true access-restricted Pages requires GitHub Enterprise). This is fine for
a personal, low-stakes tracker — just don't post the link publicly.

## Price checks

Price checks are run by the `pokemon-card-price-check` skill in your own browser: it opens
SNKRDUNK, pokeca-chart.com and altema pages (and Mercari for cards near your limit) in hidden
tabs, collects compact lines, and publishes them with one script. Nothing runs on a schedule.

The skill picks one of two modes (`python3 scripts/check_status.py` shows which it would pick):

- **Full** (first run of each JST day, when a card still needs its first evaluation, or when you
  ask for one): listing depth, top-20 asks, recent sales, PSA10 population, both pokeca-chart
  indices, the My-tier index, slab premiums, Scout candidates and prices of bought items that aren't
  tracked. `scripts/full_update.py` decodes the lines, assembles the snapshot and publishes it, then
  lists the follow-ups (evaluations, sell tiers, stories, tier reviews) and the Mercari step. The
  procedure is in `pricecheck/FULL-CHECK.md`.
- **Quick** (any later run that day, or when you ask for a quick check): one page
  per card, giving the lowest ask from the grade tiles plus recent completed sales.
  `scripts/quick_update.py` builds the snapshot from the latest one and publishes
  it. Depth, population and the index are carried over and labeled "as of" their
  real time on the site. Quick snapshots are marked "· quick" in the dropdown.

Publishing a snapshot saves `data/snapshots/<timestamp>.json`, updates `data/manifest.json`,
carries each card's evaluation forward, rebuilds the price history and the track record, commits
and pushes. GitHub Actions redeploys the site within a minute or two.

An assembled snapshot JSON can still be published by hand:

```bash
python3 scripts/add_snapshot.py                    # JSON from the clipboard
python3 scripts/add_snapshot.py path/to/output.json
```

Add `--no-push` to commit locally without pushing yet. A single lower price from a SNKRDUNK
"new listing" email can be applied with `python3 scripts/email_price_alert.py <id> <price>`.

## Adding and removing cards

Tap **+ Add card** on the site (sidebar, More, or the last tile of the Collection) and paste the
card's SNKRDUNK product URL into the form. That files a GitHub issue labeled
`add-card`. The next price check sees it, reads the card's name from SNKRDUNK,
adds it to `data/tracked_cards.json` (cards tracked beyond the skill's own
list), and closes the issue with a confirmation. `scripts/card_requests.py`
does the work; run it without arguments for its commands. Scout's **+ Track it** uses the same form.

**Remove card** on a card page (click twice to confirm) opens a form that adds the card to
`data/removed_cards.json`: the site hides it and price checks skip it. Its history stays, so
**Restore** in the Collection's "Removed cards" list brings it back. A card you bought or pulled
can't be removed.

## Applying a new evaluation (tiers, peak, verdict, sell tiers)

When an evaluation (the `pokemon-tcg-card-evaluation` skill) gives you a JSON block for one or
more cards, copy it and run:

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
so no token is needed. For cards you own, the block can carry `sell_tiers` and `sell_verdict` alone.

Full checks do most of this themselves: they evaluate new cards, re-evaluate cards whose tiers
are due (`scripts/review_due.py`), and rewrite a verdict once the price has moved 5% from the price it
was written at.

## Using the app

Open the Pages URL on your computer or phone (bookmark it or add it to your home screen). The
snapshot dropdown (bottom of the sidebar, top bar on phones) switches between every run you've pushed.

The app has one section per job, reached from the sidebar on a computer and the bottom tab bar on a
phone (Overview, Collection, Holdings, Planner and **More**, which holds Scout, Stories, You vs model,
Watching, Track record, Market & notes and Tables). Every section has its own address
(`#/overview`, `#/collection`, `#/card/<snkrdunk id>` …), so links and the back button work.

- **Overview:** index, My-tier and budget tiles, buy signals, alerts, and the list of cards with a
  PSA10 market (limit hits and Buy zones first, sortable by every column). The Limit column shows your
  limit for cards you watch and your gain for cards you own. On a wide screen, clicking a card opens a
  short summary in the side panel; on narrower screens and phones it opens the card page.
- **Collection:** the same cards as a display case of PSA slabs, with **Only cards I own** and
  **⇄ Compare two cards** (head to head: side-by-side numbers and a price race).
- **Card page:** price, off-peak, change since the last check, the price gauge with your limit, a
  verdict computed from today's price with the written analysis folded below it, "What stands out",
  vs. the market, hype exposure and stats. Tabs show the **Story** behind the artwork, the full price
  **History**, the **Listings** (spread, 15% cutoff, recent sales for PSA10 and raw A), the **DIY**
  grading comparison with the slab premium, and the **Upside** (12- and 24-month ranges). Previous /
  Next (← →) walk through the cards. For a card you own, the page switches to the sell view (below).
- **Scout:** three new cards a day that you don't track yet, fit your criteria and look cheap.
- **Stories:** the art behind your cards: illustrator, what it shows, set context, sources.
- **You vs model:** up to ten questions a week about your cards ("Will a listing drop to ¥X by
  Friday?"); lock in your odds, then see the model's. Scored with Brier scores.
- **Watching:** cards with no PSA10 market yet (raw A price, trading, favorites).
- **Holdings**, **Budget planner**, **Track record** and **Tables:** see the sections below.
- **Market & notes:** both pokeca-chart indices and their trading volume, the My-tier index chart,
  trading activity per card, the release calendar and the check's methodology notes.

Cards without an evaluation are labeled "tiers not yet established" rather than guessing. Alerts on
the overview show your own `banners` from the JSON, the event and correction rules, plus flags the app
computes by comparing with the previous snapshot (depth drops, favorite-count swings, a price crossing
a tier boundary).

## My limits and buy signals

Each tracked card has a **+ Set my limit** button under its price bar. Type the
price you're willing to pay (the editor shows the chance a listing gets there in 30 and 90 days),
then fine-tune it by dragging the gold handle on the bar. When the lowest PSA10 ask is at or below
your limit, the card gets a gold outline and moves to the top.

The **Buy signals** strip at the top lists every card that's at your limit, in a Buy /
Definitely-buy zone, or has a Mercari listing or ending auction at or under your limit. Items new
since your last visit are marked NEW, and tapping one opens that card. A card you own never gives a
limit signal; its sell target takes over.

A new limit is kept in the browser you set it in first ("Only on this device"); **Save to all
devices** syncs it (see "Limit prices on every device" below).

## Budget planner

Tick the cards you want to buy and set your budget (default ¥200,000). The planner adds up the
selection, subtracts what you've already spent on singles (grading included), shows what's left or
how far over you are, and marks unticked cards that would still fit ("fits").

The **Today's prices / My limits** switch changes which price each card uses:
- **Today's prices**: the current lowest PSA10 ask.
- **My limits**: your limit for the card. Cards without a limit fall back to today's price, and a
  note says how many. The summary also shows how much buying at your limits would save compared
  with buying today.

From the planner:
- **✦ Combination finder** tries every mix of cards that spends 90–120% of what's left and ranks them
  by budget fit, number of cards, value against the Buy lines, upside, chance of a profit and (at your
  limits) the chance the limits are reached. 📌 pins a card, ✕ leaves one out.
- **★ Rate this portfolio** scores the ticked cards with the same measures against every combination,
  and "Find best match" suggests what to add.
- **⇄ Compare N cards** (2–8 ticked) opens the budget duel: today's price and your limit side by side
  with the odds of reaching it and what's left of the budget.

The selection, budget, pins and switch position are saved in this browser only.

## Logging purchases, sealed product, pulls and sales

Everything you own is recorded through GitHub issue forms the site opens pre-filled. A GitHub Action
(`.github/workflows/purchases.yml` → `scripts/log_purchase.py`) updates `data/holdings.json`,
redeploys the site and closes the issue, usually within a minute or two. It works from your phone, and
nothing runs on your Mac.

- **✓ Bought it** (card page, side panel): a dialog asks for the price (today's lowest ask
  pre-filled), the date, slab or raw (with the grading fee), and notes, then opens the form ready to
  submit. **+ Bought another** logs a second copy.
- **+ Add sealed product** (Holdings): a box, set or packs bought at MSRP, with its SNKRDUNK link so
  the next price check fills in its name, picture and lowest ask.
- **Pulled one of these? / + Add pull** (under a sealed product): a valuable card that came out of it,
  raw, at PSA, PSA10 or graded otherwise. Logging a pull marks the product as opened.
- **Grading info** (raw singles and pulls): when it was sent to PSA, the service tier, and your own
  chance of a PSA10 for that copy. The site uses it for the "Grade it?" verdict and the return date.
- **✓ Sold it** (owned card page, Holdings rows, unopened sealed products): the sale price (suggested:
  the PSA10 price for a slab, the raw A-rank price for a raw card), date, quantity for sealed lots and
  the real fees if you know them. **Undo sale** puts the item back.
- **Remove** fixes a mistake. You can also edit an issue before it's processed.
- If a form can't be read (e.g. the price isn't a number), the Action comments what's wrong and
  leaves the issue open. The site links to it. Edit the issue and it retries.
- Only issues you open are processed. `scripts/add_holding.py` still works for bulk entry from the Mac.

## Holdings

The Holdings page shows what you spent, what it's worth now, the +/− and realized profit at the top;
a switch values everything at the lowest ask or after SNKRDUNK's selling costs (9.5% fee, ¥200/¥300
fixed fee, ¥1,000 shipping). Below:

- **Value over time:** worth against money spent since your first purchase, by Total / Singles /
  Sealed / Pulls.
- **Singles:** a slab is worth the PSA10 price. A card bought raw is worth the raw A-rank price
  (the median of recent sales, never below the lowest ask) and shows the PSA10 ask against your DIY
  cost, (price paid + grading & shipping) ÷ gem rate.
- **Sealed:** unopened products at their lowest SNKRDUNK ask; opened ones by the value of their pulls,
  with a "Grade it?" verdict for raw pulls.
- **Sold:** every sale with fees and profit, plus a yearly summary.

## Cards you own: the sell view

A card you hold gets a different card page and side panel: your position (paid, worth now, after
selling costs, break-even), a sell gauge with your cost, break-even, sell target and the peak, and a
sell verdict: **Sell**, **Take profit**, **Reassess**, **Near peak**, **Rich ask** or **Hold**. It
comes from the evaluation's `sell_tiers`, your own **sell target** (set and synced like a limit), the
recorded peak, and whether the lowest ask is far above recent sales. For a raw copy, a **Grade it?**
panel compares selling raw with grading it. Full checks write sell tiers for owned cards that don't
have them yet, and rewrite them when they get old or the My-tier index has moved 10% since.

## Track record (how the calls turned out)

The **Track record** page scores the tracker's own advice against what prices did afterwards.
`scripts/build_calls.py` writes it to `data/calls.json`; `build_history.py` runs it on every published
check, so nothing needs doing by hand. The "Buy / Watch calls" tile opens the **Scored calls** page.

- **Calls:** each change of verdict tag (Buy ↔ Watch …) is one call. Rewrites with the same tag count
  as "reaffirmed". A call is measured on the lowest PSA10 ask over the next 30 days:
  - A **Buy** is wrong once the ask drops more than the card's threshold below the call price, and
    right if that never happens.
  - A **Watch** is right once it drops more than the threshold. It's wrong if the window ends more than
    the threshold higher with no dip, and neutral otherwise.
  - The threshold is 5%, or the card's own normal swing between checks if larger (up to 10%), and a
    drop only counts after two checks in a row below it.
- **Stated odds:** evaluations include `verdict.predictions`, e.g. `{"text": "Reaches Buy (≤¥70k) within 3 months", "p": 0.45, "type": "touch_below", "price": 70000, "by": "2026-12-25"}`. Each resolves as happened, didn't happen (deadline passed) or void (already true when made). The Brier score shows how well the odds are calibrated (0 = perfect, 0.25 = always saying 50%). `apply_analysis.py` validates predictions and warns when a reasoning text states odds without them.
- **Limit-odds model:** each full check logs the model's odds for every card's tier prices and your
  limits (`data/odds_log.json`), scored the same way.

## Project layout

```
index.html                     the whole app shell
assets/app.js                   all client-side logic (fetches data/, renders every page)
assets/style.css                styling
data/manifest.json              list of snapshots, in chronological order
data/snapshots/*.json           one file per run — see docs/schema.md for the shape
data/history.json               per-card price series across all snapshots (auto-rebuilt on every publish)
data/calls.json                 track record (auto-rebuilt on every publish)
data/holdings.json              your purchases, sealed product, pulls and sales
data/limits.json, sell_targets.json   limits and sell targets saved to all devices
data/*.json                     indices, models, insights, stories, Scout, Mercari… (docs/HOW-IT-WORKS.md §4)
scripts/full_update.py          publish a full price check from the in-page scripts' lines
scripts/quick_update.py         publish a quick price check (lowest asks + sales, rest carried)
scripts/add_snapshot.py         save a snapshot, carry evaluations forward, rebuild history, push
scripts/apply_analysis.py       apply evaluation JSON (tiers/peak/verdict/sell tiers) to the latest snapshot
scripts/check_status.py         latest snapshot + whether today's full check has run
scripts/log_purchase.py, set_limit.py, set_predictions.py, remove_card.py   run by GitHub Actions
scripts/*.py                    everything else (docs/HOW-IT-WORKS.md §11)
pricecheck/                     the price-check skill's in-page scripts, plan and procedure
widgets/psa10-widget.js         iPhone/iPad Home Screen widget (Scriptable)
docs/schema.md                  the data shapes: snapshot, analysis overlay, holdings and the other files
docs/HOW-IT-WORKS.md            guide to how the code works
.github/workflows/              deploy to Pages + the Actions behind the site's forms
.github/ISSUE_TEMPLATE/         the issue forms the site opens
```

No build step, no dependencies, no backend — it's a static site that reads its own
`data/` folder at request time.

## My-tier index

`data/custom_index.json` holds a daily, equal-weighted PSA10 index of 22 cards in
the tier being bought (modern alt-art/SAR, ¥15k–150k at the 2026-09-26 base = 100),
shown on the Market page and under the PSA10 index tile. The full check updates it
once a day (the `MYTIER` line); by hand:

```bash
python3 scripts/add_custom_index.py --print-js          # extractor to run on pokeca-chart.com/gr/all-card/
python3 scripts/add_custom_index.py result.json --pokeca 105124
```

Constituents and base prices live in the file's `meta`; review them quarterly
(see the script's docstring for keeping the level continuous).

History before the first daily reading is backfilled from pokeca-chart's per-card PSA10
charts (entries marked `"backfill": true`; month-end values until Jul 2026, daily after).
That gives the correction rule a real 30-day change from day one. To rebuild it (e.g.
after changing constituents): run `scripts/odds_model_builder.js` list + grab on
pokeca-chart, then `add_custom_index.py --print-backfill-js` on
https://pokeca-chart.com/gr/chart-index/ and `add_custom_index.py --backfill result.json`.

## Release calendar and the event rule

`data/events.json` lists upcoming releases. In the 3 days before a major one (and on
the day), a Buy-zone price shows as Watch, the same rule the evaluation skill uses;
Definitely-buy prices and your own limits still count. An event can apply to all cards
or only some sets (`"scope": ["M6a"]`). Rumoured events without a date are listed on
the Market page but never applied. Full checks look for new announcements on Mondays.

```bash
python3 scripts/events.py list                     # upcoming + rumoured
python3 scripts/events.py window                   # is the rule on right now?
python3 scripts/events.py add 2026-11-20 "拡張パック「…」" --scope all --source URL
python3 scripts/events.py date "ハドウシーカー" 2026-11-27   # a rumoured event gets its date
python3 scripts/event_study.py                     # did prices actually dip around past releases?
```

The **correction rule** works the same way: while the My-tier index is down more than 10% over 30
days, Buy-zone prices show as Watch.

## Limit prices on every device

A limit you set on a card page is kept in that browser first ("Only on this
device"). Click **Save to all devices** to open a prefilled GitHub issue form
(label `set-limit`); submitting it runs `.github/workflows/limits.yml`, which
calls `scripts/set_limit.py` to update `data/limits.json`, commits, redeploys the
site and closes the issue. A limit of 0 removes it. Sell targets for cards you own work the same
way (label `set-sell-target`, `data/sell_targets.json`). Only issues you open are processed.

Under each limit the card page shows a rough chance that a listing reaches it
within 30 and 90 days (the card's own price swings from about two years of pokeca-chart history,
no trend assumed), next to the evaluation's own stated odds for a nearby price when there are any.

## Mercari

For cards whose SNKRDUNK ask is within 5% of your limit, price checks also read Mercari's PSA10
listings (`pricecheck/MERCARI.md`, `scripts/mercari.py`). The card page shows the cheapest ones
including the ¥1,700 あんしん鑑定 fee, and a fixed-price listing or an auction ending within 2 hours
at or under your limit becomes a buy signal.

## Home Screen widget (iPhone / iPad)

`widgets/psa10-widget.js` is a [Scriptable](https://apps.apple.com/app/scriptable/id1405459188) widget that reads this site's public data:
small = rotates through cards at your limit (first) or in a Buy zone, every ~15 min
(widget parameter = a SNKRDUNK id pins one card); medium = buy signals + My-tier index;
large = compact overview. It uses limits saved to all devices (`data/limits.json`) and doesn't know
which cards you own.
Setup: install Scriptable, create a new script, paste the file, then add a Scriptable
widget to the Home Screen and choose the script. Tapping opens the tracker.
