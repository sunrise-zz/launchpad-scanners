# Cross-alert smart-wallet overlap — July 2026

## Question

Do the same smart wallets recur across recent `CONFIRMED` and `* EARLY`
alerts often enough to justify a live recurrence signal?

## Data audited

Read-only snapshot at 2026-07-20 05:33 UTC:

- `tracker/data/alerts.jsonl`: 1,208 alerts from 2026-07-17 18:50 UTC through
  2026-07-20 05:32 UTC.
- Analysis cohort: 502 alerts / 502 distinct tokens — 2 `CONFIRMED`, 446
  `FLAP EARLY`, 23 `PUMP EARLY`, and 31 `TRENCH EARLY`.
- 418/502 cohort rows (83.3%) have a GMGN snapshot with a numeric `smart`
  count. Of those, 31 rows (7.4%; 6.2% of the full cohort) report at least one
  smart wallet, totalling 45 wallet-token observations.
- 158 cohort rows have a raw feature dictionary. None has `smart_hits` or
  another wallet-identity field.
- `pons/data/smart_wallets.json` contains 1,267 strong and 4,933 weak wallet
  identities, but it is a global reputation registry. Alert rows do not record
  which of those wallets bought which alerted token.

## Result

The retained data cannot answer the overlap question. GMGN snapshots deliberately
store scalar counts such as `smart`, `renowned`, and `sniper_w`; they do not
store the corresponding wallet addresses. The 45 observed wallet-token
memberships could therefore represent one recurring wallet, 45 distinct
wallets, or anything between. The pons registry cannot repair the missing join
because it contains wallet reputation without per-alert membership.

Fetching today's holders for old alerts would not be a valid backfill. It would
measure wallets that still hold after the outcome is partly known, not wallets
present at alert time. That creates survivor and look-ahead bias, and changing
GMGN tags would add another source of drift.

## Recommendation

**Do not build a live wallet-recurrence signal from the current history.**
There is no measured recurrence rate yet, so any score or gate would be a guess.

The useful next build is collection, not scoring:

1. At alert time, persist the tagged wallet identities returned by the holder
   source, along with source and observation timestamp.
2. Collect the same identities for shadow controls; alert-only collection
   cannot show whether recurrence beats the launchpad base rate.
3. Keep the raw identity set separate from scalar GMGN features so future
   analysis can reproduce wallet-token edges without changing existing score
   inputs.
4. Re-run this analysis after the identity-bearing alerts and controls have
   matured. Compare recurrence frequency and forward returns out of time before
   promoting it to a displayed signal.

This is a **no-build recommendation for the signal**, and a **build
recommendation for unbiased alert-time identity collection**. No live gate or
score changes follow from this audit.
