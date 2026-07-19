# HANDOFF — read this first (next session starts here)

Single entry point after a large research session (2026-07-19). Research is DONE
(24 waves). This file is the synthesis + prioritized build backlog. Detailed
sources live in the other docs; this is what to act on.

## Read order
1. **This file** — state, principles, prioritized backlog.
2. `docs/research-and-build-plan.md` — the phased pipeline (PART 0-6 + 5b + updates).
3. `docs/research-notes-raw.md` — 24 research waves (external 1-19, OUR-platform empirical 20-24).
4. `docs/signal-research-2026-07.md` — the first synthesized signal doc.

---

## CURRENT SYSTEM STATE (deployed, running on this Mac mini)
- 6 LaunchAgents live (auto-restart): `com.sunrise.{pons,flap,virtuals,arc,pump}-scanner` + `com.sunrise.tracker`.
- Repo: github.com/sunrise-zz/launchpad-scanners (all research pushed, working tree clean).
- Alerts → Telegram (creds in pons/.env). Outcome loop: every alert → tracker/data/alerts.jsonl;
  tracker samples price 5m…48h → snapshots.jsonl; `python3 tracker/report.py --min-age-h 8` reports.
- Shared alert format: `pons/alertfmt.py` (score/100 + meter + Thai verdict + platform/chain tag + pros/cons).
- GMGN client `pons/gmgn.py`; AI-DD agent `agent/analyst.py` (verdict BUY-WATCH/NEUTRAL/AVOID, advisory only).

### GUARDRAILS (live-data decisions — do NOT regress)
- pons NEAR-GRAD tier = OFF (net-negative -27%→-34%@8h). MARKETING feed = OFF (-39%@8h).
- pump bar $35k + quality gate; flap bar 80 recips. Everything is a SCORED feature, not a hard gate
  (brand-new pairs are noisy; winner ≈ 1-in-20k → FP tolerance is brutal).

