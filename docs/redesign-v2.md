# Redesign v2 — from hand-tuned rules to an EV engine

*2026-07-18. Triggered by a day of whack-a-mole patches (farm gate, bundle
gate, name gate…) and the user's verdict: "ตอนนี้มันไม่ฉลาดเลย". The tracker
now has enough outcomes to judge the system by its real job. It did.*

## The goal (restated — everything is measured against this)

> **Make money for one human trader**: surface the few launches with a real
> shot at multiplying, early enough to enter, few enough to act on, with the
> evidence shown, and with exit guidance. Every component earns its place by
> **EV per $100 per alert (peak-aware)** and **P(peak ≥ 2x)** measured by the
> outcome tracker — never by proxy targets.

Non-goals that crept in and must die: predicting *graduation* (pons CONFIRMED
optimizes this — graduation ≠ buyer returns), covering every launchpad for
coverage's sake, alert volume, hand-satisfying score aesthetics.

## What the tracker says (2026-07-18, deduped, winsorized 50x, matured ≥8h)

| slice | n | med 4h | hit@4h | med PEAK | P(2x) | EV/$100@4h |
|---|---|---|---|---|---|---|
| **flap / FLAP EARLY** | 12 | **+263%** | 67% | **+517%** | **67%** | **+$1,485** |
| flap / FLAP NEAR-GRAD | 4 | +90% | 50% | +119% | 80% | +$84 |
| pons / MARKETING (off) | 103 | -34% | 17% | +9% | 27% | +$114 |
| pons / NEAR-GRAD (off) | 99 | -84% | 10% | +10% | 24% | -$31 |
| pons / CONFIRMED | 2 | -78% | 0% | +32% | 0% | -$78 |
| arc / ARC LAUNCHED | 4 | +0% | 0% | +0% | 0% | $0 |

Calibration: corr(score, peak) = **-0.12** on FLAP EARLY (n=12), +0.32 on the
already-disabled NEAR-GRAD. The hand-tuned scores do not rank outcomes.
Concentration: top-5 coins carry 42% of all peak-return mass — power-law, so
optimize EV and tail capture, not medians. Peak vs 4h gap (flap +517% vs
+263%) says **exits are half the game** and we provide none.

Caveats: n=12 on the golden slice is small (8/12 ≥2x is binomially strong vs
any sane base rate, but the EV estimate is noisy); flap socials/features were
not recorded before today (GMGN enrichment), so per-feature lift needs more
data. That is what the evidence engine is for.

## Diagnosis — why the old logic can't get smart

1. **Wrong targets.** Each scanner predicts a platform proxy (graduation %,
   progress, KOTH). The trade target is forward price. CONFIRMED is the proof:
   scores 84/91, both -78%.
2. **Guessed weights, never fitted.** Additive scores with judgment-call
   constants; tracker existed but nothing consumed it mechanically.
3. **One-shot alerts.** No lifecycle: no take-profit milestone, no death
   notice — in a distribution where the median winner gives back half its
   peak by 4h.
4. **Whack-a-mole gates.** Farm/bundle/name gates are symptoms: sensors and
   judgment live in the same file, so every new fraud pattern needs a patch.

## The new shape — sensors → one brain → lifecycle

```
sensors  pons/flap/pump/virtuals/bags/arc — detect + featureize candidates.
         NO scoring, no judgment. One standard candidate schema
         (traction, holders, gmgn forensics, socials, dev history, age…).
brain    decider consuming model.json — per-slice fitted evidence
         (weight-of-evidence bins → P(2x), EV). Alerts only above an EV bar.
         Alert text shows fitted numbers: "P(2x) 41% · EV +$310 (n=63)".
fit      tracker/fit.py — weekly walk-forward refit from outcomes.jsonl →
         model.json. No weight ships without measured lift (the rule we
         applied ad hoc becomes the pipeline).
coach    follows open alerts via tracker snapshots: "🎯 2x reached — initial
         out?", "💀 -50% — dead" appended to the alert bubble (edit-in-place).
AI       memecoin-dd second opinion + weekly skill self-review (already
         evidence-gated; unchanged).
tracker  unchanged — it is the ground truth everything answers to.
```

## Roadmap (each phase ships value alone)

- **P1 — evidence engine (now).** `tracker/analyze.py`: the clean analysis as
  a standing CLI (slices/EV/calibration/feature-lift, winsorized, deduped) +
  `--write-stats` → `tracker/data/tier_stats.json`. Every alert then carries
  its tier's live track record (truth in advertising, auto-updating).
- **P2 — exploit the proven vein.** flap EARLY: recall/latency experiments
  (bar 80 recips → data-driven), replicate its mechanic (first-minute distinct-
  recipient burst) on bags/pump. Quarantine CONFIRMED as-is: it keeps firing
  + collecting, but its alert shows the tier record and loses the "น่าเข้า"
  implication until a refit target (forward return, not graduation) exists.
- **P3 — brain + fit.** WoE model per slice, walk-forward validated; scores
  become P(2x) with n= behind them. Sensors stop owning scores.
- **P4 — coach.** Exit milestones on open alerts (biggest free EV per the
  peak-vs-4h gap).
- **P5 — AI deepening.** Verdicts join the feature set; skill self-review
  keeps pruning its own blind spots.

## Decision log

- 2026-07-18: NEAR-GRAD + MARKETING stay off (confirmed by clean numbers).
- 2026-07-18: CONFIRMED demoted to quarantine pending target change.
- 2026-07-18: hand-tuned scores declared decorative; P(2x)/EV become the
  numbers a human sees once P3 lands.
