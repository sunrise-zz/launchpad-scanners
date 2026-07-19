"""pons launch discovery + the remains of the pons.family HTTP API.

Launch discovery reads the factory's `TokenLaunched` event over RPC. It used to
come from pons.family's Next.js routes, but that domain went NXDOMAIN around
2026-07-18 while the platform itself kept launching (~148/hour measured
on-chain) — so the scanner was deaf to launches it could see all along.

`latest()` is the seam: same name, same signature, same record shape, sourced
from the chain. The legacy HTTP path stays behind DISCOVERY_SOURCE in case the
domain returns; it is never on the critical path by default.

The remaining EP_* helpers (recent_buys, market, …) still speak to pons.family
and still fail while it is down — they feed the NEAR-GRAD tier, which outcome
tracking turned off, and are left alone here.

Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
# append, never insert(0): pons/ and vlad/ both contain a scan.py, and putting
# vlad/ first makes `import scan` in pons/alert.py resolve to the wrong one.
sys.path.append(os.path.join(HERE, "..", "vlad"))
from rpc import addr_from_topic, rpc, rpc_batch  # noqa: E402  (quiknode Robinhood mainnet)

BASE = "https://pons.family"
# official Robinhood Chain endpoints (from the pons bundle) — for optional on-chain use
RPC = "https://rpc.mainnet.chain.robinhood.com"
FACTORY = "0xA5aAb3F0c6EeadF30Ef1D3Eb997108E976351feB"
WETH = "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73"
GRAD_THRESHOLD_ETH = 4.2  # paired principal needed to graduate

EP_LAUNCHES = "/api/pons-launches"                 # full list (large ~15MB)
EP_LATEST = "/api/pons-launches/latest"            # newest launches (small)
EP_RECENT_BUYS = "/api/pons-launches/recent-buys"  # 100 most-active tokens w/ progress
EP_GRADUATIONS = "/api/pons-launches/graduations"  # graduated tokens
EP_MARKET = "/api/noxa-market"                      # per-token market state (?token=)

# TokenLaunched(token indexed, deployer indexed, dexFactory indexed, pairToken,
#               pool, dexId, launchConfigId, positionId, restrictionsEndBlock,
#               initialBuyAmount)
# `TokenDeployed` fires in the same tx but omits the pool — don't use it.
TOKEN_LAUNCHED = "0xdb51ea9ad51ab453a65a4cb7e60c3cb378c9501bb002609f8f97778fb6c4235a"

# Block time, measured 2026-07-19 over a 10,000-block span: 0.1005s.
#
# Deliberately not the same constant as alert_pro.BLOCK_SEC (0.1), despite the
# near-identical name, because the two need different precision. That one
# converts a handful of blocks into seconds-since-launch for the 2s sniper
# window, where 0.5% is 10ms and irrelevant. This one maps block heights to
# wall-clock across spans up to MAX_BACKFILL_BLOCKS, where 0.5% is 36 minutes —
# the difference between "outside the watch window" and "alert-eligible".
# Merging them is not free either: at exactly 20 blocks the sniper test
# `t <= 2.0` passes at 0.1 and fails at 0.1005, so unifying would quietly move
# sniper counts. That is a scoring change, and belongs with the refit (#10).
BLOCK_SECS = 0.1005

# Cold start window: head minus the span alert_pro will still scan a coin over
# (its ACTIVE_SECS). Derived rather than written as a block count so the two
# can't drift apart — a lookback shorter than the watch window silently drops
# launches that are still alert-eligible, which is the gap this ticket closes.
# Must stay >= alert_pro.ACTIVE_SECS; a cycle stops api.py importing it, so the
# link is pinned by test_cold_start_window_covers_the_whole_alert_eligible_span.
WATCH_SECS = 15 * 60
# ceil, not int: truncating leaves a sliver of the watch window uncovered.
DISCOVERY_LOOKBACK_BLOCKS = math.ceil(WATCH_SECS / BLOCK_SECS)  # ~8956

# Per-poll ceiling. The RPC answers 10,000 blocks in ~1.1s and returns HTTP 413
# above it (measured 2026-07-19), so this is a hard limit, not a tuning knob: an
# unbounded range after an outage fails every poll and never recovers.
MAX_BLOCKS_PER_POLL = 5000

# How far behind head we're still willing to drain. Measured against the live
# chain 2026-07-19: a drain covers ~2600 blocks/s, ~260x realtime, so a 12h gap
# closes in ~2.7 min of polls. A week-old cursor would take ~38 min, all of it
# blind to launches happening now — and it buys nothing, because every launch
# in that backlog is long past the watch window and can no longer alert. So
# above this we skip, loudly, rather than drain.
MAX_BACKFILL_BLOCKS = int(12 * 3600 / BLOCK_SECS)               # ~430k

# "rpc" (default) or "http". Env override so the LaunchAgent can flip it without
# a code change if pons.family ever comes back.
DISCOVERY_SOURCE = os.environ.get("PONS_DISCOVERY_SOURCE", "rpc").strip().lower()

CURSOR_FILE = os.environ.get(
    "PONS_DISCOVERY_CURSOR", os.path.join(HERE, "data", "discovery_cursor.json"))

_cursor = None    # next block to scan; None until the first poll sets it
_cursor_warned = 0.0   # last time a cursor-save failure was logged
_BLOCK_TS = {}    # block (hex str) -> unix ts, for RPCs that omit blockTimestamp
_SYM = {}         # token -> resolved ERC20 symbol (or None)


def _load_cursor():
    """Next block to scan, as persisted by the last poll, or None for a cold start."""
    try:
        with open(CURSOR_FILE) as f:
            return int(json.load(f)["next_block"])
    except Exception:  # noqa: BLE001
        return None


def _save_cursor(next_block, head):
    """Persist the cursor so a restart resumes instead of re-basing at head.

    Written through a temp file and os.replace (atomic within a directory) so a
    crash mid-write can't leave a truncated file behind. `head` is carried for
    operators reading the file by hand — how far behind we were when it landed.
    """
    tmp = CURSOR_FILE + ".tmp"
    try:
        # dirname is "" for a bare filename (PONS_DISCOVERY_CURSOR=cursor.json),
        # and os.makedirs("") raises — which would drop us to in-memory cursors
        # for the life of the process, silently.
        parent = os.path.dirname(CURSOR_FILE)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(tmp, "w") as f:
            json.dump({"next_block": next_block, "head": head,
                       "updated": _iso(int(time.time()))}, f)
        os.replace(tmp, CURSOR_FILE)
    except Exception as e:  # noqa: BLE001
        # Never let a disk problem kill discovery: the in-memory cursor still
        # advances, so this degrades to the old behaviour rather than stalling.
        # Throttled — the poll runs every ~2s, and a full disk would otherwise
        # bury the launch lines this log exists to show.
        global _cursor_warned
        if time.time() - _cursor_warned > 60:
            _cursor_warned = time.time()
            print(f"  cursor save failed ({e}) — restarts will lose their place",
                  flush=True)


def get(path, params=None, timeout=30, retries=4):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last = None
    headers = {
        "accept": "application/json",
        "user-agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"GET {path} failed after {retries}: {last}")


# ---- symbol resolution -----------------------------------------------------

def _decode_symbol(hexstr):
    """Decode an ERC20 symbol() return: ABI dynamic string OR legacy bytes32."""
    raw = bytes.fromhex(hexstr[2:]) if hexstr.startswith("0x") else bytes.fromhex(hexstr)
    if len(raw) >= 64:
        # dynamic string: [offset(32)][length(32)][data...]
        try:
            length = int.from_bytes(raw[32:64], "big")
            if 0 < length <= 64:
                txt = raw[64:64 + length].decode("utf-8", "ignore").strip("\x00").strip()
                if txt:
                    return txt
        except Exception:  # noqa: BLE001
            pass
    # legacy bytes32: right-padded ascii
    txt = raw[:32].decode("utf-8", "ignore").strip("\x00").strip()
    return txt or None


def resolve_symbols(tokens):
    """Batch symbol() for tokens we haven't resolved yet, into _SYM.

    One round trip per poll rather than one per launch — at ~148 launches/hour
    a burst can share a single block. A token whose call *fails* is left
    uncached so the next poll retries it; only a definitive answer (including
    "this contract has no readable symbol") is cached.
    """
    todo = [t for t in dict.fromkeys(tokens) if t not in _SYM]
    if not todo:
        return
    try:
        results = rpc_batch(
            [("eth_call", [{"to": t, "data": "0x95d89b41"}, "latest"]) for t in todo],
            timeout=20,
        )
    except Exception:  # noqa: BLE001
        return      # transient: leave unresolved, retry next poll
    for t, r in zip(todo, results):
        try:
            _SYM[t] = _decode_symbol(r) if (r and r != "0x") else None
        except Exception:  # noqa: BLE001
            _SYM[t] = None


def token_symbol(token):
    """On-chain ERC20 symbol() for one token — the only naming source now that
    pons.family is gone (it was showing the raw 0x… address). Cached."""
    if token not in _SYM:
        resolve_symbols([token])
    return _SYM.get(token)


# ---- on-chain launch discovery ---------------------------------------------

def _iso(ts):
    if ts is None:
        return None
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def decode_launch(log, timestamp=None, symbol=None):
    """One TokenLaunched log -> the launch record `latest()` yields. Pure.

    `launchedAt` stays an ISO-8601 string because every consumer runs it through
    alert_pro.parse_ts(), which does `.replace("Z", "+00:00")` — handing back a
    float raises inside the poll's blanket except and discovery goes silently
    deaf, which is exactly the failure this ticket exists to fix.

    `initialBuyAmount` (raw wei) and `restrictionsEndBlock` are measurements
    only, carried for the refit in #10 — no scoring weight. Note that
    restrictionsEndBlock is an **L1** block number: Robinhood Chain is an
    Arbitrum Orbit chain, so Solidity's block.number returns the L1 block, ~12s
    apart, while our `blockNumber` is the ~0.1s L2 block. The two are not
    comparable. Measured 2026-07-19: the window is a constant 2 L1 blocks (~24s)
    across sampled launches, so it only becomes an interesting feature if pons
    starts varying it per launchConfigId.
    """
    data = log["data"][2:]
    w = [data[i:i + 64] for i in range(0, len(data), 64)]
    if timestamp is None and log.get("blockTimestamp"):
        timestamp = int(log["blockTimestamp"], 16)

    # dexFactory (topic3), dexId, launchConfigId and positionId (data words
    # 2-4) are decoded by position but deliberately not carried: nothing
    # consumes them. Add them here if the refit ever wants them.
    return {
        # --- the key set alert_pro/scan/alert have always read ---
        "token": addr_from_topic(log["topics"][1]).lower(),
        "pool": ("0x" + w[1][-40:]).lower(),
        "blockNumber": int(log["blockNumber"], 16),
        "deployer": addr_from_topic(log["topics"][2]).lower(),
        "symbol": symbol,
        "launchedAt": _iso(timestamp),
        # --- new, from the event ---
        # pairToken is what CoinState orders the pool by; the other two are
        # measurements for the refit.
        "pairToken": ("0x" + w[0][-40:]).lower(),
        "restrictionsEndBlock": int(w[5], 16),
        "initialBuyAmount": int(w[6], 16),
    }


def _block_timestamps(logs):
    """Fill _BLOCK_TS for logs whose RPC omitted blockTimestamp. Cached per
    block — at this launch rate many launches share one."""
    need = sorted({lg["blockNumber"] for lg in logs
                   if not lg.get("blockTimestamp") and lg["blockNumber"] not in _BLOCK_TS})
    if not need:
        return
    try:
        blocks = rpc_batch([("eth_getBlockByNumber", [b, False]) for b in need], timeout=20)
    except Exception:  # noqa: BLE001
        return      # launchedAt falls back to None; alert_pro substitutes now()
    for b, blk in zip(need, blocks):
        if blk and blk.get("timestamp"):
            _BLOCK_TS[b] = int(blk["timestamp"], 16)
    if len(_BLOCK_TS) > 5000:       # keep the cache from growing unbounded
        # by block height, not lexically: keys are hex strings, so a plain sort
        # would rank "0x1000000" below "0xd1842b" and evict the newest blocks.
        for b in sorted(_BLOCK_TS, key=lambda h: int(h, 16))[:2500]:
            del _BLOCK_TS[b]


def _cold_start(head):
    """Where a poll begins with no usable cursor: head minus the watch window.
    Far enough back to catch everything still alert-eligible, not so far as to
    replay history a fresh install has no business seeing."""
    return max(1, head - DISCOVERY_LOOKBACK_BLOCKS)


def _reconcile(cursor, head):
    """Where this poll should start, given the cursor we have and where the
    chain actually is.

    Applied on every poll rather than only to a cursor just read off disk: a
    laptop that slept leaves the *in-memory* cursor exactly as stale as a file
    would, and the process never restarted to re-read it. Three ways a cursor
    loses to head, each of which is otherwise silent.
    """
    if cursor is None:
        return _cold_start(head)

    if cursor > head + MAX_BLOCKS_PER_POLL:
        # A cursor past head is a bad cursor, not a lead on the chain: hand
        # edited, copied off another machine, or written against a different
        # chain. Left alone, the `head < cursor` return below fires on every
        # poll forever — no launches, no exception, no log line — which is
        # precisely the silent deafness this ticket exists to prevent. The
        # slack absorbs the legitimate caught-up case (cursor is head + 1) and
        # an RPC node lagging its peers.
        print(f"  discovery cursor {cursor} is ahead of head {head} "
              f"— bad cursor file, cold-starting instead", flush=True)
        return _cold_start(head)

    if head - cursor > MAX_BACKFILL_BLOCKS:
        resume = _cold_start(head)
        print(f"  discovery cursor {head - cursor} blocks behind head "
              f"(>{MAX_BACKFILL_BLOCKS}): skipping to {resume}, "
              f"blocks {cursor}-{resume - 1} never scanned", flush=True)
        return resume

    return cursor


def _latest_onchain():
    global _cursor
    head = int(rpc("eth_blockNumber", []), 16)
    if _cursor is None:
        _cursor = _load_cursor()        # still None on a genuine cold start
    _cursor = _reconcile(_cursor, head)
    if head < _cursor:
        return []       # no new blocks yet
    # Bounded: a long outage drains over several polls instead of one oversized
    # query. Measured ~2600 blocks/s, ~260x realtime, so a 6h gap closes in
    # ~80s and a 12h one in ~2.7 min.
    to = min(head, _cursor + MAX_BLOCKS_PER_POLL - 1)
    logs = rpc("eth_getLogs", [{
        "address": FACTORY,
        "topics": [TOKEN_LAUNCHED],
        "fromBlock": hex(_cursor),
        "toBlock": hex(to),
    }], timeout=30)
    _block_timestamps(logs)
    tokens = [addr_from_topic(lg["topics"][1]).lower() for lg in logs]
    resolve_symbols(tokens)
    now = time.time()
    records = []
    for lg, tok in zip(logs, tokens):
        ts = _BLOCK_TS.get(lg["blockNumber"])
        if ts is None and not lg.get("blockTimestamp"):
            # Neither the log nor the block lookup gave us a timestamp — the
            # lookup is one batched call and it can fail. Estimate from block
            # height instead of leaving it None, because None sends
            # register_launches() down its `or time.time()` fallback, which
            # dates an hours-old launch as new: it lands inside the watch
            # window and alerts. A drain makes that likely, not exotic.
            #
            # `now` stands in for head's timestamp (head is, by definition,
            # about now). Good to a few seconds against a 15-minute window.
            ts = now - (head - int(lg["blockNumber"], 16)) * BLOCK_SECS
        # ts=None here means the log carried its own blockTimestamp, which
        # decode_launch prefers anyway — it is exact, this is an estimate.
        records.append(decode_launch(lg, timestamp=ts, symbol=_SYM.get(tok)))
    # Advance only once the batch is decoded: a mid-poll failure re-polls the
    # same range next tick rather than skipping past unseen launches.
    _cursor = to + 1
    _save_cursor(_cursor, head)
    return records


def _latest_http():
    return get(EP_LATEST)


def latest():
    """Newest launches, one record per launch. On-chain by default."""
    if DISCOVERY_SOURCE == "http":
        return _latest_http()
    return _latest_onchain()


def recent_buys():
    return get(EP_RECENT_BUYS)


def graduations():
    return get(EP_GRADUATIONS)


def all_launches():
    return get(EP_LAUNCHES, timeout=60)


def market(token):
    return get(EP_MARKET, {"token": token})
