#!/usr/bin/env python3
"""
First (and only) setup call of a price check: one device_bash call instead of four.

    R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); cd "$R" && git pull --ff-only --quiet; python3 pricecheck/start.py [--mode full|quick]

It prints, in order:
  1. the status line (scripts/check_status.py) and open card requests (scripts/card_requests.py list);
  2. MODE: the mode to run (the one asked for with --mode, else full for the JST day's first check, quick after);
  3. the procedure to follow for that mode (pricecheck/FULL-CHECK.md or pricecheck/QUICK-CHECK.md), in full;
  4. full: today's plan (pricecheck/plan.py), the browser calls (pricecheck/jsrun.py full) and the
     PSA backlog schedule (scripts/psa_backlog.py due); quick: the browser call (pricecheck/jsrun.py quick).
It also starts the run clock (scripts/runclock.py). Nothing is published or changed in the repo.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Local Claude Code runs (the menu bar widget sets PSA10_RUN=1) already work in the repo root. The procedures' repo-finding
# prefix R=$(ls -d …); cd "$R" && can't be matched against .claude/settings.json's allow list (the $(…)), so every
# command written with it stops an unattended run for a permission question. Print the procedure without it.
LOCAL = os.environ.get("PSA10_RUN") == "1"
PREFIX = re.compile(r'R=\$\(ls -d "\$HOME"/mnt/\*/psa10-tracker[^;]*;\s*cd "\$R"\s*(?:&&|;)\s*')
# the procedures also write the short form `cd "$R" && …` once $R is set; locally $R is never set, so drop that too
CD_R = re.compile(r'cd "\$R"\s*(?:&&|;)\s*')


# A heredoc (`cmd <<'EOF'` + lines + `EOF`) makes the command long and hard to parse: Claude Code's permission check gives
# up on it ("Parser aborted … over-length", always above 10,000 characters), so it can't match the allow list and asks.
# Locally the lines go into a file with the Write tool and the command reads it with `< file` (2026-10-18).
FENCED_HEREDOC = re.compile(r"(?ms)^```[a-z]*\n(?P<cmd>[^\n]*?)\s*<<'(?P<tag>\w+)'(?P<rest>[^\n]*)\n(?P<body>.*?)\n(?P=tag)\n```")
INLINE_HEREDOC = re.compile(r"`(?P<cmd>[^`]*?(?P<stem>\w+)\.py[^`]*?)\s*<<'(?P<tag>\w+)'`")


def _stem(cmd):
    m = re.findall(r"(\w+)\.py", cmd)
    return m[-1] if m else "input"


def no_heredocs(text):
    def fenced(m):
        f = f"data/incoming/{_stem(m['cmd'])}-in.txt"
        return (f"Save these lines, verbatim, with the **Write** tool to `{f}`:\n```\n{m['body']}\n```\n"
                f"and **in the same message** (after the Write; the calls run in order, so the command reads the new file) "
                f"run this one Bash call:\n```\n{m['cmd'].rstrip()} < {f}{m['rest']}\n```")
    text = FENCED_HEREDOC.sub(fenced, text)
    text = INLINE_HEREDOC.sub(lambda m: f"`{m['cmd'].rstrip()} < data/incoming/{m['stem']}-in.txt` (save the lines to that file with the Write tool first, in the same message)", text)
    # the leftover "+ the lines verbatim + `EOF`" / "… `EOF`" after an inline heredoc
    text = re.sub(r"\s*(?:\+ the lines verbatim \+|…)\s*`(?:EOF|JSON)`", "", text)
    return text.replace("into a heredoc", "into a file (Write tool)").replace("with a heredoc", "with the Write tool")


def local(text):
    if not LOCAL:
        return text
    # section 0 (delete permission for the desktop app's mounted folder) doesn't apply on the Mac itself
    text = re.sub(r"(?ms)^## 0\. .*?(?=^## )", "", text)
    text = CD_R.sub("", PREFIX.sub("", text)).replace('"$R"/', "").replace("$R/", "")
    return no_heredocs(text)


def clear_inputs():
    """Remove the previous run's data/incoming/*-in.txt files. The Write tool refuses to overwrite a file this session
    hasn't read, which cost a failed Write and a second copy of the lines; and a Write sent in the same message as its
    command must never leave the command reading the last run's lines (it now fails on the missing file instead)."""
    for f in (ROOT / "data" / "incoming").glob("*-in.txt"):
        try:
            f.unlink()
        except OSError:
            pass   # a desktop-app run without delete permission: harmless (its procedures use heredocs)


