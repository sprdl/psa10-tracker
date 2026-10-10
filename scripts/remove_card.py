#!/usr/bin/env python3
"""
Remove a card from the tracker, or restore one, from a GitHub issue (the site's "Remove card" /
"Restore" buttons open pre-filled forms; .github/workflows/cards.yml runs this).

    python3 scripts/remove_card.py "$GITHUB_EVENT_PATH" [--dry-run]

Removal adds the card's SNKRDUNK id to data/removed_cards.json. Nothing else is deleted: the card's
history, tiers and analysis stay in old snapshots, and its entry in data/tracked_cards.json or
pricecheck/references/cards.json stays too, so a restore brings it straight back. While removed:
  - the site hides it everywhere,
  - pricecheck/plan.py and assemble.py leave it out of price checks,
  - add_snapshot.py drops it from new snapshots.
A card you've logged as bought can't be removed (delete the purchase first).

    python3 scripts/remove_card.py --list        # removed cards, for checking by hand
"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from log_purchase import JST, ROOT, FormError, field, finish, gh, git, parse_form  # noqa: E402

PATH = ROOT / "data" / "removed_cards.json"
ID_RE = re.compile(r"(?:apparels/)?(\d{3,9})")


def load():
    if PATH.exists():
        return json.loads(PATH.read_text(encoding="utf-8"))
    return {"_about": "Cards removed from the tracker (scripts/remove_card.py).", "removed": {}}


def save(d):
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def removed_ids(root=ROOT):
    p = root / "data" / "removed_cards.json"
    if not p.exists():
        return set()
    return set((json.loads(p.read_text(encoding="utf-8")).get("removed") or {}).keys())


def owned_ids():
    p = ROOT / "data" / "holdings.json"
    if not p.exists():
        return set()
    d = json.loads(p.read_text(encoding="utf-8"))
    urls = [h.get("card_url", "") for h in d.get("holdings", [])]
    urls += [x.get("card_url", "") for sd in d.get("sealed", []) for x in sd.get("pulls", [])]   # pulled cards too
    return {str(u).rstrip("/").split("/")[-1] for u in urls if u}


def apply(issue, labels, store):
    form = parse_form(issue.get("body"))
    raw = field(form, "snkrdunk id", "id") or ""
    m = ID_RE.search(raw)
    if not m:
        raise FormError(f'"{raw}" isn\'t a SNKRDUNK id (a number like 387059).')
    sid = m.group(1)
    name = (field(form, "card") or "").strip() or sid
    rem = store.setdefault("removed", {})
    if "restore-card" in labels:
        if sid not in rem:
            raise FormError(f"{name} ({sid}) isn't removed, so there's nothing to restore.")
        del rem[sid]
        import eval_queue   # its old tiers may be stale: the next price check re-evaluates it
        eval_queue.add(sid, name, f"restored from #{issue['number']}", ROOT)
        return (f"Restored **{name}** ({sid}). It's back on the site now, and the next price check re-evaluates it.",
                f"cards: restore {sid} {name} (#{issue['number']})")
    if sid in owned_ids():
        raise FormError(f"You've logged {name} as bought or pulled. Remove that first if you really want to stop tracking it.")
    if sid in rem:
        raise FormError(f"{name} ({sid}) is already removed.")
    rem[sid] = {"name": name, "at": datetime.now(JST).replace(microsecond=0).isoformat(), "issue": issue["number"],
                "reason": (field(form, "reason") or "").strip() or None}
    return (f"Removed **{name}** ({sid}) from the tracker. The site updates in about a minute; price checks skip it from now on. "
            "Its history stays, and the site's Restore button brings it back.",
            f"cards: remove {sid} {name} (#{issue['number']})")


def main():
    if "--list" in sys.argv:
        for sid, v in load().get("removed", {}).items():
            print(f"{sid}  {v.get('name')}  removed {v.get('at')}")
        return
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        sys.exit(__doc__)
    issue = json.loads(Path(args[0]).read_text(encoding="utf-8"))["issue"]
    labels = {l["name"] for l in issue.get("labels", [])}
    title = issue.get("title") or ""   # the form's title also works if the labels don't exist in the repo
    if title.startswith("Remove card"):
        labels.add("remove-card")
    elif title.startswith("Restore card"):
        labels.add("restore-card")
    if not labels & {"remove-card", "restore-card"}:
        print("Not a card removal/restore issue; nothing to do.")
        return
    try:
        msg, commit_msg = apply(issue, labels, load())
    except FormError as e:
        finish(issue, f"Couldn't do this: {e}", False, dry)
        return
    if dry:
        print(msg)
        return
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    changed = False
    for attempt in range(6):
        git("fetch", "-q", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        store = load()
        try:
            msg, commit_msg = apply(issue, labels, store)
        except FormError as e:
            finish(issue, f"Couldn't do this: {e}", False, dry)
            return
        save(store)
        git("add", "data/removed_cards.json", *(["data/eval_queue.json"] if (ROOT / "data" / "eval_queue.json").exists() else []))
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
            break
        git("commit", "-q", "-m", commit_msg)
        if subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=ROOT).returncode == 0:
            changed = True
            break
        time.sleep(3 + attempt * 2)
    else:
        raise RuntimeError("git push failed six times")
    if changed:
        gh("POST", "/actions/workflows/deploy.yml/dispatches", {"ref": "main"})
    finish(issue, msg, True, dry)


if __name__ == "__main__":
    main()
