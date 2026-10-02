#!/usr/bin/env python3
"""
Save a value model built in the browser (scripts/value_model_builder.js) as data/value_model.json,
then commit and push. The site's Upside tab, Tier check and the combination finder's
"Best chance to hold value" read it.

    python3 scripts/save_value_model.py --codes          # print the tracked cards' codes for window.__valueCodes
    python3 scripts/save_value_model.py built.json [--no-push]

Rebuild it monthly together with the odds model (price-check step 5b): the builder reuses the
card histories the odds-model 'grab' step leaves in the browser.
"""
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "value_model.json"

# Release months for tracked cards that pokeca-chart's PSA10 list doesn't carry (no PSA10 page yet,
# or older than its list). Year-month of the Japanese release.
RELEASE_EXTRA = {
    "s8b 222/184": "2021-12",   # VMAX Climax
    "sm9 038/095": "2019-03",   # Tag Bolt
    "mf 043/040": "2026-09",    # 30th anniversary premium deck
    "mf 044/040": "2026-09",
}

ABOUT = {
    "what": "Upside ranges (12 and 24 months), the age curve and per-card swings for the tracked cards.",
    "method": [
        "Monthly PSA10 price per card = median of that month's pokeca-chart points.",
        "Mature market = equal-weighted average monthly change of cards at least 9 months old.",
        "Market part = the mature market's move over every 12/24-month window since 2022 (market quantiles).",
        "Card part = single cards' move minus the market over the same windows, pooled over cards 9+ months old, centred; scaled on the site by the card's own swing vs the pool (0.6x to 2x).",
        "Age curve = average monthly change vs the mature market by card age; the site adds it for cards under 12 months.",
        "The site centres the market part on zero (neutral) and also shows the result with the 2022-26 market as it was.",
        "Selling: SNKRDUNK Regular rank 9.5% fee, ¥300 transfer fee (¥200 under ¥30k), about ¥1,000 shipping.",
    ],
    "findings_2026_10_02": [
        "A card's price vs its own 6-12 month median did not predict how it did against other cards once the measurement month is skipped (3-month IC -0.07, t -1.0; 12-month IC +0.06, t 0.4). The earlier 'relative mean reversion' was mostly a monthly-sampling artifact.",
        "New cards fall against the market: about -20%/month in months 0-3, -8.5%/month in 3-6, -2% in 6-9, then flat.",
        "Popular characters (Pikachu, Charizard, Eeveelutions, Mew, Gengar, Lugia, Rayquaza, Greninja) beat other cards by about +14%/12 months and +27%/24 months, but not significantly (t 1.5-1.6); not used.",
        "Price level, card age (after 12 months), the card's own swing and its drawdown from the 12-month high did not predict relative returns.",
        "The market itself dominates outcomes: 12-month moves of the mature market ranged from -69% to +143% in 2022-26.",
    ],
}


def tracked_codes():
    snap = sorted(glob.glob(str(ROOT / "data" / "snapshots" / "*.json")))[-1]
    d = json.loads(Path(snap).read_text(encoding="utf-8"))
    out = []
    for c in d.get("cards", []):
        m = re.search(r"\[([^\]]+)\]", c.get("card_name_ja", ""))
        if m:
            out.append(m.group(1))
    return out


def main():
    args = sys.argv[1:]
    if "--codes" in args:
        print("window.__valueCodes = " + json.dumps(tracked_codes(), ensure_ascii=False) + ";")
        return
    files = [a for a in args if not a.startswith("--")]
    if not files:
        sys.exit(__doc__)
    new = json.loads(Path(files[0]).read_text(encoding="utf-8"))
    for k in ("horizons", "age_curve", "swing_pool", "swing", "release"):
        if k not in new:
            sys.exit(f"missing {k}: not a value-model build")
    for h in ("12", "24"):
        H = new["horizons"][h]
        if H["market_n"] < 20 or H["card_part_n"] < 500:
            sys.exit(f"too little data for {h} months ({H['market_n']} market windows, {H['card_part_n']} card windows): not saving")
    rel = {k.lower(): v for k, v in RELEASE_EXTRA.items()}
    rel.update(new["release"])
    new["release"] = rel
    out = {"about": ABOUT, **new}
    PATH.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Saved value model built {new['built']}: {len(new['swing'])} card swings, {len(rel)} release dates.")
    if "--no-push" not in args:
        subprocess.run(["git", "add", str(PATH)], cwd=ROOT, check=True)
        if subprocess.run(["git", "commit", "-q", "-m", f"value model: build {new['built']}"], cwd=ROOT).returncode == 0:
            subprocess.run(["git", "push", "-q"], cwd=ROOT, check=True)
            print("Pushed.")


if __name__ == "__main__":
    main()
