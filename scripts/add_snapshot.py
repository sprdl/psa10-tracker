#!/usr/bin/env python3
"""
Add a new price-check snapshot to the PSA10 tracker.

Usage:
    python3 scripts/add_snapshot.py                 # reads JSON from the clipboard (macOS pbpaste)
    python3 scripts/add_snapshot.py path/to/data.json  # reads JSON from a file instead
    python3 scripts/add_snapshot.py --no-push        # save + commit locally but don't push
    python3 scripts/add_snapshot.py --no-carry-forward  # skip step 3 below for this run

By default this script:
  1. Reads the snapshot JSON (clipboard or file argument)
  2. Saves it to data/snapshots/<YYYYMMDD-HHMM>.json (derived from collected_at_jst)
  3. Carries forward each card's `analysis.tiers`, `analysis.peak`, and DIY-grading fields
     (grading_fee_jpy / shipping_insurance_jpy / raw_tiers) from the previous snapshot, matched
     by card `url` — so a fresh price check never regresses a tracked card back to "tiers not
     yet established". representative_price, price_source, and verdict are NOT carried forward:
     those describe *this* snapshot's own price action and would be actively misleading if
     copied from an older run, so those three are left for a human/Claude review pass after
     each check. The script prints exactly which cards were touched and what still needs review.
  4. Adds/updates the entry in data/manifest.json, keeping it sorted chronologically
  5. Runs `git add`, `git commit`, and `git push` so the site updates automatically
     (GitHub Actions redeploys Pages on every push to main)

Run it from anywhere inside the repo.
"""

import copy
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# analysis.* keys treated as durable judgment that should carry forward run-to-run
# until a human/Claude revises them (tier boundaries, the reference peak, and the
# DIY-grading economics inputs rarely change day to day).
CARRY_FORWARD_KEYS = ("tiers", "peak", "grading_fee_jpy", "shipping_insurance_jpy", "raw_tiers")

# analysis.* keys that describe *this specific snapshot's* observed price action and
# must NOT be silently reused from an older run — they need a fresh look each time.
SNAPSHOT_SPECIFIC_KEYS = ("representative_price", "price_source", "verdict")

# The pokemon-card-price-check skill's native output uses flat psa10_*/a_* field
# names on each card. The app (assets/app.js) and docs/schema.md instead expect a
# nested `grades: {psa10: {...}, raw_a_grade: {...}}` shape. If that raw output is
# ever pasted straight into this script without converting it first, `grades` ends
# up missing entirely and every card silently renders as "no market data yet" —
# this happened for real on 2026-09-18 (run11). These maps let us auto-detect and
# fix that shape instead of writing broken data to the live site.
_PSA10_FIELD_MAP = {
    "psa10_lowest_price": "lowest_price",
    "psa10_threshold_115pct_of_lowest": "threshold_115pct_of_lowest",
    "psa10_top20": "top20_cheapest_listings",
    "psa10_listings_within_15pct": "listings_within_15pct_of_lowest",
    "psa10_count_within_15pct": "count_within_15pct",
    "psa10_count_excluded_over_15pct": "count_excluded_over_15pct",
    "psa10_sales": "recent_completed_sales",
    "psa10_note": "note",
    "psa10_sales_note": "sales_note",
    "psa10_top20_stats": "top20_stats",
    "psa10_error": "error",
}
_A_GRADE_FIELD_MAP = {
    "a_lowest_price": "lowest_price",
    "a_threshold_115pct_of_lowest": "threshold_115pct_of_lowest",
    "a_top20": "top20_cheapest_listings",
    "a_listings_within_15pct": "listings_within_15pct_of_lowest",
    "a_count_within_15pct": "count_within_15pct",
    "a_count_excluded_over_15pct": "count_excluded_over_15pct",
    "a_sales": "recent_completed_sales",
    "a_note": "note",
    "a_sales_note": "sales_note",
    "a_top20_stats": "top20_stats",
    "a_error": "error",
}


