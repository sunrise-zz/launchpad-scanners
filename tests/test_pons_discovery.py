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

import datetime as dt
import json
import os
import time

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

HEAD = 13732726          # the fixture's newest block
FIRST_BLOCK = 13730859   # the fixture's oldest block
BLOCK0_TS = 1784453066   # its block timestamp
RPC_LOG_SPAN_LIMIT = 10_000   # measured: 10k spans answer in ~1.1s, 50k is a 413


def stub_chain(module, monkeypatch, logs, cursor_file, head=HEAD,
               block_timestamps=True):
    """Serve `logs` over a fake JSON-RPC on `module` and record the calls.

    A function rather than a fixture so the cursor tests can stub a *second*,
    freshly-loaded module instance — that is what a restart looks like from the
    outside. `cursor_file` is always redirected into tmp_path: a test that wrote
    into pons/data/ would hand the live scanner a bogus cursor.
    """
    calls = []

    def fake_rpc(method, params, **kw):
        calls.append((method, params))
        if method == "eth_blockNumber":
            return hex(head)
        if method == "eth_getLogs":
            frm = int(params[0]["fromBlock"], 16)
            to = int(params[0]["toBlock"], 16)
            if to - frm + 1 > RPC_LOG_SPAN_LIMIT:
                # what the live RPC actually does above ~10k blocks, measured
                # 2026-07-19 — not a timeout, a hard refusal
                raise RuntimeError("rpc eth_getLogs failed after 5: "
                                   "HTTP Error 413: Request Entity Too Large")
            return [L for L in logs if frm <= int(L["blockNumber"], 16) <= to]
        raise AssertionError(f"unexpected rpc {method}")

    # ABI-encoded dynamic string "TEST": offset, length, then the bytes
    # LEFT-aligned in their word (right-padded) — not right-aligned like ints.
    sym_ret = "0x" + "20".rjust(64, "0") + "4".rjust(64, "0") + "54455354".ljust(64, "0")

    def fake_rpc_batch(batch, **kw):
        # recorded as one entry, so a test can tell "batched" from "one by one"
        calls.append(("BATCH", batch))
        if batch and batch[0][0] == "eth_getBlockByNumber":
            if not block_timestamps:
                raise RuntimeError("rpc eth_getBlockByNumber failed after 5: timeout")
            return [{"timestamp": hex(BLOCK0_TS + (int(b[1][0], 16) - FIRST_BLOCK))}
                    for b in batch]
        return [sym_ret] * len(batch)

    monkeypatch.setattr(module, "rpc", fake_rpc)
    monkeypatch.setattr(module, "rpc_batch", fake_rpc_batch)
    monkeypatch.setattr(module, "CURSOR_FILE", str(cursor_file), raising=False)
    monkeypatch.setattr(module, "_cursor", None, raising=False)
    monkeypatch.setattr(module, "_BLOCK_TS", {}, raising=False)
    monkeypatch.setattr(module, "_SYM", {}, raising=False)
    return calls


def ranges(calls):
    """The (fromBlock, toBlock) of every eth_getLogs, decoded."""
    return [(int(p[0]["fromBlock"], 16), int(p[0]["toBlock"], 16))
            for m, p in calls if m == "eth_getLogs"]


def drain(module, head=HEAD, max_polls=500):
    """Poll until the cursor catches up to head, as the scanner's loop does.

    Since #4 a poll covers a bounded slice rather than everything up to head, so
    "what did discovery find" is the sum over a drain, not one call. Returns
    (records, polls). An empty poll does not mean caught up — a 5000-block slice
    with no launches in it is perfectly normal mid-drain.
    """
    out, polls = [], 0
    while module._cursor is None or module._cursor <= head:
        out.extend(module.latest())
        polls += 1
        assert polls < max_polls, "drain never converged — the cursor is stuck"
    return out, polls


@pytest.fixture
def cursor_file(tmp_path):
    return tmp_path / "discovery_cursor.json"


