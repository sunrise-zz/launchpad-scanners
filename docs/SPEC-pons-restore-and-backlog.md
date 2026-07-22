# SPEC — Restore pons discovery on-chain, then close the research backlog

Status: ready-for-agent · Written 2026-07-19 · Supersedes the "HOW TO PICK UP" section of `docs/HANDOFF.md`

> **Update 2026-07-23 — the domain moved, it did not die.** `pons.family` still does not
> resolve, but the launchpad is serving from **`www.ponsfamily.com`** (root 308 →
> `/launchpad`, 200). Three of the four `EP_*` routes answer there with live data —
> `/api/pons-launches/latest`, `/api/pons-launches/recent-buys` and
> `/api/pons-launches/graduations`; only `/api/noxa-market` is retired (410). This does
> not change the plan below — a launchpad that silently changes hostname is the same
> class of dependency risk as one that goes NXDOMAIN, so RPC still wins the default. It
> does mean story 9's comparison can be run for real instead of hypothetically. See #1.

## Problem Statement

The pons scanner has been silently dead for over 12 hours, and it is the scanner we
understand best.

`pons.family` — the launchpad's website and API — went NXDOMAIN. Not a timeout, not a
502: the domain does not resolve at all. The pons scanner discovers new coins by polling
that API, so with the API gone it discovers nothing, scores nothing, and alerts nothing.

Three things make this worse than a normal outage:

1. **It looks healthy.** `launchctl` reports `state = running`, the process is up, the
   startup banner prints normally. The only symptom is a repeating line in a log file
   nobody watches. Every other scanner shares this failure mode — any feed can die and
   the operator will not be told.
2. **The platform is not dead — only the website is.** The pons launchpad factory
   contract is on-chain and actively launching coins right now: ~148 launches/hour,
   most recent one 22 seconds before this spec was written. We are blind to a live
   firehose because we depend on a dead middleman.
3. **Our best scoring work is idle behind it.** The Tier A recalibration (top1_share
   whale-domination penalty, cap_eff retiering, log-scaled conviction) shipped today and
   is measurably the sharpest discriminator we have — winner-vs-died separation widened
   from 38 to 57 points. It sits at the end of a pipe with nothing flowing through it.

Separately, two quieter failures ride along with the same dead API: the ETH/USD price
lookup falls back to a **hardcoded $1900**, so every USD figure in every pons alert is
silently computed at a stale price; and the offline collector that refreshes the
smart-wallet list can no longer run, so that list slowly decays toward irrelevance.

## Solution

Stop asking a website what launched, and read it from the chain instead.

A single `eth_getLogs` call against the pons factory contract, filtered to its
`TokenLaunched` event, returns every field the scanner needs — token, deployer, pool,
pair token, plus two fields the old API never gave us (the deployer's initial buy size
and the anti-sniper restriction window). This is the same RPC mechanism the scanner
already uses to pull swap logs, so it introduces no new dependency, no new credential,
and no new failure mode. It is strictly more reliable than what it replaces: it fails
only if the chain RPC fails, which would take the scanner down anyway.

The swap-collection, factor-computation and scoring stages are untouched. They already
run on RPC. Only the discovery stage changes.

Once pons is seeing coins again, the work returns to the research backlog: make every
scanner's failures loud, make every scanner log its raw features so the hand-tuned
weights can be replaced by a fitted model, and then build the larger signals.

## User Stories

**Restoring pons discovery**

