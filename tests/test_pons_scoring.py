"""Pins the Tier A behaviour of pons `score_confirmed` (shipped 2026-07-19).

Guards the three recalibrations from waves 21/24: the top1_share whale penalty,
the retiered cap_eff bands (with the dead >=0.1 tier removed), and log-scaled
rebuyers/net so conviction keeps paying past the old saturation caps.
"""
from __future__ import annotations

from conftest import PONS_DIED, PONS_WINNER


def score(pons, coin, *, dep_count=1, soc=None, paid=None, risk=None):
    return pons.score_confirmed(coin, dep_count, soc, paid, risk)


def test_winner_median_outscores_died_control_by_30_points(pons, make_coin):
    """The headline separation the Tier A recalibration was fit to produce."""
    winner = score(pons, make_coin(**PONS_WINNER))
    died = score(pons, make_coin(**PONS_DIED))

    assert winner - died >= 30, (
        f"winner-vs-died separation collapsed to {winner - died} points "
        f"(winner={winner}, died={died}); Tier A targets >=30"
    )


def test_whale_dominated_buys_score_below_distributed(pons, make_coin):
    """top1_share was the cleanest pons separator: winners 5.6%, died 62.8%.

    Only top_share differs, so the gap is the whale penalty alone.
    """
    distributed = score(pons, make_coin(**{**PONS_WINNER, "top_share": 0.056}))
    whale = score(pons, make_coin(**{**PONS_WINNER, "top_share": 0.60}))

    assert whale < distributed
    assert distributed - whale >= 10, (
        f"whale domination (top1 60%) only costs {distributed - whale} points; "
        "the >=50% penalty tier looks weakened or gone"
    )


def test_whale_penalty_is_monotonic_across_tiers(pons, make_coin):
    """Rising concentration must never score better than lower concentration."""
    scores = [score(pons, make_coin(**{**PONS_WINNER, "top_share": ts}))
              for ts in (0.05, 0.25, 0.35, 0.60)]

    assert scores == sorted(scores, reverse=True), (
        f"whale penalty is not monotonic across top1_share tiers: {scores}"
    )


def test_winner_median_cap_eff_beats_the_deleted_high_tier(pons, make_coin):
    """Regression guard on the dead tier.

    0/22 winners ever reached cap_eff >= 0.1, so a bonus tier up there would be
    rewarding a band no winner occupies. Scoring the winner median (0.031) at or
    above 0.15 is what makes that tier unable to silently return.

    Only `n_buys` varies, so buy_weth / net / top_share / rebuyers are all held
    constant. `n_buys` also feeds the buys/sells ratio, but 242/10 and 50/10
    both land in the same `>= 3` bucket, so cap_eff is the only term that moves.
    """
    at_winner_median = make_coin(**{**PONS_WINNER, "n_buys": 242})   # 7.5/242 = 0.031
    at_dead_tier = make_coin(**{**PONS_WINNER, "n_buys": 50})        # 7.5/50  = 0.15

    assert at_winner_median.buy_weth / at_winner_median.n_buys < 0.05
    assert at_dead_tier.buy_weth / at_dead_tier.n_buys >= 0.1

    assert score(pons, at_winner_median) >= score(pons, at_dead_tier), (
        "cap_eff >= 0.1 is scoring above the winner median again — the dead "
        "high tier that 0/22 winners reached has returned"
    )


def test_cap_eff_below_died_median_is_penalised(pons, make_coin):
    """Died coins sat at cap_eff 0.005; that band must cost points, not merely
    miss the bonus.

    The winner-median band is worth +8 on its own, so only a sub-0.012 band that
    carries its own penalty can open a gap wider than that. Asserting just
    `starved < healthy` would still pass if the penalty were deleted.

    As above, both `n_buys` values keep the buys/sells ratio in the `>= 3` bucket.
    """
    healthy = score(pons, make_coin(**{**PONS_WINNER, "n_buys": 242}))    # 0.031
    starved = score(pons, make_coin(**{**PONS_WINNER, "n_buys": 1500}))   # 0.005

    assert healthy - starved >= 10, (
        f"died-territory cap_eff only costs {healthy - starved} points relative "
        "to the winner median — the sub-0.012 penalty looks deleted"
    )


def test_rebuyers_keep_paying_past_the_old_saturation_cap(pons, make_coin):
    """The old min(rebuyers-6, 6)*2 flatlined at 12; winners run to 300+."""
    twelve = score(pons, make_coin(**{**PONS_WINNER, "rebuyers": 12}))
    three_hundred = score(pons, make_coin(**{**PONS_WINNER, "rebuyers": 300}))

    assert three_hundred > twelve, (
        "a 300-rebuyer coin no longer outscores a 12-rebuyer one — the rebuyer "
        "term has re-saturated"
    )


def test_net_eth_keeps_paying_past_the_old_saturation_cap(pons, make_coin):
    """Same reasoning: the old `min(net - 1, 4) * 2` flatlined at 5Ξ net, and
    winner p75 is 17.8Ξ.

    Both profiles sit *above* that old saturation point, so the old formula
    would score them identically — comparing 4Ξ against 60Ξ would not catch a
    revert, because 4Ξ is still on the old ramp.

    `n_buys` scales with `buy_weth` so cap_eff stays at the winner median and
    net ETH is the only term moving.
    """
    six = score(pons, make_coin(**{**PONS_WINNER, "buy_weth": 6.5,
                                   "sell_weth": 0.5, "n_buys": 210}))
    sixty = score(pons, make_coin(**{**PONS_WINNER, "buy_weth": 60.5,
                                     "sell_weth": 0.5, "n_buys": 1952}))

    assert sixty > six, (
        "net ETH stopped paying above 5Ξ — the old saturating cap is back"
    )


def test_dev_sold_and_serial_deployer_are_penalised(pons, make_coin):
    """Direction check on the two hard negatives, unchanged by Tier A."""
    clean = make_coin(**PONS_WINNER)
    baseline = score(pons, clean)

    assert score(pons, make_coin(**{**PONS_WINNER, "dev_sold": True})) < baseline
    assert score(pons, clean, dep_count=3) < baseline


def test_score_stays_within_the_clamp(pons, make_coin):
    """Every profile must land in the 5-99 display range the alert format assumes."""
    profiles = [
        PONS_WINNER,
        PONS_DIED,
        {**PONS_WINNER, "rebuyers": 400, "buy_weth": 200.0, "smart_score": 50},
        {**PONS_DIED, "snipers": 20, "dev_sold": True, "top_share": 0.99},
    ]
    for profile in profiles:
        s = score(pons, make_coin(**profile))
        assert 5 <= s <= 99
        assert isinstance(s, int)
