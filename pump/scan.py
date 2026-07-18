"""pump.fun scanner — the biggest memecoin launchpad, on Solana.

pump.fun mints ~16 tokens/MINUTE (~23k/day), so alerting on creation is
impossible — 99%+ instant-rug. The signal is **traction inflection**: a young
coin climbing the bonding curve fast, gaining replies, heading for King of the
Hill / graduation. A future $17M coin (e.g. "Jimothy") crosses every bar on the
way up, so we watch the *actively-traded* feed and alert on the climb, not the
birth.

Data source — pump.fun v3 REST (open, needs a browser UA; Cloudflare fronts it):
  /coins?sort=last_trade_timestamp&order=DESC&limit=100   coins trading NOW
  /coins?sort=created_timestamp&order=DESC                the raw new feed (unused: too noisy)
  /coins/{mint}                                           full detail (tracker uses this)

Rich per-coin fields we score on: usd_market_cap, reply_count (community),
ath_market_cap (still climbing vs dumping), king_of_the_hill_timestamp,
complete (graduated), created_timestamp, twitter, nsfw, curve reserves.

Alert tiers (chain ⛓ SOLANA, platform 💊 pump.fun):
  🐣 PUMP EARLY      young on-curve coin crossing the mcap bar with positive
                     mcap velocity (climbing), scored on replies / ATH / KOTH
  🚀 PUMP GRADUATING curve near-complete (approaching ~$69k) or `complete` flips
                     — it made it off the curve to pumpswap/Raydium

Bars are v1 heuristics; every alert is recorded via pons/outcomes.py and the
tracker follows it, so thresholds can be refit from real outcomes.

Detect + rank + alert only. It never trades.

Usage:
    python3 pump/scan.py --dry-run
    python3 pump/scan.py                 # live -> Telegram (pons/.env creds)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pons"))   # telegram + alertfmt + outcomes
import alertfmt  # noqa: E402
import gmgn  # noqa: E402
import outcomes  # noqa: E402
import telegram  # noqa: E402

DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

API = "https://frontend-api-v3.pump.fun"
PUMP_URL = "https://pump.fun/coin/"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Accept": "application/json"}
GRAD_MCAP = 69_000.0        # approx bonding-curve completion market cap (USD)


def api_get(path):
    try:
        req = urllib.request.Request(f"{API}/{path}", headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        print(f"  api error {path[:40]}: {e}", flush=True)
        return None


def log_event(kind, **kw):
    try:
        with open(os.path.join(DATA, "events.jsonl"), "a") as f:
            f.write(json.dumps({"t": time.time(), "kind": kind, **kw}) + "\n")
    except Exception:  # noqa: BLE001
        pass


def human(x, unit="$"):
    if x is None:
        return "?"
    x = float(x)
    if x >= 1_000_000:
        return f"{unit}{x/1e6:.1f}M"
    if x >= 1_000:
        return f"{unit}{x/1e3:.1f}K"
    return f"{unit}{x:.0f}"


def progress(c):
    return 100.0 * (c.get("usd_market_cap") or 0) / GRAD_MCAP


def links(mint, c):
    rows = [
        [("💊 pump.fun", f"{PUMP_URL}{mint}"),
         ("📈 DexScreener", f"https://dexscreener.com/solana/{mint}")],
        [("🔎 GMGN", f"https://gmgn.ai/sol/token/{mint}"),
         ("🔗 Solscan", f"https://solscan.io/token/{mint}")],
    ]
    tw = c.get("twitter")
    if tw:
        rows.insert(0, [("🐦 X account", tw)])
    return rows


class Coin:
    __slots__ = ("mint", "born", "hist", "early_done", "grad_done", "sym")

    def __init__(self, mint, born, sym):
        self.mint = mint
        self.born = born
        self.hist = []      # [(t, usd_mcap)]
        self.early_done = False
        self.grad_done = False
        self.sym = sym

    def push(self, now, mcap):
        self.hist.append((now, mcap))
        if len(self.hist) > 12:
            self.hist = self.hist[-12:]

    def velocity(self):
        """USD market-cap growth per minute over the tracked window."""
        if len(self.hist) < 2:
            return 0.0
        (t0, m0), (t1, m1) = self.hist[0], self.hist[-1]
        dt = (t1 - t0) / 60
        return (m1 - m0) / dt if dt > 0 else 0.0


def score_coin(c, mcap, replies, ath, koth, twitter, nsfw, vel, grad=False):
    """Heuristic 0-100. Base 45 (crossed the bar). Climb quality, community and
    momentum push it; dumping-from-ATH and nsfw pull it down. v1 weights."""
    s = 55.0 if grad else 45.0
    s += 10 if mcap >= 40_000 else (6 if mcap >= 25_000 else 0)
    s += min(vel / 1000, 12)                      # $1k/min of climb ≈ +1, capped
    s += min(replies, 30) * 0.4                    # community forming
    if ath and mcap >= 0.9 * ath:
        s += 6                                     # still at/near its peak (climbing)
    elif ath and mcap < 0.5 * ath:
        s -= 10                                    # dumped >50% from peak
    s += 8 if koth else 0                          # King of the Hill
    s += 5 if twitter else 0
    s -= 5 if nsfw else 0
    return alertfmt.clamp(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=20.0, help="live-trade feed poll (s)")
    ap.add_argument("--watch-hours", type=float, default=6.0)
    # v1 bar for a 23k/day firehose. Raised $20k→$35k on 2026-07-18 to cut volume
    # (~240/day EARLY was too noisy while unproven); EARLY also now needs a
    # community/quality signal (replies or KOTH) unless mcap is already high.
    ap.add_argument("--min-mcap", type=float, default=35_000.0, help="EARLY mcap bar (USD)")
    ap.add_argument("--strong-mcap", type=float, default=50_000.0,
                    help="mcap above which EARLY fires even without replies/KOTH")
    ap.add_argument("--near", type=float, default=80.0, help="GRADUATING at this %% of ~$69k")
    # bundle gate: $FREE hit $100k mc "graduating" with 4 holders (one operator
    # bought the whole curve). GMGN holder count is fetched pre-send; when known
    # and below this floor the alert is suppressed. GMGN-down -> no gate.
    ap.add_argument("--min-holders", type=int, default=20,
                    help="skip alerts when GMGN holder count is below this (bundled launches)")
    ap.add_argument("--include-nsfw", action="store_true", default=False)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)
    print(f"pump.fun scanner  bar: mcap>=${args.min_mcap:.0f} & climbing & (replies|KOTH|${args.strong_mcap:.0f})  "
          f"grad>={args.near:.0f}% of ${GRAD_MCAP:.0f}  "
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

    coins = {}          # mint -> Coin (in-memory, for velocity)
    # persistent dedupe: a mint we've alerted stays suppressed across restarts and
    # across prune→re-add churn (the feed is sorted by last_trade, so an old coin
    # still being traded keeps reappearing — without this it re-alerted every poll).
    ALERTED = os.path.join(DATA, "alerted_mints.txt")
    SEED_MARK = os.path.join(DATA, ".seeded")
    alerted = set()
    if os.path.exists(ALERTED):
        alerted = {ln.strip() for ln in open(ALERTED) if ln.strip()}
    first_run = not os.path.exists(SEED_MARK)   # only the very first run seeds a backlog

    def mark_alerted(mint):
        alerted.add(mint)
        try:
            with open(ALERTED, "a") as f:
                f.write(mint + "\n")
        except Exception:  # noqa: BLE001
            pass

    def poll(now):
        nonlocal first_run
        nsfw = "true" if args.include_nsfw else "false"
        feed = api_get(f"coins?offset=0&limit=100&sort=last_trade_timestamp&order=DESC&includeNsfw={nsfw}")
        if feed is None:
            return
        for c in feed:
            mint = c.get("mint")
            if not mint:
                continue
            born = (c.get("created_timestamp") or now * 1000) / 1000
            if mint not in coins:
                coins[mint] = Coin(mint, born, c.get("symbol"))
                # only the first-EVER run suppresses the current backlog; restarts do
                # NOT, so an in-flight climber that appeared while we were down can still
                # alert (the `alerted` set stops anything we already fired).
                if first_run:
                    mark_alerted(mint)
            co = coins[mint]
            mcap = c.get("usd_market_cap") or 0
            co.push(now, mcap)
            ath = c.get("ath_market_cap") or 0
            complete = bool(c.get("complete"))
            age_ok = (now - co.born) <= args.watch_hours * 3600
            healthy = (not ath) or mcap >= 0.6 * ath   # at/near peak, i.e. climbing not dumping

            if mint in alerted:
                continue

            # 🚀 GRADUATING — young coin nearing curve completion (~$69k), still healthy.
            # age_ok is essential: an old coin stuck ≥80% but never completing would
            # otherwise re-alert every poll. We never alert on the `complete` flag.
            if (not complete and age_ok and progress(c) >= args.near and healthy):
                mark_alerted(mint)
                emit(dispatch, now, co, c, mcap, grad=True)
                continue

            # 🐣 EARLY — young, on-curve, crossed the mcap bar, climbing, near its ATH.
            # Quality gate: needs community (replies) or King-of-the-Hill unless it's
            # already a strong mcap — filters the low-conviction $35k climbers.
            replies = c.get("reply_count") or 0
            koth = bool(c.get("king_of_the_hill_timestamp"))
            quality = replies >= 1 or koth or mcap >= args.strong_mcap
            if (not complete and age_ok and quality
                    and mcap >= args.min_mcap and co.velocity() > 0 and healthy):
                mark_alerted(mint)
                emit(dispatch, now, co, c, mcap, grad=False)

        if first_run:
            try:
                open(SEED_MARK, "w").write(str(int(now)))
            except Exception:  # noqa: BLE001
                pass
            first_run = False
        # prune in-memory coins no longer worth tracking (dedupe lives on disk now)
        for mint in [m for m, co in coins.items() if (now - co.born) > (args.watch_hours + 2) * 3600]:
            del coins[mint]

    def emit(dispatch, now, co, c, mcap, grad):
        mint = co.mint
        replies = c.get("reply_count") or 0
        ath = c.get("ath_market_cap") or 0
        koth = bool(c.get("king_of_the_hill_timestamp"))
        tw = c.get("twitter")
        nsfw = bool(c.get("nsfw"))
        vel = co.velocity()
        sym = html.escape(str(c.get("symbol") or mint[:8]))
        name = html.escape(str(c.get("name") or ""))
        prog = progress(c)
        g = gmgn.snapshot("sol", mint)   # pre-send: display + bundle gate + record
        holders_n = (g or {}).get("holders")
        if holders_n is not None and holders_n < args.min_holders:
            print(f"[{time.strftime('%H:%M:%S')}] SKIP bundle {c.get('symbol')} "
                  f"({holders_n} holders at {human(mcap)} mc)", flush=True)
            log_event("skip_bundle", mint=mint, sym=c.get("symbol"),
                      holders=holders_n, mcap=mcap)
            return
        score = score_coin(co, mcap, replies, ath, koth, tw, nsfw, vel, grad=grad)

        age_m = (now - co.born) / 60
        pros = [f"💰 mc <b>{human(mcap)}</b> · 📈 +{human(vel)}/min · 📊 {prog:.0f}% to grad · ⏱️ {age_m:.0f}m"]
        bits = []
        if replies:
            bits.append(f"💬 {replies} replies")
        if ath:
            bits.append(f"ATH {human(ath)}")
        if koth:
            bits.append("👑 King of the Hill")
        if tw:
            bits.append("🐦 X")
        if bits:
            pros.append(" · ".join(bits))
        if g:
            gb = [f"👥 {g.get('holders', '?')} holders", f"smart {g.get('smart', 0)}"]
            if g.get("renowned"):
                gb.append(f"renowned {g['renowned']}")
            if g.get("bot_rate") is not None:
                gb.append(f"bots {g['bot_rate']*100:.0f}%")
            if g.get("bundler_w"):
                gb.append(f"bundlers {g['bundler_w']}")
            pros.append("🧬 GMGN " + " · ".join(gb))
        cons = []
        if g and (g.get("top10_rate") or 0) >= 0.5:
            cons.append(f"top10 hold {g['top10_rate']*100:.0f}%")
        if ath and mcap < 0.5 * ath:
            cons.append(f"down {100*(1-mcap/ath):.0f}% from ATH")
        if nsfw:
            cons.append("nsfw")
        if not tw:
            cons.append("no X")
        tier_emoji, tier = ("🚀", "PUMP GRADUATING") if grad else ("🐣", "PUMP EARLY")
        body = alertfmt.compose(score, tier_emoji, tier, f"{sym} {name}".strip(),
                                "💊 pump.fun", "SOLANA", pros, cons, [],
                                f'<a href="{PUMP_URL}{mint}">{mint[:12]}…</a>')
        log_event("grad_alert" if grad else "early_alert", mint=mint, sym=c.get("symbol"),
                  mcap=mcap, replies=replies, score=score)
        dispatch(body, f"{tier} {c.get('symbol')}", buttons=links(mint, c),
                 record=dict(platform="pump.fun", chain="SOLANA", tier=tier,
                             symbol=str(c.get("symbol") or mint[:8]), token=mint, score=score,
                             track={"method": "pumpfun", "address": mint},
                             mcap0=mcap, gmgn=g))

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