1. As a trader, I want the pons scanner to find new launches without pons.family, so that a third party taking their website down does not take my alerts down.
2. As a trader, I want pons alerts to resume within minutes of this shipping, so that I stop missing ~148 launches per hour on the platform we have studied most.
3. As a trader, I want the restored scanner to apply the Tier A scoring already shipped, so that the whale-domination penalty and recalibrated capital-efficiency tiers finally affect real alerts.
4. As a trader, I want discovery to catch launches that happened while the scanner was restarting, so that a deploy or a crash does not create a silent gap in coverage.
5. As a trader, I want the scanner to skip launches older than the watch window on a cold start, so that restarting does not flood me with alerts for coins that already played out.
6. As an operator, I want the scanner to resume from the last block it processed, so that recovery after a crash is automatic rather than manual.
7. As an operator, I want the block cursor persisted to disk, so that a restart does not re-scan from genesis or skip forward past unprocessed blocks.
8. As an operator, I want a bounded block range per poll, so that a long outage does not produce one enormous RPC request that times out and wedges the scanner.
9. As an operator, I want the legacy HTTP discovery kept behind a switch, so that now the launchpad's API is reachable again (at `www.ponsfamily.com` since 2026-07-23) we can compare both sources rather than having thrown the old path away.
10. As an operator, I want the RPC path to be the default, so that the dead dependency is not on the critical path by accident.
11. As a developer, I want the launch records from RPC to have the same shape as the old API records, so that nothing downstream of discovery needs to change or be re-verified.
12. As a developer, I want the token/pair ordering derived from the pair token in the event, so that buy-vs-sell classification stays correct rather than relying on an assumption.

**Making silent failure impossible**

13. As a trader, I want to be told when a scanner stops seeing data, so that I learn about an outage from an alert rather than from noticing the silence days later.
14. As an operator, I want each scanner to track when it last successfully ingested something, so that "running" and "working" can be distinguished.
15. As an operator, I want a dead feed to notify me once rather than every poll, so that a long outage does not turn into hundreds of messages.
16. As an operator, I want to be told when a dead feed recovers, so that I know whether to re-check the coins I missed.
17. As an operator, I want the staleness threshold to be per-scanner, so that a slow launchpad is not constantly reported as broken.
18. As a trader, I want pons USD figures to use a live ETH price, so that market caps and liquidity in alerts are not silently computed at a stale hardcoded rate.
19. As an operator, I want the ETH price source to fall back across providers before it falls back to a constant, so that a hardcoded number is a last resort rather than the normal state.
20. As an operator, I want it to be visible in the alert when a fallback price was used, so that I can discount the USD figures rather than trusting them.

**Replacing guessed weights with fitted ones**

21. As an analyst, I want every scanner to log its raw launch-time measurements with each alert, so that the scores can later be refitted from data instead of adjusted by hand.
22. As an analyst, I want the logged features to be the measurements rather than the score, so that changing the scoring formula does not invalidate the history I have collected.
23. As an analyst, I want flap, pump and virtuals to log features the way pons now does, so that the refit is not limited to one of our four platforms.
24. As an analyst, I want a written map of which signals each scanner can actually compute today, so that I stop designing signals for scanners that cannot feed them.
25. As an analyst, I want that map to record measured coverage rather than whether an endpoint responds, so that we do not repeat the GoPlus mistake of mistaking availability for data.
26. As an analyst, I want to sample launches we did *not* alert on, so that the backtest has a control group and does not simply confirm survivorship bias.
27. As an analyst, I want the scoring model refitted on that data once enough has accumulated, so that the current hand-tuned weights are replaced by calibrated ones.
28. As an analyst, I want the refit validated on time-ordered holdout data, so that the model is not scored on coins it was fitted on.
29. As an analyst, I want the fitted model compared against the current heuristic, so that we ship it only if it actually beats what we have.
30. As a trader, I want scoring changes to be measured rather than asserted, so that I can trust that a change improved things.

**Bigger signals, once the foundation holds**

31. As a trader, I want wallets clustered by who funded them, so that bundling and concentration cannot be hidden by splitting across fresh addresses.
32. As a trader, I want concentration recomputed per funding cluster rather than per address, so that the existing concentration check stops being trivially evadable.
33. As a trader, I want to know when a deployer funded the wallets that sniped their own launch, so that insider setups are visible regardless of how many hops they used.
34. As a trader, I want telegram presence weighted above twitter across every platform, so that scoring reflects the one social signal that separated winners on all of them.
35. As a trader, I want more launchpads covered, so that more shots reach the funnel rather than depending on any single platform staying alive.
36. As a trader, I want the launchpad-expansion work to reuse the on-chain discovery pattern from pons, so that new platforms do not each introduce a new API that can die.

## Implementation Decisions

