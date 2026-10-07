#!/usr/bin/env python3
"""
Issue-form labels: GitHub silently drops a form's label when that label doesn't exist in the repo,
so an issue filed from the site arrives unlabeled and its workflow never runs. That's what broke
"Save to all devices" for sell targets on 2026-10-07 (the `set-sell-target` label was never created).

Two defences:
1. `labels_of(issue)` — the processing scripts use this instead of reading labels directly. When an
   issue has no labels, it infers the label from the title the site fills in ("Sell target: …").
   The workflows match the same title prefixes, so an unlabeled issue still runs.
2. `--sync` (.github/workflows/labels.yml, on every push that changes an issue form, or by hand):
   creates every label the issue forms use, then processes any open issue from the owner that is
   still unlabeled — labels it and runs its script on it, so issues filed while a label was missing
   get handled without you editing them.

    python3 scripts/issue_labels.py --sync           # in Actions (needs GH_TOKEN)
    python3 scripts/issue_labels.py --check          # list form labels; no network
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"

# Title prefix the site fills in -> label. Longest prefixes first wins (see infer()).
TITLE_LABELS = {
    "Sell target:": "set-sell-target",
    "Limit:": "set-limit",
    "Bought:": "bought",
    "Sealed:": "sealed",
    "Pull:": "pull",
    "SNKRDUNK link:": "sealed-link",
    "Grading:": "grading-info",
    "Sold:": "sold",
    "Remove purchase": "remove-purchase",
    "Remove:": "remove-purchase",
    "Undo sale:": "remove-purchase",
    "Add card": "add-card",
    "Remove card": "remove-card",
    "Restore card": "restore-card",
    "Answers": "predict",
}
# Label -> script that processes it (run with an event file).
SCRIPTS = {
    "set-limit": "set_limit.py", "set-sell-target": "set_limit.py",
    "bought": "log_purchase.py", "sealed": "log_purchase.py", "pull": "log_purchase.py",
    "sealed-link": "log_purchase.py", "grading-info": "log_purchase.py", "sold": "log_purchase.py",
    "remove-purchase": "log_purchase.py", "predict": "set_predictions.py",
}
COLORS = {"set-sell-target": "f5a524", "set-limit": "ffd23f", "grading-info": "45d483", "sold": "e5534b", "predict": "6aa9ff"}


def infer(title):
    t = (title or "").strip()
    for p in sorted(TITLE_LABELS, key=len, reverse=True):
        if t.startswith(p):
            return TITLE_LABELS[p]
    return None


def labels_of(issue):
    """The issue's label names; if it has none, the label its title implies."""
    names = {l["name"] for l in issue.get("labels", []) if isinstance(l, dict)}
    if not names:
        lab = infer(issue.get("title"))
        if lab:
            names.add(lab)
    return names


def form_labels():
    out = set()
    for f in sorted(FORMS.glob("*.yml")):
        m = re.search(r'^labels:\s*\[(.*)\]', f.read_text(encoding="utf-8"), re.M)
        if m:
            out |= {x.strip().strip('"\'') for x in m.group(1).split(",") if x.strip()}
    return out


def _gh(method, path, body=None):
    from log_purchase import gh
    return gh(method, path, body)


def sync():
    have = set()
    page = 1
    while True:
        got = _gh("GET", f"/labels?per_page=100&page={page}")
        have |= {l["name"] for l in got}
        if len(got) < 100:
            break
        page += 1
    for lab in sorted(form_labels() - have):
        _gh("POST", "/labels", {"name": lab, "color": COLORS.get(lab, "8b8b8b"), "description": "Filed by the tracker site"})
        print(f"Created label {lab}")
    owner = os.environ["GITHUB_REPOSITORY"].split("/")[0]
    issues = [i for i in _gh("GET", "/issues?state=open&per_page=100&direction=asc")
              if "pull_request" not in i and not i.get("labels") and i["user"]["login"] == owner]
    for i in issues:
        lab = infer(i["title"])
        script = SCRIPTS.get(lab)
        if not script:
            continue
        _gh("POST", f"/issues/{i['number']}/labels", {"labels": [lab]})
        i["labels"] = [{"name": lab}]
        print(f"#{i['number']} {i['title']} -> {lab}, running {script}")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump({"action": "opened", "issue": i}, fh, ensure_ascii=False)
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / script), fh.name], cwd=ROOT)
        if r.returncode:
            print(f"  #{i['number']} failed (exit {r.returncode}); edit the issue to retry")


def main():
    if "--sync" in sys.argv:
        sync()
    elif "--check" in sys.argv:
        print("Form labels:", ", ".join(sorted(form_labels())))
        missing = [l for l in SCRIPTS if l not in form_labels()]
        if missing:
            print("No form uses:", ", ".join(missing))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
