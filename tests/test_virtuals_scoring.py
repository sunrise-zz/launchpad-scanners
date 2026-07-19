"""Pins the Tier A recalibration of virtuals `score_agent` (shipped 2026-07-19).

Wave 22 compared 69 graduated agents against a real died-control of 346 on-curve
agents older than 48h. Socials were the strongest separator found on any of our
platforms (96% grad vs 2% died), so they became a near-gate rather than a
per-channel bonus. The old top10 penalty was deleted because graduated agents
natively sit around 72% top10 — it was penalising winners.
"""
from __future__ import annotations

import pytest

EARLY_BASE, NEAR_GRAD_BASE = 45, 40
ALERT_WORTHY = ("🟡", "🟢")     # bands a reader is meant to act on

# Every non-social field at its rewarded value, so the near-gate is tested
# against the strongest agent that could otherwise exist.
STRONG_FIELDS = {
    "mindshare": 5.0,
    "holderCountPercent24h": 20.0,
    "volume24h": 50_000.0,
    "devHoldingPercentage": 5.0,
    "top10HolderPercentage": 72.0,       # platform-native for graduated agents
}
FULL_SOCIALS = {"TWITTER": "https://x.com/a", "TELEGRAM": "https://t.me/a",
                "WEBSITE": "https://a.io"}


def agent(**overrides):
    return {**STRONG_FIELDS, "socials": {}, **overrides}


def test_no_socials_stays_below_the_alert_worthy_bands(virtuals, alertfmt):
    """The near-gate: strong traction cannot carry a socials-less agent into 🟡."""
    for tier_base, progress in ((EARLY_BASE, 0), (NEAR_GRAD_BASE, 100)):
        s = virtuals.score_agent(agent(), tier_base, progress)
        assert alertfmt.band(s) not in ALERT_WORTHY, (
            f"socials-less agent scored {s} ({alertfmt.band(s)}) at tier_base="
            f"{tier_base}; the -20 near-gate no longer holds"
        )


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN GAP — tracked in issue #13. The -20 near-gate loses to the two "
    "launch flags: isVerified (+10) and isDevCommitted (+10) on top of base 45 "
    "and 22 points of strong traction fields put a socials-less agent at 67 "
    "(EARLY) / 74 (NEAR-GRAD), i.e. 🟡. A single flag is enough at NEAR-GRAD "
    "(64). Wave 22 saw neither flag on any of the 346 died agents, so this "
    "combination is unobserved rather than merely rare — which is why it "
    "survived the Tier A recalibration. Fixing it means reweighting live "
    "scoring, which is a scoring change, not a test change: decide it with the "
    "Tier B refit. Remove this marker when the gate is made absolute."))
def test_no_socials_stays_below_alert_worthy_bands_even_with_launch_flags(
        virtuals, alertfmt):
    """The near-gate as issue #2 actually specifies it: 'even with good other fields'."""
    best = agent(isVerified=True, isDevCommitted=True)
    for tier_base, progress in ((EARLY_BASE, 0), (NEAR_GRAD_BASE, 100)):
        s = virtuals.score_agent(best, tier_base, progress)
        assert alertfmt.band(s) not in ALERT_WORTHY, (
            f"socials-less agent scored {s} ({alertfmt.band(s)})"
        )


def test_no_socials_never_reaches_the_top_band(virtuals, alertfmt):
    """The part of the near-gate that does hold absolutely, flags included.

    Weaker than the criterion above on purpose — this is the guarantee the
    current weights actually provide, so it is the one that guards regressions.
    """
    best = agent(isVerified=True, isDevCommitted=True)
    for tier_base, progress in ((EARLY_BASE, 0), (NEAR_GRAD_BASE, 100)):
        s = virtuals.score_agent(best, tier_base, progress)
        assert alertfmt.band(s) != "🟢", (
            f"socials-less agent reached the top band at {s}; the near-gate is gone"
        )


def test_socials_swing_outweighs_every_other_field(virtuals):
    """+12 with, -20 without: the single largest term in the function."""
    without = virtuals.score_agent(agent(), EARLY_BASE, 0)
    with_socials = virtuals.score_agent(agent(socials=FULL_SOCIALS), EARLY_BASE, 0)

    assert with_socials - without >= 30, (
        f"socials are only worth {with_socials - without} points; wave 22 "
        "measured 96% grad vs 2% died"
    )


