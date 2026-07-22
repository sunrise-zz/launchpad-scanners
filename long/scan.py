"""long.xyz scanner — Robinhood Chain, "launch with stock tokens" (chainId 4663).

app.long.xyz is a bonding-curve launchpad on the same chain as pons/flap/vlad,
and as of 2026-07-22 the busiest thing on GMGN's robinhood trenches board
(~2.4 new tokens/min observed, graduates reaching $200-400K mcap).

Two data paths were probed 2026-07-22:

  1. Its own API (api.long.xyz) is Cloudflare-hard-blocked — 403 to curl AND to
     plain urllib, unlike flap's batman.taxed.fun which only fingerprints curl.
     The web app is Next.js and its JS chunks were serving 503, so no endpoint
     shapes could be read off a live session either. Not usable from a
     stdlib-only scanner.
  2. GMGN trenches carries it natively under launchpad_platform key `longxyz`,
     pre-enriched with the same ~118 fields the bags scanner already consumes,
     and surfaces new_creation rows ~6s after mint. That is source-level
     freshness without reverse-engineering the platform, so this scanner is the
     bags trench implementation pointed at one pad.

Why its own instance instead of one more entry in bags/scan.py's PADS: GMGN
returns a fixed number of rows per trenches section, and long.xyz is big enough
to eat the board. Measured with both lists side by side, adding it to the bags
call took 46 of 50 `pump` rows and pushed bags 19 -> 1 and bankr 22 -> 2 —
adding this launchpad there would have *removed* coverage of four others. A
separate instance gets its own POST, its own 50 slots, and its own
data/heartbeat so the watchdog reports the two feeds independently.

Tiers, bar, scoring and seeding behaviour are bags/scan.py's — see that file
and bags/README.md. Alerts are labelled `🔭 long` and recorded to the tracker
under platform `longxyz`.

If GMGN ever drops the pad, the on-chain fallback is the vanity suffix: every
long.xyz token address observed ends in `1e18` (136/137 sampled), the same
CREATE2 trick flap uses with `7777`.

Detect + rank + alert only. It never trades.

Usage:
    python3 long/scan.py --dry-run          # print alerts, no Telegram
    python3 long/scan.py --once             # one pass (candidates + bars), exit
    python3 long/scan.py                    # live -> Telegram (pons/.env creds)
"""
from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pons"))   # trench's own deps

# Loaded by path under a unique name, not `import scan`: four scanners are named
# scan.py, so a plain import resolves by sys.path order and picks up whichever
# directory happens to be first — including this file, which then imports itself.
# Same reason tests/conftest.py loads the scanners by path.
_spec = importlib.util.spec_from_file_location(
    "trench_scan", os.path.join(HERE, "..", "bags", "scan.py"))
trench = importlib.util.module_from_spec(_spec)
sys.modules["trench_scan"] = trench
_spec.loader.exec_module(trench)

# Bar measured against a live board 2026-07-22 (50 `pump` rows): bags' 25/$1K/25%
# passed 12 of 50 here vs 7 at these numbers, and the extra five were thin rows
# (16-32 holders on $6-18K) that this launchpad produces continuously. Tighter
# is the same selectivity bags' bar buys on a quieter board, ~2 EARLY/h. Refit
# from data/events.jsonl once outcomes accumulate, like every other bar here.
trench.configure(name="long", emoji="🔭", self_pad="longxyz",
                 pads=["longxyz"], data=os.path.join(HERE, "data"),
                 bar={"holders": 40, "vol": 10_000.0, "progress": 0.30})

if __name__ == "__main__":
    trench.main()
