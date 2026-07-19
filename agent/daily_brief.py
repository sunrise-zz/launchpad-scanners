"""Daily 08:00 Telegram brief — what the scanners + AI did in the last 24h.

Gathers hard numbers first (stdlib, no LLM): alert counts by platform/tier,
outcome medians on matured alerts, and the AI analyst's verdict scorecard.
Hermes then turns the data block into a short Thai brief (~12 lines); if the
model call fails the raw stats are sent instead, so the brief always arrives.

Runs via LaunchAgent com.sunrise.daily-brief (StartCalendarInterval 08:00,
local time). Test by hand:

    python3 agent/daily_brief.py --now            # send to Telegram now
    python3 agent/daily_brief.py --now --dry-run  # print only
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "pons"))
sys.path.insert(0, os.path.join(REPO, "tracker"))
import report as rpt  # noqa: E402  (tracker/report.py — load/ret_at/alert_id)
import telegram  # noqa: E402

VERDICTS = os.path.join(REPO, "tracker", "data", "agent_verdicts.jsonl")
HERMES = os.path.expanduser("~/.local/bin/hermes")
DAY = 86400


def pct(x):
    return f"{x*100:+.0f}%" if x is not None else "–"


def med_ret(pairs, horizon):
    rets = [r for r in (rpt.ret_at(a, s, horizon) for a, s in pairs) if r is not None]
    return (statistics.median(rets), len(rets)) if rets else (None, 0)


def gather():
    """One plain-text data block — the source of truth the brief is written from."""
    now = time.time()
    alerts = rpt.load(rpt.ALERTS)
    snaps_by_id = defaultdict(list)
    for s in rpt.load(rpt.SNAPS):
        snaps_by_id[s["id"]].append(s)

    L = ["=== DATA (last 24h unless noted) ==="]

    # 1) alert volume by platform/tier
    last24 = [a for a in alerts if now - a["t"] <= DAY]
    cnt = defaultdict(int)
    for a in last24:
        cnt[(a.get("platform", "?"), a.get("tier", "?"))] += 1
    L.append(f"alerts 24h: {len(last24)} total")
    for (p, t), n in sorted(cnt.items(), key=lambda x: -x[1]):
        L.append(f"  {n:>3}x {p} / {t}")

    # 2) outcomes on the 7d window (matured only), per platform
    week = [(a, snaps_by_id.get(rpt.alert_id(a), [])) for a in alerts
            if now - a["t"] <= 7 * DAY]
    byp = defaultdict(list)
    for a, s in week:
        byp[a.get("platform", "?")].append((a, s))
    L.append("returns 7d (median vs alert price):")
    for p, pairs in sorted(byp.items()):
        m1, n1 = med_ret(pairs, 60)
        m4, n4 = med_ret(pairs, 240)
        m8, n8 = med_ret(pairs, 480)
        L.append(f"  {p}: 1h {pct(m1)} (n{n1}) · 4h {pct(m4)} (n{n4}) · 8h {pct(m8)} (n{n8})")

    # 3) AI analyst scorecard
    vrows = []
    if os.path.exists(VERDICTS):
        for ln in open(VERDICTS):
            try:
                vrows.append(json.loads(ln))
            except Exception:  # noqa: BLE001
                pass
    v24 = [v for v in vrows if now - v["t"] <= DAY]
    okv = [v for v in v24 if v.get("ok")]
    dist = defaultdict(int)
    for v in okv:
        dist[v.get("verdict", "?")] += 1
    fails = len(v24) - len(okv)
    L.append(f"AI DD 24h: {len(okv)} verdicts ({dict(dist)}) · {fails} failed runs")

    # verdict-vs-outcome (all-time, matured >= 4h) — the lift experiment
    amap = {rpt.alert_id(a): a for a in alerts}
    byv = defaultdict(list)
    for v in vrows:
        a = amap.get(v.get("id"))
        if v.get("ok") and a and (now - a["t"]) >= 4 * 3600:
            byv[v["verdict"]].append((a, snaps_by_id.get(v["id"], [])))
    if byv:
        L.append("AI verdict vs outcome (matured, all-time):")
        for verd in ("BUY-WATCH", "NEUTRAL", "AVOID"):
            if verd in byv:
                m4, n4 = med_ret(byv[verd], 240)
                L.append(f"  {verd}: 4h {pct(m4)} (n{n4})")
    else:
        L.append("AI verdict vs outcome: not enough matured data yet")

    return "\n".join(L)


def hermes_brief(data, timeout=180):
    """Ask Hermes to write the Thai brief. None on any failure."""
    if not os.path.exists(HERMES):
        return None
    prompt = (
        "คุณคือผู้ช่วยสรุปผลระบบสแกนเหรียญ launchpad เขียน brief ภาษาไทยประจำเช้า "
        "จากข้อมูลดิบด้านล่าง (ไม่ต้องใช้ tool ใดๆ ห้ามเดาตัวเลขเพิ่มเอง):\n"
        "- ยาวไม่เกิน ~12 บรรทัด ใช้ HTML ของ Telegram ได้เฉพาะ <b></b>\n"
        "- โครง: ภาพรวมเมื่อวาน → แพลตฟอร์ม/tier ไหนเวิร์ก-ไม่เวิร์ก (อิงตัวเลข) → "
        "ผลงาน AI DD → ข้อเสนอปรับปรุง 1-2 ข้อ\n"
        "- ห้ามชวนซื้อขาย เป็นรายงานผลเท่านั้น\n"
        "- ตอบโดยครอบคำตอบใน <BRIEF> ... </BRIEF> เท่านั้น\n\n" + data
    )
    try:
        r = subprocess.run([HERMES, "chat", "-q", prompt], capture_output=True,
                           text=True, timeout=timeout, cwd=REPO)
        # hermes echoes the prompt back before the answer, and the prompt itself
        # contains the literal "<BRIEF> ... </BRIEF>" instruction — a first-match
        # search picks up that echo and yields "...". Take the LAST block with
        # real content instead.
        for block in reversed(re.findall(r"<BRIEF>(.*?)</BRIEF>", r.stdout or "", re.S)):
            # strip the TUI box-drawing gutter hermes prints transcripts with
            txt = "\n".join(ln.strip(" │╭╮╰╯─") for ln in block.splitlines()).strip()
            if len(txt) >= 40:      # anything shorter is an echo, not a brief
                return txt
    except Exception:  # noqa: BLE001
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true", help="(compat flag — always runs once)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # refresh tier_stats.json first — the 📜 record line in every alert reads it
    try:
        subprocess.run([sys.executable, os.path.join(REPO, "tracker", "analyze.py"),
                        "--write-stats"], capture_output=True, timeout=60)
    except Exception:  # noqa: BLE001
        pass
    data = gather()
    brief = hermes_brief(data)
    if brief:
        msg = "🌅 <b>Daily brief</b>\n" + brief
    else:   # model unavailable -> raw stats, still useful
        msg = "🌅 <b>Daily brief</b> (raw — AI unavailable)\n<pre>" + html.escape(data) + "</pre>"

    if args.dry_run:
        print(msg)
        return
    ok, info = telegram.send(msg)
    print(f"[{time.strftime('%H:%M:%S')}] brief {'sent' if ok else 'FAILED: ' + str(info)}", flush=True)


if __name__ == "__main__":
    main()
