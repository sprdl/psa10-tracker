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

## Using the app

Open the Pages URL on your phone/tablet (bookmark it or add it to your home
screen). The snapshot dropdown at the top switches between every run you've ever
pushed. Tap a card to expand it and see the full listing spread, the 15%-cutoff
split, recent completed sales with a small trend sparkline, and the raw A-grade
comparison; tap it again to collapse.

## Project layout

```
index.html                 the whole app shell
assets/style.css           styling
assets/app.js               all client-side logic (fetches data/, renders cards)
data/manifest.json          list of snapshots, in chronological order
data/snapshots/*.json       one file per price-check run, exactly as produced
scripts/add_snapshot.py     the one-command "publish a new run" script
.github/workflows/deploy.yml   GitHub Actions: deploy to Pages on push
```

No build step, no dependencies, no backend — it's a static site that reads its own
`data/` folder at request time.
