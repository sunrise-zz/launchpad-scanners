# pons.family coin scanner — graduation-momentum tracker

Goal: catch interesting new coins on **pons.family** (a fixed-supply token
launchpad on **Robinhood Chain**, same chain as vlad.fun) as early as possible.

> **Scope guard:** this only **detects and ranks** coins. It never trades.

## Why pons is different from vlad.fun

| | vlad.fun | pons.family |
|---|---|---|
| model | single "pump" bonding curve | factory deploys token + AMM pool, graduates at **4.2 ETH** paired |
| data | had to decode raw on-chain events | same now — the REST API died 2026-07-18; we decode `TokenLaunched` |
| size (this snapshot) | 286 coins, 3 graduations | **17,581 coins, 94 graduations** |
| best signal | reconstruct early buy momentum | **graduation-progress velocity** (API hands us the progress) |

**That API is gone.** `pons.family` has been NXDOMAIN since ~2026-07-18 while
the factory kept launching (~148/hour, measured on-chain), so the table below is
history — discovery decodes events now, exactly like vlad.fun always did.

| endpoint | use |
|---|---|
| `GET /api/pons-launches/latest` | ~~new-coin feed~~ — replaced by `TokenLaunched` |
| `GET /api/pons-launches/recent-buys` | 100 most-active tokens with `graduationProgressPct`, `pairedPrincipalEth` — the **momentum feed** behind NEAR-GRAD (dead while the domain is) |
| `GET /api/pons-launches/graduations` | graduated tokens + timestamps (success labels) |
| `GET /api/pons-launches` | full list (~15MB, current outcomes) |
| `GET /api/noxa-market?token=` | per-token market state (reserves, latest buy) |

