# launchpad-scanners

Source-level (ต้นน้ำ) coin scanners for two **Robinhood Chain** memecoin
launchpads — **vlad.fun** and **pons.family**. Each reverse-engineers the
platform's data (on-chain events and/or public API), backtests what actually
predicts a coin pumping / graduating, and ships a live scanner that surfaces the
promising launches early. Optional Telegram alerts.

> **Detection only.** These tools rank and alert. They never place a trade —
> that's yours to do manually. Winrates below are historical and not a promise;
> most memecoin launches fail. Manage your own risk.

## Platforms

### `pons/` — pons.family (fixed-supply, graduates at 4.2 ETH)
Rich public API gives graduation progress directly. Best signal is **multi-factor
confirmation** from on-chain early trading. Backtested on 94 graduations vs 1,500
controls:

```
CONFIRMED rule (first 5 min):  rebuyers ≥ 6  &  net ETH ≥ 1.0  &  snipers ≤ 3
```
Real-world precision ~30% (41% out-of-time), ~55× the 0.54% base rate, fires
~44s after launch (graduation ~90 min later). See `pons/README.md`.

- `alert_pro.py` — **the live scanner** (multi-factor 🎯 CONFIRMED + 🔥 NEAR-GRAD → Telegram)
- `backtest_multifactor.py`, `collect_onchain.py` — how the rule was found
- `scan.py` / `alert.py` — earlier velocity-only versions

### `vlad/` — vlad.fun (bonding curve)
Unverified pump contract; events recovered from raw logs. Signal is **early buy
momentum** (distinct non-dev buyers + buy volume in the first 30–120s).

- `scan.py` — live on-chain scanner
- `run_backtest.py`, `lead_time.py` — logic search + lead-time proof

## Quick start

```bash
# pons
python3 pons/collect.py            # snapshot + reputation table
python3 pons/alert_pro.py --dry-run   # multi-factor scanner, print alerts

# vlad
python3 vlad/collect.py
python3 vlad/run_backtest.py
python3 vlad/scan.py --once
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

## Data

Small derived artifacts (best_logic, smart_wallets, graduations, reputation) are
committed. Large raw datasets (full launch lists, event/swap dumps) are gitignored
— regenerate them with each folder's `collect*.py`.

## Notes

- Both launchpads are on Robinhood Chain (chainId 4663). The public
  `rpc.mainnet.chain.robinhood.com` rejects `urllib` (403); the code uses a
  QuickNode endpoint pulled from the vlad.fun bundle. Swap in your own RPC if it
  rotates.
- Undocumented, fast-moving platforms — endpoints and contracts may change. Re-run
  the collect/backtest steps as data accumulates to refit thresholds.