def _normalize_card_schema(card: dict) -> dict:
    """Converts one card from the price-check skill's flat psa10_*/a_* field names
    to the nested grades.psa10 / grades.raw_a_grade shape the app expects. A card
    that already has a (truthy) `grades` block is assumed correct and left as-is."""
    if card.get("grades"):
        return card
    if not any(k in card for k in (*_PSA10_FIELD_MAP, *_A_GRADE_FIELD_MAP)):
        return card  # nothing flat to convert — leave whatever shape it has alone

    psa10, raw_a, rest = {}, {}, {}
    for k, v in card.items():
        if k in _PSA10_FIELD_MAP:
            psa10[_PSA10_FIELD_MAP[k]] = v
        elif k in _A_GRADE_FIELD_MAP:
            raw_a[_A_GRADE_FIELD_MAP[k]] = v
        else:
            rest[k] = v
    grades = {}
    if psa10:
        grades["psa10"] = psa10
    if raw_a:
        grades["raw_a_grade"] = raw_a
    rest["grades"] = grades
    return rest


def normalize_schema(data: dict) -> int:
    """Mutates data['cards'] in place, converting any flat-schema cards to the
    nested shape. Returns how many cards were converted."""
    converted = 0
    cards = data.get("cards", [])
    for i, card in enumerate(cards):
        fixed = _normalize_card_schema(card)
        if fixed is not card:
            cards[i] = fixed
            converted += 1
    return converted


def check_timestamp_freshness(data: dict) -> None:
    """Warns (non-fatal) if collected_at_jst looks stale compared to right now.
    This happened for real on 2026-09-19: a price-check run committed at 18:53
    JST claimed collected_at_jst of 09:03 JST (echoed from an earlier run that
    day instead of the run's actual time), and it turned out to also be using
    a pre-update tracked-card list — the stale timestamp was an early warning
    sign that got missed. Assumes the machine running this script is already
    on JST (true for the user's own Mac), so no timezone conversion needed."""
    ts = data.get("collected_at_jst", "")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", ts)
    if not m:
        return
    y, mo, d, h, mi = (int(x) for x in m.groups())
    try:
        claimed = datetime(y, mo, d, h, mi)
    except ValueError:
        return
    now = datetime.now()
    diff_minutes = abs((now - claimed).total_seconds()) / 60
    if diff_minutes > 90:
        print(f"WARNING: collected_at_jst ({ts}) is {diff_minutes:.0f} minutes off from this machine's "
              f"current local time ({now.strftime('%Y-%m-%dT%H:%M')}). This looks like it might be a "
              f"stale/echoed timestamp rather than this run's real collection time — double check "
              f"before trusting this snapshot.", file=sys.stderr)


def check_card_set_drift(data: dict, manifest: dict, snapshots_dir: Path) -> None:
    """Warns (non-fatal) if this run's tracked-card URLs differ from the most
    recently saved snapshot's. Added/removed cards should be a deliberate,
    visible event — not something that silently slips in from a run that used
    a stale copy of the price-check skill's tracked-card list. This happened
    for real on 2026-09-19: a stale run briefly reintroduced Gengar VMAX SA
    right after the user asked for it to be removed, and it landed unnoticed
    because nothing compared the incoming card set to what was already live."""
    entries = [s for s in manifest.get("snapshots", []) if s.get("collected_at_jst")]
    if not entries:
        return
    entries.sort(key=lambda s: s["collected_at_jst"])
    latest_path = snapshots_dir / entries[-1]["file"]
    if not latest_path.exists():
        return
    try:
        latest_data = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    prev_urls = {c.get("url") for c in latest_data.get("cards", []) if c.get("url")}
    new_urls = {c.get("url") for c in data.get("cards", []) if c.get("url")}
    added, removed = new_urls - prev_urls, prev_urls - new_urls
    if not (added or removed):
        return

    print(f"\nWARNING: this run's tracked-card set differs from the most recent saved snapshot "
          f"({entries[-1]['file']}):", file=sys.stderr)
    if added:
        print(f"  + {len(added)} card(s) present now that weren't in the last snapshot:", file=sys.stderr)
        for c in data.get("cards", []):
            if c.get("url") in added:
                print(f"      {c.get('card_name_ja', c.get('url'))}", file=sys.stderr)
    if removed:
        print(f"  - {len(removed)} card(s) missing that WERE in the last snapshot:", file=sys.stderr)
        for c in latest_data.get("cards", []):
            if c.get("url") in removed:
                print(f"      {c.get('card_name_ja', c.get('url'))}", file=sys.stderr)
    print("  If you didn't just add/remove a tracked card on purpose, this run may have used a stale "
          "copy of the price-check skill's tracked-card list — check before trusting it.", file=sys.stderr)


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
        sys.exit("pbpaste not found. On non-macOS, pass a file path instead: add_snapshot.py path/to/data.json")
    except subprocess.CalledProcessError as e:
        sys.exit(f"pbpaste failed: {e}")
    return result.stdout