On-chain (now the default source): RPC
`https://rpc.mainnet.chain.robinhood.com`, factory
`0xA5aAb3F0c6EeadF30Ef1D3Eb997108E976351feB`, pair token (WETH)
`0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73`. Launch discovery reads the
factory's `TokenLaunched` event (topic0 `0xdb51ea9a…`), which carries the token,
deployer, pool and pair token, plus `initialBuyAmount` (the dev's block-0 buy)
and `restrictionsEndBlock` (anti-sniper window — an **L1** block number, since
this is an Arbitrum Orbit chain, so never compare it to our L2 `blockNumber`).
`--discovery-source http` switches back if the domain ever returns.

Discovery keeps a block cursor in `data/discovery_cursor.json` so a restart
resumes where it stopped instead of re-basing at head — the difference between
a silent coverage gap and none. Each poll reads a bounded slice (5000 blocks;
the RPC answers 10k in ~1.1s and 413s above that), so an outage drains over
several polls rather than one oversized query: measured ~2600 blocks/s, ~260x
realtime, so a 6h gap closes in ~80s. A cold start with no cursor begins at head
minus the watch window (15 min, matching `alert_pro.ACTIVE_SECS`) — enough to
catch everything still alert-eligible, without replaying history. A cursor more
than 12h behind is skipped rather than drained, with the skipped range logged:
that backlog can no longer alert, and draining a week of it would cost ~38 min
blind to live launches. `PONS_DISCOVERY_CURSOR` overrides the path.

## Findings

1. **Launch-time metadata gives only weak lift** (same lesson as vlad):
   - `has description` → 0.72% graduation vs 0.30% without (~2.4x)
   - deployer with a prior graduation → 0.96% vs 0.53% (~1.8x, only 312 such launches)
   - `initialBuyWei` barely separates winners.
   None of these is strong enough to predict from alone — base rate is 0.54%.
2. **The signal is graduation velocity.** A single API snapshot has no velocity;
   polling `/recent-buys` and differencing `pairedPrincipalEth` over ~15s cleanly
   surfaces coins accelerating toward the 4.2 ETH threshold (validated live: e.g.
   a coin climbing +1.58 ETH/min from 0.93→1.34 ETH in 15s — ~2 min from graduating).
3. **Lead time exists.** Graduations take a median ~92 min from launch (p25 ~18 min,
   p75 ~8 h), so a fast climber is catchable well before it pops. ~25% graduate
   inside ~18 min, so poll fast (≤15s).

## Multi-factor CONFIRMED logic (`alert_pro.py`) — the good stuff

Backtested on **on-chain early-window swaps** (Uniswap-V3 pools, first 10 min)
for all 94 graduated coins + 1,500 random controls, corrected to the real 0.54%
base rate. GMGN-style indicators tested: smart money, snipers, bundlers, first-N
buyers, dev history, concentration, conviction.

**Shipped rule** (first 5 min of trading):

```
rebuyers >= 6      # wallets that bought 2+ times = conviction (GMGN "insiders keep adding")
net_weth >= 1.0    # net ETH flowing INTO the pool
snipers <= 3       # buys in first 2s; bot-sniped launches fail
```

| metric | value |
|---|---|
| real-world precision (winrate to graduation) | **~30%** (in-sample), **40.7%** out-of-time test |
| recall | 43% (in-sample), 84% on recent data |
| lift over base rate | **~55x** |
| median fire time | **44s** after launch (p25 = 24s) |
| median launch→graduation | ~90 min → huge lead time |

What separates winners from losers (medians, first 5 min):

| feature | graduated | non-grad | note |
|---|---|---|---|
| unique buyers | 36 | 4 | crowd arrives immediately |
| rebuyers (bought 2+) | 10 | 0 | **strongest single signal** — conviction |
| top buyer share | 7% | 50% | one-whale coins die |
| time to 5 buyers | 20s | never | speed of crowd |
| smart-money hits | 8 | 2 | wallets that entered past winners early |
| sell/buy ratio | 0.38 | 0.67 | early dumping kills |
| deployer prior launches | 0 | 4 | **serial deployers = spam factories** |
| snipers (≤2s) | 1 | 1 | equal medians, but >3 snipers → almost never graduates |

Non-findings (tested, weak): initial buy size, has_description/logo (both ~1.0),
bundle_max (same-block multi-buyer is crowd rush here, not insider bundling).

`data/smart_wallets.json`: 1,267 wallets that early-bought (≤3 min) ≥2 different
later-graduated coins — the top one entered 41 winners. Used as a live insight
(not a hard filter).

## Scanner logic (`scan.py`)

Stateful. Each poll records `(t, pairedETH, progress%)` per token, then:
- **rank** by `0.6·progress% + 40·velocity(ETH/min) + reputation + desc bonus`
- **alert `CLIMBING`** when velocity ≥ 0.10 ETH/min and progress ≥ 10%
- **alert `NEAR-GRAD`** when progress ≥ 70% and still moving (about to pop)
- filter to fresh coins (launched < 45 min) unless already near graduation
- enrich symbol/age/deployer from the `collect.py` launch snapshot

## Files

| file | purpose |
|---|---|
| `api.py` | launch discovery (`TokenLaunched` → `latest()`), symbol lookup, + the legacy REST endpoints / factory consts |
| `collect.py` | snapshot launches + graduations, print base-rate dynamics, write `deployer_grads.json` |
| `scan.py` | live scanner — poll momentum feed, compute velocity, rank, alert (terminal) |
| `alert.py` | 1s loop → Telegram — velocity-only CLIMBING / NEAR-GRAD (noisier, superseded) |
| `alert_pro.py` | **PRO: multi-factor CONFIRMED → Telegram** — on-chain factors + insights (use this) |
| `telegram.py` | tiny Telegram Bot API sender (reads creds from env `.env` or `data/telegram.json`) |
| `collect_onchain.py` | pull early-window pool swaps for graduated+control coins (backtest dataset) |
| `backtest_multifactor.py` | GMGN-style factor search → the CONFIRMED rule above |

## Telegram alerts (`alert.py`)

Polls every second and pushes a message the moment a coin starts CLIMBING
(velocity ≥ 0.1 ETH/min) or hits NEAR-GRAD (≥70% progress, still moving). Each
message shows progress, paired/threshold ETH, velocity, ETA to graduation, price
and a Blockscout link. A 180s per-token cooldown prevents spam.

**Setup** — provide bot credentials one of two ways (the file is gitignored):

```bash
# option A: env vars
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="987654321"

# option B: config file  analysis/pons/data/telegram.json
{ "token": "123456:ABC...", "chat_id": "987654321" }
```

Get the token from @BotFather; get your chat_id by messaging the bot then reading
`https://api.telegram.org/bot<TOKEN>/getUpdates` (the `chat.id` field).

```bash
python3 analysis/pons/alert.py --test      # verify credentials (sends one message)
python3 analysis/pons/alert.py             # live, 1s, Telegram
python3 analysis/pons/alert.py --dry-run   # print alerts instead of sending
python3 analysis/pons/alert.py --min-vel 0.2 --near 60   # tune sensitivity
```

With no credentials it auto-falls back to dry-run (prints the messages).

## Run

```bash
python3 analysis/pons/collect.py    # snapshot + reputation table (run first)
python3 analysis/pons/scan.py       # live graduation-momentum watchlist
python3 analysis/pons/scan.py --once --interval 12
```

## Caveats

- The small feeds (`/recent-buys`, `/latest`) do **not** rate-limit — tested 40
  back-to-back requests, all 200, ~160–500ms each. The 403 seen earlier was the
  heavy `/api/pons-launches` (15MB) endpoint, which `collect.py` hits once; never
  poll that. Use a browser User-Agent (already set).
- **Useful poll floor ≈ 1s**: the chain produces a block ~every 1–1.4s, so the
  feed data only changes ~0.7×/sec. Polling faster than ~1s returns duplicate
  snapshots. Default interval is 2s; drop to 1s to catch the fastest climbers
  (some graduate ~2 min after launch).
- No longitudinal backtest of the velocity thresholds is possible from a single
  snapshot — they're set from the graduation-pace dynamics, not fitted. Tune them
  by watching the live feed. To do a real backtest, log `/recent-buys` over time.
- Metadata-based cold-start prediction is weak here; the value is the live velocity
  feed, not pre-launch scoring.
