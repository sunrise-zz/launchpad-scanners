"""Shadow-control sampling (#9) — the control group that makes the refit honest.

The tracker only ever measured coins we alerted on, so it could say "our alerts
returned -20%" but never "…against a base rate of -60%". These tests pin the
two halves of the fix: a recorder that keeps controls out of the alert
population, and a sampler that decides which launches become controls.
"""
from __future__ import annotations

import json
import sys
import time

import pytest

TRACK = {"method": "flap", "address": "0xabc"}

# An exact multiple of 3600, so "the hour" in these tests is a real aligned
# bucket. The quota is per aligned bucket; a window starting mid-bucket
# straddles three slots and legitimately sees three.
HOUR0 = 277778 * 3600


# --- the recorder -----------------------------------------------------------

def test_a_control_never_enters_the_alert_population(outcomes_mod, tmp_alerts, tmp_controls):
    """The one invariant the whole study rests on. Every existing reader —
    report.py, daily_brief.py, recent_same_symbol — treats a row in
    alerts.jsonl as a coin we alerted on, and none of them can be made to ask
    otherwise without being changed. Keeping controls in their own file is what
    makes those readers correct by construction rather than by vigilance."""
    outcomes_mod.record_control("flap.sh", "ROBINHOOD", "MOG", "0xabc", TRACK)

    assert tmp_alerts() == [], "a control must never land in alerts.jsonl"
    assert len(tmp_controls()) == 1


def test_a_control_carries_every_column_an_alert_carries(outcomes_mod, tmp_alerts, tmp_controls):
    """Controls are measured by the *same* code that measures alerts —
    track.py's horizon cadence, report.py's baseline() and ret_at(). That reuse
    is what makes the comparison apples-to-apples instead of two pipelines that
    drifted apart, and it only holds while the two row shapes agree."""
    outcomes_mod.record_alert("flap.sh", "ROBINHOOD", "FLAP EARLY", "MOG", "0xabc",
                              50, TRACK, gmgn=False)
    outcomes_mod.record_control("flap.sh", "ROBINHOOD", "PEPE", "0xdef", TRACK)

    alert, = tmp_alerts()
    control, = tmp_controls()
    assert not set(alert) - set(control), "a control is missing a column the analysis reads"
    assert set(control) - set(alert) == {"shadow", "id"}, (
        "a control adds only its mark and its explicit snapshot id")


def test_a_control_says_it_is_one(outcomes_mod, tmp_controls):
    """Belt and braces to the file split. controls.jsonl already answers "is
    this a control?" by which file it is in — but rows get copied, grepped and
    pasted into notebooks, and a row that has left its file should still know
    what it is."""
    outcomes_mod.record_control("flap.sh", "ROBINHOOD", "PEPE", "0xdef", TRACK)

    row, = tmp_controls()
    assert row["shadow"] is True
    assert row["score"] is None, "a control was never scored — 0 would be a measurement"


def test_a_control_is_gmgn_enriched_exactly_like_an_alert(outcomes_mod, tmp_controls, monkeypatch):
    """Asymmetric enrichment would bias the very analysis this enables. If
    alerts carry GMGN forensics and controls don't, then every gmgn-derived
    feature separates the two groups perfectly — and the refit would learn
    "has smart-money data" as a predictor of being alerted, which is circular.
    Cases and controls must be measured with the same instruments."""
    monkeypatch.setattr(sys.modules["gmgn"], "chain_addr_for",
                        lambda *a, **kw: ("robinhood", "0xdef"))
    monkeypatch.setattr(sys.modules["gmgn"], "snapshot", lambda *a, **kw: {"smart": 3})

    outcomes_mod.record_control("flap.sh", "ROBINHOOD", "PEPE", "0xdef", TRACK)

    assert tmp_controls()[0]["gmgn"] == {"smart": 3}


# --- the sampler ------------------------------------------------------------

def test_a_bucket_yields_exactly_k_controls_however_many_launches_it_saw(controls_mod, tmp_path):
    """flap sees ~5000 launches a day and arc sees a handful. The quota is what
    makes the tracker's cost a function of K and the number of launchpads,
    rather than of how busy the chain happened to be that hour."""
    s = controls_mod.ControlSampler("flap.sh", k=2, bucket_s=3600,
                                    state_path=str(tmp_path / "s.json"))

    taken = sum(1 for i in range(3600) if s.take(HOUR0 + i))   # a launch every second

    assert taken == 2


