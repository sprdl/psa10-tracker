#!/usr/bin/env python3
"""
Handle "Add card" requests (GitHub issues labeled `add-card`) and the repo's
tracked-card list (data/tracked_cards.json).

    python3 scripts/card_requests.py list
        Open add-card requests as JSON: [{"number", "title", "snkrdunk_id", "url"}].
        snkrdunk_id is null if no SNKRDUNK product URL could be found in the issue.

    python3 scripts/card_requests.py add <issue#> --name "<card_name_ja>" [--mode daily|weekly_until_graded]
                                    [--image URL] [--altema URL] [--note TEXT] [--dry-run]
        Adds the requested card to data/tracked_cards.json, commits, pushes, then
        comments on and closes the issue. A card that's already tracked just gets
        the issue closed with a note.

    python3 scripts/card_requests.py set <snkrdunk_id> key=value [key=value ...] [--dry-run]
        Update fields of a card in data/tracked_cards.json (image_url, altema_url,
        altema_mode, note, card_name_ja), commit and push.

    python3 scripts/card_requests.py reject <issue#> "<reason>" [--dry-run]
        Comment the reason and close the issue (e.g. the URL isn't a SNKRDUNK card).

    python3 scripts/card_requests.py ensure-label
        Create the `add-card` label if the repo doesn't have it yet (one-time).

Auth: the same credential file git uses for this repo (via `git credential fill`),
so no token is ever typed or printed. The token needs Issues: read/write for
add/reject/ensure-label; `list` works without it (the repo is public).
"""

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = "sprdl/psa10-tracker"
API = f"https://api.github.com/repos/{REPO}"
LABEL = "add-card"
JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
TRACKED = ROOT / "data" / "tracked_cards.json"
SETTABLE = {"image_url", "altema_url", "altema_mode", "note", "card_name_ja"}
URL_RE = re.compile(r"https?://(?:www\.)?snkrdunk\.com/(?:en/)?apparels/(\d+)")


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def token():
    """Read the token for github.com from git's configured credential helper."""
    r = subprocess.run(["git", "credential", "fill"], cwd=ROOT, input="protocol=https\nhost=github.com\n\n",
                       text=True, capture_output=True, env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"})
    for line in r.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return None


def api(method, path, body=None, auth=True):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "psa10-tracker-card-requests"}
    if auth:
        t = token()
        if not t:
            die("no GitHub credential found — is the repo's credential file set up? (see README)")
        headers["Authorization"] = f"Bearer {t}"
    data = json.dumps(body).encode() if body is not None else None
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code in (401, 403):
            die(f"GitHub refused the request ({e.code}). The token probably lacks the "
                f"'Issues: Read and write' permission, or has expired. Details: {detail}")
        die(f"GitHub API {method} {path} failed ({e.code}): {detail}")
    except urllib.error.URLError as e:
        die(f"couldn't reach GitHub: {e.reason}")


def load_tracked():
    return json.loads(TRACKED.read_text(encoding="utf-8")) if TRACKED.exists() else {"cards": []}


def save_tracked(d):
    TRACKED.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def latest_snapshot_ids():
    m = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = sorted([s for s in m.get("snapshots", []) if s.get("collected_at_jst")], key=lambda s: s["collected_at_jst"])
    if not snaps:
        return set()
    d = json.loads((ROOT / "data" / "snapshots" / snaps[-1]["file"]).read_text(encoding="utf-8"))
    return {c.get("url", "").rstrip("/").split("/")[-1] for c in d.get("cards", [])}


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=check,
                          env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"})


def commit_and_push(message):
    git("add", str(TRACKED.relative_to(ROOT)))
    c = git("commit", "-m", message, check=False)
    if c.returncode != 0:
        print("Nothing to commit.")
        return
    p = git("push", check=False)
    if p.returncode != 0:
        die("git push failed:\n" + (p.stderr or p.stdout))
    print("Committed and pushed data/tracked_cards.json.")


