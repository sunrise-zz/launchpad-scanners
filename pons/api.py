"""pons.family public API helpers (Robinhood Chain launchpad).

pons exposes a rich public JSON API (Next.js routes on pons.family). Unlike
vlad.fun we don't need to decode on-chain events: the API already gives
graduation progress, paired ETH, price and latest-buy info per token.

Stdlib only.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

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


def latest():
    return get(EP_LATEST)


def recent_buys():
    return get(EP_RECENT_BUYS)


def graduations():
    return get(EP_GRADUATIONS)


def all_launches():
    return get(EP_LAUNCHES, timeout=60)


def market(token):
    return get(EP_MARKET, {"token": token})
