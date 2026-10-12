#!/usr/bin/env python3
"""
Scout: rank cards you don't track yet that fit your criteria and look cheap, for the site's Scout page.

    python3 scripts/scout.py - [--no-push] <<'EOF'      # SCP / SC lines from pricecheck/scripts/pokeca_scout.js
    EOF
    python3 scripts/scout.py --rank [--no-push]        # re-rank data/scout.json without new lines

scripts/full_update.py calls update() with a full check's scout lines.

Pool: modern secret rares (card number above the set size, released 2021+, PSA10 ¥5k–150k on
pokeca-chart; the floor was ¥15k until 2026-10-13) that aren't on the tracker. Each full check refreshes every candidate's list price
and reads up to 20 card pages (oldest reading first), so each card's history metrics are at most
about a week old.

A candidate qualifies when it has a pre-hype reference (median monthly PSA10 price Jul–Dec 2025, the
same anchor the tiers use, skipping each card's first 3 months after release), trades at least 3 times in 30 days, sits at most 10% above that reference,
and its card page was read in the last 21 days. Score (higher = more interesting):
    2 × (1 − price / pre-hype)                 how far below the pre-hype level
  + 0.5 × (1 − price / 2026 peak)              how much of the bubble it has given back
  + 1 × max(0, −(premium / norm − 1))          slab premium compressed vs its own 6-month norm
  − 0.2 if the gem rate is 90%+               easy to grade → keeps getting diluted
Young cards (no pre-hype reference because they came out after mid-2025; added 2026-10-13) use the DIY
replacement cost instead: (pokeca-chart raw 美品 price + ¥12,430 PSA Standard incl. shipping) ÷ gem rate,
with raw = PSA10 price ÷ slab premium at the last card-page read. Only when the gem rate is at least 75%
(below that nobody self-grades, so DIY cost is no floor), the card is at least 3 months old (the age curve:
cards under 3 months drift about −20% a month vs the market) and the price is at or below DIY cost (no 10%
allowance: pokeca-chart's raw average runs above SNKRDUNK A-rank, which flatters DIY cost). Score:
    1 × (1 − price / DIY) + 0.5 × (1 − price / 2026 peak) − 0.3 if under 6 months − 0.1 if 6–9 months
    − 0.2 if the gem rate is 90%+
They carry "basis": "diy" (pre-hype cards "prehype") and say why in their reasons.

"Close to cheap" (data["near"], added 2026-10-13): cards with a pre-hype reference that pass every other
rule but sit 10–25% above it. Shown on the Scout page as a separate list, never in the daily picks.

"kind" is "pokemon" for ex/V/VMAX/VSTAR/GX/BREAK names, else "other" (trainers, and the odd plain-name
Pokémon illustration rare); the site shows Pokémon by default with a switch for the rest. The site
shows 3 new cards per JST day from data["daily"], which schedule() plans two weeks ahead so a card
isn't shown again for 30 days while unseen candidates are left.

data/scout.json: {"updated", "about", "pool": {slug: {...metrics, "read": date, "price": list price,
"seen": date}}, "ranked": [{slug, score, kind, basis, reasons: [...]}, ...], "near": [same, plus "disc"],
"dismissed": [slugs]}
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
TOP = 40
NEAR_MAX = 1.25    # "close to cheap": up to 25% above the pre-hype reference
NEAR_TOP = 20
GRADE_COST = 12430 # PSA Standard ¥9,980 + insurance/shipping ¥1,900 + handling ¥550 (the user's order screen)
DIY_MIN_GEM = 75   # below this gem rate DIY cost is no floor
DAILY = 3        # new cards on the Scout page each JST day
AHEAD = 14       # days scheduled in advance, so new picks appear even without a price check
COOLDOWN = 30    # a card isn't picked again within this many days while unseen ones are left


def decode(lines):
    prices, cards, errors = {}, {}, {}
    for line in lines:
        s = line.strip()
        if s.startswith("SCP "):
            for pair in s[4:].split(","):
                if ":" in pair:
                    slug, p = pair.rsplit(":", 1)
                    if p.isdigit():
                        prices[slug] = int(p)
        elif s.startswith("SC! "):
            parts = s.split(" ", 2)
            if len(parts) == 3:
                errors[parts[1]] = unquote(parts[2])
        elif s.startswith("SC "):
            d = json.loads(s[3:])
            cards[d["s"]] = d
    return prices, cards, errors


def _yen(v):
    return f"¥{v:,.0f}"


def prehype(c):
    """Median monthly PSA10 price Jul–Dec 2025, skipping the first 3 months after release (launch
    premium), from the card's monthly series; None if fewer than 2 such months."""
    rel = c.get("rel") or "2000-01"
    y, m = int(rel[:4]), int(rel[5:7]) + 3
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    start = max("2507", f"{y % 100:02d}{m:02d}")
    vals = []
    for pair in (c.get("ser") or "").split(","):
        if ":" in pair:
            k, v = pair.split(":")
            if start <= k <= "2512":
                vals.append(float(v) * 1000)
    if len(vals) < 2:
        return None
    vals.sort()
    n = len(vals)
    return round(vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2)


