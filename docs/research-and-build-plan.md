# Research → Build Plan & Pipeline (action tracker)

Created 2026-07-19 after an overnight research sprint (11 waves in
`research-notes-raw.md`). Session limit hit → this file is the handoff so work
resumes cleanly. **Nothing here is decided/committed** — it's a ranked menu +
sequencing. Each build item is a PROPOSAL pending the user's go-ahead.

Status legend: ☐ todo · ◐ partial/in-progress · ☑ done · ⏸ blocked/waiting

---

## PART 0 — Finish the research (re-run after 7am reset) ☑ COMPLETE (18 waves total, 07-19)

- ☑ **EVM-specific detection** (Base/Robinhood) — WAVE 12. GoPlus token_security API
  (free, chain_id 8453=Base, ~30 calls/min), honeypot.is simulation API (free, ETH/
  BSC/Base only, no confirmed V4 support), Uniswap V2 Mint/Burn/Sync rug detection +
  the DIFFERENT Uniswap V4 Initialize/ModifyLiquidity event model (Clanker v4/Zora/
  Flaunch all use V4, not V2), EVM funder-graph via Blockscout (better free fallback
  than Etherscan V2 whose free tier is shrinking), Clanker (3 factory addrs by
  version) + Zora (1 fixed factory addr) + Flaunch on-chain launch detection.
- ☑ **ML feature-combination + backtesting methodology** — WAVE 13. GBM (class-
  weighted, not resampled) as primary model, AUPRC + precision@top-K + recall@fixed-
  FP-budget as eval, WOE/scorecard as the principled hand-weight replacement, purged-
  K-fold+embargo walk-forward keyed off alert_ts, shadow/control sampling as the
  prerequisite fix for survivorship bias, PSI for drift-triggered refit.
- ☑ **Public alpha-wallet / KOL datasets** — WAVE 14. kolscan.io (now pump.fun-owned,
  free, UI-only/scrape-needed) + kolscan.fun (Robinhood Chain), 8 new Dune queries w/
  address output, Cielo (Solana+Base API, paid tiers for discovery), Birdeye top-
  traders/gainers-losers, GMGN official skill-spec endpoints (/v1/user/smartmoney,
  sol+bsc+base+eth), SolanaTracker (free 2500 req/mo), refined bootstrap recipe (add
  min-trade-count floor + 14-30d decay re-check + late-entry-copytrader filter).

Queued angles — also run this pass:
- ☑ Telegram alpha-caller channels with track records — WAVE 15 (thin: no ready
  cross-channel API exists, would need custom build; noted survivorship bias in
  "qualified channel" curation lists).
- ☑ Time-of-day / regime / market-beta context signals — WAVE 16 (hour-of-day study
  found w/ concrete UTC hours, but weak statistical significance per its own authors;
  BTC.D/altseason-index = well-evidenced generic regime proxy; DXY/stablecoin angle
  unconfirmed/speculative).
- ☑ VOLTA bundlemaps staggered-bundle thresholds — WAVE 17, unreachable (403 + proxy
  blocks archive.org). Correction: our existing 45-90s/20-25-wallet constants were
  always a multi-source aggregate, not a verified single VOLTA number — don't
  upgrade confidence on them based on this retry.
- ☑ Verify Robinhood chainId — WAVE 18. Confirmed: Robinhood Chain (4663, Arbitrum
  Orbit L2) and Arc (5042) are genuinely different chains; repo configs (arc/,
  pons/, flap/, vlad/) are correctly separated, no mismatch found. Minor hygiene
  gap noted: no code file asserts chainId numerically (identified by RPC URL/
  Blockscout domain string only) — see new PART 1 item below.

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
- ☐ **EVM honeypot/tax dual-check hard-stop** (WAVE 12, Base/Robinhood): GoPlus
  `token_security` (free, chain_id 8453) buy_tax/sell_tax>10%/is_honeypot/
  is_blacklisted/cannot_sell_all + honeypot.is live buy-sell simulation as a second
  independent check — treat GoPlus-clean-but-honeypot.is-fails (or vice versa) as
  its OWN elevated-risk signal, not just an OR of two redundant checks.