### KNOWN OPEN OPERATIONAL ISSUE
- **pons.family is NXDOMAIN — the pons scanner is fully dark.** Re-checked 2026-07-19 ~13:00: both
  `pons.family` and `www.pons.family` return NXDOMAIN (not SERVFAIL/timeout — the domain does not resolve
  at all), curl → 000. This has now persisted >12h, so treat it as *the platform is gone//renamed*, not a
  transient outage. The scanner starts fine but every poll errors ("recent-buys/latest failed, nodename nor
  servname"); it just logs+retries silently, so it looks alive in `launchctl` while emitting nothing.
  → Decide: (a) add a health-check that alerts when a feed is dead N minutes, and (b) if pons is really gone,
  either retire the scanner or rebuild its feed on RPC — wave 21 already reconstructed full launch-time
  factors from QuickNode RPC + Blockscout alone, so an API-free pons path is proven feasible.
  Robinhood chain RPC (QuickNode) + Blockscout were UP.

---

## THE 3 ORGANIZING PRINCIPLES (from all 24 waves)
1. **Raw activity is what bots fake.** Velocity/volume/holders/transfers = manufactured. Winrate lives in the
   ORGANIC-SHARE transform (capital-eff, human-origin volume, cluster-concentration, wash-adjusted, top1_share).
2. **Two winner archetypes** need two score models: organic cold-fermentation (price leads social — on-chain
   detects early) vs narrative-catalyst (social leads price — needs mindshare). Don't blend into one score.
3. **Several current checks are already DEFEATED by evasion** (same-slot bundle→stagger; concentration→<1%
   dispersion; serial-deployer→hop funding). Master counter = recursive multi-hop **funder-graph clustering**
   (re-arms concentration + sniper + serial-deployer at once). Biggest single winrate build.
   NOTE two tensions that resolve to this: sniper/bundler count is not-count-but-WHO (funder-linked=bad);
   "fast fill" is only bullish when organic-share is high. Don't build contradictory gates.

---

## PRIORITIZED BUILD BACKLOG

### TIER A — ✅ SHIPPED 2026-07-19 (items 1-5; item 6 killed by measurement).
Each is proven on our own coins, not a paper. Ordered by ROI/effort.
**Status: 1-5 implemented, compiled, dry-run smoke-tested, live. 6 = do not build (see below).**
Measured effect on synthetic profiles built from the wave-21/24 medians (winner vs died-control):
pons 82→81 winner / 44→24 died-FP (gap 38→57); virtuals 95 vs 29; pump 98 (TG+web+X) vs 83 (none).
⚠️ These weights are DIRECTIONAL, fitted by hand on tiny n (pons control n=9, flap 12w/5l). They are the
best available prior, NOT a calibrated model — Tier B #8 (WOE refit on tracker data) still supersedes them.
To make that refit possible, pons now logs its raw launch-time factors (`f={rebuyers,net_weth,top_share,
cap_eff,...}`) into every tracker alert record. **Do the same for flap/pump/virtuals before the refit** —
right now only pons emits raw features, so only pons is refittable.

1. **pons: wire `top_share` penalty into `score_confirmed`** [🔥 highest ROI, ~zero effort]
   - Data: winner top1_share median 5.6% vs died 62.8% (11x, the cleanest pons separator).
   - `CoinState.top_share` (= max(buyers.values())/buy_weth) ALREADY EXISTS, computed, never scored.
   - Change: penalise when top_share > ~0.15-0.20 (one wallet dominates early buys = whale/not-organic).
   - File: `pons/alert_pro.py` → `score_confirmed()`.

2. **pons: fix cap_eff tiers (delete the dead ≥0.1 tier)** [high]
   - Data: 0/22 winners reach cap_eff 0.1; winner band 0.02-0.04 (median 0.031), died 0.005.
   - Change: `score_confirmed` currently +8 @≥0.1 (never fires) / +4 @≥0.03. Set threshold ~0.02, kill 0.1.
   - Also log-scale the rebuyers/net "beyond-bar" bonus (winners hit 300+ rebuyers / 60Ξ; current cap = 12).

3. **flap: reward recipients + penalise churn; STOP rewarding raw transfers** [high]
   - Data (our tracker, winners>2x vs losers): recipients 107 vs 82; churn (transfers/recip) 3.44 vs 3.78;
     entry mcap $10.2k vs $12.7k. Our score `+min(transfers/100,8)` rewards transfers — which correlate with
     LOSING. Score doesn't separate win/lose (59.5 vs 60.0).
   - Change: `flap/scan.py` score — reward recipient count, penalise transfers/recipient, favor lower entry mcap.

4. **pump: weight TG + website, drop/minimise twitter** [free]
   - Data (grad vs died): twitter 77% vs 60% (noise/table-stakes); TG 44% vs 13%; website 74% vs 37%.
   - Change: `pump/scan.py` `score_coin` gives +5 twitter → replace with TG + website weighting.

5. **virtuals: socials near-gate; don't gate top10; ignore antiSniperTax** [free]
   - Data (69 grad vs 346 died): socials 96% vs 2% (strongest separator anywhere); isDevCommitted 12% vs 0%;
     top10 winners ~72% (a low-top10 gate would kill winners); antiSniperTax 13%/98% = TEMPORAL CONFOUND (skip).
   - Change: `virtuals/scan.py` `score_agent`/gates — weight socials much higher; reward isDevCommitted/verified.

6. ~~**flap tax backstop via GoPlus**~~ — ❌ **KILLED 2026-07-19, do not build.**
   - Wave 19 confirmed the *endpoint* answers on chain 4663 (and 4663 is in `/supported_chains`), but that is
     endpoint availability, NOT token coverage. Measured against our own tracker: **16/16 Robinhood tokens
     returned `code:1 / "OK"` with an EMPTY `result` object** — oldest and newest alike, paced to avoid the
     4029 rate-limit. GoPlus simply has no rows for flap/pons launchpad tokens.
   - Reconciling with wave 19's one positive probe (39 fields on one flap token): that token had
     holder_count 2977 — a large, already-graduated coin. GoPlus indexes tokens once they are big/old,
     which is exactly useless at alert time (our coins are minutes old when we need the check). Not a
     contradiction — a coverage profile that excludes our use case.
   - Lesson (generalise this): "API supports chain X" ≠ "API has data for OUR tokens on chain X". Any future
     data-source claim must be validated against real addresses from `tracker/data/alerts.jsonl` before it
     earns a backlog slot. The Tier B data-availability matrix should record COVERAGE %, not just reachability.
   - The flap tax gate therefore keeps its current 2 sources (batman.taxed.fun → GMGN) and its −10 penalty
     when neither answers. If a third source is still wanted, evaluate honeypot.is (Base-only today) or an
     RPC-level `eth_call` simulated buy/sell, which needs no third-party coverage at all.

### TIER B — prerequisite infra (do before trusting any weight changes)
7. **Per-scanner data-availability matrix** — CRITICAL. Map each signal → can each scanner compute it today?
   Known gap: **flap collects only transfer COUNTS, no per-swap value** → capital-eff / trade-size-variance /
   wash-price-impact NOT computable on flap without new collection. Produce this before building signals.
8. **Backtest on our tracker + shadow-control sampling** (wave 13 method): our flap score is proven non-
   predictive → refit, don't tweak. Needs shadow-control (sample non-alerted launches, same launchpad/window)
   to fix survivorship bias. Then WOE-scorecard/GBM per wave 13. This validates everything in Tier A/C.

### TIER C — bigger builds (highest winrate lever, more infra)
9. **Funder-graph clustering** (master counter, Part 2) — EVM via Blockscout/Basescan multi-hop, Solana via
   Helius funded-by + MELT's 3 heuristics (co-tx, funder, Jito bundle_id). Powers entity-clustered
   concentration delta + deployer→sniper funding-link. See waves 7,8,10,12.
10. **Jito bundle ground-truth + tip-fingerprinting** (pump, Part 3) — getTipAccounts + same-slot contiguity.
11. **Social layer** (Part 4) — recycled-handle (Sorsa), smart-follower velocity, Farcaster/Zora (Neynar,
    least-crowded edge), attention (Kaito free API). For the narrative archetype.
12. **Launchpad expansion** (Part 5) — Clanker (Base, API firehose READY: www.clanker.world/api/tokens),
    Raydium LaunchLab + Meteora DBC (Solana substrate = many launchpads), GeckoTerminal/DexScreener free
    new-pool firehose. Independent of the above; more ต้นน้ำ = more shots.

### TIER D — from the cloud research agent's Part 0 (waves 12-18), verified/gap-closed in wave 19
- EVM honeypot/tax free on GoPlus (4663 + 8453); honeypot.is Base-only (no 4663). Uniswap V4 event model
  (Clanker v4/Zora/Flaunch use V4 Initialize/ModifyLiquidity, NOT V2 Mint/Burn). Clanker/Zora factory addrs
  in wave 12. ML methodology (WOE scorecard, purged walk-forward, PSI drift) in wave 13. Alpha-wallet sources
  (kolscan now pump.fun-owned, GMGN /v1/user/smartmoney, SolanaTracker free 2500/mo) in wave 14. Hour-of-day
  blacklist (weak significance) wave 16. Defensive chainId assertion (hygiene) wave 18.

---

## HOW TO PICK UP (next session)
- Fastest visible win: **Tier A #1 (pons top_share)** — one function, real-data-backed, ~zero risk.
- Correct order: do **Tier B #7 (data matrix)** first so you only build signals a scanner can feed, then
  batch Tier A, stand up **#8 (backtest+shadow)** so changes are measured not guessed, then Tier C.
- Every scanner change: compile-check, `--dry-run` smoke test, `launchctl kickstart -k`, verify banner/log,
  commit + push. Don't touch a tier's guardrails without data.
- After ~24-48h more tracker data: rerun `tracker/report.py --min-age-h 24` for the first mature read.
