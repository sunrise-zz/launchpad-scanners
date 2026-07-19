"""ETH/USD provider chain and its visible fallback (#5).

Every USD figure in a pons alert is a chain-side ETH amount multiplied by this
price, so a wrong price is wrong everywhere at once and never looks wrong. Two
things therefore get pinned here:

  1. A provider answer is only trusted if it survives a sanity band. The
     measured trap (issue #5): DexScreener's cross-chain WETH pairs price the
     *PulseChain* token at $0.0000065 — nine orders of magnitude off, and a
     "did the provider return a number?" check waves it straight through.
  2. When every provider fails we fall back to a constant, and the alert says
     so. A silently stale $1900 was accurate by luck when it was written; at
     ETH $3,000 it is 37% wrong on every alert with nothing on screen to show it.

Nothing here touches the network — providers are stubbed, parsers are pure.
"""
from __future__ import annotations

import pytest

# Measured 2026-07-19: DexScreener $1872.10, GMGN $1871.17 (0.05% apart).
LIVE = 1872.10

# The wrong-chain answer from the issue #5 investigation. Same address, different
# token, ~$0.0000065. This is the number the sanity band exists to reject.
PULSECHAIN_PRICE = "0.000006412"


# --- sanity band ------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    None, "", "n/a", {}, [],          # provider returned no usable number
    0, 0.0, "0",                      # DexScreener sends 0 for unindexed pairs
    -1872.10,                         # sign flip
    PULSECHAIN_PRICE,                 # wrong chain, nine orders low
    0.0000065, 99.99,                 # below the band
    100_000.01, 1e9,                  # above the band
])
def test_sane_rejects_values_no_eth_price_could_be(ethprice, bad):
    assert ethprice.sane(bad) is None


@pytest.mark.parametrize("good", [LIVE, str(LIVE), 100.0, 100_000.0, 3000, "1871.16536607"])
def test_sane_accepts_plausible_prices_as_floats(ethprice, good):
    got = ethprice.sane(good)
    assert got == pytest.approx(float(good))
    assert isinstance(got, float), "callers do arithmetic on this; a str would concatenate"


# --- provider parsing: pure, offline ---------------------------------------

def test_dexscreener_parse_reads_the_mainnet_base_side_price(ethprice):
    assert ethprice.parse_dexscreener([
        {"chainId": "ethereum",
         "baseToken": {"address": ethprice.WETH_MAINNET, "symbol": "WETH"},
         "quoteToken": {"symbol": "USDC"},
         "priceUsd": str(LIVE)},
    ]) == pytest.approx(LIVE)


def test_dexscreener_parse_ignores_pairs_from_other_chains(ethprice):
    """The same address on PulseChain is a different token. Taking a naive
    median over an unfiltered response returns $0.0000065."""
    assert ethprice.parse_dexscreener([
        {"chainId": "pulsechain",
         "baseToken": {"address": ethprice.WETH_MAINNET, "symbol": "WETH"},
         "quoteToken": {"symbol": "WPLS"},
         "priceUsd": PULSECHAIN_PRICE},
        {"chainId": "pulsechain",
         "baseToken": {"address": ethprice.WETH_MAINNET, "symbol": "WETH"},
         "quoteToken": {"symbol": "ATROPA"},
         "priceUsd": "0.000006473"},
    ]) is None


def test_dexscreener_parse_ignores_pairs_where_weth_is_the_quote(ethprice):
    """priceUsd is the *base* token's price. In a SHIB/WETH pair it is SHIB's
    price, which is not an ETH price and would sail through the band if the
    base token happened to be worth a few hundred dollars."""
    assert ethprice.parse_dexscreener([
        {"chainId": "ethereum",
         "baseToken": {"address": "0x" + "9" * 40, "symbol": "PEPE"},
         "quoteToken": {"address": ethprice.WETH_MAINNET, "symbol": "WETH"},
         "priceUsd": "420.00"},
    ]) is None


def test_dexscreener_parse_medians_across_mainnet_pairs(ethprice):
    """One thin pool should not move the price; the measured response has 8
    base-side pairs on the legacy endpoint."""
    pairs = [{"chainId": "ethereum",
              "baseToken": {"address": ethprice.WETH_MAINNET, "symbol": "WETH"},
              "quoteToken": {"symbol": "USDC"},
              "priceUsd": p}
             for p in ("1871.00", "1872.10", "1873.00", "1872.10", "1990.00")]
    assert ethprice.parse_dexscreener(pairs) == pytest.approx(1872.10)