- ☐ **Hour-of-day blacklist feature** (WAVE 16): down-weight/flag alerts firing in
  UTC 2/13/23 (worst mean P&L in the one study found); up-weight UTC 14/16/17 (best).
  Cheap, no new data needed (we already have alert timestamps) — but flag the
  underlying paper's own caveat that significance is weak at its sample size (n=190).
- ☐ **Defensive chainId assertion** (WAVE 18 hygiene finding): pons/flap/vlad
  identify Robinhood Chain purely by RPC URL string + Blockscout domain, never by
  checking `eth_chainId` numerically (4663) — add a startup assertion so a silently
  repointed/rotated RPC endpoint can't put us on the wrong chain without any code
  noticing. Same idea for arc/ against 5042.

---

## PART 2 — Funder-graph clustering (the master build; medium-large infra)

The highest-leverage item. Once built, it powers many signals at once.

- ☐ **EVM funder-graph** (Robinhood/Base): trace native-token funding of buyer/
  deployer wallets via Blockscout/Basescan, multi-hop (k≥3), find common ancestor;
  exclude CEX/known addresses. Flag pass-through hops (near-zero net, 1-in/1-out).
  WAVE 12 update: prefer Blockscout (`base.blockscout.com`, `robinhoodchain.
  blockscout.com`) REST v2 over Etherscan API V2 — Etherscan's free tier has been
  actively shrinking (records/request cut 10k→1k, some chains losing free coverage);
  for real multi-hop walkback, direct `eth_getLogs`/`eth_getBlockByNumber` via a
  free/cheap RPC beats either explorer's API reliability.
- ☐ **EVM LP-lock / real-time rug detection** (WAVE 12, new): for classic Uniswap V2
  pools (many Clanker v3/v3.1), watch Mint/Burn/Sync topic0 logs — LP recipient post-
  Mint not a burn-address/known-locker = unlocked; a Burn to an EOA followed by a
  large Sync = live rug. **For Clanker v4/Zora/Flaunch — all on Uniswap V4 — this is
  a DIFFERENT event model**: no per-pool contract, watch the singleton PoolManager's
  `Initialize`/`ModifyLiquidity` events instead (large-negative `liquidityDelta` =
  the rug; no auto Sync, must read `getSlot0` for reserves). LP-lock check becomes
  "does the LP position NFT sit in a known locker contract" (Clanker exposes this
  directly via `TokenCreated.lockerAddress` — a non-official locker address is
  itself a fork/risk flag).
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
- ☐ **Telegram cross-channel call-cluster signal** (WAVE 15, new — flagged THIN):
  no existing tool correlates multiple alpha-caller channels calling the same token
  within a short window; would need in-house scraping (contract-address regex per
  channel) + timestamp clustering, mirroring the on-chain smart-money-cluster idea
  but for social calls. No free ready-made API found — this is a build-from-scratch
  proposal, not an integration, and self-reported channel win-rates are known-noisy
  (survivorship bias in which channels get promoted/listed as "qualified").

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
- ☐ **Flaunch (Base) factory add** (WAVE 12, new — concrete address found): factory
  `0xfdCE459071c74b732B2dEC579Afb38Ea552C4e06`, Uniswap V4/hooks-based like Clanker
  v4; official `@flaunch/sdk` has `getPoolCreatedFromTx()` + a React hook, lowering
  build effort vs raw log-decoding.
- ☐ **Zora Explore-feed as a launch firehose** (WAVE 12, new): `api-sdk.zora.
  engineering` Explore queries (new/trending/top-gainer) work as a ready-made new-
  coin feed without needing to watch the ZoraFactory contract directly — needs an
  API key (not anonymous like GoPlus/honeypot.is).
