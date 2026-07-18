# Research → Build Plan & Pipeline (action tracker)

Created 2026-07-19 after an overnight research sprint (11 waves in
`research-notes-raw.md`). Session limit hit → this file is the handoff so work
resumes cleanly. **Nothing here is decided/committed** — it's a ranked menu +
sequencing. Each build item is a PROPOSAL pending the user's go-ahead.

Status legend: ☐ todo · ◐ partial/in-progress · ☑ done · ⏸ blocked/waiting

---

## PART 0 — Finish the research (re-run after 7am reset)

Three agents died on the session limit mid-run — relaunch these first:

- ☐ **EVM-specific detection** (Base/Robinhood): GoPlus token_security API fields
  (buy_tax/sell_tax/cannot_sell_all/honeypot/blacklist/slippage_modifiable),
  honeypot.is buy-sell simulation, Uniswap V2/V3 LP add/remove/lock (Mint/Burn/
  Sync events) real-time rug detection, EVM funder-graph via Basescan/Blockscout,
  Clanker/Zora on-chain launch detection. (agent prompt saved in chat history)
- ☐ **ML feature-combination + backtesting methodology**: model choice for extreme
  imbalance (GBM vs logistic, AUPRC not AUC), score calibration (isotonic/Platt,
  weight-of-evidence log-odds), walk-forward/out-of-time, look-ahead + survivorship
  handling, online refit for base-rate drift, signal decorrelation.
- ☐ **Public alpha-wallet / KOL datasets**: kolscan, Dune adam_tehc/pump-fun-alpha-
  wallets, Cielo/Birdeye/GMGN leaderboards, SolanaTracker /top-traders, bootstrap
  recipe for a self-grown smart-money list + EVM (Base) sources.

Queued angles not yet run (lower priority):
- ☐ Telegram alpha-caller channels with track records (signal aggregation)
- ☐ Time-of-day / regime / market-beta context signals (base-rate normalization)
- ☐ VOLTA bundlemaps staggered-bundle thresholds (was HTTP 522 — retry)
- ☐ Verify Robinhood chainId (agent claimed 4663; Arc=5042 is a DIFFERENT chain —
  confirm pons/flap configs point at the right RPC)

---

## THE ORGANIZING PRINCIPLE (from all 11 waves)

1. **Raw activity is what bots manufacture.** Velocity/volume/holders/transfers —
   what we alert on — is faked by bundlers/volume-bots. The winrate lives in the
   **organic-share** transform of each (see meta-table in research-notes-raw.md).
2. **Two winner archetypes need two score models**: (A) organic cold-fermentation
   (price leads social, slow accumulation — on-chain detects early) vs (B)
   narrative-catalyst (social leads price — needs mindshare detection).
3. **Several of our current checks are ALREADY defeated** by evasion (same-slot
   bundle → stagger; concentration → <1% dispersion; serial-deployer → hop
   funding). The **master counter is recursive multi-hop funder-graph clustering**
   — it re-arms concentration + sniper + serial-deployer + entity-concentration at
   once. This is the single highest-leverage build.
4. **Non-linear, not monotone**: sniper/bundler count is a U-curve (0 = worst,
   11-50 = best); insider concentration is variance (size-down, not exclude);
   fast-fill <30min is BEARISH not bullish.
5. **Validate before trusting**: base rates drift; our tracker has survivorship
   bias; hand-weights are guesses. Build the measurement loop alongside the signals.

---

## PART 1 — Quick wins (computable from data we already pull; low effort)

Ordered by impact × ease. All PROPOSALS.

