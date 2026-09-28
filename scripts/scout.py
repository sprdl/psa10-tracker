#!/usr/bin/env python3
"""
Scout: rank cards you don't track yet that fit your criteria and look cheap, for the site's Scout page.

    python3 scripts/scout.py - [--no-push] <<'EOF'      # SCP / SC lines from pricecheck/scripts/pokeca_scout.js
    EOF
    python3 scripts/scout.py --rank [--no-push]        # re-rank data/scout.json without new lines

scripts/full_update.py calls update() with a full check's scout lines.

Pool: modern secret rares (card number above the set size, released 2021+, PSA10 ¥15k–150k on
pokeca-chart) that aren't on the tracker. Each full check refreshes every candidate's list price
and reads up to 20 card pages (oldest reading first), so each card's history metrics are at most
about a week old.

A candidate qualifies when it has a pre-hype reference (median monthly PSA10 price Jul–Dec 2025, the
same anchor the tiers use, skipping each card's first 3 months after release), trades at least 3 times in 30 days, sits at most 10% above that reference,
and its card page was read in the last 21 days. Score (higher = more interesting):
    2 × (1 − price / pre-hype)                 how far below the pre-hype level
  + 0.5 × (1 − price / 2026 peak)              how much of the bubble it has given back
  + 1 × max(0, −(premium / norm − 1))          slab premium compressed vs its own 6-month norm
  − 0.2 if the gem rate is 90%+               easy to grade → keeps getting diluted
"kind" is "pokemon" for ex/V/VMAX/VSTAR/GX/BREAK names, else "other" (trainers, and the odd plain-name
Pokémon illustration rare); the site shows Pokémon by default with a switch for the rest. The site
shows 3–5 of the ranked cards per JST day, rotating so each day brings different ones.

data/scout.json: {"updated", "about", "pool": {slug: {...metrics, "read": date, "price": list price,
"seen": date}}, "ranked": [{slug, score, reasons: [...]}, ...], "dismissed": [slugs]}
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


def rank(pool, today):
    out = []
    for slug, c in pool.items():
        price = c.get("price") or c.get("now")
        pre, peak = prehype(c), c.get("peak")
        c["pre"] = pre
        if not price or not pre or (c.get("vol") or 0) < 3 or not c.get("read"):
            continue
        if (today - datetime.fromisoformat(c["read"]).date()).days > 21:
            continue
        disc = price / pre
        if disc > 1.10:
            continue
        off = 1 - price / peak if peak and peak > price else 0.0
        pdev = (c["prem"] / c["norm"] - 1) if c.get("prem") and c.get("norm") else None
        gem = c.get("gem") or 0
        score = 2 * (1 - disc) + 0.5 * off + (max(0.0, -pdev) if pdev is not None else 0) - (0.2 if gem >= 90 else 0)
        why = []
        why.append(f"{_yen(price)}, {abs(1 - disc) * 100:.0f}% {'below' if disc < 1 else 'above'} its pre-hype level "
                   f"(Jul–Dec 2025 median {_yen(pre)})" if abs(1 - disc) >= 0.01 else f"{_yen(price)}, right at its pre-hype level ({_yen(pre)})")
        if off >= 0.1:
            why.append(f"{off * 100:.0f}% off its 2026 peak ({_yen(peak)}, {c.get('pk', '')})")
        if pdev is not None and pdev <= -0.15:
            why.append(f"slab premium {abs(pdev) * 100:.0f}% below its own norm ({c['prem']:.2f}× vs {c['norm']:.2f}×)")
        elif pdev is not None and pdev >= 0.2:
            why.append(f"slab premium {pdev * 100:.0f}% above its norm: may lag the market for a while")
        if gem:
            why.append(f"PSA10 population {c.get('pop') or 0:,} · {gem:g}% gem rate" + (" (easy to grade, keeps getting diluted)" if gem >= 90 else ""))
        why.append(f"{c.get('vol', 0)} PSA10 sales in 30 days on pokeca-chart")
        kind = "pokemon" if re.search(r"(ex|EX|V|VMAX|VSTAR|GX|BREAK)\s*\[", c.get("nm", "")) else "other"
        out.append({"slug": slug, "score": round(score, 3), "kind": kind, "reasons": why})
    out.sort(key=lambda x: -x["score"])
    return out[:TOP]


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
    data["ranked"] = rank(pool, now.date())
    data["updated"] = now.replace(microsecond=0).isoformat()
    data["about"] = ("Scout candidates from pokeca-chart (pricecheck/scripts/pokeca_scout.js → scripts/scout.py). "
                     "See scripts/scout.py for the filters and the score.")
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    read = sum(1 for v in pool.values() if v.get("read"))
    print(f"scout: {len(pool)} candidates ({read} with card data, {len(cards)} read this run) · {len(data['ranked'])} ranked"
          + (": " + ", ".join(pool[r['slug']].get('nm', r['slug']) for r in data["ranked"][:5]) if data["ranked"] else ""))
    if not push:
        return
    for cmd in (["git", "add", str(path)], ["git", "commit", "-q", "-m", "scout: candidates"], ["git", "push", "-q"]):
        r = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            print(f"scout: {' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()}")
            return
    print("scout: pushed.")


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
