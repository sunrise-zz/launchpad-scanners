"""Live ETH/USD for pons alerts — provider chain with a visible fallback.

Every USD figure in an alert is a chain-side ETH amount multiplied by this one
number, so a wrong price is wrong everywhere at once and never *looks* wrong.
That shapes the whole module:

  * Two independent providers, tried in order. DexScreener first (public, no
    key, ~0.1s); GMGN second (keyed, ~0.3s, different infrastructure entirely,
    so a DexScreener outage doesn't take both).
  * Every answer must clear a sanity band before it is trusted. The measured
    trap (#5): DexScreener's *cross-chain* WETH pairs price the PulseChain
    token at $0.0000065 — nine orders of magnitude off, and a "did it return a
    number?" check waves it straight through. A provider answering nonsense
    falls through to the next one exactly like a provider answering nothing.
  * Only when everything fails do we use the constant, and then `fetch()`
    returns it marked so the alert can say so. The constant was accurate by
    luck when it was written; at ETH $3,000 it is 37% wrong on every alert.

Single attempt per provider with a short timeout, deliberately — the thing this
replaced retried a dead domain four times with sleeps and stalled the poll loop
6.1s every 5 minutes (#3's bug, at a second call site). Nothing here raises.

Manual use:
    python3 pons/ethprice.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gmgn  # noqa: E402

# Mainnet WETH. Note this is NOT pons' WETH (Robinhood chain) — we want the
# price of ether itself, and mainnet is where the deep, well-arbitraged pools
# are. The chain-side amounts these prices multiply are denominated in the
# same asset either way.
WETH_MAINNET = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

FALLBACK = 1900.0
FALLBACK_SOURCE = "fallback"   # the one source name that means "nobody answered"
# Wide enough to survive any real move in ether's price, tight enough to reject
# a wrong-chain token ($0.0000065) or a wrong-side pair price. Anything outside
# is a provider bug, not a market event.
SANE_LO, SANE_HI = 100.0, 100_000.0

DEXSCR_ETH = "https://api.dexscreener.com/tokens/v1/ethereum/"
TIMEOUT = 5


class Price(float):
    """An ETH/USD price that carries where it came from.

    Subclassing float is what lets `paired * ethusd` and `human_usd(...)` at
    every existing call site keep working untouched while alerts gain the
    ability to ask whether the number is real.

    ⚠️ Provenance does NOT survive arithmetic: `price * 2` is a plain float and
    has no `.estimated`. Ask the question *before* you do the multiplication —
    which is why glance() computes its marker off `ethusd`, not off the
    product. Callers that might hold either type should use
    `getattr(x, "estimated", False)`.
    """

    __slots__ = ("source",)

    def __new__(cls, value, source):
        p = super().__new__(cls, value)
        p.source = source
        return p

    @property
    def estimated(self):
        """True when no provider answered and this is the hardcoded constant."""
        return self.source == FALLBACK_SOURCE

    def describe(self):
        """One-line provenance for logs: '$1,870.18 from dexscreener'."""
        return f"${float(self):,.2f} from {self.source}" + (
            "  ⚠️ estimated — every provider failed" if self.estimated else "")

    def __repr__(self):
        return f"Price({float(self)!r}, {self.source!r})"


def sane(x):
    """Coerce to float and reject anything no ETH price could be. None if bad."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v or not (SANE_LO <= v <= SANE_HI):   # NaN fails every comparison
        return None
    return v


# --- providers: a parse half (pure) and a fetch half (network) -------------

def parse_dexscreener(pairs):
    """Median priceUsd over mainnet pairs where WETH is the *base* token.

    Both filters matter. `chainId` because the same address on PulseChain is a
    different token; base-side because priceUsd describes the base token, so in
    a PEPE/WETH pair it is PEPE's price.
    """
    if not isinstance(pairs, list):
        return None
    want = WETH_MAINNET.lower()
    prices = []
    for p in pairs:
        if not isinstance(p, dict) or p.get("chainId") != "ethereum":
            continue
        base = p.get("baseToken") or {}
        if (base.get("address") or "").lower() != want:
            continue
        v = sane(p.get("priceUsd"))
        if v is not None:
            prices.append(v)
    return statistics.median(prices) if prices else None


def parse_gmgn(info):
    """GMGN nests the price under `price.price`, as a string."""
    if not isinstance(info, dict):
        return None
    price = info.get("price")
    if not isinstance(price, dict):
        return None
    return sane(price.get("price"))


def from_dexscreener(timeout=TIMEOUT):
    """Public, no key. The chain-scoped endpoint already filters to mainnet;
    parse_dexscreener re-checks rather than trusting that to stay true."""
    req = urllib.request.Request(DEXSCR_ETH + WETH_MAINNET,
                                 headers={"user-agent": "Mozilla/5.0",
                                          "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_dexscreener(json.loads(r.read()))


def from_gmgn(timeout=TIMEOUT):
    """Keyed, and already integrated for holder forensics. gmgn._get swallows
    its own failures and returns None, which parse_gmgn reads as 'no answer'."""
    return parse_gmgn(gmgn.token_info("eth", WETH_MAINNET, timeout))


PROVIDERS = [("dexscreener", from_dexscreener), ("gmgn", from_gmgn)]


def unconfigured():
    """Providers that cannot answer on this host, whatever the network does.

    GMGN needs a key from $GMGN_API_KEY or ~/.config/gmgn/.env — both outside
    the repo, so a fresh host has them missing. Without it gmgn._get returns
    None instantly and the "two independent providers" chain is silently a
    one-provider chain, one DexScreener outage away from the constant. Silent
    degradation is the failure mode this whole module exists to prevent, so
    the scanner announces it at startup instead.
    """
    return [] if gmgn.api_key() else ["gmgn"]


def fetch(providers=None, timeout=TIMEOUT):
    """First provider with a sane answer wins. Never raises.

    `timeout` is urllib's, which is per socket operation and does NOT bound DNS
    resolution — so this is not a hard wall-clock bound, and a host whose
    resolver hangs on a dead domain can exceed it. That is exactly #5's failure
    mode, and why the periodic refresh calls this off the poll loop.
    """
    for name, get in (PROVIDERS if providers is None else providers):
        try:
            v = sane(get(timeout=timeout))
        except Exception:  # noqa: BLE001 — a provider must never reach the poll loop
            continue
        if v is not None:
            return Price(v, name)
    return Price(FALLBACK, FALLBACK_SOURCE)


if __name__ == "__main__":
    for name, get in PROVIDERS:
        try:
            print(f"{name:14s} {get()}")
        except Exception as e:  # noqa: BLE001
            print(f"{name:14s} FAILED {type(e).__name__}: {e}")
    missing = unconfigured()
    if missing:
        print(f"\n⚠️  unconfigured (cannot answer on this host): {', '.join(missing)}")
    print(f"\n-> {fetch().describe()}")
