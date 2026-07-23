# launchpad-scanners

Source-level (ต้นน้ำ) coin scanners for six memecoin/AI-agent launchpads —
**vlad.fun**, **pons.family**, **flap.sh** (Robinhood Chain),
**Virtuals Protocol** (Base/Solana), **Arc DEX Scan** (Arc Mainnet) and
**pump.fun** (Solana). Each reverse-engineers the platform's data (on-chain
events and/or public API), backtests what actually predicts a coin pumping /
graduating, and ships a live scanner that surfaces the promising launches early.
Optional Telegram alerts.

> **Detection only.** These tools rank and alert. They never place a trade —
> that's yours to do manually. Winrates below are historical and not a promise;
> most memecoin launches fail. Manage your own risk.

## Platforms

### `pons/` — pons.family (fixed-supply, graduates at 4.2 ETH)
Launches are discovered on-chain from the factory's `TokenLaunched` event (the
public API went NXDOMAIN 2026-07-18). Best signal is **multi-factor
confirmation** from on-chain early trading. Backtested on 94 graduations vs 1,500
controls:

```
CONFIRMED rule (first 5 min):  rebuyers ≥ 6  &  net ETH ≥ 1.0  &  snipers ≤ 3
```
Real-world precision ~30% (41% out-of-time), ~55× the 0.54% base rate, fires
~44s after launch (graduation ~90 min later). See `pons/README.md`.

- `alert_pro.py` — **the live scanner** (multi-factor 🎯 CONFIRMED + 🔥 NEAR-GRAD → Telegram)
- `reputation.py` / `collect.py` — scheduled on-chain graduation, smart-wallet,
  and deployer-reputation refresh
- `backtest_multifactor.py`, `collect_onchain.py` — how the rule was found
- `scan.py` / `alert.py` — earlier velocity-only versions

### `vlad/` — shared Robinhood Chain RPC helper (not a scanner)
Stdlib JSON-RPC + event decoding against the QuickNode Robinhood endpoint,
imported by `pons/` and `flap/`. Named after vlad.fun, whose scanner and
backtest harness were removed; only `rpc.py` remains.

### `virtuals/` — Virtuals Protocol (AI agents, Base + Solana)
Fully open Strapi API with premium fields (mindshare, holder growth %, dev/top10
concentration, curve reserve → graduation progress). 🐣 EARLY traction +
🔥 NEAR-GRAD (42k VIRTUAL tier), chain-tagged alerts. See `virtuals/README.md`.

- `scan.py` — live API scanner (no RPC needed)

### `pump/` — pump.fun (Solana, the biggest launchpad)
~23k launches/day, so it watches the actively-traded feed and alerts on the
*climb*: 🐣 EARLY (young coin crossing the mcap bar, climbing near its ATH) +
🚀 GRADUATING (nearing the ~$69k curve completion). API-only. See `pump/README.md`.

- `scan.py` — live API scanner (no RPC needed)

### `bags/` — GMGN trench scanner (uncovered Robinhood launchpads)
Watches the Robinhood-chain launchpads none of the source scanners cover —
**bags, bankr, dyorswap, virtuals-on-robinhood** — via GMGN's Trenches
board (items arrive pre-enriched: smart/renowned counts, bot/rat rates,
honeypot+tax, X followers). 🐣 TRENCH EARLY (traction bar) + 🚀 TRENCH GRAD.
Needs `GMGN_API_KEY`. See `bags/README.md`. (`noxa` was dropped 2026-07-23 —
GMGN's `noxa` key is the dead V1; live noxa V2 has its own scanner in `noxa/`.)

### `noxa/` — noxa (Robinhood Chain), source-level via noxa.fi
noxa died (noxa.fun went NXDOMAIN 2026-07-18) and relaunched at **noxa.fi** on a
new factory ~2026-07-22 — the same domain-move pons made — immediately running
busier than pons (~205 launches/h). GMGN can't see the new factory (its `noxa`
key is the dead V1; V2 lives under `noxafi`), but noxa.fi ships a clean public
API (no auth, 240 req/min), so this is a **source-level** scanner, not a trench
rider. 🐣 NOXA EARLY (holders+volume bar — *not* the misleading `graduationPct`)
+ 🚀 NOXA GRAD. No API key. See `noxa/README.md` and `docs/research/noxa-fi-api.md`.

- `scan.py` — live API scanner (no RPC needed)

### `potato/` — potato.fm "Potato Pad" (Robinhood Chain), source-level
A Robinhood-chain launchpad **aggregator** (several pad factories, `kind`
`direct`/`curve`) that plants coins straight into a locked Uniswap V3 position,
live from block one. Its own Next.js origin ships an open, urllib-reachable API
(not Cloudflare-walled like long.xyz), and the pad is small enough (~60 tokens
all-time) that one page of `/api/tokens` *is* the complete board — so this is a
source-level scanner with 100% coverage, not a trench rider. The Growing feed's
only per-token traction is `volume24Usd` (socials inline; no holders/mcap — the
site derives mcap from the V3 pool over RPC), so the bar is **volume + age**;
the `/api/ancient` feed is richer (fdv/liquidity) and drives the GRAD tier.
🥔 POTATO EARLY (young coin crossing the volume bar) + 🚀 POTATO GRAD (surfaces
in Ancients on a real WETH pool). No API key. Prices outcomes via the shared
`gmgn` snap (potato coins are gmgn-indexable V3 tokens). See `potato/README.md`
and `docs/research/potato-fm-api.md`.

