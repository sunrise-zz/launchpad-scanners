"""potato scanner — identity, the volume-only bar, and the gmgn track method.

potato/ is a source-level scanner over potato.fm (a Robinhood-chain Uniswap-V3
launchpad aggregator), not a GMGN trench rider, so it carries its own
map_growing / map_ancient / passes_bar / score_item. These tests pin the things
that would fail silently:

  - the track method is **gmgn**, not "potato" — potato coins are ordinary V3
    tokens GMGN indexes, so a "potato" method would leave every alert unpriceable
    (there is no snap_potato in tracker/track.py, by design);
  - the EARLY bar gates on volume + age only (the Growing feed has no holders/
    mcap), and a placeholder "test" launch or an over-age coin must not pass;
  - a GRAD row carries fdvUsd as a real baseline while an EARLY row carries none;
  - scores separate a strong coin from a thin one.

Direction and separation only, never exact score values — the weights are
provisional until the refit, same rule as the rest of tests/.
"""
import importlib.util
import os
import sys
import types

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = 1_784_780_000            # a fixed "now" the fixtures are aged against


@pytest.fixture(scope="session")
def potato():
    sys.path.insert(0, os.path.join(ROOT, "pons"))
    spec = importlib.util.spec_from_file_location("potato_scan", os.path.join(ROOT, "potato", "scan.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["potato_scan"] = mod
    spec.loader.exec_module(mod)
    return mod


def _args(**kw):
    base = dict(max_age_h=24.0, min_vol=5_000.0)
    base.update(kw)
    return types.SimpleNamespace(**base)


# a strong young Growing coin (BLUECHIP on the live board, 2026-07-23):
STRONG = {"token": "0xBb31694F74B11b38D05566fcf25398360B6b531b", "symbol": "BLUECHIP",
          "name": "Blue Chip", "creator": "0xAbC", "pool": "0xpool",
          "pad": "0x94085E08B91dA3cB974c14FE6d51B20a014b6069", "kind": "curve",
          "website": "https://x.example", "twitter": "https://x.com/bluechip", "telegram": "",
          "volume24Usd": 16_300.0, "timestamp": NOW - 3600}       # 1h old
# a thin young sub-bar coin
THIN = {"token": "0x0000000000000000000000000000000000000001", "symbol": "SPUD",
        "name": "Spud", "creator": "0xDef", "pool": "0xp2", "pad": "0x12A075A9",
        "kind": "direct", "website": "", "twitter": "", "telegram": "",
        "volume24Usd": 200.0, "timestamp": NOW - 3600}            # 1h old
# a placeholder test launch (real: the pad's test flow leaves these behind)
TESTTOK = {"token": "0x0000000000000000000000000000000000000002", "symbol": "TEST",
           "name": "test", "creator": "0xDef", "pool": "0xp3", "pad": "0x94085E08",
           "kind": "curve", "website": "https://potato.fm", "twitter": "", "telegram": "",
           "volume24Usd": 29_700.0, "timestamp": NOW - 3600}      # over the bar but a test
# a matured Ancient row (CASHCAT on the live board):
ANCIENT = {"address": "0x020bfc650a365f8bb26819deaabf3e21291018b4", "name": "Cash Cat",
           "symbol": "CASHCAT", "imageUrl": "ipfs://x", "tradePool": "0xa70f",
           "feeTier": 10000, "fdvUsd": 48_733_874.0, "volume24Usd": 5_184_857.0,
           "liquidityUsd": 4_176_923.0, "hasWethPool": True}


def test_identity_and_track_method(potato):
    # The non-obvious one: the price-source method is gmgn (potato coins are
    # gmgn-indexable V3 tokens), while the platform label is potato. A "potato"
    # method would file alerts that tracker/track.py can never price.
    assert potato.NAME == "potato"
    assert potato.PLATFORM == "potato"
    # track_dict passes the address through as-is (map_* already lower-cased it).
    assert potato.track_dict("0xabc") == {"method": "gmgn", "chainSlug": "robinhood", "address": "0xabc"}


def test_strong_young_coin_passes_bar(potato):
    assert potato.passes_bar(potato.map_growing(STRONG), _args(), NOW) is True


def test_thin_coin_fails_the_bar(potato):
    assert potato.passes_bar(potato.map_growing(THIN), _args(), NOW) is False


def test_test_token_never_passes_bar(potato):
    # over the volume bar and young, but a literal "test" placeholder — excluded.
    it = potato.map_growing(TESTTOK)
    assert it["vol24h"] >= 5_000.0                      # would clear a naive vol gate
    assert potato.is_test(it) is True
    assert potato.passes_bar(it, _args(), NOW) is False


def test_over_age_coin_fails_the_bar(potato):
    old = dict(STRONG, timestamp=NOW - 200 * 3600)      # 200h old, still over vol
    assert potato.passes_bar(potato.map_growing(old), _args(), NOW) is False


def test_score_separates_strong_from_thin(potato):
    assert potato.score_item(potato.map_growing(STRONG), 42) > potato.score_item(potato.map_growing(THIN), 42)


def test_map_growing_lowercases_address_and_reads_inline_socials(potato):
    it = potato.map_growing(STRONG)
    assert it["address"] == STRONG["token"].lower()
    # socials are inline on the Growing feed — no per-alert detail fetch needed.
    assert it["twitter"] == "https://x.com/bluechip"
    assert it["mcap"] is None and it["liq"] is None      # no per-token mcap on Growing


def test_map_ancient_reads_fdv_and_liquidity(potato):
    it = potato.map_ancient(ANCIENT)
    assert it["address"] == ANCIENT["address"]           # already lower-case
    assert it["mcap"] == 48_733_874.0                    # fdvUsd is the baseline mcap
    assert it["liq"] == 4_176_923.0


def test_early_record_has_no_baseline_grad_record_does(potato):
    # EARLY (Growing) has no t0 mcap -> mcap0 None (tracker uses earliest snapshot).
    early = potato.record_for(potato.map_growing(STRONG), "POTATO EARLY", 55)
    assert early["platform"] == "potato"
    assert early["mcap0"] is None
    assert early["track"]["method"] == "gmgn"
    # GRAD (Ancient) carries fdvUsd as a real return baseline.
    grad = potato.record_for(potato.map_ancient(ANCIENT), "POTATO GRAD", 60)
    assert grad["mcap0"] == 48_733_874.0
    assert grad["liq0"] == 4_176_923.0


def test_alert_body_is_labelled_potato_and_well_formed(potato):
    it = potato.map_growing(STRONG)
    score, body = potato.build_alert("🥔", "POTATO EARLY", 42, it, ["lead"], NOW)
    assert "🥔 potato" in body
    assert "POTATO EARLY" in body
    assert 0 <= score <= 100
