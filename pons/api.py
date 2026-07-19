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

# Cold start window. Blocks are ~0.1s, so 3000 blocks ~= 5 min — enough to pick
# up launches from a brief restart without replaying history on a fresh install.
# A persisted cursor that survives restarts properly is #4.
DISCOVERY_LOOKBACK_BLOCKS = 3000

# "rpc" (default) or "http". Env override so the LaunchAgent can flip it without
# a code change if pons.family ever comes back.
DISCOVERY_SOURCE = os.environ.get("PONS_DISCOVERY_SOURCE", "rpc").strip().lower()

_cursor = None    # next block to scan; None until the first poll sets it
_BLOCK_TS = {}    # block (hex str) -> unix ts, for RPCs that omit blockTimestamp
_SYM = {}         # token -> resolved ERC20 symbol (or None)


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


def _latest_onchain():
    global _cursor
    head = int(rpc("eth_blockNumber", []), 16)
    if _cursor is None:
        _cursor = max(1, head - DISCOVERY_LOOKBACK_BLOCKS)
    if head < _cursor:
        return []       # no new blocks yet
    logs = rpc("eth_getLogs", [{
        "address": FACTORY,
        "topics": [TOKEN_LAUNCHED],
        "fromBlock": hex(_cursor),
        "toBlock": hex(head),
    }], timeout=30)
    _block_timestamps(logs)
    tokens = [addr_from_topic(lg["topics"][1]).lower() for lg in logs]
    resolve_symbols(tokens)
    records = [
        decode_launch(lg, timestamp=_BLOCK_TS.get(lg["blockNumber"]),
                      symbol=_SYM.get(tok))
        for lg, tok in zip(logs, tokens)
    ]
    # Advance only once the batch is decoded: a mid-poll failure re-polls the
    # same range next tick rather than skipping past unseen launches.
    _cursor = head + 1
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
