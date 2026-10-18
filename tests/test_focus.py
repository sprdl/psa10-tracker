"""Focus watch (scripts/focus.py): status rules on a tiny synthetic repo."""
import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import focus  # noqa: E402

URL = "https://snkrdunk.com/apparels/1"
NAME = "テストex SAR [M2a 240/193](パック)"


def repo(asks, sales, limit=60000, listings=None):
    d = Path(tempfile.mkdtemp())
    (d / "data" / "snapshots").mkdir(parents=True)
    snaps, files = [], []
    for i, a in enumerate(asks):
        ts = f"2026-10-{10 + i:02d}T09:00:00+09:00"
        snaps.append({"d": ts, "m": "full", "r": {URL: [a, 0, 0, 0, 0]}})
        f = f"202610{10 + i:02d}-0900.json"
        files.append({"file": f, "collected_at_jst": ts})
        lst = listings[i] if listings else [a] * 20
        (d / "data" / "snapshots" / f).write_text(json.dumps({"collected_at_jst": ts, "cards": [{
            "url": URL, "card_name_ja": NAME, "grades": {"psa10": {"top20_cheapest_listings": lst}},
            "analysis": {"tiers": {"definitely_buy": 55000, "buy_upper": 60000, "ceiling": 68000}}}]}))
    (d / "data" / "history.json").write_text(json.dumps({"snapshots": snaps}))
    (d / "data" / "manifest.json").write_text(json.dumps({"snapshots": files}))
    (d / "data" / "sales.json").write_text(json.dumps({"cards": {URL: sales}}))
    (d / "data" / "limits.json").write_text(json.dumps({"limits": {URL: {"price": limit}}}))
    (d / "data" / "focus.json").write_text(json.dumps({"cards": {URL: {"since": "2026-10-10"}}}))
    return d


def hour(day, h=0):  # JST 2026-10-<day> h:00 as hours since the epoch
    from datetime import datetime, timedelta, timezone
    return int(datetime(2026, 10, day, h, tzinfo=timezone(timedelta(hours=9))).timestamp() // 3600)


class FocusTest(unittest.TestCase):
    def status(self, *a, **k):
        return focus.build(repo(*a, **k))["cards"][0]

    def test_buy_window(self):
        self.assertEqual(self.status([65000, 62000, 59500], [])["status"], "buy_window")

    def test_near_by_sale(self):
        c = self.status([65000, 63000, 62500], [[hour(12, 6), 59900]])
        self.assertEqual(c["status"], "close")
        self.assertEqual(c["flags"][0]["level"], "go")

    def test_drifting(self):
        asks = [70000, 69000, 68000, 67000, 66000, 65500, 65000, 64500, 64000]
        self.assertEqual(self.status(asks, [])["status"], "drifting")

    def test_turning(self):
        asks = [65000, 64000, 63000, 66000]
        sales = [[hour(11, 6), 63000], [hour(11, 8), 63000], [hour(13, 6), 66000]]
        self.assertEqual(self.status(asks, sales)["status"], "turning")

    def test_thinning(self):
        lst = [[62000] * 15 + [70000] * 5, [62000] * 4 + [70000] * 16]
        c = self.status([62000, 62000], [], listings=lst)
        self.assertTrue(any("thinning" in f["text"] for f in c["flags"]))


if __name__ == "__main__":
    unittest.main()
