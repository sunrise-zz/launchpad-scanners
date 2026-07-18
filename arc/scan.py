"""Arc DEX Scan scanner — source-level launches on Arc Mainnet (chainId 5042).

arcdexscan.com is a token explorer + launchpad on Arc Mainnet
(RPC 5042.rpc.thirdweb.com, explorer arcscan.app). Its backend
`web-production-efe27.up.railway.app` is fully open (Railway, no Cloudflare,
plain urllib): a `/launches` feed gives the newest deploys and `/token/{addr}`
enriches with traders/volume/liquidity/socials.

This is a small, young chain (probed 2026-07-17: 225 tokens, ~$4K/24h volume) —
alerts are naturally rare, which is fine: it's a fresh ต้นน้ำ source where being
early matters most. Two tiers:

  🐣 ARC EARLY     new token crossing the traction bar (traders + liquidity +
                   buy pressure), gated on buy/sell balance
  🚀 ARC LAUNCHED  a tracked token's `launched` flag flips True (migrated from
                   the deploy pool to a full DEX pool — Arc's "graduation")

Endpoints (verified):
  /launches[?limit=N]                token, deployer, pool, name, symbol, createdAt
  /token/{addr}                      launched, verified, price, mcap, fdv,
                                     liquidityUsdc, volume5m/1h/24, buys24,
                                     sells24, traders24, txns24, socials, pools
  /tokens?sort=volume24&window=24h   full market board (momentum fallback)

Every launch/alert/expiry is logged to data/events.jsonl to refit the v1
heuristic bar once outcomes accumulate.

Detect + rank + alert only. It never trades.

Usage:
    python3 arc/scan.py --dry-run
    python3 arc/scan.py                # live -> Telegram (pons/.env creds)
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pons"))   # telegram + alertfmt
import alertfmt  # noqa: E402
import outcomes  # noqa: E402
import telegram  # noqa: E402

DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

BASE = "https://web-production-efe27.up.railway.app"
EXPLORER = "https://arcscan.app/token/"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Accept": "application/json", "Origin": "https://arcdexscan.com",
      "Referer": "https://arcdexscan.com/"}


def api_get(path, **params):
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    try:
        req = urllib.request.Request(f"{BASE}/{path}{qs}", headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        print(f"  api error {path}: {e}", flush=True)
        return None


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


def parse_created(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def socials_bits(d):
    return [(lbl, d.get(k)) for lbl, k in
            (("🐦 X", "twitter"), ("🌐 web", "website"), ("💬 TG", "telegram"), ("💬 DC", "discord"))
            if d.get(k)]


def links(addr, d):
    row = [("🔎 arcdexscan", f"https://arcdexscan.com/token/{addr}"),
           ("🔗 arcscan", f"{EXPLORER}{addr}")]
    tw = d.get("twitter")
    return [[("🐦 X account", tw)], row] if tw else [row]


def score_token(d, base, launched=False):
    """Heuristic 0-100 from the enrichment fields. Low-liquidity chain, so the
    bars are modest and weights are v1 judgment calls — refit from events.jsonl."""
    s = float(base)
    traders = fnum(d, "traders24")
    liq = fnum(d, "liquidityUsdc")
    buys, sells = fnum(d, "buys24"), fnum(d, "sells24")
    s += min(traders / 5, 12)                     # more distinct traders = broader
    s += 8 if liq >= 1000 else (4 if liq >= 250 else -6)
    if buys or sells:
        ratio = buys / sells if sells else buys
        s += 6 if ratio >= 3 else (4 if ratio >= 1.5 else (-6 if ratio < 1 else 0))
    s += min(len(socials_bits(d)), 3) * 3         # socials: strongest cross-chain signal
    s += 6 if d.get("verified") else 0
    s += 8 if launched else 0
    try:
        s += 4 if float(d.get("change1h") or 0) > 0 else 0
    except (TypeError, ValueError):
        pass
    return alertfmt.clamp(s)


def build_alert(tier_emoji, tier, base_score, addr, d, lead_pros, launched=False):
    score = score_token(d, base_score, launched)
    sym = html.escape(str(d.get("symbol") or addr[:8]))
    name = html.escape(str(d.get("name") or ""))
    pros = list(lead_pros)
    sb = socials_bits(d)
    if sb:
        pros.append(" · ".join(lbl for lbl, _ in sb))
    if d.get("verified"):
        pros.append("✅ verified")
    cons = []
    buys, sells = fnum(d, "buys24"), fnum(d, "sells24")
    if sells and buys / sells < 1:      # buys is a float; catches the pure-dump (buys=0) case too
        cons.append(f"more sells ({int(buys)}/{int(sells)})")
    if fnum(d, "liquidityUsdc") < 250:
        cons.append(f"thin liq {human(d.get('liquidityUsdc'))}")
    if not sb:
        cons.append("no socials")
    stats = [f"💰 mc {human(d.get('mcap'))} · liq {human(d.get('liquidityUsdc'))} "
             f"· vol24h {human(d.get('volume24'))} · 👥 {int(fnum(d, 'traders24'))} traders"]
    return score, alertfmt.compose(score, tier_emoji, tier, f"{sym} {name}".strip(),
                                   "🛰️ arcdexscan", "ARC", pros, cons, stats,
                                   f'<a href="{EXPLORER}{addr}">{addr[:12]}…</a>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=30.0, help="/launches poll (s)")
    ap.add_argument("--watch-hours", type=float, default=24.0)
    # v1 heuristic bar for a low-volume chain — refit from data/events.jsonl.
    ap.add_argument("--min-traders", type=int, default=8)
    ap.add_argument("--min-liq", type=float, default=200.0, help="liquidity USDC")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)
    print(f"arc scanner (Arc Mainnet 5042)  bar: traders>={args.min_traders} & liq>=${args.min_liq:.0f}  "
          f"-> {'DRY-RUN' if dry else f'Telegram {chat_id}'}", flush=True)

    def dispatch(text, label, buttons=None, record=None):
        stamp = time.strftime("%H:%M:%S")
        if dry:
            print(f"[{stamp}] DRY {label}\n" + text, flush=True)
            return
        ok, info = telegram.send(text, token_tg, chat_id, buttons=buttons)
        if record and ok:
            outcomes.record_alert(**record)   # only record alerts that actually sent
        print(f"[{stamp}] {'sent -> ' + label if ok else 'send FAILED (' + label + '): ' + info}", flush=True)

    tracked = {}       # addr -> {born, early_done, launched_done}
    start_ts = [0.0]   # only tokens born after this alert; set on first poll

    def poll_launches(now):
        d = api_get("launches", limit=30)
        for L in (d or {}).get("launches", []):
            addr = (L.get("token") or "").lower()
            if not addr or addr in tracked:
                continue
            born = parse_created(L.get("createdAt")) or now
            # the /launches feed churns (older tokens rotate back in), so gate on
            # birth time: anything already on-chain when we started is context,
            # not a fresh launch. Pre-start tokens are tracked but pre-marked done.
            pre = born < start_ts[0]
            tracked[addr] = {"born": born, "early_done": pre, "launched_done": pre,
                             "sym": L.get("symbol")}
            if not pre:
                log_event("launch", addr=addr, sym=L.get("symbol"), deployer=L.get("deployer"))
                print(f"[{time.strftime('%H:%M:%S')}] new launch {L.get('symbol')} ({addr[:10]})", flush=True)

    def scan_cohort(now):
        for addr in list(tracked):
            t = tracked[addr]
            if (now - t["born"]) > args.watch_hours * 3600:
                if not t["early_done"]:
                    log_event("expired", addr=addr, sym=t.get("sym"))
                del tracked[addr]
                continue
            if t["early_done"] and t["launched_done"]:
                continue
            d = api_get(f"token/{addr}")
            if not d:
                continue

            # 🚀 LAUNCHED tier — the `launched` flag flipped (Arc's graduation)
            if d.get("launched") and not t["launched_done"]:
                t["launched_done"] = True
                t["early_done"] = True     # LAUNCHED subsumes EARLY; don't fire a stale
                #                            EARLY for an already-graduated token later
                score, body = build_alert("🚀", "ARC LAUNCHED", 50, addr, d,
                                          ["🚀 migrated to full DEX pool"], launched=True)
                log_event("launched_alert", addr=addr, sym=d.get("symbol"), score=score)
                dispatch(body, f"ARC LAUNCHED {d.get('symbol')}", buttons=links(addr, d),
                         record=dict(platform="arcdexscan", chain="ARC", tier="ARC LAUNCHED",
                                     symbol=str(d.get("symbol") or addr[:8]), token=addr, score=score,
                                     track={"method": "arc", "address": addr},
                                     price0=d.get("price"), mcap0=d.get("mcap"), liq0=d.get("liquidityUsdc")))
                continue

            # 🐣 EARLY tier — traction bar
            if not t["early_done"]:
                traders = fnum(d, "traders24")
                liq = fnum(d, "liquidityUsdc")
                if traders < args.min_traders or liq < args.min_liq:
                    continue
                t["early_done"] = True
                age_m = (now - t["born"]) / 60
                buys, sells = int(fnum(d, "buys24")), int(fnum(d, "sells24"))
                score, body = build_alert("🐣", "ARC EARLY", 42, addr, d, [
                    f"👥 <b>{int(traders)}</b> traders · buys/sells {buys}/{sells} · ⏱️ {age_m:.0f}m",
                ])
                log_event("early_alert", addr=addr, sym=d.get("symbol"),
                          traders=traders, liq=liq, score=score)
                dispatch(body, f"ARC EARLY {d.get('symbol')}", buttons=links(addr, d),
                         record=dict(platform="arcdexscan", chain="ARC", tier="ARC EARLY",
                                     symbol=str(d.get("symbol") or addr[:8]), token=addr, score=score,
                                     track={"method": "arc", "address": addr},
                                     price0=d.get("price"), mcap0=d.get("mcap"), liq0=d.get("liquidityUsdc")))

    print("running… Ctrl-C to stop", flush=True)
    start_ts[0] = time.time()
    last = {"launch": 0.0, "cohort": 0.0}
    while True:
        try:
            now = time.time()
            if now - last["launch"] >= args.interval:
                poll_launches(now)
                last["launch"] = now
            if now - last["cohort"] >= 45:
                scan_cohort(now)
                last["cohort"] = now
            time.sleep(5)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  loop error: {e}", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
