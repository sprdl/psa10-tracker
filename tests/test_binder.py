import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import binder  # noqa: E402

JST = timezone(timedelta(hours=9))
MON = datetime(2026, 10, 19, 9, 0, tzinfo=JST)
MON2 = MON + timedelta(days=7)
SUN = datetime(2026, 10, 18, 9, 0, tzinfo=JST)


def make(cards):
    d = Path(tempfile.mkdtemp())
    (d / "data").mkdir()
    binder.write({"cards": cards}, d)
    return d


class BinderTest(unittest.TestCase):
    def test_due_only_on_monday_with_id(self):
        d = make([{"id": "a", "snkrdunk_id": "11"}, {"id": "b", "snkrdunk_id": None}])
        self.assertEqual(binder.due_ids(d, SUN), [])
        self.assertEqual(binder.due_ids(d, MON), ["11"])
        self.assertEqual([c["id"] for c in binder.missing_ids(d)], ["b"])

    def test_save_keeps_previous_price_and_rule(self):
        d = make([{"id": "a", "snkrdunk_id": "11", "qty": 2}])
        binder.save({"11": {"ask": 1000, "sales": [1500, 1400, 1600]}}, d, push=False, now=MON)
        c = binder.load(d)["cards"][0]
        self.assertEqual((c["price"], c["basis"], c.get("prev_price")), (1500, "sales", None))
        binder.save({"11": {"ask": 1200, "sales": [1100]}}, d, push=False, now=MON2)
        c = binder.load(d)["cards"][0]
        self.assertEqual((c["price"], c["basis"], c["prev_price"], c["prev_date"]), (1200, "ask", 1500, "2026-10-19"))
        self.assertEqual(binder.due_ids(d, MON2), [])   # read today

    def test_same_day_rerun_keeps_prev(self):
        d = make([{"id": "a", "snkrdunk_id": "11"}])
        binder.save({"11": {"ask": 1000, "sales": []}}, d, push=False, now=MON)
        binder.save({"11": {"ask": 1100, "sales": []}}, d, push=False, now=MON2)
        binder.save({"11": {"ask": 1300, "sales": []}}, d, push=False, now=MON2)
        c = binder.load(d)["cards"][0]
        self.assertEqual((c["price"], c["prev_price"]), (1300, 1000))

    def test_failed_read_keeps_last_price(self):
        d = make([{"id": "a", "snkrdunk_id": "11", "price": 900, "date": "2026-10-12"}])
        binder.save({"11": {"error": "page did not load"}}, d, push=False, now=MON)
        c = binder.load(d)["cards"][0]
        self.assertEqual((c["price"], c["date"]), (900, "2026-10-12"))

    def test_real_data_file(self):
        cards = json.loads((ROOT / "data" / "binder.json").read_text(encoding="utf-8"))["cards"]
        self.assertEqual(len(cards), 21)
        self.assertEqual(len({c["id"] for c in cards}), 21)
        self.assertEqual(sum(c["qty"] for c in cards), 22)


if __name__ == "__main__":
    unittest.main()