def months_old(rel, today):
    try:
        return (today.year - int(rel[:4])) * 12 + today.month - int(rel[5:7])
    except Exception:  # noqa: BLE001
        return None


def diy_cost(c):
    """(raw, DIY cost) from pokeca-chart's raw 美品 price implied by the slab premium, or (None, None)."""
    now, prem, gem = c.get("now"), c.get("prem"), c.get("gem")
    if not (now and prem and gem):
        return None, None
    raw = now / prem
    return round(raw), round((raw + GRADE_COST) / (gem / 100))


def _common_reasons(c, price, off, pdev, gem):
    why = []
    if off >= 0.1:
        why.append(f"{off * 100:.0f}% off its 2026 peak ({_yen(c.get('peak'))}, {c.get('pk', '')})")
    if pdev is not None and pdev <= -0.15:
        why.append(f"slab premium {abs(pdev) * 100:.0f}% below its own norm ({c['prem']:.2f}× vs {c['norm']:.2f}×)")
    elif pdev is not None and pdev >= 0.2:
        why.append(f"slab premium {pdev * 100:.0f}% above its norm: may lag the market for a while")
    if gem:
        why.append(f"PSA10 population {c.get('pop') or 0:,} · {gem:g}% gem rate" + (" (easy to grade, keeps getting diluted)" if gem >= 90 else ""))
    why.append(f"{c.get('vol', 0)} PSA10 sales in 30 days on pokeca-chart")
    return why


def rank(pool, today, near=None):
    """The ranked candidates (pre-hype and young-card DIY basis). Fills `near` (a list) with the
    "close to cheap" cards when one is passed."""
    out, close = [], []
    for slug, c in pool.items():
        price = c.get("price") or c.get("now")
        pre, peak = prehype(c), c.get("peak")
        c["pre"] = pre
        if not price or (c.get("vol") or 0) < 3 or not c.get("read"):
            continue
        if (today - datetime.fromisoformat(c["read"]).date()).days > 21:
            continue
        off = 1 - price / peak if peak and peak > price else 0.0
        pdev = (c["prem"] / c["norm"] - 1) if c.get("prem") and c.get("norm") else None
        gem = c.get("gem") or 0
        kind = "pokemon" if re.search(r"(ex|EX|V|VMAX|VSTAR|GX|BREAK)\s*\[", c.get("nm", "")) else "other"
        if pre:
            disc = price / pre
            if disc > NEAR_MAX:
                continue
            score = 2 * (1 - disc) + 0.5 * off + (max(0.0, -pdev) if pdev is not None else 0) - (0.2 if gem >= 90 else 0)
            why = [f"{_yen(price)}, {abs(1 - disc) * 100:.0f}% {'below' if disc < 1 else 'above'} its pre-hype level "
                   f"(Jul–Dec 2025 median {_yen(pre)})" if abs(1 - disc) >= 0.01 else f"{_yen(price)}, right at its pre-hype level ({_yen(pre)})"]
            entry = {"slug": slug, "score": round(score, 3), "kind": kind, "basis": "prehype",
                     "reasons": why + _common_reasons(c, price, off, pdev, gem)}
            if disc > 1.10:
                entry["disc"] = round(disc, 3)
                close.append(entry)
            else:
                out.append(entry)
            continue
        # young card: no pre-hype reference → DIY replacement cost, conservatively
        age = months_old(c.get("rel") or "", today)
        raw, diy = diy_cost(c)
        c["diy"] = diy
        if age is None or age < 3 or not diy or gem < DIY_MIN_GEM or price > diy:
            continue
        ratio = price / diy
        score = (1 - ratio) + 0.5 * off - (0.3 if age < 6 else 0.1 if age < 9 else 0) - (0.2 if gem >= 90 else 0)
        why = [f"{_yen(price)}, {(1 - ratio) * 100:.0f}% below the cost of grading a raw copy yourself (DIY {_yen(diy)}: "
               f"pokeca-chart raw ~{_yen(raw)} + {_yen(GRADE_COST)} grading, ÷ {gem:g}% gem rate)",
               f"young card ({age} months, no pre-hype price): DIY cost is the reference. pokeca-chart's raw average often runs "
               f"above SNKRDUNK A-rank, so check the card's DIY numbers before buying"]
        if age < 9:   # the age curve: under 9 months cards still drift down against the market
            why.append("age curve: cards this young have drifted about "
                       + ("−8.5% a month vs the market at 3–6 months" if age < 6 else "−2.2% a month vs the market at 6–9 months"))
        out.append({"slug": slug, "score": round(score, 3), "kind": kind, "basis": "diy",
                    "reasons": why + _common_reasons(c, price, off, pdev, gem)})
    out.sort(key=lambda x: -x["score"])
    if near is not None:
        near[:] = sorted(close, key=lambda x: x["disc"])[:NEAR_TOP]
    return out[:TOP]


