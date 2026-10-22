#!/usr/bin/env python3
"""
The SNKRDUNK lines as a diff against the previous run (2026-10-20): the Python half of pricecheck/runner.js's POLL.

A card's line re-sends its last 20 PSA10 and 20 A-rank sales (and, on full checks, its listing lists), and most of
them are the same as last time. Claude has to retype every line into the publish step, which was the slowest part
of a run. So for snkrdunk_quick / snkrdunk_full the POLL writes each run of entries that also stands in the previous
line's list of the same letter as <start>.<count> (a literal entry never looks like that):

    P^3.10,39480@261015,14.6,39700@3h  = base P entries 3..12, a new one, base entries 14..19, a new one

and ends the run's lines with

    #B <mode> <new base hash> <lines hash>
       mode: the base hash it diffed against | - (base didn't match: lines sent whole, base started over)
             | + (a retry run: lines whole, base updated)

The base is each card's last good line (plus its last L/R list when the new line has none), kept in the site's
localStorage ("pc:base") and here in data/incoming/snk-base.json; jsrun.py passes this file's hash in the RUN call,
so the page diffs only when both hold the same base. process() rebuilds the lines, checks them against the page's
hash (the exact text the POLL used to return) and applies the same base update. The base file is saved only once
the run is published (save()); when anything doesn't add up it's dropped, and the next run sends whole lines and
starts the base over on both sides.

    python3 scripts/salesdiff.py hash      # the hash jsrun.py passes
    python3 scripts/salesdiff.py expand F  # print F's lines rebuilt (no base update)
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_FILE = Path("data") / "incoming" / "snk-base.json"
ID = re.compile(r"\d+")
LIST = re.compile(r"[PALR][^=^\s]*=")
PACKED = re.compile(r"([PALR])([^=^\s]*)\^(.+)")
REF = re.compile(r"(\d+)\.(\d+)")


class DiffError(ValueError):
    pass


def h16(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def canon(base):
    return "".join(f"{k}\t{base[k]}\n" for k in sorted(base))


def load_base(root=ROOT):
    try:
        b = json.loads((root / BASE_FILE).read_text(encoding="utf-8"))
        return b if isinstance(b, dict) and all(isinstance(v, str) for v in b.values()) else {}
    except (OSError, ValueError):
        return {}


def base_hash(root=ROOT):
    return h16(canon(load_base(root)))


def update(base, lines):
    """Same rule as runner.js update(): each card's last good line, keeping its last L/R list when the new line has none."""
    for line in lines:
        t = line.split(" ")
        if not ID.fullmatch(t[0]) or (len(t) > 1 and t[1].startswith("E")):
            continue
        keep = [y for y in (base.get(t[0]) or "").split(" ")
                if y[:1] in ("L", "R") and LIST.match(y) and not any(z[:1] == y[:1] and LIST.match(z) for z in t)]
        base[t[0]] = " ".join(t + keep)


def expand_line(line, base):
    t = line.split(" ")
    if not ID.fullmatch(t[0]):
        return line
    b = (base.get(t[0]) or "").split(" ")
    out = [t[0]]
    for x in t[1:]:
        m = PACKED.fullmatch(x)
        if not m:
            out.append(x)
            continue
        bt = next((y for y in b if y[:1] == m[1] and LIST.match(y)), None)
        if bt is None:
            raise DiffError(f"card {t[0]}: no {m[1]} list in the base line for {x!r}")
        old = bt[bt.index("=") + 1:].split(",")
        lst = []
        for it in m[3].split(","):
            r = REF.fullmatch(it)
            if not r:
                lst.append(it)
                continue
            j, k = int(r[1]), int(r[2])
            if k < 1 or j + k > len(old):
                raise DiffError(f"card {t[0]}: {x!r} points past the base list ({len(old)} entries)")
            lst += old[j:j + k]
        out.append(f"{m[1]}{m[2]}={','.join(lst)}")
    return " ".join(out)


def process(text, root=ROOT):
    """(lines with every diff rebuilt and the #B lines removed, new base or None, saw a #B line, notes).
    Raises DiffError when diffed lines can't be rebuilt exactly (then the full lines have to be sent)."""
    base = load_base(root)
    valid, seen, notes = True, False, []
    out, pending = [], []          # pending: (index in out, line) card lines since the last #B line
    for raw in text.splitlines():
        st = raw.strip()
        if st.startswith("#B "):
            parts = st.split()
            if len(parts) != 4:
                raise DiffError(f"bad #B line {st!r}")
            seen = True
            mode, nb, fh = parts[1:]
            packed = any("^" in ln for _, ln in pending)
            cur = h16(canon(base))
            if packed and mode != cur:
                raise DiffError("the page diffed against another base than data/incoming/snk-base.json")
            exp = [expand_line(ln, base) if packed else ln for _, ln in pending]
            if h16("\n".join(exp)) != fh:
                if packed:
                    raise DiffError("the rebuilt lines don't match the page's hash")
                notes.append("the SNKRDUNK lines differ from what the page returned (hash check); published as pasted")
                valid = False
            for (i, _), e in zip(pending, exp):
                out[i] = e
            if mode == "-":
                base = {}
            elif mode != "+" and mode != cur:
                valid = False
            update(base, exp)
            if nb == "-" or h16(canon(base)) != nb:
                valid = False
            pending = []
            continue
        out.append(raw)
        first = st.split(" ", 1)[0]
        if ID.fullmatch(first):
            pending.append((len(out) - 1, st))
    if any("^" in ln for _, ln in pending):
        raise DiffError("diffed lines without their #B line (paste every line the POLL returned, the #B line too)")
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), (base if valid else None), seen, notes


TIMING = re.compile(r"#T (\S+) (\S+) (\S+)")


def take_timings(text):
    """(text without the `#T <script> <started> <finished>` lines the runner's POLL adds, [(script, started, finished)])."""
    keep, times = [], []
    for ln in text.splitlines():
        m = TIMING.fullmatch(ln.strip())
        if m:
            times.append(m.groups())
        else:
            keep.append(ln)
    return "\n".join(keep) + ("\n" if text.endswith("\n") else ""), times


def save(root, base, seen):
    """After a successful publish: keep the new base, or drop it when it didn't add up (the next run starts over)."""
    if not seen:
        return
    p = root / BASE_FILE
    try:
        if base is None:
            p.unlink(missing_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(base, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError as e:
        print(f"warning: couldn't update {BASE_FILE}: {e}")


FALLBACK = ("Re-read the lines whole instead: print the full POLL with `python3 pricecheck/jsrun.py poll {name} --full`, "
            "paste it on the same tab (it returns the same lines undiffed, plus the #B line) and publish those lines.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["hash"]:
        print(base_hash())
    elif a[:1] == ["expand"] and len(a) == 2:
        print(process(Path(a[1]).read_text(encoding="utf-8"))[0], end="")
    else:
        print(__doc__)
