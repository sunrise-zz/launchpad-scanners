"""Operator-facing alert and AI-DD output contracts."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        (
            "PUMP GRADUATING",
            "73% fell below 40% of migration price within 20m",
        ),
        (
            "TRENCH GRAD",
            "post-grad is a timing pivot, not an all-clear",
        ),
        (
            "ARC LAUNCHED",
            "post-grad is a timing pivot, not an all-clear",
        ),
    ],
)
def test_graduation_alerts_warn_about_the_post_migration_window(
        alertfmt, tier, expected):
    message = alertfmt.compose(
        70, "🚀", tier, "COIN", "platform", "CHAIN",
        ["traction"], [], [], "https://example.test/coin")

    assert expected in message


def test_early_alert_does_not_claim_the_coin_has_migrated(alertfmt):
    message = alertfmt.compose(
        70, "🐣", "PUMP EARLY", "COIN", "platform", "SOLANA",
        ["traction"], [], [], "https://example.test/coin")

    assert "migration price" not in message
    assert "post-grad" not in message


def test_ai_dd_outputs_include_exit_discipline_note(analyst):
    alert = {
        "symbol": "COIN",
        "tier": "CONFIRMED",
        "platform": "pons.family",
        "token": "0x1234567890123456789012345678901234567890",
    }
    verdict = {
        "verdict": "BUY-WATCH",
        "conf": 80,
        "whys": ["verified traction"],
    }

    assert "30% trailing stop" in analyst.fmt_msg(alert, verdict)
    assert "30% trailing stop" in analyst.fmt_section(verdict)
