#!/usr/bin/env python3
"""
Save the story behind a card's artwork to data/stories.json (the card page's Story tab and the
Stories page), then commit and push.

    python3 scripts/set_story.py --missing                 # tracked cards that have no story yet
    python3 scripts/set_story.py <snkrdunk_id> [--no-push] <<'EOF'
    {"illustrator": "YASHIRO Nanaco", "illustrator_ja": "八館ななこ" or null,
     "art": "2–4 sentences: what the artwork shows, details worth noticing",
     "story": "1–3 sentences: series/connection/game or anime reference" or null,
     "set": "1–2 sentences: set or product, release date, what it was known for",
     "trivia": ["verifiable fact", ...],
     "english": "English release name/number" or null,
     "sources": [{"title": "...", "url": "https://..."}, ...],
     "confidence": "high" | "medium" | "low"}
    EOF

Full checks run this for newly added cards (pricecheck/FULL-CHECK.md step 8c). A new story
replaces the card's old one. Required: art, set and at least one source; illustrator may be null
only when no source credits one.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "stories.json"
sys.path.insert(0, str(ROOT / "pricecheck"))


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {"cards": {}}


def missing():
    import plan
    have = load().get("cards", {})
    out = []
    for c in plan.load_cards(ROOT):
        url = f"https://snkrdunk.com/apparels/{c['snkrdunk_id']}"
        if url not in have:
            out.append((c["snkrdunk_id"], c.get("card_name_ja", "")))
    return out


def validate(d):
    for k in ("art", "set"):
        if not isinstance(d.get(k), str) or len(d[k].strip()) < 20:
            die(f'"{k}" is missing or too short')
    src = d.get("sources") or []
    if not src or not all(isinstance(s, dict) and str(s.get("url", "")).startswith("http") for s in src):
        die('"sources" needs at least one {"title", "url"} with an http(s) url')
    if re.search(r"snkrdunk\.com|pokeca-chart\.com", json.dumps(src)):
        die("sources must not be SNKRDUNK or pokeca-chart pages")
    if d.get("confidence") not in ("high", "medium", "low"):
        d["confidence"] = "medium"
    keep = ("illustrator", "illustrator_ja", "art", "story", "set", "trivia", "english", "sources", "confidence")
    out = {k: d.get(k) for k in keep}
    out["trivia"] = [t for t in (out["trivia"] or []) if isinstance(t, str) and t.strip()]
    out["written"] = datetime.now(JST).replace(microsecond=0).isoformat()
    return out


def main():
    a = sys.argv[1:]
    if "--missing" in a:
        m = missing()
        print(f"{len(m)} tracked card(s) without a story" + (":" if m else "."))
        for sid, name in m:
            print(f"  {sid} {name}")
        return
    ids = [x for x in a if x.isdigit()]
    if not ids:
        die(__doc__)
    sid = ids[0]
    try:
        d = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        die(f"the story isn't valid JSON: {e}")
    entry = validate(d)
    push = "--no-push" not in a
    if push:
        subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=ROOT)
    data = load()
    data.setdefault("cards", {})[f"https://snkrdunk.com/apparels/{sid}"] = entry
    data["updated"] = entry["written"]
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"saved the story for {sid} (illustrator: {entry['illustrator'] or 'unknown'}, {len(entry['sources'])} source(s))")
    if not push:
        return
    for cmd in (["git", "add", str(PATH)], ["git", "commit", "-q", "-m", f"story: {sid}"], ["git", "push", "-q"]):
        r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        if r.returncode != 0:
            die(f"{' '.join(cmd)} failed:\n{r.stderr or r.stdout}")
    print("Pushed.")


if __name__ == "__main__":
    main()