def test_a_burst_cannot_swallow_the_whole_bucket_quota(controls_mod, tmp_path):
    """The reason the rule is slots and not "the first K launches of the hour".
    Launches cluster — a listing, a trend, one deployer spamming — and first-K
    would spend the entire quota inside the burst, which is precisely when
    launches least resemble the hour they came from."""
    s = controls_mod.ControlSampler("flap.sh", k=2, bucket_s=3600,
                                    state_path=str(tmp_path / "s.json"))

    burst = sum(1 for i in range(60) if s.take(HOUR0 + i))   # 60 launches in one minute

    assert burst == 1, "the second slot has not opened yet — its quota is not spendable early"
    assert s.take(HOUR0 + 1800), "and it becomes available exactly when the slot opens"


def test_a_restart_cannot_reopen_a_slot_already_spent(controls_mod, tmp_path):
    """Scanners restart — on deploy, on crash, and on a crash *loop*. Quota
    held only in memory would reset every time, so a scanner crash-looping once
    a minute would sample a control a minute instead of two an hour, and the
    tracker load this design is built around would be unbounded."""
    state = str(tmp_path / "s.json")
    assert controls_mod.ControlSampler("flap.sh", k=2, bucket_s=3600, state_path=state).take(HOUR0)

    restarted = controls_mod.ControlSampler("flap.sh", k=2, bucket_s=3600, state_path=state)

    assert not restarted.take(HOUR0 + 5), "the slot was already spent before the restart"
    assert restarted.take(HOUR0 + 1800), "but the next slot is still owed its control"


def test_one_launch_is_never_sampled_as_a_control_twice(controls_mod, tmp_path):
    """Caught on the first live run: flap sampled TITDAQ in two consecutive
    slots, at 0.7s and 11.5s old. The pool is whatever is under watch right
    then, and just after a restart that is a handful of coins — so an unlucky
    random.choice lands on the same one. Two rows for one coin double its
    weight in a base rate built from only ~48 rows a day."""
    s = controls_mod.ControlSampler("flap.sh", k=2, bucket_s=3600,
                                    state_path=str(tmp_path / "s.json"))
    s.mark("0xaaa")

    assert s.sampled("0xaaa")
    assert not s.sampled("0xbbb")


def test_the_sampled_set_cannot_grow_without_bound(controls_mod, tmp_path):
    """These run for weeks inside a 24/7 daemon, and flap alone sees ~5000
    launches a day. Remembering every token forever is the memory leak in #14
    written a second time; a coin old enough to have fallen out of this window
    is also long past its watch window, so it can never be offered again."""
    s = controls_mod.ControlSampler("flap.sh", k=2, bucket_s=3600,
                                    state_path=str(tmp_path / "s.json"))
    for i in range(controls_mod.SEEN_MAX + 100):
        s.mark(f"0x{i}")

    assert len(s._seen) <= controls_mod.SEEN_MAX
    assert s.sampled(f"0x{controls_mod.SEEN_MAX + 99}"), "the most recent must still be remembered"


def test_an_empty_pool_does_not_burn_the_slot(controls_mod, tmp_path):
    """A quiet stretch with nothing eligible must not forfeit that slot's
    control — otherwise the launchpads with the least traffic, which are the
    ones whose base rate is hardest to accumulate, quietly sample least."""
    s = controls_mod.ControlSampler("arc", k=2, bucket_s=3600,
                                    state_path=str(tmp_path / "s.json"))

    assert s.choose(HOUR0, [], key=lambda x: x) is None

    assert s.choose(HOUR0 + 1, ["0xaaa"], key=lambda x: x) == "0xaaa", (
        "the slot was still open once something eligible showed up")


