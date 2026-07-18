# virtuals/ — Virtuals Protocol scanner (Base + Solana)

AI-agent launchpad (app.virtuals.io). Agents launch on a bonding curve
(**UNDERGRAD**, trades via `preToken`) and graduate to a Uniswap LP once the
curve reserve reaches **42k VIRTUAL** (tiers 21k/42k/100k). ~100 launches/day
on BASE; SOLANA has been dormant since 2026-06 (kept on a cheap 10-min poll).

## Data source

`https://api2.virtuals.io/api/virtuals` — fully open Strapi (plain urllib, no
Cloudflare). The list response alone carries fields the Robinhood-chain
platforms never give us:

- `mindshare` — attention score (unique to Virtuals)
- `holderCount` + `holderCountPercent24h` — holder growth pre-computed
- `devHoldingPercentage`, `top10HolderPercentage` — concentration for free
- `totalValueLocked` — curve reserve in VIRTUAL → **graduation progress = TVL/42000**
- `volume24h`, `netVolume24h`, `priceChangePercent24h`, `liquidityUsd`
- `isVerified`, `isDevCommitted`, `socials`, `category`,
  `launchInfo.antiSniperTaxType`

Quirks: `filters[status]` is silently ignored (filter client-side: on-curve =
`preToken` set & `tokenAddress` null); the createdAt feed has duplicate rows
(dedupe by `id`).

## Alert tiers — every alert carries a ⛓ chain tag

- 🐣 **VIRTUALS EARLY** — tracked-from-birth agent crossing the traction bar
  (default ≥25 holders & ≥1000 VIRTUAL reserve), gated on dev ≤30% /
  top10 ≤95% concentration.
- 🔥 **VIRTUALS NEAR-GRAD** — any on-curve agent reaching ≥70% of graduation,
  found via the volume board (catches agents older than the scanner), once per
  agent.

The bar is a v1 heuristic — launches/alerts/expiries append to
`data/events.jsonl` for a proper refit once outcomes accumulate.

## Run

```bash
python3 virtuals/scan.py --dry-run
python3 virtuals/scan.py               # live -> Telegram (reuses pons/.env)
python3 virtuals/scan.py --min-holders 50 --near 80    # stricter
```
