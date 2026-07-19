"""Raw launch-time features on flap, pump and virtuals (#7).

These rows are the training set the score refit (#10) will be fit on, which
makes one distinction load-bearing above all others:

    None means "not measured". 0 means "measured, and it was zero".

Every scanner's existing helpers collapse those two. `virtuals.fnum()` defaults
to 0.0, pump reads `c.get("reply_count") or 0`, flap does
`float(d.get("marketCap") or 0)` — all correct for *scoring*, where a missing
field should simply not earn points, and all wrong for a *training row*, where
a fabricated 0 is indistinguishable from a real one and silently drags a
coefficient toward zero. So the bulk of this file is the same question asked of
each scanner: does an absent field come back None, and does a genuine zero come
back 0?

The other invariant is that features are measurements, never scores — a
derived score in a row would silently reinterpret every row accumulated under
the old formula the moment the weights are refit.

Everything here is offline: the feature builders are pure functions of a feed
row plus what the scanner already computed.
"""
from __future__ import annotations

import json
import os

import pytest

# --- the row shapes each scanner sees, as measured in the live feeds ---------

FLAP_COIN = {           # batman /v3/coin/{addr}
    "symbol": "MOG", "name": "Mog", "price": "0.0000123", "marketCap": "10200",
    "liquidity": "4300", "volume24h": "88000", "holdersCount": 142,
    "isLowRisk": True, "tax": {"hasTax": False},
}

PUMP_ROW = {            # frontend-api-v3.pump.fun coin
    "mint": "A" * 43 + "pump", "symbol": "WIF", "name": "dogwifhat",
    "usd_market_cap": 24000.0, "created_timestamp": 1784450000000,
    "ath_market_cap": 31000.0, "reply_count": 47,
    "king_of_the_hill_timestamp": 1784451000000,
    "twitter": "https://x.com/wif", "telegram": None, "website": None,
    "nsfw": False, "complete": False,
}

# An ESTABLISHED agent — every field populated. Measured against the live BASE
# feed 2026-07-19, a young ON-CURVE agent (the population EARLY actually alerts
# on) is much sparser: mindshare 0/10 rows, holderCount 3/10,
# top10HolderPercentage 3/10, while devHoldingPercentage and volume24h are
# 10/10. Virtuals simply hasn't computed the first three yet at that age. So
# the sparse case below is the realistic one for EARLY, not the exception —
# see test_virtuals_absent_fields_are_none_not_zero, and #8's coverage matrix.
VIRTUALS_ROW = {        # api2.virtuals.io agent (Strapi — numerics arrive as strings)
    "id": 4321, "symbol": "AIXBT", "name": "aixbt", "chain": "BASE",
    "preToken": "0x" + "b" * 40, "tokenAddress": None,
    "totalValueLocked": "33600", "holderCount": "812",
    "holderCountPercent24h": "12.5", "devHoldingPercentage": "3.2",
    "top10HolderPercentage": "28.4", "mindshare": "0.41",
    "volume24h": "91000", "liquidityUsd": "45000", "mcapInVirtual": "50400",
    "priceChangePercent24h": "8.1", "isVerified": True, "isDevCommitted": True,
    "socials": {"TWITTER": "https://x.com/aixbt", "TELEGRAM": None,
                "WEBSITE": "https://aixbt.tech"},
}


# --- builders ---------------------------------------------------------------

@pytest.fixture
def flap_features(flap):
    """FLAP EARLY: the tier that has everything in scope, no extra API call."""
    def _build(**over):
        kw = dict(recips=107, transfers=368, age_s=214.0, mcap=10200.0, liq=4300.0,
                  vol24h=88000.0, feed_holders=142, top1_pot_pct=8.4, top10_pot_pct=31.2,
                  buy_bps=0, sell_bps=0, tax_known=True, low_risk=True)
        kw.update(over)
        return flap.launch_features(**kw)
    return _build


@pytest.fixture
def pump_features(pump):
    def _build(row=None, *, born=1784450000.0, now=1784450600.0, hist=None):
        c = dict(PUMP_ROW if row is None else row)
        co = pump.Coin(c["mint"], born, c.get("symbol"))
        for t, m in (hist if hist is not None else [(now - 300, 12000.0), (now, 24000.0)]):
            co.push(t, m)
        return pump.launch_features(c, co, now)
    return _build


