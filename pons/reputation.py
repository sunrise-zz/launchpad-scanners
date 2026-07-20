"""Pons graduation and reputation refresh from Robinhood Chain only.

The collector treats graduation as the first Uniswap V3 Swap that moves the
Pons pool's WETH reserve across 4.2 WETH. There is no separate graduation event
in that transaction, and a later sell can move the reserve below the threshold,
so the first crossing is persisted as an edge.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(HERE, "..", "vlad"))
import api  # noqa: E402
import health  # noqa: E402
from rpc import rpc, rpc_batch  # noqa: E402

WETH = "0x0bd7d308f8e1639fab988df18a8011f41eacad73"
SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
GRADUATION_WEI = 4_200_000_000_000_000_000
BLOCK_SECS = 0.1005
SMART_WINDOW_BLOCKS = math.ceil(180 / BLOCK_SECS)
TRANSFER_BALANCE_OF = "0x70a08231"

# The 94 API-labeled graduations resolve on Blockscout to these two contract
# creators: 89 on the current factory and 5 on its predecessor. Other contracts
# on Robinhood Chain emit the same generic TokenLaunched signature, so scanning
# topic0 without this evidence-backed allowlist would contaminate reputation.
FACTORIES = (
    "0xa5aab3f0c6eeadf30ef1d3eb997108e976351feb",
    "0x0c37a24f5d23a486fa692d1500881d698b1f77a4",
)
START_BLOCK = 8_600_000
LOG_CHUNK_BLOCKS = 10_000
CHECKPOINT_BLOCKS = 100_000
RPC_BATCH = 8

DATA = os.path.join(HERE, "data")
STATE_NAME = "reputation_state.json"
GRADUATIONS_NAME = "graduations.json"
SMART_NAME = "smart_wallets.json"
DEPLOYERS_NAME = "deployer_grads.json"
HEARTBEAT_NAME = "reputation_heartbeat.json"


def _sint(word):
    value = int(word, 16)
    return value - (1 << 256) if value >= (1 << 255) else value


def _weth_delta(log, token):
    data = log["data"][2:]
    amount0 = _sint(data[:64])
    amount1 = _sint(data[64:128])
    return amount1 if token.lower() < WETH else amount0


def _iso(timestamp):
    return (
        dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def apply_swaps(launches_by_pool, balances, graduated, logs):
    """Apply ordered pool swaps and return newly crossed graduation edges."""
    edges = []
    ordered = sorted(
        logs,
        key=lambda row: (
            int(row["blockNumber"], 16),
            int(row.get("logIndex") or "0x0", 16),
        ),
    )
    for log in ordered:
        pool = log["address"].lower()
        launch = launches_by_pool.get(pool)
        if not launch:
            continue
        block = int(log["blockNumber"], 16)
        if block <= int(launch.get("balanceBlock", -1)):
            continue
        token = launch["token"].lower()
        if token in graduated:
            continue
        before = balances.get(pool, 0)
        after = before + _weth_delta(log, token)
        balances[pool] = after
        if not (before < GRADUATION_WEI <= after):
            continue
        timestamp = log.get("blockTimestamp")
        if timestamp is None:
            raise ValueError(f"graduation block {block} has no timestamp")
        graduated.add(token)
        edges.append({
            "token": token,
            "graduatedAt": _iso(int(timestamp, 16)),
            "observedBlockNumber": block,
        })
    return edges


def build_reputation(launches_by_token, graduations, swaps_by_token):
    """Rebuild weighted early-buyer and per-deployer graduation counts."""
    wallet_graduations = Counter()
    deployer_graduations = Counter()
    for graduation in graduations:
        token = graduation["token"].lower()
        launch = launches_by_token.get(token)
        if not launch:
            continue
        deployer = (launch.get("deployer") or "").lower()
        if deployer:
            deployer_graduations[deployer] += 1
        launch_block = int(launch["launchBlock"])
        buyers = set()
        for log in swaps_by_token.get(token, ()):
            block = int(log["blockNumber"], 16)
            if block - launch_block > SMART_WINDOW_BLOCKS:
                continue
            if _weth_delta(log, token) <= 0:
                continue
            buyers.add("0x" + log["topics"][2][-40:].lower())
        wallet_graduations.update(buyers)
    weak = dict(wallet_graduations)
    strong = {wallet: count for wallet, count in weak.items() if count >= 2}
    return {"strong": strong, "weak": weak}, dict(deployer_graduations)


def build_reputation_from_buyers(launches_by_token, graduations, buyers_by_token):
    """Build the same tables from the collector's cached per-token buyer sets."""
    wallet_graduations = Counter()
    deployer_graduations = Counter()
    for graduation in graduations:
        token = graduation["token"].lower()
        launch = launches_by_token.get(token)
        if not launch:
            continue
        deployer = (launch.get("deployer") or "").lower()
        if deployer:
            deployer_graduations[deployer] += 1
        wallet_graduations.update(set(buyers_by_token.get(token, ())))
    weak = dict(wallet_graduations)
    strong = {wallet: count for wallet, count in weak.items() if count >= 2}
    return {"strong": strong, "weak": weak}, dict(deployer_graduations)


