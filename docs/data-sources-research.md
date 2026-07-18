# Data sources research — improving winrate & coverage (2026-07-17)

Probed live: DexScreener API, GMGN, flap.sh. Goal: more signal inputs for the
pons/vlad scanners + a possible third launchpad source.

## What the scanners use today

- pons.family API — launches, graduation progress
- On-chain via QuickNode RPC — rebuyers, net ETH, snipers, net-hold
- Blockscout — holder count, dev%/top1%/top10% concentration
- DexScreener `tokens/v1` — **only** a binary "has socials" check

## 1. DexScreener (api.dexscreener.com) — open, no auth

### `GET /tokens/v1/robinhood/{addr}` (300 req/min) — already called, fields unused

Verified live (PONSDOG):

```json
"txns":  {"m5": {"buys": 49, "sells": 31}, "h1": {"buys": 430, "sells": 174}, ...}
"volume": {"m5": 2961.21, "h1": 40583.41, ...}
"priceChange": {"m5": -16.38, "h1": 56.97, ...}
"liquidity": {"usd": 10250.13, ...}, "fdv": ..., "marketCap": ..., "pairCreatedAt": ..., "boosts": ...
```

Unused signals sitting in a response we already fetch:
- **Buy-pressure ratio** `buys/sells` per m5/h1 — momentum quality, not just size
- **Volume acceleration** `vol.m5*12 vs vol.h1` — is interest growing right now
- **Liquidity floor** — drop thin pools where any pump is exit-proof
- Social **depth** (info.socials types + websites count), not just presence

### Paid-marketing endpoints (60 req/min) — strongest new signal family

- `GET /token-profiles/latest/v1` — teams that filled/paid a DexScreener profile.
  Live check: 11 of latest 30 were robinhood chain. Doubles as a discovery feed.
- `GET /token-boosts/latest/v1`, `/token-boosts/top/v1` — paid boosts with
  `amount`/`totalAmount`. Live: 9/30 robinhood.
- `GET /orders/v1/robinhood/{token}` — per-token payment history
  (`tokenProfile` / boosts, with `paymentTimestamp`, `status`). Team spending
  real money on marketing ≈ intent to push the coin; timestamp can lead price.

## 2. GMGN (gmgn.ai) — blocked for scripts

`/defi/quotation/...` returns 403 (Cloudflare JA3/bot check) for curl/urllib;
works only in a real browser. Not worth a 24/7 headless dependency.

What GMGN actually adds (smart-money PnL tags, dev rug history, sniper/insider
tags) we can **self-compute** from data we already collect:
- We have every early swap per wallet → wallet realized PnL over past launches
  → upgrade `smart_wallets` from a binary list (1,267 flat) to a **scored**
  reputation table → `weighted_rebuyers = Σ score(wallet)` instead of a count.
- Dev rug history: deployer address → past launches → did top wallet dump
  pre-graduation. We already track dev-spam; extend to "dev's coins' outcomes".

## 3. flap.sh — third launchpad on Robinhood chain (found its backend)

Backend: **`https://batman.taxed.fun`** (found via network capture; the magic
query param `_refresh=YYYYMMDD` is required). Verified robinhood-chain: RWA
token matches robinhoodchain.blockscout holders.

Endpoints (all GET, JSON):
- `/v3/board?limit=20&_refresh=...` — trending, sorted volume24h; cursor paging
- `/v3/board/graduatinghot?limit=20&_refresh=...` — **near-graduation feed** (ready-made NEAR-GRAD)
- `/v3/board?isLowRisk=true&...` — platform's own safety filter
- `/v3/coin/{addr}?_refresh=...` — full detail

Per-coin fields (verified): `progress` %, `holders` count + **inline top-20
holder list with amounts** (no Blockscout round-trip), `liquidity`,
`volume24h`, `change5m/1h/4h/24h`, `marketCap`, `creator`, `tweet`,
`createdAt`, pool address, bonding-curve params (`r,h,k,reserve,
dexThreshSupply`), and uniquely:
- **`tax.buyTaxBps` / `tax.sellTaxBps`** — flap tokens can carry trade tax;
  high sell tax = soft honeypot. Hard gate candidate.
- **`isLowRisk`** — "Flap Assurance Check (FAC)" badge from the platform
- `isInnovation`, `mode`, `version`

Caveats:
- Cloudflare blocks plain curl/urllib after a few requests (first request
  succeeded, subsequent ones challenged). A scanner needs either browser-context
  polling, TLS-impersonation, or the **pure on-chain route**: every flap token
  address ends in `...7777` (vanity CREATE2 → single factory), so factory events
  via the QuickNode RPC (same infra as vlad) enumerate launches; Blockscout
  covers holders; only tax/isLowRisk/progress need the API occasionally.
