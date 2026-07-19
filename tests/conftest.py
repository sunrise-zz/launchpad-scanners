"""Shared loaders and profile builders for the scoring tests.

The scanners are standalone scripts, not an installed package, and three of them
are named `scan.py` — so they are loaded by path under unique module names
rather than imported. Each one does its own `sys.path` juggling at import time
to reach `pons/` and `vlad/`, which works unchanged here.

Profiles come from the measured medians in docs/research-notes-raw.md (waves
21/24 for pons, 20/23 for pump, 20/22 for virtuals). Tests assert separation
and direction only — never an exact score — because the weights are provisional
until the Tier B refit.
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Don't leave __pycache__ in the scanner directories. Bytecode caches are keyed
# on (source mtime, source size), so an edit that preserves both — which is easy
# when tweaking a single digit in a weight — can leave a test run reading stale
# bytecode and scoring the *previous* version of the function.
sys.dont_write_bytecode = True


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, relpath))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def pons():
    return _load("pons_alert_pro", "pons/alert_pro.py")


@pytest.fixture(scope="session")
def pump():
    return _load("pump_scan", "pump/scan.py")


@pytest.fixture(scope="session")
def virtuals():
    return _load("virtuals_scan", "virtuals/scan.py")


@pytest.fixture(scope="session")
def alertfmt():
    return _load("pons_alertfmt", "pons/alertfmt.py")


@pytest.fixture
def make_coin(pons):
    """Build a real CoinState with the swap-derived state a scored coin would have.

    Uses the production class (not a stub) so `rebuyers`, `net_weth` and
    `top_share` stay the real computed properties. Buy volume is split so the
    largest single buyer holds exactly `top_share` of it.
    """

    def _make(*, n_buys, buy_weth, n_sells=0, sell_weth=0.0, rebuyers=0,
              top_share=0.05, smart_score=0, snipers=0, dev_sold=False):
        c = pons.CoinState(
            token="0x" + "1" * 40, pool="0x" + "2" * 40, launch_block=1000,
            deployer="0x" + "3" * 40, symbol="TEST", launched_at=0,
        )
        c.n_buys, c.buy_weth = n_buys, buy_weth
        c.n_sells, c.sell_weth = n_sells, sell_weth

        whale_weth = buy_weth * top_share
        rest = buy_weth - whale_weth
        # Spread the remainder over enough co-buyers that none of them
        # individually outsizes the whale — otherwise `top_share` is silently
        # not what was asked for. Splitting 94.4% between 6 co-buyers makes each
        # of them the top buyer at 15.7%, and a test meaning to hold
        # concentration constant would drift across a penalty tier instead.
        min_others = math.ceil(rest / whale_weth) + 1 if whale_weth > 0 else 1
        others = max(rebuyers, min_others, 1)

        c.buyers["0x" + "a" * 40] = whale_weth
        for i in range(others):
            c.buyers["0x%040d" % i] = rest / others
        for i in range(rebuyers):
            c.rebuy["0x%040d" % i] = 2      # >=2 buys is what makes a rebuyer

        c.smart_score, c.snipers, c.dev_sold = smart_score, snipers, dev_sold

        assert c.rebuyers == rebuyers, "builder did not produce the requested rebuyers"
        if buy_weth > 0:
            assert abs(c.top_share - top_share) < 1e-9, (
                f"builder produced top_share {c.top_share:.4f}, asked for {top_share:.4f}"
            )
        return c

    return _make


# --- pons: measured launch-time medians (waves 21/24) -----------------------
# winner: top1 5.6%, cap_eff 0.031 (7.5Ξ / 242 buys), 25 rebuyers, net 7.0Ξ
# died:   top1 62.8%, cap_eff 0.005 (1.2Ξ / 240 buys), bar-minimum conviction
PONS_WINNER = dict(n_buys=242, buy_weth=7.5, n_sells=10, sell_weth=0.5,
                   rebuyers=25, top_share=0.056)
PONS_DIED = dict(n_buys=240, buy_weth=1.2, n_sells=120, sell_weth=0.2,
                 rebuyers=6, top_share=0.628)
