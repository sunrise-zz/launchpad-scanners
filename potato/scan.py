"""potato scanner — Robinhood Chain (chainId 4663), source-level via potato.fm.

"Potato Pad — PEOPLE'S LAUNCHPAD" plants a coin straight into a locked Uniswap
V3 position, live and tradable from the first block (no bonding curve on the
`direct` kind). It runs on Robinhood Chain, the same chain as pons/flap/noxa/long,
and is an **aggregator over several pad factory contracts** rather than a single
launchpad — the `/api/tokens` feed carries a `pad` address and a `kind`
(`direct` = straight-to-V3, `curve` = bonding-curve) on every row.

Why its own source-level scanner and not a GMGN trench rider: potato.fm ships a
clean public API off its own Next.js origin (no auth, urllib-reachable — it is
NOT Cloudflare-walled the way long.xyz's own API is), and the whole pad is tiny
enough (~60 tokens all-time at first sight) that one page IS the complete board.
That is source-level, 100%-coverage freshness a fixed 50-row GMGN board can't
match. Two feeds, deduped by address (symbols repeat — several live "MASH" and
"POTATO" tokens are distinct addresses, so anything keyed on symbol would fold
real coins together):

    GET /api/tokens   -> {creations:[…]}  the "Growing" board: discovery, EARLY
                                          bar, control pool. Socials are INLINE
                                          (unlike noxa, so no per-alert detail
                                          fetch). Only traction field: volume24Usd.
    GET /api/ancient  -> {tokens:[…]}     the "Ancients": tokens matured into a
                                          real WETH pool. RICHER than Growing —
                                          carries fdvUsd + liquidityUsd + volume.

The two feeds are asymmetric on purpose (it mirrors what the site itself has):
a Growing row has no per-token mcap/holders/price/trades — the site computes
market cap client-side from the V3 pool over RPC — so the EARLY bar is
**volume + age** only, and scores are weaker than the trench scanners' (no
holders, no 5m momentum, and none of GMGN's forensics — smart money, bot/insider
/honeypot rates). Honest v1; refit the bar and weights from data/events.jsonl
once outcomes accumulate, like every scanner here.

Tiers:
    🥔 POTATO EARLY  — a young coin on the Growing board crossing the volume bar.
    🚀 POTATO GRAD   — a coin surfacing in the Ancients (matured to a WETH pool),
                       carrying real fdv/liquidity. Appearance is the event.

Pricing the outcome: a Growing row has no t0 mcap, so EARLY alerts record
mcap0=None and lean on the tracker's earliest-snapshot baseline; GRAD alerts
carry fdvUsd as a real baseline. Every potato alert prices by track method
**gmgn** (chainSlug robinhood) — potato coins are ordinary Uniswap V3 tokens on
robinhood that GMGN indexes, unlike noxa V2 which is invisible to GMGN and needs
its own snap. tracker/track.py needs no potato-specific method as a result.

Liveness caveat, same as noxa/flap: potato.fm's API IS its web layer, so if it
goes down this scanner goes deaf. It is also an unaudited demo MVP and the
/api/tokens endpoint occasionally 502s or times out under a cold scan cache —
get() folds every such failure to None so a bad poll is skipped, never fatal.
The on-chain fallback (unused here — the factory events carry no traction field
to score a bar on) is the pad factory `Creation`/launch event; the pad addresses
are on each row under `pad`.

Alerts are labelled `🥔 potato` and recorded to the tracker under platform
`potato`. Detect + rank + alert only. It never trades. Stdlib only.

Usage:
    python3 potato/scan.py --dry-run          # print alerts, no Telegram
    python3 potato/scan.py --once             # one pass (candidates vs bar), exit
    python3 potato/scan.py                     # live -> Telegram (pons/.env creds)
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
NAME = "potato"
EMOJI = "🥔"
PLATFORM = "potato"          # tracker platform key

API = "https://potato.fm/api"
COIN = "https://potato.fm/token/"
BLOCKSCOUT = "https://robinhoodchain.blockscout.com/token/"

# 🐣 EARLY traction bar — volume + age only. v1 judgment call, refit from
# data/events.jsonl once outcomes accumulate.
#
# The Growing feed carries no per-token mcap/holders/trades — only volume24Usd —
# so there is nothing else to gate on, and unlike noxa there is no graduationPct
# name-collision trap to sidestep. Measured 2026-07-23 the young end of the board
# (coins <24h) sat almost entirely under $1K, with a clean gap up to the one real
# mover (~$13K). $5K sits in that gap: above the sub-$1K noise, below the mover.
BAR = {"vol": 5_000.0}

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
    """One potato.fm GET -> parsed JSON, or None. Never raises into the loop.

    potato.fm is an unaudited demo MVP: /api/tokens occasionally 502s or times
    out while its scan cache is cold. Folding every failure to None means one bad
    poll is skipped and the next one recovers — the same shape as noxa's get()."""
    try:
        req = urllib.request.Request(path, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def fetch_growing(limit=100):
    """The Growing board rows (creations), or None on any failure.

    None (fetch failed) is kept distinct from [] (empty board) so the caller can
    decide whether to seed — the same distinction the trench scanners draw."""
    d = get(f"{API}/tokens")
    if not isinstance(d, dict) or d.get("unavailable"):
        return None
    items = d.get("creations")
    if not isinstance(items, list) or not health.is_record_list(items):
        return None
    return items[:limit]


def fetch_ancient(limit=100):
    """The Ancients rows (matured tokens), or None on any failure."""
    d = get(f"{API}/ancient")
    if not isinstance(d, dict) or d.get("unavailable"):
        return None
    items = d.get("tokens")
    if not isinstance(items, list) or not health.is_record_list(items):
        return None
    return items[:limit]


def map_growing(r):
    """A /api/tokens `creations` row -> the internal item shape.

    Socials are inline here (website/twitter/telegram), so an EARLY alert needs
    no per-token detail fetch. No mcap/holders/price/trades in this feed — the
    site derives market cap from the V3 pool over RPC, which this scanner does
    not do (see module docstring). volume24Usd is the only traction field."""
    addr = (r.get("token") or "").lower()
    return {
        "address": addr,
        "symbol": r.get("symbol"),
        "name": r.get("name"),
        "vol24h": fnum(r, "volume24Usd"),
        "created_ts": r.get("timestamp") or 0,
        "deployer": (r.get("creator") or "").lower(),
        "pool": (r.get("pool") or "").lower(),
        "pad": (r.get("pad") or "").lower(),
        "kind": r.get("kind") or "direct",
        "twitter": r.get("twitter") or None,
        "telegram": r.get("telegram") or None,
        "website": r.get("website") or None,
        # Growing rows carry no per-token mcap/liquidity:
        "mcap": None,
        "liq": None,
    }


def map_ancient(r):
    """A /api/ancient `tokens` row -> the internal item shape.

    Richer than a Growing row: fdvUsd (the baseline mcap), liquidityUsd and
    volume24Usd are all server-computed here. No socials/creator/timestamp/kind
    on this feed, so a GRAD alert shows fdv/liq/vol rather than social pros."""
    addr = (r.get("address") or "").lower()
    return {
        "address": addr,
        "symbol": r.get("symbol"),
        "name": r.get("name"),
        "vol24h": fnum(r, "volume24Usd"),
        "mcap": r.get("fdvUsd"),
        "liq": r.get("liquidityUsd"),
        "pool": (r.get("tradePool") or "").lower(),
        "has_weth_pool": bool(r.get("hasWethPool")),
        "created_ts": 0,
        "kind": "ancient",
        "twitter": None, "telegram": None, "website": None,
    }


def is_test(it):
    """Obvious placeholder launches the pad's own docs/test flow leave behind
    (name or symbol literally "test"). Kept out of alerts; harmless to skip."""
    return (str(it.get("name") or "").strip().lower() == "test"
            or str(it.get("symbol") or "").strip().lower() == "test")


def age_min(it, now):
    ts = it.get("created_ts") or 0
    return (now - ts) / 60 if ts > 1_000_000_000 else None


def passes_bar(it, args, now):
    """The EARLY predicate. Volume + age only — the Growing feed carries no
    holders/mcap/honeypot signal to gate on (see module docstring). Test-token
    placeholders never pass."""
    if is_test(it):
        return False
    am = age_min(it, now)
    return ((am is None or am <= args.max_age_h * 60)
            and it["vol24h"] >= args.min_vol)


def score_item(it, base):
    """Heuristic 0-100 from the potato.fm row. Deliberately thin: this feed has
    volume + socials (+ fdv/liq for grads) and none of the forensic fields the
    trench scanners score, so there is little here to fake a high score with —
    and correspondingly few red-flag cons. Refit against tracker outcomes once
    history accumulates."""
    s = float(base)
    v = it["vol24h"]
    if v >= 100_000:
        s += 6
    elif v >= 20_000:
        s += 4
    elif v >= 5_000:
        s += 2
    if it.get("mcap") and float(it["mcap"]) >= 100_000:   # grads: real size
        s += 3
    if it.get("liq") and float(it["liq"]) >= 50_000:
        s += 2
    if it.get("twitter") or it.get("telegram"):
        s += 3
    if it.get("website"):
        s += 2
    return alertfmt.clamp(s)


def links(addr):
    return [[("📈 GMGN", f"https://gmgn.ai/robinhood/token/{addr}"),
             ("📊 DexScreener", f"https://dexscreener.com/robinhood/{addr}")],
            [("🥔 potato", f"{COIN}{addr}"),
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
    if it.get("kind") != "ancient" and not (it.get("twitter") or it.get("telegram") or it.get("website")):
        cons.append("no socials")

    am = age_min(it, now)
    agebit = (f"{am/60:.1f}h" if am and am >= 60 else (f"{am:.0f}m" if am else "?"))
    stats = [f"💰 mc {human(it.get('mcap'))} · 💧 liq {human(it.get('liq'))} "
             f"· 📈 vol24h {human(it['vol24h'])} · ⏱️ {agebit}"]
    addr = it["address"]
    body = alertfmt.compose(score, tier_emoji, tier, sym, f"{EMOJI} {NAME}", "ROBINHOOD",
                            pros, cons, stats,
                            f'<a href="{BLOCKSCOUT}{addr}">{addr[:12]}…</a>')
    return score, body


def track_dict(addr):
    # potato coins are ordinary Uniswap V3 tokens on robinhood chain that GMGN
    # indexes, so the outcome prices via the shared gmgn snap — no potato method
    # in tracker/track.py. (noxa needs its own snap because V2 is gmgn-invisible.)
    return {"method": "gmgn", "chainSlug": "robinhood", "address": addr}


def record_for(it, tier, score):
    return dict(platform=PLATFORM, chain="ROBINHOOD", tier=tier,
                symbol=str(it.get("symbol") or it["address"][:8]), token=it["address"],
                score=score, track=track_dict(it["address"]),
                price0=None, mcap0=it.get("mcap"), liq0=it.get("liq"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=30.0, help="poll (s)")
    ap.add_argument("--max-age-h", type=float, default=24.0, help="EARLY only for coins younger than this")
    ap.add_argument("--min-vol", type=float, default=BAR["vol"], help="volume_24h USD")
    ap.add_argument("--limit", type=int, default=100, help="rows per feed")
    ap.add_argument("--once", action="store_true", help="one pass, print candidates vs bar, exit")
    ap.add_argument("--dry-run", action="store_true")
    controls.add_args(ap)
    args = ap.parse_args()

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)

    if args.once:
        rows = fetch_growing(args.limit) or []
        now = time.time()
        print(f"### /api/tokens (Growing): {len(rows)}")
        for r in rows:
            it = map_growing(r)
            am = age_min(it, now)
            print(f"  {str(it.get('symbol'))[:14]:<14} {it['kind']:<6} "
                  f"vol24h={human(it['vol24h']):>8} "
                  f"soc={'Y' if (it.get('twitter') or it.get('telegram') or it.get('website')) else ' '} "
                  f"age={f'{am:.0f}m' if am else '?':>6} "
                  f"{'BAR✓' if passes_bar(it, args, now) else ''}")
        anc = fetch_ancient(args.limit) or []
        print(f"### /api/ancient (Ancients): {len(anc)}")
        for r in anc:
            it = map_ancient(r)
            print(f"  {str(it.get('symbol'))[:14]:<14} fdv={human(it.get('mcap')):>8} "
                  f"liq={human(it.get('liq')):>8} vol24h={human(it['vol24h']):>8}")
        return

    print(f"{NAME} scanner (potato.fm, robinhood)  "
          f"bar: vol24h>=${args.min_vol:.0f} & age<={args.max_age_h:.0f}h  "
          f"-> {'DRY-RUN' if dry else f'Telegram {chat_id}'}", flush=True)

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
    seen_new = set()     # addresses already registered from the Growing feed
    early_sent = set()
    grad_sent = set()
    seeded = set()       # feeds that had one successful poll (silent seed pass)

    def sample_control(now, pool):
        """One Growing coin we evaluated and passed over becomes a control (#9).

        Drawn from the sub-bar coins with a measurable baseline — here that means
        volume24Usd > 0 (a coin that has traded has a GMGN price to snapshot; a
        just-minted $0-volume coin has no t0 to measure a return from and would
        spend a control slot on an unmeasurable row). This is the potato analog
        of noxa's mcap>0 gate — potato has no per-token mcap, but volume>0 is the
        same "has a baseline" test. See docs/shadow-control-sampling.md."""
        picked = sampler.choose(now, pool, key=lambda x: x["address"])
        if picked is None:
            return
        addr = picked["address"]
        log_event("control", addr=addr, sym=picked.get("symbol"),
                  vol=picked["vol24h"], pad_kind=picked.get("kind"))
        outcomes.record_control(PLATFORM, "ROBINHOOD",
                                str(picked.get("symbol") or addr[:8]), addr,
                                track_dict(addr))

    def handle_grad(it, now, first):
        addr = it["address"]
        if not addr or addr in grad_sent:
            return
        grad_sent.add(addr)
        if first:
            return                 # backlog: seed silently
        score, body = build_alert("🚀", "POTATO GRAD", 50, it, [
            "🚀 matured — live on a Uniswap V3 WETH pool",
        ], now)
        log_event("grad_alert", addr=addr, sym=it.get("symbol"), score=score,
                  mc=it.get("mcap"), liq=it.get("liq"), vol=it["vol24h"])
        dispatch(body, f"POTATO GRAD {it.get('symbol')}", buttons=links(addr),
                 record=record_for(it, "POTATO GRAD", score))

    def handle_early(it, now, first, pool):
        addr = it["address"]
        if not addr or addr in early_sent or addr in grad_sent:
            return
        if first:
            # Seed only the coins ALREADY over the bar — the strong backlog we
            # must not re-alert on restart. Sub-bar coins are left un-seeded on
            # purpose so a coin launched shortly before a restart can still alert
            # if it crosses the bar afterwards (a real crossing, not backlog).
            if passes_bar(it, args, now):
                early_sent.add(addr)
            return
        if not passes_bar(it, args, now):
            # Control population (#9): sub-bar coins we evaluated and passed over,
            # restricted to those with a measurable baseline (volume > 0).
            if not is_test(it) and it["vol24h"] > 0:
                pool.append(it)
            return
        early_sent.add(addr)
        score, body = build_alert("🥔", "POTATO EARLY", 42, it, [
            f"📈 vol24h {human(it['vol24h'])} · {it['kind']}"
            + (f" · {it['name']}" if it.get("name") else ""),
        ], now)
        log_event("early_alert", addr=addr, sym=it.get("symbol"), score=score,
                  vol=it["vol24h"], pad_kind=it.get("kind"), pad=it.get("pad"))
        dispatch(body, f"POTATO EARLY {it.get('symbol')}", buttons=links(addr),
                 record=record_for(it, "POTATO EARLY", score))

    def poll(now):
        grow_rows = fetch_growing(args.limit)
        anc_rows = fetch_ancient(args.limit)
        if grow_rows is None and anc_rows is None:
            print(f"[{time.strftime('%H:%M:%S')}] potato.fm fetch failed", flush=True)
            return
        pool = []   # sub-bar Growing coins this poll, for one control draw

        if grow_rows is not None:
            first = "grow" not in seeded
            for r in grow_rows:
                it = map_growing(r)
                if not it["address"]:
                    continue
                if it["address"] not in seen_new:
                    seen_new.add(it["address"])
                    if not first:
                        log_event("launch", addr=it["address"], sym=it.get("symbol"),
                                  deployer=it.get("deployer"), pad_kind=it.get("kind"),
                                  pad=it.get("pad"))
                handle_early(it, now, first, pool)
            if not first:
                sample_control(now, pool)
            seeded.add("grow")

        if anc_rows is not None:
            first = "ancient" not in seeded
            for r in anc_rows:
                it = map_ancient(r)
                if not it["address"]:
                    continue
                handle_grad(it, now, first)
            seeded.add("ancient")

        health.touch(HEARTBEAT, NAME, now=now,
                     detail={"growing": len(grow_rows or []), "ancient": len(anc_rows or [])})

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
