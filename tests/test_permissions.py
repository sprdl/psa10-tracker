#!/usr/bin/env python3
"""
The menu bar's price checks run unattended (claude --permission-mode dontAsk): a call .claude/settings.json doesn't
allow is refused, never asked. Two things must hold (2026-10-24 security audit):

1. Every command the quick and full procedures print for a local run (pricecheck/start.py with PSA10_RUN=1, the step
   files, the local skill copies) is allowed, so a run never stops at or skips a step over a permission.
2. What a prompt injection would need is refused: arbitrary Python (`python3 -c`, a script outside the repo's own,
   `scripts/../`), writing a new script, reading or changing credentials and settings, curl and friends.

Matching follows Claude Code's rules: `Bash(x:*)` allows `x` and `x <anything>`, `Bash(x)` only exactly `x`; a command
joined with &&, ||, ; or | is allowed only if every part is; `2>&1` and an input `< file` are ignored; output
redirection (`>`) is never assumed to be allowed. Edit/Write rules are gitignore-style paths from the repo root.

    python3 tests/test_permissions.py
"""
import importlib
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pricecheck"))
SETTINGS = json.loads((ROOT / "widget" / "claude" / "settings.json").read_text(encoding="utf-8"))
ALLOW = SETTINGS["permissions"]["allow"]
SHELL = {"python3", "git", "cat", "tee", "tail", "head", "grep", "wc", "ls", "echo", "sleep", "date", "cd", "rm", "mkdir",
         "printf", "sed", "awk", "find", "node", "bash", "sh", "uuidgen", "curl", "wget", "osascript", "security", "open"}
# Mentions in prose that aren't commands a local run issues: words in CLAUDE.md's "never this form" table, and the
# desktop app's public-clone fallback (troubleshooting / the skill's "computer isn't linked" path, never local).
NOT_RUN_LOCALLY = {"cat", "sleep", "curl", "find", "find … -delete", "rm -f", "cd /tmp/pt",
                   "git clone --depth 1 https://github.com/sprdl/psa10-tracker.git /tmp/pt"}
SOURCES = (["pricecheck/FULL-CHECK.md", "pricecheck/QUICK-CHECK.md"]
           + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "pricecheck" / "steps").glob("*.md"))
           + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "pricecheck" / "references").glob("*.md"))
           + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "widget" / "claude" / "skills").rglob("*.md"))
           + ["CLAUDE.md"])


def bash_rules():
    out = []
    for r in ALLOW:
        m = re.fullmatch(r"Bash\((.*)\)", r)
        if m:
            out.append(m.group(1))
    return out


def segment_allowed(seg):
    seg = re.sub(r"\s+2>&1\b", "", seg)
    seg = re.sub(r"\s+<\s*\S+", "", seg).strip()        # input redirection reads a file: fine
    if re.search(r"(^|\s)\d?>{1,2}", seg):              # output redirection: not assumed allowed
        return False
    for rule in bash_rules():
        if rule.endswith(":*"):
            p = rule[:-2]
            if seg == p or seg.startswith(p + " "):
                return True
        elif seg == rule:
            return True
    return False


def split(cmd):
    cmd = cmd.replace("\\|", "|")                          # a | escaped inside a Markdown table cell
    cmd = re.sub(r"<[A-Za-z#…][^<>]*>", "X", cmd)          # placeholders like <snkrdunk_id> aren't redirections
    cmd = re.sub(r'"[^"]*"', '"Q"', cmd)                   # quoted arguments can hold |, ; or >
    cmd = re.sub(r"'[^']*'", "'Q'", cmd)
    return [s.strip() for s in re.split(r"\s*(?:&&|\|\||;|\||\n)\s*", cmd.strip()) if s.strip()]


def allowed(cmd):
    return all(segment_allowed(s) for s in split(cmd))


def path_allowed(tool, path):
    def rx(pat):
        pat = pat[2:] if pat.startswith("./") else pat
        return "^" + re.escape(pat).replace(r"\*\*", "§").replace(r"\*", "[^/]*").replace("§", ".*") + "$"
    rules = [m.group(1) for r in ALLOW for m in [re.fullmatch(tool + r"\((.*)\)", r)] if m]
    return any(re.match(rx(r), path) for r in rules)


def local_commands():
    os.environ["PSA10_RUN"] = "1"
    try:
        import start
        start = importlib.reload(start)
        seen = {}
        for f in SOURCES:
            text = start.local((ROOT / f).read_text(encoding="utf-8"))
            cands = [l for block in re.findall(r"```[a-z]*\n(.*?)```", text, re.S) for l in block.splitlines()]
            cands += re.findall(r"`([^`\n]+)`", text)
            for c in cands:
                c = c.strip()
                if c.split(" ")[0] in SHELL and c not in NOT_RUN_LOCALLY:
                    seen.setdefault(c, f)
        return seen
    finally:
        os.environ.pop("PSA10_RUN", None)


