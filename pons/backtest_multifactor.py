"""Multi-factor backtest: which combination of GMGN-style indicators best
predicts a pons coin graduating, with HIGH precision (winrate) as the goal.

Features per coin, computed from the first W minutes of on-chain swaps
(1 block = 0.1s on Robinhood Chain):

  crowd     n_buys, uniq_buyers, buy_weth, time_to_5_buyers
  quality   top_share (max buyer / total buy), rebuyers (conviction),
            bundle_max (max distinct buyers in one block = insider bundling),
            snipers (buys in first 2s)
  pressure  sells/buys ratio, distinct sellers, net_weth
  dev       dev_sold, dev_buy_weth, deployer prior launches / prior grads
  smart     n_smart (early buyers seen early in PREVIOUSLY graduated coins;
            leakage-free: smart set built only from coins graduated before
            this coin's launch)
  meta      initial_buy, has_desc

Evaluation: coins ordered by launch time, 60/40 time split. Because the control
set is a sample (1500 of ~17.4k non-grads), precision is corrected back to the
real-world base rate via sampling weight.
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

BLOCK_SEC = 0.1
CONTROL_WEIGHT = None  # set in load(): (total_non_grad / sampled_non_grad)


def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load():
    global CONTROL_WEIGHT
    swaps = json.load(open(os.path.join(DATA, "early_swaps.json")))
    launches = json.load(open(os.path.join(DATA, "launches.json")))
    n_non_grad_total = sum(1 for L in launches if L.get("pool"))
    grads = json.load(open(os.path.join(DATA, "graduations.json")))
    n_grad = len({g["token"].lower() for g in grads})
    n_non_grad_total -= n_grad
    sampled_non = sum(1 for v in swaps.values() if not v["graduated"])
    CONTROL_WEIGHT = n_non_grad_total / sampled_non
    print(f"loaded {len(swaps)} coins ({sum(v['graduated'] for v in swaps.values())} grad, "
          f"{sampled_non} control x weight {CONTROL_WEIGHT:.1f})")

    # deployer history from full launch list (time-ordered, leakage-free at use time)
    coins = []
    for tok, v in swaps.items():
        t = parse_ts(v["launchedAt"]) if v.get("launchedAt") else None
        if t is None:
            continue
        coins.append({"tok": tok, "t": t, **v})
    coins.sort(key=lambda c: c["t"])

    # deployer prior stats (over ALL launches, not just sample)
    all_by_time = sorted(
        [(parse_ts(L["launchedAt"]), L["deployer"].lower(), L["token"].lower())
         for L in launches if L.get("launchedAt")], key=lambda x: x[0])
    gset = {g["token"].lower() for g in grads}
    grad_at = {g["token"].lower(): parse_ts(g["graduatedAt"]) for g in grads}
    dep_launches = defaultdict(list)      # dep -> [launch_ts...]
    dep_grad_times = defaultdict(list)    # dep -> [graduation_ts...]
    for ts_, dep, tok in all_by_time:
        dep_launches[dep].append(ts_)
        if tok in grad_at:
            dep_grad_times[dep].append(grad_at[tok])
    for c in coins:
        dep = c["deployer"]
        c["dep_prior_launches"] = sum(1 for x in dep_launches.get(dep, []) if x < c["t"])
        c["dep_prior_grads"] = sum(1 for x in dep_grad_times.get(dep, []) if x < c["t"])
    return coins, grad_at


def build_smart_sets(coins, grad_at, early_sec=180, top_n=None):
    """For each coin (time-ordered), the set of 'smart wallets' = wallets that
    bought within early_sec of launch on a coin that GRADUATED BEFORE this
    coin's launch. Returns list aligned with coins."""
    smart_events = []  # (available_from_ts, wallet)
    for c in coins:
        if not c["graduated"]:
            continue
        gts = grad_at.get(c["tok"])
        if gts is None:
            continue
        for dblk, side, weth, recip in c["swaps"]:
            if side == 1 and dblk * BLOCK_SEC <= early_sec:
                smart_events.append((gts, recip))
    smart_events.sort(key=lambda x: x[0])
    out = []
    cur = set()
    i = 0
    for c in coins:
        while i < len(smart_events) and smart_events[i][0] < c["t"]:
            cur.add(smart_events[i][1])
            i += 1
        out.append(set(cur))
    return out


