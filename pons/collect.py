"""Snapshot pons.family launches + graduations and print the base-rate dynamics
that justify the scanner's thresholds. Writes to analysis/pons/data/.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import api  # noqa: E402

DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def pct(x, q):
    return x[min(int(len(x) * q), len(x) - 1)]


def main():
    launches = api.all_launches()
    grads = api.graduations()
    json.dump(launches, open(os.path.join(DATA, "launches.json"), "w"))
    json.dump(grads, open(os.path.join(DATA, "graduations.json"), "w"))
    gset = {g["token"].lower() for g in grads}
    n = len(launches)
    ng = sum(1 for L in launches if L["token"].lower() in gset)
    print(f"launches={n}  graduations(joined)={ng}  base rate={100*ng/n:.3f}%")

    # time-to-graduate
    Lby = {L["token"].lower(): L for L in launches}
    ttg = []
    for g in grads:
        L = Lby.get(g["token"].lower())
        if L and L.get("launchedAt"):
            d = ts(g["graduatedAt"]) - ts(L["launchedAt"])
            if d > 0:
                ttg.append(d / 60)
    ttg.sort()
    print(f"time-to-graduate min: p10={pct(ttg,.1):.1f} p25={pct(ttg,.25):.1f} "
          f"median={pct(ttg,.5):.1f} p75={pct(ttg,.75):.1f} p90={pct(ttg,.9):.1f}")

    # deployer reputation (weak but recorded): prior graduations lift
    for L in launches:
        L["_t"] = ts(L["launchedAt"]) if L.get("launchedAt") else 0
        L["_dep"] = L["deployer"].lower()
    launches.sort(key=lambda x: x["_t"])
    tok2dep = {L["token"].lower(): L["_dep"] for L in launches}
    dep_grad_times = defaultdict(list)
    for g in grads:
        dep = tok2dep.get(g["token"].lower())
        if dep:
            dep_grad_times[dep].append(ts(g["graduatedAt"]))
    b = {"0 prior grad": [0, 0], ">=1 prior grad": [0, 0]}
    for L in launches:
        prior = sum(1 for t in dep_grad_times.get(L["_dep"], []) if t < L["_t"])
        k = ">=1 prior grad" if prior >= 1 else "0 prior grad"
        b[k][0] += 1
        b[k][1] += L["token"].lower() in gset
    print("deployer reputation lift (leakage-free):")
    for k, (nn, gg) in b.items():
        print(f"  {k:16s} n={nn:6d} rate={100*gg/nn:.2f}%")

    # metadata lift
    for feat, f in [("has_desc", lambda L: bool(L.get("description"))),
                    ("has_logo", lambda L: bool(L.get("logo")))]:
        for val in (True, False):
            sub = [L for L in launches if f(L) == val]
            gg = sum(1 for L in sub if L["token"].lower() in gset)
            if sub:
                print(f"  {feat}={str(val):5s} n={len(sub):6d} rate={100*gg/len(sub):.2f}%")

    # save a deployer reputation table for the scanner (all-time grad count per deployer)
    dep_grads = Counter()
    for g in grads:
        dep = tok2dep.get(g["token"].lower())
        if dep:
            dep_grads[dep] += 1
    json.dump(dict(dep_grads), open(os.path.join(DATA, "deployer_grads.json"), "w"))
    print(f"wrote deployer_grads.json ({len(dep_grads)} deployers with >=1 graduation)")


if __name__ == "__main__":
    main()
