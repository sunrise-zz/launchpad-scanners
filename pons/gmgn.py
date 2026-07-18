"""GMGN OpenAPI helper (read-only) — https://openapi.gmgn.ai

Professional launch forensics GMGN computes that we can't from raw chain data
alone: cross-platform smart-money/renowned wallet tags, bot/rat/bundler rates,
dev reputation (tokens created, best prior ATH, twitter rename/delete history)
and copycat detection (duplicate image/twitter/website counters).

Auth ("exist" mode — the read-only tier, no request signature):
    X-APIKEY header + query params timestamp (unix sec, server tolerance ±5s)
    and client_id (fresh uuid4 per call; replays rejected within 7s).
Key comes from $GMGN_API_KEY or ~/.config/gmgn/.env. NEVER configure
GMGN_PRIVATE_KEY in this repo — that unlocks trading ("signed" mode) and this
repo is detection-only by policy.

snapshot() returns the compact alert-time feature dict that
outcomes.record_alert() stores under row["gmgn"]. Collected-not-gated: the
outcome tracker will tell us which fields actually predict returns before any
of them earns score weight (same display-then-refit discipline as the rest).

Chains: sol / bsc / base / eth / robinhood. Arc is NOT covered by GMGN.
Rate limits (per key, weight-based): info/security ~20 req/s, holders ~4 req/s
— orders of magnitude above our alert volume. Every function is best-effort
and returns None/{} on failure; nothing here ever raises into a scanner loop.

Manual use:
    python3 pons/gmgn.py snapshot robinhood 0xff4c…7777
    python3 pons/gmgn.py info|security|holders sol <mint>
    python3 pons/gmgn.py trending robinhood 1h
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import uuid

HOST = "https://openapi.gmgn.ai"
ENV_FILE = os.path.expanduser("~/.config/gmgn/.env")
CHAINS = ("sol", "bsc", "base", "eth", "robinhood")

_KEY = [None, False]   # [value, loaded]


def api_key():
    """$GMGN_API_KEY, else ~/.config/gmgn/.env. None when unconfigured."""
    if not _KEY[1]:
        k = os.environ.get("GMGN_API_KEY")
        if not k and os.path.exists(ENV_FILE):
            try:
                for line in open(ENV_FILE):
                    line = line.strip()
                    if line.startswith("GMGN_API_KEY="):
                        k = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            except Exception:  # noqa: BLE001
                k = None
        _KEY[0], _KEY[1] = (k or None), True
    return _KEY[0]


def _get(path, params, timeout=8):
    """GET with exist-auth. Unwraps the {code, data} envelope. None on ANY
    failure (no key, HTTP error, rate limit, bad JSON) — callers stay alive."""
    key = api_key()
    if not key:
        return None
    q = dict(params or {})
    q["timestamp"] = int(time.time())
    q["client_id"] = str(uuid.uuid4())
    url = f"{HOST}{path}?" + urllib.parse.urlencode(q, doseq=True)
    req = urllib.request.Request(url, headers={
        "X-APIKEY": key,
        "Content-Type": "application/json",
        "User-Agent": "launchpad-scanners/0.1",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None
    if isinstance(d, dict) and "code" in d:
        return d.get("data") if d.get("code") == 0 else None
    return d


def _post(path, params, body, timeout=10):
    """POST with exist-auth (same envelope handling as _get)."""
    key = api_key()
    if not key:
        return None
    q = dict(params or {})
    q["timestamp"] = int(time.time())
    q["client_id"] = str(uuid.uuid4())
    url = f"{HOST}{path}?" + urllib.parse.urlencode(q, doseq=True)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={
                                     "X-APIKEY": key,
                                     "Content-Type": "application/json",
                                     "User-Agent": "launchpad-scanners/0.1",
                                 })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None
    if isinstance(d, dict) and "code" in d:
        return d.get("data") if d.get("code") == 0 else None
    return d


# GMGN's own robinhood quote-address allow-list (from gmgn-cli). Sent verbatim;
# an EMPTY launchpad_platform/quote list filters out EVERYTHING, so both must
# always be non-empty.
_TRENCH_QUOTES = {"robinhood": [11, 20, 24, 12, 0], "sol": [4, 5, 3, 1, 13, 0],
                  "base": [11, 3, 12, 13, 0], "eth": [20, 11, 8, 3, 12, 1, 0],
                  "bsc": [6, 7, 1, 16, 8, 3, 9, 10, 2, 17, 18, 0]}


def trenches(chain, platforms, types=("new_creation", "near_completion", "completed"),
             limit=50, timeout=12):
    """GMGN Trenches board — the launchpad-native new/completing/completed
    columns. `platforms` is a REQUIRED allow-list of launchpad keys (e.g.
    ["bags", "bankr"]); server defaults return nothing. Response section for
    near_completion comes back named "pump". None on failure."""
    section = {"filters": ["offchain", "onchain"], "launchpad_platform_v2": True,
               "limit": limit, "launchpad_platform": list(platforms)}
    qt = _TRENCH_QUOTES.get(chain)
    if qt:
        section["quote_address_type"] = qt
    body = {"version": "v2"}
    for t in types:
        body[t] = dict(section)
    return _post("/v1/trenches", {"chain": chain}, body, timeout)


def token_info(chain, address, timeout=8):
    return _get("/v1/token/info", {"chain": chain, "address": address}, timeout)


def token_security(chain, address, timeout=8):
    return _get("/v1/token/security", {"chain": chain, "address": address}, timeout)


def top_holders(chain, address, limit=20, tag=None, order_by=None, timeout=10):
    p = {"chain": chain, "address": address, "limit": limit}
    if tag:
        p["tag"] = tag           # smart_degen|renowned|sniper|rat_trader|bundler|fresh_wallet|dev|…
    if order_by:
        p["orderby"] = order_by  # amount_percentage|profit|…
    return _get("/v1/market/token_top_holders", p, timeout)


def trending(chain, interval="1h", limit=20, timeout=10):
    d = _get("/v1/market/rank", {"chain": chain, "interval": interval, "limit": limit}, timeout)
    return (d or {}).get("rank") if isinstance(d, dict) else d


def _f(x):
    """Float coercion — GMGN returns most rates as strings. None on failure."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def chain_addr_for(chain, track, token):
    """Map an alert's (chain, track, token) to a (gmgn_chain, address) pair,
    or (None, None) when GMGN can't serve it (arc, numeric virtuals ids…)."""
    track = track or {}
    slug = {"robinhood": "robinhood", "base": "base", "solana": "sol"}.get(track.get("chainSlug"))
    gchain = slug or {"pumpfun": "sol", "flap": "robinhood"}.get(track.get("method")) \
        or ({"BASE": "base", "SOLANA": "sol", "ROBINHOOD": "robinhood", "ETH": "eth", "BSC": "bsc"}
            .get((chain or "").upper()))
    addr = track.get("address") or token or ""
    if gchain in ("robinhood", "base", "eth", "bsc"):
        ok = addr.startswith("0x") and len(addr) == 42
    elif gchain == "sol":
        ok = 32 <= len(addr) <= 44 and not addr.startswith("0x")
    else:
        ok = False
    return (gchain, addr) if ok else (None, None)