def load_input(args) -> dict:
    file_args = [a for a in args if not a.startswith("--")]
    if file_args:
        path = Path(file_args[0])
        if not path.exists():
            sys.exit(f"File not found: {path}")
        raw = path.read_text(encoding="utf-8")
    else:
        raw = read_clipboard()
        if not raw.strip():
            sys.exit("Clipboard is empty. Copy the snapshot JSON first, or pass a file path.")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"That doesn't look like valid JSON ({e}). "
                  f"If you passed a file, double check its contents; if using the clipboard, "
                  f"make sure you copied the full JSON output.")


def slug_from_timestamp(collected_at_jst: str) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", collected_at_jst or "")
    if not m:
        # fall back to current time if the field is missing/malformed
        now = datetime.now()
        return now.strftime("%Y%m%d-%H%M")
    y, mo, d, h, mi = m.groups()
    return f"{y}{mo}{d}-{h}{mi}"


def find_previous_snapshot(manifest: dict, snapshots_dir: Path, new_collected_at: str) -> Optional[Path]:
    """Return the snapshot file immediately before new_collected_at, or the most
    recent one overall if new_collected_at is missing/unparseable."""
    entries = [s for s in manifest.get("snapshots", []) if s.get("collected_at_jst")]
    if not entries:
        return None
    entries.sort(key=lambda s: s["collected_at_jst"])
    if new_collected_at:
        earlier = [s for s in entries if s["collected_at_jst"] < new_collected_at]
        candidate = earlier[-1] if earlier else None
    else:
        candidate = entries[-1]
    if not candidate:
        return None
    path = snapshots_dir / candidate["file"]
    return path if path.exists() else None


def carry_forward_analysis(data: dict, prev_path: Optional[Path]) -> None:
    """Mutates data['cards'] in place, copying durable analysis fields forward from
    the previous snapshot for any card matched by url. Prints a summary either way."""
    if prev_path is None:
        print("No previous snapshot found — nothing to carry forward (this may be the first run).")
        return

    try:
        prev_data = json.loads(prev_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: couldn't read previous snapshot {prev_path.name} to carry forward analysis ({e}). Skipping.",
              file=sys.stderr)
        return

    prev_by_url = {c.get("url"): c.get("analysis") for c in prev_data.get("cards", []) if c.get("url")}

    carried, needs_review, untouched_new = [], [], []
    for card in data.get("cards", []):
        url = card.get("url")
        name = card.get("card_name_ja", url or "?")
        prev_analysis = prev_by_url.get(url) if url else None

        if card.get("analysis"):
            # the incoming raw data already has an analysis block (e.g. hand-added
            # before running this script) — leave it alone entirely.
            continue

        if not prev_analysis:
            untouched_new.append(name)
            continue

        forwarded = {k: copy.deepcopy(prev_analysis[k]) for k in CARRY_FORWARD_KEYS if k in prev_analysis}
        if not forwarded:
            untouched_new.append(name)
            continue

        card["analysis"] = forwarded
        carried.append(name)
        if any(k in prev_analysis for k in SNAPSHOT_SPECIFIC_KEYS):
            needs_review.append(name)

    print(f"Carried forward tiers/peak/DIY-fields from {prev_path.name} for {len(carried)} card(s).")
    if carried:
        for n in carried:
            print(f"  - {n}")
    if needs_review:
        print("\nThese cards had a representative_price/price_source/verdict in the previous snapshot "
              "that was intentionally NOT carried forward (it describes the old run's price action, "
              "not this one). Review this run's own numbers and re-add those three fields before "
              "trusting the verdict shown:")
        for n in needs_review:
            print(f"  - {n}")
    if untouched_new:
        print(f"\n{len(untouched_new)} card(s) have no analysis yet (new card, or previous snapshot had none):")
        for n in untouched_new:
            print(f"  - {n}")


