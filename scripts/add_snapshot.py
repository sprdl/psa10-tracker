#!/usr/bin/env python3
"""
Add a new price-check snapshot to the PSA10 tracker.

Usage:
    python3 scripts/add_snapshot.py                 # reads JSON from the clipboard (macOS pbpaste)
    python3 scripts/add_snapshot.py path/to/data.json  # reads JSON from a file instead
    python3 scripts/add_snapshot.py --no-push        # save + commit locally but don't push

By default this script:
  1. Reads the snapshot JSON (clipboard or file argument)
  2. Saves it to data/snapshots/<YYYYMMDD-HHMM>.json (derived from collected_at_jst)
  3. Adds/updates the entry in data/manifest.json, keeping it sorted chronologically
  4. Runs `git add`, `git commit`, and `git push` so the site updates automatically
     (GitHub Actions redeploys Pages on every push to main)

Run it from anywhere inside the repo.
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


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


def main():
    args = sys.argv[1:]
    no_push = "--no-push" in args

    root = find_repo_root()
    snapshots_dir = root / "data" / "snapshots"
    manifest_path = root / "data" / "manifest.json"

    data = load_input(args)
    if "collected_at_jst" not in data:
        print("Warning: JSON has no 'collected_at_jst' field — using the current time for the filename.", file=sys.stderr)

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

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("snapshots", [])
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
