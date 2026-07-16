"""Live vlad.fun coin scanner — surfaces interesting new launches at the source.

Polls the pump contract's logs (Launched / Bought / Sold) block-by-block, keeps
rolling per-coin state, and ranks freshly launched coins by the early-momentum
logic learned in run_backtest.py. Fires a WATCH / STRONG alert the moment a coin
crosses the trigger thresholds.

This tool only DETECTS and RANKS. It never places a trade — buying/selling is
left entirely to you.

Usage:
    python3 analysis/vlad/scan.py                # live, poll every 4s
    python3 analysis/vlad/scan.py --once         # one poll then exit (smoke test)
    python3 analysis/vlad/scan.py --interval 3   # custom poll interval
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rpc import rpc, PUMP, decode_log, TOPIC_NAME  # noqa: E402

DATA = os.path.join(HERE, "data")
ACTIVE_SECS = 30 * 60          # a coin is "active" (scored) for 30 min after launch
LOOKBACK_BLOCKS_ON_START = 3000  # warm up state from recent history


def load_logic():
    p = os.path.join(DATA, "best_logic.json")
    if not os.path.exists(p):
        raise SystemExit("best_logic.json missing - run run_backtest.py first")
    return json.load(open(p))


class Coin:
    __slots__ = ("token", "creator", "launch_ts", "symbol", "name", "meta",
                 "buys", "sells", "alerted")

    def __init__(self, token, creator, launch_ts, symbol, name, meta):
        self.token = token
        self.creator = creator
        self.launch_ts = launch_ts
        self.symbol = symbol
        self.name = name
        self.meta = meta
        self.buys = []   # (ts, account, eth)
        self.sells = []  # (ts, account, eth)
        self.alerted = None  # None | "WATCH" | "STRONG"


def win_feats(coin, window, now):
    t0 = coin.launch_ts
    buys = [b for b in coin.buys if b[0] - t0 <= window]
    sells = [s for s in coin.sells if s[0] - t0 <= window]
    buy_eth = sum(b[2] for b in buys)
    non_dev = {b[1] for b in buys if b[1] != coin.creator}
    dev_sold = any(s[1] == coin.creator for s in sells)
    max_buy = max((b[2] for b in buys), default=0.0)
    top_share = (max_buy / buy_eth) if buy_eth > 0 else 1.0
    return {
        "non_dev_buyers": float(len(non_dev)),
        "buy_eth": buy_eth,
        "buysell_ratio": len(buys) / (len(sells) + 1),
        "top_share": top_share,
        "dev_sold": 1.0 if dev_sold else 0.0,
        "n_buys": len(buys),
        "n_sells": len(sells),
    }


def score(feats, logic):
    z = 0.0
    for k, w in logic["weights"].items():
        m, s = logic["standardize"][k]
        z += w * ((feats.get(k, 0.0) - m) / (s or 1.0))
    return z


def check_trigger(coin, logic, now):
    tg = logic["trigger"]
    f = win_feats(coin, tg["window"], now)
    if f["dev_sold"] and logic["filters"]["drop_if_dev_sold"]:
        return None
    if f["top_share"] > logic["filters"]["max_top_share"]:
        return None
    if f["buysell_ratio"] < tg["min_ratio"]:
        return None
    if f["non_dev_buyers"] >= tg["escalate_nondev_buyers"]:
        return "STRONG"
    if f["non_dev_buyers"] >= tg["min_nondev_buyers"]:
        return "WATCH"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=4.0)
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    logic = load_logic()
    window = logic["window"]
    print(f"loaded logic '{logic['logic']}' window={window}s  trigger={logic['trigger']}")

    coins = {}   # token -> Coin
    ts_cache = {}

    def block_ts(bn):
        if bn not in ts_cache:
            blk = rpc("eth_getBlockByNumber", [hex(bn), False])
            ts_cache[bn] = int(blk["timestamp"], 16) if blk else int(time.time())
        return ts_cache[bn]

    latest = int(rpc("eth_blockNumber", []), 16)
    cursor = max(0, latest - LOOKBACK_BLOCKS_ON_START)

    def ingest(frm, to):
        logs = rpc("eth_getLogs", [{"address": PUMP, "fromBlock": hex(frm), "toBlock": hex(to)}], timeout=45)
        for lg in logs:
            ev = decode_log(lg)
            n = TOPIC_NAME.get(ev["name"], ev["name"])
            tok = (ev.get("token") or "").lower()
            ts = block_ts(ev["block"])
            if n == "Launched":
                coins[tok] = Coin(tok, ev.get("creator", "").lower(), ts,
                                  ev.get("symbol"), ev.get("tname"), ev.get("meta"))
            elif n == "Bought" and tok in coins:
                coins[tok].buys.append((ts, ev["account"], ev["eth"]))
            elif n == "Sold" and tok in coins:
                coins[tok].sells.append((ts, ev["account"], ev["eth"]))
            elif n == "Graduated" and tok in coins:
                print(f"  🎓 GRADUATED  {coins[tok].symbol}  ({tok[:10]})")
        return len(logs)

    print(f"warming up from block {cursor}..{latest}")
    ingest(cursor, latest)
    cursor = latest + 1

    def render():
        now = int(time.time())
        active = [c for c in coins.values() if now - c.launch_ts <= ACTIVE_SECS]
        scored = []
        for c in active:
            f = win_feats(c, window, now)
            if f["dev_sold"] and logic["filters"]["drop_if_dev_sold"]:
                continue
            if f["top_share"] > logic["filters"]["max_top_share"]:
                continue
            scored.append((score(f, logic), c, f))
        scored.sort(key=lambda t: -t[0])
        print(f"\n[{time.strftime('%H:%M:%S')}] active={len(active)} scored={len(scored)}  (top {args.top})")
        print(f"  {'score':>6s} {'age':>5s} {'sym':12s} {'buyers':>6s} {'buyETH':>7s} {'b/s':>5s} {'trig':>6s}")
        for sc, c, f in scored[:args.top]:
            age = now - c.launch_ts
            trig = check_trigger(c, logic, now) or ""
            # fire alert once per escalation level
            if trig and c.alerted != trig and not (c.alerted == "STRONG" and trig == "WATCH"):
                c.alerted = trig
                print(f"  🔔 {trig}: {c.symbol} ({c.token[:10]}) "
                      f"{int(f['non_dev_buyers'])} non-dev buyers, {f['buy_eth']:.3f} ETH in {logic['trigger']['window']}s")
            print(f"  {sc:>6.2f} {age:>4d}s {(c.symbol or '?')[:12]:12s} "
                  f"{int(f['non_dev_buyers']):>6d} {f['buy_eth']:>7.3f} {f['buysell_ratio']:>5.1f} {trig:>6s}")

    render()
    if args.once:
        return
    while True:
        time.sleep(args.interval)
        try:
            latest = int(rpc("eth_blockNumber", []), 16)
            if latest >= cursor:
                ingest(cursor, latest)
                cursor = latest + 1
            render()
        except KeyboardInterrupt:
            print("\nstopped")
            break
        except Exception as e:  # noqa: BLE001
            print(f"  poll error: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()
