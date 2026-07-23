"""Shadow-control sampling for the trench scanners (#9).

pons/flap/virtuals/pump each cover one launchpad, so controls.py could assume
one quota per process. The trench scanner breaks that assumption: bags/scan.py
covers five launchpads in one process, and report.py's EDGE subtracts the
control median of the *same* platform. A quota that isn't split per launchpad
produces no error — just an EDGE that silently cannot be computed for whichever
pads lost the race. These tests pin the split.

See tests/test_shadow_controls.py for the shared sampler policy itself.
"""
from __future__ import annotations

import os

# Aligned bucket, same convention as test_shadow_controls.py: the quota is per
# aligned bucket, so a window starting mid-bucket straddles slots.
HOUR0 = 277778 * 3600


def test_each_launchpad_gets_its_own_quota(bags, tmp_path):
    # The bags process polls five pads from one feed. Sharing one quota would
    # mean the first pad to be offered a coin spends the hour for all of them.
    registry = bags.sampler_registry(os.fspath(tmp_path), k=1, bucket_s=3600)
    assert registry("bags") is not registry("bankr")
    assert registry("bags") is registry("bags"), "quota must persist across polls"


def test_one_pad_spending_its_slot_does_not_starve_another(bags, tmp_path):
    registry = bags.sampler_registry(os.fspath(tmp_path), k=1, bucket_s=3600)
    now = HOUR0

    assert registry("bags").take(now) is True
    assert registry("bags").take(now) is False, "same pad, same slot: quota spent"
    # The regression this file exists for: bankr must still have its own slot.
    assert registry("bankr").take(now) is True


def test_quotas_survive_a_restart_independently(bags, tmp_path):
    # State is per-pad on disk, so a restart must not hand every pad a fresh
    # slot — a crash-looping scanner would otherwise sample without bound.
    first = bags.sampler_registry(os.fspath(tmp_path), k=1, bucket_s=3600)
    assert first("bags").take(HOUR0) is True

    reborn = bags.sampler_registry(os.fspath(tmp_path), k=1, bucket_s=3600)
    assert reborn("bags").take(HOUR0) is False, "restart replayed a spent slot"
    assert reborn("bankr").take(HOUR0) is True, "bankr's untouched slot was lost"


def test_pads_do_not_share_a_state_file(bags, tmp_path):
    registry = bags.sampler_registry(os.fspath(tmp_path), k=1, bucket_s=3600)
    registry("bags").take(HOUR0)
    registry("bankr").take(HOUR0)

    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == ["control_slot_bags.json", "control_slot_bankr.json"]


def test_long_keeps_its_controls_out_of_the_bags_directory(long_scan, bags):
    # long/ and bags/ are separate instances of one implementation; a shared
    # control_slot file would make each restart of one clobber the other's quota.
    assert long_scan.trench.DATA != bags.DATA