def test_more_social_channels_never_score_lower(virtuals):
    one = virtuals.score_agent(agent(socials={"TWITTER": "https://x.com/a"}), EARLY_BASE, 0)
    two = virtuals.score_agent(agent(socials={"TWITTER": "https://x.com/a",
                                              "TELEGRAM": "https://t.me/a"}), EARLY_BASE, 0)
    three = virtuals.score_agent(agent(socials=FULL_SOCIALS), EARLY_BASE, 0)

    assert one <= two <= three


@pytest.mark.parametrize("top10", [30.0, 72.0, 85.0, 95.0])
def test_top10_concentration_is_deliberately_unscored(virtuals, top10):
    """Graduated agents natively sit ~72% top10, so any penalty hits winners."""
    baseline = virtuals.score_agent(
        agent(socials=FULL_SOCIALS, top10HolderPercentage=72.0), EARLY_BASE, 0)
    varied = virtuals.score_agent(
        agent(socials=FULL_SOCIALS, top10HolderPercentage=top10), EARLY_BASE, 0)

    assert varied == baseline, (
        f"top10={top10}% changed the score to {varied} (baseline {baseline}); "
        "the deleted concentration penalty has returned"
    )


def test_anti_sniper_tax_is_deliberately_unscored(virtuals):
    """13% grad vs 98% died is a temporal confound — it dates a coin, not its quality.

    The field is `launchInfo.antiSniperTaxType` (see virtuals/README.md); the
    record has to carry it under the real name or a re-added penalty would read
    a key this test never set and the guard would pass regardless.
    """
    baseline = virtuals.score_agent(agent(socials=FULL_SOCIALS), EARLY_BASE, 0)
    taxed = virtuals.score_agent(
        agent(socials=FULL_SOCIALS,
              launchInfo={"antiSniperTaxType": "PERCENTAGE", "antiSniperTax": 99}),
        EARLY_BASE, 0)

    assert taxed == baseline


@pytest.mark.parametrize("flag", ["isVerified", "isDevCommitted"])
def test_zero_false_positive_launch_flags_are_rewarded(virtuals, flag):
    baseline = virtuals.score_agent(agent(socials=FULL_SOCIALS), EARLY_BASE, 0)
    flagged = virtuals.score_agent(agent(socials=FULL_SOCIALS, **{flag: True}), EARLY_BASE, 0)

    assert flagged > baseline


def test_dev_holdings_are_rewarded_low_and_penalised_high(virtuals):
    """Three bands: <10 rewarded, 10-15 neutral, >=15 penalised.

    The neutral middle band is the reference that makes this a penalty test
    rather than an absence-of-bonus test — `high < low` alone would still pass
    if the >=15 penalty were deleted.
    """
    def at(dev):
        return virtuals.score_agent(
            agent(socials=FULL_SOCIALS, devHoldingPercentage=dev), EARLY_BASE, 0)

    assert at(5.0) > at(12.0), "low dev holdings stopped being rewarded"
    assert at(20.0) < at(12.0), "high dev holdings stopped being penalised"


def test_near_grad_ramp_rewards_progress_only_on_the_near_grad_tier(virtuals):
    r = agent(socials=FULL_SOCIALS)

    assert (virtuals.score_agent(r, NEAR_GRAD_BASE, 95)
            > virtuals.score_agent(r, NEAR_GRAD_BASE, 70))
    # EARLY has no ramp — progress must not move its score
    assert (virtuals.score_agent(r, EARLY_BASE, 95)
            == virtuals.score_agent(r, EARLY_BASE, 0))


def test_string_and_missing_fields_do_not_crash(virtuals):
    """The API hands back strings and nulls; fnum must absorb both (round-2 fix)."""
    messy = {"socials": FULL_SOCIALS, "mindshare": "5.0", "volume24h": None,
             "devHoldingPercentage": "not-a-number", "holderCountPercent24h": ""}

    s = virtuals.score_agent(messy, EARLY_BASE, 0)
    assert 5 <= s <= 99


def test_score_stays_within_the_clamp(virtuals):
    floor = virtuals.score_agent(
        {"socials": {}, "devHoldingPercentage": 90.0}, NEAR_GRAD_BASE, 0)
    ceiling = virtuals.score_agent(
        agent(socials=FULL_SOCIALS, isVerified=True, isDevCommitted=True),
        NEAR_GRAD_BASE, 100)

    assert 5 <= floor <= 99
    assert 5 <= ceiling <= 99
    assert floor < ceiling