@pytest.fixture
def stub_rpc(pons_api, monkeypatch, logs, cursor_file):
    return stub_chain(pons_api, monkeypatch, logs, cursor_file)


def test_rpc_is_the_default_discovery_source(pons_api):
    assert pons_api.DISCOVERY_SOURCE == "rpc"


def test_latest_returns_decoded_launches_without_touching_http(pons_api, monkeypatch,
                                                               stub_rpc):
    """If any HTTP call leaked into the RPC path this raises: pons.family is
    NXDOMAIN, which is the whole reason for this ticket."""
    def boom(*a, **kw):
        raise AssertionError("HTTP must not be on the discovery path")

    monkeypatch.setattr(pons_api, "_latest_http", boom)
    records, _ = drain(pons_api)
    assert len(records) == 6
    assert records[0]["token"] == FIRST["token"]
    assert REQUIRED_KEYS <= set(records[0])


def test_cold_start_looks_back_a_bounded_window_not_all_history(pons_api, stub_rpc):
    pons_api.latest()
    frm, _ = ranges(stub_rpc)[0]
    assert frm == HEAD - pons_api.DISCOVERY_LOOKBACK_BLOCKS
    assert frm > 0, "a cold start from block 0 would replay the whole chain"


def test_cold_start_window_covers_the_whole_alert_eligible_span(pons_api, pons):
    """The two constants live in different files — api.py can't import alert_pro
    without a cycle — so this is the only thing holding them together.

    alert_pro scans a coin only while it is younger than ACTIVE_SECS. A lookback
    shorter than that window means a fresh install starts blind to launches that
    are still alert-eligible: live coins, inside their alert window, silently
    never scanned. Longer is harmless (they register but can't alert), shorter
    is a silent miss — hence >=, not ==.
    """
    covered = pons_api.DISCOVERY_LOOKBACK_BLOCKS * pons_api.BLOCK_SECS
    assert covered >= pons.ACTIVE_SECS, (
        f"cold start covers {covered:.0f}s but coins stay alert-eligible for "
        f"{pons.ACTIVE_SECS}s — the difference is a blind spot"
    )


def test_cursor_advances_so_a_launch_is_never_returned_twice(pons_api, stub_rpc):
    """Re-returned launches re-register and re-alert. register_launches() dedupes
    on `tok in coins`, but that is a second line of defence, not this one."""
    records, _ = drain(pons_api)
    tokens = [r["token"] for r in records]
    assert len(tokens) == len(set(tokens)) == 6
    assert pons_api.latest() == [], "caught up, yet still returning launches"


def test_symbols_are_resolved_and_cached_across_polls(pons_api, stub_rpc):
    """Six launches must cost one batched round trip, not six — the poll runs
    every ~2s against a chain doing ~148 launches/hour."""
    records, _ = drain(pons_api)
    assert all(r["symbol"] == "TEST" for r in records)
    assert not [m for m, _ in stub_rpc if m == "eth_call"], "issued one by one"
    batches = [b for m, b in stub_rpc if m == "BATCH"]
    assert len(batches) == 1 and len(batches[0]) == 6
    assert pons_api._SYM["0x" + FIRST["token"][2:]] == "TEST"


# --- cursor persistence, bounded ranges, outage drain (#4) ------------------

def test_cursor_survives_a_restart(load_pons_api, monkeypatch, logs, cursor_file):
    """The scanner restarts constantly — LaunchAgent KeepAlive, deploys, crashes.
    With the cursor in memory only, every restart silently re-based discovery at
    head minus the lookback, so launches in the gap were never seen and never
    alerted. Nothing in the log said so. Resume must be exact: no gap, and no
    replay of blocks already processed."""
    first = load_pons_api()
    stub_chain(first, monkeypatch, logs, cursor_file)
    records, _ = drain(first)
    assert len(records) == 6

    restarted = load_pons_api()
    calls = stub_chain(restarted, monkeypatch, logs, cursor_file, head=HEAD + 100)
    restarted.latest()

    assert ranges(calls) == [(HEAD + 1, HEAD + 100)], (
        "a restart that does not resume from the persisted cursor is a silent "
        "coverage gap (re-based at head) or an alert flood (replayed history)"
    )