def flag(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            die(f"{name} needs a value")
        return args[i + 1]
    return default


# ---------- commands ----------

def cmd_list(args):
    t = token()
    issues = api("GET", f"/issues?state=open&labels={LABEL}&per_page=50", auth=bool(t))
    out = []
    for it in issues:
        if "pull_request" in it:
            continue
        m = URL_RE.search((it.get("title") or "") + "\n" + (it.get("body") or ""))
        out.append({"number": it["number"], "title": it.get("title"),
                    "snkrdunk_id": m.group(1) if m else None,
                    "url": f"https://snkrdunk.com/apparels/{m.group(1)}" if m else None})
    print(json.dumps(out, ensure_ascii=False))


def cmd_add(args):
    if len(args) < 1 or not args[0].isdigit():
        die("usage: add <issue#> --name \"<card_name_ja>\" [--mode ...] [--image URL] [--altema URL] [--note TEXT]")
    num = int(args[0])
    dry = "--dry-run" in args
    name = flag(args, "--name")
    if not name:
        die("--name is required (use the title SNKRDUNK shows for the card)")
    mode = flag(args, "--mode", "weekly_until_graded")
    if mode not in ("daily", "weekly_until_graded"):
        die("--mode must be daily or weekly_until_graded")

    issue = api("GET", f"/issues/{num}", auth=bool(token()))
    m = URL_RE.search((issue.get("title") or "") + "\n" + (issue.get("body") or ""))
    if not m:
        die(f"issue #{num} has no SNKRDUNK product URL — use `reject {num} \"...\"` instead")
    sid = m.group(1)

    tracked = load_tracked()
    already = sid in {c["snkrdunk_id"] for c in tracked["cards"]} or sid in latest_snapshot_ids()
    if already:
        msg = f"Already tracked: {name} (https://snkrdunk.com/apparels/{sid}). Nothing to add."
    else:
        entry = {"snkrdunk_id": sid, "card_name_ja": name, "url": f"https://snkrdunk.com/apparels/{sid}",
                 "image_url": flag(args, "--image", ""), "altema_url": flag(args, "--altema", ""),
                 "altema_mode": mode, "note": flag(args, "--note", f"added from issue #{num}"),
                 "added": datetime.now(JST).strftime("%Y-%m-%d")}
        tracked["cards"].append(entry)
        msg = (f"Added to the tracker: **{name}** (https://snkrdunk.com/apparels/{sid}). "
               f"It will appear on the site after this price check publishes.")
    print(msg)
    if dry:
        print("(dry run — nothing written, issue left open)")
        return
    if not already:
        save_tracked(tracked)
        commit_and_push(f"track {name} (requested in #{num})")
    api("POST", f"/issues/{num}/comments", {"body": msg})
    api("PATCH", f"/issues/{num}", {"state": "closed", "state_reason": "completed"})
    print(f"Closed issue #{num}.")


def cmd_set(args):
    if not args:
        die("usage: set <snkrdunk_id> key=value [...]")
    sid, pairs = args[0], [a for a in args[1:] if "=" in a and not a.startswith("--")]
    dry = "--dry-run" in args
    tracked = load_tracked()
    card = next((c for c in tracked["cards"] if c["snkrdunk_id"] == sid), None)
    if not card:
        die(f"{sid} isn't in data/tracked_cards.json (cards in the skill's own cards.json are changed via the skill)")
    for p in pairs:
        k, v = p.split("=", 1)
        if k not in SETTABLE:
            die(f"can't set '{k}' (allowed: {sorted(SETTABLE)})")
        if k == "altema_mode" and v not in ("daily", "weekly_until_graded"):
            die("altema_mode must be daily or weekly_until_graded")
        card[k] = v
        print(f"{sid}: {k} = {v}")
    if dry:
        print("(dry run — nothing written)")
        return
    save_tracked(tracked)
    commit_and_push(f"update tracked card {sid}: {', '.join(p.split('=')[0] for p in pairs)}")


def cmd_reject(args):
    if len(args) < 2 or not args[0].isdigit():
        die('usage: reject <issue#> "<reason>"')
    num, reason = int(args[0]), args[1]
    msg = f"Couldn't add this card: {reason}"
    print(msg)
    if "--dry-run" in args:
        print("(dry run — issue left open)")
        return
    api("POST", f"/issues/{num}/comments", {"body": msg})
    api("PATCH", f"/issues/{num}", {"state": "closed", "state_reason": "not_planned"})
    print(f"Closed issue #{num}.")


def cmd_ensure_label(args):
    labels = api("GET", "/labels?per_page=100")
    if any(l.get("name") == LABEL for l in labels):
        print(f"Label '{LABEL}' already exists.")
        return
    api("POST", "/labels", {"name": LABEL, "color": "d6903f",
                            "description": "Request to start tracking a card (picked up by the next price check)"})
    print(f"Created label '{LABEL}'.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd, rest = sys.argv[1], sys.argv[2:]
    {"list": cmd_list, "add": cmd_add, "set": cmd_set, "reject": cmd_reject,
     "ensure-label": cmd_ensure_label}.get(cmd, lambda a: die(f"unknown command '{cmd}'"))(rest)


if __name__ == "__main__":
    main()