- ☐ **Virtuals Protocol Base coverage — research gap, needs follow-up**: exact
  Base contract address for `AgentFactoryV3`/the post-2025 "Unicorn" launch system
  wasn't recoverable via search; needs a direct Basescan/whitepaper lookup before
  this can be scanned (WAVE 12).
- ☐ **Robinhood Chain GoPlus/honeypot.is coverage — verify** (WAVE 12): neither
  service's published chain list confirms chainId 4663 support; probe
  `token_security/4663/...` and `IsHoneypot?chainID=4663` directly before assuming
  the Base-chain integration above just works on Robinhood Chain too.

---

## PART 5b — Data backends: Bitquery + Dune (cross-cutting infra MANY signals need)

Not a single feature — the plumbing that unlocks Parts 1-5 cheaply. Right now we
hand-roll everything from RPC + Blockscout + per-platform APIs. These two give
unified, queryable access that removes most custom indexing.

- ☐ **Bitquery** ($49/mo personal, free tier + free gRPC Corecast for eligible use)
  — evaluate as the unified backend for: multi-launchpad new-token streams (pump.fun,
  LaunchLab, Meteora DBC, Clanker, Moonshot, Boop in ONE place → covers most of Part 5),
  first-100-buyers-still-holding query, transfer-before-buy flag, wash-forensics
  (funding-uniformity / buy-sell $ symmetry / both-sides rate), Jito bundle API,
  DEX-trades signed order-flow. Decide: adopt as primary stream vs keep per-platform.
  Docs: docs.bitquery.io (Pumpfun / launchpad-raydium / meteora-dbc / Jito-Bundle / dextrades).
- ☐ **Dune** — not for live alerts (dashboards 500 to fetchers, not real-time) but for
  OFFLINE analysis & list-building: replicate deployer-history SQL (oladeeayo repo:
  per-deployer graduation rate + PnL + self-buy count), alpha-wallet lists
  (adam_tehc/pump-fun-alpha-wallets), smart-money cutoffs (>$10k realized = top 0.5%).
  Use to SEED/refresh our smart-money list and validate thresholds, run periodically.
  WAVE 14 update: 8 more candidate Dune queries found w/ address output (dev2020/
  solana-alphas is the most parameterized — win-ratio/min-tokens-bought/recent-
  activity filters built in); free-tier pattern = pin/refresh on the website UI and
  scrape the rendered CSV rather than paying for programmatic re-execution.
- ☐ **GeckoTerminal + DexScreener free APIs** (already listed in Part 5) — the free
  layer of the same job; start here before paying for Bitquery.
