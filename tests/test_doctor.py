#!/usr/bin/env python3
"""scripts/doctor.py: finds leftover git locks and a run clock whose run is gone, and --fix clears them (2026-10-23)."""
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))


def load():
    spec = importlib.util.spec_from_file_location("doctor", ROOT / "scripts" / "doctor.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Doctor(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".git" / "refs" / "heads").mkdir(parents=True)
        (self.tmp / "data" / "incoming").mkdir(parents=True)
        self.d = load()
        self.d.ROOT = self.tmp
        self.d.CLOCK = self.tmp / "data" / "incoming" / "runclock.json"
        self.d.git_running = lambda: False

    def test_locks(self):
        self.assertEqual(self.d.check_locks(False)[0][0], "ok")
        fresh = self.tmp / ".git" / "index.lock"
        fresh.write_text("")
        self.assertEqual(self.d.check_locks(False)[0][0], "ok")       # a git command may be using it right now
        old = time.time() - 3600
        os.utime(fresh, (old, old))
        ref = self.tmp / ".git" / "refs" / "heads" / "main.lock"
        ref.write_text("")
        os.utime(ref, (old, old))
        k, t = self.d.check_locks(False)[0]
        self.assertEqual(k, "warn")
        self.assertIn("index.lock", t)
        self.assertIn("main.lock", t)
        self.assertEqual(self.d.check_locks(True)[0][0], "fixed")
        self.assertFalse(fresh.exists() or ref.exists())

    def test_clock(self):
        self.assertEqual(self.d.check_clock(False)[0][0], "ok")
        now = datetime.now(JST)
        self.d.CLOCK.write_text(json.dumps({"mode": "full", "start": now.isoformat(), "pid": os.getpid()}))
        self.assertIn("is running", self.d.check_clock(False)[0][1])
        self.d.CLOCK.write_text(json.dumps({"mode": "full", "start": (now - timedelta(hours=2)).isoformat()}))
        self.assertEqual(self.d.check_clock(False)[0][0], "warn")
        self.assertEqual(self.d.check_clock(True)[0][0], "fixed")
        self.assertFalse(self.d.CLOCK.exists())
        self.assertTrue(list(self.d.CLOCK.parent.glob("runclock-stale-*.json")))


if __name__ == "__main__":
    unittest.main()