def main():
    args = sys.argv[1:]
    no_push = "--no-push" in args
    no_carry_forward = "--no-carry-forward" in args

    root = find_repo_root()
    snapshots_dir = root / "data" / "snapshots"
    manifest_path = root / "data" / "manifest.json"

    data = load_input(args)
    if "collected_at_jst" not in data:
        print("Warning: JSON has no 'collected_at_jst' field — using the current time for the filename.", file=sys.stderr)

    converted = normalize_schema(data)
    if converted:
        print(f"Converted {converted} card(s) from the price-check skill's flat psa10_*/a_* field names "
              f"to the app's nested grades.psa10/raw_a_grade shape.")

    check_timestamp_freshness(data)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("snapshots", [])

    check_card_set_drift(data, manifest, snapshots_dir)

    # Guard against saving an exact duplicate under a new filename (e.g. the same
    # run pasted in twice) — compare against any existing snapshot with the same
    # collected_at_jst timestamp before creating a "-2" file for it.
    same_ts_files = [s["file"] for s in manifest["snapshots"] if s.get("collected_at_jst") == data.get("collected_at_jst")]
    for existing_file in same_ts_files:
        existing_path = snapshots_dir / existing_file
        if not existing_path.exists():
            continue
        try:
            existing_data = json.loads(existing_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if existing_data.get("cards") == data.get("cards"):
            sys.exit(f"This snapshot's cards are byte-identical to the already-saved {existing_file} "
                      f"(same collected_at_jst). Not saving a duplicate — nothing to do.")

    if no_carry_forward:
        print("Skipping analysis carry-forward (--no-carry-forward).")
    else:
        prev_path = find_previous_snapshot(manifest, snapshots_dir, data.get("collected_at_jst", ""))
        carry_forward_analysis(data, prev_path)
    print()

    slug = slug_from_timestamp(data.get("collected_at_jst", ""))
    filename = f"{slug}.json"
    dest = snapshots_dir / filename

    suffix = 2
    while dest.exists():
        filename = f"{slug}-{suffix}.json"
        dest = snapshots_dir / filename
        suffix += 1

    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {dest.relative_to(root)}")

    manifest["snapshots"].append({
        "file": filename,
        "collected_at_jst": data.get("collected_at_jst", ""),
    })
    manifest["snapshots"].sort(key=lambda s: s.get("collected_at_jst", ""))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {manifest_path.relative_to(root)} ({len(manifest['snapshots'])} snapshot(s) total)")

    subprocess.run(["git", "add", "data/manifest.json", str(dest.relative_to(root))], cwd=root, check=True)
    commit_msg = f"snapshot: {data.get('collected_at_jst', filename)}"
    commit = subprocess.run(["git", "commit", "-m", commit_msg], cwd=root)
    if commit.returncode != 0:
        print("Nothing to commit (snapshot may already match the last one) — skipping push.")
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
