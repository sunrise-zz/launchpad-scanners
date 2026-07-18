"""Evidence engine — the numbers every design decision answers to.

Clean, robust mining of alerts.jsonl × snapshots.jsonl (dedup by token+tier
keep-first, winsorized returns, stale snapshots dropped) producing the tables
that docs/redesign-v2.md is built on:

  1. slice table    — per platform/tier: n, med/mean @horizon, hit, median
                      PEAK, P(peak>=2x), EV per $100
  2. calibration    — does the displayed score actually rank outcomes?
  3. feature lift   — P(2x) by alert-time feature bins (gmgn forensics,
                      socials, liq) where sample size permits
  4. --write-stats  — tier_stats.json consumed by alertfmt so every Telegram
                      alert carries its tier's LIVE track record

The north-star metrics are EV/$100 (peak-aware) and P(peak>=2x) — chosen in
docs/redesign-v2.md because launch outcomes are power-law (top-5 coins carry
~42% of all peak mass); medians alone mislead.

Usage:
    python3 tracker/analyze.py                  # full report
    python3 tracker/analyze.py --horizon 480
    python3 tracker/analyze.py --write-stats    # refresh tier_stats.json
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
STATS = os.path.join(DATA, "tier_stats.json")

CAP = 50.0          # winsorize: >50x is a data artifact (pair switch / unit break)
MATURE_S = 8 * 3600


def _load(path):
    rows = []
    if os.path.exists(path):
        for ln in open(path):
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except Exception:  # noqa: BLE001
                    pass
    return rows


def _num(x):
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def load_joined():
    """[(alert, {horizon: ret}, peak)] — deduped (token,tier) keep-first,
    winsorized, stale snapshots excluded."""
    snaps = defaultdict(list)
    for s in _load(SNAPS):
        if not s.get("stale"):
            snaps[s["id"]].append(s)
    out, seen = [], set()
    for a in _load(ALERTS):
        k = (a.get("token"), a.get("tier"))
        if k in seen:
            continue
        seen.add(k)
        aid = f"{a['t']:.0f}:{a.get('token')}"
        ss = snaps.get(aid, [])
        base, metric = (_num(a.get("price0")), "price") if _num(a.get("price0")) \
            else (_num(a.get("mcap0")), "mcap")
        if not base:
            for s in sorted(ss, key=lambda s: s["h"]):
                for m in ("price", "mcap"):
                    if _num(s.get(m)):
                        base, metric = _num(s[m]), m
                        break
                if base:
                    break
        rets, peak = {}, None
        if base:
            for s in ss:
                v = _num(s.get(metric))
                if v:
                    r = min(v / base - 1, CAP)
                    rets[s["h"]] = r
                    peak = r if peak is None else max(peak, r)
        out.append((a, rets, peak))
    return out


def slice_key(a):
    return f"{(a.get('platform') or '?').split('.')[0]}/{a.get('tier') or '?'}"


def slice_table(rows, horizon, min_n=2, mature_only=True):
    now = time.time()
    groups = defaultdict(list)
    for a, r, p in rows:
        if mature_only and now - a["t"] < MATURE_S:
            continue
        groups[slice_key(a)].append((a, r, p))
    table = []
    for k, pairs in groups.items():
        xs = [r[horizon] for _, r, _ in pairs if horizon in r]
        pk = [p for _, _, p in pairs if p is not None]
        if len(xs) < min_n or not pk:
            continue
        table.append(dict(
            slice=k, n=len(xs),
            med=statistics.median(xs), mean=statistics.mean(xs),
            hit=sum(1 for x in xs if x >= 0.5) / len(xs),
            med_peak=statistics.median(pk),
            p2x=sum(1 for x in pk if x >= 1.0) / len(pk),
            ev=statistics.mean(xs) * 100,
        ))
    return sorted(table, key=lambda d: -d["n"])


def rankcorr(xs, ys):
    def rk(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for i, j in enumerate(order):
            r[j] = i
        return r
    rx, ry = rk(xs), rk(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    return cov / (vx * vy) ** 0.5 if vx and vy else 0.0


def feature_lift(rows, min_n=8):
    """P(2x) by alert-time feature bins — the input for future fitted weights."""
    feats = {
        "gmgn.has_x": lambda a: (a.get("gmgn") or {}).get("has_x"),
        "gmgn.smart>=1": lambda a: None if not a.get("gmgn") else (a["gmgn"].get("smart") or 0) >= 1,
        "gmgn.bots>=30%": lambda a: None if not a.get("gmgn") or a["gmgn"].get("bot_rate") is None
        else a["gmgn"]["bot_rate"] >= 0.3,
        "gmgn.holders>=100": lambda a: None if not a.get("gmgn") or a["gmgn"].get("holders") is None
        else a["gmgn"]["holders"] >= 100,
        "liq0>=$5k": lambda a: None if _num(a.get("liq0")) is None else _num(a.get("liq0")) >= 5000,
    }
    out = []
    peaked = [(a, p) for a, _, p in rows if p is not None]
    for name, fn in feats.items():
        buckets = defaultdict(list)
        for a, p in peaked:
            v = fn(a)
            if v is not None:
                buckets[bool(v)].append(p)
        if all(len(buckets[b]) >= min_n for b in (True, False)):
            pt = sum(1 for x in buckets[True] if x >= 1) / len(buckets[True])
            pf = sum(1 for x in buckets[False] if x >= 1) / len(buckets[False])
            out.append((name, pt, len(buckets[True]), pf, len(buckets[False])))
    return out


def pct(x):
    return f"{x*100:+.0f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=240)
    ap.add_argument("--min-n", type=int, default=2)
    ap.add_argument("--write-stats", action="store_true",
                    help="refresh data/tier_stats.json (read by alertfmt tier-record line)")
    args = ap.parse_args()

    rows = load_joined()
    table = slice_table(rows, args.horizon, args.min_n)

    if args.write_stats:
        stats = {}
        for d in table:
            tier = d["slice"].split("/", 1)[1]
            stats[tier] = {"n": d["n"], "p2x": round(d["p2x"], 3),
                           "med_peak": round(d["med_peak"], 3),
                           "med": round(d["med"], 3), "h": args.horizon,
                           "t": time.time()}
        os.makedirs(DATA, exist_ok=True)
        json.dump(stats, open(STATS, "w"), indent=1)
        print(f"wrote {STATS} ({len(stats)} tiers)")
        return

    print(f"\n=== SLICES (h={args.horizon}m, matured, deduped, winsorized {CAP:.0f}x) ===")
    print(f"{'slice':<26} {'n':>4} {'med':>7} {'mean':>7} {'hit+50%':>8} {'medPEAK':>8} {'P(2x)':>6} {'EV/$100':>8}")
    for d in table:
        print(f"{d['slice']:<26} {d['n']:>4} {pct(d['med']):>7} {pct(d['mean']):>7} "
              f"{d['hit']*100:>7.0f}% {pct(d['med_peak']):>8} {d['p2x']*100:>5.0f}% {d['ev']:>+7.0f}$")

    print("\n=== CALIBRATION corr(score, peak) per slice ===")
    groups = defaultdict(list)
    for a, r, p in rows:
        if p is not None and a.get("score"):
            groups[slice_key(a)].append((a.get("score"), p))
    for k, pts in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(pts) >= 10:
            rc = rankcorr([x for x, _ in pts], [y for _, y in pts])
            print(f"  {k:<26} n={len(pts):<4} {rc:+.2f}")

    print("\n=== FEATURE LIFT — P(2x) with vs without ===")
    fl = feature_lift(rows)
    if not fl:
        print("  (not enough per-feature samples yet — gmgn enrichment started 2026-07-18)")
    for name, pt, nt, pf, nf in fl:
        print(f"  {name:<22} with {pt*100:>3.0f}% (n{nt})  vs  without {pf*100:>3.0f}% (n{nf})")

    top = sorted([p for _, _, p in rows if p is not None], reverse=True)[:5]
    allp = [p for _, _, p in rows if p is not None]
    if allp and sum(allp) > 0:
        print(f"\nconcentration: top-5 peaks carry {sum(top)/sum(allp)*100:.0f}% of total peak mass "
              f"(n={len(allp)}) — optimize EV/tails, not medians")


if __name__ == "__main__":
    main()
