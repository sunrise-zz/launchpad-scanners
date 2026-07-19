"""Shared alert-outcome recorder.

Every scanner calls record_alert() when it fires, appending one row to
tracker/data/alerts.jsonl. A separate daemon (tracker/track.py) then follows
each coin's price/mcap/liquidity over time so we can measure — after the fact —
whether the score actually predicted anything, and refit the weights.

The `track` dict tells the daemon HOW to fetch the coin's live metrics later:
    {"method": "dexscreener", "chainSlug": "robinhood"|"base"|"solana", "address": "0x…"}
    {"method": "arc", "address": "0x…"}
    {"method": "virtuals", "id": 12345}

When a GMGN API key is configured (see pons/gmgn.py), each row is also
enriched with row["gmgn"] — GMGN's alert-time forensics (smart-money tags,
bot/bundler rates, dev reputation, …). Collected, not gated: report.py will
tell us which fields predict returns before any earns score weight.
"""
from __future__ import annotations

import json
import os
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_DIR = os.path.join(REPO, "tracker", "data")
ALERTS = os.path.join(TRACK_DIR, "alerts.jsonl")
CONTROLS = os.path.join(TRACK_DIR, "controls.jsonl")


def num(x):
    """Coerce a feed value to a number, preserving "not measured" as None.

    This is the deliberate inverse of the coercion every scanner uses for
    *scoring* — `fnum(r, k)`, `c.get(k) or 0`, `float(x or 0)` — which folds a
    missing field into 0 so it simply earns no points. Right for a score,
    wrong for a training row: the refit (#10) cannot tell a fabricated 0 from a
    measured one, so an absent field logged as 0 drags its coefficient toward
    zero on data that was never collected.

    None, empty string and unparseable text all mean "not measured". A real 0
    — zero tax, zero replies, zero dev holdings — survives as 0.
    """
    if x is None or x == "":
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):   # not measurements
        return None
    return int(v) if v.is_integer() else v


def record_alert(platform, chain, tier, symbol, token, score, track,
                 price0=None, mcap0=None, liq0=None, gmgn=None, tg=None, features=None):
    """Append one alert row. Best-effort — never raises into the scanner loop.

    `gmgn`: pass a prefetched pons/gmgn.py snapshot to avoid a duplicate API
    call (alert_pro does); leave None to auto-fetch here (runs post-send, so
    the ≤8s timeout never delays the Telegram alert itself).
    `tg`: {"msg_id", "text", "buttons"} of the sent Telegram message — lets
    agent/analyst.py append its AI verdict INTO that message (edit-in-place)
    instead of posting a separate follow-up that gets visually orphaned.
    `features`: raw launch-time measurements (never scores) for the refit to
    fit on. Stored under row["f"], the same short key backtest_multifactor.py
    already uses for a feature dict. Omitted when absent, so old rows and new
    ones read alike.

    These were passed by alert_pro as f=… from ab4a8f2 before any such
    parameter existed, so every pons CONFIRMED alert raised TypeError here —
    after the Telegram send, which left the alert delivered but untracked. Keep
    this signature and alert_pro's record dict in step."""
    row = {
        "t": time.time(),
        "platform": platform,
        "chain": chain,
        "tier": tier,
        "symbol": symbol,
        "token": token,
        "score": score,
        "track": track,
        "price0": price0,
        "mcap0": mcap0,
        "liq0": liq0,
    }
    if tg and tg.get("msg_id"):
        row["tg"] = tg
    return _enrich_and_append(ALERTS, row, gmgn, features)


