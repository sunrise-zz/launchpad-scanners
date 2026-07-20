# Data-availability matrix

Measured 2026-07-19 to 2026-07-21 for issue #8. This is the gate for proposing
new scoring signals: a schema, reachable endpoint, or documented field does not
count as available until it is populated for launches at the age when a scanner
would use it.

## Legend and scope

- **P** — already persisted at alert/control time and usable retrospectively.
- **C** — computable by the scanner today, but the required raw value is not
  persisted yet.
- **S** — a currently used source populated the value in the live sample, but
  the scanner does not persist it yet.
- **N** — needs new collection or a new join before it can be used.
- **I** — structurally specific to a different platform; do not build it here.

The six columns name scanner implementations, not the `platform` value recorded
by every source. In particular, Bags can emit rows whose underlying venue is
Virtuals, Bankr, Noxa, or Clanker.

## Matrix

| Candidate signal | pons | flap | pump | virtuals | arc | bags |
|---|---:|---:|---:|---:|---:|---:|
| Per-swap values for Kyle lambda / wash impact and trade-size variance or entropy | C | **N** | N | N | N | N |
| Trades-to-graduation plus breakeven gate | N | N | N | N | N | N |
| Sniper/bundler U-curve position | N | N | N | N | I | N |
| Telegram liveness, not merely link presence | N | N | N | N | N | N |
| Funder recency and aged/fresh first-buyer ratio | N | N | N | N | N | N |
| First 100 buyers still holding and transfer-before-buy | N | N | N | N | N | N |
| GMGN `rug_ratio` | N | N | N | N | I | S |
| GMGN `is_wash_trading` | N | N | N | N | I | S |
| GMGN `dev.creator_token_status` | S | S | S | S | I | S |
| GMGN `sniper_count` | N | N | N | N | I | S |
| GMGN signal feed types 12 and 10 | N | N | N | N | I | N |
| GMGN `visiting_count` | P | P | P | P | I | P |
| Drawdown from ATH | N | N | N | N | I | N |
| Hour of day | P | P | P | P | P | P |
| Market regime: BTC dominance | N | N | N | N | N | N |
| `initialBuyAmount` and `restrictionsEndBlock` | P | I | I | I | I | I |

### What the compact cells mean

- **Per-swap values:** pons already reads value-bearing swap logs and can derive
  the measures during the watch window, but does not retain the individual
  trades. Flap reads only transfer and recipient **counts**. It has no per-swap
  values, so capital efficiency, trade-size variance/entropy, and wash-price
  impact require a new swap collector. Pump, Virtuals, Arc, and Bags currently
  consume aggregate/list snapshots rather than a value-bearing swap stream.
- **Graduation and U-curves:** the current rows are point-in-time snapshots.
  These signals need a durable launch-to-graduation series and an outcome join;
  a current trade count or current bundler percentage is not the proposed
  curve-position signal.
- **Wallet-history rows:** no scanner retains the ordered first-buyer cohort,
  each buyer's pre-launch funding time, or the later balance needed to know
  whether that buyer still holds. Existing concentration aggregates cannot
  reconstruct those facts.
- **Telegram:** presence of a `t.me` URL is not liveness. No scanner currently
  joins Telegram API status, last-message time, membership, or deletion state.
- **Hour of day:** every alert/control row has Unix timestamp `t`, so this is
  available without another provider or schema change.
- **BTC dominance:** the current value cannot be joined retrospectively without
  leaking future information. Store a timestamped regime observation at alert
  time before evaluating this signal.
- **Pons launch fields:** on-chain `TokenLaunched` discovery already persists
  `initial_buy_wei` and `restrictions_end_block` in pons raw features. The event
  and fields do not exist on the other five launchpads.

## Measured coverage

### Retained alert/control-time features

Counts below treat `null`/missing as absent and genuine zero as present.

