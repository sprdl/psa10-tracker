#!/usr/bin/env python3
"""
Publish a QUICK price check: fresh lowest asks + completed sales, everything else carried.

Usage:
    python3 scripts/quick_update.py data/incoming/quick-raw.json            # build, save, commit, push
    python3 scripts/quick_update.py data/incoming/quick-raw.json --no-push  # build, save, commit only
    python3 scripts/quick_update.py data/incoming/quick-raw.json --dry-run  # build + print, write nothing
    python3 scripts/quick_update.py - <<'EOF' … EOF                        # compact lines on stdin (below)

Input is either the JSON shape below or, since 2026-09-27, the compact lines that
pricecheck/scripts/snkrdunk_quick.js returns (one card per line, see decode_compact),
which are decoded into exactly the same JSON before anything else happens.

A quick run reads ONE page per card (the SNKRDUNK product page) instead of the full
routine (listings pages, altema, pokeca index). The raw file the price-check skill
writes looks like:

    {"mode": "quick",
     "cards": {"<snkrdunk_id>": {"base":  <snkrdunk_base.js result>,
                                 "tiles": <grade-tile snippet result>}, ...}}

This script starts from the latest snapshot in the repo and replaces only what the
quick run actually measured, per card:
  - favorite_count
  - grades.psa10 / grades.raw_a_grade: lowest_price (from the grade tile's "¥X~"),
    its 115% threshold, and recent_completed_sales
Everything else is carried from the latest snapshot and labeled with when it was
really measured, so the site never presents old numbers as new:
  - listing depth (top-20, within-15%, counts) → `listings_as_of`
  - PSA10 population / gem rate → `population_as_of`
  - pokeca-chart market index → `as_of` on each index object
The result is marked "check_mode": "quick" and handed to add_snapshot.py, which
carries the analysis (tiers/peak/verdict) forward, saves, commits and pushes.

Cards the quick run didn't cover are kept as they were (and reported). Cards the
quick run covered that aren't in the tracker yet are skipped — add new cards with a
full check, which knows their names.
"""

import copy
import json
import re
from urllib.parse import unquote
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
GRADE_KEYS = {"PSA10": "psa10", "A": "raw_a_grade"}
LISTING_ARRAYS = ("top20_cheapest_listings", "listings_within_15pct_of_lowest",
                  "count_within_15pct", "count_excluded_over_15pct", "top20_stats")


def die(msg):
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def snkrdunk_id(url: str) -> str:
    return (url or "").rstrip("/").split("/")[-1]


WHEN_UNITS = {"s": "秒", "m": "分", "h": "時間", "d": "日", "w": "週間", "M": "ヶ月", "K": "か月"}
TILE_NOTE = {"-": "no listings (出品待ち)", "?": "no price on tile"}


def _when(code):
    """Inverse of enc() in snkrdunk_quick.js: 3h → 3時間前, 260421 → 2026/04/21, n → たった今."""
    if code == "n":
        return "たった今"
    if code.startswith("~"):
        return unquote(code[1:])
    m = re.fullmatch(r"(\d{2})(\d{2})(\d{2})", code)
    if m:
        return f"20{m[1]}/{m[2]}/{m[3]}"
    m = re.fullmatch(r"(\d+)([smhdwMK])", code)
    if m:
        return f"{m[1]}{WHEN_UNITS[m[2]]}前"
    raise ValueError(f"unknown time code {code!r}")


def _sales(tok, grade):
    """P=… / P~4=… / P0 / P!n / P!a → the snkrdunk_base.js result for one grade."""
    body = tok[1:]
    if body == "!n":
        return {"error": "sales-history grade pill not found"}
    if body == "!a":
        return {"pill_active": False, "recent_completed_sales": [], "error": "grade pill did not activate after 3 clicks"}
    if body == "0":
        return {"pill_active": True, "recent_completed_sales": [],
                "sales_note": "no completed sales in period (この期間内に取引がありません)"}
    m = re.fullmatch(r"(?:~(\d+))?=(.*)", body)
    if not m:
        raise ValueError(f"bad sales token {tok!r}")
    rows = []
    for item in filter(None, m[2].split(",")):
        price, _, when = item.partition("@")
        rows.append({"price": int(price), "when": _when(when)})
    res = {"pill_active": True, "recent_completed_sales": rows}
    if m[1]:
        res["sales_note"] = f"{m[1]} row(s) discarded: grade/quantity did not match {grade}/1枚"
    return res