def test_choose_never_returns_a_launch_it_already_sampled(controls_mod, tmp_path):
    """The dedup and the quota are one decision, so every scanner gets both by
    driving the same call — rather than four scan loops each remembering to
    filter the pool themselves."""
    s = controls_mod.ControlSampler("flap.sh", k=3600, bucket_s=3600,   # a slot a second
                                    state_path=str(tmp_path / "s.json"))
    pool = ["0xaaa", "0xbbb"]

    picks = {s.choose(HOUR0 + i, pool, key=lambda x: x) for i in range(4)}

    assert picks == {"0xaaa", "0xbbb", None}, "each sampled once, then nothing eligible left"


# --- the tracker ------------------------------------------------------------

def _write(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _snaps(tracker):
    with open(tracker.SNAPS) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def test_the_tracker_measures_controls_on_the_same_cadence_as_alerts(tracker, monkeypatch):
    """A control with no outcome attached is just a logged address. The whole
    value is the return series, and it has to come off the same horizon
    schedule as the alerts it will be compared against — a control sampled on a
    different cadence is measuring a different thing."""
    monkeypatch.setattr(tracker, "take_snapshot", lambda track: {"price": 2.0, "mcap": 9, "liq": 8})
    now = time.time()
    _write(tracker.ALERTS, [{"t": now - 400, "token": "0xaaa", "tier": "FLAP EARLY",
                             "track": {"method": "flap", "address": "0xaaa"}}])
    _write(tracker.CONTROLS, [{"t": now - 400, "token": "0xccc", "shadow": True, "tier": "CONTROL",
                               "track": {"method": "flap", "address": "0xccc"}}])

    tracker.cycle()

    tokens = {s["token"] for s in _snaps(tracker)}
    assert tokens == {"0xaaa", "0xccc"}, "the control must be sampled alongside the alert"


def test_a_control_and_an_alert_on_one_coin_in_one_second_stay_distinct(tracker, monkeypatch,
                                                                        outcomes_mod, tmp_controls):
    """Snapshot ids truncate to whole seconds, and flap samples a control at
    the top of the same tick that can alert the same coin — so the two rows
    could collide on one id. Whichever the tracker reached second would be
    marked already-done and silently get no snapshots of its own, leaving the
    control showing the alert's return. That is the base rate quietly
    inheriting the outcome it is supposed to be measured against."""
    monkeypatch.setattr(tracker, "take_snapshot", lambda track: {"price": 2.0})
    now = time.time()
    outcomes_mod.record_control("flap.sh", "ROBINHOOD", "MOG", "0xsame",
                                TRACK, gmgn=False)
    control, = tmp_controls()
    control["t"] = now - 400                      # same coin, same second, as an alert
    _write(tracker.CONTROLS, [control])
    _write(tracker.ALERTS, [{"t": now - 400, "token": "0xsame", "tier": "FLAP EARLY",
                             "track": {"method": "flap", "address": "0xsame"}}])

    tracker.cycle()

    ids = {s["id"] for s in _snaps(tracker)}
    assert len(ids) == 2, "the alert and its control must not share one snapshot series"


def test_a_control_without_an_explicit_id_keeps_the_derived_one(tracker, monkeypatch):
    """The rows migrated out of alerts.jsonl were written before controls
    carried an explicit id, and thousands of snapshots are already joined to
    them by the derived "<t>:<token>". Falling back to that form rather than computing
    a new one is what keeps their accumulated history readable."""
    monkeypatch.setattr(tracker, "take_snapshot", lambda track: {"price": 2.0})
    now = time.time()
    _write(tracker.CONTROLS, [{"t": now - 400, "token": "0xccc", "shadow": True,
                               "track": {"method": "flap", "address": "0xccc"}}])

    tracker.cycle()

    assert _snaps(tracker)[0]["id"] == f"{now - 400:.0f}:0xccc"


# --- the comparison ---------------------------------------------------------

def _pair(price0, price_at_h, h=60):
    """One (row, snapshots) pair returning a known amount at horizon h."""
    return ({"t": 0, "token": "0x1", "price0": price0},
            [{"id": "0:0x1", "h": h, "price": price_at_h}])


def test_lift_is_measured_against_the_controls_not_against_zero(report_mod):
    """The number this whole pipeline exists to produce. "flap EARLY returned
    -20%" reads as a failure and "-20% against a base rate of -60%" reads as a
    +40% edge — same alerts, opposite conclusion. Before controls existed only
    the first sentence was sayable."""
    alerted = [_pair(1.0, 1.5)]      # +50%
    controls = [_pair(1.0, 0.4)]     # -60%

    alert_med, control_med, lift = report_mod.lift_at(alerted, controls, 60)

    assert alert_med == 0.5
    assert control_med == -0.6
    assert lift == pytest.approx(1.1), "the edge is the gap between them, not the raw return"


def test_lift_is_unknown_rather_than_zero_when_there_are_no_controls(report_mod):
    """A platform with no controls yet must not report its raw return as if it
    were an edge — that is the survivorship-biased reading #9 removes, and it
    would be worse for being dressed in a control-group column."""
    alert_med, control_med, lift = report_mod.lift_at([_pair(1.0, 1.5)], [], 60)

    assert alert_med == 0.5
    assert control_med is None and lift is None


def test_the_base_rate_uses_only_the_uniformly_sampled_controls(report_mod):
    """controls.jsonl holds two different experiments. #9's CONTROL rows are
    sampled uniformly from every launch, which is what makes them a base rate.
    flap's older SHADOW rows are sampled only from coins that already cleared
    60 recipients — a deliberately *selected* population, for the separate
    question of whether the EARLY bar should drop.

    Pooling them would quietly raise the base rate toward the traction end and
    understate our edge, which is the same class of selection error #9 exists
    to remove — just pointed the other way."""
    rows = [{"tier": "CONTROL", "token": "0x1"},
            {"tier": "FLAP SHADOW-60", "token": "0x2"},
            {"tier": "FLAP SHADOW-XFER", "token": "0x3"}]

    assert [r["token"] for r in report_mod.base_rate_controls(rows)] == ["0x1"]


# --- the migration ----------------------------------------------------------

def test_only_the_known_legacy_control_tiers_leave_the_alert_population(migrate_mod):
    """#9 moves ~450 pre-existing rows out of alerts.jsonl. Misclassify one and
    a real alert silently vanishes from every historical number — so the rule
    is an explicit allow-list of the three tiers that were ever written
    tracker-only, never a guess from a substring or a null score."""
    rows = [{"tier": "FLAP EARLY", "token": "0x1"},
            {"tier": "FLAP SHADOW-60", "token": "0x2"},
            {"tier": "TRENCH BURST", "token": "0x3"},
            {"tier": "CONFIRMED", "token": "0x4"},
            {"tier": "FLAP SHADOW-XFER", "token": "0x5"}]

    alerts, controls = migrate_mod.split(rows)

    assert [r["token"] for r in alerts] == ["0x1", "0x4"]
    assert [r["token"] for r in controls] == ["0x2", "0x3", "0x5"]


def test_the_migration_loses_nothing(migrate_mod):
    """The only unrecoverable failure mode. Every input row must come out one
    side or the other — a row that matches no rule belongs in alerts, because
    leaving a control in the alert population is a reporting bug we can see and
    fix, while dropping a row destroys data we cannot get back."""
    rows = [{"tier": t, "token": str(i)} for i, t in
            enumerate(["FLAP EARLY", "FLAP SHADOW-60", None, "SOMETHING NEW", "TRENCH BURST"])]

    alerts, controls = migrate_mod.split(rows)

    assert len(alerts) + len(controls) == len(rows)
    assert {r["token"] for r in alerts} == {"0", "2", "3"}, "unknown tiers stay put"


def test_migration_is_idempotent(migrate_mod):
    """It runs against live production files, so running it twice — or on a
    half-finished previous run — has to be safe."""
    already_moved = [{"tier": "FLAP EARLY", "token": "0x1"}]

    alerts, controls = migrate_mod.split(already_moved)

    assert alerts == already_moved and controls == []


def test_a_new_style_control_is_recognised_by_its_mark_not_its_tier(migrate_mod):
    """Legacy rows are identified by tier because that is all they carry.
    Anything written since #9 says so outright, and that mark must win — the
    tier allow-list is a historical artefact, not the definition."""
    rows = [{"tier": "WHATEVER", "shadow": True, "token": "0x9"}]

    alerts, controls = migrate_mod.split(rows)

    assert alerts == [] and controls == rows