- `scan.py` — live API scanner (no RPC needed)

### `long/` — long.xyz (Robinhood Chain, stock-token launches)
The busiest launchpad on GMGN's robinhood trenches board (~2.4 launches/min,
graduates at $200–400K mcap). Its own API is Cloudflare-blocked to `urllib`, so
this rides GMGN's native `longxyz` pad — which surfaces new mints ~6s old — using
`bags/scan.py`'s implementation as a **separate instance**: sharing the bags feed
call would have cost four other launchpads 46 of their 50 board rows. Tighter bar
than bags (40 holders / $10K / 30%). See `long/README.md`.

- `scan.py` — thin profile over the shared trench scanner

### `agent/` — Hermes AI second-opinion layer
`analyst.py` tails the alert stream and runs **Hermes Agent** headlessly with
the `memecoin-dd` skill on each CONFIRMED / TRENCH alert: GMGN forensics → X
account quality → narrative → strict `VERDICT/CONF/WHY` block, posted to
Telegram as a 🤖 AI-DD follow-up and recorded for `report.py --by-verdict`
to score against real outcomes. Advisory until it proves lift. See
`agent/README.md` + `docs/hermes-agent-integration.md`.

### `tracker/` — alert outcome tracking (feedback loop)
Records every alert, follows each coin's price at 5m…48h, and reports whether
the scores actually predicted pumps — the data for refitting score weights.
`report.py` slices returns by platform / tier / score band. See `tracker/README.md`.

### `watchdog/` — feed-ingest health monitoring
Every installed scanner writes an atomic heartbeat only after its primary feed
responds successfully. The watchdog discovers scanner and scheduled collector
LaunchAgents, sends one Telegram DOWN edge when a heartbeat goes stale and one
UP edge on recovery, and exposes its own heartbeat. See `watchdog/README.md`.

### `arc/` — Arc DEX Scan (Arc Mainnet, chainId 5042)
Small, young chain. Open Railway backend with a `/launches` feed + `/token`
enrichment. 🐣 EARLY traction + 🚀 LAUNCHED (migration) tiers, API-only. See
`arc/README.md`.

- `scan.py` — live API scanner (no RPC needed)

### `flap/` — flap.sh (bonding curve, trade-tax tokens)
The busiest launchpad on the chain (~5k launches/day). New tokens are caught
**on-chain** (mint events + the `...7777` vanity suffix from the factory);
the reverse-engineered `batman.taxed.fun` API enriches candidates with
progress %, holders, **buy/sell tax bps** (honeypot gate) and the platform's
own `isLowRisk` (FAC) flag. See `flap/README.md`.

- `scan.py` — live scanner (🐣 EARLY traction + 🔥 NEAR-GRAD → Telegram)

## Quick start

```bash
# pons
python3 pons/collect.py            # on-chain graduation + reputation refresh
python3 pons/alert_pro.py --dry-run   # multi-factor scanner, print alerts
```

Pure stdlib Python 3 — no dependencies.

## Telegram alerts (pons)

Copy `pons/.env.example` → `pons/.env` and fill in your bot token + chat id
(from @BotFather; chat id via `https://api.telegram.org/bot<TOKEN>/getUpdates`).
The `.env` and any `telegram.json` are gitignored. Then:

```bash
python3 pons/alert_pro.py --test   # verify credentials
nohup python3 -u pons/alert_pro.py > pons/data/pons_pro.log 2>&1 &   # run 24/7
```

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # once
.venv/bin/python -m pytest                                              # run
```

The venv is test-only — the scanners stay stdlib-only and keep running on the
system `python3` under launchd.

`tests/` pins the Tier A scoring behaviour (shipped 2026-07-19) for pons, pump
and virtuals, so the pons discovery rebuild and every later scoring change
happens under a safety net. The tests assert **separation and direction, never
exact score values** — the weights are provisional until the Tier B refit, and
pinning magnitudes would break every recalibration for no reason. Profiles come
from the measured medians in `docs/research-notes-raw.md` (waves 20-24).

## Data

Small derived artifacts (smart_wallets, graduations, reputation) are
committed. Large raw datasets (full launch lists, event/swap dumps) are gitignored
— regenerate them with each folder's `collect*.py`.

## GMGN enrichment (optional)

With a GMGN Agent API key (`~/.config/gmgn/.env`, read-only — see
`pons/gmgn.py`; **never** set `GMGN_PRIVATE_KEY`, that unlocks trading), every
alert row in `tracker/data/alerts.jsonl` is auto-enriched with GMGN forensics:
cross-platform smart-money/renowned wallet tags, bot/rat/bundler rates, dev
reputation (tokens created, best prior ATH, twitter delete history) and
copycat detection. Collected-not-gated — `report.py` decides which fields earn
score weight. pons CONFIRMED alerts also display a 🧬 GMGN line. Covers
robinhood/sol/base/eth/bsc (not arc). Research: `docs/hermes-agent-integration.md`.

## Notes

- Both launchpads are on Robinhood Chain (chainId 4663). The public
  `rpc.mainnet.chain.robinhood.com` rejects `urllib` (403); the code uses a
  QuickNode endpoint pulled from the vlad.fun bundle. Swap in your own RPC if it
  rotates.
- Undocumented, fast-moving platforms — endpoints and contracts may change. Re-run
  the collect/backtest steps as data accumulates to refit thresholds.