def _tile(code):
    if code.isdigit():
        return {"lowest_ask": int(code)}
    if code in TILE_NOTE:
        return {"lowest_ask": None, "note": TILE_NOTE[code]}
    if code == "x":
        return {"error": "tile not found"}
    raise ValueError(f"bad tile code {code!r}")


def decode_compact(text):
    """Compact quick-check lines → {"mode": "quick", "cards": {id: {"base": …, "tiles": …}}}.

    Line: <id> f<fav|?> p<tile> a<tile> P<sales> A<sales>   (or  <id> E<reason>)
    Only lines that start with a SNKRDUNK id are read, so a header line is harmless."""
    cards = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue
        sid, toks = parts[0], parts[1:]
        if toks and toks[0].startswith("E"):
            cards[sid] = {"base": {"error": unquote(toks[0][1:])}, "tiles": {}}
            continue
        by = {t[0]: t for t in toks}
        fav = by.get("f", "f?")[1:]
        base = {"favorite_count": int(fav) if fav.isdigit() else None, "sales": {}}
        if not fav.isdigit():
            base["favorite_error"] = "favorite count pattern not found"
        for key, grade in (("P", "PSA10"), ("A", "A")):
            if key in by:
                base["sales"][grade] = _sales(by[key], grade)
        if by.get("p") == "p!" or by.get("a") == "a!":
            tiles = {"error": "grade tiles not found"}
        else:
            tiles = {g: _tile(by[k][1:]) for k, g in (("p", "PSA10"), ("a", "A")) if k in by}
        cards[sid] = {"base": base, "tiles": tiles}
    return {"mode": "quick", "cards": cards}


def load_raw(path):
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    if text.lstrip().startswith("{"):
        return json.loads(text), None
    decoded = decode_compact(text)
    return decoded, text


