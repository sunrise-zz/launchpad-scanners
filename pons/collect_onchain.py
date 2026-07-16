"""Collect early-window on-chain swaps for pons coins (case-control sample).

For every graduated coin plus a random sample of non-graduated ones, pulls the
Uniswap-V3 Swap logs on the coin's pool for the first WINDOW_BLOCKS after launch
and stores decoded trades. This is the dataset the multi-factor backtest runs on.

Robinhood Chain blocks are ~0.1s, so 6000 blocks ~= 10 minutes of trading.
Relative time uses block deltas (t_sec = (block - launch_block) * 0.1).

Output: analysis/pons/data/early_swaps.json
  {token: {"launchBlock": int, "pool": str, "deployer": str, "graduated": bool,
           "swaps": [[dblock, side(+1/-1), weth, recipient], ...]}}
"""
from __future__ import annotations

import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "vlad"))
from rpc import rpc, rpc_batch  # noqa: E402  (vlad's quiknode helper — same chain)

DATA = os.path.join(HERE, "data")
WETH = "0x0bd7d308f8e1639fab988df18a8011f41eacad73"
SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
WINDOW_BLOCKS = 6000          # ~10 min at 0.1s/block
N_CONTROL = 1500              # non-graduated sample size
BATCH = 8


def sint(h):
    v = int(h, 16)
    return v - (1 << 256) if v >= (1 << 255) else v


def decode_swaps(logs, token_is_0, launch_block):
    out = []
    for lg in logs:
        data = lg["data"][2:]
        a0 = sint(data[0:64])
        a1 = sint(data[64:128])
        weth_amt = (a1 if token_is_0 else a0) / 1e18
        side = 1 if weth_amt > 0 else -1        # weth flowing INTO pool = buy
        recip = "0x" + lg["topics"][2][-40:]
        out.append([int(lg["blockNumber"], 16) - launch_block, side, abs(weth_amt), recip])
    out.sort(key=lambda r: r[0])
    return out


def main():
    launches = json.load(open(os.path.join(DATA, "launches.json")))
    grads = json.load(open(os.path.join(DATA, "graduations.json")))
    gset = {g["token"].lower() for g in grads}

    pool_coins = [L for L in launches if L.get("pool") and L.get("blockNumber")]
    grad_coins = [L for L in pool_coins if L["token"].lower() in gset]
    non_grad = [L for L in pool_coins if L["token"].lower() not in gset]
    random.seed(42)
    control = random.sample(non_grad, min(N_CONTROL, len(non_grad)))
    targets = grad_coins + control
    print(f"targets: {len(grad_coins)} graduated + {len(control)} control = {len(targets)}")

    out_path = os.path.join(DATA, "early_swaps.json")
    out = json.load(open(out_path)) if os.path.exists(out_path) else {}
    todo = [L for L in targets if L["token"].lower() not in out]
    print(f"already have {len(out)}, fetching {len(todo)}")

    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        calls = [("eth_getLogs", [{
            "address": L["pool"],
            "topics": [SWAP_TOPIC],
            "fromBlock": hex(L["blockNumber"]),
            "toBlock": hex(L["blockNumber"] + WINDOW_BLOCKS),
        }]) for L in chunk]
        try:
            results = rpc_batch(calls, timeout=60)
        except Exception as e:  # noqa: BLE001
            print(f"  batch {i} failed ({e}); falling back to singles")
            results = []
            for L in chunk:
                try:
                    results.append(rpc("eth_getLogs", calls[len(results)][1], timeout=60))
                except Exception:  # noqa: BLE001
                    results.append(None)
        for L, logs in zip(chunk, results):
            tok = L["token"].lower()
            if logs is None:
                continue
            token_is_0 = tok < WETH
            out[tok] = {
                "launchBlock": L["blockNumber"],
                "pool": L["pool"],
                "deployer": (L.get("deployer") or "").lower(),
                "graduated": tok in gset,
                "launchedAt": L.get("launchedAt"),
                "initialBuyWei": L.get("initialBuyWei"),
                "has_desc": bool(L.get("description")),
                "symbol": L.get("symbol"),
                "swaps": decode_swaps(logs, token_is_0, L["blockNumber"]),
            }
        if (i // BATCH) % 10 == 0:
            json.dump(out, open(out_path, "w"))
            done = min(i + BATCH, len(todo))
            print(f"  {done}/{len(todo)}  (saved)", flush=True)
        time.sleep(0.05)

    json.dump(out, open(out_path, "w"))
    ns = sum(len(v["swaps"]) for v in out.values())
    print(f"done: {len(out)} coins, {ns} swaps -> early_swaps.json")


if __name__ == "__main__":
    main()
