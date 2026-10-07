#!/usr/bin/env python3
"""
Save (or remove) a personal limit price in data/limits.json from a GitHub issue,
so the limit is the same on every device. The same script saves sell targets for cards you own
(label `set-sell-target`) in data/sell_targets.json: same rules, key "targets", form field "Sell target".

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
from issue_labels import labels_of

LIMITS = ROOT / "data" / "limits.json"
TARGETS = ROOT / "data" / "sell_targets.json"
STEP = 500


def load(path=LIMITS, key="limits"):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {key: {}}


def parse(issue, field_name="limit", what="Limit price"):
    form = parse_form(issue.get("body"))
    m = URL_RE.search(field(form, "snkrdunk url", "card url", "url"))
    if not m:
        raise FormError("No SNKRDUNK product URL found (it should look like https://snkrdunk.com/apparels/123456).")
    url = f"https://snkrdunk.com/apparels/{m.group(1)}"
    raw = field(form, field_name)
    price = 0 if raw.strip() in ("", "0", "¥0") else parse_yen(raw, what)
    if price:
        price = max(STEP, round(price / STEP) * STEP)
    return url, price


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        sys.exit(__doc__)
    issue = json.loads(Path(args[0]).read_text(encoding="utf-8"))["issue"]
    labels = labels_of(issue)  # infers the label from the title if GitHub dropped it
    if not labels & {"set-limit", "set-sell-target"}:
        print("Not a limit or sell-target issue; nothing to do.")
        return
    target = "set-sell-target" in labels
    path, key, noun = (TARGETS, "targets", "sell target") if target else (LIMITS, "limits", "limit")
    rel = path.relative_to(ROOT).as_posix()
    try:
        url, price = parse(issue, "sell target", "Sell target") if target else parse(issue)
    except FormError as e:
        finish(issue, f"Couldn't save this {noun}: {e}\n\nEdit the issue to fix it and it will be retried automatically.", False, dry)
        return
    card = next((c for c in latest_cards() if c.get("url", "").rstrip("/") == url), None)
    name = (card or {}).get("card_name_ja") or url
    def apply(store):
        lim = store.setdefault(key, {})
        if price:
            lim[url] = {"price": price, "set": datetime.now(JST).isoformat(timespec="seconds"), "issue": issue["number"]}
            return (f"Saved your {noun} for **{name}**: ¥{price:,}. Every device shows it once the site updates (about a minute).",
                    f"{key}: {name} ¥{price:,} (#{issue['number']})")
        existed = lim.pop(url, None)
        return ((f"Removed your {noun} for **{name}**." if existed else f"**{name}** had no saved {noun}; nothing to remove.")
                + " The site updates in about a minute.", f"{key}: remove {name} (#{issue['number']})")

    if dry:
        store = load(path, key); msg, _ = apply(store)
        print(json.dumps(store, ensure_ascii=False, indent=1)); print(msg); return
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    # Several limit forms submitted at once run in parallel. Each attempt starts from the
    # latest main, re-applies this one change and pushes, so they never conflict.
    pushed = changed = False
    for attempt in range(6):
        git("fetch", "-q", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        store = load(path, key)
        msg, commit_msg = apply(store)
        path.write_text(json.dumps(store, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        git("add", rel)
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
