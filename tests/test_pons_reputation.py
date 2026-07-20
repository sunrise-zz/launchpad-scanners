"""On-chain graduation and reputation collector behavior."""
from __future__ import annotations

import plistlib
from pathlib import Path

import pytest


TOKEN = "0x37e3c0327b54e2c647ed453449a9970dbb8c1775"
POOL = "0x4bd2872ece3efa88da3ddee00e27d6fdb249a835"
WALLET = "0xa21b7c287d6a8619669769ed551c4704eeb01159"
CAPTURED_CROSSING = {
    "address": POOL,
    "topics": [
        "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67",
        "0x000000000000000000000000d9fc1771672f08f3abce96d033cc21d1e5a3ac7f",
        "0x000000000000000000000000a21b7c287d6a8619669769ed551c4704eeb01159",
    ],
    "data": (
        "0x000000000000000000000000000000000000000000000000039277efad2f8000"
        "fffffffffffffffffffffffffffffffffffffffffff5d01599966d00bdd2432a"
        "0000000000000000000000000000000000001a82b01d859fcabdea037fc5f84f"
        "0000000000000000000000000000000000000000000007cbf9d9985f0629c56e"
        "000000000000000000000000000000000000000000000000000000000002b14f"
    ),
    "blockNumber": "0xa5fa1b",
    "blockTimestamp": "0x6a5839e2",
    "logIndex": "0x9",
}
def swap(pool, block, wallet, weth_wei):
    """Synthetic Swap with WETH as token0 (the token address sorts after WETH)."""
    amount0 = weth_wei if weth_wei >= 0 else (1 << 256) + weth_wei
    return {
        "address": pool,
        "topics": [
            "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67",
            "0x" + "0" * 64,
            "0x" + "0" * 24 + wallet[2:],
        ],
        "data": "0x" + f"{amount0:064x}" + "0" * (64 * 4),
        "blockNumber": hex(block),
        "blockTimestamp": hex(1_700_000_000 + block),
        "logIndex": "0x0",
    }


def test_first_reserve_crossing_records_exact_onchain_graduation(reputation):
    launches = {
        POOL: {
            "token": TOKEN,
            "pool": POOL,
            "pairToken": reputation.WETH,
            "launchBlock": 10_851_955,
        }
    }
    balances = {POOL: 3_960_214_815_997_883_112}
    graduated = set()

    edges = reputation.apply_swaps(
        launches, balances, graduated, [CAPTURED_CROSSING])

    assert edges == [{
        "token": TOKEN,
        "graduatedAt": "2026-07-16T01:54:42Z",
        "observedBlockNumber": 10_877_467,
    }]

    # Falling below and crossing again never creates a second graduation.
    reputation.apply_swaps(
        launches, balances, graduated,
        [swap(POOL, 10_877_500, WALLET, -300_000_000_000_000_000)])
    assert reputation.apply_swaps(
        launches, balances, graduated,
        [swap(POOL, 10_877_600, WALLET, 400_000_000_000_000_000)]) == []


def test_balance_snapshot_does_not_double_count_same_block_swaps(reputation):
    launches = {
        POOL: {
            "token": TOKEN,
            "pool": POOL,
            "pairToken": reputation.WETH,
            "launchBlock": 100,
            "balanceBlock": 100,
        }
    }
    balances = {POOL: 4_100_000_000_000_000_000}
    graduated = set()

    assert reputation.apply_swaps(
        launches, balances, graduated,
        [
            swap(POOL, 100, WALLET, 200_000_000_000_000_000),
            swap(POOL, 101, WALLET, 50_000_000_000_000_000),
        ],
    ) == []
    assert balances[POOL] == 4_150_000_000_000_000_000

    assert len(reputation.apply_swaps(
        launches, balances, graduated,
        [swap(POOL, 102, WALLET, 100_000_000_000_000_000)],
    )) == 1


