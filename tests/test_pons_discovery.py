"""On-chain pons launch discovery: decoding TokenLaunched into launch records.

The fixture in tests/fixtures/pons_token_launched.json is six real logs pulled
from the factory on 2026-07-19 (blocks 13730859-13732726). Nothing here touches
the network: `decode_launch` is pure, and the `latest()` tests drive a stubbed
RPC so the poll/cursor logic is exercised offline.

These tests pin the *record shape* rather than the decode internals, because the
whole point of the seam is that alert_pro/scan/alert keep consuming `latest()`
unchanged whether the records came from the chain or the legacy HTTP API.
"""
from __future__ import annotations

import json
import os

import pytest

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# The first fixture log, decoded by hand from the raw hex (see the probe in the
# issue #3 notes). Every other expectation in this file derives from these.
FIRST = dict(
    token="0x372f0fda5feaa5e0ba635ae7b80c2694645e6f83",
    deployer="0xaa52222d4b22d343aaddba8019bbaa379c2127cc",
    pool="0x2a05a5a5274803bd1a69622570de246581195f1d",
    pairToken="0x0bd7d308f8e1639fab988df18a8011f41eacad73",   # WETH
    blockNumber=13730859,
    restrictionsEndBlock=25565840,
    initialBuyAmount=67782880000000000,                        # 0.06778 ETH
)

# The key set alert_pro.register_launches() reads off every record. Adding keys
# is fine; losing one of these silently breaks discovery.
REQUIRED_KEYS = {"token", "pool", "blockNumber", "deployer", "symbol", "launchedAt"}


@pytest.fixture
def logs():
    with open(os.path.join(FIXTURES, "pons_token_launched.json")) as f:
        return json.load(f)


# --- decode_launch: pure, offline ------------------------------------------

def test_decodes_every_field_of_a_real_launch(pons_api, logs):
    r = pons_api.decode_launch(logs[0])
    for key, expected in FIRST.items():
        assert r[key] == expected, f"{key}: got {r[key]!r}, want {expected!r}"


def test_record_carries_the_keys_the_scanner_reads(pons_api, logs):
    for lg in logs:
        assert REQUIRED_KEYS <= set(pons_api.decode_launch(lg)), (
            "a missing key here is a silent discovery outage in alert_pro"
        )


def test_addresses_are_lowercased(pons_api, logs):
    """CoinState keys coins by lowercased address and compares addresses as
    strings for pool ordering — a checksummed address would break both."""
    r = pons_api.decode_launch(logs[0])
    for key in ("token", "pool", "deployer", "pairToken"):
        assert r[key] == r[key].lower()


def test_launched_at_is_an_iso_string_parse_ts_can_read(pons_api, logs):
    """Regression guard: alert_pro/scan/alert all run launchedAt through
    parse_ts(), which calls .replace("Z", ...) — a float or int here raises
    AttributeError inside the poll's blanket except and discovery goes silently
    deaf. The HTTP API returned ISO strings; the RPC path must too."""
    import datetime as dt

    r = pons_api.decode_launch(logs[0])
    assert isinstance(r["launchedAt"], str)
    parsed = dt.datetime.fromisoformat(r["launchedAt"].replace("Z", "+00:00"))
    assert parsed.timestamp() == 1784453066


def test_timestamp_falls_back_when_the_log_omits_blockTimestamp(pons_api, logs):
    """Not every RPC provider returns blockTimestamp on eth_getLogs; the caller
    then supplies it from the block. Without the fallback launchedAt would be
    None and the coin would never become alert-eligible (the #4 bug class)."""
    stripped = {k: v for k, v in logs[0].items() if k != "blockTimestamp"}
    assert pons_api.decode_launch(stripped)["launchedAt"] is None
    r = pons_api.decode_launch(stripped, timestamp=1784453066)
    assert r["launchedAt"] == "2026-07-19T09:24:26Z"


def test_symbol_is_passed_through_not_invented(pons_api, logs):
    assert pons_api.decode_launch(logs[0])["symbol"] is None
    assert pons_api.decode_launch(logs[0], symbol="WIF")["symbol"] == "WIF"


def test_pool_is_not_confused_with_the_other_addresses_in_the_event(pons_api, logs):
    """The event carries five addresses. `pool` is data word 1 — picking the
    dexFactory (topic3) or pairToken (word 0) instead would poll swap logs on
    the wrong contract and every coin would look dead."""
    r = pons_api.decode_launch(logs[0])
    assert r["pool"] == FIRST["pool"]
    assert r["pool"] not in (r["token"], r["deployer"], r["pairToken"],
                             "0x1f7d7550b1b028f7571e69a784071f0205fd2efa")  # dexFactory


def test_extra_measurement_fields_are_ints_not_scaled(pons_api, logs):
    """initialBuyAmount stays raw wei: the refit (#10) fits on measurements, and
    rescaling later would silently reinterpret the accumulated history."""
    r = pons_api.decode_launch(logs[0])
    assert isinstance(r["initialBuyAmount"], int)
    assert isinstance(r["restrictionsEndBlock"], int)


