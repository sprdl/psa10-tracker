#!/usr/bin/env python3
"""
Save a written analysis for one card to data/insights.json (shown at the top of the card's
"What stands out" panel on the site), then commit and push.

    python3 scripts/set_insight.py <snkrdunk_id> --headline "One-line takeaway" [--signals "…"] [--no-push] <<'EOF'
    Two to five sentences: what is happening, the likely reason, what it means for buying
    (tiers / your limit), and what to watch next.
    EOF
    python3 scripts/set_insight.py --remove <snkrdunk_id>

The full check writes these for the cards scripts/outliers.py flags (at most 3 per run).
A newer analysis replaces the card's previous one; entries older than 30 days are dropped.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "insights.json"


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def arg(name):
    a = sys.argv
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else None


def main():
    a = sys.argv[1:]
    if not a:
        die(__doc__)
    remove = "--remove" in a
    sid = arg("--remove") if remove else a[0]
    if not sid or not sid.isdigit():
        die("pass the card's SNKRDUNK id first")
    url = f"https://snkrdunk.com/apparels/{sid}"
    if "--no-push" not in a:
        subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=ROOT)
    data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    data.setdefault("about", "Analyses written by the full price check for cards that stand out (scripts/outliers.py). "
                             "Shown on the card page above the automatic findings. Edit with scripts/set_insight.py.")
    items = data.setdefault("insights", {})
    now = datetime.now(JST).replace(microsecond=0)
    for k in [k for k, v in items.items() if datetime.fromisoformat(v["written"]) < now - timedelta(days=30)]:
        del items[k]
    if remove:
        if items.pop(url, None) is None:
            die(f"no analysis stored for {sid}")
        msg = f"insight: remove {sid}"
    else:
        text = sys.stdin.read().strip()
        if len(text) < 40:
            die("write the analysis on stdin (a heredoc), at least a couple of sentences")
        items[url] = {"written": now.isoformat(), "headline": arg("--headline") or "", "text": text,
                      "signals": arg("--signals") or ""}
        msg = f"insight: {sid} {arg('--headline') or ''}".strip()
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"saved {PATH.relative_to(ROOT)} ({len(items)} card(s) with an analysis)")
    if "--no-push" in a:
        return
    for cmd in (["git", "add", str(PATH)], ["git", "commit", "-q", "-m", msg], ["git", "push", "-q"]):
        r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        if r.returncode != 0:
            die(f"{' '.join(cmd)} failed:\n{r.stderr or r.stdout}")
    print("Pushed.")


if __name__ == "__main__":
    main()
