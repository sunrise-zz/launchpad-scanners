"""noxa scanner — identity, the graduationPct trap, and score direction.

noxa/ is a source-level scanner over noxa.fi, not a GMGN trench rider, so it
carries its own map_row / passes_bar / score_item. These tests pin the things
that would fail silently: an EARLY bar that gates on graduationPct (which would
reject the strongest coins on the board), a control row with no measurable
baseline, and scores that don't separate a strong coin from a thin one.

Direction and separation only, never exact score values — the weights are
provisional until the Tier B refit, same rule as the rest of tests/.
"""
import os
import sys
import types

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def noxa():
    import importlib.util
    sys.path.insert(0, os.path.join(ROOT, "pons"))
    spec = importlib.util.spec_from_file_location("noxa_scan", os.path.join(ROOT, "noxa", "scan.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["noxa_scan"] = mod
    spec.loader.exec_module(mod)
    return mod


def _args(**kw):
    base = dict(max_age_h=24.0, min_holders=60, min_vol=15_000.0, min_progress=0.0)
    base.update(kw)
    return types.SimpleNamespace(**base)


# a real strong pre-grad coin from the live board (noxacat, 2026-07-22):
STRONG = {"token": "0x0000000000000000000000000000000000004663", "symbol": "STRONG",
          "holderCount": 709, "volume24hUsd": 161_000.0, "trades24h": "3082",
          "marketCapUsd": 6020.0, "priceUsd": 6.0e-6, "graduationPct": 14.9,
          "changePct5m": 5.0, "createdTs": 1, "graduated": False, "deployer": "0xabc"}
# a thin sub-bar coin
THIN = {"token": "0x0000000000000000000000000000000000114663", "symbol": "THIN",
        "holderCount": 5, "volume24hUsd": 200.0, "trades24h": "6",
        "marketCapUsd": 300.0, "priceUsd": 1e-8, "graduationPct": 6.8,
        "changePct5m": 0.0, "createdTs": 1, "graduated": False, "deployer": "0xdef"}


def test_identity_and_track_method(noxa):
    # platform label, tracker platform and price-source method must all read
    # "noxa" — a mismatch would file alerts under the wrong platform or leave
    # them unpriceable (V2 is invisible to gmgn+dexscreener; only snap_noxa works).
    assert noxa.NAME == "noxa"
    assert noxa.PLATFORM == "noxa"
    assert noxa.track_dict("0xabc") == {"method": "noxa", "chainSlug": "robinhood", "address": "0xabc"}


def test_bar_does_not_gate_on_graduationpct(noxa):
    # The whole point of the graduationPct trap: the strongest coin on the board
    # reads ~15% "progress", so a progress gate would silently reject it. With
    # the shipped bar (holders+vol only) it must pass.
    now = 1_000_000_000
    it = noxa.map_row(STRONG)
    assert it["progress"] < 0.30            # would fail a naive progress>=0.30 gate
    assert noxa.passes_bar(it, _args(), now) is True


def test_thin_coin_fails_the_bar(noxa):
    now = 1_000_000_000
    assert noxa.passes_bar(noxa.map_row(THIN), _args(), now) is False


def test_min_progress_stays_available_as_optin_gate(noxa):
    # Off by default, but still wired: an operator can re-impose it.
    now = 1_000_000_000
    it = noxa.map_row(STRONG)
    assert noxa.passes_bar(it, _args(min_progress=0.30), now) is False


def test_score_separates_strong_from_thin(noxa):
    # Direction only. Strong traction must outscore a thin coin off the same base.
    assert noxa.score_item(noxa.map_row(STRONG), 42) > noxa.score_item(noxa.map_row(THIN), 42)


def test_map_row_coerces_string_trades(noxa):
    # trades24h comes back a string from /tokens/{addr}; a raw compare would blow
    # up or mis-sort. map_row must yield a number.
    assert noxa.map_row(STRONG)["trades24h"] == 3082.0
    assert isinstance(noxa.map_row(STRONG)["trades24h"], float)


def test_map_row_lowercases_address(noxa):
    r = dict(STRONG, token="0xAbC0000000000000000000000000000000004663")
    assert noxa.map_row(r)["address"] == "0xabc0000000000000000000000000000000004663"


def test_alert_body_is_labelled_noxa_and_well_formed(noxa):
    now = 1_000_000_000
    it = noxa.map_row(STRONG)
    score, body = noxa.build_alert("🐣", "NOXA EARLY", 42, it, ["lead"], now)
    assert "🌀 noxa" in body
    assert "NOXA EARLY" in body
    assert 0 <= score <= 100


def test_record_for_carries_measurable_baseline(noxa):
    # mcap0 is the tracker's return baseline; it must be the coin's real mcap,
    # not None/0, or report.py can't compute a return for the alert.
    rec = noxa.record_for(noxa.map_row(STRONG), "NOXA EARLY", 55)
    assert rec["platform"] == "noxa"
    assert rec["mcap0"] == 6020.0
    assert rec["track"]["method"] == "noxa"
