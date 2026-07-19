# Shadow-control sampling

The design of the control group, written for whoever runs the Tier B refit
(#10). Implementation: `pons/controls.py` (policy), `pons/outcomes.py`
(`record_control`), `tracker/track.py` (`load_tracked`), `tracker/report.py`
(`base_rate_controls`, `lift_at`).

## Why it exists

Before this, the tracker only ever measured coins we alerted on. That makes
every number it produced uninterpretable rather than merely incomplete:

- "flap EARLY returned +53% at 4h" — against what? In a week when every
  memecoin ran, a filter that picked at random would also have shown +53%.
- "pons NEAR-GRAD returned -27%" reads as a broken filter, but the whole
  market bled -10% to -35% over the same window (see
  `launchpad-scanners` findings, 2026-07-18). A -27% against a -35% base rate
  is a *positive* edge.
- We could not tell whether the bars were too tight, because the coins just
  under each bar were never measured at all. That is the flap 80-120
  recipients question, unanswerable by construction.

The control group makes the denominator observable. Everything downstream —
the refit, threshold tuning, the go/no-go on a new tier — is bounded by this
bias until controls have accumulated.

## The design

| Parameter | Value | Why |
|---|---|---|
| Population | every launch the scanner observed and did not alert on | The question is whether an alert beats a **random** launch from the same window. A traction floor would answer a different, easier question and stop being a base rate. |
| Bucket | 1 hour, per launchpad | Cases and controls drawn from the same hour and the same chain conditions, so a market-wide move lifts both and cancels out of the comparison. |
| K | 2 per bucket per launchpad | ≈48/day/launchpad, ≈240/day across five scanners against ≈600 alerts/day. Chosen against **tracker cost** — each control costs the same ~10 horizon fetches over 48h as an alert — not against statistical power. |
| Rule | one slot, one uniform draw | The bucket is cut into K equal slots. At the first opportunity after a slot opens, one launch is drawn **uniformly at random from the scanner's currently-eligible pool** (`ControlSampler.choose`). |
| Measurement | identical to alerts | Same `record_*` path, same GMGN enrichment, same horizons, same `f` feature dict. |

### Why slots rather than first-K

Launches cluster — a listing, a trend, one deployer spamming. "The first K
launches of the hour" would spend the whole quota inside a burst, and a burst
is exactly when launches least resemble the hour they came from. Slots bound
the rate and spread the draws across the bucket.

The draw *within* a slot is uniform over the eligible pool rather than
"whatever arrived first", because arrival order is not neutral: the pool is
iterated in insertion order, so first-offered would systematically return the
oldest coin under watch every single time.

### Why not Bernoulli sampling at rate p

The textbook answer, and it needs p calibrated to the launch rate to yield K.
Our launch rates span three orders of magnitude (flap ~5000/day, arc a
handful) and swing within each day. That calibration is a second estimator to
build, tune and get wrong. Systematic sampling buys the same "spread across
the frame" property with none of it.

## Where each scanner samples

Each scanner samples from **the pool a real alert is decided from**, not from
the raw launch event, so a control enters the tracker at a comparable point in
a coin's life and its return series covers the window the bar is judged over.

| Scanner | Pool | Seam |
|---|---|---|
| flap | tokens under watch, not yet alerted, within `--watch-secs` | `sample_control` in `check_candidates` |
| pump | feed coins that fell through both tier gates this poll | `sample_control` after the feed loop |
| virtuals | on-curve tracked agents not yet EARLY | `sample_control` in `check_candidates` |
| pons | active coins, not confirmed and not NEAR-GRAD-alerted | `sample_control` in `update_swaps` |
| arc | **none** | not sampled — see below |
| bags | **none** (but its TRENCH BURST rows are controls) | `record_control` at the burst seam |

**arc and bags deliberately do not sample controls.** #9 names only pons, flap,
pump and virtuals, and both of the others are low-volume enough that an hourly
quota would take months to reach a usable n (arc's chain saw ~$4K/24h volume
when probed; between them they account for ~40 of ~1500 alert rows). They can
be added later by constructing a `ControlSampler` and calling `choose()` — the
work is a handful of lines per scanner now that the policy is one module.

Until then, `report.py`'s EDGE table shows `–` for them, meaning *no controls
collected*, not *no edge*. bags does write TRENCH BURST rows into
`controls.jsonl`, but those are a targeted experiment, not a base rate, so
`base_rate_controls()` excludes them and the EDGE row stays empty.

Sampling at the mint event instead would baseline every control at age 0
against alerts that fire minutes in; sampling at expiry would baseline them
all at the end of the watch window, after the move an alert would have caught.
Both are uniform, and both are misaligned with the alerts they are compared
against.

## Matching, and what is NOT controlled for

Matching is currently on **launchpad × hour** only. That is deliberate for v1
and is the level the comparison in `report.py` computes at.

Known residual confounders, in rough order of how much they should worry you:

1. **Age at sampling.** A control is sampled at a uniformly random moment in
   its watch window; an alert fires when it crosses a bar, which is a
   different (and generally earlier) distribution. Both rows carry `age_s` in
   `f`, so the refit can match or regress on it — it is measured, not
   controlled. This is the largest known gap.
2. **Later-alerting controls.** A sampled coin can still cross the bar
   afterwards and alert, putting one token in both populations. Roughly ~1% of
   flap launches ever alert, so contamination is small; it is detectable by
   joining `token` across `alerts.jsonl` and `controls.jsonl` and should be
   excluded for any analysis where 1% matters.
3. **Length bias — the one to actually worry about.** The draw is uniform over
   the pool *at that instant*, not over all launches in the hour. A coin that
   stays eligible across more slot-openings therefore has a higher chance of
   being sampled. How much that bites depends on the scanner:

   - **flap, pons, virtuals** — every launch sits in the pool for a fixed
     watch window regardless of how it is doing, so eligibility duration is
     near-constant and the bias is small.
   - **pump — materially biased.** Its pool is the *actively-traded* feed, so
     a coin is eligible only while it keeps trading. Surviving longer both
     raises the sampling probability and predicts the outcome, which is
     length bias in its harmful form: pump's controls skew toward coins that
     kept trading and its base rate reads better than the true one. Treat
     pump's edge as a **lower bound**, and prefer flap/pons for any
     cross-platform base-rate claim until this is corrected.

   The fix is inverse-propensity weighting — weight each control by the
   inverse of its eligibility exposure. The research notes rate IPW a v2
   refinement rather than a wave-1 requirement, and it belongs in
   `ControlSampler.choose`, which is the single place the policy lives.
4. **One coin, sampled once.** `choose()` never returns a coin it already
   sampled (`SEEN_MAX` most recent, per process). Two rows for one coin would
   double its weight in a base rate built from ~48 rows a day. Note this
   memory is per-process and not persisted, so a restart can re-sample a coin
   still inside its watch window — rare, and one duplicate.

## Reading the data

`tracker/data/controls.jsonl`, same row shape as `alerts.jsonl` plus
`"shadow": true` and an explicit `"id"`.

Snapshots for both populations land in the shared `snapshots.jsonl`. **Join on
the row's `id` field, falling back to `"<t>:<token>"` when it is absent** — that
is exactly what `tracker/report.py:alert_id()` does, so reuse it rather than
rebuilding the key:

- Alerts, and the legacy rows migrated out of `alerts.jsonl`, carry no `id` and
  join on the derived `"<t>:<token>"`.
- Controls written since #9 carry `"id": "<t>:<token>:c"`. The `:c` suffix
  exists because a scanner can sample a coin as a control and alert the same
  coin within the same wall-clock second, and the derived key truncates to
  whole seconds — the two would collide and share one snapshot series.

Joining naively on `"<t>:<token>"` therefore silently drops every control
written since #9 while still matching the migrated ones, which makes the
failure partial and easy to miss.

```
python3 tracker/report.py --min-age-h 8      # EDGE vs CONTROL section at the end
```

**Two populations live in `controls.jsonl` and must not be pooled:**

- `tier == "CONTROL"` — the uniform sample described here. This is the base
  rate. `report.py:base_rate_controls()` selects exactly these.
- `tier` in `FLAP SHADOW-60` / `FLAP SHADOW-XFER` — flap's older bar-research
  experiment, which samples only coins that already cleared 60 recipients.
  A deliberately *selected* population, kept for the separate question of
  whether the EARLY bar should come down (`docs/redesign-v2.md`). Pooling
  these into the base rate would drag it toward the traction end and
  understate our edge.

## History

Controls used to be written into `alerts.jsonl` — flap's SHADOW tiers and
bags' TRENCH BURST — ~450 rows, 30% of the file — distinguished only by a tier
string nobody filtered on. `tracker/migrate_controls.py` moved them out. While
they were in there they inflated `report.py`'s alert count and every
per-platform median by pooling the alerted and non-alerted populations, and —
because `outcomes.recent_same_symbol()` counts prior rows of a symbol and flap
suppresses a name at 2 repeats — 66 flap symbols were being blocked from
alerting by rows that were never sent to anyone.

That is the reason controls live in their own file rather than behind a flag:
the readers that must not see them cannot see them, instead of each having to
remember to filter.
