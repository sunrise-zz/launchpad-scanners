"""noxa scanner — Robinhood Chain (chainId 4663), source-level via noxa.fi.

noxa died once and came back. Its old site (noxa.fun) went NXDOMAIN 2026-07-18
with the V1 factory (0xD9eC2db5…) going dormant the same day; ~2026-07-22 the
platform relaunched at **noxa.fi** on a *new* factory
(0xdd84fddea1206115b37dbbc0ba5721530e1ba9c5) — the same domain-move pons made.
The relaunch rebuilt its index from zero (`coins == coins24h`) and immediately
ran busier than pons: ~205 launches/hour, $4.7M/24h measured at restart.

Why its own scanner and not GMGN's `noxa` trench key: that key still points at
the DEAD V1 factory. A live probe 2026-07-22 returned only V1 tokens aged
280-510h with new_creation/pump both empty — GMGN cannot see the V2 factory, so
the noxa seat in bags/scan.py's PADS is inert and would never fire on V2. The
V2 factory also does NOT emit the `TokenLaunched` topic the V1/pons contracts
share, so pons/api.py's on-chain discovery can't see it either.

What CAN see it is noxa.fi's own API — undocumented but public, no auth, 240
req/min, everything a scanner needs in one row. So this is a source-level
scanner (like pons/), not a GMGN trench rider (like bags/ and long/):

    GET /tokens?sort=new       -> launch feed: discovery, EARLY bar, controls
    GET /tokens?sort=trending  -> traction feed: catches GRADs and late crossers
    GET /tokens/{addr}         -> per-alert enrichment (socials, description)

Liveness caveat, learned from pons: a launchpad's web layer can die while its
factory keeps minting. noxa.fi's API IS the web layer, so if it goes down this
scanner goes deaf — the same failure mode flap has when batman.taxed.fun is
down. The on-chain fallback, unused here because it carries no traction fields
to score a bar on, is the factory event:
    factory 0xdd84fddea1206115b37dbbc0ba5721530e1ba9c5
    topic0  0x328c99edaab34570f8f3cc59ed72b4c179f4cb0abd9f57e25a0c563588c36994
            (topics[1]=token, topics[2]=deployer)
V2 token addresses also all end in the chainId suffix `4663` (mined via the
API's /launch/mine-salt), a cheap secondary label if the topic ever changes.

Tiers, seeding and control sampling mirror the trench scanners; scores are
weaker on purpose — this feed carries traction (holders/vol/progress/momentum)
but none of GMGN's forensics (smart money, bot/insider/honeypot rates), so the
red-flag cons those scanners lean on simply aren't available. Refit the bar and
weights from data/events.jsonl once outcomes accumulate, like every scanner here.

Alerts are labelled `🌀 noxa` and recorded to the tracker under platform `noxa`,
priced by track method `noxa` (tracker/track.py snap_noxa). Detect + rank +
alert only. It never trades. Stdlib only.

Usage:
    python3 noxa/scan.py --dry-run          # print alerts, no Telegram
    python3 noxa/scan.py --once             # one pass (candidates vs bar), exit
    python3 noxa/scan.py                     # live -> Telegram (pons/.env creds)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pons"))   # telegram + alertfmt + outcomes + controls + health
import alertfmt  # noqa: E402
import controls  # noqa: E402
import health  # noqa: E402
import outcomes  # noqa: E402
import telegram  # noqa: E402

# ---- scanner identity ------------------------------------------------------
NAME = "noxa"
EMOJI = "🌀"
PLATFORM = "noxa"          # tracker platform + track method key

API = "https://api.noxa.fi/api"
BLOCKSCOUT = "https://robinhoodchain.blockscout.com/token/"

# 🐣 EARLY traction bar. v1 judgment calls, refit from data/events.jsonl.
#
# Deliberately NOT gated on progress, unlike the GMGN-fed trench scanners.
# noxa.fi's `graduationPct` is NOT a bonding-curve fraction despite the name:
# measured 2026-07-22 it sits at a ~6.8% floor and a ~8% median for *active*
# coins and only jumps to 100% at graduation — noxacat with 709 holders,
# $161K/24h and 3082 trades read 14.9%. On this single-sided curve it tracks a
# net reserve that continuous two-way trading keeps low, so gating EARLY on it
# would reject the strongest coins on the board. The real traction signals here
# are holders + volume + trades; progress is display/score context only. (Same
# name-collision trap as pons/api.py's two BLOCK_SEC constants.)
BAR = {"holders": 60, "vol": 15_000.0}

DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)
HEARTBEAT = os.path.join(DATA, "heartbeat.json")


def log_event(kind, **kw):
    try:
        with open(os.path.join(DATA, "events.jsonl"), "a") as f:
            f.write(json.dumps({"t": time.time(), "kind": kind, **kw}) + "\n")
    except Exception:  # noqa: BLE001
        pass


def fnum(d, key, default=0.0):
    try:
        return float(d.get(key) or default)
    except (TypeError, ValueError):
        return default


def human(x, unit="$"):
    if x is None:
        return "?"
    x = float(x)
    if x >= 1_000_000:
        return f"{unit}{x/1e6:.1f}M"
    if x >= 1_000:
        return f"{unit}{x/1e3:.1f}K"
    return f"{unit}{x:.0f}"


def get(path):
    """One noxa.fi GET -> parsed JSON, or None. Never raises into the loop."""
    try:
        req = urllib.request.Request(path, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def fetch_list(sort, limit=50):
    """A trenches-style row list for one sort, or None on any failure.

    Returns the raw noxa.fi rows (mapped lazily by map_row) so the caller can
    tell a fetch failure (None) from an empty board ([]) — the same distinction
    the trench scanners draw before deciding whether to seed."""
    d = get(f"{API}/tokens?sort={sort}&page=1&limit={limit}")
    if not isinstance(d, dict):
        return None
    items = d.get("items")
    if not isinstance(items, list) or not health.is_record_list(items):
        return None
    return items


def map_row(r):
    """noxa.fi token row -> the internal item shape the rest of this file uses.

    Works on both a list row and a /tokens/{addr} detail row (a superset), so an
    alert can be enriched by merging the detail's socials/description over the
    list row without re-mapping. Numeric fields come back inconsistently typed
    from noxa.fi (`trades24h` is a string on detail, a number on stats) — fnum
    coerces every one, and a missing field folds to 0 for *scoring* only; the
    tracker row keeps None via outcomes.num()."""
    addr = (r.get("token") or "").lower()
    soc = r.get("socials") or {}
    return {
        "address": addr,
        "symbol": r.get("symbol"),
        "holders": fnum(r, "holderCount"),
        "vol24h": fnum(r, "volume24hUsd"),
        "mcap": r.get("marketCapUsd"),
        "price": r.get("priceUsd"),
        "progress": fnum(r, "graduationPct") / 100.0,
        "created_ts": r.get("createdTs") or 0,
        "graduated": bool(r.get("graduated")),
        "change5m": fnum(r, "changePct5m"),
        "trades24h": fnum(r, "trades24h"),
        "deployer": (r.get("deployer") or "").lower(),
        # present only on an enriched (detail) row:
        "telegram": soc.get("telegram") or None,
        "twitter": soc.get("twitter") or None,
        "website": soc.get("website") or None,
        "description": r.get("description") or None,
    }


def age_min(it, now):
    ts = it.get("created_ts") or 0
    return (now - ts) / 60 if ts > 1_000_000_000 else None


def passes_bar(it, args, now):
    """The EARLY predicate. Traction only — this feed carries no honeypot/tax
    signal to gate on, unlike the GMGN-fed scanners, and its `progress` is not a
    bonding fraction (see BAR), so the gate is holders + volume. --min-progress
    stays available as an opt-in gate but defaults off."""
    am = age_min(it, now)
    return ((am is None or am <= args.max_age_h * 60)
            and it["holders"] >= args.min_holders
            and it["vol24h"] >= args.min_vol
            and it["progress"] >= args.min_progress)


def score_item(it, base):
    """Heuristic 0-100 from noxa.fi enrichment. Deliberately traction-weighted:
    the forensic fields the trench scanners score (smart_degen, bot/insider/rat
    rates, honeypot) are not in this feed, so there is nothing here to fake a
    high score with cheap holders — refit against tracker outcomes once history
    accumulates (#10)."""
    s = float(base)
    s += min(it["holders"] / 25.0, 6)             # traction, capped
    if it["vol24h"] >= 50_000:
        s += 5
    elif it["vol24h"] >= 20_000:
        s += 3
    if it["trades24h"] >= 500:
        s += 3
    # No progress term: graduationPct is not a bonding fraction on this feed
    # (see BAR), so a "mid-climb sweet spot" would score the wrong thing.
    if it["change5m"] > 0:
        s += 3
    if it["change5m"] >= 20:
        s += 2
    if it.get("twitter") or it.get("telegram"):
        s += 3
    if it.get("website"):
        s += 2
    return alertfmt.clamp(s)


def links(addr):
    return [[("📈 GMGN", f"https://gmgn.ai/robinhood/token/{addr}"),
             ("📊 DexScreener", f"https://dexscreener.com/robinhood/{addr}")],
            [("🌀 noxa", f"https://noxa.fi/coin/{addr}"),
             ("🔗 Scan", f"{BLOCKSCOUT}{addr}")]]


def build_alert(tier_emoji, tier, base, it, lead_pros, now):
    score = score_item(it, base)
    sym = html.escape(str(it.get("symbol") or it["address"][:8]))
    pros = list(lead_pros)
    socbits = []
    if it.get("twitter"):
        socbits.append("🐦 X")
    if it.get("website"):
        socbits.append("🌐 web")
    if it.get("telegram"):
        socbits.append("💬 TG")
    if socbits:
        pros.append(" · ".join(socbits))

    cons = []
    if not (it.get("twitter") or it.get("telegram") or it.get("website")):
        cons.append("no socials")

    am = age_min(it, now)
    stats = [f"💰 mc {human(it.get('mcap'))} · 👥 {int(it['holders'])} holders "
             f"· 📈 vol24h {human(it['vol24h'])} "
             f"· ⏱️ {f'{am/60:.1f}h' if am and am >= 60 else (f'{am:.0f}m' if am else '?')}"]
    addr = it["address"]
    body = alertfmt.compose(score, tier_emoji, tier, sym, f"{EMOJI} {NAME}", "ROBINHOOD",
                            pros, cons, stats,
                            f'<a href="{BLOCKSCOUT}{addr}">{addr[:12]}…</a>')
    return score, body


def enrich(it):
    """Merge /tokens/{addr} detail (socials, description) over a list row.

    Only called for a coin about to alert — the list feed omits socials, and one
    detail fetch per alert (a handful an hour) is cheap against the 240 req/min
    budget. Best-effort: a failed fetch just leaves the social pros/cons off."""
    d = get(f"{API}/tokens/{it['address']}")
    if isinstance(d, dict) and d.get("token"):
        it.update({k: v for k, v in map_row(d).items()
                   if k in ("telegram", "twitter", "website", "description")})
    return it


def track_dict(addr):
    return {"method": PLATFORM, "chainSlug": "robinhood", "address": addr}


def record_for(it, tier, score):
    return dict(platform=PLATFORM, chain="ROBINHOOD", tier=tier,
                symbol=str(it.get("symbol") or it["address"][:8]), token=it["address"],
                score=score, track=track_dict(it["address"]),
                price0=it.get("price"), mcap0=it.get("mcap"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=30.0, help="poll (s)")
    ap.add_argument("--max-age-h", type=float, default=24.0, help="EARLY only for coins younger than this")
    ap.add_argument("--min-holders", type=int, default=BAR["holders"])
    ap.add_argument("--min-vol", type=float, default=BAR["vol"], help="volume_24h USD")
    ap.add_argument("--min-progress", type=float, default=0.0,
                    help="opt-in graduationPct gate 0-1 (off by default; not a bonding fraction, see BAR)")
    ap.add_argument("--limit", type=int, default=50, help="rows per sort")
    ap.add_argument("--once", action="store_true", help="one pass, print candidates vs bar, exit")
    ap.add_argument("--dry-run", action="store_true")
    controls.add_args(ap)
    args = ap.parse_args()

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)

    if args.once:
        rows = fetch_list("new", args.limit) or []
        now = time.time()
        print(f"### /tokens?sort=new: {len(rows)}")
        for r in rows:
            it = map_row(r)
            am = age_min(it, now)
            print(f"  {str(it.get('symbol'))[:14]:<14} prog={it['progress']*100:5.1f}% "
                  f"holders={int(it['holders']):>4} vol24h={human(it['vol24h']):>8} "
                  f"trades={int(it['trades24h']):>4} age={f'{am:.0f}m' if am else '?':>5} "
                  f"{'BAR✓' if passes_bar(it, args, now) else ''}")
        return

    progbar = f" & prog>={args.min_progress*100:.0f}%" if args.min_progress > 0 else ""
    print(f"{NAME} scanner (noxa.fi, robinhood)  "
          f"bar: holders>={args.min_holders} & vol24h>=${args.min_vol:.0f}{progbar} "
          f"& age<={args.max_age_h:.0f}h  -> {'DRY-RUN' if dry else f'Telegram {chat_id}'}", flush=True)

    def dispatch(text, label, buttons=None, record=None):
        stamp = time.strftime("%H:%M:%S")
        if dry:
            print(f"[{stamp}] DRY {label}\n" + text, flush=True)
            return
        ok, info = telegram.send(text, token_tg, chat_id, buttons=buttons)
        if record and ok:
            record["tg"] = {"msg_id": info if isinstance(info, int) else None,
                            "text": text, "buttons": buttons}
            outcomes.record_alert(**record)   # only record alerts that actually sent
        print(f"[{stamp}] {'sent -> ' + label if ok else 'send FAILED (' + label + '): ' + info}", flush=True)

    sampler = controls.ControlSampler(
        PLATFORM, k=args.controls_k, bucket_s=args.controls_bucket_s,
        state_path=os.path.join(DATA, "control_slot.json"))
    seen_new = set()     # addresses already registered from the launch feed
    early_sent = set()
    grad_sent = set()
    seeded = set()       # sorts that had one successful poll (silent seed pass)

    def sample_control(now, pool):
        """One coin we evaluated and passed over becomes a control (#9).

        Drawn from the launch feed's sub-bar coins — the ones sitting just under
        the traction bar are exactly what tells us whether the bar is set right.
        A sampled coin can still cross the bar later and alert, leaving it in
        both populations: recorded rather than prevented, same as the trench
        scanners. See docs/shadow-control-sampling.md."""
        picked = sampler.choose(now, pool, key=lambda x: x["address"])
        if picked is None:
            return
        addr = picked["address"]
        log_event("control", addr=addr, sym=picked.get("symbol"),
                  holders=picked["holders"], prog=picked["progress"])
        outcomes.record_control(PLATFORM, "ROBINHOOD",
                                str(picked.get("symbol") or addr[:8]), addr,
                                track_dict(addr),
                                mcap0=picked.get("mcap"))

    def handle_grad(it, now, first):
        addr = it["address"]
        if addr in grad_sent:
            return
        grad_sent.add(addr)
        if first:
            return                 # backlog: seed silently
        score, body = build_alert("🚀", "NOXA GRAD", 50, enrich(it), [
            "🚀 bonded — curve completed, trading on DEX",
        ], now)
        log_event("grad_alert", addr=addr, sym=it.get("symbol"), score=score,
                  holders=it["holders"], mc=it.get("mcap"))
        dispatch(body, f"NOXA GRAD {it.get('symbol')}", buttons=links(addr),
                 record=record_for(it, "NOXA GRAD", score))

    def handle_early(it, now, first, pool):
        addr = it["address"]
        if addr in early_sent or addr in grad_sent:
            return
        if first:
            # Seed only the coins ALREADY over the bar — the strong backlog we
            # must not re-alert on restart. Sub-bar coins are left un-seeded on
            # purpose: the `new` feed is pre-traction, so seeding all of it would
            # blind us for life to any coin launched in the ~15min before a
            # restart that moons afterwards. An un-seeded coin that later crosses
            # the bar is a real crossing, not backlog.
            if passes_bar(it, args, now):
                early_sent.add(addr)
            return
        if not passes_bar(it, args, now):
            # Control population (#9): sub-bar coins we evaluated and passed over.
            # Require a nonzero baseline — a just-minted coin at mcap 0 has no t0
            # to measure a return from (report.py divides by it), so it would
            # spend a control slot on an unmeasurable row. The corpses that DO
            # have a baseline (a few $K that dies at -100%) still count, which is
            # the base rate we want; only the not-yet-traded mints drop out.
            if it.get("mcap"):
                pool.append(it)
            return
        early_sent.add(addr)
        it = enrich(it)
        b = int(it["trades24h"])
        score, body = build_alert("🐣", "NOXA EARLY", 42, it, [
            f"👥 <b>{int(it['holders'])}</b> holders · vol24h {human(it['vol24h'])} "
            f"· trades24h {b}" + (f" · 5m {it['change5m']:+.0f}%" if it["change5m"] else ""),
        ], now)
        log_event("early_alert", addr=addr, sym=it.get("symbol"), score=score,
                  prog=it["progress"], holders=it["holders"], vol=it["vol24h"])
        dispatch(body, f"NOXA EARLY {it.get('symbol')}", buttons=links(addr),
                 record=record_for(it, "NOXA EARLY", score))

    def poll(now):
        new_rows = fetch_list("new", args.limit)
        trend_rows = fetch_list("trending", args.limit)
        if new_rows is None and trend_rows is None:
            print(f"[{time.strftime('%H:%M:%S')}] noxa.fi fetch failed", flush=True)
            return
        pool = []   # sub-bar coins this poll, for one control draw

        if new_rows is not None:
            first = "new" not in seeded
            for r in new_rows:
                it = map_row(r)
                if not it["address"]:
                    continue
                if it["address"] not in seen_new:
                    seen_new.add(it["address"])
                    if not first:
                        log_event("launch", addr=it["address"], sym=it.get("symbol"),
                                  deployer=it.get("deployer"))
                if it["graduated"]:
                    handle_grad(it, now, first)
                else:
                    handle_early(it, now, first, pool)
            if not first:
                sample_control(now, pool)
            seeded.add("new")

        if trend_rows is not None:
            first = "trending" not in seeded
            for r in trend_rows:
                it = map_row(r)
                if not it["address"]:
                    continue
                if it["graduated"]:
                    handle_grad(it, now, first)
                else:
                    handle_early(it, now, first, [])   # trending is not a control source
            seeded.add("trending")

        health.touch(HEARTBEAT, NAME, now=now,
                     detail={"new": len(new_rows or []), "trending": len(trend_rows or [])})

    print("running… Ctrl-C to stop", flush=True)
    while True:
        try:
            poll(time.time())
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  loop error: {e}", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
