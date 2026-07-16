"""Minimal JSON-RPC + event decoding helpers for Robinhood Chain / vlad.fun.

Stdlib only (urllib) so it runs without touching the project's deps.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error

RPC = "https://dry-lively-research.robinhood-mainnet.quiknode.pro/5a684d7fb1aaa80e5a53906f9017f4ee0114cc2c/"
API = "https://api-production-de9d.up.railway.app"

PUMP = "0x6ea53e65b4a577dbbaccbfa84e9050e837c5cb0c"
DEPLOY_BLOCK = 10454184

# topic0 -> event name (decoded via openchain + keccak brute force)
LAUNCHED = "0x738f0a184ad88576a20723a62556cc48d2cd149d129d48dcf26625fbbacc6628"
BOUGHT = "0x7ce543d1780f3bdc3dac42da06c95da802653cd1b212b8d74ec3e3c33ad7095c"
SOLD = "0x9be8a5ca22b7e6e81f04b5879f0248227bb770114291bd47dfaee4c3a82ad60e"
SYNC = "0x930136a8b1ef61e0f392bd6002425e1b351a4d17d1bb960dc49d4554773be6cc"
GRADUATED = "0x487dc7f66c623fb0ff13f9024a3ff9675453d069e075eceb12d9f8d7870e2374"
FEES_HARVESTED = "0xf5149f5613f421a823c25e21089d7f43016d48d7f4e023f910f865a996998358"
OPERATOR_SET = "0xceb576d9f15e4e200fdb5096d64d5dfd667e16def20c1eefd14256d8e3faa267"

TOPIC_NAME = {
    LAUNCHED: "Launched", BOUGHT: "Bought", SOLD: "Sold", SYNC: "Sync",
    GRADUATED: "Graduated", FEES_HARVESTED: "FeesHarvested", OPERATOR_SET: "OperatorSet",
}


def rpc(method, params, timeout=30, retries=5):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
            if "error" in d:
                raise RuntimeError(d["error"])
            return d["result"]
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"rpc {method} failed after {retries}: {last}")


def rpc_batch(calls, timeout=30, retries=5):
    """calls: list of (method, params). Returns list of results in order."""
    body = json.dumps([
        {"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)
    ]).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
            out = [None] * len(calls)
            for item in d:
                out[item["id"]] = item.get("result")
            return out
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"rpc batch failed after {retries}: {last}")


def api_get(path, timeout=25, retries=4):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API + path, headers={"accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"api {path} failed after {retries}: {last}")


# ---- decoding ----

def addr_from_topic(t):
    return "0x" + t[-40:]


def decode_strings(data_hex, n):
    """Decode the first `n` dynamic strings from ABI-encoded event data."""
    data = bytes.fromhex(data_hex[2:] if data_hex.startswith("0x") else data_hex)
    out = []
    for i in range(n):
        off = int.from_bytes(data[i * 32:(i + 1) * 32], "big")
        length = int.from_bytes(data[off:off + 32], "big")
        s = data[off + 32:off + 32 + length]
        try:
            out.append(s.decode("utf-8"))
        except UnicodeDecodeError:
            out.append(s.decode("latin1"))
    return out


def decode_uints(data_hex):
    data = bytes.fromhex(data_hex[2:] if data_hex.startswith("0x") else data_hex)
    return [int.from_bytes(data[i:i + 32], "big") for i in range(0, len(data), 32)]


def decode_log(log):
    """Return a normalized event dict."""
    t0 = log["topics"][0]
    name = TOPIC_NAME.get(t0, t0)
    block = int(log["blockNumber"], 16)
    ev = {
        "name": name,
        "block": block,
        "tx": log["transactionHash"],
        "logIndex": int(log["logIndex"], 16),
        "token": addr_from_topic(log["topics"][1]) if len(log["topics"]) > 1 else None,
    }
    if name == "Launched":
        ev["creator"] = addr_from_topic(log["topics"][2])
        nm, sym, meta = decode_strings(log["data"], 3)
        ev["tname"], ev["symbol"], ev["meta"] = nm, sym, meta
    elif name in ("Bought", "Sold"):
        ev["account"] = addr_from_topic(log["topics"][2])
        u = decode_uints(log["data"])
        # field order differs by side:
        #   Bought(token, buyer, eth_in, tokens_out, fee)
        #   Sold  (token, seller, tokens_in, eth_out, fee)
        if name == "Bought":
            eth_raw, tok_raw = u[0], u[1]
        else:
            tok_raw, eth_raw = u[0], u[1]
        ev["eth"] = eth_raw / 1e18
        ev["tokens"] = tok_raw / 1e18
        ev["fee"] = (u[2] / 1e18) if len(u) > 2 else 0.0
    elif name == "Graduated":
        ev["account"] = addr_from_topic(log["topics"][2]) if len(log["topics"]) > 2 else None
        u = decode_uints(log["data"])
        ev["u"] = u
    elif name == "Sync":
        ev["other"] = addr_from_topic(log["topics"][2]) if len(log["topics"]) > 2 else None
        u = decode_uints(log["data"])
        ev["value"] = u[0] if u else 0
    return ev