@pytest.mark.parametrize("payload", [None, [], {}, "garbage", [{}], [{"chainId": "ethereum"}]])
def test_dexscreener_parse_survives_a_shape_it_did_not_expect(ethprice, payload):
    assert ethprice.parse_dexscreener(payload) is None


def test_gmgn_parse_reads_the_nested_string_price(ethprice):
    """GMGN nests the price under `price.price` and returns it as a string
    (measured shape, 2026-07-19)."""
    assert ethprice.parse_gmgn(
        {"address": ethprice.WETH_MAINNET.lower(),
         "price": {"price": "1871.16536607", "price_1h": "1861.50353589"}}
    ) == pytest.approx(1871.16536607)


@pytest.mark.parametrize("payload", [
    None, {}, "garbage",
    {"price": None},
    {"price": {}},
    {"price": 1872.10},              # flat instead of nested
    {"price": {"price": "0"}},       # in-band shape, out-of-band value
])
def test_gmgn_parse_survives_a_shape_it_did_not_expect(ethprice, payload):
    assert ethprice.parse_gmgn(payload) is None


# --- the provider chain -----------------------------------------------------

def provider(name, value=None, raises=None, calls=None):
    """A stub provider that records that it was called."""
    def _p(timeout=None):
        if calls is not None:
            calls.append(name)
        if raises:
            raise raises
        return value
    return _p


def test_first_provider_that_answers_wins_and_the_rest_are_not_called(ethprice):
    calls = []
    price = ethprice.fetch(providers=[("dexscreener", provider("dexscreener", LIVE, calls=calls)),
                                      ("gmgn", provider("gmgn", 9999.0, calls=calls))])
    assert price == pytest.approx(LIVE)
    assert price.source == "dexscreener"
    assert calls == ["dexscreener"], "a healthy first provider must not cost a second call"


def test_falls_through_to_the_next_provider_when_the_first_returns_nothing(ethprice):
    calls = []
    price = ethprice.fetch(providers=[("dexscreener", provider("dexscreener", None, calls=calls)),
                                      ("gmgn", provider("gmgn", LIVE, calls=calls))])
    assert price == pytest.approx(LIVE)
    assert price.source == "gmgn"
    assert calls == ["dexscreener", "gmgn"]


def test_falls_through_when_a_provider_raises(ethprice):
    """Providers do their own network I/O. One of them throwing must not take
    the scanner's poll loop with it."""
    price = ethprice.fetch(providers=[("dexscreener", provider("dexscreener", raises=OSError("dns"))),
                                      ("gmgn", provider("gmgn", LIVE))])
    assert price == pytest.approx(LIVE)
    assert price.source == "gmgn"


def test_falls_through_when_a_provider_answers_outside_the_sanity_band(ethprice):
    """The wrong-chain answer must not be preferred over a healthy provider
    just because it arrived first."""
    price = ethprice.fetch(providers=[("dexscreener", provider("dexscreener", PULSECHAIN_PRICE)),
                                      ("gmgn", provider("gmgn", LIVE))])
    assert price == pytest.approx(LIVE)
    assert price.source == "gmgn"


def test_falls_back_to_the_constant_only_when_every_provider_fails(ethprice):
    price = ethprice.fetch(providers=[("dexscreener", provider("dexscreener", None)),
                                      ("gmgn", provider("gmgn", raises=ValueError("boom")))])
    assert price == pytest.approx(ethprice.FALLBACK)
    assert price.source == "fallback"
    assert price.estimated is True


def test_a_live_price_is_not_marked_estimated(ethprice):
    assert ethprice.fetch(providers=[("dexscreener", provider("dexscreener", LIVE))]).estimated is False


def test_price_is_a_real_float_so_callers_can_do_arithmetic(ethprice):
    """glance() multiplies this by an ETH amount and formats the result. The
    provenance rides along on the value precisely so that every existing
    arithmetic call site keeps working untouched."""
    price = ethprice.fetch(providers=[("dexscreener", provider("dexscreener", LIVE))])
    assert isinstance(price, float)
    assert 1.2 * price == pytest.approx(1.2 * LIVE)
    assert float(price) == pytest.approx(LIVE)


