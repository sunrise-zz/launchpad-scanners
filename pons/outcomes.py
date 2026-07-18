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
                 price0=None, mcap0=None, liq0=None, gmgn=None):
    """Append one alert row. Best-effort — never raises into the scanner loop.

    `gmgn`: pass a prefetched pons/gmgn.py snapshot to avoid a duplicate API
    call (alert_pro does); leave None to auto-fetch here (runs post-send, so
    the ≤8s timeout never delays the Telegram alert itself)."""
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
    try:
        os.makedirs(TRACK_DIR, exist_ok=True)
        with open(ALERTS, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:  # noqa: BLE001
        pass
    return row
