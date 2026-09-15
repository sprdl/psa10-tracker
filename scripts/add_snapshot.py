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

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("snapshots", [])

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
