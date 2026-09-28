#!/usr/bin/env python3
"""
Save your "You vs the model" answers to data/predict.json from a GitHub issue, so every device
shows the same answers and the site can score them.

Runs inside GitHub Actions (.github/workflows/predictions.yml) when you submit the site's
"Save my answers" form (label `predict`):

    python3 scripts/set_predictions.py "$GITHUB_EVENT_PATH" [--dry-run]

The form's Answers field has one line per question, "<question id>: <percent>", e.g.
"2026-09-28-1: 35". The first saved answer to a question is final (that's what "Lock in" means).
Answers to questions that already resolved, or after Friday's close, are not accepted.
"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from log_purchase import JST, ROOT, FormError, field, finish, gh, git, parse_form

PATH = ROOT / "data" / "predict.json"
LINE = re.compile(r"(\d{4}-\d{2}-\d{2}-\d+)\s*[:=]\s*(\d{1,3})(?:\s*%)?")


def ts(s):
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=JST)


def parse(issue):
    form = parse_form(issue.get("body"))
    pairs = LINE.findall(field(form, "answers") or issue.get("body") or "")
    if not pairs:
        raise FormError('No answers found. Each line should look like "2026-09-28-1: 35".')
    out = {}
    for qid, pct in pairs:
        p = int(pct)
        if not 0 <= p <= 100:
            raise FormError(f"{qid}: {p}% isn't between 0 and 100.")
        out[qid] = p / 100
    return out


def apply(data, answers, when):
    saved, skipped = [], []
    for qid, p in answers.items():
        wk = data.get("weeks", {}).get(qid.rsplit("-", 1)[0])
        q = next((x for x in (wk or {}).get("questions", []) if x["id"] == qid), None)
        if not q:
            skipped.append(f"{qid}: no such question")
            continue
        if qid in wk.get("answers", {}):
            skipped.append(f"{qid}: already locked at {round(wk['answers'][qid]['p'] * 100)}%")
            continue
        r = wk.get("results", {}).get(qid)
        if r and ts(r["at"]) <= when:
            skipped.append(f"{qid}: already resolved")
            continue
        if when > ts(wk["close"]):
            skipped.append(f"{qid}: the week closed")
            continue
        wk.setdefault("answers", {})[qid] = {"p": round(p, 2), "at": when.isoformat(timespec="seconds")}
        saved.append(f"{q['name'][:24]}: {round(p * 100)}%")
    return saved, skipped


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        sys.exit(__doc__)
    issue = json.loads(Path(args[0]).read_text(encoding="utf-8"))["issue"]
    if "predict" not in {l["name"] for l in issue.get("labels", [])} and not (issue.get("title") or "").startswith("Answers"):
        print("Not a predictions issue; nothing to do.")
        return
    try:
        answers = parse(issue)
    except FormError as e:
        finish(issue, f"Couldn't save these answers: {e}\n\nEdit the issue to fix it and it will be retried automatically.", False, dry)
        return
    when = ts(issue.get("created_at") or datetime.now(JST).isoformat())  # the moment you locked in, not when the Action ran
    if dry:
        data = json.loads(PATH.read_text(encoding="utf-8"))
        print(apply(data, answers, when))
        return
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    saved = skipped = []
    for attempt in range(6):
        git("fetch", "-q", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        data = json.loads(PATH.read_text(encoding="utf-8"))
        saved, skipped = apply(data, answers, when)
        PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        git("add", "data/predict.json")
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
            break
        git("commit", "-q", "-m", f"predict: {len(saved)} answer(s) (#{issue['number']})")
        if subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=ROOT).returncode == 0:
            gh("POST", "/actions/workflows/deploy.yml/dispatches", {"ref": "main"})
            break
        time.sleep(3 + attempt * 2)
    else:
        raise RuntimeError("git push failed six times")
    msg = ("Locked in: " + "; ".join(saved) + ". The site shows them in about a minute." if saved else "Nothing new to save.")
    if skipped:
        msg += "\n\nNot saved: " + "; ".join(skipped) + "."
    finish(issue, msg, True, dry)


if __name__ == "__main__":
    main()
