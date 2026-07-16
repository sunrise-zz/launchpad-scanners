"""Collect full on-chain history from the vlad.fun pump contract + REST outcomes.

Writes to analysis/vlad/data/:
  events.json      - all decoded Launched/Bought/Sold/Sync events (with ts)
  coins_rest.json  - snapshot of /v1/coins (outcome labels: status, athUsd, volUsd, ...)
  topics.json      - histogram of every topic0 seen (to catch unknown event types)
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rpc import rpc, rpc_batch, api_get, decode_log, PUMP, DEPLOY_BLOCK, TOPIC_NAME  # noqa: E402

DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

CHUNK = 2500


def get_logs_range(frm, to):
    return rpc("eth_getLogs", [{"address": PUMP, "fromBlock": hex(frm), "toBlock": hex(to)}], timeout=45)


def main():
    latest = int(rpc("eth_blockNumber", []), 16)
    print(f"latest block {latest}  deploy {DEPLOY_BLOCK}  span {latest - DEPLOY_BLOCK} blocks", flush=True)

    raw = []
    topic_hist = Counter()
    frm = DEPLOY_BLOCK
    while frm <= latest:
        to = min(frm + CHUNK - 1, latest)
        logs = get_logs_range(frm, to)
        for lg in logs:
            topic_hist[lg["topics"][0]] += 1
        raw.extend(logs)
        print(f"  {frm}-{to}: +{len(logs)}  (total {len(raw)})", flush=True)
        frm = to + 1
        time.sleep(0.05)

    print("topic0 histogram:", flush=True)
    for t, n in topic_hist.most_common():
        print(f"  {TOPIC_NAME.get(t, 'UNKNOWN')}  {t}  count={n}", flush=True)
    json.dump(dict(topic_hist), open(os.path.join(DATA, "topics.json"), "w"), indent=2)

    # decode
    events = [decode_log(lg) for lg in raw]

    # attach timestamps: batch fetch distinct block numbers
    blocks = sorted({e["block"] for e in events})
    print(f"fetching timestamps for {len(blocks)} distinct blocks...", flush=True)
    ts_map = {}
    B = 100
    for i in range(0, len(blocks), B):
        chunk = blocks[i:i + B]
        res = rpc_batch([("eth_getBlockByNumber", [hex(b), False]) for b in chunk], timeout=45)
        for b, blk in zip(chunk, res):
            ts_map[b] = int(blk["timestamp"], 16) if blk else None
        if i % 1000 == 0:
            print(f"  ts {i}/{len(blocks)}", flush=True)
        time.sleep(0.05)
    for e in events:
        e["ts"] = ts_map.get(e["block"])

    events.sort(key=lambda e: (e["block"], e["logIndex"]))
    json.dump(events, open(os.path.join(DATA, "events.json"), "w"))
    print(f"wrote {len(events)} events", flush=True)

    # REST outcomes
    coins = api_get("/v1/coins")
    json.dump(coins, open(os.path.join(DATA, "coins_rest.json"), "w"))
    print(f"wrote {len(coins)} REST coins", flush=True)

    # quick sanity
    launched = [e for e in events if e["name"] == "Launched"]
    print(f"Launched events (on-chain coin count): {len(launched)}", flush=True)


if __name__ == "__main__":
    main()