@pytest.fixture
def virtuals_features(virtuals):
    def _build(row=None, *, now=1784450600.0, born=1784443400.0):
        return virtuals.launch_features(dict(VIRTUALS_ROW if row is None else row),
                                        now=now, born=born)
    return _build


ALL_BUILDERS = ("flap_features", "pump_features", "virtuals_features")


# --- the invariant that matters most: None != 0 -----------------------------

def test_flap_absent_fields_are_none_not_zero(flap_features):
    """A batman 404 leaves mcap/liq/holders/top1/top10 genuinely unknown. The
    scoring path reads those as 0 and simply awards no points; a training row
    that says 'this coin had $0 market cap' is a different claim entirely."""
    f = flap_features(mcap=None, liq=None, feed_holders=None, top1_pot_pct=None, top10_pot_pct=None)
    for key in ("mcap", "liq", "feed_holders", "top1_pot_pct", "top10_pot_pct"):
        assert f[key] is None, f"{key} fabricated a value for an unmeasured field"


def test_flap_a_genuine_zero_survives_as_zero(flap_features):
    """Zero tax is a real, common, and informative measurement — it must not be
    laundered into None by a falsy check."""
    f = flap_features(buy_bps=0, sell_bps=0, transfers=0, feed_holders=0)
    assert f["buy_bps"] == 0
    assert f["sell_bps"] == 0
    assert f["transfers"] == 0
    assert f["feed_holders"] == 0


def test_pump_absent_creation_timestamp_gives_no_age(pump_features):
    """pump's Coin.born falls back to `now` when the feed omits
    created_timestamp, which makes age exactly 0.0 — a brand-new coin and a
    coin of unknown age become the same row. Age must be None instead."""
    row = dict(PUMP_ROW, created_timestamp=None)
    assert pump_features(row)["age_s"] is None


def test_pump_age_is_measured_when_the_feed_supplies_it(pump_features):
    f = pump_features(born=1784450000.0, now=1784450600.0)
    assert f["age_s"] == pytest.approx(600.0)


def test_pump_age_comes_from_the_feed_not_from_when_we_first_noticed(pump_features):
    """Regression, found in review. `Coin.born` is stamped at first sighting and
    falls back to `now` when the feed omitted created_timestamp *then*. Gating
    on the field while measuring from born is worse than using either alone: a
    coin first seen without a timestamp that later gains one reported the time
    since we noticed it as its age.

    Here the coin was created 10h before we first saw it. Age must be ~10h,
    not the 10 minutes we have been watching."""
    now = 1784450600.0
    created_ms = (now - 36_600) * 1000          # created 10h10m ago
    f = pump_features(dict(PUMP_ROW, created_timestamp=created_ms),
                      born=now - 600, now=now)   # ...but first seen 10 min ago
    assert f["age_s"] == pytest.approx(36_600.0), "age was measured from first sighting"


def test_pump_does_not_log_which_bar_fired(pump_features):
    """`tier` is already a column on the row, and which bar fired is a decision,
    not a measurement — the one thing the pons template forbids in here."""
    assert "graduating" not in pump_features()


@pytest.mark.parametrize("key,feature", [
    ("reply_count", "replies"), ("ath_market_cap", "ath"),
    ("usd_market_cap", "mcap"),
])
def test_pump_absent_numeric_is_none_not_zero(pump_features, key, feature):
    row = dict(PUMP_ROW)
    row.pop(key)
    assert pump_features(row)[feature] is None


def test_pump_zero_replies_is_a_measurement_not_a_gap(pump_features):
    """`reply_count: 0` is the single most common value in the feed and means
    'nobody has commented' — real signal, not a missing field."""
    assert pump_features(dict(PUMP_ROW, reply_count=0))["replies"] == 0