def test_fetch_never_raises_even_with_no_providers_at_all(ethprice):
    price = ethprice.fetch(providers=[])
    assert price == pytest.approx(ethprice.FALLBACK)
    assert price.estimated is True


def test_the_shipped_chain_has_at_least_two_independent_providers(ethprice):
    """The acceptance criterion is two *independent* sources — if this ever
    collapses to one, a single outage silently reverts us to the constant.
    Pins the count and the cheap-first ordering, not the exact roster, so
    adding a third provider doesn't fail the suite."""
    names = [n for n, _ in ethprice.PROVIDERS]
    assert len(names) >= 2
    assert len(set(names)) == len(names), "duplicate providers are not independent"
    assert names[0] == "dexscreener", "the keyless sub-second provider goes first"


def test_a_provider_that_cannot_answer_on_this_host_is_reported(ethprice, monkeypatch):
    """GMGN's key lives outside the repo, so a fresh host has no key and the
    chain is silently down to one provider — the exact silent degradation this
    module exists to prevent. It must be announceable, not discovered later."""
    monkeypatch.setattr(ethprice.gmgn, "api_key", lambda: None)
    assert ethprice.unconfigured() == ["gmgn"]

    monkeypatch.setattr(ethprice.gmgn, "api_key", lambda: "a-key")
    assert ethprice.unconfigured() == []


def test_describe_names_the_source_and_flags_an_estimate(ethprice):
    live = ethprice.fetch(providers=[("dexscreener", provider("dexscreener", LIVE))])
    assert live.describe() == "$1,872.10 from dexscreener"

    stale = ethprice.fetch(providers=[])
    assert stale.describe().startswith("$1,900.00 from fallback")
    assert "⚠️" in stale.describe(), "a log line for a guessed price must look like one"


# --- the alert marking ------------------------------------------------------

@pytest.fixture
def glance_of(pons, monkeypatch):
    """The at-a-glance stats line for a coin with 1.2 ETH paired.

    total_supply/holders are the network half of glance() and irrelevant here —
    stubbed so these stay offline and the line is stable enough to diff."""
    monkeypatch.setattr(pons, "total_supply", lambda token: 1_000_000_000)
    monkeypatch.setattr(pons, "holders", lambda token, now, **kw: 142)
    return lambda price: pons.glance("0x" + "1" * 40, 0.00007, 1.2, 78.0, 0, 200, price)


def test_alert_marks_usd_figures_priced_off_the_constant(ethprice, glance_of):
    line = glance_of(ethprice.fetch(providers=[]))
    assert "⚠️est" in line, "a stale USD figure that doesn't look stale is the bug"


def test_alert_does_not_mark_usd_figures_priced_off_a_live_provider(ethprice, glance_of):
    line = glance_of(ethprice.fetch(providers=[("dexscreener", provider("dexscreener", LIVE))]))
    assert "⚠️est" not in line
    assert "$" in line, "the liquidity USD figure should still be there"


def test_the_marked_and_unmarked_lines_differ_only_by_the_marker(ethprice, glance_of):
    """Guards against the marker quietly suppressing the number it annotates."""
    live = glance_of(ethprice.fetch(providers=[("dexscreener", provider("dexscreener", ethprice.FALLBACK))]))
    stale = glance_of(ethprice.fetch(providers=[]))
    assert live != stale
    assert stale.replace("~", "").replace(" ⚠️est", "") == live


def test_only_the_liquidity_figure_is_marked_not_the_market_cap(glance_of, ethprice):
    """mc is priced from the coin's own priceUsd, not from ETH/USD — marking it
    would claim staleness that isn't there."""
    stale = glance_of(ethprice.fetch(providers=[]))
    mc, liq = stale.split("💧")
    assert "⚠️est" not in mc
    assert "⚠️est" in liq


def test_glance_still_accepts_a_plain_float_price(glance_of):
    """Every existing caller passes a bare float (and the formatter tests pass
    0). Provenance is optional metadata, not a new required type."""
    assert "⚠️est" not in glance_of(1872.10)
    assert "$" in glance_of(1872.10)
    assert "liq 1.20 ETH ·" in glance_of(0), "no price means no USD figure at all"
