"""Operator-facing identity for the GMGN Bags scanner."""


def test_bags_alerts_do_not_impersonate_the_underlying_launchpad(bags):
    # Leading with "bags" keeps a virtuals-on-robinhood alert distinguishable
    # from the separate Virtuals Protocol scanner.
    for pad in ("virtuals", "bankr", "dyorswap"):
        assert bags.pad_label({"launchpad": pad}).startswith("👜 bags · ")


def test_bags_alerts_name_the_underlying_launchpad(bags):
    # The underlying pad is named so a bankr/dyorswap coin isn't read as a bare
    # bags launch — the way HOODFATHER-on-noxa was before this landed (Jul 22).
    # (noxa itself is no longer a bags pad; live V2 has its own scanner.)
    assert "bankr" in bags.pad_label({"launchpad": "bankr"})
    assert "dyorswap" in bags.pad_label({"launchpad": "dyorswap"})


def test_bags_launch_is_not_labelled_twice(bags):
    assert bags.pad_label({"launchpad": "bags"}) == "👜 bags"


def test_missing_launchpad_still_labels(bags):
    assert bags.pad_label({}).startswith("👜 bags · ")