def test_virtuals_absent_fields_are_none_not_zero(virtuals_features):
    """This is the COMMON case for the EARLY tier, not an edge case: measured
    on the live BASE feed, 0/10 young on-curve agents carried mindshare and
    only 3/10 carried holderCount or top10HolderPercentage.

    fnum() defaults to 0.0 so the cohort pass can't crash on a string. Using it
    to build a training row would report each of those agents as having 0%
    top-10 concentration and 0 holders — the most flattering possible reading
    of a total absence of data, on most of the rows."""
    row = dict(VIRTUALS_ROW)
    for key in ("devHoldingPercentage", "top10HolderPercentage", "holderCount",
                "mindshare", "volume24h", "holderCountPercent24h"):
        row.pop(key)
    f = virtuals_features(row)
    for key in ("dev_pct", "top10_pct", "feed_holders", "mindshare", "vol24h", "holders_24h_pct"):
        assert f[key] is None, f"{key} reported a fabricated 0 for a field Strapi omitted"


def test_virtuals_zero_dev_holding_is_a_real_and_good_measurement(virtuals_features):
    """dev_pct 0 means the dev holds nothing — the best possible reading, and
    exactly the row the refit needs to be able to see."""
    assert virtuals_features(dict(VIRTUALS_ROW, devHoldingPercentage="0"))["dev_pct"] == 0.0


def test_virtuals_coerces_the_strings_strapi_actually_sends(virtuals_features):
    """Strapi returns numerics as strings; a raw value here would make the
    refit's arithmetic either crash or silently string-compare."""
    f = virtuals_features()
    for key in ("dev_pct", "top10_pct", "feed_holders", "mindshare", "vol24h", "tvl"):
        assert isinstance(f[key], (int, float)), f"{key} came through as {type(f[key]).__name__}"
    assert f["dev_pct"] == pytest.approx(3.2)
    assert f["feed_holders"] == 812


def test_virtuals_garbage_numerics_degrade_to_none_not_zero(virtuals_features):
    f = virtuals_features(dict(VIRTUALS_ROW, devHoldingPercentage="n/a", holderCount=""))
    assert f["dev_pct"] is None
    assert f["feed_holders"] is None


# --- measurements, never scores ---------------------------------------------

@pytest.mark.parametrize("builder", ALL_BUILDERS)
def test_no_scanner_logs_a_score_among_its_features(builder, request):
    """The refit changes the weights. A score baked into a row would mean every
    row silently describes a formula that no longer exists — the one thing the
    pons template's docstring forbids outright."""
    f = request.getfixturevalue(builder)()
    for key in f:
        assert "score" not in key.lower(), f"{key} looks like a derived score"
    assert "tier" not in f, "tier is already a top-level column on the row"


@pytest.mark.parametrize("builder", ALL_BUILDERS)
def test_features_are_flat_and_json_round_trip(builder, request):
    """Rows are appended to alerts.jsonl as one line each; a nested dict or a
    non-serialisable value breaks the whole file, not just its own row."""
    f = request.getfixturevalue(builder)()
    assert f, "an empty feature dict would be indistinguishable from no features"
    for key, val in f.items():
        assert isinstance(key, str)
        assert val is None or isinstance(val, (int, float, str, bool)), \
            f"{key} holds a {type(val).__name__}"
    assert json.loads(json.dumps(f)) == f


@pytest.mark.parametrize("builder", ALL_BUILDERS)
def test_every_scanner_measures_progress_under_the_same_name(builder, request):
    """#10 fits across platforms, so the columns that exist everywhere must be
    named the same everywhere — otherwise each platform trains a separate model
    by accident."""
    f = request.getfixturevalue(builder)()
    assert "progress" in f, "graduation progress is the one axis all four share"


# GMGN's snapshot keys, from pons/gmgn.py snapshot(). row["f"] and row["gmgn"]
# are stored side by side on the same row, so a shared key name is ambiguous
# about which measurement is which the moment anything flattens them.
GMGN_KEYS = {
    "has_x", "has_web", "has_tg", "holders", "hot", "visits", "pad", "pad_progress",
    "smart", "renowned", "sniper_w", "bundler_w", "whale_w", "top10_rate",
    "dev_hold_rate", "fresh_rate", "bot_rate", "rat_rate", "bundler_rate",
    "entrap_rate", "sniper70_rate", "dev_created", "dev_best_ath_mc", "tw_created",
    "tw_deleted", "img_dup",
}


