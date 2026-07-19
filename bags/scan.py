"""GMGN Trenches scanner — Robinhood-chain launchpads the other scanners
don't cover: bags, bankr, noxa, dyorswap, and virtuals-on-robinhood
(virtuals/scan.py watches the app.virtuals.io API, which is BASE/SOLANA only).

Discovered 2026-07-18 while testing the GMGN Agent API: the robinhood
trending/trenches feeds surfaced coins from launchpads none of our six
source-level scanners see (e.g. RobinHub on `bags` at $157K mcap, 414
holders). Rather than reverse-engineer four more platforms, this scanner
rides GMGN's own launchpad-native Trenches board (see pons/gmgn.py):

    new_creation   -> cohort registration (logged, no alert)
    pump           -> 🐣 TRENCH EARLY   young coin crossing the traction bar
    completed      -> 🚀 TRENCH GRAD    newly bonded/graduated coin

Every item arrives pre-enriched (~118 fields): holders, progress, vol,
smart_degen/renowned counts, bot/rat/insider rates, honeypot + taxes, even
X follower counts — so the traction bar and the red-flag cons are all
computable from one POST every --interval seconds (no RPC needed).

The first successful poll of each section only SEEDS the seen-sets (no
backlog spam on restart — same pattern as the other scanners). All launches,
alerts and drops are logged to data/events.jsonl to refit the v1 bars once
outcomes accumulate. Alerts record track method "gmgn" so tracker/track.py
prices them via the same API.

Detect + rank + alert only. It never trades.

Usage:
    python3 bags/scan.py --dry-run          # print alerts, no Telegram
    python3 bags/scan.py --once             # one pass (candidates + bars), exit
    python3 bags/scan.py                    # live -> Telegram (pons/.env creds)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pons"))   # telegram + alertfmt + gmgn + outcomes
import alertfmt  # noqa: E402
import gmgn  # noqa: E402
import outcomes  # noqa: E402
import telegram  # noqa: E402

DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

# launchpad_platform request keys for GMGN trenches (allow-list; empty = nothing).
# pons / flap / flap_stocks are EXCLUDED on purpose — those launchpads are already
# covered at source level by pons/ and flap/, which see launches minutes earlier.
PADS = ["bags", "bankr", "noxa", "dyorswap", "virtuals_v2"]

PAD_EMOJI = {"bags": "👜", "bankr": "🏦", "noxa": "🌀", "dyorswap": "🔄", "virtuals": "🤖"}
BLOCKSCOUT = "https://robinhoodchain.blockscout.com/token/"


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


def age_min(it, now):
    ts = it.get("created_timestamp") or 0
    return (now - ts) / 60 if ts > 1_000_000_000 else None


def pad_label(it):
    pad = it.get("launchpad") or "?"
    return f"{PAD_EMOJI.get(pad, '📦')} {pad}"


def links(it):
    addr = it["address"]
    rows = [[("📈 GMGN", f"https://gmgn.ai/robinhood/token/{addr}"),
             ("📊 DexScreener", f"https://dexscreener.com/robinhood/{addr}")],
            [("🔗 Scan", f"{BLOCKSCOUT}{addr}")]]
    tw = it.get("twitter_handle") or it.get("twitter")
    if tw:
        rows.insert(0, [("🐦 X account", f"https://x.com/{tw}")])
    return rows


def score_item(it, base):
    """Heuristic 0-100 from trenches enrichment. v1 judgment calls — refit from
    events.jsonl + tracker outcomes once history accumulates."""
    s = float(base)
    s += min(fnum(it, "smart_degen_count") * 2, 12)      # cross-platform smart money
    s += min(fnum(it, "renowned_count"), 8)              # KOL / renowned holders
    if it.get("has_at_least_one_social"):
        s += 3
    if fnum(it, "x_user_follower") >= 100:
        s += 4
    if it.get("website"):
        s += 2
    if fnum(it, "net_buy_24h") > 0:
        s += 4
    prog = fnum(it, "progress")
    if 0.40 <= prog <= 0.85:
        s += 4                                           # mid-climb sweet spot
    s -= 6 if fnum(it, "bot_degen_rate") >= 0.40 else 0
    s -= 6 if fnum(it, "rat_trader_amount_rate") >= 0.30 else 0
    s -= 8 if fnum(it, "top_10_holder_rate") >= 0.50 else 0
    s -= 4 if fnum(it, "suspected_insider_hold_rate") >= 0.10 else 0
    s -= 4 if fnum(it, "entrapment_ratio") >= 0.40 else 0
    s -= 5 if fnum(it, "creator_created_count") > 3 else 0
    return alertfmt.clamp(s)


def build_alert(tier_emoji, tier, base, it, lead_pros, now):
    score = score_item(it, base)
    sym = html.escape(str(it.get("symbol") or it["address"][:8]))
    pros = list(lead_pros)
    sm, rn = int(fnum(it, "smart_degen_count")), int(fnum(it, "renowned_count"))
    if sm or rn:
        pros.append(f"🧬 GMGN smart <b>{sm}</b> · renowned {rn}")
    socbits = []
    if it.get("twitter_handle") or it.get("twitter"):
        f = int(fnum(it, "x_user_follower"))
        socbits.append("🐦 X" + (f" ({f} fo)" if f else ""))
    if it.get("website"):
        socbits.append("🌐 web")
    if it.get("telegram"):
        socbits.append("💬 TG")
    if socbits:
        pros.append(" · ".join(socbits))

    cons = []
    if (it.get("is_honeypot") or "").lower() == "yes":
        cons.append("⛔ honeypot flag")
    tax = fnum(it, "total_sell_tax")
    if tax > 0.05:
        cons.append(f"sell tax {tax*100:.0f}%")
    if fnum(it, "top_10_holder_rate") >= 0.50:
        cons.append(f"top10 hold {fnum(it, 'top_10_holder_rate')*100:.0f}%")
    if fnum(it, "bot_degen_rate") >= 0.40:
        cons.append(f"bots {fnum(it, 'bot_degen_rate')*100:.0f}%")
    if fnum(it, "rat_trader_amount_rate") >= 0.30:
        cons.append(f"rat traders {fnum(it, 'rat_trader_amount_rate')*100:.0f}%")
    if fnum(it, "suspected_insider_hold_rate") >= 0.10:
        cons.append(f"insiders {fnum(it, 'suspected_insider_hold_rate')*100:.0f}%")
    if fnum(it, "creator_created_count") > 3:
        cons.append(f"serial creator x{int(fnum(it, 'creator_created_count'))}")
    if not it.get("has_at_least_one_social"):
        cons.append("no socials")

    am = age_min(it, now)
    stats = [f"💰 mc {human(it.get('usd_market_cap') or it.get('market_cap'))} "
             f"· 👥 {int(fnum(it, 'holder_count'))} holders · 💧 {human(it.get('liquidity'))} "
             f"· ⏱️ {f'{am/60:.1f}h' if am and am >= 60 else (f'{am:.0f}m' if am else '?')}"]
    addr = it["address"]
    body = alertfmt.compose(score, tier_emoji, tier, sym, pad_label(it), "ROBINHOOD",
                            pros, cons, stats,
                            f'<a href="{BLOCKSCOUT}{addr}">{addr[:12]}…</a>')
    return score, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=30.0, help="trenches poll (s)")
    # v1 traction bar (EARLY tier) — refit from data/events.jsonl once outcomes exist.
    ap.add_argument("--max-age-h", type=float, default=24.0, help="EARLY only for coins younger than this")
    ap.add_argument("--min-holders", type=int, default=25)
    ap.add_argument("--min-vol", type=float, default=1000.0, help="volume_24h USD")
    ap.add_argument("--min-progress", type=float, default=0.25, help="curve progress 0-1")
    ap.add_argument("--max-sell-tax", type=float, default=0.05, help="honeypot gate (ratio)")
    ap.add_argument("--pads", default=",".join(PADS),
                    help="comma-separated launchpad_platform keys to watch")
    # TRENCH BURST shadow experiment (redesign-v2 P2): the flap goldmine's
    # mechanic is a first-minutes distinct-buyer burst. Its twin here is holder
    # VELOCITY from the trenches feed we already poll. Recorded silently into
    # the tracker (no Telegram) until outcomes prove the bar.
    ap.add_argument("--burst-gain", type=int, default=25,
                    help="holders gained within --burst-window to shadow-record (0=off)")
    ap.add_argument("--burst-window", type=float, default=600.0, help="seconds")
    ap.add_argument("--burst-max-age-m", type=float, default=60.0,
                    help="only coins younger than this (minutes)")
    ap.add_argument("--once", action="store_true", help="one pass, print candidates, exit")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    pads = [p.strip() for p in args.pads.split(",") if p.strip()]

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)
    if not gmgn.api_key():
        print("no GMGN_API_KEY configured (~/.config/gmgn/.env) — cannot run", flush=True)
        sys.exit(1)
    print(f"trench scanner (GMGN, robinhood)  pads={','.join(pads)}  "
          f"bar: holders>={args.min_holders} & vol24h>=${args.min_vol:.0f} & prog>={args.min_progress*100:.0f}% "
          f"& age<={args.max_age_h:.0f}h & sellTax<={args.max_sell_tax*100:.0f}%  "
          f"-> {'DRY-RUN' if dry else f'Telegram {chat_id}'}", flush=True)

    def dispatch(text, label, buttons=None, record=None):
        stamp = time.strftime("%H:%M:%S")
        if dry:
            print(f"[{stamp}] DRY {label}\n" + text, flush=True)
            return
        ok, info = telegram.send(text, token_tg, chat_id, buttons=buttons)
        if record and ok:
            record["tg"] = {"msg_id": info if isinstance(info, int) else None,
                            "text": text, "buttons": buttons}   # for AI edit-in-place
            outcomes.record_alert(**record)   # only record alerts that actually sent
        print(f"[{stamp}] {'sent -> ' + label if ok else 'send FAILED (' + label + '): ' + info}", flush=True)

    seen_new = set()      # addresses already registered from new_creation
    early_sent = set()
    grad_sent = set()
    seeded = set()        # section names that had one successful poll (seed pass)
    hol_hist = {}         # addr -> [(ts, holders)] for burst velocity
    burst_sent = set()

    def record_for(it, tier, score):
        return dict(platform=it.get("launchpad") or "trench", chain="ROBINHOOD", tier=tier,
                    symbol=str(it.get("symbol") or it["address"][:8]), token=it["address"],
                    score=score,
                    track={"method": "gmgn", "chainSlug": "robinhood", "address": it["address"]},
                    mcap0=it.get("usd_market_cap") or it.get("market_cap"),
                    liq0=it.get("liquidity"))

    def poll(now):
        d = gmgn.trenches("robinhood", pads, limit=50)
        if not d:
            print(f"[{time.strftime('%H:%M:%S')}] trenches fetch failed", flush=True)
            return
        # response section for near_completion is named "pump"
        for sec in ("new_creation", "pump", "completed"):
            items = d.get(sec)
            if not isinstance(items, list):
                continue
            first = sec not in seeded
            for it in items:
                addr = (it.get("address") or "").lower()
                if not addr:
                    continue
                it["address"] = addr

                if sec in ("new_creation", "pump") and args.burst_gain:
                    h_now = int(fnum(it, "holder_count"))
                    hist = hol_hist.setdefault(addr, [])
                    hist.append((now, h_now))
                    if len(hist) > 30:
                        del hist[:len(hist) - 30]
                    am_b = age_min(it, now)
                    pts = [hh for tt, hh in hist if now - tt <= args.burst_window]
                    if (addr not in burst_sent and addr not in early_sent
                            and am_b is not None and am_b <= args.burst_max_age_m
                            and pts and h_now - pts[0] >= args.burst_gain):
                        burst_sent.add(addr)
                        log_event("burst_shadow", addr=addr, pad=it.get("launchpad"),
                                  sym=it.get("symbol"), holders=h_now,
                                  gain=h_now - pts[0], age_m=round(am_b, 1))
                        # tracker-only: outcomes decide whether BURST becomes a
                        # live tier. Goes to controls.jsonl, not alerts.jsonl
                        # (#9) — it never reached Telegram, so every reader of
                        # the alert file counting it as an alert was wrong.
                        # Without this the migration would move the old BURST
                        # rows out and this line would write new ones straight
                        # back in.
                        outcomes.record_control(it.get("launchpad") or "trench", "ROBINHOOD",
                                                str(it.get("symbol") or addr[:8]), addr,
                                                {"method": "gmgn", "chainSlug": "robinhood",
                                                 "address": addr},
                                                tier="TRENCH BURST",
                                                mcap0=it.get("usd_market_cap") or it.get("market_cap"),
                                                liq0=it.get("liquidity"))

                if sec == "new_creation":
                    if addr in seen_new:
                        continue
                    seen_new.add(addr)
                    if not first:
                        log_event("launch", addr=addr, pad=it.get("launchpad"),
                                  sym=it.get("symbol"), creator=it.get("creator"))
                        print(f"[{time.strftime('%H:%M:%S')}] new {it.get('launchpad')} launch "
                              f"{it.get('symbol')} ({addr[:10]})", flush=True)
                    continue

                if sec == "pump":
                    if addr in early_sent or addr in grad_sent:
                        continue
                    if first:
                        early_sent.add(addr)   # backlog: seed silently
                        continue
                    am = age_min(it, now)
                    ok = ((am is None or am <= args.max_age_h * 60)
                          and fnum(it, "holder_count") >= args.min_holders
                          and fnum(it, "volume_24h") >= args.min_vol
                          and fnum(it, "progress") >= args.min_progress
                          and fnum(it, "total_sell_tax") <= args.max_sell_tax
                          and (it.get("is_honeypot") or "").lower() != "yes")
                    if not ok:
                        continue
                    early_sent.add(addr)
                    prog = fnum(it, "progress")
                    b, s_ = int(fnum(it, "buys_24h")), int(fnum(it, "sells_24h"))
                    score, body = build_alert("🐣", "TRENCH EARLY", 42, it, [
                        f"progress <b>{prog*100:.0f}%</b> · vol24h {human(it.get('volume_24h'))} "
                        f"· buys/sells {b}/{s_}" + (f" ({b/s_:.1f}x)" if s_ else ""),
                    ], now)
                    log_event("early_alert", addr=addr, pad=it.get("launchpad"),
                              sym=it.get("symbol"), score=score, prog=prog,
                              holders=it.get("holder_count"), vol=it.get("volume_24h"))
                    dispatch(body, f"TRENCH EARLY {it.get('symbol')}", buttons=links(it),
                             record=record_for(it, "TRENCH EARLY", score))
                    continue

                if sec == "completed":
                    if addr in grad_sent:
                        continue
                    grad_sent.add(addr)
                    if first:
                        continue               # backlog: seed silently
                    score, body = build_alert("🚀", "TRENCH GRAD", 50, it, [
                        "🚀 bonded — curve completed, trading on DEX",
                    ], now)
                    log_event("grad_alert", addr=addr, pad=it.get("launchpad"),
                              sym=it.get("symbol"), score=score,
                              holders=it.get("holder_count"), mc=it.get("usd_market_cap"))
                    dispatch(body, f"TRENCH GRAD {it.get('symbol')}", buttons=links(it),
                             record=record_for(it, "TRENCH GRAD", score))
            seeded.add(sec)
        for a_ in [a_ for a_, hh in hol_hist.items() if hh and now - hh[-1][0] > 7200]:
            del hol_hist[a_]

    if args.once:
        # diagnostic single pass: show every pump-section coin vs the bar
        d = gmgn.trenches("robinhood", pads, limit=50) or {}
        now = time.time()
        for sec in ("new_creation", "pump", "completed"):
            items = d.get(sec) or []
            print(f"### {sec}: {len(items)}")
            for it in items:
                am = age_min(it, now)
                print(f"  {it.get('launchpad'):>9} {str(it.get('symbol'))[:14]:<14} "
                      f"prog={fnum(it, 'progress')*100:5.1f}% holders={int(fnum(it, 'holder_count')):>4} "
                      f"vol24h={human(it.get('volume_24h')):>8} age={f'{am/60:.1f}h' if am else '?':>6} "
                      f"smart={int(fnum(it, 'smart_degen_count'))} tax={fnum(it, 'total_sell_tax')*100:.0f}%")
        return

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
