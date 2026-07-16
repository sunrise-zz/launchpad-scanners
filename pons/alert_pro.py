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
                 "dead", "pct", "paired")

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


def fmt_confirmed(c, dep_count, args):
    sym = html.escape(str(c.symbol or c.token[:8]))
    dev_note = "first launch" if dep_count <= 1 else f"⚠️ serial deployer x{dep_count}"
    if c.dev_sold:
        dev_note += " · ⚠️ dev SOLD"
    prog = f" · progress {c.pct:.0f}%" if c.pct is not None else ""
    return "\n".join([
        f"🎯 <b>CONFIRMED</b> — <b>{sym}</b>",
        f"✅ rebuyers <b>{c.rebuyers}</b> (≥{args.rebuyers}) · net <b>{c.net_weth:+.2f}</b> ETH (≥{args.net}) · snipers <b>{c.snipers}</b> (≤{args.snipers})",
        f"👥 buyers {len(c.buyers)} · top-share {c.top_share:.0%} · 🧠 smart-money <b>{len(c.smart_hits)}</b>",
        f"🧑‍💻 dev: {dev_note}{prog}",
        f'<a href="{BLOCKSCOUT}{c.token}">{c.token[:12]}…</a>  (backtest winrate ~30-40%)',
    ])


def fmt_neargrad(tok, sym, pct, paired, vel):
    return "\n".join([
        f"🔥 <b>NEAR-GRAD</b> — <b>{html.escape(str(sym or tok[:8]))}</b>",
        f"progress <b>{pct:.0f}%</b> · {paired:.2f}/{api.GRAD_THRESHOLD_ETH} ETH · vel {vel:+.2f} ETH/min",
        f'<a href="{BLOCKSCOUT}{tok}">{tok[:12]}…</a>',
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--rebuyers", type=int, default=6)
    ap.add_argument("--net", type=float, default=1.0)
    ap.add_argument("--snipers", type=int, default=3)
    ap.add_argument("--near", type=float, default=70.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)
    smart = load_smart()
    dep_counts = load_deployer_counts()
    print(f"pons PRO scanner  rule: rebuyers>={args.rebuyers} & net>={args.net}ETH & snipers<={args.snipers}"
          f"  smart-wallets={len(smart)}  -> {'DRY-RUN' if dry else f'Telegram {chat_id}'}", flush=True)

    coins = {}          # token -> CoinState
    near_sent = {}      # token -> ts
    prog_hist = defaultdict(list)  # token -> [(t, paired)]

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
                  if not c.dead and not c.confirmed
                  and c.launched_at and (now - c.launched_at) <= ACTIVE_SECS]
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
            if c.rebuyers >= args.rebuyers and c.net_weth >= args.net and c.snipers <= args.snipers:
                c.confirmed = True
                dispatch(fmt_confirmed(c, dep_counts.get(c.deployer, 1), args),
                         f"CONFIRMED {c.symbol or c.token[:8]}",
                         buttons=links(c.token, c.pool))

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
            if tok in coins:
                coins[tok].pct = pct
                coins[tok].paired = paired
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
            dispatch(fmt_neargrad(tok, sym, pct, paired, vel), f"NEAR-GRAD {sym or tok[:8]}",
                     buttons=links(tok, r.get("pool")))

    print("running… Ctrl-C to stop", flush=True)
    while True:
        try:
            now = time.time()
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