def main():
    args = sys.argv[1:]
    files = [a for a in args if not a.startswith("--")]
    if not files:
        die("Pass the quick-run raw file, e.g. data/incoming/quick-raw.json")
    dry = "--dry-run" in args
    root = Path(__file__).resolve().parent.parent

    raw, compact = load_raw(files[0])
    raw_cards = raw.get("cards") or {}
    if not raw_cards:
        die("The raw file has no cards.")

    if not dry:
        pull = subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=root, text=True, capture_output=True)
        if pull.returncode != 0:
            die("`git pull --ff-only` failed — sort out the local repo first:\n" + (pull.stderr or pull.stdout))

    manifest = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = sorted([s for s in manifest.get("snapshots", []) if s.get("collected_at_jst")],
                   key=lambda s: s["collected_at_jst"])
    if not snaps:
        die("No snapshot to build on yet — run a full check first.")
    base_file = snaps[-1]["file"]
    base = json.loads((root / "data" / "snapshots" / base_file).read_text(encoding="utf-8"))
    base_ts = base.get("collected_at_jst", snaps[-1]["collected_at_jst"])

    out = copy.deepcopy(base)
    now = datetime.now(JST).replace(microsecond=0)
    out["collected_at_jst"] = now.isoformat()
    out["check_mode"] = "quick"
    out["notes"] = ("Quick check: lowest asks read from the SNKRDUNK grade tiles (¥X~) and completed sales "
                    "from 売買履歴 (grade + 1枚). Listing depth, PSA10 population and the pokeca-chart index "
                    "are carried from earlier full checks — see listings_as_of / population_as_of / as_of.")
    out.pop("psa_tier_status", None)
    out.pop("banners", None)

    updated, not_checked, problems = [], [], []
    seen_ids = set()
    for card in out.get("cards", []):
        sid = snkrdunk_id(card.get("url"))
        seen_ids.add(sid)
        name = card.get("card_name_ja", sid)
        card.pop("analysis", None)  # add_snapshot.py carries tiers/peak/verdict forward properly
        rc = raw_cards.get(sid)
        grades = card.setdefault("grades", {})

        # whatever isn't re-measured below keeps its original measurement time
        for g in grades.values():
            if any(k in g for k in LISTING_ARRAYS):
                g.setdefault("listings_as_of", base_ts)
        if card.get("psa10_population") is not None:
            card.setdefault("population_as_of", base_ts)

        base_res = (rc or {}).get("base") or {}
        if not rc or base_res.get("error"):
            reason = base_res.get("error") or "not in this quick run"
            card["quick_note"] = f"not re-checked in this quick run ({reason}); all values carried from {base_ts}"
            not_checked.append(f"{name}: {reason}")
            continue

        if base_res.get("favorite_count") is not None:
            card["favorite_count"] = base_res["favorite_count"]
        tiles = rc.get("tiles") or {}
        sales_all = base_res.get("sales") or {}

        for label, gk in GRADE_KEYS.items():
            g = grades.setdefault(gk, {})
            tile = tiles.get(label) or {"error": "tile not collected"}
            if tile.get("lowest_ask") is not None:
                v = int(tile["lowest_ask"])
                g["lowest_price"] = v
                g["threshold_115pct_of_lowest"] = round(v * 1.15)
                g.pop("error", None)
                g.pop("quick_note", None)
            elif "出品待ち" in (tile.get("note") or ""):
                # no live listings right now: say so, and drop the old order book entirely
                for k in ("lowest_price", "threshold_115pct_of_lowest", "listings_as_of", *LISTING_ARRAYS):
                    g.pop(k, None)
                g["error"] = "no for-sale listings (出品待ち on the grade tile)"
            else:
                g["quick_note"] = f"grade tile not read ({tile.get('error') or tile.get('note')}); lowest ask carried from {base_ts}"
                problems.append(f"{name} {label}: {tile.get('error') or tile.get('note')}")

            s = sales_all.get(label)
            if s and not s.get("error"):
                g["recent_completed_sales"] = s.get("recent_completed_sales", [])
                g.pop("sales_error", None)
                if s.get("sales_note"):
                    g["sales_note"] = s["sales_note"]
                else:
                    g.pop("sales_note", None)
            else:
                g["sales_note"] = f"completed sales not re-read this run ({(s or {}).get('error', 'missing')}); carried from {base_ts}"
                problems.append(f"{name} {label} sales: {(s or {}).get('error', 'missing')}")
        updated.append(name)

    for k, idx in (out.get("pokeca_chart_index") or {}).items():
        if isinstance(idx, dict):
            idx.setdefault("as_of", base_ts)
            idx.pop("same_day_note", None)

    unknown = [sid for sid in raw_cards if sid not in seen_ids]

    print(f"Quick check built on {base_file} ({base_ts}) → {out['collected_at_jst']}")
    print(f"  re-checked: {len(updated)} card(s)")
    if not_checked:
        print("  NOT re-checked (values carried):")
        for n in not_checked:
            print(f"    - {n}")
    if problems:
        print("  partial problems:")
        for p in problems:
            print(f"    - {p}")
    if unknown:
        print("  skipped (not in the tracker yet — add them with a full check): " + ", ".join(unknown))

    if dry:
        print("\nDry run — nothing written.")
        return

    incoming = root / "data" / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    if compact is not None:  # keep what came in, for debugging (gitignored, overwritten each run)
        (incoming / "quick-raw.txt").write_text(compact, encoding="utf-8")
    built = incoming / "latest-run.json"
    built.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print()
    passthrough = [a for a in args if a == "--no-push"]
    r = subprocess.run([sys.executable, str(root / "scripts" / "add_snapshot.py"), str(built), *passthrough], cwd=root)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
