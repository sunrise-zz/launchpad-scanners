# Signal research — improving winrate & early-detection (2026-07-19)

Multi-source research (Sorsa/TweetScout, GitHub scanners, 4 arXiv papers, GMGN
skills taxonomy, practitioner data studies) into signals that predict a memecoin
pumping/graduating vs rugging. Goal: signals NOT already in our stack, ranked by
evidence × implementability.

## The one meta-finding that reframes everything

**Raw activity is what bots manufacture.** Velocity, volume, holder count,
transfer count — the signals we alert on — are exactly what bundlers, bump-bots
and volume-bots fake. Every serious source converts a raw metric into its
**organic-share** form, and that transformation is where the winrate lives:

| raw (we use) | organic version (the edge) |
|---|---|
| progress velocity (per second) | **capital efficiency** = SOL/ETH raised **per trade** |
| volume | **human-origin volume** (frontend vs direct-contract) |
| holder / top10% | **entity-clustered** concentration (merge bundled wallets) |
| buy count | **wash-adjusted** buys (net-balance-change ≈ 0 → drop) |
| sniper count | deployer-**funded** snipers (near-certain dump) |
| "has socials" | **Telegram-weighted** + smart-follower graph |

## Evidence tiers: [A] papers · [B] large-N data study · [C] anecdote/PR

## Ranked signals to add

### #1 Capital efficiency — SOL/ETH raised per trade  [A, top-ranked twice]
arXiv 2602.14860 (655k tokens): *"fast accumulation through a SMALL number of
trades is the strongest predictor of graduation, dominating every other variable."*
A Random-Forest study ranked `volume/tx` #1 of 12 features; `whale_score` ranked
LAST. Real conviction arrives in size; bots churn many micro-buys that never fill
the curve. **Orthogonal to our velocity** (progress-per-second) — this is
progress-per-trade. Compute: `net_weth / n_buys`, `mean(swap_size)`.
→ **pons has buy_weth/n_buys already.** flap/pump need per-trade value.

### #2 Deployer→early-buyer funding-link  [B strong / A]
Pine Analytics: 15k launches where deployers pre-funded their own snipers — **87%
of those snipes profitable, 90% exited in 1-2 swaps.** Our sniper *count* can't
tell neutral bots from deployer-coordinated ones; the funding edge is the
discriminator. Compute: for first/same-block buyers, walk SOL/ETH funding back N
hops; flag if it meets the deployer or a shared funder. (Helius `funded-by` on
Solana; trace transfers on EVM.)

### #3 Entity-clustered concentration delta  [A]
MemeTrans (arXiv 2602.13480): top-10 of high-risk tokens hold **+17pp** more; after
clustering wallets into entities, measured concentration rises **+24% (high-risk)
vs +6% (low-risk)** — insiders split supply to defeat per-address top10%. The
*delta* between naive and clustered concentration is itself the deception signal.
Cluster by: same-tx multi-buy, shared Jito bundle, common funder ≤k hops. A single
bundle >10% supply = red flag. Using the risk score cut simulated losses **56%.**

### #4 Dev initial-buy size (skin-in-the-game)  [A]
Survival analysis (832k launches, Cox concordance 0.858): initial mcap above the
platform default → **hazard ratio 4.51** for graduation. Production: dev funding
**>10 SOL → 30.3% graduation vs 2.6% for <1 SOL.** NOTE the tension with dev%
concentration: moderate dev buy is GOOD, extreme dev% is BAD — model separately,
not one monotone feature.

### #5 Telegram-weighted socials (not binary "has socials")  [A]
Same survival paper: **Telegram → 1.485% grad vs 0.166% (8.9x)**; TG+X+web →
1.919% vs 0.110% (**17.4x**). We already fetch x/tg/web — just weight TG highest
and score the full triple as its own tier. **One-line upgrade.**

### #6 Bot-share of the whole flow  [A+B]
arXiv 2602.14860: only tokens with **>70% non-bot share** approached breakeven.
Production: **<3% pro-traders → 32% moon vs 2.6% bot-dominated (12.5x).** Classify
buyers by inter-trade timing regularity, cross-token rate, wallet age, fee pattern.

### #7 Trade-size variance / volume std  [B corroborating A]
#2 RF feature. Humans buy heterogeneous sizes; bots buy uniform. Near-zero
coefficient-of-variation across many buys = manufactured. Compute `std(swap_size)`.

### #8 GMGN organic-quality fields we fetch but under-score  [B]
`gmgn.py snapshot()` already returns bundler_rate, rat_rate (insider),
sniper70_rate (sniper hold), bluechip_owner%, holders. **pump already GATES on
holders** (bundle gate ✓) — but should also fold bundler/rat/sniper-hold into the
SCORE, and reward bluechip_owner% (holders who also hold bluechips = organic).
Market-signal type 10 (bundler sells = de-risk) and type 12 (smart buys).

