"""Raw launch-time features travel from the TokenLaunched event onto the alert row.

Scores are opinions and get refit (#10); these are the measurements the refit is
fit on, so they must survive the whole path — event -> CoinState -> alert record
-> alerts.jsonl — without being rescaled or dropped.

The pattern pinned here is the one flap/pump/virtuals mirror in #7.
"""
from __future__ import annotations

import json
import os

import pytest


@pytest.fixture
def outcomes(tmp_path, monkeypatch):
    """Load outcomes.py with its append path pointed at a temp file."""
    import importlib.util
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "pons_outcomes", os.path.join(root, "pons", "outcomes.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pons_outcomes"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "TRACK_DIR", str(tmp_path))
    monkeypatch.setattr(mod, "ALERTS", str(tmp_path / "alerts.jsonl"))
    return mod


def _rows(outcomes):
    with open(outcomes.ALERTS) as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


BASE = dict(platform="pons.family", chain="ROBINHOOD", tier="CONFIRMED",
            symbol="TEST", token="0x" + "1" * 40, score=70, track={}, gmgn=False)


# --- record_alert accepts the features dict ---------------------------------

def test_record_alert_persists_the_features_dict(outcomes):
    """Regression: alert_pro has passed f=dict(...) since ab4a8f2 while
    record_alert had no such parameter — every pons CONFIRMED alert raised
    TypeError *after* the Telegram send, so the alert went out but no outcome
    row was ever written. 0 of 1305 accumulated rows carry `f`."""
    outcomes.record_alert(**BASE, features=dict(rebuyers=7, net_weth=1.4))
    assert _rows(outcomes)[0]["f"] == {"rebuyers": 7, "net_weth": 1.4}


def test_rows_without_features_stay_shaped_as_before(outcomes):
    """tracker/report.py reads a year of old rows — an always-present `f` key
    (even empty) would change what those tools see."""
    outcomes.record_alert(**BASE)
    assert "f" not in _rows(outcomes)[0]


def test_a_failing_features_dict_never_costs_us_the_alert_row(outcomes):
    """record_alert is best-effort by contract; the outcome row matters more
    than any one field in it."""
    outcomes.record_alert(**BASE, features={"unserializable": {1, 2}})
    rows = _rows(outcomes)
    assert len(rows) == 1 and rows[0]["token"] == BASE["token"]


# --- the pons feature dict --------------------------------------------------

def test_launch_event_measurements_reach_the_feature_dict(pons, make_coin):
    """initialBuyAmount and restrictionsEndBlock are the two new measurements
    from TokenLaunched — carried, never scored (research: dev initial-buy size
    predicts graduation, but it earns weight only after the refit measures it)."""
    c = make_coin(n_buys=100, buy_weth=5.0, rebuyers=10)
    c.initial_buy_wei = 67782880000000000
    c.restrictions_end_block = 25565840

    f = pons.launch_features(c, dep_launches=3)
    assert f["initial_buy_wei"] == 67782880000000000
    assert f["restrictions_end_block"] == 25565840


def test_features_are_raw_measurements_not_scores(pons, make_coin):
    c = make_coin(n_buys=100, buy_weth=5.0, rebuyers=10)
    f = pons.launch_features(c, dep_launches=3)
    assert not [k for k in f if "score" in k and k != "smart_score"], (
        "a derived score in the feature dict invalidates accumulated history "
        "the moment the formula changes"
    )
    assert f["n_buys"] == 100 and f["rebuyers"] == 10


def test_features_survive_a_coin_discovered_without_the_new_fields(pons, make_coin):
    """A coin registered over the legacy HTTP source has no event fields. That
    must log as absent, not crash the alert."""
    c = make_coin(n_buys=100, buy_weth=5.0, rebuyers=10)
    f = pons.launch_features(c, dep_launches=1)
    assert f["initial_buy_wei"] is None
    assert f["restrictions_end_block"] is None


def test_zero_dev_buy_is_recorded_as_zero_not_missing(pons, make_coin):
    """A dev who bought nothing is a real signal, distinct from 'we don't know'."""
    c = make_coin(n_buys=100, buy_weth=5.0, rebuyers=10)
    c.initial_buy_wei = 0
    assert pons.launch_features(c, dep_launches=1)["initial_buy_wei"] == 0


def test_features_are_json_serialisable(pons, make_coin):
    """They are written straight into alerts.jsonl."""
    c = make_coin(n_buys=100, buy_weth=5.0, rebuyers=10, top_share=0.2)
    c.initial_buy_wei, c.restrictions_end_block = 5, 6
    assert json.loads(json.dumps(pons.launch_features(c, dep_launches=2)))


# --- pool ordering from the event ------------------------------------------

def test_coin_state_orders_the_pool_by_the_event_pair_token(pons):
    """Ordering must follow the launch event's pairToken, not an assumed WETH."""
    low = "0x" + "0" * 39 + "1"
    high = "0x" + "f" * 40
    mk = lambda pair: pons.CoinState(                       # noqa: E731
        token="0x" + "8" * 40, pool="0x" + "2" * 40, launch_block=1,
        deployer="0x" + "3" * 40, symbol="T", launched_at=0, pair_token=pair)
    assert mk(high).token_is_0 is True
    assert mk(low).token_is_0 is False


def test_pool_ordering_falls_back_to_weth_when_the_pair_is_unknown(pons):
    """Legacy HTTP records carry no pairToken; the old WETH assumption stands."""
    c = pons.CoinState(token="0x" + "8" * 40, pool="0x" + "2" * 40, launch_block=1,
                       deployer="0x" + "3" * 40, symbol="T", launched_at=0)
    assert c.token_is_0 is ("0x" + "8" * 40 < pons.WETH)