def test_reputation_weights_wallets_by_distinct_graduated_coins(reputation):
    token_a = "0x3000000000000000000000000000000000000001"
    token_b = "0x3000000000000000000000000000000000000002"
    pool_a = "0x4000000000000000000000000000000000000001"
    pool_b = "0x4000000000000000000000000000000000000002"
    deployer = "0x5000000000000000000000000000000000000001"
    repeat = "0x6000000000000000000000000000000000000001"
    once = "0x6000000000000000000000000000000000000002"
    seller = "0x6000000000000000000000000000000000000003"
    launches = {
        token_a: {
            "token": token_a, "pool": pool_a, "deployer": deployer,
            "pairToken": reputation.WETH, "launchBlock": 1_000,
        },
        token_b: {
            "token": token_b, "pool": pool_b, "deployer": deployer,
            "pairToken": reputation.WETH, "launchBlock": 2_000,
        },
    }
    swaps = {
        token_a: [
            swap(pool_a, 1_010, repeat, 10),
            swap(pool_a, 1_020, once, 10),
        ],
        token_b: [
            swap(pool_b, 2_010, repeat, 10),
            swap(pool_b, 2_020, seller, -10),
        ],
    }
    graduations = [{"token": token_a}, {"token": token_b}]

    wallets, deployers = reputation.build_reputation(
        launches, graduations, swaps)

    assert wallets == {
        "strong": {repeat: 2},
        "weak": {repeat: 2, once: 1},
    }
    assert deployers == {deployer: 2}


def test_backfill_chunk_discovers_launch_and_checkpoints_after_crossing(
        reputation, monkeypatch):
    token = "0x3000000000000000000000000000000000000001"
    pool = "0x4000000000000000000000000000000000000001"
    launch = {
        "token": token,
        "pool": pool,
        "deployer": "0x5000000000000000000000000000000000000001",
        "pairToken": reputation.WETH,
        "launchBlock": 100,
    }
    state = {
        "nextBlock": 100,
        "launches": {},
        "balances": {},
        "earlyBuyers": {},
    }
    monkeypatch.setattr(
        reputation, "_fetch_launches", lambda start, end: {token: launch})
    monkeypatch.setattr(
        reputation,
        "_fetch_swap_log_batches",
        lambda windows, pools: [[
            swap(pool, 100, WALLET, reputation.GRADUATION_WEI),
        ]],
    )

    edges = reputation._process_checkpoint(state, set(), 100, 199)

    assert edges[0]["token"] == token
    assert edges[0]["observedBlockNumber"] == 100
    assert state["nextBlock"] == 200
    assert state["launches"][token]["balanceBlock"] == 99
    assert pool not in state["balances"]


def test_collector_launchagent_runs_every_six_hours():
    path = (
        Path(__file__).resolve().parents[1]
        / "pons"
        / "com.sunrise.pons-reputation-collector.plist"
    )
    with path.open("rb") as f:
        config = plistlib.load(f)

    assert config["Label"] == "com.sunrise.pons-reputation-collector"
    assert config["StartInterval"] == 21_600
    assert config["RunAtLoad"] is True
    assert config["ProgramArguments"][-2:] == [
        "--heartbeat",
        "pons/data/reputation_heartbeat.json",
    ]


def test_missing_swap_batch_never_advances_the_backfill(reputation, monkeypatch):
    monkeypatch.setattr(reputation, "rpc_batch", lambda *args, **kwargs: [None])

    with pytest.raises(RuntimeError, match="swap log batch"):
        reputation._fetch_swap_log_batches(
            [(100, 199)],
            ["0x4000000000000000000000000000000000000001"],
        )


def test_missing_launch_batch_never_creates_a_coverage_gap(
        reputation, monkeypatch):
    monkeypatch.setattr(reputation, "rpc_batch", lambda *args, **kwargs: [None])

    with pytest.raises(RuntimeError, match="launch log batch"):
        reputation._fetch_launches(100, 199)


def test_missing_historical_balance_is_not_treated_as_zero(
        reputation, monkeypatch):
    token = "0x3000000000000000000000000000000000000001"
    launches = {
        token: {
            "token": token,
            "pool": "0x4000000000000000000000000000000000000001",
        },
    }
    monkeypatch.setattr(reputation, "rpc_batch", lambda *args, **kwargs: [None])

    with pytest.raises(RuntimeError, match="historical balance batch"):
        reputation._bootstrap_balances(launches, set(), 100)


def test_missing_early_buyer_logs_are_retried_later(reputation, monkeypatch):
    token = "0x3000000000000000000000000000000000000001"
    state = {
        "launches": {
            token: {
                "token": token,
                "pool": "0x4000000000000000000000000000000000000001",
                "launchBlock": 100,
            },
        },
        "earlyBuyers": {},
    }
    monkeypatch.setattr(reputation, "rpc_batch", lambda *args, **kwargs: [None])

    with pytest.raises(RuntimeError, match="early-buyer log batch"):
        reputation._refresh_early_buyers(state, [{"token": token}])
    assert state["earlyBuyers"] == {}
