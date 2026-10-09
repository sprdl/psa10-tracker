#!/usr/bin/env python3
"""
The same rules live in several places: the site (assets/app.js), the Python scripts the price checks run, and
the Home Screen widget (widgets/psa10-widget.js). This test runs them on the repo's own data (the latest
snapshots, with the clock frozen at each snapshot's time) and fails when two versions disagree:

  raw A-rank price      rawPrice (app.js)         ↔  raw_price.py via build_history.py (history.json "r")
  trading rate          salesPerDay (app.js)      ↔  build_history.sales_per_day (history.json "h")
  "What stands out"     insightsFor (app.js)      ↔  outliers.findings
  tier review due       tierReview (app.js)       ↔  review_due.compute
  limit odds            touchOdds (app.js)        ↔  odds_model.odds
  event rule            activeEvents (app.js)     ↔  events.active          ↔  the widget's eventFor
  verdict pill, limit hit, sell signal,
  correction and rally rules                      app.js  ↔  the widget

    python3 tests/test_rules.py            # the latest 3 snapshots
    RULES_N=10 python3 tests/test_rules.py # more

Needs Node (for tests/rules.mjs). Runs in GitHub Actions on every push that changes code (.github/workflows/tests.yml).
"""
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_history  # noqa: E402
import events  # noqa: E402
import odds_model  # noqa: E402
import outliers  # noqa: E402
import review_due  # noqa: E402

N = int(os.environ.get("RULES_N", "3"))
REASON_KIND = (("days old", "age"), ("index", "market"), ("market moved", "market"), ("long shot", "longshot"), ("young card", "young"))


def kinds(reasons):
    """Reason texts → kinds; the site and review_due.py word them differently."""
    return sorted({next((k for key, k in REASON_KIND if key in r), r) for r in reasons})


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run(["node", str(ROOT / "tests" / "rules.mjs"), str(N)], cwd=ROOT, capture_output=True, text=True)
        if out.returncode:
            raise RuntimeError("tests/rules.mjs failed:\n" + out.stderr)
        cls.js = json.loads(out.stdout)
        cls.entries = {e["d"]: e for e in build_history.entries(ROOT)[0]}
        cls.holdings = {h.get("card_url") for h in json.loads((ROOT / "data" / "holdings.json").read_text(encoding="utf-8")).get("holdings", [])}

    def each(self):
        for s in self.js:
            for c in s["cards"]:
                yield s, c

    def test_raw_price(self):
        for s, c in self.each():
            r = (self.entries[s["at"]].get("r") or {}).get(c["url"])
            py = r[4] if r else None
            with self.subTest(snapshot=s["file"], card=c["name"][:20]):
                if py is None or c["raw"] is None:
                    self.assertEqual(py, c["raw"])
                else:
                    self.assertLessEqual(abs(py - c["raw"]), 1)

    def test_trading_rate(self):
        for s, c in self.each():
            h = (self.entries[s["at"]].get("h") or {}).get(c["url"]) or [None, None]
            for i, label in ((0, "PSA10"), (1, "raw A")):
                with self.subTest(snapshot=s["file"], card=c["name"][:20], grade=label):
                    if h[i] is None or c["heat"][i] is None:
                        self.assertEqual(h[i], None if c["heat"][i] is None else h[i])
                        self.assertEqual(c["heat"][i], None if h[i] is None else c["heat"][i])
                    else:
                        self.assertAlmostEqual(h[i], c["heat"][i], delta=0.006)

    def test_insights(self):
        for s in self.js:
            py = {r[1]: r[4] for r in outliers.findings(ROOT, upto=s["file"])}
            for c in s["cards"]:
                if c["ask"] is None:
                    continue
                with self.subTest(snapshot=s["file"], card=c["name"][:20]):
                    p = sorted((k, round(v, 2)) for k, v, _ in py.get(c["url"], []))
                    j = sorted((k, round(v, 2)) for k, v in c["insights"])
                    self.assertEqual([k for k, _ in p], [k for k, _ in j])
                    for (_, a), (_, b) in zip(p, j):
                        self.assertAlmostEqual(a, b, delta=0.03)

    def test_tier_review(self):
        for s in self.js:
            due, _ = review_due.compute(ROOT, latest=s["file"])
            py = {d[1]: kinds(d[4]) for d in due}
            for c in s["cards"]:
                if c["tier_due"] is None or c["ask"] is None or c["url"] in self.holdings:
                    continue
                with self.subTest(snapshot=s["file"], card=c["name"][:20]):
                    self.assertEqual(py.get(c["url"], []), kinds(c["tier_reasons"]) if c["tier_due"] else [])

    def test_limit_odds(self):
        model = odds_model.load_model(ROOT)
        for s, c in self.each():
            for price, js in c["odds"]:
                with self.subTest(snapshot=s["file"], card=c["name"][:20], price=price):
                    py = odds_model.odds(model, c["name"], c["ask"], price)
                    if js == "reached":
                        self.assertIsNone(py)
                    elif js is None:
                        self.assertIsNone(py)
                    else:
                        self.assertAlmostEqual(py[0], js[0], delta=0.002)
                        self.assertAlmostEqual(py[1], js[1], delta=0.002)

    def test_event_rule(self):
        ev = json.loads((ROOT / "data" / "events.json").read_text(encoding="utf-8"))
        for s in self.js:
            day = datetime.fromisoformat(s["at"]).date()
            with self.subTest(snapshot=s["file"]):
                self.assertEqual(sorted(e["name"] for e in events.active(ev, day)), sorted(s["events"]))
            for c in s["cards"]:
                with self.subTest(snapshot=s["file"], card=c["name"][:20], what="widget"):
                    self.assertEqual(c["event"], c["widget_event"])

    def test_site_and_widget(self):
        for s in self.js:
            with self.subTest(snapshot=s["file"], rule="correction"):
                self.assertEqual(s["correction"], s["widget_correction"])
            with self.subTest(snapshot=s["file"], rule="rally"):
                self.assertEqual(s["rally"], s["widget_rally"])
            for c in s["cards"]:
                w = c["widget"]
                if w is None:   # no PSA10 ask: the widget doesn't list it
                    self.assertIsNone(c["ask"])
                    continue
                with self.subTest(snapshot=s["file"], card=c["name"][:20]):
                    self.assertEqual(w["sell"], c["sell"])
                    self.assertEqual(w["limit_hit"], c["limit_hit"])
                    self.assertEqual(w["tag"], "sell_" + c["sell"] if c["sell"] else c["tag"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