def snapshot(chain, address, timeout=8):
    """Compact predictive-candidate features from one token_info call.
    None when GMGN has no data / no key. None-valued fields are stripped so
    alerts.jsonl rows stay small."""
    d = token_info(chain, address, timeout)
    if not isinstance(d, dict) or not d.get("address"):
        return None
    stat = d.get("stat") or {}
    wt = d.get("wallet_tags_stat") or {}
    dev = d.get("dev") or {}
    ath = dev.get("ath_token_info") or {}
    link = d.get("link") or {}
    g = {
        # socials known to GMGN (booleans kept even when False — "no X at alert
        # time" is itself the strongest loser signal in pons outcome data)
        "has_x": bool(link.get("twitter_username")),
        "has_web": bool(link.get("website")),
        "has_tg": bool(link.get("telegram")),
        # traction / attention
        "holders": d.get("holder_count"),
        "hot": d.get("hot_level"),
        "visits": d.get("visiting_count"),
        "pad": d.get("launchpad") or None,
        "pad_progress": _f(d.get("launchpad_progress")),
        # wallet-tag counts among holders (cross-platform smart-money prior)
        "smart": wt.get("smart_wallets"),
        "renowned": wt.get("renowned_wallets"),
        "sniper_w": wt.get("sniper_wallets"),
        "bundler_w": wt.get("bundler_wallets"),
        "whale_w": wt.get("whale_wallets"),
        # concentration / bot forensics (rates 0-1)
        "top10_rate": _f(stat.get("top_10_holder_rate")),
        "dev_hold_rate": _f(stat.get("dev_team_hold_rate")),
        "fresh_rate": _f(stat.get("fresh_wallet_rate")),
        "bot_rate": _f(stat.get("bot_degen_rate")),
        "rat_rate": _f(stat.get("top_rat_trader_percentage")),
        "bundler_rate": _f(stat.get("top_bundler_trader_percentage")),
        "entrap_rate": _f(stat.get("top_entrapment_trader_percentage")),
        "sniper70_rate": _f(stat.get("top70_sniper_hold_rate")),
        # dev reputation (⚠️ on flap `creator` is the factory address — keep our
        # own mint-event deployer as truth there; recorded anyway for analysis)
        "dev_created": stat.get("creator_created_count"),
        "dev_best_ath_mc": _f(ath.get("ath_mc")),
        "tw_created": dev.get("twitter_create_token_count"),
        "tw_deleted": dev.get("twitter_del_post_token_count"),
        # copycat detection
        "img_dup": d.get("image_dup_count"),
    }
    return {k: v for k, v in g.items() if v is not None} or None


def main():
    import sys
    if len(sys.argv) < 3:
        print(__doc__)
        return
    cmd, chain = sys.argv[1], sys.argv[2]
    arg = sys.argv[3] if len(sys.argv) > 3 else None
    if cmd == "snapshot":
        print(json.dumps(snapshot(chain, arg), indent=2))
    elif cmd == "info":
        print(json.dumps(token_info(chain, arg), indent=2))
    elif cmd == "security":
        print(json.dumps(token_security(chain, arg), indent=2))
    elif cmd == "holders":
        print(json.dumps(top_holders(chain, arg), indent=2))
    elif cmd == "trending":
        print(json.dumps(trending(chain, arg or "1h"), indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
