"""Feed-ingest heartbeats and edge-triggered scanner outage alerts."""
from __future__ import annotations

import os
import plistlib

import pytest


def test_successful_ingest_heartbeat_round_trips_atomically(health, tmp_path):
    path = tmp_path / "heartbeat.json"

    assert health.touch(path, "pump", now=1_234.5, detail={"items": 100})
    assert health.read(path) == {
        "scanner": "pump",
        "t": 1_234.5,
        "pid": os.getpid(),
        "detail": {"items": 100},
    }
    assert list(tmp_path.iterdir()) == [path]


def test_feed_rows_must_all_be_json_objects(health):
    assert health.is_record_list([])
    assert health.is_record_list([{"id": 1}])
    assert not health.is_record_list(None)
    assert not health.is_record_list([None])
    assert not health.is_record_list([{}, "bad"])


def test_feed_dead_process_alive_emits_one_down_and_one_recovery(
        health, watchdog, tmp_path):
    """Process liveness is deliberately irrelevant: only feed-ingest age drives
    the edge-triggered DOWN/UP state machine."""
    path = tmp_path / "pons-heartbeat.json"
    target = watchdog.Target(
        label="com.sunrise.pons-scanner",
        scanner="pons",
        heartbeat=path,
        threshold=120,
    )
    health.touch(path, "pons", now=1_000)

    events, state = watchdog.evaluate([target], {}, now=1_000)
    assert events == []
    assert state == {target.label: "up"}

    events, state = watchdog.evaluate([target], state, now=1_121)
    assert [(e.label, e.status) for e in events] == [(target.label, "down")]
    assert state == {target.label: "up"}  # transition is unacknowledged until Telegram succeeds

    state = watchdog.acknowledge(state, events[0])
    events, state = watchdog.evaluate([target], state, now=1_500)
    assert events == []

    health.touch(path, "pons", now=1_501)
    events, state = watchdog.evaluate([target], state, now=1_501)
    assert [(e.label, e.status) for e in events] == [(target.label, "up")]

    state = watchdog.acknowledge(state, events[0])
    events, state = watchdog.evaluate([target], state, now=1_502)
    assert events == []


def test_targets_come_from_installed_scanner_launchagents(watchdog, tmp_path):
    repo = tmp_path / "repo"
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()

    def install(label, script):
        with open(agents / f"{label}.plist", "wb") as f:
            plistlib.dump({
                "Label": label,
                "WorkingDirectory": str(repo),
                "ProgramArguments": ["/opt/homebrew/bin/python3", "-u", script],
            }, f)

    install("com.sunrise.pons-scanner", "pons/alert_pro.py")
    install("com.sunrise.arc-scanner", "arc/scan.py")
    install("com.sunrise.bags-scanner", "bags/scan.py")
    install("com.sunrise.tracker", "tracker/track.py")
    with open(agents / "com.sunrise.pons-reputation-collector.plist", "wb") as f:
        plistlib.dump({
            "Label": "com.sunrise.pons-reputation-collector",
            "WorkingDirectory": str(repo),
            "ProgramArguments": [
                "/opt/homebrew/bin/python3", "-u", "pons/reputation.py",
                "--heartbeat", "pons/data/reputation_heartbeat.json",
            ],
        }, f)

    targets = watchdog.discover_targets(
        agents, repo, {
            "pons": 120, "arc": 300, "bags": 240,
            "pons-reputation": 28_800,
        })

    assert [(t.label, t.scanner, t.threshold) for t in targets] == [
        ("com.sunrise.arc-scanner", "arc", 300),
        ("com.sunrise.bags-scanner", "bags", 240),
        ("com.sunrise.pons-reputation-collector", "pons-reputation", 28_800),
        ("com.sunrise.pons-scanner", "pons", 120),
    ]
    assert [os.fspath(t.heartbeat) for t in targets] == [
        os.fspath(repo / "arc/data/heartbeat.json"),
        os.fspath(repo / "bags/data/heartbeat.json"),
        os.fspath(repo / "pons/data/reputation_heartbeat.json"),
        os.fspath(repo / "pons/data/heartbeat.json"),
    ]


def test_watchdog_cycle_persists_state_and_its_own_liveness(
        health, watchdog, tmp_path):
    feed = tmp_path / "pump-heartbeat.json"
    state_path = tmp_path / "state.json"
    liveness = tmp_path / "watchdog-heartbeat.json"
    target = watchdog.Target(
        "com.sunrise.pump-scanner", "pump", feed, threshold=180)
    health.touch(feed, "pump", now=2_000)
    sent = []

    watchdog.run_once(
        [target],
        state_path=state_path,
        liveness_path=liveness,
        sender=lambda text: (sent.append(text) or True, 1),
        now=2_000,
    )

    assert sent == []
    assert health.read(state_path) == {
        "acknowledged": {"com.sunrise.pump-scanner": "up"}}
    heartbeat = health.read(liveness)
    assert heartbeat["scanner"] == "watchdog"
    assert heartbeat["t"] == 2_000
    assert heartbeat["detail"] == {"targets": 1, "events": 0}


def test_successful_notification_is_not_repeated_when_state_write_fails(
        health, watchdog, tmp_path, monkeypatch):
    feed = tmp_path / "missing-heartbeat.json"
    state_path = tmp_path / "state.json"
    liveness = tmp_path / "watchdog-heartbeat.json"
    target = watchdog.Target(
        "com.sunrise.pons-scanner", "pons", feed, threshold=120)
    runtime_state = {}
    sent = []
    monkeypatch.setattr(watchdog.health, "write", lambda path, row: False)

    with pytest.raises(RuntimeError, match="persist watchdog state"):
        watchdog.run_once(
            [target],
            state_path=state_path,
            liveness_path=liveness,
            sender=lambda text: (sent.append(text) or True, 1),
            now=2_000,
            runtime_state=runtime_state,
        )

    with pytest.raises(RuntimeError, match="persist watchdog state"):
        watchdog.run_once(
            [target],
            state_path=state_path,
            liveness_path=liveness,
            sender=lambda text: (sent.append(text) or True, 2),
            now=2_030,
            runtime_state=runtime_state,
        )

    assert len(sent) == 1
    assert not liveness.exists()


def test_virtuals_rejects_malformed_feed_envelopes(virtuals, monkeypatch):
    monkeypatch.setattr(virtuals, "api_get", lambda *args, **kwargs: {})
    assert virtuals.list_virtuals("BASE", "createdAt:desc") is None

    monkeypatch.setattr(
        virtuals, "api_get", lambda *args, **kwargs: {"error": "upstream"})
    assert virtuals.list_virtuals("BASE", "createdAt:desc") is None

    monkeypatch.setattr(
        virtuals, "api_get", lambda *args, **kwargs: {"data": []})
    assert virtuals.list_virtuals("BASE", "createdAt:desc") == []
