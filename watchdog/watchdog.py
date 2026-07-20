"""Edge-triggered watchdog for scanner feed-ingest heartbeats."""
from __future__ import annotations

import argparse
import os
import plistlib
import sys
import time
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "pons"))
import health  # noqa: E402
import telegram  # noqa: E402

LAUNCH_AGENTS = os.path.expanduser("~/Library/LaunchAgents")
DATA = os.path.join(HERE, "data")
STATE_PATH = os.path.join(DATA, "state.json")
LIVENESS_PATH = os.path.join(DATA, "heartbeat.json")

# Five-ish missed polls before DOWN. Arc is deliberately looser because its
# source is small/slow; every threshold still reports an outage within minutes.
THRESHOLDS = {
    "pons": 120,
    "flap": 120,
    "pump": 180,
    "virtuals": 240,
    "arc": 300,
    "bags": 240,
}


@dataclass(frozen=True)
class Target:
    label: str
    scanner: str
    heartbeat: object
    threshold: float


@dataclass(frozen=True)
class Event:
    label: str
    scanner: str
    status: str
    age: float | None
    threshold: float


def evaluate(targets, acknowledged, now):
    """Return notification edges and silently initialize healthy targets."""
    state = dict(acknowledged)
    events = []
    for target in targets:
        row = health.read(target.heartbeat)
        try:
            age = max(float(now) - float(row["t"]), 0.0)
        except (KeyError, TypeError, ValueError):
            age = None
        status = "up" if age is not None and age <= target.threshold else "down"
        previous = state.get(target.label)
        if previous is None and status == "up":
            state[target.label] = "up"
        elif previous != status:
            events.append(Event(
                label=target.label,
                scanner=target.scanner,
                status=status,
                age=age,
                threshold=target.threshold,
            ))
    return events, state


def acknowledge(state, event):
    """Record an edge only after its Telegram notification succeeded."""
    updated = dict(state)
    updated[event.label] = event.status
    return updated


def discover_targets(launch_agents_dir, repo_root, thresholds, default_threshold=300):
    """Build the watch list from installed `com.sunrise.*-scanner` plists."""
    targets = []
    try:
        names = sorted(os.listdir(launch_agents_dir))
    except OSError:
        return targets
    for name in names:
        path = os.path.join(launch_agents_dir, name)
        try:
            with open(path, "rb") as f:
                config = plistlib.load(f)
        except (OSError, ValueError):
            continue
        label = config.get("Label")
        prefix, suffix = "com.sunrise.", "-scanner"
        if not isinstance(label, str) or not label.startswith(prefix) or not label.endswith(suffix):
            continue
        scanner = label[len(prefix):-len(suffix)]
        args = config.get("ProgramArguments") or []
        script = next((arg for arg in args
                       if isinstance(arg, str) and arg.endswith(".py")), None)
        if not script:
            continue
        if not os.path.isabs(script):
            workdir = config.get("WorkingDirectory") or os.fspath(repo_root)
            script = os.path.join(workdir, script)
        heartbeat = os.path.join(os.path.dirname(script), "data", "heartbeat.json")
        targets.append(Target(
            label=label,
            scanner=scanner,
            heartbeat=heartbeat,
            threshold=float(thresholds.get(scanner, default_threshold)),
        ))
    return targets


def format_event(event):
    """Render one operator-facing outage or recovery notification."""
    name = event.scanner.upper()
    if event.status == "down":
        age = "no heartbeat yet" if event.age is None else f"{event.age / 60:.1f} min stale"
        return (
            f"🔴 <b>SCANNER FEED DOWN</b> — <b>{name}</b>\n"
            f"{age} (limit {event.threshold / 60:.1f} min)\n"
            "process may still be running; no successful feed ingest"
        )
    return (
        f"🟢 <b>SCANNER FEED RECOVERED</b> — <b>{name}</b>\n"
        "successful feed ingestion resumed"
    )


def run_once(targets, state_path, liveness_path, sender, now, runtime_state=None):
    """Evaluate all targets once, notify edges, and expose watchdog liveness."""
    if runtime_state is None:
        runtime_state = {}
    acknowledged = runtime_state.get("acknowledged")
    if not isinstance(acknowledged, dict):
        stored = health.read(state_path) or {}
        acknowledged = stored.get("acknowledged")
        if not isinstance(acknowledged, dict):
            acknowledged = {}
    events, state = evaluate(targets, acknowledged, now)
    runtime_state["acknowledged"] = state
    results = []
    for event in events:
        ok, info = sender(format_event(event))
        results.append((event, ok, info))
        if ok:
            state = acknowledge(state, event)
            runtime_state["acknowledged"] = state
    if not health.write(state_path, {"acknowledged": state}):
        raise RuntimeError(f"could not persist watchdog state: {state_path}")
    if not health.touch(
        liveness_path,
        "watchdog",
        now=now,
        detail={"targets": len(targets), "events": len(events)},
    ):
        raise RuntimeError(f"could not write watchdog liveness: {liveness_path}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=30.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="print transition messages instead of sending Telegram")
    ap.add_argument("--launch-agents", default=LAUNCH_AGENTS)
    ap.add_argument("--state", default=STATE_PATH)
    ap.add_argument("--liveness", default=LIVENESS_PATH)
    args = ap.parse_args()

    token, chat_id = telegram.load_creds()

    def send(text):
        if args.dry_run:
            print(text, flush=True)
            return True, "dry-run"
        return telegram.send(text, token, chat_id)

    print("scanner watchdog  targets=installed com.sunrise.*-scanner LaunchAgents  "
          f"interval={args.interval:.0f}s  -> "
          f"{'DRY-RUN' if args.dry_run else 'Telegram'}", flush=True)
    runtime_state = {}
    while True:
        try:
            now = time.time()
            targets = discover_targets(args.launch_agents, REPO, THRESHOLDS)
            results = run_once(
                targets,
                state_path=args.state,
                liveness_path=args.liveness,
                sender=send,
                now=now,
                runtime_state=runtime_state,
            )
            for event, ok, info in results:
                print(f"[{time.strftime('%H:%M:%S')}] {event.scanner} "
                      f"{event.status.upper()} {'sent' if ok else 'FAILED: ' + str(info)}",
                      flush=True)
            if args.once:
                return
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            print(f"  watchdog loop error: {exc}", flush=True)
            if args.once:
                raise
            time.sleep(min(args.interval, 30))


if __name__ == "__main__":
    main()