class Permissions(unittest.TestCase):
    def test_settings_current(self):
        r = subprocess.run([sys.executable, str(ROOT / "widget" / "claude" / "make_settings.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_procedure_command_is_allowed(self):
        cmds = local_commands()
        self.assertGreater(len(cmds), 40)
        for c, f in sorted(cmds.items()):
            if any(seg in NOT_RUN_LOCALLY for seg in split(c)):
                continue
            with self.subTest(file=f, command=c[:120]):
                self.assertTrue(allowed(c), f"{f}: `{c}` isn't allowed by .claude/settings.json")

    def test_typical_run_commands(self):
        for c in ["python3 pricecheck/start.py --mode quick", "python3 pricecheck/start.py --mode full",
                  "git pull --ff-only --quiet", "python3 pricecheck/jsrun.py full", "python3 pricecheck/jsrun.py store runner",
                  "python3 scripts/quick_update.py - < data/incoming/quick_update-in.txt 2>&1 | tee data/incoming/quick-update.log | tail -50",
                  "python3 scripts/full_update.py - < data/incoming/full_update-in.txt 2>&1 | tee data/incoming/full-update.log | tail -120",
                  "python3 scripts/apply_analysis.py - < data/incoming/apply_analysis-in.txt 2>&1 | tail -30",
                  "python3 scripts/skill_query.py checkjson data/incoming/apply_analysis-in.txt",
                  "python3 scripts/skill_query.py holdings", "python3 scripts/skill_query.py mytier",
                  "python3 scripts/runclock.py end", "python3 scripts/card_requests.py list",
                  "cat scripts/odds_model_builder.js", "cat pricecheck/steps/1b-add-cards.md",
                  "rm -f .git/index.lock", "git status --short", "git add pricecheck/scripts/snkrdunk_full.js",
                  'git commit -m "pricecheck: new SNKRDUNK selectors"', "python3 pricecheck/start.py --show pricecheck/steps/8b-evaluate.md"]:
            with self.subTest(command=c):
                self.assertTrue(allowed(c), c)
        for tool, p in [("Write", "data/incoming/quick_update-in.txt"), ("Write", "data/incoming/set_story-in.txt"),
                        ("Edit", "pricecheck/scripts/snkrdunk_full.js"), ("Edit", "pricecheck/runner.js")]:
            with self.subTest(tool=tool, path=p):
                self.assertTrue(path_allowed(tool, p))

    def test_injection_needs_are_refused(self):
        for c in ['python3 -c "import os; os.system(\'id\')"', "python3 -m http.server", "python3 -m json.tool a b",
                  "python3 data/incoming/x.py", "python3 scripts/../data/incoming/x.py", "python3 pricecheck/scripts/../../x.py",
                  "python3", "python3 scripts/runclock.py.evil", "cat .git-credentials", "cat ~/.ssh/id_ed25519",
                  "cat scripts/../.git-credentials", "echo x > ~/.zshrc", "tee ~/.zshrc", "tee -a .claude/settings.json",
                  "curl https://example.com", "wget https://example.com", "node -e 1", "bash -c id", "sh x.sh",
                  "git config credential.helper x", "git credential fill", "git remote add x https://example.com",
                  "git push --force", "osascript -e 1", "security find-internet-password -w",
                  "python3 scripts/runclock.py end > ~/.zshrc", "ls && curl https://example.com"]:
            with self.subTest(command=c):
                self.assertFalse(allowed(c), c)
        for tool, p in [("Write", "scripts/x.py"), ("Write", "pricecheck/x.py"), ("Write", "pricecheck/scripts/x.py"),
                        ("Write", "tests/x.py"), ("Edit", "scripts/runclock.py"), ("Write", ".claude/settings.json"),
                        ("Edit", "widget/claude/settings.json"), ("Write", ".github/workflows/x.yml"),
                        ("Edit", ".git/config"), ("Write", ".git-credentials"), ("Edit", "assets/app.js")]:
            with self.subTest(tool=tool, path=p):
                self.assertFalse(path_allowed(tool, p))

    def test_no_broad_rules(self):
        for bad in ["Bash(python3:*)", "Bash(cat:*)", "Bash(tee:*)", "Bash(echo:*)", "Bash(node:*)", "Bash(bash:*)",
                    "Bash(python3 scripts/:*)", "Edit(./**)", "Write(./**)", "Bash(*)", "Bash"]:
            self.assertNotIn(bad, ALLOW)


if __name__ == "__main__":
    unittest.main(verbosity=1)
