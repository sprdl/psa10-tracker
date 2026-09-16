#!/usr/bin/env python3
"""
Record a card you've actually bought in the PSA10 tracker's portfolio section.

Usage:
    python3 scripts/add_holding.py                   # reads JSON from the clipboard (macOS pbpaste)
    python3 scripts/add_holding.py path/to/holding.json  # reads JSON from a file instead
    python3 scripts/add_holding.py --no-push          # save + commit locally but don't push

Input is one holding object, or a JSON array of several, shaped like:

    {
      "card_url": "https://snkrdunk.com/apparels/...",   // must match a tracked card's `url`
      "card_name_ja": "...",                              // denormalized label, kept even if
                                                            // the card later drops out of tracking
      "image_url": "https://.../card-photo.jpg",          // optional, only used if card_url stops matching
      "condition": "psa10",                                // "psa10" (bought already-slabbed) or
                                                            // "raw_to_grade" (bought raw, paying to grade it)
      "purchase_price_jpy": 65000,
      "purchase_date": "2026-09-20",
      "grading_fee_jpy": 9980,                             // only meaningful if condition is raw_to_grade
      "shipping_insurance_jpy": 2000,                      // optional, defaults to 2000 if grading_fee_jpy is set
      "notes": "optional free text"
    }

The app matches `card_url` against the live tracker data to show current price and
unrealized P&L — it never stores a computed value here, only what you actually paid
and when (see docs/schema.md). This script only appends; to edit or remove a
holding, edit data/holdings.json directly and commit as usual.

By default this script:
  1. Reads the holding JSON (clipboard or file argument)
  2. Validates the required fields are present
  3. Appends it to data/holdings.json
  4. Runs `git add`, `git commit`, and `git push` so the site updates automatically

Run it from anywhere inside the repo.
"""

import json
import subprocess
import sys
from pathlib import Path

REQUIRED_FIELDS = ("card_url", "card_name_ja", "purchase_price_jpy", "purchase_date")


def find_repo_root() -> Path:
    here = Path(__file__).resolve().parent
    root = here.parent
    if not (root / "data" / "manifest.json").exists():
        sys.exit(f"Couldn't find data/manifest.json under {root} — is the repo layout intact?")
    return root


def read_clipboard() -> str:
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
    except FileNotFoundError:
        sys.exit("pbpaste not found. On non-macOS, pass a file path instead: add_holding.py path/to/holding.json")
    except subprocess.CalledProcessError as e:
        sys.exit(f"pbpaste failed: {e}")
    return result.stdout


def load_input(args) -> list:
    file_args = [a for a in args if not a.startswith("--")]
    if file_args:
        path = Path(file_args[0])
        if not path.exists():
            sys.exit(f"File not found: {path}")
        raw = path.read_text(encoding="utf-8")
    else:
        raw = read_clipboard()
        if not raw.strip():
            sys.exit("Clipboard is empty. Copy the holding JSON first, or pass a file path.")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"That doesn't look like valid JSON ({e}). "
                  f"If you passed a file, double check its contents; if using the clipboard, "
                  f"make sure you copied the full JSON output.")

    entries = data if isinstance(data, list) else [data]
    for entry in entries:
        missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
        if missing:
            sys.exit(f"Holding is missing required field(s): {', '.join(missing)}\n{json.dumps(entry, ensure_ascii=False, indent=2)}")
        if entry.get("condition") not in (None, "psa10", "raw_to_grade"):
            sys.exit(f"condition must be \"psa10\" or \"raw_to_grade\", got: {entry.get('condition')!r}")
    return entries


def main():
    args = sys.argv[1:]
    no_push = "--no-push" in args

    root = find_repo_root()
    holdings_path = root / "data" / "holdings.json"

    new_entries = load_input(args)

    if holdings_path.exists():
        store = json.loads(holdings_path.read_text(encoding="utf-8"))
    else:
        store = {"holdings": []}
    store.setdefault("holdings", [])

    store["holdings"].extend(new_entries)
    holdings_path.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added {len(new_entries)} holding(s):")
    for e in new_entries:
        print(f"  - {e['card_name_ja']} — ¥{e['purchase_price_jpy']:,} on {e['purchase_date']}")
    print(f"Updated {holdings_path.relative_to(root)} ({len(store['holdings'])} holding(s) total)")

    subprocess.run(["git", "add", str(holdings_path.relative_to(root))], cwd=root, check=True)
    names = ", ".join(e["card_name_ja"] for e in new_entries)
    commit_msg = f"holdings: add {names}"
    commit = subprocess.run(["git", "commit", "-m", commit_msg], cwd=root)
    if commit.returncode != 0:
        print("Nothing to commit — skipping push.")
        return

    if no_push:
        print("Committed locally. Skipping push (--no-push).")
        return

    push = subprocess.run(["git", "push"], cwd=root)
    if push.returncode != 0:
        sys.exit("git push failed — check your git remote/auth, then run `git push` manually.")
    print("Pushed. GitHub Actions will redeploy the site in a minute or two.")


if __name__ == "__main__":
    main()
