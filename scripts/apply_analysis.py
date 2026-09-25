#!/usr/bin/env python3
"""
Apply card evaluations (tiers, peak, verdict, ...) to the tracker's latest snapshot.

Usage:
    python3 scripts/apply_analysis.py                  # reads the JSON from the clipboard (macOS pbpaste)
    python3 scripts/apply_analysis.py path/to/eval.json
    python3 scripts/apply_analysis.py --dry-run        # show what would change, write nothing
    python3 scripts/apply_analysis.py --no-push        # write + commit locally, don't push
    python3 scripts/apply_analysis.py --card "SV5a 090/066"   # input is ONE bare analysis object
    python3 scripts/apply_analysis.py --skip-missing   # apply what matches, skip cards not in the snapshot

Accepted input shapes (whatever the evaluation skill or a chat hands you):
  1. {"<card name or SNKRDUNK url>": {analysis}, ...}      keys like "_note" are ignored
  2. "<card name>": {analysis}, "<card name>": {analysis}  the same without the outer braces
  3. {analysis}                                            one bare block — needs --card

Cards are matched against the latest snapshot by, in order: SNKRDUNK url, exact card
name, card name after normalizing full-/half-width characters, and finally the set code
+ number in brackets (e.g. "[SV5a 090/066]"). A key that matches more than one card, or
none, stops the run rather than guessing — similar names really do collide here
(ピカチュウV CSR vs ピカチュウVMAX CSR, ゲッコウガ vs メガゲッコウガ).

The new block is merged over the card's existing analysis: keys you provide replace the
old ones, keys you leave out (e.g. raw_tiers, grading_fee_jpy) are kept. When a new
verdict comes in, the old verdict_price_ref is dropped (a fresh representative_price
takes its place, or else today's lowest ask becomes the new reference).

Before writing, the script runs `git pull --ff-only` so it always edits the real latest
snapshot, and afterwards commits and pushes (credentials come from the repo's
configured credential file — no token needed here).
"""

import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

VALID_TAGS = {"definitely_buy", "buy", "watch", "dont_buy", "defer"}
VALID_SOURCES = {"sales_confirmed", "ask_depth", "unconfirmed"}
TAG_LABELS = {"definitely_buy": "Definitely buy", "buy": "Buy", "watch": "Watch",
              "dont_buy": "Don't buy", "defer": "Defer"}


# ---------- small helpers ----------

