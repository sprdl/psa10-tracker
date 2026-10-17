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

    def test_desktop_run_unchanged(self):
        start = self.load("")
        text = (ROOT / "pricecheck" / "FULL-CHECK.md").read_text(encoding="utf-8")
        self.assertEqual(start.local(text), text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
