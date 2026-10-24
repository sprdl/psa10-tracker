#!/usr/bin/env python3
"""
Build the folder GitHub Pages publishes (.github/workflows/deploy.yml): the repo without what the site never loads.

    python3 scripts/site_bundle.py _site

Left out (2026-10-16):
  - snapshots older than SITE_DAYS before the newest check. They stay in the repo (the scripts read them all:
    build_history.py, build_calls.py, the studies), but the site only offers checks from the last SITE_DAYS in its
    check picker (assets/app.js SITE_DAYS), and its charts come from data/history.json. Before, every deploy
    uploaded all of them (13 MB after a month, growing ~0.8 MB a day).
  - .git, .github, data/incoming (local run files), __pycache__, tests, scripts, pricecheck, widget, docs.
"""
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_DAYS = 30   # keep in step with SITE_DAYS in assets/app.js
# never published, even from a local build (2026-10-24 security audit): credentials and Finder metadata
SKIP_FILES = {".git-credentials", ".psa10-git-credentials", ".DS_Store", ".env"}
SKIP_DIRS = {".git", ".github", ".claude", "_site", "__pycache__", "tests", "scripts", "pricecheck", "widget", "docs", "node_modules"}


def keep_snapshots(root=ROOT):
    m = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = [s for s in m.get("snapshots", []) if s.get("collected_at_jst")]
    if not snaps:
        return set()
    newest = max(datetime.fromisoformat(s["collected_at_jst"]) for s in snaps)
    cut = newest - timedelta(days=SITE_DAYS + 1)   # a day more: the oldest offered check needs the one before it
    return {s["file"] for s in snaps if datetime.fromisoformat(s["collected_at_jst"]) >= cut}


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "_site").resolve()
    if out.exists():
        shutil.rmtree(out)
    keep = keep_snapshots()
    snapdir = (ROOT / "data" / "snapshots").resolve()
    incoming = (ROOT / "data" / "incoming").resolve()

    def ignore(d, names):
        d = Path(d).resolve()
        skip = {n for n in names if n in SKIP_DIRS or (d == ROOT and n == out.name)}
        skip |= {n for n in names if n in SKIP_FILES}
        if d == ROOT / "data":
            skip |= {n for n in names if (d / n).resolve() == incoming}
        if d == snapdir:
            skip |= {n for n in names if n.endswith(".json") and n not in keep}
        return skip

    shutil.copytree(ROOT, out, ignore=ignore)
    n_all = len(list(snapdir.glob("*.json")))
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"site bundle {out}: {len(keep)} of {n_all} snapshots, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