def test_a_single_poll_never_asks_for_an_unbounded_block_range(
        pons_api, monkeypatch, logs, cursor_file):
    """Measured against the live RPC on 2026-07-19: eth_getLogs answers a
    10,000-block span in 1.1s but returns HTTP 413 above it. So an unbounded
    range after an outage doesn't merely run slow — it fails outright, on every
    poll, and discovery never recovers on its own. The cursor never advances,
    the range keeps growing, and it fails harder every tick."""
    cursor_file.write_text(json.dumps({"next_block": HEAD - 500_000}))
    calls = stub_chain(pons_api, monkeypatch, logs, cursor_file)

    pons_api.latest()

    (frm, to), = ranges(calls)
    assert to - frm + 1 <= pons_api.MAX_BLOCKS_PER_POLL, "one oversized log query"
    assert pons_api.MAX_BLOCKS_PER_POLL <= 10_000, "measured 413 ceiling"


def test_a_multi_hour_outage_drains_over_several_polls(
        pons_api, monkeypatch, logs, cursor_file):
    """Six hours down is 216,000 blocks behind. Discovery has to come back on
    its own, in bounded steps, and land exactly on head: contiguous coverage is
    the whole point — a skipped range is a silent miss, an overlapping one
    re-registers launches that already alerted."""
    gap = int(6 * 3600 / pons_api.BLOCK_SECS)
    cursor_file.write_text(json.dumps({"next_block": HEAD - gap}))
    calls = stub_chain(pons_api, monkeypatch, logs, cursor_file)

    records, polls = drain(pons_api)

    spans = ranges(calls)
    assert polls > 1, "a 6h gap answered in one poll is the oversized query again"
    assert spans[0][0] == HEAD - gap, "drain must resume exactly where it stopped"
    assert spans[-1][1] == HEAD, "drain must finish flush against head"
    assert all(nxt[0] == cur[1] + 1 for cur, nxt in zip(spans, spans[1:])), (
        "ranges must be contiguous: a hole is a silent miss, an overlap re-alerts"
    )
    assert len(records) == 6


def test_a_week_old_cursor_skips_ahead_instead_of_blocking_live_discovery(
        pons_api, monkeypatch, logs, cursor_file, capsys):
    """A laptop shut over a long weekend leaves the cursor days behind. Draining
    it costs ~40 minutes of polls during which the scanner is blind to launches
    happening *now* — and buys nothing, because every launch in that backlog is
    far outside the watch window and can no longer alert. Skip it, and say so in
    the log: a silently skipped range is the failure mode this ticket is about.

    The 6h case above proves the other half — real outages still drain in full.
    """
    stale = HEAD - int(7 * 86400 / pons_api.BLOCK_SECS)
    cursor_file.write_text(json.dumps({"next_block": stale}))
    calls = stub_chain(pons_api, monkeypatch, logs, cursor_file)

    pons_api.latest()

    frm, _ = ranges(calls)[0]
    assert frm == HEAD - pons_api.DISCOVERY_LOOKBACK_BLOCKS, (
        "a week-old cursor must re-base at the watch window, not drain 6M blocks"
    )
    assert "skip" in capsys.readouterr().out.lower(), (
        "skipping blocks without logging it is exactly the silent gap we're fixing"
    )


