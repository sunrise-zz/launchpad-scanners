"""Pins the Tier A social reweighting in pump `score_coin` (shipped 2026-07-19).

Waves 20/23 (n=66 graduated vs 30 died) found twitter is table-stakes noise
(77% grad vs 60% died) while telegram (44% vs 13%) and website (74% vs 37%)
actually separate. Twitter dropped +5 -> +1 to encode that.
"""
from __future__ import annotations

import pytest

# Mid-range inputs: high enough to be a plausible EARLY alert, far enough from
# the 5-99 clamp that social deltas are not compressed at either end.
BASE = dict(c=None, mcap=30_000.0, replies=10, ath=None, koth=False,
            nsfw=False, vel=0.0)

TWITTER = "https://twitter.com/acoin"
WEBSITE = "https://acoin.io"
TELEGRAM = "https://t.me/acoin"


def test_telegram_and_website_outscore_twitter_only(pump):
    tg_web = pump.score_coin(**BASE, tg=TELEGRAM, web=WEBSITE, twitter=None)
    twitter_only = pump.score_coin(**BASE, tg=None, web=None, twitter=TWITTER)

    assert tg_web - twitter_only >= 10, (
        f"TG+website only beats twitter-only by {tg_web - twitter_only} points; "
        "the real separators have lost their weight"
    )


def test_twitter_only_is_near_indistinguishable_from_no_socials(pump):
    """Twitter is a faint tiebreak, not a signal — that is the whole finding.

    The ~1-point tolerance is the one magnitude issue #2 pins deliberately
    ("twitter-only ≈ no-socials (within ~1 point)"); a refit that gives twitter
    real weight again is meant to fail here.
    """
    twitter_only = pump.score_coin(**BASE, tg=None, web=None, twitter=TWITTER)
    no_socials = pump.score_coin(**BASE, tg=None, web=None, twitter=None)

    assert abs(twitter_only - no_socials) <= 1, (
        f"twitter is worth {twitter_only - no_socials} points again; wave 20/23 "
        "measured it as table-stakes noise (77% grad vs 60% died)"
    )


@pytest.mark.parametrize("channel,value", [("tg", TELEGRAM), ("web", WEBSITE)])
def test_each_real_separator_outweighs_twitter(pump, channel, value):
    none_set = {"tg": None, "web": None, "twitter": None}
    with_channel = pump.score_coin(**BASE, **{**none_set, channel: value})
    twitter_only = pump.score_coin(**BASE, **{**none_set, "twitter": TWITTER})

    assert with_channel > twitter_only


def test_graduating_base_outranks_early_base(pump):
    early = pump.score_coin(**BASE, tg=None, web=None, twitter=None, grad=False)
    grad = pump.score_coin(**BASE, tg=None, web=None, twitter=None, grad=True)

    assert grad > early


def test_dumping_from_ath_scores_below_holding_near_ath(pump):
    """Direction check on the climb-quality term, unchanged by Tier A."""
    inputs = dict(BASE, tg=None, web=None, twitter=None)
    near_ath = pump.score_coin(**{**inputs, "mcap": 30_000.0, "ath": 31_000.0})
    dumped = pump.score_coin(**{**inputs, "mcap": 30_000.0, "ath": 90_000.0})

    assert dumped < near_ath


def test_organic_quality_penalties_lower_the_score(pump):
    """GMGN overlay: coordinated supply must cost points, smart money must pay."""
    inputs = dict(BASE, tg=TELEGRAM, web=WEBSITE, twitter=None)
    clean = pump.score_coin(**inputs, g=None)
    bundled = pump.score_coin(**inputs, g={"bundler_rate": 0.5})
    ratted = pump.score_coin(**inputs, g={"rat_rate": 0.3})
    smart = pump.score_coin(**inputs, g={"smart": 5, "renowned": 3})

    assert bundled < clean
    assert ratted < clean
    assert smart > clean


def test_score_stays_within_the_clamp(pump):
    floor = pump.score_coin(c=None, mcap=0.0, replies=0, ath=100_000.0, koth=False,
                            nsfw=True, vel=-5000.0, tg=None, web=None, twitter=None,
                            g={"bundler_rate": 0.9, "rat_rate": 0.9,
                               "sniper70_rate": 0.9, "bot_rate": 0.9})
    ceiling = pump.score_coin(c=None, mcap=200_000.0, replies=500, ath=200_000.0,
                              koth=True, nsfw=False, vel=50_000.0, grad=True,
                              tg=TELEGRAM, web=WEBSITE, twitter=TWITTER,
                              g={"smart": 10, "renowned": 10})

    # No `floor < ceiling` assertion — both land on a clamp bound, so it would
    # only be restating 5 < 99.
    assert 5 <= floor <= 99
    assert 5 <= ceiling <= 99