- All observations 2026-07-17; undocumented backend, may change.

## Status — ALL IMPLEMENTED 2026-07-17

1. ✅ **Buy/sell-ratio + volume-accel + liquidity display** — in `pons/alert_pro.py`
   (`momentum_line`); on-chain bs-ratio and DexScreener m5/h1 shown in every
   alert. Gates exist (`--min-bs-ratio`, `--min-liq-usd`) but default OFF until
   alert history is enough to fit thresholds.
2. ✅ **Paid-marketing** — `dex_paid()` (orders/v1) shown as `💰 paid:` in
   alerts + 💰 MARKETING feed alerts (profiles/boosts latest, 75 s poll,
   startup backlog seeded silently).
3. ✅ **Weighted smart-wallets** — `smart_score` (Σ grad-count per hitting
   wallet) in CONFIRMED alerts; `--min-smart-score` gate default off.
4. ✅ **flap.sh scanner** — `flap/scan.py`: on-chain mint+suffix detection,
   cohort transfer traction, tax/FAC gates, graduatinghot NEAR-GRAD. Deployed
   as LaunchAgent `com.sunrise.flap-scanner`. Bar fit from first 4.5 h of
   collected data (2,512 launches → ≥60 recips ≈ ~20 alerts/day).
5. ✅ **Social depth** — `depth`/3 in alerts, `--min-socials` gate.

Next: let `flap/data/events.jsonl` + alert history accumulate a few days, then
backtest the soft gates and turn them on with fitted thresholds.

---

# Virtuals Protocol (app.virtuals.io) — probed 2026-07-17

AI-agent launchpad on **Base** (VIRTUAL quote token). Backend
`https://api2.virtuals.io` — **fully open**: plain urllib passes, no
Cloudflare, standard Strapi query syntax. 53,966 agents on BASE; new
UNDERGRAD (bonding-curve) agents appear every ~10–20 min (~100/day, some
duplicate rows).

## Endpoints (verified live)

| endpoint | gives |
|---|---|
| `/api/virtuals?filters[chain]=BASE&sort=createdAt:desc` | **new-agent stream** |
| same list, `sort=volume24h:desc` etc. | momentum board (sort works: volume24h, holders, liquidity…) |
| `/api/virtuals/{id}` | + characterDescription, projectMembers, overview, metadata |
| `/api/geneses?...` | Genesis launches — **dormant** (last FINALIZED Oct 2025; 363 total, recent all CANCELLED) |
| `/api/geneses/parameters` | graduation reserve tiers: 21k / 42k / 100k VIRTUAL |
| `/api/virtuals/influence-metrics/{ids}` | per-agent influence metrics |

Quirk: `filters[status]=...` is silently ignored (total unchanged) — filter
client-side on the `status` field (UNDERGRAD = on curve, graduated agents have
`tokenAddress` + `lpCreatedAt` set).

## Fields no other platform gives us

Per agent, in the LIST response (no extra calls needed):
- **`mindshare`** — Kaito-style attention score (unique to Virtuals)
- **`holderCountPercent24h`** — holder growth rate, pre-computed
- **`devHoldingPercentage`**, **`top10HolderPercentage`** — concentration
  gates for free (we compute these ourselves on Robinhood chain)
- `holderCount`, `volume24h`, `netVolume24h`, `priceChangePercent24h`,
  `mcapInVirtual`, `liquidityUsd`, `totalValueLocked`
- `isDevCommitted`, `isVerified`, `socials`, `category`, `cores`
- `launchInfo.antiSniperTaxType`, `launchInfo.airdropPercent`, `launchMode`
- `createdAt` vs `launchedAt`, `preToken` (curve) vs `tokenAddress` (post-grad)

## Scanner blueprint (API-only viable — no Base RPC needed for v1)

1. Poll `sort=createdAt:desc` (~30 s) → register new UNDERGRAD agents.
2. Track young cohort via the sorted list / per-id fetch: holder growth,
   net volume, mindshare; gates on dev%/top10%/isVerified/antiSniperTax.
3. 🐣 EARLY alert on traction bar; 🔥 NEAR-GRAD as `mcapInVirtual` approaches
   the 42k-VIRTUAL reserve tier.
4. DexScreener fully supports Base → the existing paid-marketing (`orders/v1`)
   and momentum enrichments reuse unchanged for graduated agents.
5. Genesis endpoints: leave a cheap watcher (1/day) in case the format revives.

Note: launch volume is ~50× lower than flap but each launch carries far richer
metadata; the AI-agent meta cooled after Oct 2025 (dead Genesis pipeline) —
signal quality per launch may be higher, but validate winrate from collected
outcomes before trusting it.