- ☐ **Concrete smart-money bootstrap pipeline** (WAVE 14, new proposal — fleshes out
  the "seed smart-money list" idea above into an actual recipe): (1) SolanaTracker
  `/v2/pnl/leaderboard/top` (free, 2500 req/mo) + GMGN official `/v1/user/smartmoney`
  (sol/base/eth/bsc — API key needed, spec at github.com/GMGNAI/gmgn-skills) as the
  two cheapest API-accessible address sources; (2) cross-reference against Dune CSV
  exports for Solana; (3) Cielo free tier as the Base supplement (Dune has no Base
  wallet-ranking equivalent yet); (4) kolscan.fun + GMGN `chain=robinhood` for
  Robinhood Chain. Acceptance gate: >$10k realized PnL, win-rate>60% (validated
  against GMGN's own `smart_degen` definition), **NEW: ≥15-20 closed trades** before
  trusting the win-rate, ≥2-independent-source agreement, **NEW: 14-30 day decay
  re-check** (auto-demote on trailing-30D win-rate<60% or >14d inactivity — alpha
  decays fast once a wallet gets followed). **NEW: filter late-entry copytraders**
  (positive PnL from providing exit liquidity to earlier buyers ≠ real signal) via
  entry-timing-percentile within a token's trade sequence.
- Decision to make: how much to centralize on Bitquery (cost + single-dependency risk)
  vs keep our resilient per-platform on-chain detection (harder to rate-limit/kill).
  Leaning: on-chain detection stays primary for reliability; Bitquery/Dune as an
  enrichment + backtest + list-building layer, not the critical path.

---

## PART 6 — Scoring model + validation infra (do alongside; gates trust)

- ☐ **Two-archetype scoring** (organic vs narrative) instead of one blended score.
- ☐ **Score calibration**: move from hand-weights to weight-of-evidence log-odds /
  isotonic calibration so score ≈ real probability (needs the ML research + data).
  WAVE 13 update: **WOE/scorecard is the recommended path specifically because it
  matches our stated goal** — WOE per feature-bin is mathematically identical to
  logistic-regression coefficients, so the resulting log-odds sum is a principled,
  auditable, drop-in replacement for the current hand-weighted sum (same "sum of
  feature contributions" mental model, data-fit instead of eyeballed). Use OptBinning
  for monotonic-constrained binning. Prefer **Platt over isotonic** until positive-
  label (winner) count is well over ~1000 — isotonic overfits sparse regions, and our
  top-score tail is exactly where labeled positives are fewest.
- ☐ **Model choice** (WAVE 13, new item): GBM (LightGBM/XGBoost/CatBoost), class-
  weighted (`scale_pos_weight`/`is_unbalance`, tuned not formula-trusted) as the
  primary model — tree ensembles are the established tabular-data default and
  natively reduce the signal-decorrelation problem below as a side effect of split
  selection. **Avoid vanilla SMOTE** for our ~1:20,000 imbalance (fabricates
  implausible synthetic feature combos at this sparsity, risks train/test leakage).
  Run GBM and the WOE-scorecard above in parallel, compare AUPRC — GBM is the
  higher-power model, WOE is the interpretable/auditable one that directly replaces
  hand-weights; not mutually exclusive.
- ☐ **Evaluation metric** (WAVE 13, new item): report AUPRC (not AUC-ROC — ROC's FPR
  term is swamped by huge true-negative count under extreme imbalance) PLUS
  operating points: precision@top-K (e.g. top 100 alerts/week) and recall-at-fixed-
  FP-budget — the actually-actionable numbers given "FP tolerance must be brutal."
- ☐ **Backtest protocol** on alerts.jsonl+snapshots.jsonl: MELT win-label (price
  <30% of migration in 20min = bad), walk-forward, look-ahead-safe, min-sample
  gate before trusting a weight. WAVE 13 update: use **purged K-fold + embargo**
  (López de Prado) keyed off alert_ts — purge training alerts whose label-maturity
  window overlaps the test window, embargo a buffer after each fold, exclude alerts
  younger than the maturity horizon entirely (don't zero-fill as negative). Slide
  the train/test cutoff forward monthly and report AUPRC PER WINDOW, not one
  aggregate number, so drift is visible directly.
- ☐ **Shadow/control tracking** (fixes survivorship bias): also track a sample of
  sub-bar coins so we can tell if bars are too tight (the flap 80-120 question).
  WAVE 13 update: **this is the single highest-leverage new pipeline in PART 6** —
  every other backtest/calibration item here is bounded by this bias until it
  exists. Recipe: for each alert, sample K random non-alerted launches from the
  SAME launchpad+time-bucket, snapshot them identically to alerted tokens. This is
  sufficient for the main use cases (true base rates, sanity-checking whether
  alerted tokens actually outperform random launches); full inverse-propensity-
  weighting is a valid v2 refinement, not a wave-1 requirement.
- ☐ **Rolling base-rate normalization** (thresholds decay monthly). WAVE 13 update:
  drive refit off **PSI (Population Stability Index)** on the score distribution +
  top-IV features + realized base rate, not a fixed calendar cadence — thresholds
  <0.1 stable / 0.1-0.25 watch / >0.25 retrain-trigger, checked weekly; given our
  observed 0.63%→0.2% graduation-rate drift over 8 months, PSI will likely breach
  0.25 before any fixed monthly/quarterly cadence would have caught it.
- ☐ **Decorrelate signals** (bundle%/top10%/insider% all measure concentration —
  don't triple-count). WAVE 13 update: if we go GBM, this is largely solved for free
  (trees split on whichever correlated proxy is locally best, not a naive sum) —
  only a real problem for the WOE/linear scorecard path, where the fix is grouping
  correlated features and capping the group's combined log-odds contribution (or
  PCA within just the concentration sub-block, not globally).
- ☐ **Regime/context normalization feature** (WAVE 16, new item): rolling BTC
  Dominance level/delta (or BTC/SOL 24h return+volatility) as a token-independent
  control variable, so a token's score isn't just riding a broad alt-season pump —
  well-evidenced generically for crypto, not yet memecoin-native-validated.

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

---

## UPDATES — 2026-07-19 gap-closer probes (local, closed the cloud agent's 403s)

Verified live via direct API probe (see research-notes-raw.md WAVE 19). Changes to items above:

- ☑→confirmed: **GoPlus EVM honeypot/tax is FREE + KEYLESS on BOTH our EVM chains** — Robinhood
  4663 AND Base 8453 (Part 1 "EVM honeypot/tax dual-check" is now high-confidence, not speculative).
  honeypot.is does NOT support 4663 (Base-only for the dynamic sim) → on Robinhood use GoPlus static only.
- ☐ **NEW Part-1 item — flap tax backstop via GoPlus**: flap's "tax ? (api unavailable)" gap (batman
  Cloudflare rate-limit) can be backstopped by GoPlus token_security/4663 (buy_tax/sell_tax/is_honeypot).
  Cheap, independent, closes a live bug we already hit. High ROI / low effort.
- ☑→confirmed: **Clanker (Part 5) is a READY API firehose** — www.clanker.world/api/tokens?limit=N returns
  contract_address/factory_address/locker_address/type/pair/starting_market_cap/warnings/cast_hash(Farcaster)/
  socialLinks per token, ~minutes-fresh. No factory-event listening needed for v1. Upgrades Clanker from
  "medium (event decode)" to "easy (poll API)".
- ◐ Virtuals AgentFactoryV3 on-chain address still not found (factory field null in API) — MINOR, our
  scanner is API-based.

## NEW PREREQUISITE (blocks most of Part 1/2 — do this FIRST, before building signals)

- ☐ **Per-scanner data-availability matrix**: map every proposed signal → can pons/flap/virtuals/arc/pump
  compute it with data collected TODAY? Known gap: **flap collects only transfer COUNTS, not per-swap value**
  → capital-efficiency, trade-size-variance, wash-price-impact are NOT computable on flap without adding
  swap-value collection. This matrix decides what's a quick win vs what needs a collection change first.
  Cheap to produce (audit the 5 scanners' CoinState/data structures); saves building signals we can't feed.

## SYNTHESIS NOTE — two apparent contradictions resolve to ONE rule (don't build contradictory gates)

- sniper/bundler U-curve (wave 9) vs bundle=rug (wave 8) vs cohort=selection-bias (wave 11): it's not the
  COUNT, it's WHO — dev-funder-linked = bad, independent-sophisticated = neutral, raw-presence = confounded.
- capital-efficiency few-trades=good (wave 2/3) vs fast-fill<30min=bad (wave 9): few LARGE buys from DIVERSE
  wallets = good; many fast COORDINATED buys = bad.
- BOTH collapse to: the discriminator is organic-share + the FUNDER-GRAPH (Part 2). State this in any final
  scoring design so "sniper count" / "fill speed" aren't naively gated in contradictory directions.