**Seam: the existing `latest()` function in the pons API module.** Confirmed with the
developer. Its internals are replaced; its name, call signature and return shape stay
exactly as they are. It is module-level, has a single call site, and everything
downstream consumes its output as a list of dictionaries — so this is the highest
available seam and it requires no changes to the scanner's main loop. Rejected
alternatives: a new `fetch_launches()` abstraction (adds a seam and forces call-site
changes for no benefit), and a shared cross-scanner launch-source abstraction (correct
eventually, but couples this fix to a refactor of three working scanners).

**Discovery reads one event.** The pons factory emits `TokenLaunched` on every launch,
and it alone carries everything the scanner's coin state needs. Verified by decoding a
real launch transaction:

```
TokenLaunched(
  token         address indexed   -> the launched token
  deployer      address indexed   -> creator, feeds the serial-deployer check
  dexFactory    address indexed
  pairToken     address           -> quote token; matches the WETH constant already
                                     in the code, and determines token0/token1 ordering
  pool          address           -> the Uniswap V3 pool to pull swap logs from
  dexId         uint256
  launchConfigId uint256
  positionId    uint256
  restrictionsEndBlock uint256    -> anti-sniper window (new, not in the old API)
  initialBuyAmount uint256        -> deployer's block-0 buy size (new)
)
```

A second event, `TokenDeployed`, fires in the same transaction but omits the pool, so it
is not used. The pool's own `PoolCreated` event is likewise unnecessary — the pool
address is already in `TokenLaunched`. One filtered log query per poll is sufficient.

**Record shape is preserved, not extended in place.** The normalized record keeps the
old API's keys so downstream code is untouched. `initialBuyAmount` and
`restrictionsEndBlock` are carried as additional keys; nothing consumes them yet, but
they are logged as features so they can earn scoring weight later from outcome data
rather than from a guess.

**Launch timestamp comes from the block, not the event.** The event carries no
timestamp. Block timestamps are fetched for the blocks in a batch and cached, since many
launches share a block at 148/hour.

**The cursor is a persisted block number.** Discovery polls from the last processed
block to current head, with the range capped per poll so that a long outage drains over
several polls instead of one oversized query. On a cold start with no cursor, discovery
begins at head minus the watch window rather than at genesis, so a fresh install does
not replay history.

**The legacy HTTP path stays, switched off.** A source selector keeps the old
pons.family implementation reachable for comparison. RPC is the default. A path we do
not control must not be on the critical path — which the 2026-07-23 discovery reinforces
rather than weakens: the API came back at a *different hostname*, so pointing the switch
at it means editing `BASE` (`pons/api.py:35`), not merely flipping `DISCOVERY_SOURCE`.

**Health-checking is a shared concern, not a pons one.** Each scanner records the time
of its last successful ingest. A watchdog alerts once when that exceeds a per-scanner
threshold, and once more on recovery — edge-triggered, not level-triggered, so an outage
produces two messages rather than a flood. Thresholds differ per scanner because launch
rates differ by orders of magnitude.

**ETH/USD gets a real source.** The current lookup calls the dead API and silently falls
back to a hardcoded 1900. It moves to a provider chain — DexScreener and GMGN are both
already used elsewhere in this scanner — with the constant remaining only as a final
resort, and its use surfaced in the alert so stale USD figures are visibly stale.

**Feature logging is the prerequisite for the refit, not part of it.** pons now writes
its raw launch-time measurements into each tracker record. flap, pump and virtuals must
do the same before a cross-platform refit is possible. Until then only pons is
refittable. Features are logged as measurements, never as derived scores, so that
changing a formula does not invalidate accumulated history.

**The data-availability matrix records coverage, not reachability.** This is a direct
consequence of killing the GoPlus backstop today: that API supports the Robinhood chain
and answers `code:1 / "OK"`, but returned an empty result for 16 of 16 of our own
tokens. Any data source must be validated against real addresses from our own alert
history before it earns backlog space.

**Known gap that constrains scope:** flap collects transfer counts but no per-swap
values, so capital-efficiency, trade-size variance and wash-price-impact are not
computable on flap without new collection. The matrix must state this rather than let a
future session design flap signals that cannot be fed.

**Sequencing.** Pons discovery first — it unblocks the scanner and the scoring work
already shipped behind it. Health-checking second, since it is small and prevents the
next silent outage on any scanner. Feature logging and the availability matrix third,
because the refit depends on both. The refit follows once data has accumulated. The
larger signals — funder-graph clustering, Jito bundle ground truth, the social layer,
launchpad expansion — come after, in the order set out in the handoff document, with
funder-graph clustering first among them since it re-arms three checks at once.