| Population | Real tracker rows | Relevant measured coverage |
|---|---:|---|
| pons controls | 50 | `initial_buy_wei` 50/50; `restrictions_end_block` 50/50; core swap-derived aggregates 50/50 |
| flap EARLY alerts | 288 | recipients/transfers/churn/tax 288/288; Batman enrichment 14-15/288; no per-swap value field 0/288 |
| flap NEAR-GRAD alerts | 18 | enrichment 18/18; no recipients/transfers or per-swap values 0/18 |
| pump controls | 50 | core point-in-time fields 50/50; velocity 20/50; no individual trades 0/50 |
| virtuals.io controls | 46 | feed fields 46/46; holder/top-10/dev fields 20/46; mindshare 0/46; no individual trades 0/46 |
| Arc alerts | 13 | alert timestamp 13/13; no raw feature dictionary or individual trades 0/13 |
| Bags-backed tracker rows | at least 10 | alert timestamp present; detailed external-field probe below |

Virtuals coverage is age-dependent. A separate live BASE-feed sample measured
10 young on-curve and 10 established agents: `mindshare` was 0/10 versus 4/10,
`holderCount` and `top10HolderPercentage` were 3/10 versus 10/10, while
`devHoldingPercentage` and `volume24h` were 10/10 in both cohorts. Therefore a
field present in the list schema must not be treated as usable for EARLY.

### External-source qualification probes

The probes used real addresses selected from tracker history, queried at the
age represented by the scanner population. They record populated values, not
HTTP success. Raw responses and credentials were not committed.

| Source and population | n / realistic age | Populated result |
|---|---|---|
| GMGN token-info/security, latest flap alerts | 10, approximately 0.1-31 minutes old | token info 10/10; security 10/10; `visiting_count` 10/10; nested `dev.creator_token_status` 10/10; top-level `rug_ratio`, `is_wash_trading`, `sniper_count`, and ATH history 0/10 |
| GMGN token-info/security, latest pump alert/control rows | 10, approximately 7-277 minutes after tracker capture | token info 10/10; security 10/10; `visiting_count` 10/10; nested `dev.creator_token_status` 10/10; the same rug/wash/sniper/ATH fields 0/10 |
| GMGN signal feed, same pump sample | 10, approximately 7-277 minutes after capture | usable token signal response 0/10; requested feed types 12/10 populated 0/10 |
| Bags Trenches source, real Bags-backed tracker addresses | 10, alert-age launches | rug, wash, creator status, sniper count, and visits populated 10/10 |
| Virtuals first-party BASE list feed | 10 young on-curve plus 10 established | coverage split reported above; the provider has not computed several fields for the young cohort |

No external provider is marked usable for Telegram liveness, funder history,
buyer retention, or historical BTC dominance: no candidate source has yet
produced the required observation for a qualifying 10-address/timestamp sample.
Those cells remain **N**, rather than promoting reachability into availability.
The same rule excludes GoPlus for Robinhood-chain launch-time use: its response
was successful but the result was empty for 16/16 real pons/flap tracker tokens.

## Evidence and implementation anchors

- Alert/control feature values and timestamps: `tracker/data/alerts.jsonl` and
  `tracker/data/controls.jsonl` (live runtime files; intentionally not committed).
- Pons value-bearing swaps and launch-event fields:
  [`pons/alert_pro.py`](../pons/alert_pro.py).
- Flap transfer-count collection: [`flap/scan.py`](../flap/scan.py).
- Pump, Virtuals, Arc, and Bags snapshot ingestion:
  [`pump/scan.py`](../pump/scan.py),
  [`virtuals/scan.py`](../virtuals/scan.py),
  [`arc/scan.py`](../arc/scan.py), and
  [`bags/scan.py`](../bags/scan.py).
- GMGN normalization, including `visiting_count` as `visits`:
  [`pons/gmgn.py`](../pons/gmgn.py).
- The Virtuals age-split measurements and the candidate-row handoff are recorded
  in GitHub issue #8; the GoPlus 0/16 qualification failure is recorded in
  [`HANDOFF.md`](HANDOFF.md).

## Decision rule for future signal work

Before promoting any **N** cell, collect at least 10 real tracker launches per
relevant tier at realistic token age, report non-null coverage and field
semantics, and persist the observation at alert/control time. Re-measure after
collector changes; never substitute a current snapshot for a historical
launch-time feature.
