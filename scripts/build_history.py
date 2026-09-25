#!/usr/bin/env python3
"""
Rebuild data/history.json: a compact per-card price series across every snapshot.

The site's price-history charts used to download every snapshot file (≈70 KB
each) the first time a card was expanded, which grows without bound with
several checks a day. This index is what the site reads instead: one small file,
a few hundred bytes per snapshot.

    python3 scripts/build_history.py          # rebuild (add_snapshot / apply_analysis call this)

Per snapshot: {"d": collected_at_jst, "m": check_mode, "p": {url: [price, confirmed]}}
where price follows the site's own rule (analysis.representative_price if set,
else the PSA10 lowest ask; cards with no PSA10 ask are left out) and confirmed
is 1 when price_source is sales_confirmed.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build(root: Path = ROOT) -> Path:
    manifest = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = sorted([s for s in manifest.get("snapshots", []) if s.get("collected_at_jst")],
                   key=lambda s: s["collected_at_jst"])
    series = []
    for s in snaps:
        path = root / "data" / "snapshots" / s["file"]
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        points = {}
        for c in d.get("cards", []):
            psa10 = (c.get("grades") or {}).get("psa10") or {}
            if psa10.get("lowest_price") is None:
                continue
            a = c.get("analysis") or {}
            price = a.get("representative_price", psa10["lowest_price"])
            if price is None:
                continue
            points[c.get("url")] = [price, 1 if a.get("price_source") == "sales_confirmed" else 0]
        series.append({"d": d.get("collected_at_jst", s["collected_at_jst"]),
                       "m": s.get("check_mode", "full"), "p": points})
    out = root / "data" / "history.json"
    out.write_text(json.dumps({"snapshots": series}, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    # The track record (data/calls.json) is derived from the same snapshots.
    try:
        import build_calls
        build_calls.build(root)
    except Exception as e:  # never block publishing a price check over it
        print(f"warning: couldn't rebuild data/calls.json: {e}")
    return out


if __name__ == "__main__":
    p = build()
    print(f"Rebuilt {p.relative_to(ROOT)} ({p.stat().st_size:,} bytes)")
