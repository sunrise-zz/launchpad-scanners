"""Shared alert-outcome recorder.

Every scanner calls record_alert() when it fires, appending one row to
tracker/data/alerts.jsonl. A separate daemon (tracker/track.py) then follows
each coin's price/mcap/liquidity over time so we can measure — after the fact —
whether the score actually predicted anything, and refit the weights.

The `track` dict tells the daemon HOW to fetch the coin's live metrics later:
    {"method": "dexscreener", "chainSlug": "robinhood"|"base"|"solana", "address": "0x…"}
    {"method": "arc", "address": "0x…"}
    {"method": "virtuals", "id": 12345}

When a GMGN API key is configured (see pons/gmgn.py), each row is also
enriched with row["gmgn"] — GMGN's alert-time forensics (smart-money tags,
bot/bundler rates, dev reputation, …). Collected, not gated: report.py will
tell us which fields predict returns before any earns score weight.
"""
from __future__ import annotations

import json
import os
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_DIR = os.path.join(REPO, "tracker", "data")
ALERTS = os.path.join(TRACK_DIR, "alerts.jsonl")


def record_alert(platform, chain, tier, symbol, token, score, track,
                 price0=None, mcap0=None, liq0=None, gmgn=None, tg=None):
    """Append one alert row. Best-effort — never raises into the scanner loop.

    `gmgn`: pass a prefetched pons/gmgn.py snapshot to avoid a duplicate API
    call (alert_pro does); leave None to auto-fetch here (runs post-send, so
    the ≤8s timeout never delays the Telegram alert itself).
    `tg`: {"msg_id", "text", "buttons"} of the sent Telegram message — lets
    agent/analyst.py append its AI verdict INTO that message (edit-in-place)
    instead of posting a separate follow-up that gets visually orphaned."""
    row = {
        "t": time.time(),
        "platform": platform,
        "chain": chain,
        "tier": tier,
        "symbol": symbol,
        "token": token,
        "score": score,
        "track": track,
        "price0": price0,
        "mcap0": mcap0,
        "liq0": liq0,
    }
    if gmgn is None:
        try:
            import gmgn as _gmgn   # sibling module; every scanner has pons/ on sys.path
            gchain, addr = _gmgn.chain_addr_for(chain, track, token)
            if gchain:
                gmgn = _gmgn.snapshot(gchain, addr)
        except Exception:  # noqa: BLE001
            gmgn = None
    if gmgn:
        row["gmgn"] = gmgn
    if tg and tg.get("msg_id"):
        row["tg"] = tg
    try:
        os.makedirs(TRACK_DIR, exist_ok=True)
        with open(ALERTS, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:  # noqa: BLE001
        pass
    return row


def recent_same_symbol(platform, symbol, token, hours=24.0):
    """Prior alerts on `platform` carrying the SAME symbol but a DIFFERENT
    token address within `hours`. Detects relaunch farms: 2026-07-18 one
    operator deployed "RUDY" three times ~11 min apart, each copy crossing the
    flap traction bar with near-identical manufactured transfers (~130
    recipients each). Address-based dedup can't see that — the name can."""
    if not symbol or not os.path.exists(ALERTS):
        return []
    sym = str(symbol).strip().lower()
    tok = (token or "").lower()
    cutoff = time.time() - hours * 3600
    out = []
    try:
        for ln in open(ALERTS):
            try:
                r = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if (r.get("t", 0) >= cutoff and r.get("platform") == platform
                    and str(r.get("symbol") or "").strip().lower() == sym
                    and (r.get("token") or "").lower() != tok):
                out.append(r)
    except Exception:  # noqa: BLE001
        return []
    return out