### #9 Zero-bundler paradox — insider % has a sweet spot  [B]
Zero bundlers → HIGHEST dump rate (28%) — no skin in the game. Insider **10-30%
optimal** (18.7% moon/9% dump) vs <3% or >30%. Change concentration scoring from
monotone-penalty to **band-based**.

### #10 Recycled/renamed X-account detection  [B — Sorsa]
Serial deployers recycle aged X accounts and rename to the new ticker. Sorsa
`/about` returns `username_change_count` + `last_username_change_at`. Old
`created_at` + rename <7d before launch = bought shell. Social twin of our
serial-deployer wallet detection. Also: smart-follower count/velocity on the
token's X (curated KOL list ∩ followers), and **bot-follower ratio** replacing
binary socials. Caveat: Sorsa Score is gameable (boost services exist) — use as a
weighted feature, never a gate.

### #11 Dump-event detector (4σ control limit)  [A]
92% of tokens with ≥30 swaps had ≥1 dump event, clustering pre-graduation (selling
before migration yields more). A late-curve token *without* a dump = strong
outlier. Compute rolling z-score of log-returns per swap, flag |z|>4 down-moves.

### #12 Aged- vs fresh-wallet ratio among first buyers  [B/C]
Aged/active wallets among first-30s buyers = "strongest early predictor"
(practitioner). Farms use fresh star-topology wallets. Score = fraction of first-N
buyers with age >7d & >50 txs.

### #13 Wash-trade share (net-balance ≈ 0)  [A]
MemeTrans top feature group; MELT found **21% of pre-migration txs were wash**
(buy+sell in one tx). Per cluster: `1 - |net_balance_change|/gross_volume`.

### #14 Creator funding-network (upgrade serial-deployer)  [A+B]
SolRugDetector mapped 78 syndicates (star topology, 1 funder → ≤169 wallets).
Serial behavior lives at the **funding-network** level, not the wallet — a fresh
deployer funded by a wallet that funded prior ruggers inherits their record.
Serial deployers = 18% of creators but drained **82% of liquidity.** COUNTERPOINT
[A]: prolific-creator identity added NO graduation lift — it's a rug FILTER, not a
winner-picker.

### #15 Post-migration liquidity & holder band (2nd-stage scanner)  [B]
$100k+ LP → **84% moon / 0.25% dump**; <$1k → 59% dump. Holders 1k-5k → 66% moon;
>5k decays. Launch platform is itself a feature (Meteora DBC 92% dump vs pump.fun
10% in one study). Useful for a post-graduation re-entry scanner.

## Cross-cutting caveats
- **Base rates drift hard**: pump.fun graduation fell 0.63% → 0.2% in ~8 months.
  Any fixed threshold decays — normalize against a rolling platform baseline.
- **Selection vs causation**: socials & dev-buy predict graduation but also predict
  slow-rugs post-grad — pair with sell-side death monitors.
- **The best production thresholds** (Memecoin Encyclopedia, Medium) are single-source
  with self-defined moon/dump labels — validate on OUR tracker before trusting numbers.
- **Our own labels**: adopt MELT's rule — high-risk if price <30% of migration within
  20 min. Graduation alone is a weak win-label (84% of graduates were still high-risk).

## Highest-ROI given our stack (what to build first)
1. **Capital efficiency + trade-size variance** — top-ranked, computable from pons's
   existing swap stream. (flap/pump need per-trade value first.)
2. **Telegram-weighted socials** — one-line, 9-17x measured lift, data already fetched.
3. **Fold GMGN organic fields into pump's score** (bundler/rat/sniper-hold/bluechip) —
   already fetched for the gate, near-zero cost to score.
4. **Entity-clustered concentration** (#3) + **funding-link tracing** (#2) — highest
   winrate lift but need a funder-graph; a bigger build.
5. **Recycled-handle detection** (#10) — cheap Sorsa API call, strong rug filter.

## Key sources
- arXiv 2602.14860 (pump.fun graduation, 655k) · 2602.13480 (MemeTrans/MELT, 41k) ·
  2607.02823 (survival, 832k) · 2603.24625 (SolRugDetector, 76k rugs) · 2601.08641
  (bot detection formulas) · 2504.07132 (SolRPDS dataset)
- Pine Analytics "Exit Liquidity Machines"; Memecoin Trading Encyclopedia (Medium);
  Trench Radar bundle docs; GMGN skills (github.com/GMGNAI/gmgn-skills); GODMODE
  (funding-graph); Sorsa/TweetScout API (docs.sorsa.io)
