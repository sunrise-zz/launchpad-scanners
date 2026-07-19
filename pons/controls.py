"""Shadow-control sampling — which launches become the control group (#9).

The tracker only ever measured coins we alerted on, so it could tell us "flap
EARLY returned +53% at 4h" but never "…against what?". Without a control group
every number it produces is survivorship-biased confirmation: we cannot tell a
good filter from a rising market, and we cannot tell whether the bars are too
tight, because the coins just under the bar were never measured at all.

This module answers one question — *should this launch become a control?* — and
nothing else. The caller does the measuring (`outcomes.record_control`), which
keeps the expensive part (an API call, a feature dict) on the accepted path
only, and keeps the policy here small enough to reason about.

SAMPLING DESIGN
    Population   every launch the scanner observes and did not alert on. Not
                 "every launch with some traction": the question is whether an
                 alert beats a *random* launch from the same window, so the
                 denominator has to include the corpses. Most controls will die
                 at ~-100%. That is the finding, not a defect.
    Bucket       one hour, per launchpad. Alerted and control coins are then
                 drawn from the same hour and the same chain conditions, so a
                 market-wide pump lifts both and cancels out of the comparison.
    K            2 per bucket per launchpad (~48/day each). Chosen against
                 tracker cost — every control costs the same ~10 horizon
                 fetches over 48h as an alert — not against statistical power.
    Rule         systematic time sampling. The bucket is cut into K equal
                 slots and the first launch offered in each slot is taken.

Why slots rather than "the first K launches of the hour": launches cluster hard
(a listing, a trend, one deployer spamming), so first-K would hand the entire
hour's quota to whatever happened during a burst — and bursts are exactly when
launches are least representative of the hour. Slots spread the sample across
the bucket for free, with no RNG, which also makes the policy deterministic and
testable.

Why not Bernoulli sampling at rate p, which is the textbook answer: p has to be
calibrated to the launch rate to yield K, and the launch rate varies by three
orders of magnitude across our launchpads (flap ~5000/day, arc a handful) and
by time of day within each. That calibration is a second estimator to build,
tune and get wrong. Systematic sampling buys the same "spread across the frame"
property with none of it.

The known bias, recorded for the refit: within a slot we take the *first*
launch, so a launch that opens a slot is likelier to be sampled than one
arriving mid-slot. Slot-opening is a function of arrival time, not of the
launch's own traits, so this does not correlate with outcome — but it does mean
the sample is not strictly uniform-at-random, and inverse-propensity weighting
is the v2 refinement if that ever needs to be exact.
"""
from __future__ import annotations

import collections
import json
import os
import random

DEFAULT_K = 2
DEFAULT_BUCKET_S = 3600
# How many recently-sampled tokens to remember, to avoid sampling one twice.
# Bounded rather than complete: these run for weeks inside a 24/7 daemon and
# flap alone sees ~5000 launches a day, so an unbounded set is the memory leak
# in #14 written a second time. A coin old enough to fall out of this window is
# long past its watch window and can never be offered again anyway.
SEEN_MAX = 5000


def add_args(ap):
    """Attach the shared --controls-* flags to a scanner's parser.

    Here rather than copied into each scanner so the defaults, the help text
    and the kill switch are one thing. Every scanner runs from a LaunchAgent
    with no arguments, so these defaults ARE the production configuration."""
    ap.add_argument("--controls-k", type=int, default=DEFAULT_K,
                    help="shadow-control launches to sample per bucket (#9; 0=off)")
    ap.add_argument("--controls-bucket-s", type=int, default=DEFAULT_BUCKET_S,
                    help="shadow-control sampling bucket, seconds")


class ControlSampler:
    """Per-launchpad quota. `take(now)` says whether to make this one a control.

    One instance per scanner process, since each scanner covers one launchpad.
    """

    __slots__ = ("platform", "k", "bucket_s", "state_path", "_slot", "_seen", "_order")

    def __init__(self, platform, k=DEFAULT_K, bucket_s=DEFAULT_BUCKET_S, state_path=None):
        self.platform = platform
        self.k = max(0, int(k))
        self.bucket_s = float(bucket_s)
        self.state_path = state_path
        self._slot = self._load()
        self._seen = set()
        self._order = collections.deque()

    def _slot_of(self, now):
        """Which slot `now` falls in, counted from the epoch so the boundaries
        are wall-clock aligned and survive a restart without being stored."""
        return int(now // (self.bucket_s / self.k))

    def _load(self):
        """The last slot we spent, from a previous run. None when there is no
        state to read — a fresh host, or a corrupt file we would rather ignore
        than crash a scanner over."""
        if not self.state_path or not os.path.exists(self.state_path):
            return None
        try:
            with open(self.state_path) as f:
                slot = json.load(f).get("slot")
            return int(slot) if slot is not None else None
        except Exception:  # noqa: BLE001
            return None

    def _save(self):
        if not self.state_path:
            return
        try:
            os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
            with open(self.state_path, "w") as f:
                json.dump({"platform": self.platform, "slot": self._slot}, f)
        except Exception:  # noqa: BLE001
            pass

    def sampled(self, token):
        """Whether this token has already been taken as a control.

        Callers filter their pool on this. Observed live on the first run:
        flap sampled one token in two consecutive slots, at 0.7s and 11.5s old
        — the pool is whatever is under watch right then, which just after a
        restart is a handful of coins, so random.choice lands on the same one.
        Two rows for one coin double its weight in a base rate built from ~48
        rows a day.

        In memory only, deliberately. Re-sampling one coin after a restart is a
        single duplicate in a rare event; a persisted set is a file that grows
        forever."""
        return token in self._seen

    def mark(self, token):
        """Remember a token as sampled, evicting the oldest past SEEN_MAX."""
        if token in self._seen:
            return
        self._seen.add(token)
        self._order.append(token)
        while len(self._order) > SEEN_MAX:
            self._seen.discard(self._order.popleft())

    def choose(self, now, pool, key):
        """One item from `pool` to record as a control, or None.

        The whole sampling decision in one call: skip anything already sampled,
        spend a slot if one is open, pick uniformly from what remains, and
        remember the pick. Every scanner drives it the same way and differs only
        in how it builds `pool` and what it then measures — so a change to the
        policy (the inverse-propensity weighting the design doc names as v2) is
        a change to this method, not to four scan loops.

        `key` maps a pool item to its token/id, since each scanner's pool holds
        a different type.
        """
        eligible = [x for x in pool if not self.sampled(key(x))]
        if not eligible or not self.take(now):
            return None
        pick = random.choice(eligible)
        self.mark(key(pick))
        return pick

    def take(self, now):
        """True if a slot is open for another control. Fires at most once per
        slot, so at most K times per aligned bucket.

        Callers should normally use choose(), which spends the slot only when
        it has something to spend it on.

        The spent slot is persisted before returning True, because the thing it
        guards against is a scanner that dies and comes back: quota kept only
        in memory would reset on every restart, and a crash-looping scanner
        would sample without bound."""
        if not self.k:
            return False
        slot = self._slot_of(now)
        if slot == self._slot:
            return False
        self._slot = slot
        self._save()
        return True
