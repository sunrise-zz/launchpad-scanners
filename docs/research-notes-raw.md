# Raw research notes — overnight signal hunt (started 2026-07-19)

Accumulation log. Each research wave's findings appended verbatim-ish as agents
complete. NO decisions made here — this is source material for later synthesis
into signal-research-2026-07.md. User asleep; loop runs until session limit.

Signals ALREADY in our stack (for reference — flag NEW vs these):
smart-money count (weighted), buy/sell ratio, holder concentration dev%/top10%,
sniper count (first-2s), serial-deployer, socials (TG-weighted), paid-marketing,
bonding-curve progress/velocity, capital-efficiency (ETH/trade), transfer/recipient
velocity, GMGN organic fields (bundler_rate/rat_rate/sniper70_rate/bot_rate/
top10_rate/dev_hold_rate/fresh_rate/bluechip/smart/renowned).

Research angles queue (to keep the loop going):
- [done] Sorsa/TweetScout (social graph)
- [done] academic arXiv x4 (graduation/rug/bot papers)
- [running] GitHub scanner code deep-dive (exact thresholds/APIs)
- [running] GMGN methodology + skills market (exact cutoffs)
- [running] Dune/Bitquery/Helius/Birdeye + practitioner analysts
- [running] trading terminals (Photon/BullX/Axiom/Trojan/GMGN filter presets)
- [running] attacker tooling (bundler/volume-bot evasion → counter-signals)
- [running] new launchpads on our chains (untapped ต้นน้ำ)
- [queued] Nansen/Arkham/Chainalysis smart-money methodology
- [queued] MEV/Jito bundle mechanics + mempool detection
- [queued] winner post-mortems (reverse-engineer launch-time fingerprint of past 100x)
- [queued] Kaito/mindshare/attention leading indicators
- [queued] copy-trading wallet-selection science (which wallets, how ranked)
- [queued] AMM/liquidity microstructure + orderflow signals
- [queued] YouTube trader setups; Farcaster/Zora/Clanker Base meta

---

## WAVE 1 — Sorsa/TweetScout (social-graph intelligence) [done]

Sorsa = rebranded TweetScout, a crypto X/Twitter social-graph oracle (NOT on-chain).
Stealable signals:
- **Recycled/renamed X-account detection** — `/about` returns username_change_count +
  last_username_change_at. Old created_at + rename <7d before launch = bought shell.
  Social twin of serial-deployer. Best single steal.
- **Smart-follower count** — # of curated KOL/VC accounts following the token's X handle
  (social analog of smart-money wallet inflow; expensive to fake, fires before volume).
- **Smart-follower velocity** — new smart followers in last hours (/new-followers-7d,
  /score-changes week/month delta).
- **Bot-follower ratio** — % fake followers (empty bio, 0 followers, default avatar,
  same-day creation waves) — replaces binary "has socials". High followers + high bot% =
  stronger rug signal than no socials.
