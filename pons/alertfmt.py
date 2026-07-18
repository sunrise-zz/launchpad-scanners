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
    lines.append(link)
    return "\n".join(lines)