# Sections of a procedure that apply only on some runs (FULL-CHECK.md): <!-- only:<cond> --> … <!-- /only -->.
# start.py prints them only when today's plan needs them, so a run doesn't read steps it won't do (2026-10-23).
ONLY = re.compile(r"(?ms)^<!-- only:(\w+) -->\n(.*?)^<!-- /only -->\n")
ONLY_NAMES = {"psapop": "PSA pop report", "scout": "Scout", "rebuild": "monthly model rebuild", "monday": "Monday steps"}


def only(text, conds):
    """Keep a marked section when its condition holds (an unknown condition keeps it); drop the markers either way."""
    return ONLY.sub(lambda m: m[2] if conds.get(m[1], True) else "", text)


def today_conds():
    try:
        sys.path.insert(0, str(ROOT / "pricecheck"))
        import plan as planmod
        p = planmod.build_plan(ROOT)
        return {"psapop": bool(p.get("psapop")), "scout": p.get("scout") is not None,
                "rebuild": bool(p.get("odds_rebuild_due")), "monday": bool(p.get("monday"))}
    except Exception:  # noqa: BLE001  never lose a section over this
        return {}


def sh(*cmd):
    r = subprocess.run([sys.executable, *cmd], cwd=ROOT, text=True, capture_output=True)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode:
        out += f"\n(!) {' '.join(cmd)} exited with {r.returncode}"
    return out.rstrip("\n")


def main():
    a = sys.argv[1:]
    if a[:1] == ["--show"] and len(a) == 2:   # a step file, as a local run should read it
        print(local(only((ROOT / a[1]).read_text(encoding="utf-8"), {})).rstrip("\n"))
        return
    asked = None
    for i, x in enumerate(a):
        if x == "--mode" and i + 1 < len(a):
            asked = a[i + 1]
        elif x.startswith("--mode="):
            asked = x[7:]
    if asked not in (None, "full", "quick"):
        sys.exit("ERROR: --mode must be full or quick")

    status = sh("scripts/check_status.py")
    print(status)
    print(sh("scripts/card_requests.py", "list"))
    try:
        st = json.loads(status.splitlines()[0])
    except Exception:  # noqa: BLE001
        st = {}
    mode = asked or st.get("suggested_mode") or "full"
    why = "asked for" if asked else ("first check of the JST day" if mode == "full" else f"today's full check already ran ({st.get('last_full_jst')})")
    print(f"\nMODE: {mode} ({why})")
    print(sh("scripts/runclock.py", "start", mode))
    clear_inputs()

    doc = ROOT / "pricecheck" / ("FULL-CHECK.md" if mode == "full" else "QUICK-CHECK.md")
    print(f"\n======== {doc.relative_to(ROOT)} (follow it) ========\n")
    if LOCAL:
        print("LOCAL RUN (menu bar widget): the working directory is the repo root and was just pulled. Run every command "
              "exactly as printed here, one plain command per Bash call: no R=$(ls -d …); cd \"$R\" && prefix, no $(…), no \"$HOME\". "
              "When a step file or skill shows that prefix, leave it out. Never use a heredoc (<<'EOF' … EOF): save the lines "
              "with the Write tool to data/incoming/<script>-in.txt and run the command with `< data/incoming/<script>-in.txt`. "
              "Read a step file through the same filter: python3 pricecheck/start.py --show pricecheck/steps/<file>. "
              "Save round trips: send calls that don't depend on each other in one message, and put browser steps you can "
              "predict into one browser_batch (the procedure says which). "
              "This run can't ask for permission: anything not pre-approved is refused, so a refused call means "
              "the command has the wrong form, not that you should retry it differently.\n")
    conds = today_conds() if mode == "full" else {}
    skipped = [ONLY_NAMES.get(k, k) for k, v in conds.items() if not v]
    if skipped:
        print(f"(Not part of today's run, so left out below: {', '.join(skipped)}.)\n")
    print(local(only(doc.read_text(encoding="utf-8"), conds).rstrip("\n")))
    print("\n======== today's setup output ========\n")
    if mode == "full":
        print(sh("pricecheck/plan.py"))
        print()
        print(sh("pricecheck/jsrun.py", "full"))
        print()
        print(sh("scripts/psa_backlog.py", "due"))
    else:
        print(sh("pricecheck/jsrun.py", "quick"))


if __name__ == "__main__":
    main()
