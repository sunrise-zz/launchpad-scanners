# tracker/ — alert outcome tracking

Closes the loop: records every alert, follows each coin's price afterward, and
reports whether the scores actually predicted anything — the data you need to
refit the score weights instead of guessing.

## Pipeline

```
scanners ──record_alert()──► data/alerts.jsonl
                                   │
              track.py (daemon) ───┤ samples price at 5m,15m,30m,1h,2h,4h,8h,12h,24h,48h
                                   ▼
                             data/snapshots.jsonl
                                   │
              report.py ──────────►┘ joins + summarizes by platform/tier/score band
```

- **`pons/outcomes.py`** — `record_alert(...)`; every scanner calls it at dispatch
  time. Writes one row per alert with the coin, score, alert-time price, and a
  `track` descriptor telling the daemon how to price it later.
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

## Reading it / acting on it

- Give it a few days so alerts mature past 24h before trusting the numbers.
- If a whole tier or platform shows negative median at every horizon, tighten its
  gate or drop it.
- If a single signal (e.g. paid-marketing, smart-money score) correlates with the
  winners, raise its weight in the `score_*` function; if not, lower it.
- Baselines: uses `price0` when the alert captured one, else the first snapshot;
  returns fall back to mcap when price is unavailable (bonding-curve coins).