def _ranges(start, end):
    for first in range(start, end + 1, LOG_CHUNK_BLOCKS):
        yield first, min(first + LOG_CHUNK_BLOCKS - 1, end)


def _read_json(path, default):
    try:
        with open(path) as f:
            value = json.load(f)
        return value
    except (OSError, ValueError, TypeError):
        return default


def _write_json(path, value):
    """Atomically persist collector state or a derived reputation artifact."""
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(value, f, separators=(",", ":"), sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _require_log_results(results, expected, label):
    """Reject missing/malformed sub-responses before a cursor can advance."""
    if (
        not isinstance(results, list)
        or len(results) != expected
        or any(not isinstance(logs, list) for logs in results)
    ):
        raise RuntimeError(f"{label} is missing or malformed")
    return results


def _decode_launch(log):
    if log.get("address", "").lower() not in FACTORIES:
        return None
    try:
        row = api.decode_launch(log)
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    token = row.get("token", "").lower()
    pool = row.get("pool", "").lower()
    pair = row.get("pairToken", "").lower()
    if pair != WETH or len(token) != 42 or len(pool) != 42:
        return None
    return {
        "token": token,
        "pool": pool,
        "deployer": (row.get("deployer") or "").lower(),
        "pairToken": pair,
        "launchBlock": int(row["blockNumber"]),
        "launchedAt": row.get("launchedAt"),
    }


def _fetch_launches(start, end):
    """All official Pons TokenLaunched rows in a bounded block interval."""
    windows = list(_ranges(start, end))
    rows = {}
    for offset in range(0, len(windows), RPC_BATCH):
        batch = windows[offset:offset + RPC_BATCH]
        results = _require_log_results(rpc_batch([
            ("eth_getLogs", [{
                "address": list(FACTORIES),
                "topics": [api.TOKEN_LAUNCHED],
                "fromBlock": hex(first),
                "toBlock": hex(last),
            }])
            for first, last in batch
        ], timeout=60), len(batch), "launch log batch")
        for logs in results:
            for log in logs or ():
                row = _decode_launch(log)
                if row:
                    rows[row["token"]] = row
    return rows


def _balance_call(pool, block):
    data = TRANSFER_BALANCE_OF + "0" * 24 + pool[2:]
    return "eth_call", [{"to": WETH, "data": data}, hex(block)]


def _bootstrap_balances(launches, graduated, block):
    """Historical WETH balances at the last trusted API-labeled block."""
    active = [
        row for token, row in launches.items()
        if token not in graduated
    ]
    balances = {}
    for offset in range(0, len(active), 100):
        chunk = active[offset:offset + 100]
        results = rpc_batch(
            [_balance_call(row["pool"], block) for row in chunk],
            timeout=60,
        )
        if (
            not isinstance(results, list)
            or len(results) != len(chunk)
            or any(not isinstance(result, str) for result in results)
        ):
            raise RuntimeError("historical balance batch is missing or malformed")
        for row, result in zip(chunk, results):
            try:
                balances[row["pool"]] = int(result, 16)
            except ValueError as exc:
                raise RuntimeError(
                    "historical balance batch is missing or malformed"
                ) from exc
            row["balanceBlock"] = block
    return balances


def _bootstrap(graduations, baseline):
    print(f"bootstrap: launch map blocks {START_BLOCK}-{baseline}", flush=True)
    launches = _fetch_launches(START_BLOCK, baseline)
    graduated = {row["token"].lower() for row in graduations}
    print(f"bootstrap: {len(launches)} launches; reading active pool balances", flush=True)
    balances = _bootstrap_balances(launches, graduated, baseline)
    return {
        "nextBlock": baseline + 1,
        "launches": launches,
        "balances": balances,
        "earlyBuyers": {},
    }


def _fetch_swap_log_batches(windows, pools):
    """Fetch only Pons pool swaps, batching the provider's 10k-block windows."""
    results = []
    for offset in range(0, len(windows), RPC_BATCH):
        batch = windows[offset:offset + RPC_BATCH]
        batch_results = _require_log_results(rpc_batch([
            ("eth_getLogs", [{
                "address": pools,
                "topics": [SWAP_TOPIC],
                "fromBlock": hex(first),
                "toBlock": hex(last),
            }])
            for first, last in batch
        ], timeout=90), len(batch), "swap log batch")
        results.extend(batch_results)
    return results


def _process_checkpoint(state, graduated, start, end):
    new_launches = _fetch_launches(start, end)
    for token, row in new_launches.items():
        if token in state["launches"]:
            continue
        # A new pool has zero WETH before its launch transaction. Starting one
        # block earlier lets same-block initial buys count exactly once.
        row["balanceBlock"] = row["launchBlock"] - 1
        state["launches"][token] = row
        if token not in graduated:
            state["balances"][row["pool"]] = 0
    launches_by_pool = {
        row["pool"]: row for row in state["launches"].values()
        if row["pool"] in state["balances"]
    }
    windows = list(_ranges(start, end))
    edges = []
    for logs in _fetch_swap_log_batches(windows, list(launches_by_pool)):
        edges.extend(apply_swaps(
            launches_by_pool,
            state["balances"],
            graduated,
            logs or (),
        ))
    for edge in edges:
        pool = state["launches"][edge["token"]]["pool"]
        state["balances"].pop(pool, None)
    state["nextBlock"] = end + 1
    return edges


def _merge_graduations(existing, edges):
    by_token = {row["token"].lower(): row for row in existing}
    for row in edges:
        by_token.setdefault(row["token"].lower(), row)
    old_tokens = {row["token"].lower() for row in existing}
    added = sorted(
        (row for token, row in by_token.items() if token not in old_tokens),
        key=lambda row: row["observedBlockNumber"],
    )
    return list(existing) + added


def _early_buyers(launch, logs):
    token = launch["token"]
    buyers = set()
    for log in logs:
        block = int(log["blockNumber"], 16)
        if block - launch["launchBlock"] > SMART_WINDOW_BLOCKS:
            continue
        if _weth_delta(log, token) > 0:
            buyers.add("0x" + log["topics"][2][-40:].lower())
    return sorted(buyers)


def _refresh_early_buyers(state, graduations, checkpoint=None):
    missing = [
        row["token"].lower() for row in graduations
        if row["token"].lower() in state["launches"]
        and row["token"].lower() not in state["earlyBuyers"]
    ]
    for offset in range(0, len(missing), RPC_BATCH):
        tokens = missing[offset:offset + RPC_BATCH]
        launches = [state["launches"][token] for token in tokens]
        results = _require_log_results(rpc_batch([
            ("eth_getLogs", [{
                "address": launch["pool"],
                "topics": [SWAP_TOPIC],
                "fromBlock": hex(launch["launchBlock"]),
                "toBlock": hex(launch["launchBlock"] + SMART_WINDOW_BLOCKS),
            }])
            for launch in launches
        ], timeout=60), len(launches), "early-buyer log batch")
        for token, launch, logs in zip(tokens, launches, results):
            state["earlyBuyers"][token] = _early_buyers(launch, logs or ())
        completed = min(offset + len(tokens), len(missing))
        if completed == len(missing) or (offset // RPC_BATCH + 1) % 10 == 0:
            if checkpoint is not None:
                checkpoint()
            print(
                f"early buyers: {completed}/{len(missing)} refreshed",
                flush=True,
            )
    return len(missing)


def _paths(data_dir, heartbeat_path=None):
    return {
        "state": os.path.join(data_dir, STATE_NAME),
        "graduations": os.path.join(data_dir, GRADUATIONS_NAME),
        "smart": os.path.join(data_dir, SMART_NAME),
        "deployers": os.path.join(data_dir, DEPLOYERS_NAME),
        "heartbeat": heartbeat_path or os.path.join(data_dir, HEARTBEAT_NAME),
    }


def run(data_dir=DATA, heartbeat_path=None):
    paths = _paths(data_dir, heartbeat_path)
    graduations = _read_json(paths["graduations"], [])
    if not isinstance(graduations, list) or not graduations:
        raise RuntimeError("graduations.json baseline is missing or malformed")
    baseline = max(int(row["observedBlockNumber"]) for row in graduations)
    state = _read_json(paths["state"], None)
    if not isinstance(state, dict) or not isinstance(state.get("launches"), dict):
        state = _bootstrap(graduations, baseline)
        _write_json(paths["state"], state)

    head = int(rpc("eth_blockNumber", []), 16)
    start = int(state.get("nextBlock") or baseline + 1)
    new_count = 0
    while start <= head:
        checkpoint_end = min(start + CHECKPOINT_BLOCKS - 1, head)
        edges = _process_checkpoint(
            state,
            {row["token"].lower() for row in graduations},
            start,
            checkpoint_end,
        )
        graduations = _merge_graduations(graduations, edges)
        new_count += len(edges)
        # Derived edge first, cursor second: a crash can re-scan, but it cannot
        # advance past a graduation that was never persisted.
        _write_json(paths["graduations"], graduations)
        _write_json(paths["state"], state)
        print(
            f"scanned {start}-{checkpoint_end}: +{len(edges)} graduations "
            f"({len(graduations)} total)",
            flush=True,
        )
        start = checkpoint_end + 1

    refreshed = _refresh_early_buyers(
        state,
        graduations,
        checkpoint=lambda: _write_json(paths["state"], state),
    )
    wallets, deployers = build_reputation_from_buyers(
        state["launches"], graduations, state["earlyBuyers"])
    _write_json(paths["smart"], wallets)
    _write_json(paths["deployers"], deployers)
    _write_json(paths["state"], state)
    if not health.touch(
        paths["heartbeat"],
        "pons-reputation",
        min_interval=0,
        detail={
            "head": head,
            "graduations": len(graduations),
            "new": new_count,
            "smart": len(wallets["strong"]),
        },
    ):
        raise RuntimeError(f"could not write collector heartbeat: {paths['heartbeat']}")
    print(
        f"done: {len(graduations)} graduations; "
        f"{len(wallets['strong'])} strong wallets; {len(deployers)} deployers; "
        f"early buyers refreshed for {refreshed} coins",
        flush=True,
    )
    return {
        "graduations": len(graduations),
        "new": new_count,
        "strong": len(wallets["strong"]),
        "deployers": len(deployers),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=DATA)
    parser.add_argument("--heartbeat", default=None)
    args = parser.parse_args()
    run(args.data_dir, args.heartbeat)


if __name__ == "__main__":
    main()
