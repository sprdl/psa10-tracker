#!/usr/bin/env python3
"""
pricecheck/start.py prints the procedures for local Claude Code runs (PSA10_RUN=1, set by the menu bar widget) without
the repo-finding prefix: a command with `$(…)` or `"$R"` can't match .claude/settings.json's allow list, so it would stop
an unattended run for a permission question (CLAUDE.md). Until 2026-10-18 the short form `cd "$R" && …` slipped through.

    python3 tests/test_start.py
"""
import importlib
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pricecheck"))


class LocalProcedure(unittest.TestCase):
    def load(self, run):
        os.environ["PSA10_RUN"] = run
        import start
        return importlib.reload(start)

    def tearDown(self):
        os.environ.pop("PSA10_RUN", None)

    def test_local_run_has_no_repo_prefix(self):
        start = self.load("1")
        for name in ("FULL-CHECK.md", "QUICK-CHECK.md"):
            text = start.local((ROOT / "pricecheck" / name).read_text(encoding="utf-8"))
            with self.subTest(procedure=name):
                self.assertNotIn('cd "$R"', text)
                self.assertNotIn("R=$(", text)
                self.assertNotIn('"$R"/', text)
                self.assertIn("python3 scripts/runclock.py end", text)   # the command itself survives

    def test_local_run_has_no_heredoc(self):
        # a long heredoc can't be pre-approved (Claude Code's checker gives up: "Parser aborted … over-length"),
        # so locally the lines go to data/incoming/<script>-in.txt and the command reads them with `< file`
        start = self.load("1")
        files = [ROOT / "pricecheck" / n for n in ("FULL-CHECK.md", "QUICK-CHECK.md")] + sorted((ROOT / "pricecheck" / "steps").glob("*.md"))
        for f in files:
            text = start.local(f.read_text(encoding="utf-8"))
            with self.subTest(file=f.name):
                self.assertNotIn("<<'", text)
                self.assertNotIn("$(", text)
        q = start.local((ROOT / "pricecheck" / "QUICK-CHECK.md").read_text(encoding="utf-8"))
        self.assertIn("python3 scripts/quick_update.py - < data/incoming/quick_update-in.txt 2>&1 | tee", q)

    def test_only_sections(self):
        # FULL-CHECK.md's day-dependent sections (<!-- only:… -->) are printed only when today's plan needs them (2026-10-23)
        start = self.load("")
        text = (ROOT / "pricecheck" / "FULL-CHECK.md").read_text(encoding="utf-8")
        self.assertIn("<!-- only:scout -->", text)
        kept = start.only(text, {})
        self.assertNotIn("<!-- only:", kept)
        self.assertIn("**Scout (step 4.4)**", kept)
        dropped = start.only(text, {"scout": False, "psapop": False, "monday": False, "rebuild": False})
        for gone in ("**Scout (step 4.4)**", "4. **Tab P, collect the PSA pop report.**", "**5b. Monthly model rebuild**", "**6 / 6b. Mondays:**"):
            self.assertNotIn(gone, dropped)
        for kept_step in ("5. **Tab S, collect SNKRDUNK.**", "**Slab premiums:**", "## 7. Publish", "python3 scripts/runclock.py end"):
            self.assertIn(kept_step, dropped)

    def test_desktop_run_unchanged(self):
        start = self.load("")
        text = (ROOT / "pricecheck" / "FULL-CHECK.md").read_text(encoding="utf-8")
        self.assertEqual(start.local(text), text)   # local() itself changes nothing for a desktop-app run


if __name__ == "__main__":
    unittest.main(verbosity=1)
