"""flap.sh (Robinhood Chain) scanner — source-level detection of new launches.

flap.sh is by far the busiest launchpad on Robinhood Chain (~170 new tokens per
30 min observed 2026-07-17, vs a handful on pons). Two independent data paths:

  1. ON-CHAIN (primary, unblockable): every flap token address ends in `...7777`
     (vanity CREATE2 from the factory diamond 0xe9f7...197b). New launches are
     caught by polling Transfer-mint events (from 0x0) and filtering that suffix.
     Early activity per young token = Transfer events of the token itself
     (unique recipients ≈ holders, transfer count ≈ trades).

  2. API (enrichment, Cloudflare-guarded): https://batman.taxed.fun
       /v3/board                 trending (sortBy=marketcap|holders|liquidity)
       /v3/board/graduatinghot   near-graduation feed
       /v3/coin/{addr}           full detail: progress %, holders count, inline
                                 top-20 holder list, tax bps, isLowRisk (FAC),
                                 liquidity, volume24h, change5m/1h/4h/24h
     Cloudflare passes plain urllib (it fingerprints curl's TLS, not Python's),
     but be polite: enrichment is only fetched for candidates + one 60s feed
     poll. On repeated failures the scanner degrades to on-chain-only.

Alert tiers:
  🐣 EARLY      young token crossing the activity bar, passed tax/risk gates
  🔥 NEAR-GRAD  graduatinghot entry above --near progress, passed tax gates

Every launch and alert is appended to data/events.jsonl so thresholds can be
backtested properly once enough history accumulates (v1 gates are heuristics).

Detect + rank + alert only. It never trades.

Usage:
    python3 flap/scan.py --dry-run
    python3 flap/scan.py                # live -> Telegram (pons/.env creds)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "vlad"))   # rpc (QuickNode Robinhood)
sys.path.insert(0, os.path.join(HERE, "..", "pons"))   # telegram sender
import alertfmt  # noqa: E402
import gmgn  # noqa: E402
import outcomes  # noqa: E402
import telegram  # noqa: E402
from rpc import rpc  # noqa: E402

DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ZERO32 = "0x" + "0" * 64
SUFFIX = "7777"                 # flap vanity-address suffix
BLOCK_SEC = 0.1
MAX_SPAN = 2500                 # blocks per eth_getLogs call (413-safe)
ADDR_CHUNK = 50                 # tokens per cohort getLogs call

API = "https://batman.taxed.fun/v3"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Accept": "application/json", "Origin": "https://flap.sh", "Referer": "https://flap.sh/"}
BLOCKSCOUT = "https://robinhoodchain.blockscout.com/token/"

_api_fail = [0, 0.0]     # [consecutive failures, down-since ts] -> backoff


def api_get(path, params=""):
    """GET batman.taxed.fun with browser headers. Returns dict or None (never raises).
    After 5 straight failures the API is considered down for 10 min."""
    if _api_fail[0] >= 5:
        if time.time() - _api_fail[1] < 600:
            return None
        _api_fail[0] = 0     # 10 min served — probe again
    url = f"{API}/{path}?{params}&_refresh={time.strftime('%Y%m%d')}" if params else \
          f"{API}/{path}?_refresh={time.strftime('%Y%m%d')}"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        _api_fail[0] = 0
        return d
    except Exception:  # noqa: BLE001
        _api_fail[0] += 1
        if _api_fail[0] == 5:
            _api_fail[1] = time.time()
        return None


def log_event(kind, **kw):
    """Append to data/events.jsonl — raw material for a future proper backtest."""
    try:
        with open(os.path.join(DATA, "events.jsonl"), "a") as f:
            f.write(json.dumps({"t": time.time(), "kind": kind, **kw}) + "\n")
    except Exception:  # noqa: BLE001
        pass


_SYM = {}   # token -> resolved ERC20 symbol (cached)


def token_symbol(addr):
    """On-chain ERC20 symbol() — the fallback when the batman API is rate-limited
    (Cloudflare) and can't name the coin, so alerts don't degrade to a raw 0x…
    address. Decodes both ABI dynamic-string and legacy bytes32 returns. Cached."""
    if addr in _SYM:
        return _SYM[addr]
    sym = None
    try:
        r = rpc("eth_call", [{"to": addr, "data": "0x95d89b41"}, "latest"], timeout=8)
        if r and r != "0x":
            raw = bytes.fromhex(r[2:])
            if len(raw) >= 64:                       # dynamic string [offset][len][data]
                length = int.from_bytes(raw[32:64], "big")
                if 0 < length <= 64:
                    sym = raw[64:64 + length].decode("utf-8", "ignore").strip("\x00").strip() or None
            if not sym:                              # legacy bytes32
                sym = raw[:32].decode("utf-8", "ignore").strip("\x00").strip() or None
    except Exception:  # noqa: BLE001
        sym = None
    _SYM[addr] = sym
    return sym


def human_usd(x):
    if x is None:
        return "?"
    x = float(x)
    if x >= 1_000_000:
        return f"${x/1e6:.1f}M"
    if x >= 1_000:
        return f"${x/1e3:.0f}K"
    return f"${x:.0f}"


def tax_line(tax):
    """Trade-tax gate line. flap tokens can carry buy/sell tax; a fat sell tax is
    a soft honeypot — the single most flap-specific rug signal."""
    if not tax or not tax.get("hasTax"):
        return "🧾 tax: none ✅", 0, 0
    # `or 0`: the key can be present with a null value — .get(k, 0) would return
    # None and crash the f-string / the sell_bps > max comparison downstream.
    b, s = tax.get("buyTaxBps") or 0, tax.get("sellTaxBps") or 0
    warn = " ⚠️" if s > 500 or b > 500 else ""
    return f"🧾 tax: buy {b/100:.0f}% / sell {s/100:.0f}%{warn}", b, s


def concentration(detail):
    """Top-1/top-10 share of the inline holder list, excluding the curve/pool."""
    hl = detail.get("holders") or []
    pool = (detail.get("pool") or "").lower()
    bals = []
    for h in hl:
        a = (h.get("holder") or "").lower()
        if a and a != pool:
            try:
                bals.append(int(h.get("amount") or 0))
            except (TypeError, ValueError):
                pass
    bals.sort(reverse=True)
    if not bals:
        return None, None
    # shares are of the visible top-20 pot (the API only returns top-20), so the
    # figures are biased high — read them as "how lopsided is the whale table"
    tot = sum(bals)
    top1 = 100 * bals[0] / tot
    top10 = 100 * sum(bals[:10]) / tot
    return top1, top10


def links(token):
    return [[("🦇 flap", f"https://flap.sh/robinhood/{token}"),
             ("📈 DexScreener", f"https://dexscreener.com/robinhood/{token}")],
            [("🔎 GMGN", f"https://gmgn.ai/robinhood/token/{token}"),
             ("🔗 Scan", f"{BLOCKSCOUT}{token}")]]


def gmgn_line(g):
    """One pros line from the GMGN snapshot (fetched pre-send; flap's own batman
    API misses many brand-new coins entirely — GMGN indexes them in seconds)."""
    if not g:
        return None
    bits = [f"smart <b>{g.get('smart', 0)}</b>", f"renowned {g.get('renowned', 0)}"]
    if g.get("bot_rate") is not None:
        bits.append(f"bots {g['bot_rate']*100:.0f}%")
    soc = [b for b, on in (("🐦X", g.get("has_x")), ("🌐web", g.get("has_web")),
                           ("💬TG", g.get("has_tg"))) if on]
    if soc:
        bits.append(" ".join(soc))
    return "🧬 GMGN " + " · ".join(bits)


def wave_decision(sym, prior_same, g, max_repeats):
    """Same-name relaunch: farm spam or narrative wave? Returns
    (suppress: bool, pro: str|None, con: str|None).

    A farm can fake traction numbers every round but can't fake QUALITY:
    smart/renowned/whale wallet tags, a real X account, or a prior copy of the
    name that actually ran (we track every alerted copy's price). Any of those
    lets the coin through flagged as a wave — the 5th relaunch that whales
    finally play must NOT be suppressed. Count-only suppression applies to
    copies with zero quality signals (the RUDY profile: ~130 manufactured
    recipients, smart 0, renowned 0, no socials, every copy dead)."""
    if not prior_same:
        return False, None, None
    n = len(prior_same)
    gq = g or {}
    quality = []
    if (gq.get("smart") or 0) >= 1:
        quality.append(f"smart {gq['smart']}")
    if (gq.get("renowned") or 0) >= 1:
        quality.append(f"renowned {gq['renowned']}")
    if (gq.get("whale_w") or 0) >= 1:
        quality.append(f"whale {gq['whale_w']}")
    if gq.get("has_x"):
        quality.append("real X")
    if quality:
        return False, (f"🔁 wave #{n+1} + {' · '.join(quality)} "
                       f"(possible narrative winner)"), None
    # proven demand must come from the most RECENT copies — an old winner with
    # every later copy dead is a farm milking its first pump (OilRig: copy #1
    # +779%, waves 2-15 all dead, yet the any-prior-peak check re-opened the
    # name forever -> 16 alerts in a day). A wave that's actually hot has a
    # recent copy that ran (or quality signals above).
    recent = sorted(prior_same, key=lambda p: p.get("t", 0))[-2:]
    rets = [r for r in (outcomes.peak_return(p) for p in recent) if r is not None]
    best_recent = max(rets) if rets else None
    if best_recent is not None and best_recent >= 1.0:
        return False, (f"🔁 wave #{n+1} — recent {sym} copy peaked "
                       f"{best_recent*100:+.0f}% (wave still hot)"), None
    if n >= max_repeats:
        return True, None, None
    return False, None, f"⚠️ name relaunched x{n} in 24h, no quality signals (farm?)"


def gmgn_tax(addr):
    """Tax gate fallback via GMGN token_security when batman doesn't know the
    coin. Returns (line, buy_bps, sell_bps, known)."""
    sec = gmgn.token_security("robinhood", addr) or {}
    try:
        buy_bps = int(round(float(sec.get("buy_tax")) * 10000))
        sell_bps = int(round(float(sec.get("sell_tax")) * 10000))
    except (TypeError, ValueError):
        return "🧾 tax: ？ (both APIs unavailable — check before buying)", 0, 0, False
    if str(sec.get("is_honeypot")) == "1":
        return "⛔ GMGN honeypot flag", 10_000, 10_000, True   # force the tax gate to drop it
    return f"🧾 tax: buy {buy_bps/100:.0f}% / sell {sell_bps/100:.0f}% (GMGN)", buy_bps, sell_bps, True


class Tok:
    __slots__ = ("addr", "birth_block", "birth_ts", "recips", "transfers", "alerted", "shadowed", "dead")

    def __init__(self, addr, birth_block, birth_ts):
        self.addr = addr
        self.birth_block = birth_block
        self.birth_ts = birth_ts
        self.recips = set()
        self.transfers = 0
        self.alerted = False
        self.shadowed = False
        self.dead = False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--watch-secs", type=float, default=900.0,
                    help="how long a token stays in the early-watch cohort")
    # v1 heuristic bar. flap is the ONLY proven-profitable source in outcome
    # tracking (FLAP EARLY +53%→+113%, score-predictive), so on 2026-07-18 the bar
    # was LOWERED 120→80 to catch more of it — the 120-200 recips bucket returned
    # +190% median, and the score filters the weaker 80-120 range. Refit as the
    # 80-120 bucket accumulates outcome data.
    ap.add_argument("--min-recips", type=int, default=80,
                    help="unique transfer recipients within watch window to become a candidate")
    ap.add_argument("--min-transfers", type=int, default=150)
    ap.add_argument("--max-sell-tax", type=int, default=500,
                    help="drop candidates whose sell tax exceeds this (bps, default 5%%)")
    ap.add_argument("--max-buy-tax", type=int, default=500)
    # relaunch-farm gate: same NAME alerted repeatedly on different addresses
    # (RUDY x3 in 23 min, 2026-07-18). 2 = second copy still alerts (with a
    # warning con), third+ is suppressed.
    ap.add_argument("--max-name-repeats", type=int, default=2,
                    help="skip EARLY when this many same-name alerts already fired in 24h")
    # SHADOW experiment (redesign-v2 P2): GMGN ATH backtest says the 60-79
    # recips zone hits est-2x ~81% (n=135) and recips>=80-but-transfers<150
    # ~77% (n=97) — both currently discarded. Record them into the tracker
    # WITHOUT alerting so post-signal peaks (true entry basis) decide whether
    # the live bar drops. 0 = off.
    ap.add_argument("--shadow-min-recips", type=int, default=60,
                    help="silently track coins crossing this recips bar (bar research; 0=off)")
    ap.add_argument("--near", type=float, default=70.0,
                    help="graduatinghot progress %% for NEAR-GRAD alerts")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)
    print(f"flap scanner  bar: recips>={args.min_recips} & transfers>={args.min_transfers} "
          f"in {args.watch_secs/60:.0f}min & sellTax<={args.max_sell_tax}bps  near>={args.near}%  "
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

    toks = {}            # addr -> Tok
    # near-grad dedup is PERSISTED: the graduatinghot board holds the same ~20
    # coins for hours, so a memory-only set re-alerts every one of them after
    # every restart (OIL CAT went out 5x on 2026-07-18's deploy day).
    near_file = os.path.join(DATA, "neargrad_sent.txt")
    near_sent = {}       # addr -> ts
    if os.path.exists(near_file):
        for ln in open(near_file):
            a = ln.strip().lower()
            if a:
                near_sent[a] = 0.0

    def mark_near(addr):
        near_sent[addr] = time.time()
        try:
            with open(near_file, "a") as f:
                f.write(addr + "\n")
        except Exception:  # noqa: BLE001
            pass
    cursor = [int(rpc("eth_blockNumber", []), 16)]   # start at head: only future launches

    def poll_chain(now):
        """One pass: new mints + cohort transfer activity, chunk-safe."""
        head = int(rpc("eth_blockNumber", []), 16)
        if head <= cursor[0]:
            return
        frm = cursor[0] + 1
        # never let a stall (rpc outage) force a giant catch-up scan
        if head - frm > 10 * MAX_SPAN:
            frm = head - 10 * MAX_SPAN
        for a in range(frm, head + 1, MAX_SPAN):
            b = min(a + MAX_SPAN - 1, head)
            # 1. new flap tokens: mint events, vanity suffix
            for lg in rpc("eth_getLogs", [{"fromBlock": hex(a), "toBlock": hex(b),
                                           "topics": [TRANSFER, ZERO32]}], timeout=30):
                addr = lg["address"].lower()
                if addr.endswith(SUFFIX) and addr not in toks:
                    blk = int(lg["blockNumber"], 16)
                    toks[addr] = Tok(addr, blk, now - (head - blk) * BLOCK_SEC)
                    log_event("launch", addr=addr, block=blk)
                    print(f"[{time.strftime('%H:%M:%S')}] new flap token {addr}", flush=True)
            # 2. cohort activity. Rebuild `young` INSIDE the loop and AFTER the mint
            # scan so a token minted in THIS range is scanned for its own launch-burst
            # transfers in the same range — the earliest traction the bar measures,
            # which the old (pre-loop) snapshot silently dropped forever (cursor jumps
            # past these blocks and never revisits them).
            young = [t for t in toks.values() if not t.dead and (now - t.birth_ts) <= args.watch_secs]
            for i in range(0, len(young), ADDR_CHUNK):
                chunk = young[i:i + ADDR_CHUNK]
                logs = rpc("eth_getLogs", [{"address": [t.addr for t in chunk],
                                            "fromBlock": hex(a), "toBlock": hex(b),
                                            "topics": [TRANSFER]}], timeout=30)
                by_addr = defaultdict(list)
                for lg in logs:
                    by_addr[lg["address"].lower()].append(lg)
                for t in chunk:
                    for lg in by_addr.get(t.addr, ()):
                        t.transfers += 1
                        recip = "0x" + lg["topics"][2][-40:]
                        if recip != "0x" + "0" * 40:
                            t.recips.add(recip)
        cursor[0] = head

    def check_candidates(now):
        expired = []
        for t in toks.values():
            if t.alerted or t.dead:
                # prune finished tokens ~1h after birth: at flap's ~8k launches/day
                # the registry (and its recipient sets) would otherwise grow forever
                if now - t.birth_ts > 3600:
                    expired.append(t.addr)
                continue
            age = now - t.birth_ts
            if age > args.watch_secs:
                t.dead = True
                log_event("expired", addr=t.addr, recips=len(t.recips), transfers=t.transfers)
                continue
            live_ok = len(t.recips) >= args.min_recips and t.transfers >= args.min_transfers
            if (args.shadow_min_recips and not t.shadowed and not live_ok
                    and len(t.recips) >= args.shadow_min_recips):
                # tracker-only record: no Telegram, no dedup interference; the
                # coin can still promote to a live EARLY alert later.
                t.shadowed = True
                stier = ("FLAP SHADOW-XFER" if len(t.recips) >= args.min_recips
                         else "FLAP SHADOW-60")
                ssym = token_symbol(t.addr) or t.addr[:8]
                log_event("shadow", addr=t.addr, tier=stier,
                          recips=len(t.recips), transfers=t.transfers)
                outcomes.record_alert("flap.sh", "ROBINHOOD", stier, str(ssym), t.addr,
                                      None, {"method": "flap", "address": t.addr})
            if not live_ok:
                continue
            t.alerted = True   # one shot per token, decided before the API round-trip
            d = api_get(f"coin/{t.addr}") or {}
            g = gmgn.snapshot("robinhood", t.addr)   # display + record (GMGN indexes in seconds)
            tax_known = True
            if d:
                tl, buy_bps, sell_bps = tax_line(d.get("tax"))
            else:
                # batman doesn't know the coin (common for brand-new launches) —
                # run the tax/honeypot gate via GMGN instead of skipping it
                tl, buy_bps, sell_bps, tax_known = gmgn_tax(t.addr)
            if sell_bps > args.max_sell_tax or buy_bps > args.max_buy_tax:
                print(f"[{time.strftime('%H:%M:%S')}] SKIP high-tax {t.addr[:10]} "
                      f"(buy {buy_bps} / sell {sell_bps} bps)", flush=True)
                log_event("skip_tax", addr=t.addr, buy=buy_bps, sell=sell_bps)
                continue
            sym = d.get("symbol") or token_symbol(t.addr) or t.addr[:8]
            name = d.get("name") or ""
            prior_same = outcomes.recent_same_symbol("flap.sh", sym, t.addr)
            suppress, wave_pro, farm_con = wave_decision(sym, prior_same, g, args.max_name_repeats)
            if suppress:
                print(f"[{time.strftime('%H:%M:%S')}] SKIP relaunch-farm {sym} "
                      f"({len(prior_same)} same-name alerts in 24h, zero quality signals)", flush=True)
                log_event("skip_name_farm", addr=t.addr, sym=sym, prior=len(prior_same))
                continue
            top1, top10 = concentration(d) if d else (None, None)

            # heuristic score: base 45 (crossed the traction bar), extras shift.
            s = 45.0
            s += min(max(len(t.recips) - args.min_recips, 0) / 10, 15)   # traction beyond the bar
            s += min(t.transfers / 100, 8)
            s += 10 if d.get("isLowRisk") else 0              # platform FAC check
            hc = (d.get("holdersCount") if d else None) or (g or {}).get("holders")
            if tax_known:   # tax numbers from batman OR GMGN — same gate either way
                s += 8 if (buy_bps == 0 and sell_bps == 0) else (4 if sell_bps <= 200 else 0)
            else:
                s -= 10                                       # tax gate could not run
            s += 6 if (hc or 0) >= 100 else 0
            s -= 8 if (top1 or 0) >= 30 else 0
            score = alertfmt.clamp(s)

            pros = [f"⚡ <b>{len(t.recips)}</b> recipients · {t.transfers} transfers in {age/60:.0f}m"]
            if d:
                bits = [f"👥 {d.get('holdersCount') or '?'} holders"]
                if d.get("progress"):
                    bits.append(f"📊 {float(d['progress']):.0f}% to grad")
                if d.get("isLowRisk"):
                    bits.append("🛡️ FAC low-risk")
                pros.append(" · ".join(bits))
            elif g:
                bits = [f"👥 {g.get('holders') or '?'} holders"]
                if g.get("pad_progress"):
                    bits.append(f"📊 {g['pad_progress']*100:.0f}% to grad")
                pros.append(" · ".join(bits))
            gl = gmgn_line(g)
            if gl:
                pros.append(gl)
            if wave_pro:
                pros.append(wave_pro)

            cons = []
            if sell_bps or buy_bps:
                cons.append(f"tax buy {buy_bps/100:.0f}% / sell {sell_bps/100:.0f}%"
                            + ("" if d else " (GMGN)"))
            if not tax_known:
                cons.append("tax ？ (apis unavailable — check before buying)")
            if farm_con:
                cons.append(farm_con)
            if top1 is not None and top1 >= 30:
                cons.append(f"top wallet {top1:.0f}% of top-20 pot")
            elif g and (g.get("top10_rate") or 0) >= 0.5:
                cons.append(f"top10 hold {g['top10_rate']*100:.0f}% (GMGN)")

            stats = []
            if d:
                stats.append(f"💰 mc {human_usd(d.get('marketCap'))} · liq {human_usd(d.get('liquidity'))}"
                             f" · vol24h {human_usd(d.get('volume24h'))}")
            body = alertfmt.compose(score, "🐣", "FLAP EARLY",
                                    f"{html.escape(str(sym))} {html.escape(str(name))}".strip(),
                                    "🦇 flap.sh", "ROBINHOOD", pros, cons, stats,
                                    f'<a href="{BLOCKSCOUT}{t.addr}">{t.addr[:12]}…</a>')
            log_event("early_alert", addr=t.addr, recips=len(t.recips), transfers=t.transfers,
                      sym=sym, sell_bps=sell_bps, low_risk=bool(d.get("isLowRisk")))
            dispatch(body, f"FLAP EARLY {sym}", buttons=links(t.addr),
                     record=dict(platform="flap.sh", chain="ROBINHOOD", tier="FLAP EARLY",
                                 symbol=str(sym), token=t.addr, score=score,
                                 track={"method": "flap", "address": t.addr},
                                 price0=d.get("price") if d else None,
                                 mcap0=d.get("marketCap") if d else None,
                                 liq0=d.get("liquidity") if d else None,
                                 gmgn=g))
        for a in expired:
            del toks[a]

    def check_neargrad(now):
        d = api_get("board/graduatinghot", "limit=20")
        if not d:
            return
        for it in d.get("items", []):
            coin = it.get("coin") or {}
            addr = (coin.get("address") or "").lower()
            prog = float(it.get("progress") or 0)
            if not addr or prog < args.near or it.get("listed"):
                continue
            if addr in near_sent:      # once per token — graduatinghot holds ~20
                continue               # entries, re-firing every 10 min is spam
            tl, buy_bps, sell_bps = tax_line(it.get("tax"))
            if sell_bps > args.max_sell_tax or buy_bps > args.max_buy_tax:
                continue
            mark_near(addr)   # persisted — restarts must not re-alert the board
            sym = coin.get("symbol") or token_symbol(addr) or addr[:8]

            # heuristic score: base 40 (progress tier), momentum + safety shift it
            s = 40.0
            s += min(max(prog - 70, 0), 30) * 0.5
            s += 10 if it.get("isLowRisk") else 0
            s += 8 if not (it.get("tax") or {}).get("hasTax") else (4 if sell_bps <= 200 else 0)
            try:
                s += 6 if float(it.get("change1h") or 0) > 0 else 0
                s += 4 if float(it.get("change5m") or 0) > 0 else 0
            except ValueError:
                pass
            s += 5 if (it.get("holders") or 0) >= 100 else 0
            score = alertfmt.clamp(s)

            g = gmgn.snapshot("robinhood", addr)
            pros = [f"📊 <b>{prog:.0f}%</b> to grad · 👥 {it.get('holders') or '?'} holders"
                    + (" · 🛡️ FAC low-risk" if it.get("isLowRisk") else ""),
                    f"Δ 5m {it.get('change5m')}% · 1h {it.get('change1h')}% · vol24h {human_usd(it.get('volume24h'))}"]
            gl = gmgn_line(g)
            if gl:
                pros.append(gl)
            cons = []
            if sell_bps or buy_bps:
                cons.append(f"tax buy {buy_bps/100:.0f}% / sell {sell_bps/100:.0f}%")
            stats = [f"💰 mc {human_usd(it.get('marketCap'))} · liq {human_usd(it.get('liquidity'))}"]
            body = alertfmt.compose(score, "🔥", "FLAP NEAR-GRAD", html.escape(str(sym)),
                                    "🦇 flap.sh", "ROBINHOOD", pros, cons, stats,
                                    f'<a href="{BLOCKSCOUT}{addr}">{addr[:12]}…</a>')
            log_event("neargrad_alert", addr=addr, sym=sym, progress=prog)
            dispatch(body, f"FLAP NEAR-GRAD {sym}", buttons=links(addr),
                     record=dict(platform="flap.sh", chain="ROBINHOOD", tier="FLAP NEAR-GRAD",
                                 symbol=str(sym), token=addr, score=score,
                                 track={"method": "flap", "address": addr},
                                 mcap0=it.get("marketCap"), liq0=it.get("liquidity"),
                                 gmgn=g))

    print("running… Ctrl-C to stop", flush=True)
    last_grad = [0.0]
    while True:
        try:
            now = time.time()
            poll_chain(now)
            check_candidates(now)
            if now - last_grad[0] > 60:
                check_neargrad(now)
                last_grad[0] = now
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  loop error: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
