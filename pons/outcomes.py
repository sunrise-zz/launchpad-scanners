"""Shared alert-outcome recorder.

Every scanner calls record_alert() when it fires, appending one row to
tracker/data/alerts.jsonl. A separate daemon (tracker/track.py) then follows
each coin's price/mcap/liquidity over time so we can measure — after the fact —
whether the score actually predicted anything, and refit the weights.

The `track` dict tells the daemon HOW to fetch the coin's live metrics later:
    {"method": "dexscreener", "chainSlug": "robinhood"|"base"|"solana", "address": "0x…"}
    {"method": "arc", "address": "0x…"}
    {"method": "virtuals", "id": 12345}
"""
from __future__ import annotations

import json
import os
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_DIR = os.path.join(REPO, "tracker", "data")
ALERTS = os.path.join(TRACK_DIR, "alerts.jsonl")


def record_alert(platform, chain, tier, symbol, token, score, track,
                 price0=None, mcap0=None, liq0=None):
    """Append one alert row. Best-effort — never raises into the scanner loop."""
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
    try:
        os.makedirs(TRACK_DIR, exist_ok=True)
        with open(ALERTS, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:  # noqa: BLE001
        pass
    return row
