"""Outcome report — did the alerts (and their scores) actually predict pumps?

Joins tracker/data/alerts.jsonl with snapshots.jsonl and computes, per horizon,
the return vs the alert-time baseline. Slices by platform, tier, and score band
so you can see whether higher scores really earned higher returns — the input
for refitting the score weights.

Baseline price = the alert's price0 if present, else the earliest snapshot.
"Return" uses price when available on both ends, else mcap (so bonding-curve
coins priced only in mcap still count).

Usage:
    python3 tracker/report.py                 # full summary
    python3 tracker/report.py --platform flap.sh
    python3 tracker/report.py --horizon 360   # focus one horizon (minutes)
    python3 tracker/report.py --min-age-h 24  # only alerts old enough to be mature
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ALERTS = os.path.join(DATA, "alerts.jsonl")
SNAPS = os.path.join(DATA, "snapshots.jsonl")
VERDICTS = os.path.join(DATA, "agent_verdicts.jsonl")   # agent/analyst.py output

KEY_HORIZONS = [60, 240, 480]    # 1h, 4h, 8h — MUST be values in track.py HORIZONS
                                 # (was 360, which the tracker never samples, so the
                                 #  column was always empty). 24h needs >1 day of runtime.


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


def alert_id(a):
    return f"{a['t']:.0f}:{a.get('token')}"


def num(x):
    """Coerce to positive float, or None. Several APIs return numbers as strings."""
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def baseline(a, snaps):
    """(value, metric) at alert time — prefer price0, else earliest snapshot."""
    if num(a.get("price0")):
        return num(a["price0"]), "price"
    if num(a.get("mcap0")):
        return num(a["mcap0"]), "mcap"
    ss = sorted(snaps, key=lambda s: s["h"])
    for s in ss:
        if num(s.get("price")):
            return num(s["price"]), "price"
    for s in ss:
        if num(s.get("mcap")):
            return num(s["mcap"]), "mcap"
    return None, None


def ret_at(a, snaps, horizon):
    """Return (fraction) at a horizon vs baseline, or None if not computable."""
    base, metric = baseline(a, snaps)
    if not base:
        return None
    snap = next((s for s in snaps if s["h"] == horizon), None)
    if not snap:
        return None
    cur = num(snap.get(metric))
    if metric == "price" and not cur:            # fall back to mcap if price gap
        cur, base2 = num(snap.get("mcap")), num(a.get("mcap0"))
        if cur and base2:
            return cur / base2 - 1
        return None
    if not cur:
        return None
    return cur / base - 1


def pct(x):
    return f"{x*100:+.0f}%" if x is not None else "  –"


def summarize(label, alerts_snaps, horizons):
    """One row: n, and median / hit-rate per horizon."""
    n = len(alerts_snaps)
    cells = []
    for h in horizons:
        rets = [ret_at(a, s, h) for a, s in alerts_snaps]
        rets = [r for r in rets if r is not None]
        if rets:
            med = statistics.median(rets)
            hit = sum(1 for r in rets if r >= 0.5) / len(rets)   # >= +50%
            cells.append(f"{pct(med):>6} {hit*100:>3.0f}%↑ n{len(rets):<3}")
        else:
            cells.append(f"{'–':>6} {'–':>4} {'':<4}")
    return f"{label:<28} tot{n:<4} " + " │ ".join(cells)


def band(score):
    if score is None:
        return "no-score"
    if score >= 80:
        return "🟢 80+"
    if score >= 60:
        return "🟡 60-79"
    if score >= 40:
        return "🟠 40-59"
    return "🔴 <40"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform")
    ap.add_argument("--tier")
    ap.add_argument("--horizon", type=int, help="focus a single horizon (min)")
    ap.add_argument("--min-age-h", type=float, default=0,
                    help="only alerts at least this many hours old (matured)")
    args = ap.parse_args()

    alerts = load(ALERTS)
    snaps_by_id = defaultdict(list)
    for s in load(SNAPS):
        snaps_by_id[s["id"]].append(s)

    now = time.time()
    pairs = []   # (alert, its snapshots)
    for a in alerts:
        if args.platform and a.get("platform") != args.platform:
            continue
        if args.tier and a.get("tier") != args.tier:
            continue
        if (now - a["t"]) / 3600 < args.min_age_h:
            continue
        pairs.append((a, snaps_by_id.get(alert_id(a), [])))

    horizons = [args.horizon] if args.horizon else KEY_HORIZONS
    hlabel = {60: "1h", 240: "4h", 480: "8h", 1440: "24h"}
    header = "  ".join(hlabel.get(h, f"{h}m") + " (med  hit  n)" for h in horizons)

    print(f"\nOutcome report — {len(pairs)} alerts"
          + (f" · {args.platform}" if args.platform else "")
          + (f" · ≥{args.min_age_h}h old" if args.min_age_h else ""))
    print(f"{'':<28} {'':<7} {header}")
    print("─" * (36 + len(horizons) * 22))

    if not pairs:
        print("(no alerts yet — the tracker needs alerts to fire and mature first)")
        print("Metric = median return vs alert-time baseline · hit = share reaching +50%\n")
        return

    print(summarize("ALL", pairs, horizons))
    print()

    # by platform
    byp = defaultdict(list)
    for a, s in pairs:
        byp[a.get("platform", "?")].append((a, s))
    for p in sorted(byp):
        print(summarize(f"  {p}", byp[p], horizons))
    print()

    # by tier
    byt = defaultdict(list)
    for a, s in pairs:
        byt[a.get("tier", "?")].append((a, s))
    for tkey in sorted(byt):
        print(summarize(f"  {tkey}", byt[tkey], horizons))
    print()

    # by score band — the key signal for refitting weights
    bys = defaultdict(list)
    for a, s in pairs:
        bys[band(a.get("score"))].append((a, s))
    order = ["🟢 80+", "🟡 60-79", "🟠 40-59", "🔴 <40", "no-score"]
    for b in order:
        if b in bys:
            print(summarize(f"  score {b}", bys[b], horizons))

    # by AI verdict (agent/analyst.py) — does the LLM DD add lift over the score?
    verdicts = {}
    for v in load(VERDICTS):
        if v.get("ok") and v.get("verdict"):
            verdicts[v["id"]] = v["verdict"]     # last verdict per alert wins
    if verdicts:
        print()
        byv = defaultdict(list)
        for a, s in pairs:
            byv[verdicts.get(alert_id(a), "(no DD)")].append((a, s))
        for vkey in ["BUY-WATCH", "NEUTRAL", "AVOID", "(no DD)"]:
            if vkey in byv:
                print(summarize(f"  AI {vkey}", byv[vkey], horizons))

    print("\nMetric = median return vs alert-time baseline · hit = share reaching +50%")
    print("If score bands don't separate (🟢 ≈ 🔴), the weights need refitting.\n")


if __name__ == "__main__":
    main()
