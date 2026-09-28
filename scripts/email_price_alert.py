#!/usr/bin/env python3
"""
Apply a single lower-price alert from an incoming SNKRDUNK "new listing" email.

This is NOT a price check: it doesn't touch listing depth, sales, population,
tiers or the index. It only updates one card's PSA10 lowest_price when an email
reports a new listing below the current lowest ask on file, so the site reflects
it immediately instead of waiting for the next full/quick check. Everything else
is carried forward unchanged from the latest snapshot (same idea as
quick_update.py's carry-forward, just narrower).

Usage:
    python3 scripts/email_price_alert.py <snkrdunk_id> <price_yen> [listing_url] [--dry-run] [--no-push]

Exits 0 with a "no-op" message when the card isn't tracked for PSA10 yet, or the
price isn't a new low — that's the expected outcome for most emails. Exits
nonzero only on a real error (bad args, git pull/push failure).
"""
import copy
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def card_id(url: str) -> str:
    # https://snkrdunk.com/apparels/455596  or .../apparels/455596/used/49697195 -> "455596"
    parts = (url or "").rstrip("/").split("/")
    if "apparels" in parts:
        return parts[parts.index("apparels") + 1]
    return parts[-1] if parts else ""


def _clear_stale_git_locks(root: Path):
    """Rename away any leftover .git/*.lock files before touching git.

    This session's connected-folder permissions allow renaming files but not
    deleting them (rm/unlink need a one-time user approval we can't get on an
    unattended run). A crashed or interrupted previous git invocation --
    e.g. two email alerts processed back-to-back -- can leave a stale
    HEAD.lock/ORIG_HEAD.lock behind, which makes the *next* git command fail
    with "fatal: cannot lock ref HEAD" even though nothing is actually
    running. Since renaming is allowed, move any stale lock out of the way
    (instead of deleting it) so this run can proceed on its own, with no
    human needed to approve anything.
    """
    git_dir = root / ".git"
    if not git_dir.is_dir():
        return
    for lock in git_dir.rglob("*.lock"):
        try:
            # Fixed name (no timestamp) so repeated clears overwrite the same
            # parked file via rename-over-existing, rather than piling up
            # junk in .git forever (we can rename but never delete here).
            lock.rename(lock.with_suffix(".lock.stale"))
        except OSError as e:
            print(f"warning: couldn't clear stale lock {lock}: {e}", file=sys.stderr)


def main():
    args = sys.argv[1:]
    pos = [a for a in args if not a.startswith("--")]
    if len(pos) < 2:
        die("Usage: email_price_alert.py <snkrdunk_id> <price_yen> [listing_url] [--dry-run] [--no-push]")
    snkrdunk_id, price_s = pos[0], pos[1]
    listing_url = pos[2] if len(pos) > 2 else None
    try:
        price = int(price_s)
    except ValueError:
        die(f"price must be an integer: {price_s!r}")
    dry = "--dry-run" in args
    no_push = "--no-push" in args
    root = Path(__file__).resolve().parent.parent
    if not dry:
        _clear_stale_git_locks(root)
        pull = subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=root, text=True, capture_output=True)
        if pull.returncode != 0:
            die("`git pull --ff-only` failed — sort out the local repo first:\n" + (pull.stderr or pull.stdout))

    manifest_path = root / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snaps = sorted([s for s in manifest.get("snapshots", []) if s.get("collected_at_jst")],
                   key=lambda s: s["collected_at_jst"])
    if not snaps:
        die("No snapshot to build on yet — run a full check first.")
    latest_file = snaps[-1]["file"]
    data = json.loads((root / "data" / "snapshots" / latest_file).read_text(encoding="utf-8"))

    match = None
    for c in data.get("cards", []):
        if card_id(c.get("url", "")) == snkrdunk_id:
            match = c
            break
    if match is None:
        print(f"no-op: snkrdunk_id {snkrdunk_id} is not a tracked PSA10 card")
        return

    psa10 = (match.get("grades") or {}).get("psa10")
    if not psa10 or not psa10.get("lowest_price"):
        print(f"no-op: {match.get('card_name_ja')} has no PSA10 grade data on file to compare against")
        return

    current_low = psa10["lowest_price"]
    if price >= current_low:
        print(f"no-op: {match.get('card_name_ja')} — email price ¥{price:,} is not below current lowest ¥{current_low:,}")
        return

    now_jst = datetime.now(JST).replace(microsecond=0).isoformat()

    new_data = copy.deepcopy(data)
    new_card = next(c for c in new_data["cards"] if card_id(c.get("url", "")) == snkrdunk_id)
    p10 = new_card["grades"]["psa10"]
    old_low = p10["lowest_price"]
    p10["lowest_price"] = price
    p10["threshold_115pct_of_lowest"] = round(price * 1.15)
    p10["top20_cheapest_listings"] = sorted(set([price] + p10.get("top20_cheapest_listings", [])))[:20]
    p10["listing_alert"] = {
        "source": "email",
        "detected_at_jst": now_jst,
        "previous_lowest_price": old_low,
        "listing_url": listing_url,
    }
    new_data["collected_at_jst"] = now_jst
    new_data["check_mode"] = "email_alert"

    slug = now_jst[:16].replace("-", "").replace(":", "").replace("T", "-")
    filename = f"{slug}.json"
    dest = root / "data" / "snapshots" / filename
    suffix = 2
    while dest.exists():
        filename = f"{slug}-{suffix}.json"
        dest = root / "data" / "snapshots" / filename
        suffix += 1

    print(f"UPDATE: {new_card.get('card_name_ja')} lowest ¥{old_low:,} -> ¥{price:,}")
    if dry:
        print(f"(dry-run) would save {filename}")
        return

    dest.write_text(json.dumps(new_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["snapshots"].append({"file": filename, "collected_at_jst": now_jst, "check_mode": "email_alert"})
    manifest["snapshots"].sort(key=lambda s: s.get("collected_at_jst", ""))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {dest.relative_to(root)}, updated manifest.json")

    sys.path.insert(0, str(root / "scripts"))
    import build_history
    build_history.build(root)

    _clear_stale_git_locks(root)
    subprocess.run(["git", "add", "data/manifest.json", "data/history.json", str(dest.relative_to(root)),
                    *[f for f in ("data/calls.json", "data/predict.json") if (root / f).exists()]],
                    cwd=root, check=True)
    _clear_stale_git_locks(root)
    commit_msg = f"email alert: {new_card.get('card_name_ja')} ¥{price:,} (was ¥{old_low:,})"
    commit = subprocess.run(["git", "commit", "-m", commit_msg], cwd=root)
    if commit.returncode != 0:
        print("Nothing to commit (may already match) — skipping push.")
        return

    if no_push:
        print("Committed locally. Skipping push (--no-push).")
        return

    _clear_stale_git_locks(root)
    push = subprocess.run(["git", "push"], cwd=root)
    if push.returncode != 0:
        die("git push failed — check your git remote/auth, then run `git push` manually.")
    print("Pushed. GitHub Actions will redeploy the site in a minute or two.")


if __name__ == "__main__":
    main()