def test_initial_buy_of_zero_is_preserved_not_dropped(pons_api, logs):
    """The last fixture launch has a zero dev buy — a real, meaningful
    measurement. `or None` style coercion would erase it."""
    r = pons_api.decode_launch(logs[-1])
    assert r["initialBuyAmount"] == 0


# --- pool token ordering ----------------------------------------------------

def test_pair_token_is_carried_so_the_pool_ordering_is_not_assumed(pons_api, logs):
    """CoinState orders token0/token1 by comparing against pairToken (Uniswap V3
    sorts by address). It can only do that if the record carries the event's
    pairToken rather than the scanner assuming WETH — a launch paired against
    anything else would otherwise decode every buy as a sell. The ordering
    itself is pinned in test_pons_features.py."""
    assert pons_api.decode_launch(logs[0])["pairToken"] == FIRST["pairToken"]


def test_a_non_weth_pair_token_decodes_as_itself(pons_api, logs):
    """Every launch sampled so far pairs against WETH; nothing may hardcode it."""
    lg = json.loads(json.dumps(logs[0]))
    odd = "0x" + "a1" * 20
    lg["data"] = "0x" + odd[2:].rjust(64, "0") + lg["data"][2:][64:]
    assert pons_api.decode_launch(lg)["pairToken"] == odd


# --- latest(): source switch + cursor, against a stubbed RPC ----------------

@pytest.fixture
def stub_rpc(pons_api, monkeypatch, logs):
    """Serve the fixture logs over a fake JSON-RPC and record the calls."""
    calls = []

    def fake_rpc(method, params, **kw):
        calls.append((method, params))
        if method == "eth_blockNumber":
            return hex(13732726)
        if method == "eth_getLogs":
            frm = int(params[0]["fromBlock"], 16)
            to = int(params[0]["toBlock"], 16)
            return [L for L in logs if frm <= int(L["blockNumber"], 16) <= to]
        raise AssertionError(f"unexpected rpc {method}")

    # ABI-encoded dynamic string "TEST": offset, length, then the bytes
    # LEFT-aligned in their word (right-padded) — not right-aligned like ints.
    sym_ret = "0x" + "20".rjust(64, "0") + "4".rjust(64, "0") + "54455354".ljust(64, "0")

    def fake_rpc_batch(batch, **kw):
        # recorded as one entry, so a test can tell "batched" from "one by one"
        calls.append(("BATCH", batch))
        return [sym_ret] * len(batch)

    monkeypatch.setattr(pons_api, "rpc", fake_rpc)
    monkeypatch.setattr(pons_api, "rpc_batch", fake_rpc_batch)
    monkeypatch.setattr(pons_api, "_cursor", None, raising=False)
    monkeypatch.setattr(pons_api, "_BLOCK_TS", {}, raising=False)
    monkeypatch.setattr(pons_api, "_SYM", {}, raising=False)
    return calls


def test_rpc_is_the_default_discovery_source(pons_api):
    assert pons_api.DISCOVERY_SOURCE == "rpc"


def test_latest_returns_decoded_launches_without_touching_http(pons_api, monkeypatch,
                                                               stub_rpc):
    """If any HTTP call leaked into the RPC path this raises: pons.family is
    NXDOMAIN, which is the whole reason for this ticket."""
    def boom(*a, **kw):
        raise AssertionError("HTTP must not be on the discovery path")

    monkeypatch.setattr(pons_api, "_latest_http", boom)
    records = pons_api.latest()
    assert len(records) == 6
    assert records[0]["token"] == FIRST["token"]
    assert REQUIRED_KEYS <= set(records[0])


def test_cold_start_looks_back_a_bounded_window_not_all_history(pons_api, stub_rpc):
    pons_api.latest()
    frm = int(stub_rpc[1][1][0]["fromBlock"], 16)
    assert frm == 13732726 - pons_api.DISCOVERY_LOOKBACK_BLOCKS
    assert frm > 0, "a cold start from block 0 would replay the whole chain"


def test_cursor_advances_so_a_second_poll_does_not_re_return_launches(pons_api, stub_rpc):
    assert len(pons_api.latest()) == 6
    assert pons_api.latest() == [], "re-returned launches re-register and re-alert"


def test_symbols_are_resolved_and_cached_across_polls(pons_api, stub_rpc):
    """Six launches must cost one batched round trip, not six — the poll runs
    every ~2s against a chain doing ~148 launches/hour."""
    records = pons_api.latest()
    assert all(r["symbol"] == "TEST" for r in records)
    assert not [m for m, _ in stub_rpc if m == "eth_call"], "issued one by one"
    batches = [b for m, b in stub_rpc if m == "BATCH"]
    assert len(batches) == 1 and len(batches[0]) == 6
    assert pons_api._SYM["0x" + FIRST["token"][2:]] == "TEST"


def test_legacy_http_source_is_selectable(pons_api, monkeypatch, stub_rpc):
    """The domain may come back. The HTTP path stays reachable behind the
    switch — and must not be reachable without it."""
    sentinel = [{"token": "0xhttp", "pool": "0xp", "blockNumber": 1}]
    monkeypatch.setattr(pons_api, "DISCOVERY_SOURCE", "http")
    monkeypatch.setattr(pons_api, "_latest_http", lambda: sentinel)
    assert pons_api.latest() is sentinel