def _enrich_and_append(path, row, gmgn, features):
    """Enrich a row with GMGN + features and append it. Best-effort throughout.

    Shared by record_alert and record_control deliberately: a case and its
    controls have to be measured with the same instruments, or every
    GMGN-derived field separates the two groups perfectly and the refit learns
    "we had smart-money data on it" as a predictor of being alerted. That is
    circular, and it is the exact failure #9 exists to prevent — so the
    enrichment lives in one place that neither recorder can drift away from.

    The chain/track/token the GMGN lookup needs are read back off `row`, which
    already carries all three — passing them alongside it would be the same
    three values travelling in two forms, free to disagree.
    """
    if gmgn is None:
        try:
            import gmgn as _gmgn   # sibling module; every scanner has pons/ on sys.path
            gchain, addr = _gmgn.chain_addr_for(row["chain"], row["track"], row["token"])
            if gchain:
                gmgn = _gmgn.snapshot(gchain, addr)
        except Exception:  # noqa: BLE001
            gmgn = None
    if gmgn:
        row["gmgn"] = gmgn
    if features:
        try:
            json.dumps(features)   # one bad field must not cost us the whole row
            row["f"] = features
        except (TypeError, ValueError):
            pass
    try:
        os.makedirs(TRACK_DIR, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:  # noqa: BLE001
        pass
    return row


def record_control(platform, chain, symbol, token, track, tier="CONTROL",
                   price0=None, mcap0=None, liq0=None, gmgn=None, features=None):
    """Append one shadow-control row — a launch we saw and did NOT alert on.

    Same columns as record_alert so tracker/track.py samples it on the same
    horizon cadence and report.py's baseline()/ret_at() read it unchanged. Two
    deliberate differences:

      * It lands in controls.jsonl, never alerts.jsonl. Every reader of
        alerts.jsonl — report.py, agent/daily_brief.py, recent_same_symbol —
        treats a row there as a coin we alerted on, and none of them can be
        asked to think otherwise without being changed. The file split makes
        them correct by construction instead of by vigilance. (Before #9 the
        flap SHADOW rows *were* in alerts.jsonl, where they inflated the alert
        count 30%, pooled with real alerts in every per-platform median, and
        counted toward the relaunch-farm threshold that suppresses live
        alerts.)
      * No score and no tg. A control was never scored and never sent; a 0
        would read as a measurement, and see num() on why that matters.

    `tier` defaults to CONTROL, the uniformly-sampled group that is a true base
    rate. Pass something else only for a *targeted* control experiment — flap's
    SHADOW tiers sample coins that already cleared 60 recipients, to ask
    whether the EARLY bar should come down. Both belong out of the alert
    population, but only CONTROL rows are a base rate, and report.py's
    base_rate_controls() is what keeps them from being pooled.

    Best-effort — never raises into a scan loop."""
    now = time.time()
    row = {
        "t": now,
        "shadow": True,          # survives a row being copied out of its file
        # Explicit snapshot id. The derived one, "<t>:<token>", truncates to
        # whole seconds, and a scanner can sample a coin as a control and alert
        # the same coin in the same tick — flap runs sample_control at the top
        # of the loop that then alerts. Colliding ids would make the tracker
        # treat one row's horizons as already sampled, so the control would
        # silently show the alert's return: the base rate inheriting the
        # outcome it exists to be measured against.
        #
        # Stored rather than derived so the rows migrated out of
        # alerts.jsonl, which have no id, keep falling back to the computed one
        # and stay joined to the snapshots already taken for them.
        "id": f"{now:.0f}:{token}:c",
        "platform": platform,
        "chain": chain,
        "tier": tier,
        "symbol": symbol,
        "token": token,
        "score": None,
        "track": track,
        "price0": price0,
        "mcap0": mcap0,
        "liq0": liq0,
    }
    return _enrich_and_append(CONTROLS, row, gmgn, features)


SNAPS = os.path.join(TRACK_DIR, "snapshots.jsonl")


def peak_return(alert_row):
    """Max return vs the alert-time baseline across every horizon the tracker
    sampled for that alert. None when no usable data. Used to tell a relaunch
    FARM (every prior copy died instantly) from a NARRATIVE wave (a prior copy
    of this name already ran — the market proved demand). Cheap file scan;
    only called for the rare same-name candidates."""
    try:
        base = float(alert_row.get("price0") or alert_row.get("mcap0") or 0) or None
    except (TypeError, ValueError):
        base = None
    if base is None or not os.path.exists(SNAPS):
        return None
    metric = "price" if alert_row.get("price0") else "mcap"
    aid = f"{alert_row['t']:.0f}:{alert_row.get('token')}"
    best = None
    try:
        for ln in open(SNAPS):
            try:
                s = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if s.get("id") != aid:
                continue
            try:
                v = float(s.get(metric) or 0)
            except (TypeError, ValueError):
                continue
            if v > 0:
                r = v / base - 1
                best = r if best is None else max(best, r)
    except Exception:  # noqa: BLE001
        return None
    return best


def recent_same_symbol(platform, symbol, token, hours=24.0):
    """Prior alerts on `platform` carrying the SAME symbol but a DIFFERENT
    token address within `hours`. Detects relaunch farms: 2026-07-18 one
    operator deployed "RUDY" three times ~11 min apart, each copy crossing the
    flap traction bar with near-identical manufactured transfers (~130
    recipients each). Address-based dedup can't see that — the name can."""
    if not symbol or not os.path.exists(ALERTS):
        return []
    sym = str(symbol).strip().lower()
    tok = (token or "").lower()
    cutoff = time.time() - hours * 3600
    out = []
    try:
        for ln in open(ALERTS):
            try:
                r = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if (r.get("t", 0) >= cutoff and r.get("platform") == platform
                    and str(r.get("symbol") or "").strip().lower() == sym
                    and (r.get("token") or "").lower() != tok):
                out.append(r)
    except Exception:  # noqa: BLE001
        return []
    return out