def die(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def norm(s: str) -> str:
    """NFKC folds full-width ＆/Ａ/０ etc. to half-width; also collapse whitespace."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip().lower()


def set_code(name: str) -> Optional[str]:
    """'ゲッコウガex SAR [SV5a 090/066](...)' -> 'sv5a 090/066'."""
    m = re.search(r"\[([^\]]+)\]", unicodedata.normalize("NFKC", name or ""))
    return norm(m.group(1)) if m else None


def zone(tiers: dict, price) -> Optional[str]:
    if not tiers or price is None:
        return None
    if price <= tiers["definitely_buy"]:
        return "definitely_buy"
    if price <= tiers["buy_upper"]:
        return "buy"
    if price <= tiers["ceiling"]:
        return "watch"
    return "dont_buy"


def fmt_yen(v) -> str:
    return "—" if v is None else f"¥{v:,.0f}"


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, check=check, text=True,
                          capture_output=True, env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"})


# ---------- input ----------

def read_input(args: List[str]) -> str:
    files = [a for a in args if not a.startswith("--")]
    # --card takes a value; don't treat it as a file
    if "--card" in args:
        i = args.index("--card")
        if i + 1 < len(args) and args[i + 1] in files:
            files.remove(args[i + 1])
    if files:
        p = Path(files[0])
        if not p.exists():
            die(f"File not found: {p}")
        return p.read_text(encoding="utf-8")
    try:
        raw = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True).stdout
    except FileNotFoundError:
        die("pbpaste not found. On non-macOS, pass a file path instead.")
    if not raw.strip():
        die("Clipboard is empty. Copy the evaluation JSON first, or pass a file path.")
    return raw


def parse_input(raw: str):
    text = raw.strip()
    # tolerate ```json fences pasted from chat
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as first_err:
        # shape 2: "key": {...}, "key": {...}  (no outer braces, maybe a trailing comma)
        wrapped = "{" + re.sub(r",\s*$", "", text) + "}"
        try:
            return json.loads(wrapped)
        except json.JSONDecodeError:
            die(f"That isn't valid JSON ({first_err}). Make sure you copied the whole block.")


def looks_like_analysis(obj) -> bool:
    return isinstance(obj, dict) and any(k in obj for k in ("tiers", "verdict", "representative_price", "peak"))


def to_entries(data, card_arg: Optional[str]) -> List[Tuple[str, dict]]:
    if looks_like_analysis(data):
        if not card_arg:
            die("This is a single analysis block with no card name attached. Re-run with "
                '--card "<name, url, or set code like SV5a 090/066>".')
        return [(card_arg, data)]
    if not isinstance(data, dict):
        die("Expected a JSON object mapping card names/urls to analysis blocks.")
    entries = [(k, v) for k, v in data.items() if not k.startswith("_")]
    bad = [k for k, v in entries if not looks_like_analysis(v)]
    if bad:
        die("These entries don't look like analysis blocks (no tiers/verdict/peak): " + ", ".join(bad))
    if not entries:
        die("No card entries found in the input.")
    return entries


# ---------- validation ----------

def validate(key: str, a: dict) -> List[str]:
    """Returns warnings; dies on anything that would break the site."""
    warn = []
    t = a.get("tiers")
    if t is not None:
        for k in ("definitely_buy", "buy_upper", "ceiling"):
            if not isinstance(t.get(k), (int, float)):
                die(f"{key}: tiers.{k} is missing or not a number.")
        if not (t["definitely_buy"] <= t["buy_upper"] <= t["ceiling"]):
            die(f"{key}: tiers must satisfy definitely_buy ≤ buy_upper ≤ ceiling "
                f"(got {t['definitely_buy']} / {t['buy_upper']} / {t['ceiling']}).")
    v = a.get("verdict")
    if v is not None:
        if v.get("tag") not in VALID_TAGS:
            die(f"{key}: verdict.tag '{v.get('tag')}' isn't one of {sorted(VALID_TAGS)}.")
        if not v.get("reasoning"):
            warn.append("verdict has no reasoning text")
        preds = v.get("predictions")
        if preds is not None:
            if not isinstance(preds, list):
                die(f"{key}: verdict.predictions must be a list.")
            for i, p in enumerate(preds):
                where = f"{key}: verdict.predictions[{i}]"
                if not isinstance(p, dict):
                    die(f"{where} must be an object.")
                if p.get("type") not in ("touch_below", "touch_above"):
                    die(f"{where}.type must be touch_below or touch_above.")
                if not isinstance(p.get("p"), (int, float)) or not 0 < p["p"] < 1:
                    die(f"{where}.p must be a probability between 0 and 1 (e.g. 0.45).")
                if not isinstance(p.get("price"), (int, float)):
                    die(f"{where}.price must be a number.")
                try:
                    datetime.strptime(str(p.get("by")), "%Y-%m-%d")
                except ValueError:
                    die(f"{where}.by must be a date like 2026-12-25.")
                if not p.get("text"):
                    warn.append(f"predictions[{i}] has no text")
        elif v.get("reasoning") and "%" in v.get("reasoning", ""):
            warn.append("reasoning states odds but verdict.predictions is missing, so they won't be scored")
    src = a.get("price_source")
    if src is not None and src not in VALID_SOURCES:
        warn.append(f"price_source '{src}' is unusual (expected one of {sorted(VALID_SOURCES)})")
    if "verdict" in a and a.get("representative_price") is None:
        warn.append("verdict given without representative_price — the site will show the live lowest ask instead")
    pk = a.get("peak")
    if pk is not None and not isinstance(pk.get("price"), (int, float)):
        die(f"{key}: peak.price is missing or not a number.")
    return warn


# ---------- matching ----------

def match_card(key: str, cards: List[dict]) -> dict:
    k = key.strip()
    if k.startswith("http"):
        hits = [c for c in cards if c.get("url", "").rstrip("/") == k.rstrip("/")]
        if len(hits) == 1:
            return hits[0]
        die(f"No card in the snapshot has url {k}.")
    stages = [
        lambda c: c.get("card_name_ja") == k,
        lambda c: norm(c.get("card_name_ja")) == norm(k),
    ]
    code = set_code(k) or (norm(k) if re.search(r"\d+/\d+", k) else None)
    if code:
        stages.append(lambda c: set_code(c.get("card_name_ja")) == code)
    for test in stages:
        hits = [c for c in cards if test(c)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            die(f"'{key}' matches more than one card: " + "; ".join(h["card_name_ja"] for h in hits))
    raise LookupError(key)


# ---------- main ----------

def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    no_push = "--no-push" in args
    skip_missing = "--skip-missing" in args
    card_arg = None
    if "--card" in args:
        i = args.index("--card")
        if i + 1 >= len(args):
            die("--card needs a value.")
        card_arg = args[i + 1]

    root = Path(__file__).resolve().parent.parent
    manifest_path = root / "data" / "manifest.json"
    if not manifest_path.exists():
        die(f"Couldn't find data/manifest.json under {root}.")

    entries = to_entries(parse_input(read_input(args)), card_arg)

    if not dry:
        pull = git(root, "pull", "--ff-only", "--quiet", check=False)
        if pull.returncode != 0:
            die("`git pull --ff-only` failed — your local repo has diverged or has uncommitted "
                "changes. Sort that out first:\n" + (pull.stderr or pull.stdout))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snaps = sorted([s for s in manifest.get("snapshots", []) if s.get("collected_at_jst")],
                   key=lambda s: s["collected_at_jst"])
    if not snaps:
        die("No snapshots in the manifest yet.")
    snap_file = snaps[-1]["file"]
    snap_path = root / "data" / "snapshots" / snap_file
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    cards = data.get("cards", [])
    print(f"Latest snapshot: {snap_file} ({snaps[-1]['collected_at_jst']})\n")

    planned, missing = [], []
    for key, new in entries:
        warns = validate(key, new)
        try:
            card = match_card(key, cards)
        except LookupError:
            missing.append(key)
            continue
        planned.append((card, new, warns))

    if missing:
        msg = "Not found in the latest snapshot (add the card to the tracker first):\n  - " + "\n  - ".join(missing)
        if skip_missing:
            print("Skipping — " + msg + "\n")
        else:
            die(msg + "\nRe-run with --skip-missing to apply the rest anyway.")
    if not planned:
        die("Nothing to apply.")

    for card, new, warns in planned:
        old = card.get("analysis") or {}
        merged = {**old, **new}
        # verdict_price_ref = "the price the current verdict was written against",
        # used by the site's drift note. A fresh representative_price replaces it;
        # a new verdict without one is anchored to today's lowest ask instead, so
        # the drift note never measures from the *previous* verdict's price.
        if new.get("representative_price") is not None:
            merged.pop("verdict_price_ref", None)
        elif "verdict" in new:
            merged.pop("verdict_price_ref", None)
            lowest = (card.get("grades", {}).get("psa10") or {}).get("lowest_price")
            if lowest is not None and merged.get("representative_price") is None:
                merged["verdict_price_ref"] = lowest
        live_price = merged.get("representative_price")
        if live_price is None:
            live_price = (card.get("grades", {}).get("psa10") or {}).get("lowest_price")
        name = card["card_name_ja"]
        old_tag = (old.get("verdict") or {}).get("tag")
        new_tag = (merged.get("verdict") or {}).get("tag")
        z = zone(merged.get("tiers"), live_price)
        t = merged.get("tiers") or {}
        print(f"• {name}")
        print(f"    price {fmt_yen(live_price)}   tiers {fmt_yen(t.get('definitely_buy'))} / "
              f"{fmt_yen(t.get('buy_upper'))} / {fmt_yen(t.get('ceiling'))}")
        print(f"    verdict {TAG_LABELS.get(old_tag, old_tag or '—')} → {TAG_LABELS.get(new_tag, new_tag or '—')}"
              f"   (live zone: {TAG_LABELS.get(z, '—')})")
        if new_tag and z and new_tag not in ("defer", z):
            print(f"    note: written verdict ({TAG_LABELS[new_tag]}) differs from the price zone "
                  f"({TAG_LABELS[z]}) — the site will show the zone and flag the difference")
        for w in warns:
            print(f"    warning: {w}")
        card["analysis"] = merged

    if dry:
        print("\nDry run — nothing written.")
        return

    snap_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rel = str(snap_path.relative_to(root))
    sys.path.insert(0, str(root / "scripts"))
    import build_history
    build_history.build(root)  # representative_price feeds the price-history chart
    git(root, "add", rel, "data/history.json", "data/calls.json")
    names = ", ".join(re.sub(r"[\[(].*$", "", c["card_name_ja"]).strip() for c, _, _ in planned)
    commit = git(root, "commit", "-m", f"analysis: update {names}", check=False)
    if commit.returncode != 0:
        print("\nNothing changed (the snapshot already had exactly this analysis).")
        return
    print(f"\nCommitted to {rel}.")
    if no_push:
        print("Skipping push (--no-push).")
        return
    push = git(root, "push", check=False)
    if push.returncode != 0:
        die("git push failed:\n" + (push.stderr or push.stdout))
    print("Pushed. The site updates in a minute or two.")


if __name__ == "__main__":
    main()