def features(c, W_sec, smart_set):
    dep = c["deployer"]
    buys, sells = [], []
    for dblk, side, weth, recip in c["swaps"]:
        t = dblk * BLOCK_SEC
        if t > W_sec:
            break
        (buys if side == 1 else sells).append((t, weth, recip))
    buy_weth = sum(w for _, w, _ in buys)
    sell_weth = sum(w for _, w, _ in sells)
    buyers = defaultdict(float)
    per_block = defaultdict(set)
    rebuy = defaultdict(int)
    for t, w, r in buys:
        buyers[r] += w
        per_block[round(t, 1)].add(r)
        rebuy[r] += 1
    uniq = len(buyers)
    non_dev_buyers = {r for r in buyers if r != dep}
    top_share = (max(buyers.values()) / buy_weth) if buy_weth > 0 else 1.0
    snipers = sum(1 for t, w, r in buys if t <= 2.0)
    bundle_max = max((len(v) for v in per_block.values()), default=0)
    # time to 5 distinct buyers
    seen = set()
    t5 = W_sec + 1
    for t, w, r in buys:
        seen.add(r)
        if len(seen) >= 5:
            t5 = t
            break
    smart_hits = sum(1 for r in buyers if r in smart_set)
    return {
        "n_buys": len(buys),
        "uniq_buyers": uniq,
        "non_dev_buyers": len(non_dev_buyers),
        "buy_weth": buy_weth,
        "net_weth": buy_weth - sell_weth,
        "sell_ratio": len(sells) / (len(buys) + 1),
        "n_sellers": len({r for _, _, r in sells}),
        "top_share": top_share,
        "rebuyers": sum(1 for k, v in rebuy.items() if v >= 2),
        "snipers": snipers,
        "bundle_max": bundle_max,
        "t5": t5,
        "dev_sold": 1.0 if any(r == dep for _, _, r in sells) else 0.0,
        "dev_prior_launches": c["dep_prior_launches"],
        "dev_prior_grads": c["dep_prior_grads"],
        "smart": smart_hits,
        "initial_buy": int(c.get("initialBuyWei") or 0) / 1e18,
        "has_desc": 1.0 if c.get("has_desc") else 0.0,
    }


def adj_precision(tp, fp):
    """Correct case-control precision back to the real population."""
    return tp / (tp + fp * CONTROL_WEIGHT) if (tp + fp) else 0.0


def evaluate_rule(rows, rule):
    tp = fp = fn = 0
    for r in rows:
        fire = all(cmp(r["f"][k]) for k, cmp in rule)
        if fire and r["grad"]:
            tp += 1
        elif fire:
            fp += 1
        elif r["grad"]:
            fn += 1
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    return tp, fp, rec, adj_precision(tp, fp)


def main():
    coins, grad_at = load()
    smart_sets = build_smart_sets(coins, grad_at)

    for W in (120, 300, 600):
        rows = []
        for c, ss in zip(coins, smart_sets):
            rows.append({"grad": c["graduated"], "t": c["t"], "f": features(c, W, ss)})
        n_grad = sum(r["grad"] for r in rows)

        print(f"\n================ window {W}s ================")
        # single-factor discrimination: median grad vs non-grad
        print(f"{'feature':>18s} {'grad_med':>9s} {'non_med':>9s}")
        keys = list(rows[0]["f"].keys())
        for k in keys:
            gv = sorted(r["f"][k] for r in rows if r["grad"])
            nv = sorted(r["f"][k] for r in rows if not r["grad"])
            print(f"{k:>18s} {gv[len(gv)//2]:>9.2f} {nv[len(nv)//2]:>9.2f}")

        # candidate thresholds per factor (direction from medians)
        cands = {
            "uniq_buyers": [("ge", v) for v in (8, 12, 18, 25)],
            "buy_weth": [("ge", v) for v in (0.5, 1.0, 2.0)],
            "top_share": [("le", v) for v in (0.5, 0.35, 0.25)],
            "rebuyers": [("ge", v) for v in (2, 4, 6)],
            "smart": [("ge", v) for v in (1, 2, 3)],
            "dev_sold": [("eq0", 0)],
            "t5": [("le", v) for v in (60, 120, 300)],
            "net_weth": [("ge", v) for v in (0.3, 1.0)],
            "sell_ratio": [("le", v) for v in (0.6, 0.4)],
            "bundle_max": [("le", v) for v in (4, 8)],
            "snipers": [("le", v) for v in (3, 6)],
        }

        def mk(kind, v):
            if kind == "ge":
                return lambda x: x >= v
            if kind == "le":
                return lambda x: x <= v
            return lambda x: x == 0

        # search AND-rules of size 2..4 over a curated factor pool
        results = []
        factor_opts = [(k, kind, v) for k, cs in cands.items() for kind, v in cs]
        # limit: pick per-factor best-2 options to keep search tractable
        for size in (2, 3, 4):
            for combo in itertools.combinations(cands.keys(), size):
                opt_lists = [[(k, kind, v) for kind, v in cands[k]] for k in combo]
                for opts in itertools.product(*opt_lists):
                    rule = [(k, mk(kind, v)) for k, kind, v in opts]
                    tp, fp, rec, prec = evaluate_rule(rows, rule)
                    if tp >= max(10, 0.25 * n_grad) and prec > 0:
                        desc = " & ".join(f"{k}{'>=' if kind=='ge' else ('<=' if kind=='le' else '==0')}{v}"
                                          for k, kind, v in opts)
                        results.append((prec, rec, tp, fp, desc))
        results.sort(key=lambda x: (-x[0], -x[1]))
        print(f"\ntop rules by REAL precision (winrate), window {W}s  [grad={n_grad}]")
        print(f"{'prec':>6s} {'recall':>6s} {'tp':>4s} {'fp':>4s}  rule")
        seen_desc = set()
        shown = 0
        for prec, rec, tp, fp, desc in results:
            if shown >= 12:
                break
            root = desc.split(" & ")[0]
            if (root, round(prec, 2)) in seen_desc:
                continue
            seen_desc.add((root, round(prec, 2)))
            print(f"{prec:>6.1%} {rec:>6.1%} {tp:>4d} {fp:>4d}  {desc}")
            shown += 1

    json_path = os.path.join(DATA, "factor_rows.json")
    print(f"\n(feature rows cached per window not saved; rerun as needed)")


if __name__ == "__main__":
    main()
