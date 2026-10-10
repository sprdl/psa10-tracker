#!/usr/bin/env python3
"""
The PSA backlog look schedule and the parser for PSA's update text (scripts/psa_backlog.py).

    python3 tests/test_psa_backlog.py

Schedule (FULL-CHECK step 8i): an update is expected 14 days after the newest stored one; the first look is the day
after (2026-10-21 with 2026-10-06 stored); with nothing newer on the page it repeats every day (once per day) until
there is; then the next look starts the day after the next expected date, 14 days after the new update's own date.
"""
import json, shutil, sys, tempfile, unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import psa_backlog as pb  # noqa: E402

BASE = {"threshold_m": 5.0, "readings": [{"d": "2026-08-25", "m": 10.9}, {"d": "2026-09-08", "m": 9.9},
                                         {"d": "2026-09-22", "m": 9.0}, {"d": "2026-10-06", "m": 8.2}]}


def clone(**over):
    d = json.loads(json.dumps(BASE)); d.update(over); return d


class Schedule(unittest.TestCase):
    def due(self, d, y, m, day):
        return pb.due_state(d, date(y, m, day))[0]

    def test_first_look_is_the_21st(self):
        d = clone()
        for day in (10, 19, 20):
            self.assertFalse(self.due(d, 2026, 10, day))
        self.assertTrue(self.due(d, 2026, 10, 21))

    def test_repeats_daily_until_new_data(self):
        d = clone()
        for day in (22, 23, 31):
            self.assertTrue(self.due(d, 2026, 10, day))
        self.assertTrue(self.due(d, 2026, 11, 5))

    def test_once_per_day(self):
        d = clone(check={"last_checked": "2026-10-21", "result": "no new update"})
        self.assertFalse(self.due(d, 2026, 10, 21))
        self.assertTrue(self.due(d, 2026, 10, 22))

    def test_back_to_two_weeks_after_new_data(self):
        d = clone(); d["readings"].append({"d": "2026-10-20", "m": 7.4})   # saved on 10/23, dated by PSA 10/20
        self.assertFalse(self.due(d, 2026, 10, 23))
        self.assertFalse(self.due(d, 2026, 11, 3))
        self.assertTrue(self.due(d, 2026, 11, 4))

    def test_late_update_moves_the_next_one(self):
        d = clone(); d["readings"].append({"d": "2026-10-27", "m": 7.1})
        self.assertFalse(self.due(d, 2026, 11, 10))
        self.assertTrue(self.due(d, 2026, 11, 11))


class Vpn(unittest.TestCase):
    def test_reminder_only_when_due(self):
        import io, contextlib
        for day, want in ((20, False), (21, True)):
            tmp = Path(tempfile.mkdtemp()); (tmp / "data").mkdir()
            d = clone(); pb.save(pb.recompute(d), tmp)
            real = pb.today; pb.today = lambda day=day: date(2026, 10, day)
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    pb.print_due(tmp)
            finally:
                pb.today = real; shutil.rmtree(tmp)
            self.assertEqual("VPN REMINDER" in buf.getvalue(), want, day)


class Parser(unittest.TestCase):
    CASES = [
        ("October 6, 2026 Update\nOur active grading backlog is now 8.2 million units, down from 9 million reported September 22.", (date(2026, 10, 6), 8.2, 9.0)),
        ("September 22, 2026 Update\nOur active global backlog is down to approximately 9 million units (from 9.9 million on September 8).", (date(2026, 9, 22), 9.0, 9.9)),
        ("September 8, 2026 Update\nOur active grading backlog is down to 9.9 million units, from 10.9 million reported August 25.", (date(2026, 9, 8), 9.9, 10.9)),
        ("August 25, 2026 Update\nOur active global backlog is down to approximately 10.9 million units. Driven by steady", (date(2026, 8, 25), 10.9, None)),
        ("August 11, 2026 Update\nJuly set a record. Backlog fell to 11.85 million from 12.4 million.", (date(2026, 8, 11), 11.85, 12.4)),
        ("June 08, 2026 Update\nPackages may take longer to be marked as received.", (date(2026, 6, 8), None, None)),
    ]

    def test_psa_wording(self):
        for text, want in self.CASES:
            self.assertEqual(pb.parse_update(text)[:3], want, text[:40])

    def test_newest_is_the_first_heading(self):
        got = pb.parse_update("October 20, 2026 Update\nOur active grading backlog is now 7.4 million units, down from 8.2 million.\n\n" + self.CASES[0][0])
        self.assertEqual(got[:3], (date(2026, 10, 20), 7.4, 8.2))
        self.assertNotIn("October 6", got[3])


class Saving(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); (self.tmp / "data").mkdir()
        shutil.copy(ROOT / "data" / "psa_backlog.json", self.tmp / "data")
        d = json.loads((self.tmp / "data/psa_backlog.json").read_text())
        d["readings"] = [r for r in d["readings"] if r["d"] <= "2026-10-06"]
        pb.save(pb.recompute(d), self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_page(self, text):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pb.from_page(text, self.tmp, True)
        return rc, buf.getvalue(), json.loads((self.tmp / "data/psa_backlog.json").read_text())

    def test_nothing_new_records_the_look(self):
        rc, out, d = self.run_page(self.CASE_OLD)
        self.assertEqual(rc, 0); self.assertIn("NO NEW UPDATE", out)
        self.assertEqual(len(d["readings"]), 7); self.assertEqual(d["check"]["last_checked"], pb.today().isoformat())

    CASE_OLD = "October 6, 2026 Update\nOur active grading backlog is now 8.2 million units, down from 9 million reported September 22."
    CASE_NEW = "October 20, 2026 Update\nOur active grading backlog is now 7.4 million units, down from 8.2 million reported October 6."

    def test_new_update_is_saved_and_projected(self):
        rc, out, d = self.run_page(self.CASE_NEW + "\n\n" + self.CASE_OLD)
        self.assertEqual(rc, 0); self.assertIn("SAVED", out)
        self.assertEqual((d["readings"][-1]["d"], d["readings"][-1]["m"]), ("2026-10-20", 7.4))
        self.assertEqual(d["projection"]["backlog_m"], 7.4); self.assertEqual(d["projection"]["next_update"], "2026-11-03")

    def test_refuses_what_does_not_fit(self):
        for text in ("November 3, 2026 Update\nOur active grading backlog is now 6.0 million units, down from 6.9 million.",   # a missed update in between
                     "November 3, 2026 Update\nOur active grading backlog is now 2.0 million units.",                           # a jump of more than 3M
                     "no heading here"):
            rc, out, d = self.run_page(text)
            self.assertEqual(rc, 2); self.assertIn("CHECK BY HAND", out); self.assertEqual(len(d["readings"]), 7)


if __name__ == "__main__":
    unittest.main(verbosity=1)
