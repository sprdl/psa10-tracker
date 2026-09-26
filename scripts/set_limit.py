#!/usr/bin/env python3
"""
Save (or remove) a personal limit price in data/limits.json from a GitHub issue,
so the limit is the same on every device.

Runs inside GitHub Actions (.github/workflows/limits.yml) when you submit the
site's "Save to all devices" form (label `set-limit`):

    python3 scripts/set_limit.py "$GITHUB_EVENT_PATH"

A limit of 0 (or empty) removes the card's limit. Limits are rounded to ¥500,
the same step the site uses. Commits, pushes, redeploys the site, then comments
and closes the issue. If the form can't be read it comments what's wrong and
leaves the issue open; editing the issue re-runs this.

    python3 scripts/set_limit.py event.json --dry-run
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from log_purchase import (JST, ROOT, URL_RE, FormError, field, finish, gh, git,
                          latest_cards, parse_form, parse_yen)

LIMITS = ROOT / "data" / "limits.json"
STEP = 500


def load():
    return json.loads(LIMITS.read_text(encoding="utf-8")) if LIMITS.exists() else {"limits": {}}


def parse(issue):
    form = parse_form(issue.get("body"))
    m = URL_RE.search(field(form, "snkrdunk url", "card url", "url"))
    if not m:
        raise FormError("No SNKRDUNK product URL found (it should look like https://snkrdunk.com/apparels/123456).")
    url = f"https://snkrdunk.com/apparels/{m.group(1)}"
    raw = field(form, "limit")
    price = 0 if raw.strip() in ("", "0", "¥0") else parse_yen(raw, "Limit price")
    if price:
        price = max(STEP, round(price / STEP) * STEP)
    return url, price


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        sys.exit(__doc__)
    issue = json.loads(Path(args[0]).read_text(encoding="utf-8"))["issue"]
    if "set-limit" not in {l["name"] for l in issue.get("labels", [])}:
        print("Not a limit issue; nothing to do.")
        return
    try:
        url, price = parse(issue)
    except FormError as e:
        finish(issue, f"Couldn't save this limit: {e}\n\nEdit the issue to fix it and it will be retried automatically.", False, dry)
        return
    card = next((c for c in latest_cards() if c.get("url", "").rstrip("/") == url), None)
    name = (card or {}).get("card_name_ja") or url
    def apply(store):
        lim = store.setdefault("limits", {})
        if price:
            lim[url] = {"price": price, "set": datetime.now(JST).isoformat(timespec="seconds"), "issue": issue["number"]}
            return (f"Saved your limit for **{name}**: ¥{price:,}. Every device shows it once the site updates (about a minute).",
                    f"limits: {name} ¥{price:,} (#{issue['number']})")
        existed = lim.pop(url, None)
        return ((f"Removed your limit for **{name}**." if existed else f"**{name}** had no saved limit; nothing to remove.")
                + " The site updates in about a minute.", f"limits: remove {name} (#{issue['number']})")

    if dry:
        store = load(); msg, _ = apply(store)
        print(json.dumps(store, ensure_ascii=False, indent=1)); print(msg); return
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    # Several limit forms submitted at once run in parallel. Each attempt starts from the
    # latest main, re-applies this one change and pushes, so they never conflict.
    pushed = changed = False
    for attempt in range(6):
        git("fetch", "-q", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        store = load()
        msg, commit_msg = apply(store)
        LIMITS.write_text(json.dumps(store, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        git("add", "data/limits.json")
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
            break  # already saved (e.g. a re-run)
        git("commit", "-q", "-m", commit_msg)
        if subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=ROOT).returncode == 0:
            pushed = changed = True
            break
        time.sleep(3 + attempt * 2)
    else:
        raise RuntimeError("git push failed six times")
    if not card:
        msg += "\n\nNote: this card isn't on the tracker right now."
    if changed:
        # Pushes made with the Actions token don't start other workflows, so start the Pages deploy explicitly.
        gh("POST", "/actions/workflows/deploy.yml/dispatches", {"ref": "main"})
    finish(issue, msg, True, dry)


if __name__ == "__main__":
    main()
