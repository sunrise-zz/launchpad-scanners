# arc/ — Arc DEX Scan scanner (Arc Mainnet, chainId 5042)

arcdexscan.com is a token explorer + launchpad on **Arc Mainnet**
(RPC `5042.rpc.thirdweb.com`, explorer `arcscan.app`). Small, young chain —
probed 2026-07-17 it had 225 tokens and ~$4K/24h volume — so alerts are rare
by nature; the value here is being early on a fresh ต้นน้ำ source.

## Data source

Backend `web-production-efe27.up.railway.app` — **fully open** (Railway, no
Cloudflare, plain urllib):

| endpoint | gives |
|---|---|
| `/launches?limit=N` | newest deploys: token, deployer, pool, name, symbol, createdAt |
| `/token/{addr}` | launched flag, verified, price, mcap, fdv, liquidityUsdc, volume5m/1h/24, buys24, sells24, traders24, txns24, socials, pools |
| `/tokens?sort=volume24&window=24h` | full market board (momentum fallback) |

The `/launches` feed **churns** — older tokens rotate back in — so the scanner
gates alerts on `createdAt`: anything already on-chain at startup is tracked as
context but never replayed as a fresh launch.

## Alert tiers (chain tag ⛓ ARC, platform 🛰️ arcdexscan)

- 🐣 **ARC EARLY** — a token born after startup crossing the traction bar
  (default ≥8 traders24 & ≥$200 liquidity), scored on buy/sell balance,
  socials, verified.
- 🚀 **ARC LAUNCHED** — a tracked token's `launched` flag flips True (migrated
  from the deploy pool to a full DEX pool — Arc's "graduation").

Both share the standard scored alert format (score/100 + meter + verdict).
The bar and score weights are v1 heuristics — every launch/alert/expiry is
logged to `data/events.jsonl` to refit once outcomes accumulate.

## Run

```bash
python3 arc/scan.py --dry-run
python3 arc/scan.py                       # live -> Telegram (reuses pons/.env)
python3 arc/scan.py --min-traders 15 --min-liq 500   # stricter
```