- **Follower composition** (influencers/projects/VC-employees/retail/bots).
- **Mention-quality weighting** — mentions weighted by mentioner's own score, not count.
- **Social×on-chain join** — KOL follows handle ↔ smart wallet buys, same window (Sorsa
  can't do this; we can). Caveat: Sorsa Score is gameable (boost services exist) → weighted
  feature, never a gate. Sources: docs.sorsa.io, app.sorsa.io/early-projects.

## WAVE 2 — academic arXiv + practitioner data [done]

Meta-finding: raw activity = what bots fake; winrate lives in ORGANIC-share versions.
Top signals (evidence tier in brackets):
- [A] **Capital efficiency** = vSOL/trade — strongest graduation predictor across whole
  curve (arXiv 2602.14860, 655k tokens); RF study ranks volume/tx #1 of 12, whale_score
  LAST. → IMPLEMENTED on pons.
- [B] **Deployer→sniper funding-link** — Pine Analytics: deployer pre-funds own snipers,
  87% profitable, 90% exit in 1-2 swaps. Walk funding back N hops; flag intersect deployer/
  shared funder. Near-deterministic rug flag.
- [A] **Entity-clustered concentration delta** — MemeTrans 2602.13480: after clustering
  wallets (same-tx, Jito bundle, common funder), high-risk concentration +24% vs +6%
  low-risk. Single bundle >10% supply = red flag. Cut simulated losses 56%.
- [A] **Dev initial-buy size** — survival 832k (2607.02823): initial mcap above default →
  HR 4.51 graduation; >10 SOL dev fund → 30% grad vs 2.6% (<1 SOL). Model separately from
  dev% (moderate buy GOOD, extreme dev% BAD).
- [A] **Telegram-weighted socials** — TG → 8.9x, TG+X+web → 17.4x graduation lift.
  → IMPLEMENTED on pons.
- [A+B] **Bot-share of flow** — only >70% non-bot share approaches breakeven; <3% pro
  traders → 32% moon vs 2.6% bot-dominated.
- [B] **Trade-size variance / volume std** — #2 RF feature; humans heterogeneous, bots
  uniform. near-zero CV = manufactured.
- [B] **Priority-fee spend** — #4 RF feature; costly hard-to-fake urgency (EVM: gas tip).
- [B] **Zero-bundler paradox** — 0 bundlers = HIGHEST dump (28%); insider 10-30% optimal.
  Band-based, not monotone penalty.
- [B/C] **Aged vs fresh wallet ratio** among first buyers — strongest early predictor
  (practitioner); farms use fresh star-topology wallets.
- [A] **Wash-trade share** — net-balance≈0 despite gross volume; MELT: 21% of pre-migration
  txs were wash (buy+sell in one tx).
- [A] **Dump-event detector** — 4σ log-return control limit; 92% of ≥30-swap tokens had ≥1
  dump clustering pre-graduation; a late-curve token WITHOUT one = outlier.
- [A+B] **Creator funding-network** (upgrade serial-deployer) — SolRugDetector 78 syndicates,
  star topology (1 funder → ≤169 wallets). Serial devs = 18% of creators, drained 82% of
  liquidity. BUT prolific-creator identity added NO graduation lift → rug FILTER not winner-picker.
- [B] **Post-migration LP & holder band** (2nd-stage) — $100k+ LP → 84% moon/0.25% dump;
  holders 1k-5k → 66% moon, >5k decays. Launch platform itself a feature (Meteora DBC 92%
  dump vs pump.fun 10%).
- Caveats: base rates drift (0.63%→0.2% grad in 8mo) — normalize vs rolling baseline. Our
  own win-label: MELT rule — high-risk if price <30% of migration within 20min (graduation
  alone weak: 84% of graduates still high-risk).
- Sources: arXiv 2602.14860, 2602.13480, 2607.02823, 2603.24625, 2601.08641, 2504.07132;
  Pine Analytics "Exit Liquidity Machines"; Memecoin Trading Encyclopedia (Medium).

## WAVE 3 — Dune / Bitquery / Helius / Birdeye / analysts [done]

CONCRETE + replicable (this wave = implementation detail, not just findings):
- **Deployer-funded sniper (Pine)**: 15k launches where wallet (a) got direct SOL from
  deployer pre-launch AND (b) bought in creation block → 87% profitable, 55% exit <1min,
  90% exit in 1-2 sells, active 14-23 UTC. Soft flags: top-3 wallets >80% supply; >50%
  volume in first 10 blocks. NOTE: >50% of pump tokens now sniped in creation-block →
  same-block alone no longer discriminates, FUNDING-LINKAGE is the edge. Exit-fingerprint
  (1-2 sell txs, <60s) = reusable wallet-reputation feature (also a POSITIVE copytrade
  signal if flipped).
- **Trade-velocity conditioned on curve position** (arXiv 2602.14860): ≤10 trades to reach
  a vSOL level → dramatically higher grad; 1000+ trades → baseline. Subtly diff from our
  capital-eff (it's conditioned on curve progress). Breakeven rule: buying at vSol is +EV
  only if P(grad|vSol) > vSol²/115² — blind mid-curve entry is structurally -EV.
- **Bot-share via ROUTING classification**: bot = tx routed directly to pump program vs via
  UI/aggregator (has referral instruction). >70% organic = elevated grad. (concrete way to
  compute bot-share we listed abstractly in wave 2.)
- **Wash-volume forensics trio (Bitquery OpenLie case)**: 200 bots funded exactly 0.5 SOL
  each in 52s; both-sides participation 96%; uniform ~$13 trade sizes; per-wallet buy$≈sell$.
  → NEW signals: (a) funding-uniformity (N buyers funded identical amt from 1 source in tight
  window), (b) per-wallet buy/sell $ symmetry, (c) trade-size entropy, (d) both-sides rate.
- **Bitquery GraphQL patterns (directly replicable)**:
  · first-100-buyers-still-holding ratio (DEXTrades asc by Block_Time limit 100 → owners →
    PostBalance) — distinct from top10%.
  · transfer-before-buy flag (first inbound transfer time vs first buy time; got tokens w/o
    buying = insider distribution).
  · EXACT pump grad math: progress = 100 - ((balance - 206,900,000)*100/793,100,000);
    graduates when curve balance = 206,900,000 (~85 SOL/~$69k). KOTH at ~45 SOL (mid-curve
    checkpoint feature). Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P, create/create_v2.
- **Dune deployer-history SQL (oladeeayo repo)**: "manipulator" = wallet with >6 buys on one
  token (per-token count feature we lack); sniper window 1-40s; per-deployer graduation RATE +
  cumulative PnL + self-buy count + deployer→wallet transfer count (richer than our binary flag).
- **Smart-money PnL cutoffs (adam_tehc Dune / Nansen)**: only 3.06% of wallets ever net >$1k,
  0.48% >$10k, 0.037% >$100k → a wallet with >$10k realized pump PnL = top 0.5% (concrete
  smart-list cutoff). Nansen copytrade filter: win_rate > 0.5; warns memecoin smart-money is
  noisy ("hint not thesis").
- **Mechanics/timing**: Virtuals grad at 42k VIRTUAL → Uniswap V3 Base, LP locked 10y; some
  Virtuals launches have 99% tax decaying 1%/min → 1% (~98-min window); Virtuals RECOMMENDS
  dev self-scoop in creation block → dev-same-block-buy is NOT a rug flag on Virtuals (unlike
  pump). pump KOTH ~45 SOL, $12k LP injected at migration. Solana slot ~400ms — retail can't
  win same-block race → our edge is post-block-0 SELECTION not speed.
- **Infra found**: Birdeye Wallet-PnL API (realized/unrealized/win-rate per wallet — cheapest
  path to exit-fingerprint + smart cutoff w/o indexing); Bitquery token-sniffer ref impl
  (first-1000-address insider analysis); github.com/buddies2705/awesome-memecoin-trading
  (Trench Bot slot-bundle, Bubblemaps clusters, kolscan KOL wallets).
- Sources: pineanalytics.substack.com/p/exit-liquidity-machines; bitquery.io/blog/
  solana-volume-numbers-are-a-lie + wash-trading-detection; docs.bitquery.io Pumpfun API;
  github.com/oladeeayo/Pumpfun-Token-Deployer-Records-Dashboard; nansen.ai; bds.birdeye.so.

## WAVE 4 — GMGN methodology + exact thresholds + skills market [done]

**THRESHOLD CHEAT-SHEET (GMGN official from their own agent-skill docs — pass/skip):**
- smart_degen_count: ≥3 pass · 0 skip
- rug_ratio: <0.1 pass · >0.3 HARD STOP
- top_10_holder_rate: <0.20 pass · >0.50 skip · >0.60 hard stop (UI "safe" = <30%)
- bundler_rate: <0.1 pass · >0.3 skip
- rat_trader_amount_rate (insider): <0.1 pass · >0.3 skip (community ≤0.2)
- sniper_count: >20 wallets = danger; pump community 5+ snipers ≈ 99% rug
- is_wash_trading: true = instant skip
- liquidity: >$50k pass · <$10k skip (initial pool >$300k good, <$4k bad); -30% drop = exit
- sell/buy tax: >10% hard stop; is_honeypot(EVM) yes = halt
- renounced_mint + renounced_freeze (SOL): either 0 = skip; LP burn <100% ≈ 60% rug prob
- creator_token_status: creator_close (dev exited) GOOD vs creator_hold BAD
- dev_team_hold_rate: >30% ≈ rug; top-3 wallets >20% = insider control
- swaps velocity: ≥60 tx/1min or ≥600/5min = legit activity; token age <1h avoid unless exceptional
- **GMGN server-side presets** (the codified strategy): safe = rug<0.3 & bundler<0.3 & insider<0.3;
  smart-money = smart_degen≥1; strict = safe+smart+vol24h>$1000.

**Wallet-tag definitions**: smart_degen (win>0.6 strong/>0.5 ok, PnL ratio>1, community 70%+);
renowned = human-verified KOL; sniper = early-block buyer; first-70 = fixed cohort (sniper70_rate
= share still holding); rat_trader/insider = held w/o buying (dev distribution) OR shared creation-
time/funder/transfer-time; bundler = multi-wallet txs in same block (DEV team = creator+bundlers);
whale huge = single tx >$10k; bluechip_owner = holders who also hold bluechips (higher better).
Wallet red flags: buy+sell within 10s (bot/farm), sold>bought, blacklist-token buys.

**Market-signal feed** `/v1/market/token_signal` (SOL+BSC), 18 types — KEY: **type 12 SmartDegenBuy**
(highest-value entry), **type 10 BundlerSell** (supply overhang cleared = de-risk event), 7 PriceATH,
8 McpKeyLevel. `signal_times` = repeat-trigger count (momentum); trigger_mc vs first_trigger_mc.
Don't pass types 14/15/16 (API 400).

**Signal-strength framework (copy this)**: Weak=1 KOL buy · Medium=2-3 smart same dir OR 1 full open ·
**Strong=≥3 smart wallets same direction within 30min (cluster)** · Very strong=cluster+full opens+KOL.
**Copytrade wallet ranking weights: win-rate 40% / PnL 40% / diversification 10% / trend 10%**; style
by hold time (scalper<1h, day 1-24h, swing 1-7d, holder>7d).

**Fields we DON'T use yet (add)**: rug_ratio (composite hard-stop), is_wash_trading, creator_token_status
(creator_close flip = real de-risk), the signal feed (type 12/10/7/8 + signal_times), sniper_count
(distinct from sniper70), hot_level, net_buy_24h, history_highest_market_cap (drawdown-from-ATH),
visiting_count (attention/hot-search rank = leading social indicator), dexscr_ad/boost (paid-mktg tells),
cto_flag, dev_token_burn_ratio, top_holders per-wallet unrealized_profit/avg_cost/transfer_in (smart
still-holding vs distributed), maker tag_rank, trenches tags distribed/not_risk/img_not_duplicate/
social_not_duplicate (copycat detection).
- Skills market: gmgn.ai/static/opstatic/skills.json (40+ skills, browser-UA only); 6 first-party skills
  + 9 workflow playbooks (early-screening, smart-money-profile, risk-warning, market-opportunities,
  lifecycle-staging). Sources: docs.gmgn.ai; github.com/GMGNAI/gmgn-skills; chaincatcher.com/en/article/2153149.

## WAVE 5 — new launchpads / untapped ต้นน้ำ [done]

⚠️ VERIFY: agent claims Robinhood Chain = chainId 4663 (Arbitrum Orbit L2). Our Arc scanner uses
5042 (that's Arc Mainnet, a DIFFERENT chain). pons/flap use rpc.mainnet.chain.robinhood.com directly
(no chainId constant) so likely fine — but double-check Arc≠Robinhood and our configs.

**TIER 1 (hot 2026 + easy) — best expansion targets:**
- **Raydium LaunchLab (Solana)** = the substrate under LetsBonk/bonk.fun (#1 pump.fun challenger,
  20k+ launches/day peak) + Bags + Jupiter Studio. Scan ONE program → catch many launchpads
  ("ต้นน้ำ ของ ต้นน้ำ"). Bitquery API + on-chain IDL. HIGH leverage.
- **Meteora DBC (Dynamic Bonding Curve, Solana)** = other substrate, under Believe/Jupiter Studio/
  Moonshot/Bags. Open-source IDL (github.com/MeteoraAg/dynamic-bonding-curve). Jupiter screener only
  supports DBC launchpads = dominant rail. LaunchLab + DBC = most of Solana long tail at source.
- **Clanker (Base)** — ~$27M rev, ~$364M/day peak, 300k+ tokens. Verified factories on BaseScan:
  v4 `0xE85A59c628F7d27878ACeB4bf3b35733630083a9`. Listen token-created events. Best Base add.
- **DexScreener free endpoints** (no auth): /token-profiles/latest/v1, /token-boosts/latest/v1
  (+top), WebSocket. Cross-chain new-token firehose. (we already use boosts on pons.)
- **GeckoTerminal /networks/{network}/new_pools** + /networks/new_pools — pools created past 48h,
  30 req/min, FREE no key. Truer new-pairs than DexScreener profiles. Base+Solana+more.

**TIER 2**: Bags (Sol, +1347% QoQ, on DBC), Heaven/HeavenDex (novel burn, uncrowded), Jupiter Studio
(on DBC), Moonshot (fiat on-ramp), Token Mill (gamified niche), Flaunch+Zora (Base content-coins;
Zora factory fixed `0xf74b146ce44cc162b601dec3be331784db111dc1`), Robinhood other pads: LaunchHood/
RobinPad/Openfair (Uniswap V3 pool-creation events; NOXA Fun DEAD — shut down Jul 2026).

**TIER 3 (dead/hype, skip)**: Believe/LAUNCHCOIN (dead, $233/24h), Boop (faded), Daos.fun/Time.fun
(dormant), Sun Pump (Tron), Four.meme (BSC).

**Emerging chains (genuinely uncrowded — get in before aggregators index)**: HyperEVM/Hypurr,
MegaETH (mainnet Feb 2026), Monad (TVL >$400M). Standard EVM factory/pool-creation listening.
NOTE: no new launchpad has a clean vanity suffix like pump's `...pump` / flap's `...7777` —
identify by factory/program address + event signature.
- Data-API cheat: DexScreener (free 60/min) + GeckoTerminal (free 30/min) = best free start;
  Bitquery (unified multi-launchpad streams, $49/mo); GMGN OpenAPI (Base pads: Clanker/Zora/
  Virtuals V2/Flaunch). Sources: docs.bitquery.io launchpad APIs; docs.dexscreener.com;
  docs.coingecko.com/reference/latest-pools-network; clanker.gitbook.io; messari Q1 2026.

## WAVE 6 — trading terminals (Photon/BullX/Axiom/Trojan/Maestro/Bloom/Nova) [done]

NEW filters (not in our set) with pro threshold values:
- **Dev MIGRATIONS count** (Axiom) — # of dev's past tokens that actually graduated (success history,
  not raw deploy count). Rug dev deploys many, migrates few. Refines serial-deployer.
- **Bundle-held-NOW / decay** (Trench Bot) — supply bundlers STILL hold vs at launch; exiting = dump
  predictor. Use current-held%, not launch%.
- **Twitter-handle reuse + tweet/account age** (Axiom "Twitter Reuses"/"Tweet Age") — recycled-social
  (= Sorsa rename signal, terminal side).
- **creator_token_status hold vs close** (GMGN) — dev already exited (creator_close = de-risk)?
- **Dev-sold as real-time EVENT** (Bloom/Nova auto-sell-on-dev-sell) — discrete alert vs static %.
- **Insider/funding-cluster % as own axis** (BullX "Inside Wallet Supply", exclude >0.25-0.30).
- **Renowned/KOL count** separate axis from smart-money (GMGN min_renowned_count).
- **Honeypot buy/sell SIMULATION + tax-threshold wait** (Maestro) — active sellability sim (EVM mainly).
- **Bot-holder count SIGN FLIP** (Photon caps bots pre-grad 0-18; BullX REQUIRES ≥15 post-grad) — same
  metric opposite polarity by lifecycle stage.
- Pro thresholds: dev ≤5%, top10 <15% strict/<30% loose, snipers ≤10% or ≤7, bundle ≤5%/≤20%,
  holders >50-100, new-pair mc >$5-10k, liq >$10k/$50k safe.
- **Copytrade selection (GMGN pro)**: win rate ≥60% w/ 50-100 trades/wk; REJECT 100%+few (noise) AND
  500+/wk (bot); prefer 5x+ exits, reject ~1.2x flips; red flag if 15-20%+ sold within 5s (exit-liq
  farm); reject realized gains w/ no buy history (insider); copy 10-20% size, cap 5-7 wallets.
- Sources: memecoinnavigator.com (Axiom), moonshotsdaily.com (BullX), docs.maestrobots.com,
  docs.bloombot.app, trench.bot, docs.gmgn.ai copy-trade.

## WAVE 7 — GitHub scanner CODE (exact thresholds/formulas, 11 repos) [done]

THE implementation reference. Recurring constants:
- **Bundle**: ≥2-3 wallets sharing NON-exchange funder (godmode/GMGN) OR same slot ~0.4s (Trench);
  supply >25% red / 10-25% yellow / <10% green (NoesisAPI). gmgn-screener burst: ≤2 feePayers doing
  ≥12 transfers in ≤10-30s = ACTIVE bundling (rug-prep); ≥10 payers = organic rush (FP guard).
- **Funder id (godmode/Helius)**: first incoming nativeTransfer where to==owner & amt>0; fallback feePayer.
  Walk /v1/wallet/{a}/funded-by 2-3 hops. Exclude exchange funders (binance/coinbase/phantom/robinhood…).
- **Fresh wallet**: <100 txs (practically <20) + first-activity near mint + holds ≥0.05% supply.
- **Concentration**: top10 >50% red/>30% yellow; top20 >60%/>40%; single wallet >10-15% danger.
- **Sniper**: first-slot/first-10min buy + rapid-fire (<60s avg gap) + swap-only profile.
- **Rug label**: final MC ≤ 20% of peak (-80%). Serial rugger: ≥10 tokens & <10% success (success=mc>$10k);
  ≥5 & <20% high; ≥3 in 24h flag. Creator trust (Dexter): exclude if 2 launches <900s apart AND has failures.
- **godmode risk score**: +20/red flag +8/yellow, +35 if bundled; ≥60 CRITICAL. Flags: distributes-to ≥10
  addrs, rapid-fire <60s, swap-only, sends-back-to-funder (circular).
- **Airdrop/insider wallet**: buy_tx_count==0 & balance>0 (got via transfer, zero-cost=HIGH sell pressure).
- **Dev covert control**: creator token_transfer_out addr in top-100 = sock-puppet (DANGER).
- **rug_ratio > 0.3 high risk** (GMGN). LP locked := LP-token burn >95%. rugcheck.xyz /v1/tokens/{mint}/report/summary.
- **Wallet PnL trick (tymur999)**: sum nativeBalanceChange over txs touching mint = net SOL profit (no FIFO).
- **Recurring smart-money (lelantos)**: wallets in ≥2 tokens' first-buyers/top-traders, exclude AMM addrs.
  Strongly-linked = ≥0.5 SOL bidirectional (ignore dust <0.05).
- **Curve infra (chainstacklabs)**: pump 6EF8..F6P, bonding discriminator 6966180631402821399, progress =
  100 - real_token_reserves*100/793,100,000. Listeners: geyser gRPC / logsSubscribe / blockSubscribe / pumpportal wss.
- Repos: olarike/godmode, FLOCK4H/Dexter, GMGNAI/gmgn-skills, kontia1/gmgn-screener, degenfrends/
  solana-rugchecker, matthewrahm/token-launch-monitor, chainstacklabs/pumpfun-bonkfun-bot, Rengon0x/NoesisAPI,
  trench.bot, heil-kaizen/lelantos, tymur999/profit-script. (repos cloned to scratchpad/repos/)

## WAVE 8 — attacker tooling / evasion → counter-signals [done] ⚠️ CRITICAL

**WHICH OF OUR CHECKS ARE ALREADY DEFEATED (from attacker feature lists):**
| our check | status vs current evasion | counter to add |
|---|---|---|
| same-slot bundle | DEFEATED by 45-90s stagger / cross-slot | funding-graph clustering + inter-buy entropy |
| holder concentration | DEFEATED by <1% dispersion across 50-200 wallets | CLUSTER-level concentration after funder-collapse |
| sniper count | WEAKENED by multi-wallet + aged wallets | funding-recency / last-topup-window clustering |
| serial-deployer | DEFEATED by fresh deployer + hop funding | deployer funding lineage + launch-template fingerprint |
| bot rates (GMGN) | WEAKENED by human-jitter mimicry + aged wallets | net-position wash detection + timing entropy |

Attacker constants (→ our thresholds): bundle 20-25 wallets; stealth-launch 45-90s between buys; disperse
across 50-200 fresh wallets each <1%; 24-72h delay between associated addrs; volume-bot 0.025 SOL/100 makers
randomized size+timing; Jito "first-or-fail" needs ≥10 wallets; migrate ~85% curve.

**Master counter = recursive MULTI-HOP funding-graph clustering** (re-arms concentration+sniper+serial-deployer
at once). Helius funded-by is SINGLE-HOP only — attackers add 1 intermediary to beat it → must BFS back k≥3 hops
for common ancestor. Pass-through hop wallets: near-zero net balance, 1-in/1-out, short lifespan (structural tell).
Other robust counters:
- **Wash: net-position/zero-net-balance** — |net|/gross < ~5% while gross high = wash. Catches **94.48%** of
  wash-traded memecoins (arXiv 2102.07001). + AMM invariant (pool balance barely moved despite volume).
- **Volume-vs-holder-growth divergence**: vol +300% w/ holder count flat = manufactured (arXiv 2507.01963).
- **Timing entropy**: bot jitter is bounded-uniform → low Shannon entropy / periodic autocorrelation in
  inter-trade gaps + trade sizes. Human = heavy-tailed high-entropy.
- **Distribution shape**: attacker allocations suspiciously uniform (wallets within 5% of avg, amounts %1000==0);
  real holders log-normal. Deviation-from-lognormal per cluster.
- **Funding-recency > wallet-age** (defeats aged-wallet evasion): time between last SOL top-up and first buy;
  burst of aged wallets funded in same pre-launch window = coordinated.
- **Launch-template fingerprint** (links serial operators across fresh identities): identical LUT setup, Jito
  tip amount, stagger cadence, bundle wallet count, metadata/bio style → template hash matched across deployers.
- **Fake social**: commenter wallets in same funding cluster / also bundle-buyers = astroturf; engagement
  outpacing on-chain holder growth = fake; separate paid-boost multiplier from organic.
- Sources: cicere/pumpfun-bundler, Rabnail-SOL bundler, smithii volume/comment bots, bananagun sniper blog,
  VOLTA bundlemaps, arXiv 2507.01963 + 2102.07001, helius funded-by docs, tracer.solanalyze.wtf.

## WAVE 9 — winner post-mortems (reverse-engineer 100x launch fingerprints) [done]

**BIGGEST insight: TWO opposite winner archetypes — one score template will miss half:**
- **Archetype A "cold fermentation / organic"** (WIF, POPCAT, FARTCOIN): fair launch, mint burned,
  low/no dev alloc, SLOW holder accumulation (weeks), smart money buys on PULLBACKS not block 0,
  **social LAGS price** (FARTCOIN 22k followers vs GOAT 214k — price ran first). On-chain detects this early.
- **Archetype B "narrative catalyst"** (GOAT, ai16z, zerebro): fast accel from external endorsement/
  AI-agent narrative, **social IS the catalyst, inflects BEFORE/with price**; launched by anon then
  endorsed. Needs SOCIAL/mindshare detection to catch pre-pump.

**Winner common-denominators (production data, moon:dump odds):**
- Liquidity depth $100k+ → 308x (84% moon/0.25% dump) — STRONGEST in set (2nd-stage/post-grad)
- Holder count 1000-5000 → 5.55x (proven but still growing)
- Pro-trader/bot ratio <3% pro (organic) → 12.5x gap vs >25% bots
- Creator funding >10 SOL → 30% grad vs 2.6% (<1 SOL)
- First-time deployer → 19.9% pump vs 4.16% serial (4.8x) — serial = rug filter
- Token age <6h = highest-alpha window; slow fill 6-24h/10-50 traders/hr = highest survival
- Base rate brutal: only 18 pump tokens EVER hit $10M; winner ≈ 1-in-20,000 → FP tolerance must be brutal.

**COUNTERINTUITIVE (encode as NON-LINEAR features):**
- **Sniper/bundler = U-CURVE not penalty**: ZERO bundlers = HIGHEST dump (28%); 11-50 = best risk-adjusted.
  Sophisticated bots act as quality pre-filter. Hard "sniper=bad" rule is WRONG.
- **Insider concentration = bimodal/variance not pure-risk**: <3% safe-modest; 30%+ = highest moon (31.5%)
  AND 1-in-4 dump. High concentration = high-beta → size-DOWN not exclude.
- **Fast fill <30min / 200+ traders/hr = RED flag** (coordinated cabal/KOL → dump wave 2). Accelerating
  hour-0 holder growth correlates with INSIDERS not organic demand. (contradicts naive "velocity=good"!)

**Rug/dump launch fingerprint (inverse)**: bundle >15% serious/>30% avoid; single cluster >50% = one entity;
distribution shape = winner "galaxy" (many unconnected bubbles, CEX/DEX in top holders) vs rug "solar system"
(one dominant connected cluster); deployer retains holdings; concentration RISING while price rising = soft-rug
in progress; clusters fragmenting into fresh addrs = pre-selling; death tick = 0 buys 5min + active sells;
wash tell = >$100k vol with <50 traders.

**Actionable deltas**: (1) split scoring into 2 archetype models; (2) sniper/bundler U-curve; (3) insider conc
= variance→size-down not exclude; (4) weight liquidity-depth + organic-ratio heaviest; (5) add price-leads-
social divergence as BULLISH organic flag (rising cap + low Twitter = under-radar); (6) fast-fill <30min +
concentration-rising-while-price-rising = bearish. "Enhanced Killer Combo" (500+ traders/hr + social +
first-time deployer + 1000+ holders) = 6.89x — alpha is COMPOUNDING independent signals. Insider intent
readable only first 1-24h (best <6h). Sources: chaincatcher FARTCOIN 2158328 + pump base-rates 2139008;
rakesh.therani encyclopedia; bubblemaps holder-analysis; nansen; ai16z 2149152.

## WAVE 10 — MEV/Jito bundle detection + institutional smart-money [done]

**JITO BUNDLE — ground-truth detection (upgrades our heuristic bundle guesses, NO auth needed):**
- Bundle = ≤5 txs atomic, same slot, contiguous, adjacent to a TIP transfer. Min tip 1000 lamports.
- **8 Jito tip accounts** (or call `getTipAccounts` for live list) — detect: pull getBlock for launch slot →
  find tx with SOL transfer to a tip account → contiguous same-slot buys ending at that tip = the bundle.
- `getBundleStatuses` (POST mainnet.block-engine.jito.wtf/api/v1/bundles) returns exact tx signatures +
  slot per bundle_id — but LOOKUP-by-id only, no reverse index sig→bundle. bundle_id = SHA256 of sigs.
- **Tip-fingerprinting (cheap high-precision same-operator signal we're NOT using)**: cluster wallets by
  IDENTICAL tip lamports; round-number tips (0.001/0.005/0.01) = scripted; tip >> tip-floor 75th pct =
  aggressive coordinated snipe (pull tip-floor from Jito REST/WS feed); one tip at end of multi-wallet buy
  seq = classic pump bundle.
- **Solana has NO public mempool** — can't front-run pre-land. "Early" = fastest same-slot ingestion
  (ShredStream gRPC / Geyser Yellowstone) + tip-account + contiguity. For atomic same-slot bundle that's
  as early as physically possible.
- 3rd-party: Bitquery Jito Bundle API (Trading.Trades MEV-filtered + Transfers to tip accounts);
  Trench Bot (paste mint → % bundled, wallets/bundle, current-vs-sold per bundle).

**MELT clustering blueprint (arXiv 2602.13480 — replicate this, mirrors our funder-graph):**
- 3 co-ownership heuristics COMBINED: (1) multi-account co-purchase (buy/sell in SAME tx = same owner),
  (2) fund-flow/funder graph (exclude CEX), (3) shared Jito bundle_id = same operator.
- 36.5% of supply bundled at migration avg; high-risk top-10 share jumps +24pp after clustering vs +6pp
  low-risk → **concentration-DELTA-after-clustering is itself the discriminating feature**.
- 122 features / 5 categories; dominant = 59 holding-concentration + 35 bundle-statistics.

**Institutional smart-money definitions (no hard cutoffs published — use these anchors):**
- **Nansen Smart Money**: rule-based top-N-by-PnL per rolling window. Tier N-sizes: 30D ~200 wallets, 90D
  ~410, 180D ~600, 2Y ~850; total universe ~5-10k. Inputs: realized PnL + holding duration + trade count +
  consistency across windows (exact numbers undisclosed). Memecoin caveat: labels calibrated on multi-month
  PnL → "hint not thesis" for memecoins; smart-money accumulation LEADS retail 1-7 days. → replicate as
  top-N-by-PnL-per-window + consistency, NOT a fixed PnL floor.
- **Bubblemaps edge model (most copyable)**: nodes=wallets (size∝balance); edge=transfer; DOTTED=one-way,
  SOLID=bidirectional (stronger same-entity); same-controller wallets share color. **Magic Nodes** = infer
  INDIRECT links via shared counterparty/funder even w/o direct transfer (generalizes our funder-graph).
  Winner="galaxy" (many unconnected), rug="solar system" (one connected cluster).
- **Arkham**: common-input-ownership + co-spend + change-address heuristics + ML + OSINT + crowdsourced labels.
- **Chainalysis wash rule (concrete numbers)**: 1 buy+1 sell within 25 blocks, <1% volume diff, repeated ≥3x
  = wash. + volume-without-price-discovery, fresh→active→dormant lifecycle, uniform gas across "independent"
  wallets. Academic wash-graph (arXiv 2603.13830): self-loops, A→B→C→A cycles, multi-window; RF over graph features.

**Highest-leverage adds**: (1) ground-truth bundle via getTipAccounts+same-slot contiguity; (2) tip-fingerprinting
by identical lamports; (3) concentration-delta-after-clustering feature; (4) Bubblemaps edge typing
(dotted/solid + shared-counterparty); (5) wash graph features (self-loop/cycle/matched-pair 25blk/<1%/≥3x).
Sources: github.com/jito-labs/mev-protos; docs.jito.wtf; docs.bitquery.io Jito-Bundle-api; arXiv 2602.13480;
academy.nansen.ai; blog.bubblemaps.io; arXiv 2603.13830.

## WAVE 11 — attention/mindshare + AMM microstructure/orderflow [done]

**⚠️ KEY NEGATIVE RESULT (contradicts naive use)**: coordinated sniper-cohort presence is SELECTION BIAS
not causal alpha — cohort-touched launches +132% buyers BUT activity-matched PLACEBO wallets showed
LARGER +216% lift (arXiv 2607.02795). → do NOT use "smart sniper bought" as naive bullish; it double-
counts organic flow. (Reconciles with wave 9 U-curve: bots pile onto already-interesting launches.)

**ATTENTION / MINDSHARE (leading indicators):**
- **Kaito Yaps** — FREE public API (api.kaito.ai, docs.kaito.ai). Mindshare best as PRE-launch relative
  ranking (top pre-TGE ~1.2 bps mindshare per $1M raised); weak as intraday timing for live memecoins.
  Use rate-of-change/rank-momentum not level.
- **LunarCrush** — Galaxy Score composite = black-box/weak (company disclaims prediction). Use RAW inputs:
  social-volume VELOCITY + social dominance z-score vs own 7d baseline. API $24-29/mo (no real free).
- **Santiment** — FREE tier (1000 calls/mo, 90d lag). IMPORTANT: social-volume LEVEL is CONTRARIAN
  (entering top-10 = local TOP/exhaustion); social-volume ACCELERATION from low base = the leading signal.
- **Farcaster/Zora/Base content-coins = LEAST-CROWDED EDGE**: Neynar API (free-ish) → trending casts,
  unique-caster velocity, reply/recast velocity, channel propagation. Base App Zora tokenization: coin
  creation doubled in 48h when added to feed. Compute: alert when unique-caster growth OUTPACES on-chain
  buyer growth (attention leading flow). No published lead-time yet = uncrowded.
- **Telegram msg-velocity = evidence-backed** (ACM: TG message count leads BTC next week). FREE via Bot/
  MTProto API — messages/min + net member growth z-scored, weight unique senders. Verify TG is LIVE
  (attached-but-dead = rug tell). Google Trends = too slow/inconsistent for memecoins (skip).
- Academic mechanism: Twitter sentiment Granger-causes returns, lag ≥6h large-cap / <3h some alts →
  memecoins likely compress to minutes (no clean study).

**AMM MICROSTRUCTURE / ORDERFLOW:**
- **Signed OFI acceleration (B1) — best-supported microstructure predictor**: AMM has no orderbook →
  reconstruct from signed swap direction: net(buy-sell) SOL flow per window + acceleration. Top-ranked
  predictor across assets incl. LOW-CAP (arXiv 2602.00776); thin memecoin pools = bigger impact per unit.
  Watch positive OFI ACCELERATION while price still FLAT = accumulation. FREE Bitquery/GeckoTerminal.
- **Wash-adjusted volume via PRICE-IMPACT (B4)**: real buys move price, wash doesn't. Two ratios:
  (1) realized price move per $ volume (Kyle's-lambda) — genuine momentum high, wash ~0; (2) unique
  address diversity vs trade count (few addrs + many trades = wash). 82.8% of >100%-gain tokens showed
  artificial growth; Solana wash ~30% of volume; MemeTrans 21.4% pre-migration txs wash. Upgrades our
  volume/buy-sell features into REAL-MONEY features. FREE.
- **Trades-to-graduation (B2)** — reaffirmed strongest single: fewer trades to reach vSOL = higher grad
  (74.5% near threshold on favorable path); breakeven gate P(grad) > (vSOL/115)². (already partly = our capital-eff)
- **Social-presence hazard (B3)** — TG→8.9x, all-three→17.4x, creator self-buy>30SOL HR 4.51. FREE binary +
  liveness check. (already implemented TG-weighting on pons.)
- **Post-graduation 20-min window**: 73% of tokens drop below 40% of migration price within 20min (insider
  unwind) → graduation = EXIT/timing pivot not all-clear. pump→PumpSwap LP auto-burned (removes LP-rug) BUT
  dev allocation NOT locked. Listen `migrate` instruction (Chainstack/Bitquery). Mark t=0, caution 20min.
- **Free data backbone**: Bitquery free tier + GeckoTerminal free API (Solana DEX trades/curve/LP/migration/
  buy-sell) + Telegram/Neynar social + Kaito Yaps + Santiment free. Sources: arXiv 2602.00776, 2602.14860,
  2607.02823, 2507.01963, 2602.13480, 2607.02795; docs.kaito.ai; docs.neynar.com; bitquery/geckoterminal.

## WAVE 12 — EVM-specific detection (Base/Robinhood) [done]

**GoPlus token_security (Base/EVM static analysis)** — `GET https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={addr1,addr2,...}`; chain_id **8453 = Base**. No API key needed for basic/free access (~30 calls/min free tier); Pro/Ultra needs a signed `access_token` (sha1(app_key+time+app_secret) via console.gopluslabs.io) for batch (100 addrs/query) + higher throughput. Full confirmed field list: `buy_tax, sell_tax, cannot_buy, cannot_sell_all, is_honeypot, is_blacklisted, is_whitelisted, slippage_modifiable, transfer_pausable, is_mintable, owner_change_balance, hidden_owner, external_call, trading_cooldown, personal_slippage_modifiable, can_take_back_ownership, is_open_source, is_proxy, is_anti_whale, is_in_dex, selfdestruct, holder_count, holders[], lp_holder_count, lp_holders[], lp_total_supply, creator_address/balance/percent, owner_address/balance/percent, dex[], total_supply`. Sources: gopluslabs.io/en/token-security-api; docs.gopluslabs.io/reference/tokensecurityusingget_1; github.com/Normalizex/gopluslabs-api.

**GoPlus static vs honeypot.is dynamic — use BOTH, disagreement itself is a signal**: GoPlus = static bytecode/source analysis (catches known patterns pre-emptively, misses novel obfuscation); honeypot.is = live buy→sell tx simulation (catches runtime behavior GoPlus misses, but can't guarantee future-safety since owner can flip a switch post-check). GoPlus-clean + honeypot.is-fails (or vice versa) = elevated-risk signal in itself. Sources: arXiv 2309.04700 (Trapdoor Tokens survey); honeypot.is.

**honeypot.is simulation API** — `GET https://api.honeypot.is/v2/IsHoneypot?address={token}&pair=...&chainID=...&simulateLiquidity=true`. No API key required (free, open). Covers **Ethereum, BSC, Base only** — no confirmed Uniswap V4 support (gap for Clanker v4/Zora v4/Flaunch pools — flag for build team). Returns `honeypotResult.isHoneypot`, `simulationSuccess`, `simulationResult` (buy/sell tax %, maxSell/maxBuy), `holderAnalysis` (holders/successful/failed/siphoned/averageTax/highestTax/taxDistribution — simulates sells across REAL holders, not just querying wallet, a stronger rug-detector than single-wallet probe), `flags[]`. Sources: docs.honeypot.is/ishoneypot; honeypot.is/base.

**Uniswap V2 LP event detection** (classic pairs, e.g. many Clanker v3/v3.1 pools) — topic0 for `eth_getLogs`/Basescan `getLogs`: `PairCreated` → `0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e`; `Mint` → `0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4`; `Burn` → `0xdccd412f0b1252819cb1fd330b93224ca42612892bb3f4f789976e6d81936496`; `Sync` → `0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1`. **LP-lock detection**: check whether LP-token recipient post-Mint is `0x000...dEaD` (burn) or a known locker (Unicrypt/Team Finance) — neither = unlocked/rug-able. **Real-time rug tell**: `Burn` with `to` ≠ pool/expected recipient (LP owner pulling to an EOA), same/next-block large-magnitude `Sync` = classic LP-removal rug (reserves crash). Free via any Base RPC `eth_getLogs` or Basescan/Blockscout. Sources: docs.uniswap.org/contracts/v2/reference/smart-contracts/pair; rareskills.io/post/uniswap-v2-mint-and-burn.

**Uniswap V4 event model — IMPORTANT: Clanker v4, Flaunch, and Zora's CoinCreatedV4 all use this, NOT V2 events**. V4 is a singleton PoolManager (no per-pool contract) — watch: `Initialize(PoolId, currency0, currency1, fee, tickSpacing, hooks, sqrtPriceX96, tick)` (pool creation; non-null `hooks` = custom hook attached, relevant since Clanker/Zora/Flaunch all use hooks) and `ModifyLiquidity(PoolId, sender, tickLower, tickUpper, liquidityDelta, salt)` (ONE event covers add+remove — a rug shows as large-negative `liquidityDelta`, no separate Burn/Sync; must read pool state via `poolManager.getSlot0` since there's no auto Sync event). LP-lock check becomes: does the deployer retain the LP position NFT, or is it held by a locker contract (see Clanker below). Sources: docs.uniswap.org/contracts/v4/reference/core/PoolManager; uniswapfoundation.org/blog/how-to-navigate-uniswap-v4-data.

**EVM multi-hop funder-graph** — Etherscan API V2 unified endpoint `api.etherscan.io/v2/api?chainid=8453&module=account&action=txlistinternal|txlist|...&address=`; free tier 5 calls/sec /100k calls/day, but **free tier has been shrinking** (July-2026 cut max records/request 10k→1k, some chains losing free coverage — verify current status before relying on it). **Blockscout is the better free fallback**: `base.blockscout.com` REST API v2, `GET /api/v2/addresses/{hash}` + internal-tx endpoints, no key needed for basic use (IP-rate-limited not key-limited); paid Pro API tier exists but also recently cut bulk "internal-tx-by-block-range" + per-request limits. Net recommendation: for k≥3-hop walkback, direct `eth_getLogs`/`eth_getBlockByNumber` via a free/cheap RPC is more reliable than either explorer's shrinking free API. Sources: docs.etherscan.io/etherscan-v2/rate-limits; docs.blockscout.com/devs/apis/requests-and-limits; base.blockscout.com/api-docs.

**Clanker (Base) on-chain launch detection** — Factories: v3.0.0 `0x375C15db32D28cEcdcAB5C03Ab889bf15cbD2c5E`; v3.1.0 `0x2A787b2362021cC3eEa3C24C4748a6cD5B687382`; v4.0.0 `0xE85A59c628F7d27878ACeB4bf3b35733630083a9`. `TokenCreated(tokenAddress, lpNftId, deployer, name, symbol, supply, _supply, lockerAddress)` — `lockerAddress` tells you which contract holds the LP NFT (v4 uses `ClankerLpLockerFeeConversion`, auto-collects/distributes fees to ≤7 reward recipients; a `lockerAddress` NOT matching Clanker's known official lockers = possible fork with rug-capable LP custody = red flag). v4 has pluggable MEV modules (e.g. `ClankerMevDescendingFees` — LP fee starts up to 80%, decays parabolically ≤2min, a built-in sniper-tax — presence is a mild legitimacy/positive signal) + a public `ClankerSniperAuctionV0`. Public API at clanker.world/docs/api-reference/public (site blocked automated fetch this pass — needs direct human check); Bitquery has a paid "Base Clanker API". Sources: clanker.gitbook.io/clanker-documentation/references/deployed-contracts; clanker.gitbook.io/documentation/references/core-contracts/clankertoken-v3.1.0-and-v4.0.0.

**Zora (Base) on-chain launch detection** — Single `ZoraFactory` at **the same address on every supported chain incl. Base**: `0x777777751622c0d3258f214F9DF38E35BF45baF3`. Events: `CoinCreated(...)` for classic pools; `CoinCreatedV4` (Content Coins) and `CreatorCoinCreated` (Creator Coins) for V4-based coins — both emit a full `PoolKey`+`poolKeyHash` (no pool address, since V4 has none). All hook contracts consolidated into a single `ZoraV4CoinHook` (SDK v2.3.0+). Public REST API `api-sdk.zora.engineering/api` (Swagger at .../docs) — **requires an API key** (not anonymous like GoPlus/honeypot.is); Explore-feed queries (new/trending/top-gainer) work as a "new launch" firehose without watching factory events directly. Farcaster/Base-App tie-in: Zora coins are the mechanism behind Farcaster post-tokenization + Coinbase "Creator Coins" in the Base App. Sources: docs.zora.co/coins/contracts/factory; docs.zora.co/coins/sdk/public-rest-api; docs.zora.co/coins/contracts/hook.

**Flaunch (Base)** — Factory `0xfdCE459071c74b732B2dEC579Afb38Ea552C4e06`, built on Uniswap V4 (hooks-based like Clanker v4/Zora). `PoolCreated(_poolId, _memecoin, _memecoinTreasury, _tokenId, _currencyFlipped, _flaunchFee, _params)`. Official SDK (`@flaunch/sdk`) has `getPoolCreatedFromTx()` + a `usePoolCreatedEvents` React hook — lowers the lift vs raw log-decoding. Sources: docs.flaunch.gg/developer-resources/contract-addresses; github.com/flayerlabs/flaunch-sdk.

**Virtuals Protocol (Base) — research gap flagged**: core launch contract is `AgentFactoryV3`; original "Genesis" launchpad flow replaced late-2025 by a system called "Unicorn" (mechanism overhaul). No exact Base contract address for AgentFactoryV3/Unicorn was recoverable from search alone — needs a direct Basescan/whitepaper.virtuals.io lookup. Virtuals is dual-chain: Base agents get a Uniswap V2 LP, Solana-side agents get a Meteora pool — these are separate venues, not literally bridged. Sources: whitepaper.virtuals.io/builders-hub/agent-launch-mechanisms/more-on-standard-launch.

**Robinhood Chain (not previously scoped for EVM detection)** — Mainnet live July 1, 2026; Arbitrum Orbit L2 settling to Ethereum, **chainId 4663**, gas=ETH, public RPC `rpc.mainnet.chain.robinhood.com`, explorer is a **Blockscout instance** (`robinhoodchain.blockscout.com`, supported by Blockscout Pro API). Practical implication: all Base Blockscout-based funder-graph/log tooling should be directly reusable on Robinhood Chain by swapping chain_id/host. **GoPlus/honeypot.is coverage of chainId 4663 NOT confirmed** (too new / not in either's published chain list) — open item: probe `token_security/4663/...` and `IsHoneypot?chainID=4663` directly. Sources: docs.robinhood.com/chain/connecting; blog.arbitrum.io/robinhood-chain-mainnet; blog.blockscout.com/build-on-robinhood-chain-with-the-blockscout-pro-api.

**Open follow-ups** (docs sites 403'd to automated fetch, need human/browser check): clanker.world/docs/api-reference/public full spec, docs.honeypot.is full JSON schema, docs.gopluslabs.io full param reference, docs.bitquery.io Base Clanker GraphQL schema.

## WAVE 13 — ML feature-combination + backtesting methodology [done]

**⚠️ DIRECT PRIOR ART (closest thing to our exact problem)**: arXiv 2602.14860 (Marino/Naviglio/Tarantelli/
Lillo, "Predicting the success of new crypto-tokens: the Pump.fun case") explicitly modeled graduation-
probability conditional on bonding-curve SOL-locked state, but used non-parametric binning + control
charts for dump-detection and explicitly declined to fit Kaplan-Meier/Cox/logit/ML, flagging those as
future work → the GBM/scorecard gap we're closing is genuinely open, not solved-and-ignored. arXiv
2607.02823 (survival/Cox, already in wave 9/11) is the closest published outcome model but is hazard-based
not classification-based. A Medium writeup (Krzeckovskij, Apr 2026) built literal RandomForest-on-
extreme-imbalance for pump.fun graduation from first ~100 blocks/~40s of life — directionally validates
"tree ensemble + short early-window features" as viable but is a blog post, not peer-reviewed (treat as
weak-tier corroboration only). Sources: arxiv.org/abs/2602.14860; arxiv.org/pdf/2607.02823;
medium.com/@alleg88/predicting-pump-fun-token-graduation-with-random-forest-on-extremely-imbalanced-data.

**1. MODEL CHOICE for 1-in-10k+ positive rate, tabular features:**
- **GBM (LightGBM/XGBoost/CatBoost) is the established default for tabular data generally** — tree
  ensembles beat deep nets on medium-sized tabular data because their inductive bias (axis-aligned splits,
  rotation-non-invariance, native robustness to uninformative/irrelevant features) matches tabular data's
  structure; DL needs much more data/tuning to match (Grinsztajn et al. 2022, NeurIPS, "Why do tree-based
  models still outperform deep learning on typical tabular data?"). No memecoin-specific paper compares
  GBM-vs-logit directly, so this is generalized-from-adjacent-domain, not memecoin-native evidence.
- **Handling the imbalance itself — use loss reweighting, NOT resampling, as the primary lever**:
  `scale_pos_weight` (XGBoost) / `is_unbalance` (LightGBM) ≈ ratio of neg:pos (for us ~19,999:1 theoretical,
  but tune don't trust the formula value — empirically the naive ratio overweights and hurts precision;
  grid-search scale_pos_weight ∈ {1, 10, 50, 100, ratio} and pick by AUPRC not accuracy).
  Source: woteq.com/how-to-use-xgboost-scale_pos_weight-parameter; apxml.com boosting-imbalance chapter.
- **SMOTE — AVOID or heavily restrict for our regime.** Known failure modes directly applicable to us:
  (a) generates synthetic points by interpolating between minority neighbors — with our ~1:20,000 ratio the
  few real winners are so sparse that "neighbors" are often not meaningfully similar, so synthetic points
  land in implausible regions of feature space (fabricated bundler%/top10%/smart-money combos that never
  co-occur in reality); (b) high-dimensional blowup — extreme values stop being exceptional once you have
  dozens of correlated concentration/social/microstructure features, so SMOTE's convex-hull assumption
  breaks down; (c) can silently leak info if oversampling is done BEFORE train/test split (classic bug —
  synthetic test points get "seen" via their real-point neighbors during training). If used at all: fit
  only inside the training fold, and prefer variants that filter implausible synthetic points ("conservative
  plausibility-filtered SMOTE", Frontiers 2026) over vanilla SMOTE. Sources: Frontiers 2026 (frontiersin.org
  10.3389/frai.2026.1871972); Springer 2022 theoretical-distribution analysis (10.1007/s10994-022-06296-4).
- **Undersampling vs class-weighting — no consistent winner empirically**; large empirical study found
  resampling changed AUPRC materially in only ~12% of cases and was MORE likely to hurt than help; when it
  does help, undersampling trades recall-up for majority-class info loss / higher variance (fewer effective
  training rows). → **recommendation for us: class-weighting (or focal loss) as default; only add
  undersampling as a secondary experiment, always compared against the weighted-baseline on AUPRC, never
  assumed better.** Source: PMC9333262 empirical evaluation of sampling methods.
- **CatBoost-specific edge relevant to us**: ordered target-statistics + ordered boosting specifically
  prevent target leakage from categorical/high-cardinality features (e.g. launchpad name, DEX, deployer
  cluster ID) without manual target-encoding — useful since several of our features are effectively
  categorical (launchpad, chain, social-platform-present). Source: arXiv 1706.09516 (CatBoost paper).

**2. EVALUATION METRIC — AUPRC + operating points, not AUC-ROC:**
- **Why AUPRC**: under extreme imbalance, TN is enormous, so FPR = FP/(FP+TN) stays near-zero even when
  the model generates thousands of false positives — ROC curves look deceptively good while precision
  (what actually matters when a human/bot has to act on every alert) collapses. AUPRC uses precision
  (TP/(TP+FP)) directly, which is sensitive to exactly the failure mode we care about (too many false
  alerts burning capital/attention). As prevalence p→0, precision ≈ (p·TPR)/((1−p)·FPR) → 0 unless FPR is
  driven extremely small — formalizes "FP tolerance must be brutal." Sources: towardsdatascience.com
  imbalanced-data-stop-using-roc-auc; NeurIPS 2024 "A Closer Look at AUROC and AUPRC under Class Imbalance"
  (dl.acm.org/doi/10.5555/3737916.3739316) — caveat: this paper shows AUPRC is NOT universally superior in
  all imbalance regimes and can unfairly favor subpopulations with higher local positive rates, so don't
  treat AUPRC as a silver bullet either — report both, plus operating points below.
- **Operating-point reporting (the actually-actionable numbers for us)**: report precision@top-K (e.g.
  precision among our top 100 highest-scored alerts per week — directly answers "if we only acted on the
  best N alerts, how many won") AND recall-at-fixed-FP-budget (e.g. "at ≤X false alerts/day, what fraction
  of eventual winners did we still catch") — the latter mirrors how security/fraud teams report under
  analyst-capacity constraints ("≤k false alarms per N items reviewed"). Concretely for us: pick FP budget
  = alerts/day the team can actually act on, sweep threshold, report recall at that FP count. Source:
  arXiv 2601.18696 (hardware-trojan detection, exact framing "recall at fixed FPR budget", reports e.g.
  55.6% recall at ≤11 FPs / 11,392 gates at FPR≤0.1% — same shape of problem as ours).

**3. CALIBRATION — isotonic vs Platt vs WOE scorecard (our stated goal: kill hand-tuned weights):**
- **Isotonic regression**: non-parametric, only assumes monotonicity — flexible enough to fix any shape of
  miscalibration, but overfits with sparse data, especially in the thin high-score tail (exactly where we
  have the fewest labeled winners). Rule of thumb from calibration literature: isotonic ≥ Platt once
  calibration set is ~1000+ points; below that, Platt is safer. **Our alert volumes (thousands-tens of
  thousands total, but likely only tens to low-hundreds of POSITIVE outcomes) put us in the danger zone for
  isotonic specifically in the region that matters most (top of the score distribution) — use Platt (or
  isotonic with heavy regularization / binned isotonic) until positive-label count is large.** Source:
  Niculescu-Mizil & Caruana ICML05 "Predicting Good Probabilities with Supervised Learning"
  (cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf); abzu.ai calibration-intro-part-2.
- **WOE/scorecard approach — directly matches our "move off hand-weights" goal, recommend as primary path**:
  Weight of Evidence for a bin = ln( %(non-events in bin) / %(events in bin) ) [or the inverse sign
  convention — pick one and be consistent]; equivalently ln(good/bad odds in bin vs overall). Bin each raw
  feature (bundler%, top10%, sniper-count, smart-money-count, etc.) into ~5-10 monotonic bins (constrained
  so WOE is monotonic in the raw feature — enforced via optimal-binning solvers, not manual cutoffs) →
  Information Value per feature = Σ_bins (%good − %bad) × WOE_bin, standard IV interpretation bands: <0.02
  useless, 0.02-0.1 weak, 0.1-0.3 medium, 0.3-0.5 strong, >0.5 suspicious/likely-leaky. Fit logistic
  regression on the WOE-transformed features (not raw features) — **the resulting logistic coefficients ARE
  literally what our current "hand-tuned weights" are trying to approximate by eyeball**: WOE values are
  mathematically identical to the coefficients from a logistic regression with the raw categorical
  indicators (planspace.org "Weight of Evidence is logistic coefficients"). Final score = intercept + Σ
  (coefficient_i × WOE_i) → a fully principled, auditable log-odds sum that REPLACES our ad hoc weighted
  sum with data-fit weights, keeps the same "sum of feature contributions" mental model the team already
  uses, and gives free bin-level interpretability for debugging ("this alert scored high because bundler%
  bin contributed +2.1 log-odds"). Practical tooling: OptBinning (convex/MIP optimal binning with monotonic
  constraints, ~17x faster than scorecardpy per benchmark) or scorecardpy. Sources: listendata.com WOE-IV;
  ucanalytics.com banking-case-study; planspace.org/20210917-weight_of_evidence_is_logistic_coefficients;
  github.com/guillermo-navas-palencia/optbinning; arXiv 2509.09855 (info-theoretic scorecard framework).

**4. WALK-FORWARD / OUT-OF-TIME VALIDATION — concrete structure against alerts.jsonl + snapshots.jsonl:**
- **Naive k-fold leaks via regime correlation**: random k-fold shuffles alerts across time, so a model can
  "learn" that e.g. bundler% > X was predictive during the Sept-2025 bull window and get tested on OTHER
  Sept-2025 alerts in a held-out fold — this leaks the market-regime signal (graduation base rate was
  ~0.63% then vs ~0.2% now per our own context) rather than testing genuine feature predictiveness.
- **Purged K-Fold + embargo (López de Prado, standard in financial ML)**: for each alert in a test fold,
  its label isn't "resolved" (graduated/rugged/mooned) until some maturity horizon (e.g. 7/30/90 days of
  snapshots.jsonl data) after alert time. PURGE: remove from the training set any alert whose
  label-formation window [alert_ts, alert_ts+maturity] overlaps the test fold's time range — otherwise
  training rows can "see" outcomes that happened concurrently with/inside the test window via correlated
  market conditions. EMBARGO: additionally exclude a buffer period immediately after each test fold from
  training, since features computed near the fold boundary can still encode short-horizon leakage.
  Source: en.wikipedia.org/wiki/Purged_cross-validation; risklab.ai financial cross-validation writeup;
  López de Prado "Advances in Financial Machine Learning" (industry-standard reference, not fetched
  directly here but the purging/embargo algorithm is reproduced across the sources above).
- **Concrete recipe for alerts.jsonl/snapshots.jsonl**: (1) sort alerts.jsonl by alert_ts; (2) define
  label-maturity horizon per outcome type (e.g. "rugged" can resolve in hours, "graduated" in days,
  "mooned to $10M" may take weeks — use the LONGEST relevant horizon, or model each outcome separately with
  its own horizon, pulling the outcome from snapshots.jsonl at t=alert_ts+horizon, or first-crossing time if
  earlier); (3) build rolling walk-forward splits: train on alerts with alert_ts < T, purge any training
  alert whose maturity window extends past T, embargo an extra buffer, test on alerts with alert_ts ∈
  [T, T+Δ]; (4) slide T forward in fixed steps (e.g. monthly) — this is the walk-forward analog and is
  strictly preferred over a single train/test split because it also SHOWS drift (see #6) — track AUPRC per
  window over time, don't just report one aggregate number.
- **Immature labels at the right edge**: any alert within the last `maturity_horizon` of "now" doesn't have
  a resolved outcome yet — exclude these from train/test entirely (don't label them as negative just
  because they haven't mooned yet — that's a subtle but common bug that injects false negatives near the
  most recent, most-regime-relevant data). Related concept: "outcome maturity" / delayed-ground-truth
  monitoring — arXiv 2604.15740 formalizes this as label-freshness/blind-period tracking for risk-decision
  systems (their finding: pure concept-drift with constant P(X) is undetectable by feature-only proxies,
  reinforcing that we need the actual matured outcome labels, not shortcuts).

**5. SURVIVORSHIP / LOOK-AHEAD BIAS from only tracking alerted tokens:**
- **The core problem stated precisely**: alerts.jsonl is a biased sample — it's conditioned on our OWN
  scanner having already decided the token looked interesting, so any backtest of "does feature X predict
  outcome" is confounded by "features that made OUR heuristic score it high" — we can validate ranking
  WITHIN alerted tokens, but can't learn true base rates or true feature/outcome relationships for the full
  launch population from alerts.jsonl alone. This is exactly the observational "selection on treatment"
  setup in causal inference.
- **Two practical fixes, in order of practicality for us**:
  (a) **Stratified/matched random sampling of NON-alerted launches ("shadow" control), on the same chain/
  launchpad/time-bucket as each alert** — pull a random sample of tokens from the SAME source (pump.fun/
  flap/etc.) launched in the same time window that did NOT trigger an alert, snapshot them the same way
  (price/mcap/holders over time) so snapshots.jsonl-equivalent history exists for controls too. This is the
  cheap, good-enough-for-most-purposes fix: lets you compute true base rates, and lets you check whether
  alerted-and-won tokens actually differ from a matched random launch, not just from other alerted tokens.
  (b) **Inverse-propensity weighting (IPW) framing, if (a) alone proves insufficient**: model
  P(alerted | features-at-launch) (a propensity model — literally: fit a classifier on
  alerted-vs-shadow-sampled-controls using the same features), then weight alerted observations by
  1/P(alerted|X) when estimating outcome relationships — this is the same machinery as IPTW in
  observational medical studies correcting for confounded treatment assignment (in our case "treatment" =
  "our own scanner alerted on it"). Doubly-robust variants (combine propensity weighting + outcome
  regression) are more robust to propensity-model misspecification if we go this route. This is more
  statistically rigorous but needs the shadow-control data from (a) to even fit the propensity model — so
  (a) is a prerequisite either way, not an alternative. Sources: academic.oup.com/ckj IPTW intro;
  pmc.ncbi.nlm.nih.gov/PMC7377436 weighted-nearest-neighbor control selection; sciencedirect.com
  survivor-bias-in-case-control (stratify-on-survival-time + negative-control framing, directly analogous).
- **Assessment for our stated question ("is stratified random sampling sufficient, or do we need IPW")**:
  stratified/matched random sampling of non-alerts is the RIGHT FIRST STEP and likely sufficient for our
  main use cases (estimating true base rates, sanity-checking whether alerted tokens actually outperform
  random launches, checking if hand-picked features have any signal at all pre-alert). Full IPW/causal
  machinery is over-engineering until (a) is in place and shows a real signal worth refining — treat IPW as
  a v2 refinement, not the wave-1 fix.

**6. DRIFT / REFIT CADENCE — PSI + rolling windows:**
- **Population Stability Index (PSI)** — standard credit-risk drift metric, compares a feature's (or the
  score's) distribution between a reference window (e.g. model-training period) and a current window across
  the same bins: PSI = Σ_bins (%current − %reference) × ln(%current/%reference). Thresholds (industry
  convention): PSI < 0.1 stable, 0.1-0.25 moderate shift/watch, > 0.25 significant shift → retrain trigger.
  Apply PSI to (a) each raw feature's distribution AND (b) the final score distribution AND (c) the
  graduation/outcome base rate itself — given our stated 0.63%→0.2% base-rate drift over 8 months, base-rate
  PSI will almost certainly breach 0.25 well before 8 months elapse, meaning refit cadence should be driven
  by MONITORING PSI continuously, not a fixed calendar cadence. Sources: coralogix.com PSI intro;
  fiddler.ai PSI blog; geeksforgeeks.org PSI; note a 2026 statistical-testing refinement exists (turns PSI
  into a proper hypothesis test with Type I/II error control) if ad hoc thresholds prove noisy at our alert
  volumes — crc.business-school.ed.ac.uk sample-size-dependent PSI paper.
  - **Concrete cadence recommendation**: rolling 30-day training window as default (matches typical
  memecoin-cycle attention half-life faster than the 90-day windows credit-risk uses, given how fast
  regimes shift in this market per our own base-rate-drift observation) + PSI computed weekly on the score
  distribution and top-3 raw features by IV; trigger an out-of-cycle refit if PSI > 0.25 on the score or
  base rate before the 30-day mark. Exponential recency-weighting of training samples (w_i = exp(−λ·age_i))
  as an alternative/complement to hard rolling windows — softer than a cliff-edge window cutoff, lets old
  data still contribute a little rather than vanishing abruptly. Source: general online-learning concept-
  drift literature (fading-factor weighting is standard in streaming ML, e.g. surveyed via
  researchgate.net/publication/220571390 "Learning drifting concepts: example selection vs example weighting").

**7. SIGNAL DECORRELATION — bundler%/top10%/insider% triple-counting problem:**
- **Tree-based models (GBM) handle correlated features natively** — at each split, the tree picks whichever
  correlated feature best separates the current node's data; it does NOT sum contributions from all
  correlated features simultaneously the way a naive hand-weighted linear sum does, so switching from
  "ad hoc weighted sum" to a GBM largely SOLVES the triple-counting problem as a side effect of the model
  choice in #1 — this is a genuine advantage of GBM over both hand-weights and plain (non-WOE) logistic
  regression for us. Caveat: correlated features still split GBM feature-importance credit somewhat
  arbitrarily between them (importance gets "shared" across correlated proxies), so use permutation
  importance or SHAP for interpretability rather than raw split-count/gain importance when correlated
  features are present.
- **If sticking with a linear/WOE-scorecard approach (recommended path in #3), decorrelation is NOT
  automatic and must be handled explicitly**: (a) simplest — group correlated features (bundler%/top10%/
  insider% all = "concentration" group) and cap the group's total log-odds contribution, or keep only the
  single highest-IV feature per group and drop/shrink the rest; (b) PCA/factor analysis on the concentration
  sub-block only (not the whole feature set, since mixing e.g. social features with concentration features
  in one PCA would produce uninterpretable components) — first principal component of {bundler%, top10%,
  insider%} likely captures ">90% of shared variance as a single 'concentration factor'", feed that single
  factor into the scorecard instead of three raw features; (c) VIF (variance inflation factor) screening —
  drop/merge features with VIF > 10 before fitting the linear scorecard, a standard multicollinearity
  diagnostic. Practical recommendation for us: (a) is the cheapest and most auditable (matches "group
  correlated signals, cap combined weight" mental model already close to how the team thinks about scoring)
  — reserve PCA for the concentration sub-block specifically if (a) proves too coarse. Sources:
  medium.com/@chandradip93 multicollinearity-tree-models; group-wise-PCA-in-boosting concept (apxml.com /
  general boosting literature); standard VIF>10 threshold (widely-cited applied-stats convention).

**CONCRETE END-TO-END PIPELINE recommendation against our two files:**
- Labeling: for each alerts.jsonl row, join snapshots.jsonl by token_id, compute outcome at horizon(s)
  (rugged/graduated/mooned-$10M) using first-crossing-time logic, drop alerts younger than the maturity
  horizon (immature/right-censored — exclude, don't zero-fill).
- Controls: for each alert, sample K random non-alerted launches from the same launchpad+week (needs new
  data collection — currently NOT in either file — this is the single highest-leverage new pipeline to
  stand up, since every other item here is bounded by this bias until it exists).
- Model: GBM (LightGBM, class-weighted, monotonic-constraints on features with clear risk direction e.g.
  higher top10% → monotonically non-decreasing risk) as primary; parallel WOE-scorecard/logistic as the
  interpretable/auditable model that also directly replaces hand-weights — run both, compare AUPRC.
- Validation: purged walk-forward over alert_ts, monthly step, report AUPRC + precision@top100 +
  recall@fixed-FP-budget PER WINDOW (not just averaged) to surface drift directly.
- Monitoring: weekly PSI on score + top-IV features + realized base rate; refit trigger at PSI>0.25 or
  30-day cadence, whichever first.
Sources (wave 13 aggregate): arxiv.org/abs/2602.14860; arxiv.org/pdf/2607.02823; arXiv 1706.09516 (CatBoost);
Grinsztajn et al. NeurIPS 2022 (tabular vs DL); dl.acm.org/doi/10.5555/3737916.3739316 (AUROC/AUPRC NeurIPS
2024); arXiv 2601.18696 (recall@FP-budget); cs.cornell.edu/~alexn calibration ICML05; arXiv 2509.09855
(WOE scorecard framework); listendata.com + planspace.org (WOE=logit-coefficients); github.com/guillermo-
navas-palencia/optbinning; en.wikipedia.org/wiki/Purged_cross-validation; risklab.ai cross-validation;
arXiv 2604.15740 (delayed ground truth/outcome maturity); academic.oup.com/ckj (IPTW); sciencedirect.com
survivor-bias-case-control; coralogix.com/fiddler.ai (PSI); crc.business-school.ed.ac.uk (PSI stat test);
PMC9333262 (undersample vs weight empirical); Frontiers 2026 10.3389/frai.2026.1871972 (SMOTE pitfalls).

## WAVE 14 — Public alpha-wallet / KOL datasets [done]

**kolscan.io (Solana)** — now **owned by pump.fun** (acquired July 2025, made free). Three pillars: live Trades feed, Tokens, Leaderboard (`kolscan.io/leaderboard`, ranks by realized PnL/ROI/win-rate/volume across time windows). Website-UI only — **no public documented API**; direct fetch 403'd (bot-blocked), addresses visible on-page so scrape-feasible with a headless browser. Related: **kolscan.fun** = a dedicated **Robinhood Chain** KOL tracker (directly relevant, one of our target chains). SolanaTracker mirrors kolscan data via its own API (see below) — likely the easiest API-accessible route to kolscan-equivalent addresses. Sources: blockworks.com/news/pump-fun-kolscan; theblock.co/post/362119; kolscan.fun.

**Dune Analytics — public queries with actual address output** (beyond adam_tehc/pump-fun-alpha-wallets, already known): `dune.com/adam_tehc/pumpfun-wallet-analysor`, `dune.com/dunesleuth/top-pumpfun-traders`, `dune.com/rpat/pump-fun-top-wallets-6h-hold-1min` (bakes in an anti-sniper ≥1min-hold filter), `dune.com/dev2020/solana-alphas` — **most parameterized found**: "Solana alpha wallets across 31 trading bots" with interactive filters (Bot, Balance, Min win ratio, Min tokens bought, Recent activity days, Min scalp ratio). Also `pixelz/solana-alpha-wallet-signals`, `couldbebasic/top-traders`, `couldbebasic/wallet-analyzer-for-copy-traders`, `queries/5114926` ("Alpha Wallets v2"), `holder_bro/alpha-wallets-dashboard-checker`. **Base/Clanker/Zora Dune coverage exists but is token/protocol-level, NOT wallet-ranking** (`openrank/clanker-scores-dashboard`, `luccnx/zora-creator-coins-trading-dashboard`, `clanker_protection_team/awesome-clanker`) — Base smart-money-by-wallet is underdeveloped on Dune vs Solana. **Dune API economics**: query results cached by default (free/cheap if not force-re-run); new pricing is credit-based/compute-proportional; practical free pattern = pin/refresh query on the website UI (free) and scrape the rendered CSV rather than paying for programmatic re-execution. Sources: docs.dune.com/api-reference/overview/billing; dune.com/blog/credits-changing.

**Cielo Finance** — API at `developer.cielo.finance` (portal `build.cielo.finance`): Get Tracked Wallets, Token PnL (per-wallet/token), Aggregated Token PnL endpoints. Docs explicitly describe using the API to **"build custom scripts to automate wallet discovery: fetch trending wallets by Chain, PnL, Winrate, Hold Time, Last Trade"** — i.e. usable as a discovery source, not just lookup. Covers 30+ chains **including Solana AND Base**. Free tier exists (limited alert caps); PnL/discovery endpoints need Builder/Architect/Enterprise (Pro $59/mo, Whale $199/mo) — free tier likely insufficient for bulk seeding. Sources: developer.cielo.finance/reference/gettrackedwallets; docs.cielo.finance/guides/copy-trading/finding-good-wallets; developer.cielo.finance/docs/supported-chains.

**Birdeye** — `GET /trader/gainers-losers` (public leaderboard, also viewable free at birdeye.so/trader-board); `GET /defi/v2/tokens/top_traders` (per-token, sortable by total/unrealized/realized PnL, 2d-90d windows, **Solana only**); `GET /wallet/v2/pnl/multiple` (batch wallet PnL, beta, universal 5 req/sec / 75 req/min cap regardless of tier). Batch/trader endpoints need **Business package+**; basic Lite/Starter tier can't hit them — free bulk pulls not really available, but the UI leaderboard is free to view/scrape manually. Sources: docs.birdeye.so/reference/get-trader-gainers-losers; docs.birdeye.so/reference/get-defi-v2-tokens-top_traders; docs.birdeye.so/reference/get-wallet-v2-pnl-multiple.

**GMGN.ai** — no self-serve public dev-key portal, but GMGN's own official skill spec (github.com/GMGNAI/gmgn-skills, `skills/gmgn-track/SKILL.md`) documents concrete endpoints: `/v1/user/kol` and `/v1/user/smartmoney` (GET, 20 req/s rate limit, params `--chain` required + `--limit` 1-200 + `--side`). **Chains for kol/smartmoney: sol, bsc, base, eth** (robinhood excluded from these two specifically, but included for other track commands — `gmgn.ai/trend?chain=robinhood` confirms Robinhood Chain IS tracked by GMGN generally). Wallet fields: `maker_info.name/.twitter_username/.tags(smart_degen/KOL/fresh)/.tag_rank`; third-party scrapers describe 50+ fields (realized profit, win rate, tx count, holding period, daily-profit history, Twitter, ENS). Requires an API key. **No standalone ranking/leaderboard endpoint documented** — the visible `/rank` UI is separate from these query endpoints, must reconstruct ranking client-side or scrape `/rank`'s internal XHR calls. Apify marketplace has 3rd-party GMGN scrapers (wallet stats, copytrade wallets, token top-traders) if the above proves inaccessible. Best Base "smart-money" source found overall. Sources: raw.githubusercontent.com/GMGNAI/gmgn-skills/main/skills/gmgn-track/SKILL.md; gmgn.ai/trend?chain=robinhood.

**SolanaTracker** — `getPnlV2TopTraders({days, pnlMode, limit})` → `/v2/pnl/leaderboard/top`; `getTopTraders(1,true,'total')` for cross-token top traders; 70+ endpoints incl. token leaderboards + first-buyers-with-PnL. **Free tier: 2,500 requests/month** (paid ~€50/€200/€397/mo). Also mirrors a "Kolscan Leaderboard" page (`solanatracker.io/leaderboard/kolscan`) — likely the easiest API-accessible route to kolscan-equivalent data. Real API, addresses+PnL returned directly, usable free tier for prototyping. Sources: docs.solanatracker.io; madeonsol.com/pricing (third-party pricing summary).

**Base/EVM sources summary**: GMGN (first-class Base chain, same tag system as Solana) is the strongest free-ish Base source; **Nansen Smart Money dashboard** (`app.nansen.ai/smart-money`) covers Base+Arbitrum+Polygon+BNB+Avalanche+Solana with a PnL leaderboard + live DEX feed, but the labeled-wallet list is paywalled at Standard ($99/mo)+/VIP ($1,899/mo); free tier exists but doesn't expose the list. Cielo covers Base natively (paid). Dune has no clear Base equivalent of pump-fun-alpha-wallets yet. **Robinhood Chain**: kolscan.fun + GMGN `chain=robinhood` are the two trackers found; a "stalkchain" family also runs a BSC KOL leaderboard (bnb.stalkchain.com/kol-leaderboard), suggesting per-chain expansion pattern worth watching. **Arc (Circle's stablecoin L1, not our Arc DEX Scan chain)**: no memecoin/KOL tooling exists — it's built for stablecoin/FX settlement, out of scope for smart-money seeding for the foreseeable future. Sources: nansen.ai/post/nansens-new-smart-money-dashboard; app.nansen.ai/smart-money; stalkchain.com/blog/how-to-track-wallets-on-robinhood-chain.

**Bootstrap recipe — refined against findings**: keep **>$10k realized PnL** floor for Solana (validated: top 0.5% per prior research); no Base percentile data exists yet — start with same $10k floor, recalibrate once data collected. **Win-rate >60%** validated directly by GMGN's own `smart_degen` definition (win-rate>0.6 AND PnL-ratio>1) — a live production system, not just a guess, keep it. **NEW: add a minimum trade-count floor (≥15-20 closed trades)** before trusting win-rate/PnL — not in the original recipe; justified by Dune's dev2020/solana-alphas dashboard exposing "Min tokens bought"/"Recent activity days" as first-class filters in practice. Keep the **≥2-independent-source cross-validation** requirement (best defense against one-hit-wonders; kolscan/GMGN/Dune tag-agreement can serve as the ≥2 sources). **NEW: add explicit decay/expiry** — literature says alpha decays and crowds cannibalize it fast ("the second a wallet gets enough followers, its picks become self-fulfilling... late copiers become exit liquidity"); recommend rolling 14-30 day re-evaluation, auto-demote on trailing-30D win-rate <60% or >14 days inactivity. **NEW: flag late-entry copy-trader wallets** (entries consistently AFTER a token's initial volume spike can still show positive PnL by providing exit liquidity to earlier buyers, but have null signal value) — filter via entry-timing-percentile within a token's trade sequence, not PnL alone; several dashboards already implicitly do this via hold-time filters. **Practical pipeline**: (1) SolanaTracker `/v2/pnl/leaderboard/top` (free, 2500 req/mo) + GMGN `/v1/user/smartmoney` (sol/base/eth/bsc) as cheapest API sources; (2) cross-reference against Dune dev2020/adam_tehc CSV exports (free via UI) for Solana; (3) Cielo free-tier for Base supplement; (4) kolscan.fun + GMGN chain=robinhood for Robinhood Chain; (5) apply thresholds above as accept/demote gate.

**Methodology caveat**: most primary sites (dune.com, kolscan.io, gmgn.ai, docs.birdeye.so, docs.solanatracker.io, docs.cielo.finance) 403'd direct WebFetch (bot-blocked) — findings reconstructed from search-result snippets plus one successful direct fetch (GMGN's GitHub-hosted skill spec via raw.githubusercontent.com). Treat exact numeric thresholds (rate limits, pricing) as approximate pending live verification before hard-coding into scanner config.

## WAVE 15 — Telegram alpha-caller track records [partial]

- **Call Analyser** (`@CallAnalyser`/`@CallAnalyserBot`/`@TokenPingBot`, per-chain spinoffs incl. `@CallAnalyserSol`) — bills itself "listing qualified call channels only," posts a numeric Score (seen 31-60/100) per call + mcap/perf stats, ~50k subs. Direct fetch of `t.me/s/CallAnalyserSol` blocked (403) — methodology/API unconfirmed, only inferable via third-party stat sites (telemetr.io, tgstat.com).
- **No free/scrapeable cross-channel API confirmed.** Closest: github.com/OkoyaUsman/telegram-group-crypto-call-analyzer (open-source TG bot) — monitors groups for contract addresses, computes TP/SL at 12h/24h/48h via the **Birdeye API** (needs your own paid key) — no cross-channel correlation built in.
- **CoinCodeCap** (signals.coincodecap.com) logs every signal (win/loss/stop-out) to a public auditable Google Sheet — most transparent approach found, but manual/curated, not an API.
- **"N distinct alpha channels called token X within Y minutes" — no existing tool does this.** Would require independently scraping multiple channels (contract-address regex) + building an in-house timestamp-clustering layer — same shape as the OkoyaUsman bot's ingestion, extended cross-channel. Nothing off-the-shelf; would need to be built, mirroring the smart-money wallet-cluster idea but on message timestamps.
- **Known pitfalls**: self-reported win-rates are unverifiable noise (channels like Binance Killers claim 97%+ with no independent audit); "qualified-channel" listing networks are themselves gatekept/curated, so any visible leaderboard already excludes failed/exposed pump-and-dump channels — biases any derived base rate upward (survivorship bias, social-side analog of our own alerts.jsonl bias from wave 13).
- **Assessment: thin.** No ready-made API for channel call-performance; would need custom scraping + backtest infra (similar effort to our existing on-chain backtest tooling) rather than a source callable directly.
- Sources: flexe.io/blog/crypto-quality-signals-telegram-4-proven-systems; telemetr.io/en/channels/1730427571-callanalyser; tgstat.com/channel/@CallAnalyser/stat; github.com/OkoyaUsman/telegram-group-crypto-call-analyzer; signals.coincodecap.com.

## WAVE 16 — Time-of-day / regime / market-beta normalization [done]

- **Hour-of-day study** (arXiv 2606.08232, "Hour-Aware Adaptive Risk Management for Autonomous Memecoin Trading", Jun 2026) extends our existing Pine-Analytics 14-23 UTC sniper-activity finding: worst hours by mean P&L are **UTC 2 (-16.6%, 40% win-rate), UTC 13 (-22.9%, 0% win-rate), UTC 23 (-15.5%, 62.5% win-rate)**; best are **UTC 14/16/17** (win-rates 42.9%/58.3%/47.4%, mean P&L +4.2%/+12.2%/+7.4% — maps to 10:00-13:00 US Eastern, the US session open). **Caveat from the paper itself**: Mann-Whitney U test on blacklisted-vs-other hours is NOT statistically significant at n=190 (α=0.05) — authors frame it as a candidate microstructure feature needing larger-sample replication, not a confirmed effect. Directly actionable as a "blacklist hour" adjustment but flag the weak-significance caveat.
- **Day-of-week anomaly**: peer-reviewed evidence exists generically for crypto (PMC10166693, ANN analysis of day-of-week anomaly in cryptocurrencies) — confirms DOW return anomalies are real/studied in crypto broadly, but NOT memecoin-specific; no dedicated memecoin DOW study found beyond the hour-of-day paper.
- **Market-regime feature**: no single canonical methodology paper, but industry-standard proxy = **BTC Dominance (BTC.D) + Altcoin Season Index** — BTC.D >~60% = risk-off (alts sold first, smaller/more leveraged/narrative-dependent), BTC.D <~55% = risk-on/altseason rotation. Maps cleanly to a simple regime feature: rolling BTC.D level/delta, or rolling BTC/SOL 24h return+volatility as a token-independent control variable.
- **DXY / stablecoin-mcap-change as leading filters**: NOT directly evidenced in a memecoin-specific context in sources found — speculative/unconfirmed, inferred by analogy to general crypto-macro commentary rather than a dedicated study. Reasonable hypothesis to backtest in-house, not an established finding.
- **Overall confidence**: hour-of-day = well-evidenced (published paper, concrete numbers, caveated significance); day-of-week + BTC-dominance-regime = well-evidenced generically for crypto but not memecoin-native; DXY/stablecoin angle = thin/speculative.
- Sources: arxiv.org/pdf/2606.08232; ncbi.nlm.nih.gov/pmc/articles/PMC10166693; tangem.com/en/blog/post/what-is-altseason; bitcoinfoundation.org/news/altcoins/understanding-altcoin-season-in-2026-what-are-altcoin-market-cycles; blog.bitpanda.com/en/bitcoin-vs-altcoins-which-market-phase-dominating-and-what-it-means-investors.

## WAVE 17 — VOLTA bundlemaps staggered-bundle thresholds (retry) [unreachable — exact number not recoverable]

- **Direct site fetch still fails** — `bundlemaps.volta.quest`/`volta.quest` now return HTTP 403 (was 522 previously). **archive.org is blocked at the environment's proxy gateway level** (confirmed via `$HTTPS_PROXY/__agentproxy/status` → `"connect_rejected"`/"gateway answered 403 to CONNECT" for archive.org:443) — a policy denial, not fixable client-side; Wayback is genuinely unreachable this session, not just this attempt.
- **What surfaced via search-index snippets** of the live page (title "VOLTA Bundle Scanner — The Only Solana Bundle Detector"): classifies bundles into **"same-block" (high risk)** vs **"staggered" (low risk)** buckets; example output `cluster_01: 7 wallets · same-block · risk: HIGH`, `cluster_02: 2 wallets · staggered · LOW`; aggregate "bundle score"/100 (example 72/100). Features: Bundle Detection, Sniper Identification, Wallet Clustering, Coordinated Buy Analysis. Gated behind holding 10,000,000+ VOLTA tokens.
- **Exact numeric stagger cutoff (the actual ask) NOT recoverable** — no indexed page/cached snippet/secondary source states a precise time-gap or dispersion-% threshold attributable to VOLTA specifically.
- **Correction to our own prior sourcing**: research-notes-raw.md's existing "bundle 20-25 wallets; stealth-launch 45-90s between buys; disperse across 50-200 fresh wallets each <1%" (wave 8) was attributed to a SET of sources including VOLTA alongside cicere/pumpfun-bundler, Rabnail-SOL, smithii, bananagun, 2 arXiv papers, Helius docs — i.e. that number was a synthesized/aggregate constant, NOT confirmed as VOLTA's own documented cutoff. This retry could not verify VOLTA as its origin.
- Adjacent non-VOLTA-attributed evidence: basic bundle checkers reportedly bypassed by scripts that "execute a massive buy and immediately distribute across 50 distinct sub-wallets over 3-4 blocks," scammer scripts commonly spin up "20 to 30 clean wallets" — directionally consistent with our existing 20-25/50-200 constants but not VOLTA-sourced.
- **Conclusion**: functionally unreachable for the exact threshold. Recommend keeping existing 45-90s/20-25 wallets/<1% dispersion constants labeled as "aggregate community consensus, not a single-source-verified VOLTA cutoff."
- Sources: bundlemaps.volta.quest (search-snippet only, direct fetch 403); volta.quest.

## WAVE 18 — Robinhood chainId verification (read-only repo check) [done]

- **Web verification: Arc and Robinhood Chain are genuinely different chains.** Robinhood Chain = **chainId 4663**, Arbitrum Orbit L2 settling to Ethereum via Nitro, public mainnet launched July 1, 2026 ("The World is Flat" keynote), carries 95 tradeable stock-token RWAs + a zero-fee dYdX-built stock-token DEX. Arc Mainnet = **chainId 5042**, RPC `5042.rpc.thirdweb.com`, explorer `arcscan.app` — a small separate chain (~225 tokens, ~$4k/24h volume per repo notes), own Railway-hosted backend (arcdexscan.com). No source links Arc to Robinhood Chain/Arbitrum Orbit — unrelated, much smaller/younger chain. Confirmed genuinely distinct: different chainId, RPC, purpose. Sources: blog.thirdweb.com/robinhood-launches-its-own-l2-blockchain-on-arbitrum-3; eco.com/support/en/articles/15859739; docs.robinhood.com/chain/cross-chain-messaging; bitget.com/news/detail/12560605498256.
- **Exact repo config (via Grep/Read, all confirmed, read-only — no files edited)**: `arc/scan.py:1,4,181` and `arc/README.md:1` — Arc Mainnet chainId 5042, RPC `5042.rpc.thirdweb.com`, explorer arcscan.app; scanner is **API-only, no RPC used** (`arc/README.md:78`). `vlad/rpc.py:12` — Robinhood Chain RPC = a QuickNode endpoint (`dry-lively-research.robinhood-mainnet.quiknode.pro/...`), comment line 1 confirms "Robinhood Chain / vlad.fun". `vlad/README.md:4,18-19` — states chainId **4663**, same QuickNode RPC, explorer `robinhoodchain.blockscout.com`. `pons/api.py:16-20` — `RPC = "https://rpc.mainnet.chain.robinhood.com"` (official endpoint, comment notes it's "from the pons bundle"), plus `FACTORY = "0xA5aAb3F0c6EeadF30Ef1D3Eb997108E976351feB"`, `WETH = "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73"`. Top-level `README.md:134-137` — "Both launchpads are on Robinhood Chain (chainId 4663). The public rpc.mainnet.chain.robinhood.com rejects urllib (403); the code uses a QuickNode endpoint pulled from the vlad.fun bundle." `README.md:73` — "arc/ — Arc DEX Scan (Arc Mainnet, chainId 5042)". `flap/scan.py` and `pons/alert_pro.py` reference the same vlad QuickNode RPC + Blockscout — consistent with pons/flap/vlad all genuinely on Robinhood Chain, distinct from Arc.
- **Mismatch/ambiguity assessment: NONE found.** Arc (5042) and Robinhood Chain (4663) are correctly kept separate across the repo — `arc/` never references Robinhood RPC/explorer/chainId, and `pons/`/`flap/`/`vlad/` never reference Arc's thirdweb RPC/arcscan.app. **One minor non-bug observation**: no code file stores chainId 4663 as an actual constant/assertion — it only appears in README/docstring comments; pons/flap/vlad identify the chain purely by RPC URL string + Blockscout domain, not by checking a numeric chainId, so nothing in code would catch a silent RPC-provider chain-drift if the QuickNode endpoint ever silently repointed to a different chain. Worth a future defensive check (e.g. `eth_chainId` assertion at startup) but not an active bug. **This closes the open verification item** tracked at research-and-build-plan.md:33-34 and research-notes-raw.md:194-196.

── RESEARCH STATUS: 18 waves done (PART 0 complete — all 3 primary angles + all 4 queued angles run).
Remaining open items (not full research gaps, just follow-ups noted above): VOLTA exact stagger threshold
unreachable (proxy blocks archive.org + site 403s); Clanker/honeypot.is/GoPlus full docs pages 403'd to
automated fetch (need human/browser check); Virtuals Base AgentFactoryV3/Unicorn exact contract address;
GoPlus/honeypot.is coverage of Robinhood Chain (4663) unconfirmed. NO decisions made — still source material.

## WAVE 19 — gap-closers via DIRECT PROBE (local, non-headless — closes wave 12/14 403s) [done 07-19]

Ran the API probes the cloud agent couldn't (its headless env got 403'd). Verified live:

- ✅ **GoPlus SUPPORTS Robinhood Chain 4663** (confirmed: /supported_chains lists 44 chains incl 4663 + 8453).
  token_security/4663 on a real flap token (0x4a38...7777) returned **code 1 OK, 39 fields**: buy_tax 0.02,
  sell_tax 0.01, is_honeypot 0, cannot_sell_all 0, is_blacklisted 0, is_open_source 1, is_mintable 0,
  owner 0x0 (renounced), creator 0x051a..c508, holder_count 2977, lp_holder_count 1, is_in_dex 1. **KEYLESS,
  free (~30/min).** → closes wave 12's biggest open item: full EVM honeypot/tax/blacklist detection is
  available FREE on BOTH our EVM launchpad chains (Robinhood 4663 + Base 8453).
- 💡 **BONUS (agent couldn't see this)**: GoPlus is an INDEPENDENT tax/honeypot source for flap → backstops
  flap's "tax ? (api unavailable)" problem when batman.taxed.fun is Cloudflare-rate-limited. Cross-check:
  GoPlus buy 2%/sell 1% matched flap's own batman tax on the same token. Add as a Part-1 item.
- ✅ **honeypot.is does NOT support 4663** ("Invalid chain") — ETH/BSC/Base only. So on Robinhood, GoPlus
  static analysis is the ONLY option (no live buy-sell sim). On Base we can use BOTH (the disagreement signal).
- ✅ **Clanker public API works from a normal client** (200): `GET https://www.clanker.world/api/tokens?limit=N`
  → `{data[], total, tokensDeployed}`. Per-token fields (READY firehose, no on-chain decode needed):
  contract_address, factory_address, locker_address, type (e.g. `clanker_v4`), pair (USDC/WETH),
  pool_address, starting_market_cap, warnings[], cast_hash (Farcaster link), requestor_fid, socialLinks,
  social_context, supply, tx_hash, chain_id, created_at/deployed_at, tags. Live token seen created 04:29 UTC
  (~minutes old) → high cadence. → closes wave 12 Clanker open item; Clanker scanner = poll this API, no
  factory-event listening needed for v1.
- ◐ **Virtuals AgentFactoryV3 address** — `factory` field is NULL in the api2.virtuals.io list response;
  not exposed via API. Would need a Basescan creation-tx trace of one agent token. MINOR (our virtuals
  scanner is API-based, doesn't need the on-chain factory). Left open.
- GoPlus Base 8453 also confirmed code 1 OK (works for Clanker/Zora token security too).

## CRITICAL REVIEW — tensions to reconcile + angles still missing (2026-07-19)

**Apparent CONTRADICTIONS across waves that the synthesis must resolve (not bugs — they resolve to one rule):**
1. Wave 9 "sniper/bundler = U-curve (some is GOOD)" vs Wave 8 "bundle = rug, defeat stagger" vs Wave 11
   "sniper-cohort presence = selection bias, NOT causal alpha". RESOLUTION: it's not the COUNT, it's WHO —
   funder-linked-to-dev bundlers = rug (bad); independent sophisticated bots = quality pre-filter (mild-neutral);
   and measured raw presence is confounded by organic interest. → the discriminator is the FUNDER-GRAPH
   (Part 2), which separates dev-coordinated from independent. All three waves point to the same build.
2. Wave 2/3 "capital-efficiency: fewer trades = GOOD" vs Wave 9 "fast-fill <30min = BAD". RESOLUTION: few
   LARGE buys from DIVERSE wallets = conviction (good); many fast buys from COORDINATED wallets = cabal (bad).
   Same discriminator: trade-size + wallet-diversity + funder-graph, not raw speed. → "fast" is only bullish
   when organic-share is high.
Both tensions collapse to the meta-finding + funder-graph. Worth stating explicitly in the final synthesis
so we don't build contradictory gates.

**ANGLES STILL NOT RESEARCHED (candidates for a future wave — genuine gaps, not covered by 1-19):**
- **Our OWN tracker as the training set** — no wave analyzed what alerts.jsonl+snapshots.jsonl outcomes
  actually correlate with FOR US (the most direct "what works for our alerts" study; wave 13 gave the METHOD
  but nobody ran it on our data). Highest-value un-run analysis; needs the shadow-control data first.
- **Cross-alert wallet-overlap** — do the same smart wallets recur across our recent CONFIRMED/EARLY alerts?
  A co-occurrence signal computable purely from data we already collect; nobody looked.
- **Real-time LP-pull alert (EVM)** — wave 12 gave the events (V2 Burn/Sync, V4 ModifyLiquidity negative
  delta) but no wave developed a live "liquidity being removed RIGHT NOW" exit/danger alert.
- **Exit / take-profit logic** — all 19 waves are ENTRY-side. Winner post-mortem noted "trailing -30% beat
  fixed +50% TP by 8.5x P&L" but no wave developed exit annotations (our alerts are detection-only, but an
  exit-signal overlay would add value; the agent/analyst.py AI-DD is the natural home).
- **Per-scanner DATA-AVAILABILITY matrix** — critical pre-build gap: which signals can pons/flap/virtuals/
  arc/pump ACTUALLY compute today? e.g. flap only collects transfer COUNTS (no per-swap value) → capital-
  efficiency/trade-size-variance/wash-price-impact are NOT computable on flap without new collection. This
  mapping must exist before committing to any Part-1/2 build.

## WAVE 20 — EMPIRICAL analysis of OUR OWN platforms (the wave that was missing) [done 07-19]

All prior 19 waves were EXTERNAL (papers/tools/other platforms). This one pulls REAL coins from our own
platforms + our tracker and finds PLATFORM-SPECIFIC patterns that generic thresholds get wrong. Samples are
small/cross-sectional (current-state not launch-time) → directional, validate as data grows. But several
findings directly contradict what we currently do.

**VIRTUALS (Base) — graduated (n=55) vs on-curve recent (n=100):**
- has socials: **96% grad vs 2% dead** = the strongest separator on virtuals.
- **top10%: 72.6% grad vs 100% dead** ⇒ ⚠️ graduated virtuals coins are NATURALLY concentrated (~72% top10).
  A generic "top10 < 30%" gate (GMGN default) would KILL virtuals winners. PLATFORM-SPECIFIC threshold needed.
- holderCount 7946 vs 1; isDevCommitted 13% vs 0%; isVerified 4% vs 0%; mindshare mostly null (not populated
  early → not usable as an early signal on virtuals).

**PUMP.FUN — graduated (n=66) vs young on-curve (n=70):**
- **has twitter: 76% grad vs 74% young = NO separation!** Twitter is table-stakes on pump.fun (everyone links
  one) ⇒ ⚠️ our pump `score_coin` gives +5 for twitter — that's scoring NOISE. Drop it.
- **has telegram 44% vs 3%, has website 76% vs 11% = STRONG separators.** On pump, weight TG + website, NOT
  twitter. (reply_count 1934 vs 0 but that's cumulative/age-confounded.)

**FLAP (Robinhood) — our tracker, EARLY winners(>2x, n=12) vs losers(<+20%, n=5):**
- ⚠️⚠️ **our score does NOT separate them: winner median score 59.5 vs loser 60.0.** The hand-weighted flap
  score is not predictive at the win/lose cut. (This is exactly why wave-13 WOE-calibration matters.)
- What ACTUALLY separates (the score ignores this):
  · **recipients: winners 107 vs losers 82** — broader holder distribution = winner.
  · **transfers: winners 362 vs losers 427** — losers have MORE transfers.
  · **churn (transfers/recipient): winners 3.44 vs losers 3.78** — losers churn more per wallet (bot/wash-like).
  · **entry mcap0: winners $10.2k vs losers $12.7k**, liq0 $5.9k vs $7.0k — winners entered CHEAPER.
- ⚠️ **flap score currently REWARDS transfer count** (`min(transfers/100, 8)`) — but transfers correlate with
  LOSING. We reward the wrong variable. Fix: reward RECIPIENT count + PENALISE high transfers-per-recipient
  (churn); this is the organic-share meta-finding confirmed on our own data. Highest-ROI recalibration found.

**PONS (Robinhood) — committed data:** graduations.json stores only {token, graduatedAt, block} — NO launch-
time features → can't do a rich winner-fingerprint from committed data; would need to pull each graduated
token's early on-chain state (a real analysis to run). smart_wallets: a few wallets have 41/39/26 graduations
(the highest-signal wallets — weight these heaviest). 90 deployers with ≥1 grad; max 3.

**ACTIONABLE (platform-specific, from OUR data — override generic thresholds):**
1. flap: reward recipients + penalise churn (transfers/recip); STOP rewarding raw transfers. [highest ROI]
2. pump: drop twitter from score (noise); weight TG + website. [free, immediate]
3. virtuals: do NOT apply a low-top10% gate (winners sit ~72%); use socials-presence as the primary filter.
4. weight the 41/39/26-graduation smart wallets far above one-hit wallets in the pons smart list.
5. RUN the wave-13 backtest on our own tracker + a shadow-control pull — this empirical cut proves the score
   needs refitting, not tweaking. This is the un-run analysis of highest value.
Caveat: cross-sectional grad-vs-dead is age-confounded for count metrics (holders/replies/transfers); the
socials-presence + churn-ratio + entry-mcap findings are the launch-time-valid ones. Re-run on matured
tracker data (24-48h+) for the flap winner/loser cut as n grows beyond 12/5.
