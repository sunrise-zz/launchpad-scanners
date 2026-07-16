"""Live pons.family scanner — surface coins climbing toward graduation early.

pons gives graduation progress directly, so the useful signal is *velocity*: how
fast a coin is accumulating paired ETH toward the 4.2 ETH graduation threshold.
A single snapshot has no velocity, so this scanner is STATEFUL — it polls the
`/recent-buys` feed, records each token's progress over time, and ranks by the
rate of climb plus proximity to graduation. It also watches `/latest` for brand
new launches and applies a light cold-start filter (has description, sane
initial buy) since launch-time metadata only gives ~2-3x lift on its own.

Detect + rank + alert only. It never trades.

Usage:
    python3 analysis/pons/scan.py                 # live, poll every 12s
    python3 analysis/pons/scan.py --once          # single poll (smoke test)
    python3 analysis/pons/scan.py --interval 20
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from collections import defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import api  # noqa: E402

DATA = os.path.join(HERE, "data")

# thresholds (from collect.py dynamics: p25 graduate in ~18min, median ~92min)
NEAR_GRAD_PCT = 70          # >= this progress and still climbing = about to pop
CLIMB_ETH_PER_MIN = 0.10    # paired-ETH accrual rate that flags real momentum
FRESH_SECS = 45 * 60        # only rank coins launched within this window
HIST = 12                   # snapshots kept per token for velocity


def parse_ts(s):
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load_reputation():
    p = os.path.join(DATA, "deployer_grads.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def load_launch_seed():
    """token -> launch metadata, from collect.py's snapshot (for symbol/age enrichment)."""
    p = os.path.join(DATA, "launches.json")
    if not os.path.exists(p):
        return {}
    seed = {}
    for L in json.load(open(p)):
        seed[L["token"].lower()] = {
            "symbol": L.get("symbol"), "launchedAt": L.get("launchedAt"),
            "deployer": (L.get("deployer") or "").lower(),
            "initialBuyWei": int(L.get("initialBuyWei") or 0),
            "has_desc": bool(L.get("description")),
        }
    return seed


class Tracker:
    def __init__(self, seed=None):
        self.hist = defaultdict(lambda: deque(maxlen=HIST))  # token -> [(t, paired_eth, pct)]
        self.meta = {}       # token -> {symbol, launchedAt, deployer, ...} (only active coins)
        self.seed = seed or {}  # token -> launch metadata snapshot (17k, lazy)
        self.alerted = {}    # token -> level

    def note_launch(self, L):
        tok = L["token"].lower()
        self.meta.setdefault(tok, dict(self.seed.get(tok, {})))
        self.meta[tok].update({
            "symbol": L.get("symbol"), "launchedAt": L.get("launchedAt"),
            "deployer": (L.get("deployer") or "").lower(),
            "initialBuyWei": int(L.get("initialBuyWei") or 0),
            "has_desc": bool(L.get("description")),
        })

    def note_buy(self, r, now):
        tok = r["token"].lower()
        paired = r.get("pairedPrincipalEth") or 0.0
        pct = r.get("graduationProgressPct") or 0.0
        self.hist[tok].append((now, paired, pct))
        m = self.meta.get(tok)
        if m is None:
            m = dict(self.seed.get(tok, {}))  # enrich from snapshot if known
            self.meta[tok] = m
        m.setdefault("symbol", r.get("token", "")[:8])
        m["graduated"] = r.get("graduated", False)
        m["pct"] = pct
        m["paired"] = paired
        m["price"] = r.get("priceUsd")
        m["latestBuyAt"] = r.get("latestBuyAt")

    def velocity(self, tok):
        """paired-ETH per minute over the tracked window."""
        h = self.hist[tok]
        if len(h) < 2:
            return 0.0
        (t0, p0, _), (t1, p1, _) = h[0], h[-1]
        dtmin = (t1 - t0) / 60
        return (p1 - p0) / dtmin if dtmin > 0 else 0.0


def score(tok, tr, rep):
    m = tr.meta.get(tok, {})
    pct = m.get("pct", 0.0)
    vel = tr.velocity(tok)
    rep_grads = rep.get(m.get("deployer", ""), 0)
    # progress toward graduation dominates; velocity and reputation add lift
    return pct * 0.6 + vel * 40 + min(rep_grads, 3) * 3 + (2 if m.get("has_desc") else 0)


def alert_level(tok, tr):
    m = tr.meta.get(tok, {})
    pct = m.get("pct", 0.0)
    vel = tr.velocity(tok)
    if m.get("graduated"):
        return None
    if pct >= NEAR_GRAD_PCT and vel > 0:
        return "NEAR-GRAD"
    if vel >= CLIMB_ETH_PER_MIN and pct >= 10:
        return "CLIMBING"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    # data changes ~1x/sec (block time); feed doesn't rate-limit even back-to-back,
    # so 1-2s is the useful floor. Lower than ~0.5s just returns duplicate snapshots.
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    rep = load_reputation()
    tr = Tracker(seed=load_launch_seed())
    print(f"pons scanner  threshold={api.GRAD_THRESHOLD_ETH}ETH  "
          f"near-grad>={NEAR_GRAD_PCT}%  climb>={CLIMB_ETH_PER_MIN}ETH/min  "
          f"reputation deployers={len(rep)}")

    def poll():
        now = time.time()
        try:
            for L in api.latest():
                tr.note_launch(L)
        except Exception as e:  # noqa: BLE001
            print(f"  latest error: {e}")
        try:
            for r in api.recent_buys():
                tr.note_buy(r, now)
        except Exception as e:  # noqa: BLE001
            print(f"  recent-buys error: {e}")

        rows = []
        for tok, m in tr.meta.items():
            if m.get("graduated"):
                continue
            lt = parse_ts(m.get("launchedAt"))
            age = (now - lt) if lt else None
            # rank fresh, in-progress coins
            if m.get("pct", 0) <= 0:
                continue
            if age is not None and age > FRESH_SECS and m.get("pct", 0) < NEAR_GRAD_PCT:
                continue
            rows.append((score(tok, tr, rep), tok, m, age))
        rows.sort(key=lambda t: -t[0])

        print(f"\n[{time.strftime('%H:%M:%S')}] tracking={len(tr.meta)} ranked={len(rows)}")
        print(f"  {'score':>6s} {'age':>5s} {'sym':12s} {'prog':>5s} {'paired':>7s} "
              f"{'vel/min':>7s} {'repG':>4s} {'alert':>9s}")
        for sc, tok, m, age in rows[:args.top]:
            vel = tr.velocity(tok)
            lvl = alert_level(tok, tr)
            if lvl and tr.alerted.get(tok) != lvl:
                tr.alerted[tok] = lvl
                print(f"  🔔 {lvl}: {m.get('symbol')} ({tok[:10]}) "
                      f"{m.get('pct')}% paired={m.get('paired'):.2f}ETH vel={vel:.3f}/min")
            agestr = f"{int(age//60)}m" if age is not None else "?"
            print(f"  {sc:>6.1f} {agestr:>5s} {(m.get('symbol') or '?')[:12]:12s} "
                  f"{m.get('pct',0):>4.0f}% {m.get('paired',0):>7.2f} {vel:>7.3f} "
                  f"{rep.get(m.get('deployer',''),0):>4d} {(lvl or ''):>9s}")

    poll()
    if args.once:
        return
    while True:
        time.sleep(args.interval)
        try:
            poll()
        except KeyboardInterrupt:
            print("\nstopped")
            break
        except Exception as e:  # noqa: BLE001
            print(f"  poll error: {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
