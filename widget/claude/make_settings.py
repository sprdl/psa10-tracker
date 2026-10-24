#!/usr/bin/env python3
"""
Writes the allow list of widget/claude/settings.json (linked as .claude/settings.json) for the menu bar's unattended
price checks (claude --permission-mode dontAsk: anything not allowed here is refused, never asked).

    python3 widget/claude/make_settings.py          # rewrite settings.json's "allow" from the repo's files
    python3 widget/claude/make_settings.py --check  # exit 1 if settings.json is out of date (tests/test_permissions.py)

Why it's this narrow (2026-10-24 security audit): a run reads text other people wrote (web pages, search results,
GitHub issues), so a prompt injection must not be able to run code of its choosing. Only the repo's own scripts run
(each named exactly, so `python3 scripts/../x.py` and `python3 -c` don't match), and the run can only write its scratch
folder (data/incoming/) and the page-reading scripts (pricecheck/scripts/*.js, pricecheck/runner.js), so it can't write
a new Python file and then run it. Re-run this after adding a script; the tests fail until you do. This file lives in
widget/, which a run can neither edit nor execute.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "widget" / "claude" / "settings.json"
SCRIPT_DIRS = ["scripts", "pricecheck", "pricecheck/scripts", "tests"]
PRINTABLE = ["scripts/odds_model_builder.js", "scripts/value_model_builder.js"]   # pasted verbatim into the browser (step 5b)
FIXED = [
    "Bash(git pull:*)", "Bash(git status:*)", "Bash(git log:*)", "Bash(git diff:*)", "Bash(git show:*)",
    "Bash(git add:*)", "Bash(git commit:*)", "Bash(git push)", "Bash(git push -q)", "Bash(git rev-parse:*)",
    "Bash(rm -f .git/index.lock)", "Bash(rm -f .git/*.lock)",
    "Bash(cd:*)", "Bash(ls:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(grep:*)", "Bash(wc:*)", "Bash(sleep:*)", "Bash(date:*)",
    "Bash(tee data/incoming/quick-update.log)", "Bash(tee data/incoming/full-update.log)",
    "Bash(mkdir -p data/incoming)",
    "Read",
    "Edit(./data/incoming/**)", "Write(./data/incoming/**)",
    "Edit(./pricecheck/scripts/*.js)", "Write(./pricecheck/scripts/*.js)", "Edit(./pricecheck/runner.js)",
    "WebSearch", "WebFetch(domain:*)",
    "Skill(pokemon-card-price-check)", "Skill(pokemon-tcg-card-evaluation)",
    "mcp__claude-in-chrome",
]


def allow_list():
    py = sorted(f"Bash(python3 {p.relative_to(ROOT).as_posix()}:*)" for d in SCRIPT_DIRS for p in (ROOT / d).glob("*.py"))
    cats = [f"Bash(cat {f})" for f in PRINTABLE] + sorted(f"Bash(cat {p.relative_to(ROOT).as_posix()})" for p in (ROOT / "pricecheck" / "steps").glob("*.md"))
    return py + cats + FIXED


def main():
    s = json.loads(SETTINGS.read_text(encoding="utf-8"))
    want = allow_list()
    if "--check" in sys.argv:
        if s["permissions"]["allow"] != want:
            have = set(s["permissions"]["allow"])
            print("settings.json is out of date: run python3 widget/claude/make_settings.py")
            print("  missing:", sorted(set(want) - have), "\n  extra:", sorted(have - set(want)))
            sys.exit(1)
        print("settings.json allow list is current")
        return
    s["permissions"]["allow"] = want
    SETTINGS.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(want)} allow rules to {SETTINGS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
