"""Backtest harness: which EARLY-window signal best predicts a vlad.fun winner.

Uses only data available within `window` seconds of a coin's Launched event to
build features, then measures how well each feature / composite score ranks the
coins that actually became winners (high ATH market cap / graduated).

No third-party deps (pure stdlib + hand-rolled stats) so it runs anywhere.
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rpc import TOPIC_NAME, GRADUATED  # noqa: E402

DATA = os.path.join(HERE, "data")


def name_of(e):
    return TOPIC_NAME.get(e["name"], e["name"])


# ---------------- load ----------------

def load():
    events = json.load(open(os.path.join(DATA, "events.json")))
    coins = json.load(open(os.path.join(DATA, "coins_rest.json")))
    for e in events:
        e["_name"] = name_of(e)
    rest = {c["address"].lower(): c for c in coins}
    return events, rest


def build_coins(events, rest):
    launches = {}
    trades = defaultdict(list)   # token -> list of trade events
    graduated = set()
    for e in events:
        tok = (e.get("token") or "").lower()
        n = e["_name"]
        if n == "Launched":
            launches[tok] = e
        elif n in ("Bought", "Sold"):
            trades[tok].append(e)
        elif n == "Graduated":
            graduated.add(tok)

    coins = []
    for tok, le in launches.items():
        r = rest.get(tok)
        if not r:
            continue
        tr = sorted(trades[tok], key=lambda e: (e["ts"] or 0, e["logIndex"]))
        st = r["stats"]
        meta = r.get("meta") or {}
        coins.append({
            "token": tok,
            "symbol": r.get("symbol"),
            "creator": le.get("creator", "").lower(),
            "launch_ts": le["ts"],
            "trades": tr,
            "ath": st.get("athUsd", 0.0),
            "vol": st.get("volUsd", 0.0),
            "holders": st.get("holders", 0),
            "graduated": tok in graduated,
            "has_image": 1.0 if meta.get("image") else 0.0,
            "has_twitter": 1.0 if (meta.get("x") or meta.get("twitter")) else 0.0,
            "has_website": 1.0 if meta.get("website") else 0.0,
            "has_telegram": 1.0 if meta.get("telegram") else 0.0,
            "desc_len": float(len(meta.get("description") or "")),
        })
    coins = [c for c in coins if c["launch_ts"] is not None]
    coins.sort(key=lambda c: c["launch_ts"])
    return coins


# ---------------- features ----------------

def creator_history(coins):
    """For each coin, prior launches & prior winners by the same creator (time-ordered)."""
    seen = defaultdict(lambda: [0, 0])  # creator -> [prior_launches, prior_winners]
    for c in coins:
        pl, pw = seen[c["creator"]]
        c["creator_prior_launches"] = pl
        c["creator_prior_winners"] = pw
        seen[c["creator"]][0] += 1
        if c["ath"] > 10000 or c["graduated"]:
            seen[c["creator"]][1] += 1


def features(coin, window):
    """Signals computed from trades within `window` seconds of launch."""
    t0 = coin["launch_ts"]
    creator = coin["creator"]
    tr = [e for e in coin["trades"] if e["ts"] is not None and (e["ts"] - t0) <= window]
    buys = [e for e in tr if e["_name"] == "Bought"]
    sells = [e for e in tr if e["_name"] == "Sold"]
    buy_eth = sum(e["eth"] for e in buys)
    sell_eth = sum(e["eth"] for e in sells)
    buyers = {e["account"] for e in buys}
    non_dev_buyers = {e["account"] for e in buys if e["account"] != creator}
    dev_sold = any(e["account"] == creator for e in sells)
    dev_buy_eth = sum(e["eth"] for e in buys if e["account"] == creator)
    max_buy = max((e["eth"] for e in buys), default=0.0)
    top_share = (max_buy / buy_eth) if buy_eth > 0 else 1.0
    first_buy_dt = (buys[0]["ts"] - t0) if buys else window + 1
    span = max((e["ts"] for e in tr), default=t0) - t0 if tr else 0
    tpm = len(tr) / (span / 60) if span > 0 else 0.0
    return {
        "n_trades": len(tr),
        "n_buys": len(buys),
        "n_sells": len(sells),
        "unique_buyers": len(buyers),
        "non_dev_buyers": len(non_dev_buyers),
        "buy_eth": buy_eth,
        "net_eth": buy_eth - sell_eth,
        "buysell_ratio": len(buys) / (len(sells) + 1),
        "dev_sold": 1.0 if dev_sold else 0.0,
        "dev_buy_eth": dev_buy_eth,
        "organic_eth": buy_eth - dev_buy_eth,   # non-dev buy volume
        "top_share": top_share,                  # concentration (lower = healthier)
        "first_buy_dt": first_buy_dt,            # lower = faster interest
        "tpm": tpm,
        "creator_prior_launches": coin["creator_prior_launches"],
        "creator_prior_winners": coin["creator_prior_winners"],
        "has_image": coin["has_image"],
        "has_twitter": coin["has_twitter"],
        "has_socials": max(coin["has_twitter"], coin["has_website"], coin["has_telegram"]),
        "desc_len": coin["desc_len"],
    }


# ---------------- stats ----------------

def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma = sum(ra) / n
    mb = sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((x - mb) ** 2 for x in rb))
    return num / (da * db) if da and db else 0.0


def precision_recall_at_k(scores, is_winner, k):
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    topk = order[:k]
    hits = sum(is_winner[i] for i in topk)
    total_win = sum(is_winner)
    prec = hits / k if k else 0.0
    rec = hits / total_win if total_win else 0.0
    return prec, rec, hits


def zscore(xs):
    m = sum(xs) / len(xs)
    v = sum((x - m) ** 2 for x in xs) / len(xs)
    s = math.sqrt(v) or 1.0
    return [(x - m) / s for x in xs]