@pytest.mark.parametrize("contents", [
    "",                            # created but never written
    "{",                           # truncated by a crash mid-write
    "{}",                          # written by a future version, key renamed
    '{"next_block": null}',
    '{"next_block": "abc"}',       # hand-edited
])
def test_an_unreadable_cursor_file_falls_back_to_a_cold_start(
        pons_api, monkeypatch, logs, cursor_file, contents):
    """Discovery must degrade to a cold start, not raise. `latest()` is called
    inside register_launches()' blanket `except Exception`, which prints one
    line and carries on — so an exception here doesn't crash the scanner, it
    makes it silently deaf forever while looking perfectly healthy. That is the
    outage this whole ticket exists to prevent, reintroduced through the file
    that was supposed to prevent it."""
    cursor_file.write_text(contents)
    calls = stub_chain(pons_api, monkeypatch, logs, cursor_file)

    pons_api.latest()

    frm, _ = ranges(calls)[0]
    assert frm == HEAD - pons_api.DISCOVERY_LOOKBACK_BLOCKS


def test_a_launch_surfaced_by_a_drain_is_not_dated_as_if_it_were_new(
        pons_api, monkeypatch, logs, cursor_file):
    """Dating a launch needs the block's timestamp, and that call can fail. When
    it does, launchedAt comes back None and register_launches() substitutes
    time.time() — so an 11-hour-old launch surfaced by a drain looks seconds
    old, lands inside the watch window, and is alert-eligible. Every coin in the
    backlog fires at once: the alert flood, from the very mechanism added to
    prevent the coverage gap.

    The drain makes this likely rather than exotic — the polls that surface old
    launches are precisely the ones fetching timestamps for blocks far behind
    head. Age is recoverable with no extra call, from block height against head
    at a measured 0.1005s per block.
    """
    undated = [{k: v for k, v in lg.items() if k != "blockTimestamp"} for lg in logs]
    head = HEAD + 400_000        # ~11h of blocks past the fixture's launches
    cursor_file.write_text(json.dumps({"next_block": FIRST_BLOCK}))
    stub_chain(pons_api, monkeypatch, undated, cursor_file, head=head,
               block_timestamps=False)

    records, _ = drain(pons_api, head=head)

    assert len(records) == 6
    for r in records:
        assert r["launchedAt"] is not None, (
            "None sends register_launches() down its `or time.time()` fallback"
        )
        age = time.time() - dt.datetime.fromisoformat(
            r["launchedAt"].replace("Z", "+00:00")).timestamp()
        assert age > pons_api.WATCH_SECS, (
            f"launch dated {age:.0f}s old but it is ~11h behind head — inside "
            f"the {pons_api.WATCH_SECS}s watch window, so it can still alert"
        )


def test_a_launch_older_than_the_watch_window_is_registered_but_never_alerts(pons):
    """Draining an outage registers launches that are hours old. Registering
    them is wanted — deployer history for the serial-deployer penalty, and the
    `tok in coins` dedup that stops them alerting if seen again later. Scanning
    them is not: their moment has passed, and firing a whole backlog at once is
    the flood half of this ticket. The freshness filter is the thing standing
    between those two, so it gets a test rather than staying a closure."""
    now = time.time()

    def coin(age_secs):
        return pons.CoinState(
            token="0x" + "1" * 40, pool="0x" + "2" * 40, launch_block=1,
            deployer="0x" + "3" * 40, symbol="T", launched_at=now - age_secs,
        )

    assert coin(60).is_active(now), "a one-minute-old launch is live"
    assert not coin(pons.ACTIVE_SECS + 1).is_active(now), (
        "a launch past the watch window must not be scanned, let alone alerted"
    )

    held = coin(pons.ACTIVE_SECS + 1)
    held.pending_since = now
    assert held.is_active(now), (
        "a coin past the window with a hold outstanding must still resolve it — "
        "dropping it here strands the confirm/abandon decision forever"
    )

    # The other three exits, moved here verbatim out of update_swaps(). Cheap to
    # get wrong in a move and expensive to notice: the loop would just quietly
    # re-poll swaps for coins it has already finished with, every 2s, forever.
    dead = coin(60)
    dead.dead = True
    assert not dead.is_active(now), "a dead coin is still being polled"

    done = coin(60)
    done.confirmed = True
    assert not done.is_active(now), "a confirmed coin re-enters the scan loop"

    undated = coin(60)
    undated.launched_at = None
    assert not undated.is_active(now), "an undated coin has no age to filter on"


