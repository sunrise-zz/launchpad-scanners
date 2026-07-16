"""Does an early signal actually give lead time before the coin peaks?

Reconstructs each coin's cumulative net-ETH curve (a monotone proxy for price /
market cap on a bonding curve), finds when it peaked, and measures how much of
that peak had already happened by the end of each candidate window. A signal is
only actionable if, at trigger time, most of the move is still ahead.

Also evaluates a fast binary TRIGGER rule (early watch alert) and reports its
hit rate, time-to-trigger, and lead time before peak.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from analyze import load, build_coins, creator_history  # noqa: E402

WINNER_ATH = 10000.0


def net_curve(coin):
    """Return list of (t_since_launch, cumulative_net_eth)."""
    t0 = coin["launch_ts"]
    cum = 0.0
    pts = []
    for e in coin["trades"]:
        if e["ts"] is None:
            continue
        cum += e["eth"] if e["_name"] == "Bought" else -e["eth"]
        pts.append((e["ts"] - t0, cum))
    return pts


def net_at(pts, t):
    v = 0.0
    for dt, cum in pts:
        if dt <= t:
            v = cum
        else:
            break
    return v


def frac_realized(coin, window):
    pts = net_curve(coin)
    if not pts:
        return None, None, None
    peak = max(c for _, c in pts)
    if peak <= 0:
        return None, None, None
    peak_t = next(dt for dt, c in pts if c == peak)
    fr = net_at(pts, window) / peak
    return fr, peak_t, peak


def trigger(coin, window, min_nondev_buyers, min_ratio):
    """Fast watch alert: >=N distinct non-dev buyers within `window`s, healthy
    buy/sell ratio, dev not dumping. Returns (fired, time_to_fire)."""
    t0 = coin["launch_ts"]
    creator = coin["creator"]
    buyers = {}
    nb = ns = 0
    dev_sold = False
    for e in coin["trades"]:
        if e["ts"] is None:
            continue
        dt = e["ts"] - t0
        if dt > window:
            break
        if e["_name"] == "Bought":
            nb += 1
            if e["account"] != creator:
                buyers.setdefault(e["account"], dt)
        else:
            ns += 1
            if e["account"] == creator:
                dev_sold = True
        if (len(buyers) >= min_nondev_buyers and not dev_sold
                and nb / (ns + 1) >= min_ratio):
            # time when the Nth distinct non-dev buyer arrived
            tfire = sorted(buyers.values())[min_nondev_buyers - 1]
            return True, tfire
    return False, None


def main():
    events, rest = load()
    coins = build_coins(events, rest)
    creator_history(coins)
    winners = [c for c in coins if c["ath"] > WINNER_ATH or c["graduated"]]
    losers = [c for c in coins if c not in winners]
    print(f"coins={len(coins)} winners={len(winners)}\n")

    print("=== lead time: fraction of peak net-ETH already realized by window end (winners) ===")
    for w in [30, 60, 120, 300]:
        frs = [frac_realized(c, w)[0] for c in winners]
        frs = [f for f in frs if f is not None]
        frs.sort()
        med = frs[len(frs) // 2]
        early = sum(1 for f in frs if f < 0.5) / len(frs)
        print(f"  window {w:>3d}s: median frac realized={med:.2f}  share of winners still <50% done={early:.2f}")
    peaks = [frac_realized(c, 0)[1] for c in winners]
    peaks = sorted(p for p in peaks if p is not None)
    print(f"  winners' peak time after launch: median={peaks[len(peaks)//2]:.0f}s  "
          f"p25={peaks[len(peaks)//4]:.0f}s  p75={peaks[3*len(peaks)//4]:.0f}s")

    print("\n=== fast TRIGGER rule sweep (window, min non-dev buyers, min buy/sell ratio) ===")
    print(f"{'win':>4s} {'buyers':>6s} {'ratio':>5s} {'hits':>5s} {'FP':>5s} {'prec':>5s} {'recall':>6s} {'t_fire':>7s} {'lead':>6s}")
    best = None
    for w in [60, 120, 300]:
        for mb in [3, 5, 8, 12]:
            for mr in [1.0, 1.5, 2.0]:
                tp = fp = 0
                tfires = []
                leads = []
                for c in coins:
                    fired, tf = trigger(c, w, mb, mr)
                    is_win = c in winners
                    if fired:
                        if is_win:
                            tp += 1
                            tfires.append(tf)
                            fr, peak_t, _ = frac_realized(c, w)
                            if peak_t is not None:
                                leads.append(max(0.0, peak_t - tf))
                        else:
                            fp += 1
                prec = tp / (tp + fp) if (tp + fp) else 0.0
                rec = tp / len(winners)
                if tp + fp == 0:
                    continue
                mt = sorted(tfires)[len(tfires) // 2] if tfires else 0
                ml = sorted(leads)[len(leads) // 2] if leads else 0
                score = rec * prec  # balance
                row = (w, mb, mr, tp, fp, prec, rec, mt, ml, score)
                if best is None or score > best[-1]:
                    best = row
                if prec >= 0.4 and rec >= 0.5:
                    print(f"{w:>4d} {mb:>6d} {mr:>5.1f} {tp:>5d} {fp:>5d} {prec:>5.2f} {rec:>6.2f} {mt:>6.0f}s {ml:>5.0f}s")
    w, mb, mr, tp, fp, prec, rec, mt, ml, _ = best
    print(f"\nBEST TRIGGER: window={w}s  min_nondev_buyers={mb}  min_ratio={mr}")
    print(f"  hits={tp}/{len(winners)} (recall {rec:.2f})  precision={prec:.2f}  "
          f"median time-to-fire={mt:.0f}s  median lead before peak={ml:.0f}s")


if __name__ == "__main__":
    main()
