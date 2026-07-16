# vlad.fun coin scanner — ต้นน้ำ (source-level) detection

Goal: catch interesting new coins on **vlad.fun** (a memecoin launchpad on
**Robinhood Chain**, chainId 4663) as early as possible, straight from the
on-chain source — before/independent of the website's backend.

> **Scope guard:** everything here only **detects and ranks** coins. It never
> places a trade. Buying/selling is yours to do manually.

## What we reverse-engineered

The launchpad is a single upgradeable "pump" contract:

| thing | value |
|---|---|
| pump proxy | `0x6ea53e65b4a577dbbaccbfa84e9050e837c5cb0c` |
| implementation | `0x48bf40532c6c11176f7c4172fbb8de68e433da16` |
| RPC | `https://dry-lively-research.robinhood-mainnet.quiknode.pro/5a684d.../` |
| explorer | `https://robinhoodchain.blockscout.com` |
| backend REST | `https://api-production-de9d.up.railway.app` (undocumented) |

Contract is unverified, so events were recovered from raw logs (openchain +
keccak brute-force):

```
Launched (token, creator, string name, string symbol, string metadataJSON)   # a coin is born ← ต้นน้ำ
Bought   (token, buyer,  uint ethIn,   uint tokensOut, uint fee)
Sold     (token, seller, uint tokensIn, uint ethOut,   uint fee)   # NOTE: field order differs from Bought
Graduated(token, ...,    uint, uint, uint)   # bonding curve completed → migrated to DEX = the big win
FeesHarvested / OperatorSet                  # admin, ignored
```

The truest source is subscribing to `Launched` logs on the pump contract — you
see a coin the instant it deploys, ahead of the website's poller.

## Findings (backtest on the full history: 286 coins, 17 "winners" >$10k ATH, 3 graduated)

1. **Early buy momentum is the signal.** Distinct non-dev buyers + buy volume in
   the first 30–120s rank winners strongly. Best pure-recall single feature:
   `buy_eth` within 300s → recall@20 = 0.82, Spearman vs ATH = +0.92.
2. **There is real lead time (mostly).** By 30–60s only ~13–27% of a winner's
   net-ETH move has happened; ~65–71% of winners are still <50% done. Winners'
   peak comes a median ~173s after launch. So a scanner firing at ~30–60s
   typically has ~10–30s before the local top. Caveat: ~25% of winners peak
   within 1s (dev snipe/rug) and are uncatchable — filter those out.
3. **Cold-start / reputation does NOT work yet.** Predicting from creator history,
   dev buy size, or socials/metadata barely beats base rate (recall@20 ≈ 0.41,
   grad recall 0) — the platform is ~1 day old so creators have no track record.
   Revisit once history accumulates.
4. **Buy/sell ratio threshold barely matters**; distinct-buyer count and volume
   carry the signal. Concentration (one wallet = whole buy) and dev dumping are
   the useful *negative* filters.

## Shipped logic (`deploy_momentum`, window 120s)

```
score = 1.0·z(non_dev_buyers) + 1.0·z(buy_eth) + 0.7·z(buysell_ratio)
        − 0.7·z(top_share) − 1.0·dev_sold
```
recall@20 = 0.65, precision@20 = 0.55, grad recall = 0.67, Spearman +0.74 —
chosen over raw `buy_eth@300s` because it uses *organic* (non-dev) demand,
penalises wash/dev-dump patterns, and fires earlier (more lead time).

Fast binary alert (from the trigger sweep): **≥5 distinct non-dev buyers within
60s, buy/sell ratio ≥1.5, dev hasn't sold** → `WATCH`; ≥8 buyers → `STRONG`.
Hard drop: dev sold in window, or one wallet is >90% of buy volume.

## Files

| file | purpose |
|---|---|
| `rpc.py` | JSON-RPC + event decoders (the reverse-engineered ABI lives here) |
| `collect.py` | pull full on-chain history + REST outcomes → `data/` |
| `analyze.py` | feature engineering + stats helpers |
| `run_backtest.py` | compare candidate logics, write `data/best_logic.json` |
| `lead_time.py` | prove the signal fires before the peak; tune the trigger rule |
| `scan.py` | **live scanner** — poll Launched/Bought/Sold, rank, alert |

## Run

```bash
python3 analysis/vlad/collect.py       # refresh data (snapshot; re-run anytime)
python3 analysis/vlad/run_backtest.py  # re-fit logic → best_logic.json
python3 analysis/vlad/lead_time.py     # lead-time + trigger diagnostics
python3 analysis/vlad/scan.py          # live watchlist (Ctrl-C to stop)
python3 analysis/vlad/scan.py --once   # single poll (smoke test)
```

## Caveats

- Data is a snapshot of a launchpad that is <2 days old; label counts are tiny
  (3 graduations) so treat exact numbers as directional, not precise. Re-run
  `collect.py` + `run_backtest.py` as more coins accumulate to re-fit.
- `buy_eth`↔ATH correlation is partly mechanical (ATH is driven by buy volume);
  the lead-time analysis is what shows the signal is still *actionable*, not just
  descriptive.
- The Railway backend is undocumented and may change or disappear. On-chain logs
  are the durable source of truth; REST is a convenience layer for USD stats.