- ☑ Capital efficiency (ETH/buy) — pons `score_confirmed` [done 07-19]
- ☑ Telegram-weighted socials — pons [done 07-19]
- ☑ GMGN organic overlay (bundler/rat/sniper-hold/bot) — pump `score_coin` [done]
- ☐ **Wash-adjusted volume via price-impact** (research #B4): realized price-move
  per $ volume (Kyle-lambda) + unique-address diversity vs trade count. Turns our
  volume/buy-sell into real-money features. pons has swap data; flap/pump via API.
- ☐ **Trades-to-graduation velocity + breakeven gate** P(grad) > (vSOL/115)²
  (pump — strongest single graduation predictor; we have curve data).
- ☐ **Score the GMGN fields we fetch but ignore**: rug_ratio (>0.3 hard-stop),
  is_wash_trading, creator_token_status (creator_close = de-risk), sniper_count
  (>20 danger, distinct from sniper70), the market-signal feed (type 12 SmartBuy /
  type 10 BundlerSell + signal_times), visiting_count (attention), history_highest_
  market_cap (drawdown-from-ATH). pump/flap already call gmgn.snapshot.
- ☐ **Sniper/bundler U-curve recalibration** (0 and >50 both bad; 11-50 sweet spot)
  — pump/flap/pons scoring. Cheap, evidence-backed (wave 9).
- ☐ **TG liveness check** (msg-velocity via Telegram API) — upgrade "has TG" to
  "TG is live"; attached-but-dead = rug tell. Free.
- ☐ **Dev initial-buy size** as a separate positive axis from dev% (pons: parse
  create tx; >10 SOL-equiv = strong; keep dev% penalty separate). Model as
  "moderate buy GOOD, extreme hold BAD."
- ☐ **Post-graduation 20-min caution window** (73% drop <40% of migration) — a
  timing/exit annotation on GRADUATING alerts.
- ☐ **Recalibrate pons NEAR-GRAD** if re-enabled: it's late by nature; only the
  organic-archetype version (velocity + real buyers, not progress%) has edge.

---

## PART 2 — Funder-graph clustering (the master build; medium-large infra)

The highest-leverage item. Once built, it powers many signals at once.

- ☐ **EVM funder-graph** (Robinhood/Base): trace native-token funding of buyer/
  deployer wallets via Blockscout/Basescan, multi-hop (k≥3), find common ancestor;
  exclude CEX/known addresses. Flag pass-through hops (near-zero net, 1-in/1-out).
- ☐ **Solana funder-graph** (pump): Helius `funded-by` (single-hop) → extend to
  multi-hop; combine with same-tx co-purchase + shared Jito bundle_id (MELT's 3
  heuristics).
- ☐ **Entity-clustered concentration delta**: recompute top-10 after collapsing
  wallets into funder-clusters; the JUMP (+24pp regime = high-risk) is the feature.
- ☐ **Deployer→sniper funding-link** (Pine): flag creation-block buyers funded by
  the deployer (near-deterministic rug; also a positive copytrade signal flipped).
- ☐ **Launch-template fingerprint**: hash (bundle wallet count, tip amount, stagger
  cadence, LUT setup, metadata style) to link serial operators across fresh wallets.
- Counters it re-arms: concentration (vs <1% dispersion), sniper (vs multi-wallet),
  serial-deployer (vs hop funding). Sources: godmode code, MELT, Bubblemaps Magic Nodes.

---

## PART 3 — Jito bundle ground-truth (Solana/pump; medium)

- ☐ **Ground-truth bundle detection**: getTipAccounts + getBlock same-slot
  contiguity ending at a tip transfer = atomic bundle (no auth needed).
- ☐ **Tip-fingerprinting**: cluster wallets by identical tip lamports; tip >>
  tip-floor 75th pct = aggressive coordinated snipe; round-number tips = scripted.
- ☐ **Bundle-held-NOW / decay** (Trench): % supply bundlers STILL hold vs at launch;
  exiting = dump predictor. Use current-held%.

---

## PART 4 — Social / attention layer (medium; some free APIs)

- ☐ **Recycled-handle detection** (Sorsa `/about` username_change_count + rename
  recency) — social twin of serial-deployer; cheap API. Also Axiom "Twitter Reuses".
- ☐ **Smart-follower count + velocity** on token's X (curated KOL list ∩ followers)
  — social analog of smart-money inflow; fires before volume.
- ☐ **Bot-follower ratio** replacing binary socials.
- ☐ **Farcaster/Zora unique-caster velocity** (Neynar free-ish) — LEAST-CROWDED
  edge for Base content-coins; alert when caster-growth outpaces buyer-growth.
- ☐ **Attention leading indicators**: Kaito Yaps (free API, pre-launch ranking),
  Santiment social-volume ACCELERATION (free tier; note: level is contrarian),
  Telegram msg-velocity. For narrative-archetype (B) coins.
- ☐ **Social×on-chain join**: KOL follows handle ↔ smart wallet buys same window.

---

## PART 5 — Launchpad expansion (new ต้นน้ำ; medium)

- ☐ **DexScreener + GeckoTerminal free new-pool firehose** (cross-chain, no auth) —
  cheapest breadth add; `token-profiles/latest`, `networks/{net}/new_pools`.
- ☐ **Clanker (Base)** — verified factory 0xE85A59c...83a9; best easy Base add.
- ☐ **Raydium LaunchLab + Meteora DBC (Solana)** — the substrate under LetsBonk/
  Bags/Jupiter Studio/Believe; scan 2 programs → catch most of Solana long tail.
- ☐ **Zora factory (Base)** — one fixed address, high volume.
- ☐ **Robinhood other pads**: LaunchHood/RobinPad/Openfair via Uniswap V3 pool-
  creation events (drop NOXA — dead).
- ☐ Watch emerging chains: HyperEVM/Hypurr, MegaETH, Monad (uncrowded).

---

## PART 6 — Scoring model + validation infra (do alongside; gates trust)

- ☐ **Two-archetype scoring** (organic vs narrative) instead of one blended score.
- ☐ **Score calibration**: move from hand-weights to weight-of-evidence log-odds /
  isotonic calibration so score ≈ real probability (needs the ML research + data).
- ☐ **Backtest protocol** on alerts.jsonl+snapshots.jsonl: MELT win-label (price
  <30% of migration in 20min = bad), walk-forward, look-ahead-safe, min-sample
  gate before trusting a weight.
- ☐ **Shadow/control tracking** (fixes survivorship bias): also track a sample of
  sub-bar coins so we can tell if bars are too tight (the flap 80-120 question).
- ☐ **Rolling base-rate normalization** (thresholds decay monthly).
- ☐ **Decorrelate signals** (bundle%/top10%/insider% all measure concentration —
  don't triple-count).

---

## SEQUENCING (suggested, pending user pick)

1. Finish PART 0 research (after 7am) → complete the picture.
2. PART 1 quick wins in a batch (highest ROI/effort; validate via tracker).
3. PART 6 backtest+shadow infra EARLY (so everything after is measured, not guessed).
4. PART 2 funder-graph (the master counter) — biggest single winrate lever.
5. PART 3/4/5 as capacity allows; PART 5 (launchpad expansion) is independent and
   can run in parallel (more ต้นน้ำ coverage = more shots).

## Guardrails carried from live data (don't regress)
- pons NEAR-GRAD net-negative → stays off unless recalibrated to organic-archetype.
- MARKETING net-negative → off. pump bar $35k + quality gate. flap bar 80.
- Everything = SCORED feature with stage-dependent weight, not a hard gate (brand-
  new pairs are noisy; hard gates over-filter). Winner ≈ 1-in-20k → FP tolerance brutal.
