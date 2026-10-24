#!/usr/bin/env python3
"""
Small read-only lookups for the skills and procedures, so an unattended run never needs `python3 -c "…"` (a local
run's allow list only lets the repo's own scripts run: .claude/settings.json, 2026-10-24 security audit).

    python3 scripts/skill_query.py holdings
        One line per logged copy: id, card URL, condition, paid (JPY), grading + shipping (JPY), purchase date.
    python3 scripts/skill_query.py mytier
        The My-tier index: latest date, level and 30-day change.
    python3 scripts/skill_query.py checkjson <file>
        Checks that a file is valid JSON (e.g. data/incoming/apply_analysis-in.txt before applying it):
        prints "JSON OK: <type> with N entries" or the parse error with its line and column. Reads only.
"""
import datetime as D
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def holdings():
    for h in json.loads((ROOT / "data" / "holdings.json").read_text(encoding="utf-8"))["holdings"]:
        print(h["id"], h["card_url"], h["condition"], h["purchase_price_jpy"],
              h.get("grading_fee_jpy", 0) + h.get("shipping_insurance_jpy", 0), h["purchase_date"])


def mytier():
    s = json.loads((ROOT / "data" / "custom_index.json").read_text(encoding="utf-8"))["series"]
    last = s[-1]
    cut = (D.date.fromisoformat(last["d"]) - D.timedelta(30)).isoformat()
    old = [e for e in s if e["d"] <= cut]
    chg = f"{(last['level'] / old[-1]['level'] - 1) * 100:+.1f}%" if old else "n/a (under 30 days of data)"
    print(last["d"], last["level"], "30d:", chg)


def checkjson(path):
    p = Path(path)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"JSON ERROR in {path}: {e.msg} at line {e.lineno}, column {e.colno}")
    except OSError as e:
        sys.exit(f"can't read {path}: {e}")
    n = len(d) if isinstance(d, (dict, list)) else 1
    print(f"JSON OK: {type(d).__name__} with {n} entr{'y' if n == 1 else 'ies'}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["holdings"]:
        holdings()
    elif a == ["mytier"]:
        mytier()
    elif len(a) == 2 and a[0] == "checkjson":
        checkjson(a[1])
    else:
        sys.exit(__doc__)