def test_an_exact_block_timestamp_is_never_replaced_by_the_estimate(pons_api, stub_rpc):
    """The height-based estimate is a fallback for when the timestamp lookup
    fails, not a substitute for it. launchedAt is what the outcome tracker
    measures returns from and what the #10 refit will fit on, so quietly
    swapping a measured timestamp for an approximation would fuzz that history
    — and invisibly, because both are perfectly plausible ISO strings.

    Caught by mutation testing: inverting the fallback's guard so it always
    estimated passed the entire suite before this test existed."""
    records, _ = drain(pons_api)
    exact = [r for r in records if r["blockNumber"] == FIRST_BLOCK]
    assert exact, "the fixture's first launch went missing"
    assert exact[0]["launchedAt"] == "2026-07-19T09:24:26Z", (
        "estimated over an exact blockTimestamp the log already carried"
    )


def test_a_cursor_ahead_of_head_is_not_trusted(
        pons_api, monkeypatch, logs, cursor_file, capsys):
    """A cursor past head means the file is wrong — hand-edited, copied from
    another machine, or written against a different chain — not that we are
    somehow ahead of it. The `head < _cursor` early return then fires on every
    poll, forever, returning no launches, raising nothing and logging nothing.

    Verified against the live chain before this test was written: three polls,
    zero launches, complete silence. That is discovery going silently deaf —
    the exact failure this ticket exists to prevent, reintroduced through the
    very file added to prevent it. A bad cursor must lose to head, not outrank
    it."""
    cursor_file.write_text(json.dumps({"next_block": HEAD + 10_000_000}))
    calls = stub_chain(pons_api, monkeypatch, logs, cursor_file)

    records, _ = drain(pons_api)

    assert ranges(calls), "not one eth_getLogs issued — discovery sat mute"
    assert len(records) == 6, "launches sitting at head were never discovered"
    assert "ahead of head" in capsys.readouterr().out, (
        "discarding a persisted cursor must be visible in the log"
    )


def test_a_record_from_a_drain_lands_registered_but_not_alert_eligible(
        pons_api, pons, monkeypatch, logs, cursor_file):
    """Where the two halves meet. latest() dates a drained launch honestly, and
    CoinState.is_active() refuses anything past the window — but nothing so far
    checked that a record coming out of a *real* drain, assembled the way
    register_launches() assembles one, actually lands non-active. That
    composition is the acceptance criterion; the halves passing separately do
    not give it, and the seam between them is where a flood would appear."""
    undated = [{k: v for k, v in lg.items() if k != "blockTimestamp"} for lg in logs]
    head = HEAD + 400_000        # ~11h of blocks past the fixture's launches
    cursor_file.write_text(json.dumps({"next_block": FIRST_BLOCK}))
    stub_chain(pons_api, monkeypatch, undated, cursor_file, head=head,
               block_timestamps=False)

    records, _ = drain(pons_api, head=head)

    now = time.time()
    coins = {}
    for L in records:               # exactly what register_launches() does
        launched_at = pons.parse_ts(L.get("launchedAt")) or now
        coins[L["token"]] = pons.CoinState(
            L["token"], L["pool"], L["blockNumber"], L["deployer"],
            L.get("symbol"), launched_at, pair_token=L.get("pairToken"))

    assert len(coins) == 6, "registered: deployer history and dedup both need them"
    assert not [c for c in coins.values() if c.is_active(now)], (
        "a drained backlog that is still alert-eligible fires all at once"
    )


def test_legacy_http_source_is_selectable(pons_api, monkeypatch, stub_rpc):
    """The domain may come back. The HTTP path stays reachable behind the
    switch — and must not be reachable without it."""
    sentinel = [{"token": "0xhttp", "pool": "0xp", "blockNumber": 1}]
    monkeypatch.setattr(pons_api, "DISCOVERY_SOURCE", "http")
    monkeypatch.setattr(pons_api, "_latest_http", lambda: sentinel)
    assert pons_api.latest() is sentinel