## Testing Decisions

**What makes a good test here.** These are scoring heuristics and log parsers, so the
tests assert external behavior: given this launch event, this record comes out; given a
coin with a winner's measured profile and one with a died coin's, the winner scores
materially higher. Tests must not assert specific score values — the weights are
explicitly provisional and will be replaced by a fitted model, so pinning exact numbers
would make every future recalibration fail a test for no reason. Assert the separation
and the direction, not the magnitude.

**Introducing pytest, scoped to pure functions.** Confirmed with the developer. The
repository has no tests today; the convention has been an inline smoke script plus a
`--dry-run` start. Adding a full replay harness was considered and deferred as too much
scaffolding before the work it would protect exists.

Modules under test:

- **Launch-event parsing** — a captured real launch transaction as a fixture, asserting the parsed record carries the right token, pool, deployer and pair token, and that token ordering is derived correctly. This runs offline against the fixture; no network.
- **The three scoring functions** (pons confirmed, pump coin, virtuals agent) — fed synthetic profiles built from the medians measured in research waves 21 and 24, asserting winners outscore died-control coins by a wide margin, that whale-dominated buy distributions are penalized, and that the capital-efficiency tier which was dead code cannot silently return.
- **Cursor advancement** — that a bounded range is requested, that the cursor persists, and that a cold start does not replay history.

**Prior art.** The closest existing analogue is the offline backtest module in the pons
directory, which reconstructs launch-time factors from chain data and evaluates rules
against outcomes. The fixture-based approach here follows the same instinct: real
captured data, evaluated offline, no live dependency. The smoke checks run while
shipping Tier A today — scoring synthetic winner and died profiles and comparing the
gap — become the first scoring tests rather than being rewritten.

**Not tested:** live RPC calls, Telegram delivery, and the LaunchAgent lifecycle. These
stay covered by the existing `--dry-run` smoke check and a post-deploy log inspection.

## Out of Scope

- **Rebuilding pons.family's other endpoints.** Only launch discovery is restored. The offline collector that refreshes the smart-wallet list also depends on the dead API; its list decays slowly rather than failing outright, so it is tracked separately.
- **Reviving the NEAR-GRAD tier or the marketing feed.** Both were measured net-negative and switched off deliberately. This spec does not reopen that; the guardrails hold.
- **Changing any alert threshold or gate.** Discovery is restored and scores are refined, but which coins qualify is unchanged. Scores remain display-and-logging only, never gates.
- **The GoPlus tax backstop.** Killed by measurement, not deferred. Documented in the handoff.
- **Refitting weights in this spec.** Feature logging and control sampling are in scope; the fit itself waits for accumulated data.
- **Retiring the pons scanner.** Considered while the platform appeared dead. The on-chain evidence settled it — the platform is alive and busy.

## Further Notes

The measurement that reframed this work: the pons factory contract had launched a token
22 seconds before the check ran, at a sustained ~148 launches/hour, while the scanner
watching that platform had been reporting itself healthy and emitting nothing for over
twelve hours. The earlier recommendation in this session — build the health-check first
and treat pons as possibly retired — was made before that check and was wrong. Verifying
the chain directly rather than trusting the platform's website reversed the priority.

That generalizes into the rule this spec is built on, and it also killed the GoPlus item
today: **verify against our own data before believing a source is available or dead.**
An endpoint that answers is not an endpoint that has data; a website that is gone is not
a platform that is gone.

One consequence worth stating plainly: after this change, pons no longer depends on
pons.family at all. If the domain never returns, the scanner is unaffected. The same
pattern — discover on-chain, ignore the platform's API — is the right default for the
launchpad-expansion work later in the backlog, and it is why that item should reuse this
code path rather than integrating another API that can vanish.

The Tier A weights this restores to service are hand-fitted on very small samples: the
pons died-control is nine coins, the flap winner/loser split is twelve and five. They
are the best available prior and a clear improvement on what preceded them, but they are
not a calibrated model. The refit is what makes them trustworthy, and the feature
logging in this spec is what makes the refit possible.
