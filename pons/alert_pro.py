"""pons.family PRO scanner — multi-factor CONFIRMED alerts with insights.

Backtested on 94 graduations vs 1,500 controls (real base rate 0.54%):

    CONFIRMED rule (first 5 min, on-chain):
        rebuyers >= 6        wallets that bought 2+ times (conviction)
        net_weth >= 1.0      net ETH into the pool
        snipers <= 3         buys in the first 2s (bot-sniped launches fail)

    -> real-world precision ~30% (out-of-time test: 41%), recall ~43-84%,
       fires at median 44s after launch; graduation happens ~90 min later.

Pipeline per poll (~2s):
  1. /latest registers new launches (token, pool, launchBlock, deployer).
  2. For active coins (< 15 min old), incrementally pull Uniswap-V3 Swap logs
     from the coin's pool via RPC and update factor state.
  3. When the rule passes -> one 🎯 CONFIRMED Telegram alert with the factor
     breakdown (buyers, rebuyers, net ETH, snipers, smart-money hits, dev info).
  4. /recent-buys still powers 🔥 NEAR-GRAD (>=70% progress) as a second tier.

Detect + rank + alert only. It never trades.

Usage:
    python3 analysis/pons/alert_pro.py            # live -> Telegram (or dry-run without creds)
    python3 analysis/pons/alert_pro.py --dry-run
    python3 analysis/pons/alert_pro.py --rebuyers 8 --net 1.5   # stricter
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "vlad"))
import api  # noqa: E402
import telegram  # noqa: E402
from rpc import rpc, rpc_batch  # noqa: E402  (quiknode Robinhood mainnet)

DATA = os.path.join(HERE, "data")
BLOCK_SEC = 0.1
SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
WETH = "0x0bd7d308f8e1639fab988df18a8011f41eacad73"
ACTIVE_SECS = 15 * 60
BLOCKSCOUT = "https://robinhoodchain.blockscout.com/token/"


_SUPPLY = {}   # token -> total supply (constant, cached via on-chain call)


def total_supply(token):
    if token not in _SUPPLY:
        try:
            r = rpc("eth_call", [{"to": token, "data": "0x18160ddd"}, "latest"], timeout=10)
            _SUPPLY[token] = int(r, 16) / 1e18
        except Exception:  # noqa: BLE001
            _SUPPLY[token] = None
    return _SUPPLY[token]


def human_usd(x):
    if x is None:
        return "?"
    if x >= 1_000_000:
        return f"${x/1e6:.1f}M"
    if x >= 1_000:
        return f"${x/1e3:.0f}K"
    return f"${x:.0f}"


def age_str(launched_at, now):
    if not launched_at:
        return "?"
    s = now - launched_at
    return f"{s/3600:.1f}h" if s >= 3600 else f"{int(s//60)}m"


def glance(token, price, paired, pct, launched_at, now, ethusd):
    """One-line at-a-glance: market cap · liquidity · age · graduation progress."""
    sup = total_supply(token)
    mc = human_usd(price * sup) if (price and sup) else "?"
    liq = f"{paired:.2f} ETH" if paired else "?"
    liq_usd = f" ({human_usd(paired*ethusd)})" if (paired and ethusd) else ""
    prog = f"{pct:.0f}% to grad" if pct is not None else "pre-curve"
    return f"💰 mc {mc} · 💧 liq {liq}{liq_usd} · ⏱️ {age_str(launched_at, now)} · 📊 {prog}"


def links(token, pool=None):
    """Inline-keyboard rows for a coin. DexScreener + pons are the ones that
    actually have Robinhood Chain data; GMGN is included on request but does not
    index this chain yet, so it may show no data."""
    row1 = [("📈 DexScreener", f"https://dexscreener.com/robinhood/{pool or token}"),
            ("🐸 pons", f"https://pons.family/launchpad/{token}")]
    row2 = [("🔎 GMGN", f"https://gmgn.ai/robinhood/token/{token}"),
            ("🔗 Scan", f"{BLOCKSCOUT}{token}")]
    return [row1, row2]


def sint(h):
    v = int(h, 16)
    return v - (1 << 256) if v >= (1 << 255) else v


def parse_ts(s):
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load_smart():
    p = os.path.join(DATA, "smart_wallets.json")
    if not os.path.exists(p):
        return {}
    return json.load(open(p)).get("strong", {})


def load_deployer_counts():
    p = os.path.join(DATA, "launches.json")
    counts = defaultdict(int)
    if os.path.exists(p):
        for L in json.load(open(p)):
            counts[(L.get("deployer") or "").lower()] += 1
    return counts


class CoinState:
    __slots__ = ("token", "pool", "launch_block", "deployer", "symbol", "launched_at",
                 "token_is_0", "cursor", "buyers", "rebuy", "buy_weth", "sell_weth",
                 "n_buys", "n_sells", "snipers", "smart_hits", "dev_sold", "confirmed",
                 "dead", "pct", "paired", "price", "pending_since", "fire_net")

    def __init__(self, token, pool, launch_block, deployer, symbol, launched_at):
        self.token = token
        self.pool = pool
        self.launch_block = launch_block
        self.deployer = deployer
        self.symbol = symbol
        self.launched_at = launched_at
        self.token_is_0 = token < WETH
        self.cursor = launch_block
        self.buyers = defaultdict(float)
        self.rebuy = defaultdict(int)
        self.buy_weth = 0.0
        self.sell_weth = 0.0
        self.n_buys = 0
        self.n_sells = 0
        self.snipers = 0
        self.smart_hits = set()
        self.dev_sold = False
        self.confirmed = False
        self.dead = False
        self.pct = None
        self.paired = None
        self.price = None
        self.pending_since = None   # wall-clock when the rule first passed
        self.fire_net = None        # net_weth at that moment (for the hold check)

    def ingest(self, logs, smart):
        for lg in logs:
            data = lg["data"][2:]
            a0 = sint(data[0:64])
            a1 = sint(data[64:128])
            weth_amt = (a1 if self.token_is_0 else a0) / 1e18
            recip = "0x" + lg["topics"][2][-40:]
            blk = int(lg["blockNumber"], 16)
            t = (blk - self.launch_block) * BLOCK_SEC
            if weth_amt > 0:
                self.n_buys += 1
                self.buy_weth += weth_amt
                self.buyers[recip] += weth_amt
                self.rebuy[recip] += 1
                if t <= 2.0:
                    self.snipers += 1
                if recip in smart:
                    self.smart_hits.add(recip)
            else:
                self.n_sells += 1
                self.sell_weth += abs(weth_amt)
                if recip == self.deployer:
                    self.dev_sold = True

    @property
    def rebuyers(self):
        return sum(1 for v in self.rebuy.values() if v >= 2)

    @property
    def net_weth(self):
        return self.buy_weth - self.sell_weth

    @property
    def top_share(self):
        return (max(self.buyers.values()) / self.buy_weth) if self.buy_weth > 0 else 1.0


def fmt_confirmed(c, dep_count, args, fire_net=None, ethusd=0, now=0):
    sym = html.escape(str(c.symbol or c.token[:8]))
    dev_note = "first launch" if dep_count <= 1 else f"⚠️ serial deployer x{dep_count}"
    if c.dev_sold:
        dev_note += " · ⚠️ dev SOLD"
    held = ""
    if fire_net is not None:
        held = f"\n🛡️ net held {fire_net:+.2f} → <b>{c.net_weth:+.2f}</b> after {args.hold:.0f}s (no dump)"
    return "\n".join([
        f"🎯 <b>CONFIRMED</b> — <b>{sym}</b>",
        glance(c.token, c.price, c.paired, c.pct, c.launched_at, now, ethusd),
        f"✅ rebuyers <b>{c.rebuyers}</b> (≥{args.rebuyers}) · net <b>{c.net_weth:+.2f}</b> ETH · snipers <b>{c.snipers}</b> (≤{args.snipers})",
        f"👥 buyers {len(c.buyers)} · top-share {c.top_share:.0%} · 🧠 smart-money <b>{len(c.smart_hits)}</b>",
        f"🧑‍💻 dev: {dev_note}{held}",
        f'<a href="{BLOCKSCOUT}{c.token}">{c.token[:12]}…</a>  (backtest winrate ~30%, +net-hold guard)',
    ])


def fmt_neargrad(tok, sym, pct, paired, vel, price=None, launched_at=None, ethusd=0, now=0):
    return "\n".join([
        f"🔥 <b>NEAR-GRAD</b> — <b>{html.escape(str(sym or tok[:8]))}</b>",
        glance(tok, price, paired, pct, launched_at, now, ethusd),
        f"progress <b>{pct:.0f}%</b> · {paired:.2f}/{api.GRAD_THRESHOLD_ETH} ETH · vel <b>{vel:+.2f}</b> ETH/min",
        f'<a href="{BLOCKSCOUT}{tok}">{tok[:12]}…</a>',
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--rebuyers", type=int, default=6)
    # net kept at 1.0 (not 1.5): slow-build winners like RWC peak at ~1.4 net and
    # would fire at ~15 min (or be missed) under a higher bar. The deployer
    # anti-spam filter — not a higher net — is what removes pump-dumps (HOODCOIN).
    ap.add_argument("--net", type=float, default=1.0)
    ap.add_argument("--snipers", type=int, default=3)
    ap.add_argument("--max-dev-launches", type=int, default=4,
                    help="skip CONFIRMED if deployer has more prior launches than this AND 0 graduations")
    # net-hold guard: after the rule first passes, wait `hold` seconds and only
    # alert if net is still >= hold_keep x its fire-time value (drops pump-dumps).
    # Backtest: fp 33 -> 8, winners 45 -> 43, precision 10% -> 32%.
    ap.add_argument("--hold", type=float, default=120.0)
    ap.add_argument("--hold-keep", type=float, default=1.0)
    ap.add_argument("--near", type=float, default=70.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)
    smart = load_smart()
    dep_counts = load_deployer_counts()
    dep_grads = {k.lower(): v for k, v in
                 (json.load(open(os.path.join(DATA, "deployer_grads.json")))
                  if os.path.exists(os.path.join(DATA, "deployer_grads.json")) else {}).items()}
    print(f"pons PRO scanner  rule: rebuyers>={args.rebuyers} & net>={args.net}ETH & snipers<={args.snipers} "
          f"& NOT(dev>{args.max_dev_launches} launches & 0 grads) & net-hold {args.hold:.0f}s(keep {args.hold_keep:.0%})  "
          f"smart-wallets={len(smart)}  -> {'DRY-RUN' if dry else f'Telegram {chat_id}'}", flush=True)

    coins = {}          # token -> CoinState
    near_sent = {}      # token -> ts
    prog_hist = defaultdict(list)  # token -> [(t, paired)]

    def eth_usd():
        try:
            return api.get(api.EP_MARKET, {"token": WETH}).get("ethUsd") or 1900.0
        except Exception:  # noqa: BLE001
            return 1900.0
    ethusd = [eth_usd()]  # boxed so we can refresh it periodically

    def dispatch(text, label, buttons=None):
        stamp = time.strftime("%H:%M:%S")
        if dry:
            print(f"[{stamp}] DRY {label}\n" + text, flush=True)
            return
        ok, info = telegram.send(text, token_tg, chat_id, buttons=buttons)
        print(f"[{stamp}] {'sent -> ' + label if ok else 'send FAILED (' + label + '): ' + info}", flush=True)

    def register_launches():
        try:
            for L in api.latest():
                tok = L["token"].lower()
                if tok in coins or not L.get("pool") or not L.get("blockNumber"):
                    continue
                coins[tok] = CoinState(tok, L["pool"], L["blockNumber"],
                                       (L.get("deployer") or "").lower(),
                                       L.get("symbol"), parse_ts(L.get("launchedAt")))
                dep_counts[coins[tok].deployer] += 1
        except Exception as e:  # noqa: BLE001
            print(f"  latest error: {e}", flush=True)

    def update_swaps(now):
        active = [c for c in coins.values()
                  if not c.dead and not c.confirmed and c.launched_at
                  # keep polling young coins, and any pending coin until its hold resolves
                  and ((now - c.launched_at) <= ACTIVE_SECS or c.pending_since is not None)]
        if not active:
            return
        try:
            head = int(rpc("eth_blockNumber", []), 16)
        except Exception as e:  # noqa: BLE001
            print(f"  blockNumber error: {e}", flush=True)
            return
        calls = [("eth_getLogs", [{"address": c.pool, "topics": [SWAP_TOPIC],
                                    "fromBlock": hex(c.cursor), "toBlock": hex(head)}])
                 for c in active]
        try:
            results = rpc_batch(calls, timeout=30)
        except Exception as e:  # noqa: BLE001
            print(f"  getLogs batch error: {e}", flush=True)
            return
        for c, logs in zip(active, results):
            if logs is None:
                continue
            c.ingest(logs, smart)
            c.cursor = head + 1
            rule_ok = (c.rebuyers >= args.rebuyers and c.net_weth >= args.net
                       and c.snipers <= args.snipers)

            # stage 1: rule passes for the first time -> start the net-hold watch
            if rule_ok and c.pending_since is None:
                launches = dep_counts.get(c.deployer, 1)
                grads = dep_grads.get(c.deployer, 0)
                # anti-spam gate: serial deployer that never graduated = spam factory
                if launches > args.max_dev_launches and grads == 0:
                    c.confirmed = True  # stop re-checking, never alert
                    print(f"[{time.strftime('%H:%M:%S')}] SKIP spam-deployer "
                          f"{c.symbol or c.token[:8]} (dev x{launches}, 0 grads)", flush=True)
                    continue
                c.pending_since = now
                c.fire_net = c.net_weth
                print(f"[{time.strftime('%H:%M:%S')}] PENDING {c.symbol or c.token[:8]} "
                      f"net={c.fire_net:.2f} — hold {args.hold:.0f}s", flush=True)

            # stage 2: hold elapsed -> confirm only if net did NOT collapse
            if c.pending_since is not None and (now - c.pending_since) >= args.hold:
                held = c.net_weth >= c.fire_net * args.hold_keep
                c.confirmed = True
                if held:
                    dispatch(fmt_confirmed(c, dep_counts.get(c.deployer, 1), args,
                                           c.fire_net, ethusd[0], now),
                             f"CONFIRMED {c.symbol or c.token[:8]}",
                             buttons=links(c.token, c.pool))
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] DROP pump-dump "
                          f"{c.symbol or c.token[:8]} (net {c.fire_net:.2f} -> {c.net_weth:.2f})",
                          flush=True)

    def check_neargrad(now):
        try:
            feed = api.recent_buys()
        except Exception as e:  # noqa: BLE001
            print(f"  recent-buys error: {e}", flush=True)
            return
        for r in feed:
            tok = r["token"].lower()
            pct = r.get("graduationProgressPct") or 0
            paired = r.get("pairedPrincipalEth") or 0.0
            price = r.get("priceUsd")
            launched_at = None
            if tok in coins:
                coins[tok].pct = pct
                coins[tok].paired = paired
                coins[tok].price = price
                launched_at = coins[tok].launched_at
            prog_hist[tok].append((now, paired))
            if len(prog_hist[tok]) > 10:
                prog_hist[tok] = prog_hist[tok][-10:]
            if r.get("graduated") or pct < args.near:
                continue
            h = prog_hist[tok]
            vel = 0.0
            if len(h) >= 2 and h[-1][0] > h[0][0]:
                vel = (h[-1][1] - h[0][1]) / ((h[-1][0] - h[0][0]) / 60)
            if vel <= 0:
                continue
            if tok in near_sent and (now - near_sent[tok]) < 600:
                continue
            near_sent[tok] = now
            sym = coins[tok].symbol if tok in coins else (r.get("symbol") or tok[:8])
            dispatch(fmt_neargrad(tok, sym, pct, paired, vel, price, launched_at, ethusd[0], now),
                     f"NEAR-GRAD {sym or tok[:8]}",
                     buttons=links(tok, r.get("pool")))

    print("running… Ctrl-C to stop", flush=True)
    last_eth = [time.time()]
    while True:
        try:
            now = time.time()
            if now - last_eth[0] > 300:      # refresh ETH price every 5 min
                ethusd[0] = eth_usd()
                last_eth[0] = now
            register_launches()
            update_swaps(now)
            check_neargrad(now)
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  loop error: {e}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
