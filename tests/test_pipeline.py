#!/usr/bin/env python3
"""
The price-check pipeline between the browser and the snapshot, on fixtures (no repo data, no clock):

  - the time codes the in-page scripts write (enc() in snkrdunk_quick.js / snkrdunk_full.js, run in Node)
    decode back to SNKRDUNK's own text (quick_update._when);
  - quick_update.decode_compact and full_update.decode_listing / tile_listing turn compact lines into the
    shapes assemble.py reads, and the 115% threshold rounds like the site's JS (Math.round);
  - assemble.grade_obj builds a snapshot grade from them;
  - pricecheck/plan.py decides what a full check reads (full vs tile, photo, A-listing carry, PSA pop,
    Scout) from a temporary data folder with a frozen "now".

    python3 tests/test_pipeline.py        (needs node)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "pricecheck"))
sys.path.insert(0, str(ROOT / "pricecheck" / "scripts"))
import assemble  # noqa: E402
import full_update  # noqa: E402
import plan  # noqa: E402
import quick_update  # noqa: E402

JST = timezone(timedelta(hours=9))
SNKRDUNK_WHEN = ["たった今", "12秒前", "49分前", "3時間前", "2日前", "1週間前", "1ヶ月前", "2か月前", "2026/04/21",
                 "昨日 12:00", "  5時間前  "]


def node(src):
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(out.stderr)
    return json.loads(out.stdout)


def page_enc(script):
    """The U table and enc() exactly as written in an in-page script."""
    text = (ROOT / "pricecheck" / "scripts" / script).read_text(encoding="utf-8")
    u = re.search(r"^\s*const U = \{.*?\};$", text, re.M)
    e = re.search(r"^(\s*)const enc = \(w\) => \{.*?^\1\};$", text, re.M | re.S)
    assert u and e, f"U / enc() not found in {script}"
    return u[0] + "\n" + e[0]


class TimeCodes(unittest.TestCase):
    def test_round_trip_both_scripts(self):
        for script in ("snkrdunk_quick.js", "snkrdunk_full.js"):
            codes = node(page_enc(script) + f"\nprocess.stdout.write(JSON.stringify({json.dumps(SNKRDUNK_WHEN)}.map(enc)));")
            for raw, code in zip(SNKRDUNK_WHEN, codes):
                with self.subTest(script=script, when=raw, code=code):
                    self.assertNotIn(" ", code)   # one token in a space-separated line
                    self.assertEqual(quick_update._when(code), raw.strip())

    def test_codes_are_compact(self):
        codes = node(page_enc("snkrdunk_quick.js") + "\nprocess.stdout.write(JSON.stringify(['3時間前','2026/04/21','たった今'].map(enc)));")
        self.assertEqual(codes, ["3h", "260421", "n"])

    def test_unknown_code_is_an_error(self):
        with self.assertRaises(ValueError):
            quick_update._when("3x")


class QuickLines(unittest.TestCase):
    def test_full_line(self):
        d = quick_update.decode_compact("header line, ignored\n455596 f3921 p44000 a-  P~2=45000@3h,44000@n A0\n")["cards"]
        c = d["455596"]
        self.assertEqual(c["base"]["favorite_count"], 3921)
        self.assertEqual(c["tiles"], {"PSA10": {"lowest_ask": 44000}, "A": {"lowest_ask": None, "note": "no listings (出品待ち)"}})
        p = c["base"]["sales"]["PSA10"]
        self.assertEqual(p["recent_completed_sales"], [{"price": 45000, "when": "3時間前"}, {"price": 44000, "when": "たった今"}])
        self.assertIn("2 row(s) discarded", p["sales_note"])
        self.assertEqual(c["base"]["sales"]["A"]["recent_completed_sales"], [])
        self.assertIn("no completed sales", c["base"]["sales"]["A"]["sales_note"])

    def test_errors(self):
        d = quick_update.decode_compact("1 E" + "page%20failed\n2 f? p! a5 P!n A!a\n3 f10 px a? P=")["cards"]
        self.assertEqual(d["1"]["base"], {"error": "page failed"})
        self.assertIsNone(d["2"]["base"]["favorite_count"])
        self.assertIn("favorite_error", d["2"]["base"])
        self.assertEqual(d["2"]["tiles"], {"error": "grade tiles not found"})
        self.assertIn("pill not found", d["2"]["base"]["sales"]["PSA10"]["error"])
        self.assertFalse(d["2"]["base"]["sales"]["A"]["pill_active"])
        self.assertEqual(d["3"]["tiles"]["PSA10"], {"error": "tile not found"})
        self.assertEqual(d["3"]["tiles"]["A"]["note"], "no price on tile")
        self.assertEqual(d["3"]["base"]["sales"]["PSA10"]["recent_completed_sales"], [])

    def test_bad_tokens_raise(self):
        for line in ("9 pq", "9 P=abc@3h", "9 Pzz"):
            with self.subTest(line=line), self.assertRaises(ValueError):
                quick_update.decode_compact(line)


class Listings(unittest.TestCase):
    def test_threshold_rounds_like_js(self):
        lows = [10, 30, 70, 1030, 2990, 6200, 44000, 128888, 999999]
        js = node(f"process.stdout.write(JSON.stringify({lows}.map((x) => Math.round(x * 1.15))));")
        for low, want in zip(lows, js):
            with self.subTest(low=low):
                self.assertEqual(full_update.decode_listing(f"L={low},{low * 2}")["threshold_115pct_of_lowest"], want)

    def test_listing_shape_and_flags(self):
        o = full_update.decode_listing("Lsg2f=1000,1100,1150,1151,2000")
        self.assertEqual(o["lowest_price"], 1000)
        self.assertEqual(o["listings_within_15pct_of_lowest"], [1000, 1100, 1150])
        self.assertEqual((o["count_within_15pct"], o["count_excluded_over_15pct"]), (3, 2))
        self.assertIn("sort_note", o)
        self.assertIn("2 tile(s)", o["grade_warning"])
        self.assertIn("filter label", o["grade_warning"])
        self.assertEqual(full_update.decode_listing("R!no%20page"), {"error": "no page"})
        self.assertIn("error", full_update.decode_listing("L="))
        with self.assertRaises(ValueError):
            full_update.decode_listing("Lx=1")

    def test_tile_only(self):
        self.assertIn("error", full_update.tile_listing("p44000", "PSA10"))   # PSA10 needs real listings
        self.assertEqual(full_update.tile_listing("a5000", "A"), {"lowest_price": 5000, "threshold_115pct_of_lowest": 5750})
        self.assertIn("error", full_update.tile_listing(None, "A"))

    def test_grade_obj(self):
        assemble.warnings.clear()
        g = assemble.grade_obj(full_update.decode_listing("Ls=1000,1200"), quick_update._sales("P=900@2d", "PSA10"), "x PSA10")
        self.assertEqual(g["lowest_price"], 1000)
        self.assertEqual(g["recent_completed_sales"], [{"price": 900, "when": "2日前"}])
        self.assertIn("sort_note", g)
        self.assertTrue(any("x PSA10" in w for w in assemble.warnings))
        g = assemble.grade_obj(dict(full_update.decode_listing("R=5,6"), listings_as_of="2026-10-17T09:00:00+09:00"), None, "x A")
        self.assertEqual(g["listings_as_of"], "2026-10-17T09:00:00+09:00")
        self.assertIn("sales_error", g)
        self.assertEqual(assemble.grade_obj({"error": "boom"}, {"error": "pill"}, "y")["error"], "boom")
        self.assertIn("not collected", assemble.grade_obj(None, None, "z")["error"])


def card(sid, psa10=None, a_low=None, a_list=True, asof=None, pop=None, source="psa", verdict=None):
    a = {"lowest_price": a_low, "top20_cheapest_listings": [a_low] if a_list and a_low else []}
    if asof:
        a["listings_as_of"] = asof
    c = {"url": f"https://snkrdunk.com/apparels/{sid}", "grades": {"psa10": {"lowest_price": psa10}, "raw_a_grade": a}}
    if pop is not None:
        c.update(psa10_population=pop, population_source=source)
    if verdict:
        c["analysis"] = {"verdict": {"tag": verdict}}
    return c


class IndexCarry(unittest.TestCase):
    def test_skipped_index_is_carried_with_its_date(self):
        # a full check that couldn't read pokeca-chart keeps the last index, dated (2026-10-23)
        prev = {"latest_index_value_jpy": 127166, "data_range": "x", "same_day_note": "n"}
        o = assemble.index_obj(None, None, "x", "psa10", prev, "2026-10-23T07:55:00+09:00")
        self.assertEqual(o["latest_index_value_jpy"], 127166)
        self.assertEqual(o["as_of"], "2026-10-23T07:55:00+09:00")
        self.assertIn("carried", o["carried_note"])
        self.assertNotIn("same_day_note", o)
        kept = assemble.index_obj(None, None, "x", "psa10", dict(prev, as_of="2026-10-22T08:00:00+09:00"), "2026-10-23T07:55:00+09:00")
        self.assertEqual(kept["as_of"], "2026-10-22T08:00:00+09:00")   # carried twice: still the real reading's date
        self.assertIn("error", assemble.index_obj(None, None, None, "psa10", None, None))
        self.assertIn("error", assemble.index_obj(None, None, None, "psa10", {"error": "not collected this run"}, None))


class Plan(unittest.TestCase):
    SNAP_AT = "2026-10-15T09:00:00+09:00"   # a Thursday

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "pricecheck" / "references").mkdir(parents=True)
        (self.root / "data" / "snapshots").mkdir(parents=True)
        listed = [
            {"snkrdunk_id": "1", "card_name_ja": "A [SV8a 217/187]", "image_url": "x", "psa_pop_url": "/pop/1", "psa_pop_no": "217"},
            {"snkrdunk_id": "2", "card_name_ja": "B [M2 110/080]", "psa_pop_url": "/pop/2"},
            {"snkrdunk_id": "3", "card_name_ja": "C [M6a 131/103]", "image_url": "x"},
            {"snkrdunk_id": "4", "card_name_ja": "D [MF 044/040]", "image_url": "x"},
            {"snkrdunk_id": "5", "card_name_ja": "E [S8b 222/184]", "image_url": "x"},
        ]
        self.write("pricecheck/references/cards.json", {"cards": listed})
        self.write("data/removed_cards.json", {"removed": {"5": {"name": "E [S8b 222/184]"}}})
        cards = [card("1", psa10=70000, a_low=40000, asof="2026-10-14T09:00:00+09:00", pop=9000),
                 card("2", a_low=3000, pop=120),
                 card("3", psa10=6000, verdict="watch"),
                 card("4", psa10=5000, verdict="defer")]
        self.write("data/snapshots/s.json", {"collected_at_jst": self.SNAP_AT, "cards": cards})
        self.write("data/manifest.json", {"snapshots": [{"file": "s.json", "collected_at_jst": self.SNAP_AT}]})

    def tearDown(self):
        shutil.rmtree(self.root)

    def write(self, rel, obj):
        (self.root / rel).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def plan_at(self, y, m, d, h=9):
        return plan.build_plan(self.root, now=datetime(y, m, d, h, tzinfo=JST))

    def test_weekday(self):
        p = self.plan_at(2026, 10, 16)   # Friday
        rows = {r[0]: r for r in p["plan"]}
        self.assertNotIn("5", rows)                                      # removed card
        self.assertEqual(rows["1"][:3], ["1", "full", 0])               # PSA10 market → full; photo on file
        self.assertEqual(rows["1"][3], 40000)                            # A list 2 days old → carry if the tile matches
        self.assertEqual(rows["2"][:3], ["2", "tile", 1])               # no market → tile; no photo → fetch it
        self.assertEqual(rows["2"][3], 3000)                             # list read at the snapshot (1 day)
        self.assertEqual([x[0] for x in p["psapop"]], ["2"])            # 9,000 graded psa → weekly; 120 → every run
        self.assertIn("weekly", p["pop_skipped"]["1"])
        self.assertEqual([x[0] for x in p["psapop_missing"]], ["3"])    # market, no pop page, not Defer
        self.assertEqual(sorted(x[0] for x in p["premium"]), ["1", "3", "4"])
        self.assertFalse(p["monday"])
        self.assertIsNotNone(p["scout"])                                 # no scout.json yet → due
        self.assertIn("s8b-222-184", p["scout"]["skip"])                 # removed cards aren't suggested again
        self.assertIn("sv8a-217-187", p["scout"]["skip"])

    def test_monday(self):
        p = self.plan_at(2026, 10, 19)
        self.assertTrue(p["monday"])
        self.assertTrue(all(r[1] == "full" and r[3] == 0 for r in p["plan"]))   # every card full, A lists re-read
        self.assertEqual(sorted(x[0] for x in p["psapop"]), ["1", "2"])
        self.assertEqual(sorted(x[0] for x in p["psapop_missing"]), ["3", "4"])  # Defer cards too, on Mondays

    def test_mature_population_catches_up(self):
        # Monday's weekly read was missed (Cloudflare/VPN): 8 days later a weekday full check reads it anyway (2026-10-23)
        p = self.plan_at(2026, 10, 23)
        self.assertEqual(sorted(x[0] for x in p["psapop"]), ["1", "2"])
        self.assertNotIn("1", p["pop_skipped"])

    def test_a_carry_expires(self):
        rows = {r[0]: r for r in self.plan_at(2026, 10, 17, 10)["plan"]}   # Saturday 10:00
        self.assertEqual(rows["1"][3], 0)        # read 10/14 09:00: 3 days old → read again
        self.assertEqual(rows["2"][3], 3000)     # no listings_as_of → the snapshot's time, 10/15 09:00: 2 days → carried

    def test_a_carry_price_rules(self):
        snap = {"collected_at_jst": self.SNAP_AT}
        now = datetime(2026, 10, 17, 8, 59, tzinfo=JST)   # 1 day 23:59 after the snapshot
        c = card("x", a_low=4000)
        self.assertEqual(plan.a_carry_price(c, snap, now, False), 4000)
        self.assertEqual(plan.a_carry_price(c, snap, now, True), 0)                         # Monday
        self.assertEqual(plan.a_carry_price(c, snap, now + timedelta(days=1, minutes=1), False), 0)   # 3 days
        self.assertEqual(plan.a_carry_price(card("x", a_low=4000, a_list=False), snap, now, False), 0)   # nothing to carry
        self.assertEqual(plan.a_carry_price(card("x", a_low=4000, asof="not a date"), snap, now, False), 0)
        self.assertEqual(plan.a_carry_price({}, snap, now, False), 0)

    def test_scout_every_other_day(self):
        self.write("data/scout.json", {"updated": "2026-10-15T08:00:00+09:00", "dismissed": ["zz-1-1"],
                                       "pool": {"p-1-2": {"read": "2026-10-15"}, "p-9-9": {}}})
        self.assertIsNone(self.plan_at(2026, 10, 16, 23)["scout"])          # 39 h after the last read
        s = self.plan_at(2026, 10, 17, 1)["scout"]                           # 41 h
        self.assertIn("zz-1-1", s["skip"])
        self.assertEqual(s["read"], {"p-1-2": "2026-10-15"})


class PremiumTokens(unittest.TestCase):
    def test_moves_and_peak(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import premium
        e = premium.decode(["PREM 9 d261020 r100 p200 m1.9 n40 g- c-1.5:12.0:- k2605:139700:2 s251020:2.0"])["9"]
        self.assertEqual(e["chg"], {"7": -1.5, "30": 12.0})
        self.assertEqual(e["peak"], {"month": "2026-05", "median": 139700, "points": 2})
        old = premium.decode(["PREM 9 d261020 r100 p200 m- n4 g- s251020:2.0"])["9"]   # lines from before 2026-10-23
        self.assertNotIn("chg", old)
        self.assertNotIn("peak", old)


if __name__ == "__main__":
    unittest.main(verbosity=1)
