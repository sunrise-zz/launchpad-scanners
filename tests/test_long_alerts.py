"""Operator-facing identity and feed isolation for the long.xyz scanner.

long/ is bags/scan.py pointed at a single launchpad. These tests pin the two
things that separation buys — a label that reads as long.xyz rather than bags,
and state files that don't collide — because both fail silently: a wrong label
just looks like an alert from another platform, and a shared heartbeat would
let one scanner's liveness mask the other's outage.
"""
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_long_loads_the_shared_scanner_whatever_is_on_sys_path(long_scan):
    # Four scanners are named scan.py, so `import scan` resolves by sys.path
    # order — with long/ ahead of bags/ it picked up long/scan.py, which then
    # imported itself and died on a partially-initialized module. Loading by
    # path is what makes the entry point independent of the caller's sys.path.
    proc = subprocess.run(
        [sys.executable, "-c",
         # long/ ahead of bags/ makes plain `import scan` bind long/scan.py to
         # the name "scan" — the exact state the old entry point self-imported in.
         "import sys; sys.path.insert(0, 'long');"
         "import scan; print(scan.trench.NAME, scan.trench.PADS[0])"],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["long", "longxyz"]


def test_long_alerts_are_not_labelled_as_bags(long_scan):
    # The whole point of the split: a long.xyz coin must not read as a bags
    # launch, the way HOODFATHER-on-noxa did before the underlying pad was named.
    label = long_scan.trench.pad_label({"launchpad": "longxyz"})
    assert "bags" not in label
    assert label == "🔭 long"


def test_long_scanner_watches_only_its_own_launchpad(long_scan):
    # Adding longxyz to the bags list instead took 46 of 50 `pump` rows and cut
    # bags 19 -> 1 (measured 2026-07-22). A separate pad list is what keeps the
    # two feed budgets independent, so pin it.
    assert long_scan.trench.PADS == ["longxyz"]


def test_long_state_does_not_collide_with_bags(long_scan):
    data = long_scan.trench.DATA
    assert os.path.basename(os.path.dirname(data)) == "long"
    assert long_scan.trench.HEARTBEAT == os.path.join(data, "heartbeat.json")


def test_long_runs_a_tighter_bar_than_bags(long_scan, bags):
    # The bar has to scale with how busy the board is: long.xyz mints ~2.4
    # tokens/min, so bags' numbers pass a stream of thin rows here (12 of 50
    # board rows vs 7, measured 2026-07-22). Direction only — the magnitudes are
    # provisional until outcomes refit them.
    for key in ("holders", "vol", "progress"):
        assert long_scan.trench.BAR[key] > bags.BAR[key]


def test_long_scanner_reports_its_own_name_to_the_watchdog(long_scan):
    # watchdog.THRESHOLDS is keyed on the scanner name; "bags" here would make
    # the long feed inherit bags' entry and report outages under the wrong name.
    assert long_scan.trench.NAME == "long"