@pytest.mark.parametrize("builder", ALL_BUILDERS)
def test_feature_names_never_collide_with_the_gmgn_snapshot(builder, request):
    """Caught live on a real PUMP GRADUATING row: the feed's socials were
    named has_x/has_tg/has_web, exactly GMGN's names for its own independently
    measured socials. Both measurements are worth keeping — they disagree when
    an account is renamed or deleted — but they must stay distinguishable.

    flap's EARLY tier made this concrete beyond naming: its scoring path reads
    `holders` as batman's count *or* GMGN's as a fallback, so the same key would
    have carried a different source depending on which API answered. The feature
    logs batman's alone.
    """
    clash = set(request.getfixturevalue(builder)()) & GMGN_KEYS
    assert not clash, f"f and gmgn would both claim {sorted(clash)}"


# --- derived ratios guard their own division --------------------------------

def test_flap_churn_is_transfers_per_recipient(flap_features):
    assert flap_features(recips=100, transfers=344)["churn"] == pytest.approx(3.44)


def test_flap_churn_is_none_when_it_would_divide_by_zero(flap_features):
    """A SHADOW row can be built the instant the first transfer lands."""
    assert flap_features(recips=0, transfers=5)["churn"] is None
    assert flap_features(recips=None, transfers=None)["churn"] is None


def test_pump_velocity_needs_two_samples(pump_features):
    """One poll gives no rate of change. 0.0 would claim a flat coin."""
    assert pump_features(hist=[(1784450600.0, 24000.0)])["velocity"] is None
    assert pump_features(hist=[(1784450300.0, 12000.0), (1784450600.0, 24000.0)])["velocity"] \
        == pytest.approx(2400.0)


# --- flap: all three tiers log what they have --------------------------------

def test_flap_shadow_tier_logs_the_bar_inputs_it_has(flap):
    """SHADOW deliberately makes no API call, so it has only the on-chain
    cohort counters — but those are exactly the inputs to the EARLY bar, and
    the shadow-control study (#9) is what compares them."""
    f = flap.launch_features(recips=64, transfers=180, age_s=300.0)
    assert (f["recips"], f["transfers"]) == (64, 180)
    assert f["churn"] == pytest.approx(2.8125)
    assert f["mcap"] is None and f["feed_holders"] is None, "SHADOW must not invent API data"


def test_flap_neargrad_has_no_cohort_counters(flap):
    """NEAR-GRAD coins come off the graduatinghot board and never enter `toks`,
    so recipients/transfers/age are structurally unavailable — None, not 0."""
    f = flap.launch_features(mcap=51000.0, liq=22000.0, feed_holders=430, progress=88.0,
                             buy_bps=0, sell_bps=0, tax_known=True)
    assert f["recips"] is None and f["transfers"] is None and f["age_s"] is None
    assert f["progress"] == pytest.approx(88.0)


# --- the record contract: backward compatible -------------------------------

def test_record_alert_omits_the_features_key_when_there_are_none(outcomes_mod, tmp_alerts):
    outcomes_mod.record_alert("flap.sh", "ROBINHOOD", "FLAP EARLY", "MOG", "0xabc",
                              50, {"method": "flap", "address": "0xabc"})
    assert "f" not in tmp_alerts()[0], "old readers must not see a new key appear"


def test_record_alert_stores_features_under_the_short_key(outcomes_mod, tmp_alerts):
    outcomes_mod.record_alert("flap.sh", "ROBINHOOD", "FLAP EARLY", "MOG", "0xabc",
                              50, {"method": "flap", "address": "0xabc"},
                              features={"recips": 107, "mcap": None})
    assert tmp_alerts()[0]["f"] == {"recips": 107, "mcap": None}


def test_rows_with_and_without_features_share_every_other_column(outcomes_mod, tmp_alerts):
    """A reader written before #7 must be able to read a #7 row: the new key is
    purely additive."""
    args = ("flap.sh", "ROBINHOOD", "FLAP EARLY", "MOG", "0xabc", 50,
            {"method": "flap", "address": "0xabc"})
    outcomes_mod.record_alert(*args)
    outcomes_mod.record_alert(*args, features={"recips": 107})
    old, new = tmp_alerts()
    assert set(new) - set(old) == {"f"}
    for key in old:
        if key != "t":                      # timestamps differ by construction
            assert old[key] == new[key]
