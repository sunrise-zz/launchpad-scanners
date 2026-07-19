"""One-time migration for #9: move shadow controls out of the alert population.

Before #9 there was no controls.jsonl, so the two experiments that recorded
coins *without* alerting on them — flap's SHADOW tiers and bags' TRENCH BURST —
wrote their rows into alerts.jsonl alongside real alerts, marked only by a tier
string nobody filtered on. By the time this was written that was ~450 of ~1490
rows — 30% of the file — and it had three live consequences:

  * report.py counted them as alerts and pooled them into every per-platform
    median, mixing the alerted and non-alerted populations into one number —
    destroying the very comparison the shadow experiment existed to enable.
  * agent/daily_brief.py read "alerts 24h: N" aloud, inflated ~30%.
  * outcomes.recent_same_symbol() counts prior rows of the same symbol, and
    flap suppresses a name at 2 (--max-name-repeats). 66 flap symbols had ≥2
    control rows, so a never-sent row was suppressing real Telegram alerts —
    and because controls carry no price0, peak_return() can never rescue them,
    only ever suppress.

Snapshot ids are left exactly as they are: snapshots.jsonl joins on
"<t>:<token>" and has no idea which file a row lives in, so the thousands of
snapshots already collected against these rows stay joined and the accumulated
outcome history is preserved intact. This script prints the exact counts it
moved.

Idempotent — a second run finds nothing left to move. Writes .bak copies and
replaces atomically.

    python3 tracker/migrate_controls.py --dry-run
    python3 tracker/migrate_controls.py
"""
from __future__ import annotations

import argparse
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ALERTS = os.path.join(DATA, "alerts.jsonl")
CONTROLS = os.path.join(DATA, "controls.jsonl")

# The complete set of tiers ever written tracker-only, before record_control()
# existed to mark them. An explicit allow-list rather than a heuristic: "score
# is None" also matches real alerts from tiers that never scored, and a
# substring match on "SHADOW" would catch any future tier unlucky in its name.
# Getting this wrong deletes a real alert from every historical number.
LEGACY_CONTROL_TIERS = ("FLAP SHADOW-60", "FLAP SHADOW-XFER", "TRENCH BURST")


def is_control(row):
    """Anything written since #9 says so outright; the tier list is only how we
    recognise rows that predate the mark."""
    return bool(row.get("shadow")) or row.get("tier") in LEGACY_CONTROL_TIERS


def split(rows):
    """(alerts, controls). Every input row comes out one side or the other.

    A row matching no rule stays in alerts deliberately: a control left in the
    alert population is a reporting bug we can see and fix later, while a
    dropped row is data we cannot get back."""
    alerts, controls = [], []
    for r in rows:
        (controls if is_control(r) else alerts).append(r)
    return alerts, controls


def load(path):
    rows = []
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
    return rows


def write(path, rows):
    """Write via a temp file and replace, so an interrupted run cannot leave a
    half-written alerts.jsonl behind."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report what would move, change nothing")
    args = ap.parse_args()

    existing = load(CONTROLS)
    alerts, moved = split(load(ALERTS))

    print(f"alerts.jsonl:   {len(alerts) + len(moved)} rows → {len(alerts)} alerts")
    print(f"controls.jsonl: {len(existing)} rows → {len(existing) + len(moved)} "
          f"({len(moved)} moved)")
    if not moved:
        print("nothing to migrate.")
        return
    by_tier = {}
    for r in moved:
        by_tier[r.get("tier")] = by_tier.get(r.get("tier"), 0) + 1
    for tier, n in sorted(by_tier.items(), key=lambda x: -x[1]):
        print(f"  {n:5}  {tier}")
    if args.dry_run:
        print("\n(dry run — nothing written)")
        return

    for path in (ALERTS, CONTROLS):
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")
            print(f"backed up {os.path.basename(path)} → {os.path.basename(path)}.bak")
    write(CONTROLS, existing + moved)
    write(ALERTS, alerts)
    print("done.")


if __name__ == "__main__":
    main()
