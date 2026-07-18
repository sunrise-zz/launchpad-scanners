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

── RESEARCH STATUS: 11 waves done. Angles still queued for later loop iterations: EVM-specific detection
(Base/Robinhood honeypot-sim, LP events, Clanker/Zora on-chain), ML feature-combination/model architecture,
backtesting methodology (labeling + walk-forward + look-ahead avoidance), public KOL/alpha-wallet datasets
(kolscan), Telegram alpha-caller track records, time-of-day/regime/market-beta context. NO decisions yet.
