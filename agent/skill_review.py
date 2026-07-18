"""Weekly skill self-review — the AI reads its own scorecard and edits its
own DD method (agent/skill/memecoin-dd/SKILL.md).

Ground truth comes from the outcome tracker: every verdict is joined with the
coin's actual return after the alert. When enough verdicts have matured, the
scorecard (per-verdict performance + the worst concrete misses) is handed to
Hermes with terminal access and ONE job: make the smallest SKILL.md edit that
would have prevented the systematic mistakes. The output contract must stay
identical (analyst.py parses it).

Changes are applied to the working tree but NOT committed — the diff is sent
to Telegram for human review; `git diff` / `git checkout` are the audit trail
and undo. Skips (quietly) until >= --min-matured verdicts have outcomes.

Runs via LaunchAgent com.sunrise.skill-review (Sundays 09:00). By hand:

    python3 agent/skill_review.py --now --dry-run   # scorecard only, no edit
    python3 agent/skill_review.py --now             # full run
"""
from __future__ import annotations

import argparse
import html
import json
import os
import statistics
import subprocess
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "pons"))
sys.path.insert(0, os.path.join(REPO, "tracker"))
import report as rpt  # noqa: E402
import telegram  # noqa: E402

VERDICTS = os.path.join(REPO, "tracker", "data", "agent_verdicts.jsonl")
SKILL = os.path.join(HERE, "skill", "memecoin-dd", "SKILL.md")
HERMES = os.path.expanduser("~/.local/bin/hermes")


def matured_verdicts(min_age_h=8.0):
    """[(verdict_row, alert, ret)] for verdicts whose alert has an outcome."""
    alerts = {rpt.alert_id(a): a for a in rpt.load(rpt.ALERTS)}
    snaps_by_id = defaultdict(list)
    for s in rpt.load(rpt.SNAPS):
        snaps_by_id[s["id"]].append(s)
    now = time.time()
    out = []
    if not os.path.exists(VERDICTS):
        return out
    for ln in open(VERDICTS):
        try:
            v = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        a = alerts.get(v.get("id"))
        if not (v.get("ok") and a and (now - a["t"]) >= min_age_h * 3600):
            continue
        ret = rpt.ret_at(a, snaps_by_id.get(v["id"], []), 480) \
            or rpt.ret_at(a, snaps_by_id.get(v["id"], []), 240)
        if ret is not None:
            out.append((v, a, ret))
    return out


def scorecard(rows):
    L = ["=== AI-DD SCORECARD (return ~8h after alert) ==="]
    byv = defaultdict(list)
    for v, a, r in rows:
        byv[v["verdict"]].append(r)
    for verd in ("BUY-WATCH", "NEUTRAL", "AVOID"):
        rs = byv.get(verd)
        if rs:
            hit = sum(1 for r in rs if r >= 0.5) / len(rs)
            L.append(f"{verd}: n={len(rs)} median {statistics.median(rs)*100:+.0f}% · hit(+50%) {hit*100:.0f}%")
    L.append("")
    misses = sorted([x for x in rows if x[0]["verdict"] == "BUY-WATCH" and x[2] <= -0.5],
                    key=lambda x: x[2])[:3]
    moons = sorted([x for x in rows if x[0]["verdict"] == "AVOID" and x[2] >= 1.0],
                   key=lambda x: -x[2])[:3]
    for label, group in (("WORST BUY-WATCH (dumped)", misses), ("MISSED MOONS (said AVOID)", moons)):
        if group:
            L.append(label + ":")
            for v, a, r in group:
                L.append(f"  {a.get('symbol')} ({a.get('platform')}) ret {r*100:+.0f}% "
                         f"conf {v.get('conf')} — whys: {'; '.join(v.get('whys') or [])}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true", help="(compat flag — always runs once)")
    ap.add_argument("--min-matured", type=int, default=10)
    ap.add_argument("--timeout", type=float, default=420.0)
    ap.add_argument("--dry-run", action="store_true", help="print scorecard, skip the edit")
    args = ap.parse_args()

    rows = matured_verdicts()
    if len(rows) < args.min_matured:
        print(f"[{time.strftime('%H:%M:%S')}] skip: only {len(rows)} matured verdicts "
              f"(< {args.min_matured})", flush=True)
        return
    card = scorecard(rows)
    print(card, flush=True)
    if args.dry_run:
        return

    prompt = (
        "You maintain your own due-diligence method. Below is YOUR scorecard — "
        "your past verdicts joined with the coins' REAL returns.\n"
        f"1. Read {SKILL}\n"
        "2. Identify at most TWO systematic mistakes evidenced by the scorecard "
        "(not one-off noise).\n"
        "3. Edit the SKILL.md checklist/red-lines with the SMALLEST change that "
        "would have prevented them. Keep the 'Output contract' section BYTE-"
        "IDENTICAL — a daemon parses it. Do not touch other files.\n"
        "4. End your reply with exactly CHANGED or NO-CHANGE plus one line why.\n\n"
        + card
    )
    try:
        r = subprocess.run([HERMES, "chat", "-q", prompt, "--toolsets", "terminal"],
                           capture_output=True, text=True, timeout=args.timeout, cwd=REPO)
        tail = (r.stdout or "")[-300:]
    except Exception as e:  # noqa: BLE001
        print(f"hermes failed: {e}", flush=True)
        return

    diff = subprocess.run(["git", "diff", "--", SKILL], capture_output=True,
                          text=True, cwd=REPO).stdout
    if diff.strip():
        head = "\n".join(diff.splitlines()[:40])
        telegram.send("🧠 <b>memecoin-dd skill self-updated</b> (review with git diff; "
                      "git checkout to undo)\n<pre>" + html.escape(head) + "</pre>")
        print(f"[{time.strftime('%H:%M:%S')}] skill CHANGED — diff sent to Telegram", flush=True)
    else:
        print(f"[{time.strftime('%H:%M:%S')}] no change. model said: {tail.strip()[-120:]}", flush=True)


if __name__ == "__main__":
    main()
