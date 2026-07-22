"""Operator-facing identity for the GMGN Bags scanner."""


def test_bags_alerts_do_not_impersonate_the_underlying_launchpad(bags):
    # Leading with "bags" keeps a virtuals-on-robinhood alert distinguishable
    # from the separate Virtuals Protocol scanner.
    for pad in ("virtuals", "bankr", "noxa", "dyorswap"):
        assert bags.pad_label({"launchpad": pad}).startswith("👜 bags · ")


def test_bags_alerts_name_the_underlying_launchpad(bags):
    # HOODFATHER bonded on noxa but read as a bags launch (Jul 22).
    assert "noxa" in bags.pad_label({"launchpad": "noxa"})
    assert "bankr" in bags.pad_label({"launchpad": "bankr"})


def test_bags_launch_is_not_labelled_twice(bags):
    assert bags.pad_label({"launchpad": "bags"}) == "👜 bags"


def test_missing_launchpad_still_labels(bags):
    assert bags.pad_label({}).startswith("👜 bags · ")
