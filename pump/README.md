# pump/ — pump.fun scanner (Solana)

The biggest memecoin launchpad anywhere: **~16 new tokens/minute (~23k/day)**.
Alerting on creation is pointless — 99%+ instant-rug. The value is catching the
few that get **traction** early: a coin like "Jimothy The Raccoon" (which reached
~$17.5M) crosses every market-cap bar on its way up, so we watch the
*actively-traded* feed and alert on the climb, not the birth.

## Data source

pump.fun v3 REST — open, needs a browser UA (Cloudflare-fronted):

| endpoint | use |
|---|---|
| `/coins?sort=last_trade_timestamp&order=DESC&limit=100` | coins trading **now** — the momentum feed the scanner polls |
| `/coins?sort=created_timestamp&order=DESC` | raw new feed (intentionally unused — too noisy) |
| `/coins/{mint}` | full detail (the tracker prices coins from here) |

Scored fields: `usd_market_cap`, `reply_count` (community), `ath_market_cap`
(climbing vs dumping), `king_of_the_hill_timestamp`, `complete` (graduated),
`created_timestamp`, `twitter`, `nsfw`, bonding-curve reserves.

## Alert tiers (⛓ SOLANA · 💊 pump.fun)

- 🐣 **PUMP EARLY** — a coin younger than `--watch-hours`, still on the curve,
  crossing the mcap bar (default $20k) with **positive mcap velocity** and
  trading **at/near its ATH** (climbing, not a dumping corpse). Scored on
  velocity, replies, KOTH, ATH proximity, X.
- 🚀 **PUMP GRADUATING** — curve progress ≥ `--near`% of the ~$69k completion
  point, still healthy. We deliberately do **not** alert on the `complete` flag:
  a graduated coin is either already mooned (missed) or a post-grad corpse.

Key guards learned from testing: silent seed on first poll (no startup backlog),
and a not-dumping filter (`mcap ≥ 0.6·ATH`) so dead coins that graduated long ago
don't fire when someone pokes a trade.

## Run

```bash
python3 pump/scan.py --dry-run
python3 pump/scan.py                          # live -> Telegram (reuses pons/.env)
python3 pump/scan.py --min-mcap 30000 --near 90    # stricter
python3 pump/scan.py --include-nsfw           # include nsfw coins
```

Bars are v1 heuristics — every alert is recorded via `pons/outcomes.py` and the
tracker follows it, so thresholds can be refit from real outcomes.
