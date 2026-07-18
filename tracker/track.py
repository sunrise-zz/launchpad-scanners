"""Outcome tracker daemon — follows every alerted coin's price over time.

Reads tracker/data/alerts.jsonl (written by each scanner via pons/outcomes.py)
and, for each alert, samples the coin's price / mcap / liquidity at a fixed set
of horizons after the alert (5m … 48h), appending each sample to
tracker/data/snapshots.jsonl. tracker/report.py then turns this into a
performance summary so the score weights can be refit from real outcomes.

Price sources are chosen per alert by its `track` dict:
    dexscreener  -> api.dexscreener.com/tokens/v1/{robinhood|base|solana}/{addr}
    arc          -> web-production-efe27.up.railway.app/token/{addr}
    virtuals     -> api2.virtuals.io/api/virtuals/{id}   (mcap in VIRTUAL)
    gmgn         -> openapi.gmgn.ai token/info (needs GMGN_API_KEY; used by
                    bags/scan.py whose pads DexScreener may not index)

Idempotent and resumable: a (alert_id, horizon) already in snapshots.jsonl is
never re-sampled, so restarts and the 24/7 LaunchAgent are safe.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)
ALERTS = os.path.join(DATA, "alerts.jsonl")
SNAPS = os.path.join(DATA, "snapshots.jsonl")

# sample offsets after the alert, in minutes
HORIZONS = [5, 15, 30, 60, 120, 240, 480, 720, 1440, 2880]
DONE_AFTER = (HORIZONS[-1] + 30) * 60   # stop tracking an alert this long after it fired
STALE_SLACK = 10 * 60                   # a horizon sampled >10min late is recorded as missed,
                                        # not counted (guards against downtime poisoning the data)

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Accept": "application/json"}


def fetch_json(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def snap_dexscreener(slug, addr):
    pairs = fetch_json(f"https://api.dexscreener.com/tokens/v1/{slug}/{addr}")
    if not pairs:
        return None
    p = max(pairs, key=lambda x: (x.get("liquidity") or {}).get("usd") or 0)
    return {"price": float(p["priceUsd"]) if p.get("priceUsd") else None,
            "mcap": p.get("marketCap"),
            "liq": (p.get("liquidity") or {}).get("usd")}


def snap_arc(addr):
    d = fetch_json(f"https://web-production-efe27.up.railway.app/token/{addr}",
                   headers={"Origin": "https://arcdexscan.com", "Referer": "https://arcdexscan.com/"})
    return {"price": d.get("price"), "mcap": d.get("mcap"), "liq": d.get("liquidityUsdc")}


def snap_virtuals(vid):
    d = fetch_json(f"https://api2.virtuals.io/api/virtuals/{vid}",
                   headers={"Origin": "https://app.virtuals.io", "Referer": "https://app.virtuals.io/"})
    r = (d or {}).get("data") or {}
    # mcapInVirtual is the meaningful curve metric; liquidityUsd for context
    return {"price": None, "mcap": r.get("mcapInVirtual"), "liq": r.get("liquidityUsd"),
            "tvl": r.get("totalValueLocked"), "graduated": bool(r.get("tokenAddress"))}


def snap_pumpfun(mint):
    d = fetch_json(f"https://frontend-api-v3.pump.fun/coins/{mint}")
    return {"price": None, "mcap": (d or {}).get("usd_market_cap"),
            "liq": (d or {}).get("real_sol_reserves"),
            "complete": bool((d or {}).get("complete"))}


def snap_gmgn(chain_slug, addr):
    import sys
    sys.path.insert(0, os.path.join(HERE, "..", "pons"))
    import gmgn
    gchain = {"robinhood": "robinhood", "base": "base", "solana": "sol"}.get(chain_slug)
    d = gmgn.token_info(gchain, addr) or {}
    price = None
    try:
        price = float((d.get("price") or {}).get("price"))
    except (TypeError, ValueError):
        pass
    mcap = None
    try:
        mcap = price * float(d.get("circulating_supply")) if price else None
    except (TypeError, ValueError):
        pass
    liq = None
    try:
        liq = float(d.get("liquidity"))
    except (TypeError, ValueError):
        pass
    return {"price": price, "mcap": mcap, "liq": liq} if d else None


def snap_flap(addr):
    # DexScreener doesn't reliably index small Robinhood-chain tokens, so price
    # flap coins from flap's own backend (mcap/liquidity are USD-ish numbers).
    import time as _t
    d = fetch_json(f"https://batman.taxed.fun/v3/coin/{addr}?_refresh={_t.strftime('%Y%m%d')}",
                   headers={"Origin": "https://flap.sh", "Referer": "https://flap.sh/"})
    return {"price": (d or {}).get("price"), "mcap": (d or {}).get("marketCap"),
            "liq": (d or {}).get("liquidity")}


def take_snapshot(track):
    """Dispatch to the right price source. Returns dict or None (never raises)."""
    try:
        m = track.get("method")
        if m == "dexscreener":
            return snap_dexscreener(track["chainSlug"], track["address"])
        if m == "arc":
            return snap_arc(track["address"])
        if m == "virtuals":
            return snap_virtuals(track["id"])
        if m == "pumpfun":
            return snap_pumpfun(track["address"])
        if m == "flap":
            return snap_flap(track["address"])
        if m == "gmgn":
            return snap_gmgn(track.get("chainSlug") or "robinhood", track["address"])
    except Exception:  # noqa: BLE001
        return None
    return None


def alert_id(a):
    return f"{a['t']:.0f}:{a.get('token')}"


def load_alerts():
    out = []
    if not os.path.exists(ALERTS):
        return out
    for line in open(ALERTS):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
    return out


def load_done():
    """Set of (alert_id, horizon) already sampled."""
    done = set()
    if not os.path.exists(SNAPS):
        return done
    for line in open(SNAPS):
        try:
            s = json.loads(line)
            done.add((s["id"], s["h"]))
        except Exception:  # noqa: BLE001
            pass
    return done


def append_snap(row):
    with open(SNAPS, "a") as f:
        f.write(json.dumps(row) + "\n")


def cycle():
    now = time.time()
    alerts = load_alerts()
    done = load_done()
    cache = {}   # track-key -> snapshot this cycle (dedupe multi-horizon-due coins)
    due = 0
    for a in alerts:
        age = now - a["t"]
        if age > DONE_AFTER:
            continue
        aid = alert_id(a)
        track = a.get("track") or {}
        key = track.get("method", "") + ":" + str(track.get("address") or track.get("id"))
        for h in HORIZONS:
            if age < h * 60 or (aid, h) in done:
                continue
            # Staleness cap: if we're sampling more than STALE_SLACK past the
            # horizon (tracker was down, or a huge backlog), the current price is
            # NOT a valid "h-minute" datapoint — record it as missed and move on,
            # rather than poisoning the per-horizon medians the refit relies on.
            if age > h * 60 + STALE_SLACK:
                append_snap({"id": aid, "token": a.get("token"), "h": h, "t": now,
                             "age_min": round(age / 60, 1), "stale": True,
                             "price": None, "mcap": None, "liq": None})
                done.add((aid, h))
                continue
            # this horizon just came due — sample once per coin per cycle
            if key not in cache:
                cache[key] = take_snapshot(track)
            snap = cache[key]
            if snap is None:
                # transient fetch failure — do NOT mark done, retry next cycle
                # (the staleness cap above bounds how long we keep retrying)
                continue
            append_snap({"id": aid, "token": a.get("token"), "h": h, "t": now,
                         "age_min": round(age / 60, 1),
                         "price": snap.get("price"),
                         "mcap": snap.get("mcap"),
                         "liq": snap.get("liq")})
            done.add((aid, h))
            due += 1
    return len(alerts), due


def main():
    print(f"outcome tracker  horizons={HORIZONS}min  alerts={ALERTS}", flush=True)
    print("running… Ctrl-C to stop", flush=True)
    while True:
        try:
            n, due = cycle()
            if due:
                print(f"[{time.strftime('%H:%M:%S')}] {n} alerts tracked · {due} snapshots taken", flush=True)
            time.sleep(60)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  loop error: {e}", flush=True)
            time.sleep(30)


if __name__ == "__main__":
    main()
