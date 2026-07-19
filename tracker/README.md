# tracker/ — alert outcome tracking

Closes the loop: records every alert, follows each coin's price afterward, and
reports whether the scores actually predicted anything — the data you need to
refit the score weights instead of guessing.

## Pipeline

```
scanners ──record_alert()────► data/alerts.jsonl   ── coins we alerted on
        └──record_control()──► data/controls.jsonl ── coins we did NOT (#9)
                                   │
              track.py (daemon) ───┤ samples price at 5m,15m,30m,1h,2h,4h,8h,12h,24h,48h
                                   ▼                 (BOTH files, one cadence)
                             data/snapshots.jsonl
                                   │
              report.py ──────────►┘ joins + summarizes by platform/tier/score band,
                                     then EDGE vs CONTROL — did the alerts beat a
                                     random launch from the same hour?
```

- **`pons/outcomes.py`** — `record_alert(...)`; every scanner calls it at dispatch
  time. Writes one row per alert with the coin, score, alert-time price, and a
  `track` descriptor telling the daemon how to price it later.
- **`record_control(...)`** — the same row shape for a launch we saw and did
  **not** alert on, written to `data/controls.jsonl`. Sampled 2 per launchpad
  per hour by `pons/controls.py`. They live in their own file so every reader of
  `alerts.jsonl` stays correct without having to filter — see
  `docs/shadow-control-sampling.md` for the design, and for what went wrong
  while the two shared one file.
- **`track.py`** — daemon (LaunchAgent `com.sunrise.tracker`). Idempotent and
  resumable: a (alert, horizon) already sampled is never redone, so restarts are
  safe. Price sources: DexScreener (robinhood/base/solana), the arc backend, and
  the Virtuals API (mcap in VIRTUAL for on-curve agents).
- **`report.py`** — the analysis:

```bash
python3 tracker/report.py                  # full table
python3 tracker/report.py --min-age-h 24   # only matured alerts (fairest)
python3 tracker/report.py --platform flap.sh
python3 tracker/report.py --horizon 360    # focus 6h
```

Each row shows, per horizon (1h/6h/24h): **median return** vs the alert-time
baseline, **hit rate** (share reaching +50%), and n. The score-band slice is the
key output — if 🟢 80+ doesn't out-return 🔴 <40, the weights in each scanner's
`score_*` function need adjusting.

The **EDGE vs CONTROL** table at the end is the only one measured against
anything: `edge` = alerted median − control median at that horizon, `base` = the
control median itself. Every other number is a raw return, which a broad market
move flatters or ruins regardless of whether the alert picked well — a -20%
against a -60% base rate is a +40% edge. A **negative** edge means the filter is
picking worse than a random launch from the same hour.

## Reading it / acting on it

- Give it a few days so alerts mature past 24h before trusting the numbers.
- If a whole tier or platform shows negative median at every horizon, tighten its
  gate or drop it.
- If a single signal (e.g. paid-marketing, smart-money score) correlates with the
  winners, raise its weight in the `score_*` function; if not, lower it.
- Baselines: uses `price0` when the alert captured one, else the first snapshot;
  returns fall back to mcap when price is unavailable (bonding-curve coins).