def schedule(data, today):
    """data["daily"][YYYY-MM-DD] = {"p": [slugs], "a": [slugs]}: DAILY picks per day, Pokémon only ("p") and
    all kinds ("a"). Past days and today keep what they were given; future days are re-planned each run
    from the latest ranking. Best-ranked cards not picked in the last COOLDOWN days come first."""
    daily = data.setdefault("daily", {})
    for k in [k for k in daily if k < (today - timedelta(days=60)).isoformat()]:
        del daily[k]
    ranked = data.get("ranked", [])
    for key, keep in (("p", lambda r: r.get("kind") == "pokemon"), ("a", lambda r: True)):
        order = [r["slug"] for r in ranked if keep(r)]
        for i in range(AHEAD):
            day = today + timedelta(days=i)
            k = day.isoformat()
            if i == 0 and key in daily.get(k, {}):
                continue
            last = {}
            for dk, e in daily.items():
                if (day - timedelta(days=COOLDOWN)).isoformat() <= dk < k:
                    for sl in e.get(key, []):
                        last[sl] = max(last.get(sl, ""), dk)
            fresh = [sl for sl in order if sl not in last]
            stale = sorted([sl for sl in order if sl in last], key=lambda sl: last[sl])
            daily.setdefault(k, {})[key] = (fresh + stale)[:DAILY]


def update(prices, cards, errors, root=ROOT, push=True, now=None):
    now = now or datetime.now(JST)
    path = root / "data" / "scout.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    pool = data.setdefault("pool", {})
    data.setdefault("dismissed", [])
    today = now.date().isoformat()
    if prices:
        for slug in list(pool):                 # left the pool (tracked now, dismissed, or out of the price band)
            if slug not in prices:
                del pool[slug]
        for slug, p in prices.items():
            pool.setdefault(slug, {})
            pool[slug].update({"price": p, "seen": today})
    for slug, d in cards.items():
        if slug in pool or not prices:
            e = pool.setdefault(slug, {})
            e.update({k: v for k, v in d.items() if k != "s"})
            e["read"] = today
    for slug, err in errors.items():
        if slug in pool:
            pool[slug]["error"] = err
    near = []
    data["ranked"] = rank(pool, now.date(), near)
    data["near"] = near
    schedule(data, now.date())
    if prices or cards:   # a re-rank (--rank) reads nothing: keep the last read's time, which plan.py uses
        data["updated"] = now.replace(microsecond=0).isoformat()
    data["about"] = ("Scout candidates from pokeca-chart (pricecheck/scripts/pokeca_scout.js → scripts/scout.py). "
                     "See scripts/scout.py for the filters and the score.")
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    read = sum(1 for v in pool.values() if v.get("read"))
    print(f"scout: {len(pool)} candidates ({read} with card data, {len(cards)} read this run) · {len(data['ranked'])} ranked"
          + (": " + ", ".join(pool[r['slug']].get('nm', r['slug']) for r in data["ranked"][:5]) if data["ranked"] else ""))
    if not push:
        return
    # push="commit": commit only; full_update.py pushes everything once at the end of the publish step
    for cmd in (["git", "add", str(path)], ["git", "commit", "-q", "-m", "scout: candidates"], *([["git", "push", "-q"]] if push is True else [])):
        r = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            print(f"scout: {' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()}")
            return
    print("scout: pushed." if push is True else "scout: committed (pushed with the snapshot).")


if __name__ == "__main__":
    args = sys.argv[1:]
    push = "--no-push" not in args
    if push:
        subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=ROOT)
    if "--rank" in args:
        update({}, {}, {}, push=push)
    else:
        files = [a for a in args if not a.startswith("--")]
        text = sys.stdin.read() if not files or files[0] == "-" else Path(files[0]).read_text(encoding="utf-8")
        update(*decode(text.splitlines()), push=push)
