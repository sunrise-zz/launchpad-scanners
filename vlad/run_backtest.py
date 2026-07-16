"""Compare candidate early-scanner LOGICS to find the best one.

Two use-cases are evaluated separately:
  * momentum  - short window after launch, catch a coin while it's taking off
  * coldstart - t<=30s / pre-crowd signals (creator reputation, dev buy, socials)

Each logic is a fixed weighted sum of standardized features (unsupervised
standardization -> no label leakage), so full-sample ranking metrics are honest.
We report recall@k / precision@k for winners and graduated, plus Spearman vs ATH.
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from analyze import (  # noqa: E402
    load, build_coins, creator_history, features, spearman, precision_recall_at_k,
)

DATA = os.path.join(HERE, "data")
WINNER_ATH = 10000.0


def col(rows, k):
    return [r[k] for r in rows]


def standardize(rows, keys):
    z = {}
    stats = {}
    for k in keys:
        xs = col(rows, k)
        m = sum(xs) / len(xs)
        s = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
        stats[k] = (m, s)
        z[k] = [(x - m) / s for x in xs]
    return z, stats


def score(z, weights):
    n = len(next(iter(z.values())))
    return [sum(w * z[k][i] for k, w in weights.items()) for i in range(n)]


# candidate logics: name -> (mode, {feature: weight})
LOGICS = {
    "buy_eth_only":        ("momentum", {"buy_eth": 1}),
    "unique_buyers_only":  ("momentum", {"unique_buyers": 1}),
    "n_trades_only":       ("momentum", {"n_trades": 1}),
    "momentum_basic":      ("momentum", {"unique_buyers": 1, "buy_eth": 1, "buysell_ratio": 1, "top_share": -1}),
    "momentum_organic":    ("momentum", {"non_dev_buyers": 1.2, "organic_eth": 1.0, "buysell_ratio": 0.8,
                                          "top_share": -0.8, "dev_sold": -1.0}),
    "momentum_plus_rep":   ("momentum", {"unique_buyers": 1.0, "organic_eth": 1.0, "buysell_ratio": 0.7,
                                          "top_share": -0.7, "dev_sold": -1.0, "creator_prior_winners": 0.8}),
    "coldstart_rep":       ("coldstart", {"creator_prior_winners": 1.5, "dev_buy_eth": 1.0, "has_socials": 0.6,
                                           "has_image": 0.4, "creator_prior_launches": -0.5}),
    "coldstart_devbuy":    ("coldstart", {"dev_buy_eth": 1.0, "has_twitter": 0.6, "has_image": 0.4}),
    # deployable: momentum from organic (non-dev) buyers, penalise concentration & dev dumps
    "deploy_momentum":     ("momentum", {"non_dev_buyers": 1.0, "buy_eth": 1.0, "buysell_ratio": 0.7,
                                          "top_share": -0.7, "dev_sold": -1.0}),
}

# The logic we actually ship (chosen for recall + lead-time balance, not just peak recall).
DEPLOY_LOGIC = "deploy_momentum"
DEPLOY_WINDOW = 120
# fast binary alert thresholds (from lead_time.py sweep): balance recall vs precision
TRIGGER = {"window": 60, "min_nondev_buyers": 5, "escalate_nondev_buyers": 8, "min_ratio": 1.5}
# hard drop filters (rug / wash patterns)
FILTERS = {"drop_if_dev_sold": True, "max_top_share": 0.90}

MOMENTUM_WINDOWS = [60, 120, 300]
COLDSTART_WINDOWS = [15, 30, 60]


def eval_logic(coins, window, weights):
    rows = [features(c, window) for c in coins]
    y = [math.log1p(c["ath"]) for c in coins]
    win = [1 if (c["ath"] > WINNER_ATH or c["graduated"]) else 0 for c in coins]
    grad = [1 if c["graduated"] else 0 for c in coins]
    z, stats = standardize(rows, list(weights.keys()))
    sc = score(z, weights)
    out = {"spearman": spearman(sc, y)}
    for k in (10, 20, 30):
        p, r, h = precision_recall_at_k(sc, win, k)
        out[f"rec@{k}"] = r
        out[f"prec@{k}"] = p
    _, gr, gh = precision_recall_at_k(sc, grad, 20)
    out["grad_rec@20"] = gr
    out["stats"] = stats
    return out, sum(win), sum(grad)


def run():
    events, rest = load()
    coins = build_coins(events, rest)
    creator_history(coins)
    nwin = sum(1 for c in coins if c["ath"] > WINNER_ATH or c["graduated"])
    ngrad = sum(c["graduated"] for c in coins)
    print(f"coins={len(coins)}  winners={nwin}  graduated={ngrad}\n")

    results = []
    for name, (mode, weights) in LOGICS.items():
        windows = MOMENTUM_WINDOWS if mode == "momentum" else COLDSTART_WINDOWS
        for w in windows:
            res, _, _ = eval_logic(coins, w, weights)
            combined = res["rec@20"] + 0.5 * res["grad_rec@20"] + 0.3 * res["spearman"]
            results.append((combined, name, mode, w, weights, res))

    results.sort(key=lambda t: -t[0])
    print(f"{'logic':22s} {'mode':10s} {'win':>4s} {'r@10':>5s} {'r@20':>5s} {'r@30':>5s} {'p@20':>5s} {'grad':>5s} {'rho':>6s}")
    for combined, name, mode, w, weights, res in results:
        print(f"{name:22s} {mode:10s} {w:>4d} {res['rec@10']:>5.2f} {res['rec@20']:>5.2f} "
              f"{res['rec@30']:>5.2f} {res['prec@20']:>5.2f} {res['grad_rec@20']:>5.2f} {res['spearman']:>+6.2f}")

    best = results[0]
    _, name, mode, window, weights, res = best
    print(f"\nHIGHEST-RECALL: {name}  mode={mode}  window={window}s  -> rec@20={res['rec@20']:.2f} "
          f"grad_rec@20={res['grad_rec@20']:.2f} spearman={res['spearman']:+.2f}")

    # ship the DEPLOY logic (balances recall with lead time), not just peak-recall
    weights = LOGICS[DEPLOY_LOGIC][1]
    window = DEPLOY_WINDOW
    res, _, _ = eval_logic(coins, window, weights)
    print(f"DEPLOY: {DEPLOY_LOGIC} window={window}s -> rec@20={res['rec@20']:.2f} "
          f"p@20={res['prec@20']:.2f} grad_rec@20={res['grad_rec@20']:.2f} spearman={res['spearman']:+.2f}")
    deployed = {
        "logic": DEPLOY_LOGIC, "mode": "momentum", "window": window, "weights": weights,
        "standardize": {k: list(v) for k, v in res["stats"].items()},
        "trigger": TRIGGER, "filters": FILTERS, "winner_ath": WINNER_ATH,
        "note": "score = sum(w * (feature-mean)/std); features from trades within `window`s of Launched",
    }
    json.dump(deployed, open(os.path.join(DATA, "best_logic.json"), "w"), indent=2)
    print("wrote best_logic.json")

    # also show the top-scoring coins under the deploy logic (sanity)
    rows = [features(c, window) for c in coins]
    z, _ = standardize(rows, list(weights.keys()))
    sc = score(z, weights)
    order = sorted(range(len(coins)), key=lambda i: -sc[i])[:15]
    print("\ntop-15 coins by best logic:")
    for i in order:
        c = coins[i]
        flag = "GRAD" if c["graduated"] else ("WIN" if c["ath"] > WINNER_ATH else "")
        print(f"  {sc[i]:+6.2f}  {c['symbol'][:14]:14s} ath=${c['ath']:>10.0f} vol=${c['vol']:>9.0f} {flag}")


if __name__ == "__main__":
    run()
