"""Shared visual language for scanner alerts (Telegram HTML).

Layout contract — identical across every scanner so the eye learns positions:

    🟢 87/100 🎯 CONFIRMED — SYM        <- the 1-second line (= push preview)
    ▰▰▰▰▰▰▰▰▱▱ น่าเข้า: สูงมาก
    🐸 pons.family · ⛓ ROBINHOOD
    ✚ pro signal · pro signal            <- why it fired (max ~2 lines)
    ⚠️ risk flag · risk flag             <- only when flags exist
    💰 stats line(s)
    <link>

The score is a TRANSPARENT HEURISTIC (v1, not a backtested probability):
signals with backtest support anchor the base, extras add/subtract. Treat it
as a triage aid, not truth — refit weights once alert-outcome history exists.
"""
from __future__ import annotations

import json
import os
import time

_STATS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "tracker", "data", "tier_stats.json")
_STATS = [0.0, {}]   # [loaded_at, data] — refreshed lazily every 10 min


def tier_record(tier):
    """One line of LIVE truth from the outcome tracker for this alert tier —
    e.g. '📜 record: P(2x) 67% · med peak +517% · n=12'. Auto-updates as
    tracker/analyze.py --write-stats refreshes tier_stats.json (daily brief
    does). Returns None when no stats exist yet. The point (redesign-v2):
    the reader always sees how this tier has ACTUALLY performed, so a
    negative tier can't hide behind a confident-looking score."""
    now = time.time()
    if now - _STATS[0] > 600:
        try:
            _STATS[1] = json.load(open(_STATS_PATH))
        except Exception:  # noqa: BLE001
            _STATS[1] = {}
        _STATS[0] = now
    d = _STATS[1].get(tier)
    if not d or (d.get("n") or 0) < 2:
        return None
    return (f"📜 record: P(2x) <b>{d['p2x']*100:.0f}%</b> · med peak "
            f"{d['med_peak']*100:+.0f}% · med {d['med']*100:+.0f}% @{d.get('h', 240)//60}h · n={d['n']}")


def clamp(x, lo=5, hi=99):
    return max(lo, min(hi, int(round(x))))


def band(score):
    if score >= 80:
        return "🟢"
    if score >= 60:
        return "🟡"
    if score >= 40:
        return "🟠"
    return "🔴"


def verdict(score):
    if score >= 80:
        return "น่าเข้า: สูงมาก"
    if score >= 60:
        return "น่าเข้า: สูง"
    if score >= 40:
        return "น่าเข้า: ปานกลาง"
    return "น่าเข้า: เสี่ยง"


def meter(score, width=10):
    filled = int(round(score / 100 * width))
    return "▰" * filled + "▱" * (width - filled)


def compose(score, tier_emoji, tier, sym, platform, chain, pros, cons, stats, link):
    """Assemble the alert. pros/cons/stats are lists of pre-built strings
    (empties are dropped); cons section disappears entirely when clean."""
    lines = [
        f"{band(score)} <b>{score}/100</b> {tier_emoji} <b>{tier}</b> — <b>{sym}</b>",
        f"{meter(score)} {verdict(score)}",
        f"{platform} · ⛓ <b>{chain}</b>",
    ]
    lines += [f"✚ {p}" for p in pros if p]
    lines += [f"⚠️ {c}" for c in cons if c]
    lines += [s for s in stats if s]
    rec = tier_record(tier)
    if rec:
        lines.append(rec)
    lines.append(link)
    return "\n".join(lines)
