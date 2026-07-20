"""pons.family PRO scanner — multi-factor CONFIRMED alerts with insights.

Backtested on 94 graduations vs 1,500 controls (real base rate 0.54%):

    CONFIRMED rule (first 5 min, on-chain):
        rebuyers >= 6        wallets that bought 2+ times (conviction)
        net_weth >= 1.0      net ETH into the pool
        snipers <= 3         buys in the first 2s (bot-sniped launches fail)

    -> real-world precision ~30% (out-of-time test: 41%), recall ~43-84%,
       fires at median 44s after launch; graduation happens ~90 min later.

Pipeline per poll (~2s):
  1. TokenLaunched factory events register new launches (token, pool,
     launchBlock, deployer) — see pons/api.py latest().
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
import math
import os
import sys
import threading
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "vlad"))
import alertfmt  # noqa: E402
import api  # noqa: E402
import controls  # noqa: E402
import ethprice  # noqa: E402
import gmgn  # noqa: E402
import outcomes  # noqa: E402
import telegram  # noqa: E402
from rpc import rpc, rpc_batch  # noqa: E402  (quiknode Robinhood mainnet)

DATA = os.path.join(HERE, "data")
BLOCK_SEC = 0.1
SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
WETH = "0x0bd7d308f8e1639fab988df18a8011f41eacad73"
# One definition, in api.py, because discovery's cold-start lookback is derived
# from it: a window here that api.py didn't look back over is a launch that is
# alert-eligible but was never discovered (#4). The import already runs one way
# — api.py never imports this module — so they can't drift.
ACTIVE_SECS = api.WATCH_SECS
BLOCKSCOUT = "https://robinhoodchain.blockscout.com/token/"


_SUPPLY = {}   # token -> total supply (constant, cached via on-chain call)
_HOLDERS = {}  # token -> (fetched_ts, count) — short-lived cache
BS_TOKEN_API = "https://robinhoodchain.blockscout.com/api/v2/tokens/"


def holders(token, now, ttl=60):
    """Live holder count from Blockscout (cached `ttl` seconds). None on failure."""
    hit = _HOLDERS.get(token)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    n = None
    try:
        import urllib.request
        req = urllib.request.Request(BS_TOKEN_API + token,
                                     headers={"user-agent": "Mozilla/5.0", "accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
        n = int(d.get("holders_count") or d.get("holders") or 0) or None
    except Exception:  # noqa: BLE001
        # keep the old entry (don't renew its timestamp) so the next call retries
        return hit[1] if hit else None
    _HOLDERS[token] = (now, n)
    return n


_RISK = {}   # token -> (ts, dict)
_SOCIAL = {}  # token -> (ts, dict)
DEXSCR_TOKEN = "https://api.dexscreener.com/tokens/v1/robinhood/"


def dex_socials(token, now, ttl=90):
    """Socials + market microstructure from DexScreener (Robinhood chain).
    Socials are the single strongest winner signal in the alert history: 78% of
    winners have an X account vs 10% of coins that died. The same response also
    carries per-window txns/volume — free momentum data we previously discarded.

    Returns {x, tg, web, has, depth, liq_usd, m5_buys, m5_sells, h1_buys,
             h1_sells, vol_m5, vol_h1}. Market keys are None when the pair
    isn't indexed yet (very young coins)."""
    hit = _SOCIAL.get(token)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    out = {"x": None, "tg": None, "web": None, "has": False, "depth": 0,
           "liq_usd": None, "m5_buys": None, "m5_sells": None,
           "h1_buys": None, "h1_sells": None, "vol_m5": None, "vol_h1": None}
    try:
        import urllib.request
        req = urllib.request.Request(DEXSCR_TOKEN + token,
                                     headers={"user-agent": "Mozilla/5.0", "accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            pairs = json.loads(r.read())
        info, best = {}, None
        for p in (pairs or []):
            if best is None:
                best = p
            if (p.get("info") or {}).get("socials") or (p.get("info") or {}).get("websites"):
                info = p["info"]
                if best is not p:
                    best = p
                break
        for s in (info.get("socials") or []):
            t = (s.get("type") or "").lower()
            if t in ("twitter", "x"):
                out["x"] = s.get("url")
            elif t == "telegram":
                out["tg"] = s.get("url")
        ws = info.get("websites") or []
        if ws:
            out["web"] = ws[0].get("url") if isinstance(ws[0], dict) else ws[0]
        out["has"] = bool(out["x"] or out["web"])
        out["depth"] = sum(1 for k in ("x", "tg", "web") if out[k])
        if best:
            tx = best.get("txns") or {}
            vol = best.get("volume") or {}
            out["liq_usd"] = (best.get("liquidity") or {}).get("usd")
            out["m5_buys"] = (tx.get("m5") or {}).get("buys")
            out["m5_sells"] = (tx.get("m5") or {}).get("sells")
            out["h1_buys"] = (tx.get("h1") or {}).get("buys")
            out["h1_sells"] = (tx.get("h1") or {}).get("sells")
            out["vol_m5"] = vol.get("m5")
            out["vol_h1"] = vol.get("h1")
    except Exception:  # noqa: BLE001
        return hit[1] if hit else out   # don't cache the failure; retry next call
    _SOCIAL[token] = (now, out)
    return out


_PAID = {}  # token -> (ts, list[str])
DEXSCR_ORDERS = "https://api.dexscreener.com/orders/v1/robinhood/"


def dex_paid(token, now, ttl=300):
    """Paid-marketing check: has the team paid DexScreener for a profile/boost?
    Teams spending real money on marketing is intent to push the coin, and the
    payment timestamp often precedes the pump. Returns e.g. ["profile", "boost x80"].
    """
    hit = _PAID.get(token)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    out = []
    try:
        import urllib.request
        req = urllib.request.Request(DEXSCR_ORDERS + token,
                                     headers={"user-agent": "Mozilla/5.0", "accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
        if any(o.get("type") == "tokenProfile" and o.get("status") == "approved"
               for o in (d.get("orders") or [])):
            out.append("profile")
        boosts = d.get("boosts") or []
        if boosts:
            out.append(f"boost x{sum(b.get('amount', 0) for b in boosts)}")
    except Exception:  # noqa: BLE001
        return hit[1] if hit else []   # don't cache the failure; retry next call
    _PAID[token] = (now, out)
    return out


def holder_risk(token, pool, deployer, now, ttl=60):
    """GMGN-style holder concentration from Blockscout, excluding the bonding-curve
    pool. Returns {dev_pct, top1_pct, top10_pct} as % of CIRCULATING supply, or {}.
    """
    hit = _RISK.get(token)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    out = {}
    try:
        import urllib.request
        req = urllib.request.Request(BS_TOKEN_API + token + "/holders",
                                     headers={"user-agent": "Mozilla/5.0", "accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            items = json.loads(r.read()).get("items", [])
        sup = total_supply(token)
        if items and sup:
            pool = (pool or "").lower()
            dev = (deployer or "").lower()
            bals = [(h["address"]["hash"].lower(), int(h["value"]) / 1e18) for h in items]
            pool_bal = sum(b for a, b in bals if a == pool)
            circ = sup - pool_bal
            if circ > 0:
                non_pool = sorted([(a, b) for a, b in bals if a != pool], key=lambda x: -x[1])
                out = {
                    "dev_pct": 100 * sum(b for a, b in bals if a == dev) / circ,
                    "top1_pct": 100 * non_pool[0][1] / circ if non_pool else 0.0,
                    "top10_pct": 100 * sum(b for _, b in non_pool[:10]) / circ,
                }
    except Exception:  # noqa: BLE001
        return hit[1] if hit else {}   # don't cache the failure; retry next call
    _RISK[token] = (now, out)
    return out


def total_supply(token):
    if token not in _SUPPLY:
        try:
            r = rpc("eth_call", [{"to": token, "data": "0x18160ddd"}, "latest"], timeout=10)
            _SUPPLY[token] = int(r, 16) / 1e18
        except Exception:  # noqa: BLE001
            _SUPPLY[token] = None
    return _SUPPLY[token]


# ERC20 symbol() lives in api.py — which resolves symbols in batch during
# discovery — so both paths share one implementation and one cache. Call
# api.token_symbol() directly.


def _f(x):
    """Safe float coercion (several feeds return numbers as strings). None on fail."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


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
    """One-line at-a-glance: market cap · holders · liquidity · age · progress."""
    sup = total_supply(token)
    price = _f(price)   # recent_buys priceUsd can arrive as a string → mc math would crash
    mc = human_usd(price * sup) if (price and sup) else "?"
    h = holders(token, now)
    hstr = f" · 👥 {h} holders" if h else ""
    liq = f"{paired:.2f} ETH" if paired else "?"
    # `ethusd` is an ethprice.Price when it came from the provider chain, and a
    # bare float from older callers. When every provider is down it is the
    # hardcoded constant, and the USD figure is a guess — say so on the number
    # itself rather than letting a stale price look live (#5).
    # Asked before the multiply: `paired*ethusd` is a plain float and has lost
    # the provenance (see ethprice.Price).
    mark = " ⚠️est" if getattr(ethusd, "estimated", False) else ""
    liq_usd = f" ({'~' if mark else ''}{human_usd(paired*ethusd)}{mark})" if (paired and ethusd) else ""
    prog = f"{pct:.0f}% to grad" if pct is not None else "pre-curve"
    return f"💰 mc {mc}{hstr} · 💧 liq {liq}{liq_usd} · ⏱️ {age_str(launched_at, now)} · 📊 {prog}"


def links(token, pool=None, soc=None):
    """Inline-keyboard rows for a coin. DexScreener + pons have Robinhood Chain
    data; GMGN is included on request. An X button is added when the coin has one."""
    row1 = [("📈 DexScreener", f"https://dexscreener.com/robinhood/{pool or token}"),
            ("🐸 pons", f"https://pons.family/launchpad/{token}")]
    row2 = [("🔎 GMGN", f"https://gmgn.ai/robinhood/token/{token}"),
            ("🔗 Scan", f"{BLOCKSCOUT}{token}")]
    rows = [row1, row2]
    if soc and soc.get("x"):
        rows.insert(0, [("🐦 X account", soc["x"])])
    return rows


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


def load_deployer_tokens():
    """deployer -> set of its token addresses. A SET (not a counter) so that
    re-seeing a launch in /latest that's already in launches.json doesn't
    double-count it — the old counter double-counted and tripped the spam gate /
    serial-deployer penalty on legitimate first-time deployers."""
    p = os.path.join(DATA, "launches.json")
    toks = defaultdict(set)
    if os.path.exists(p):
        for L in json.load(open(p)):
            dep = (L.get("deployer") or "").lower()
            tk = (L.get("token") or "").lower()
            if tk:
                toks[dep].add(tk)
    return toks


class CoinState:
    __slots__ = ("token", "pool", "launch_block", "deployer", "symbol", "launched_at",
                 "token_is_0", "cursor", "buyers", "rebuy", "buy_weth", "sell_weth",
                 "n_buys", "n_sells", "snipers", "smart_hits", "smart_score", "dev_sold",
                 "confirmed", "dead", "pct", "paired", "price", "pending_since", "fire_net",
                 "initial_buy_wei", "restrictions_end_block")

    def __init__(self, token, pool, launch_block, deployer, symbol, launched_at,
                 pair_token=None, initial_buy_wei=None, restrictions_end_block=None):
        self.token = token
        self.pool = pool
        self.launch_block = launch_block
        self.deployer = deployer
        self.symbol = symbol
        self.launched_at = launched_at
        # Pool ordering from the launch event's pairToken when we have it. Every
        # sampled launch pairs against WETH, so this is the same answer today —
        # but a non-WETH pair would otherwise decode every buy as a sell.
        self.token_is_0 = token < (pair_token or WETH)
        # Launch-time measurements from TokenLaunched. Logged with the alert for
        # the refit (#10), never scored. See api.decode_launch on the units.
        self.initial_buy_wei = initial_buy_wei
        self.restrictions_end_block = restrictions_end_block
        self.cursor = launch_block
        self.buyers = defaultdict(float)
        self.rebuy = defaultdict(int)
        self.buy_weth = 0.0
        self.sell_weth = 0.0
        self.n_buys = 0
        self.n_sells = 0
        self.snipers = 0
        self.smart_hits = set()
        self.smart_score = 0    # Σ graduated-coin count of each smart wallet that bought
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
                # weighted smart money: smart_wallets.json maps wallet -> how many
                # graduated coins it bought early; a wallet with 4 grads under its
                # belt is worth 4x a one-hit wallet, not the same binary tick.
                if recip in smart and recip not in self.smart_hits:
                    self.smart_hits.add(recip)
                    self.smart_score += smart.get(recip, 1)
            elif weth_amt < 0:      # exact-zero WETH delta is neither buy nor sell
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

    def is_active(self, now):
        """Whether this coin is still worth polling swaps for: young enough to
        alert, or holding a pending confirmation that has to resolve.

        A launch first seen older than ACTIVE_SECS — everything a drained
        outage backlog surfaces (#4) — is registered but never scanned, so it
        cannot alert. That makes this the one thing standing between a backlog
        and firing all of it at once, which is why it is a named method with a
        test rather than a condition inside update_swaps().
        """
        if self.dead or self.confirmed or not self.launched_at:
            return False
        return self.should_retain(now)

    def should_retain(self, now):
        """Whether pruning this state could lose an eligible or pending coin."""
        if self.launched_at is None:
            return True
        unresolved = self.pending_since is not None and not (self.confirmed or self.dead)
        return (now - self.launched_at) <= ACTIVE_SECS or unresolved


def prune_coins(coins, now):
    """Drop coin state after its alert window, except unresolved confirmations."""
    stale = [token for token, coin in coins.items() if not coin.should_retain(now)]
    for token in stale:
        del coins[token]
    return stale


def register_launch_records(records, coins, dep_tokens, registered_tokens, now):
    """Register unseen discovery records while retaining compact dedup history."""
    n = 0
    for record in records:
        token = record["token"].lower()
        if (token in registered_tokens
                or not record.get("pool")
                or not record.get("blockNumber")):
            continue
        launched_at = parse_ts(record.get("launchedAt")) or now
        deployer = (record.get("deployer") or "").lower()
        coins[token] = CoinState(
            token, record["pool"], record["blockNumber"],
            deployer, record.get("symbol"), launched_at,
            pair_token=record.get("pairToken"),
            initial_buy_wei=record.get("initialBuyAmount"),
            restrictions_end_block=record.get("restrictionsEndBlock"),
        )
        dep_tokens.setdefault(deployer, set()).add(token)
        registered_tokens.add(token)
        n += 1
    return n


def launch_features(c, dep_launches):
    """Raw launch-time measurements for one coin, logged alongside its alert.

    Measurements only, never scores: the weights get refit (#10) and a derived
    score in here would silently reinterpret every row accumulated under the
    old formula. `initial_buy_wei` and `restrictions_end_block` come from the
    TokenLaunched event (see api.decode_launch for units — the latter is an L1
    block number); research flags dev initial-buy size as a graduation
    predictor, but it earns weight only once the refit measures it.

    This is the shape flap/pump/virtuals mirror in #7. None means "not
    measured" and is distinct from 0.
    """
    return dict(
        rebuyers=c.rebuyers, net_weth=round(c.net_weth, 4),
        n_buys=c.n_buys, n_sells=c.n_sells,
        buy_weth=round(c.buy_weth, 4), snipers=c.snipers,
        top_share=round(c.top_share, 4) if c.buy_weth > 0 else None,
        cap_eff=round(c.buy_weth / c.n_buys, 5) if c.n_buys else None,
        smart_score=c.smart_score, dep_count=dep_launches, dev_sold=c.dev_sold,
        initial_buy_wei=c.initial_buy_wei,
        restrictions_end_block=c.restrictions_end_block,
    )


def social_line(soc):
    if not soc:
        return "🔗 socials: ？"
    if not soc.get("has"):
        return "🔗 socials: <b>⚠️ none</b> (90% of dead coins have no X/web)"
    parts = []
    if soc.get("x"):
        parts.append("🐦 X")
    if soc.get("web"):
        parts.append("🌐 web")
    if soc.get("tg"):
        parts.append("💬 TG")
    return f"🔗 {' · '.join(parts)}  ✅ {soc.get('depth', len(parts))}/3"


def momentum_line(soc, paid):
    """DexScreener microstructure + paid-marketing badge. Parts appear only when
    the pair is indexed / the data exists, so young coins degrade gracefully."""
    parts = []
    if soc and soc.get("m5_buys") is not None:
        b, s = soc["m5_buys"], soc["m5_sells"] or 0
        ratio = f" ({b/s:.1f}x)" if s else ""
        parts.append(f"m5 {b}🟢/{s}🔴{ratio}")
    if soc and soc.get("vol_m5") is not None and soc.get("vol_h1"):
        # ×12 annualises m5 to an hourly pace: >1x = interest accelerating NOW
        accel = soc["vol_m5"] * 12 / soc["vol_h1"]
        parts.append(f"vol accel {accel:.1f}x")
    if soc and soc.get("liq_usd") is not None:
        parts.append(f"liq {human_usd(soc['liq_usd'])}")
    if paid:
        parts.append("💰 paid: " + "+".join(paid))
    return ("📊 " + " · ".join(parts)) if parts else ""


def score_confirmed(c, dep_count, soc, paid, r):
    """Heuristic 0-100. Base 50 = the rule itself passed (backtested ~30-40%
    precision); extras shift it. Weights are v1 judgment calls — refit later."""
    s = 50.0
    # conviction beyond the bar. Log-scaled (wave 21): winners' rebuyers median is
    # 25.5 and reaches 300+, while the old min(rebuyers-6,6)*2 flatlined at 12 —
    # a 300-rebuyer coin has to outscore a 12-rebuyer one.
    if c.rebuyers > 6:
        s += min(12 * math.log10(c.rebuyers / 6), 20)
    # net ETH beyond the bar, same reasoning (winner median 6.94Ξ, p75 17.8Ξ;
    # the old cap saturated at 4Ξ).
    if c.net_weth > 1.0:
        s += min(14 * math.log10(c.net_weth / 1.0), 16)
    s += min(c.smart_score, 10)                          # weighted smart money
    # capital efficiency: ETH raised PER buy — real conviction arrives in size,
    # bots churn many micro-buys. Tiers recalibrated to OUR measured bands
    # (waves 21/24): winners 0.021-0.041 (median 0.031, max 0.050), died 0.005.
    # The old >=0.1 tier was DEAD CODE — 0/22 winners ever reached it.
    if c.n_buys:
        cap_eff = c.buy_weth / c.n_buys
        if cap_eff >= 0.03:                              # winner median and above
            s += 8
        elif cap_eff >= 0.02:                            # winner p25 band
            s += 5
        elif cap_eff >= 0.012:                           # winner floor (min 0.013)
            s += 2
        else:
            s -= 5                                       # died territory (median 0.005)
    # top1_share — the cleanest pons separator found (wave 24): winners median
    # 5.6% (distributed/organic, only 3/22 above 15%), died median 62.8% (one
    # whale controls the early buy side). Penalise whale-domination.
    if c.buy_weth > 0:
        ts = c.top_share
        if ts >= 0.50:
            s -= 15                                      # died-median territory
        elif ts >= 0.30:
            s -= 10
        elif ts >= 0.20:
            s -= 5
    # Telegram-weighted socials (research #5): TG presence = 8.9x graduation lift,
    # all-three = 17x. Weight TG higher than the raw channel count.
    if soc:
        s += (soc.get("depth", 0)) * 2                   # base per-channel
        s += 4 if soc.get("tg") else 0                   # Telegram bonus
        s += 4 if (soc.get("x") and soc.get("tg") and soc.get("web")) else 0  # full triple
    s += 8 if paid else 0                                # team spends on marketing
    if c.n_sells:
        ratio = c.n_buys / c.n_sells
        s += 6 if ratio >= 3 else (4 if ratio >= 2 else 0)
    s -= c.snipers * 2
    s -= 8 if dep_count > 1 else 0
    s -= 10 if c.dev_sold else 0
    if r:
        s -= 6 if r.get("dev_pct", 0) >= 15 else 0
        s -= 6 if r.get("top1_pct", 0) >= 25 else 0
    return alertfmt.clamp(s)


def gmgn_line(g):
    """One pros line from the GMGN snapshot — the cross-platform view we can't
    compute ourselves (smart/renowned wallet tags span every chain/launchpad).
    Display only for now; fields earn score weight via outcome tracking."""
    if not g:
        return None
    bits = [f"smart <b>{g.get('smart', 0)}</b>", f"renowned {g.get('renowned', 0)}"]
    if g.get("bot_rate") is not None:
        bits.append(f"bots {g['bot_rate']*100:.0f}%")
    if g.get("dev_best_ath_mc"):
        bits.append(f"dev best {human_usd(g['dev_best_ath_mc'])}")
    if g.get("img_dup"):
        bits.append(f"img dup x{g['img_dup']}")
    return "🧬 GMGN " + " · ".join(bits)


def fmt_confirmed(c, dep_count, args, fire_net=None, ethusd=0, now=0, soc=None, paid=None, g=None):
    sym = html.escape(str(c.symbol or c.token[:8]))
    r = holder_risk(c.token, c.pool, c.deployer, now)
    score = score_confirmed(c, dep_count, soc, paid, r)

    bs = f"{c.n_buys}/{c.n_sells}" + (f" ({c.n_buys/c.n_sells:.1f}x)" if c.n_sells else "")
    cap = f" · avg {c.buy_weth/c.n_buys:.3f}Ξ/buy" if c.n_buys else ""
    top = f" · top1 {c.top_share*100:.0f}%" if c.buy_weth > 0 else ""
    pros = [f"rebuyers <b>{c.rebuyers}</b> · net <b>{c.net_weth:+.2f}</b>Ξ · buys/sells {bs}{cap}{top}"]
    if c.smart_hits:
        pros.append(f"🧠 smart {len(c.smart_hits)} กระเป๋า (score {c.smart_score})")
    socbits = [b for b, on in (("🐦 X", soc and soc.get("x")), ("🌐 web", soc and soc.get("web")),
                               ("💬 TG", soc and soc.get("tg"))) if on]
    if paid:
        socbits.append("💰 paid: " + "+".join(paid))
    if socbits:
        pros.append(" · ".join(socbits))
    mom = momentum_line(soc, None)
    if mom:
        pros.append(mom[2:])   # already carries its own emoji cluster, strip "📊 "
    gl = gmgn_line(g)
    if gl:
        pros.append(gl)

    cons = []
    if c.buy_weth > 0 and c.top_share >= 0.20:
        cons.append(f"top buyer {c.top_share*100:.0f}% ของ buy volume (whale-dominated)")
    if c.snipers:
        cons.append(f"snipers {c.snipers}/{args.snipers}")
    if dep_count > 1:
        cons.append(f"serial deployer x{dep_count}")
    if c.dev_sold:
        cons.append("dev SOLD")
    if r and r.get("dev_pct", 0) >= 15:
        cons.append(f"dev holds {r['dev_pct']:.0f}%")
    if r and r.get("top1_pct", 0) >= 25:
        cons.append(f"top wallet {r['top1_pct']:.0f}%")
    if soc and not soc.get("has"):
        cons.append("no socials")

    stats = [glance(c.token, c.price, c.paired, c.pct, c.launched_at, now, ethusd)]
    if fire_net is not None:
        stats.append(f"🛡️ net held {fire_net:+.2f} → <b>{c.net_weth:+.2f}</b>Ξ over {args.hold:.0f}s")

    return alertfmt.compose(score, "🎯", "CONFIRMED", sym, "🐸 pons.family", "ROBINHOOD",
                            pros, cons, stats,
                            f'<a href="{BLOCKSCOUT}{c.token}">{c.token[:12]}…</a>')


def score_neargrad(pct, vel, soc, paid, holders_n):
    """Heuristic 0-100 for the progress tier — base 40 (weaker signal than
    CONFIRMED: late, momentum-driven, no early-trading factors).

    Outcome data (2026-07-18, ~440 alerts): higher graduation % predicted WORSE
    returns (score 65-100 band peaked at only +12% vs +17% for 40-58) — because
    a coin already at 95% has done its move. So progress is NO LONGER rewarded;
    the entry edge is momentum (velocity) while still mid-climb, so velocity is
    weighted up and being very deep in the curve is penalised slightly."""
    s = 40.0
    s -= min(max(pct - 85, 0), 15)                       # >85%: late, likely already ran
    s += min(max(vel, 0) * 15, 18)                       # ETH/min into the curve (main edge)
    s += (soc.get("depth", 0) if soc else 0) * 3
    s += 8 if paid else 0
    if soc and soc.get("m5_buys") is not None:
        b, sl = soc["m5_buys"], soc["m5_sells"] or 0
        if b >= 2 * max(sl, 1):
            s += 6
    s += 5 if (holders_n or 0) >= 300 else 0
    return alertfmt.clamp(s)


def fmt_neargrad(tok, sym, pct, paired, vel, price=None, launched_at=None, ethusd=0, now=0, soc=None, paid=None):
    holders_n = holders(tok, now)
    score = score_neargrad(pct, vel, soc, paid, holders_n)

    pros = [f"progress <b>{pct:.0f}%</b> ({paired:.2f}/{api.GRAD_THRESHOLD_ETH}Ξ) · vel <b>{vel:+.2f}</b>Ξ/min"]
    socbits = [b for b, on in (("🐦 X", soc and soc.get("x")), ("🌐 web", soc and soc.get("web")),
                               ("💬 TG", soc and soc.get("tg"))) if on]
    if paid:
        socbits.append("💰 paid: " + "+".join(paid))
    if socbits:
        pros.append(" · ".join(socbits))
    mom = momentum_line(soc, None)
    if mom:
        pros.append(mom[2:])

    cons = []
    if soc and not soc.get("has"):
        cons.append("no socials")

    stats = [glance(tok, price, paired, pct, launched_at, now, ethusd)]
    return alertfmt.compose(score, "🔥", "NEAR-GRAD", html.escape(str(sym or tok[:8])),
                            "🐸 pons.family", "ROBINHOOD", pros, cons, stats,
                            f'<a href="{BLOCKSCOUT}{tok}">{tok[:12]}…</a>')


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
    # social gate: winners have an X/website 80% of the time vs 10% for dead coins.
    ap.add_argument("--require-social", dest="require_social", action="store_true", default=True,
                    help="skip CONFIRMED if the coin has no X and no website (default on)")
    ap.add_argument("--no-require-social", dest="require_social", action="store_false")
    # --- soft gates (default OFF: displayed in alerts, not yet backtested as filters;
    #     turn on once enough alert history accumulates to fit thresholds) ---
    ap.add_argument("--min-socials", type=int, default=1,
                    help="with --require-social: minimum social channels of X/TG/web (default 1)")
    ap.add_argument("--min-bs-ratio", type=float, default=0.0,
                    help="skip CONFIRMED if on-chain buys/sells ratio is below this (0 = off)")
    ap.add_argument("--min-liq-usd", type=float, default=0.0,
                    help="skip CONFIRMED if DexScreener liquidity USD is below this (0 = off)")
    ap.add_argument("--min-smart-score", type=int, default=0,
                    help="skip CONFIRMED if weighted smart-money score is below this (0 = off)")
    # marketing feed: poll DexScreener paid profiles/boosts (60 req/min budget).
    # Default OFF as of 2026-07-18: outcome tracking showed paid-marketing alerts
    # ran -14% (1h) → -39% (8h) with an 18% hit-rate — paying for a DexScreener
    # profile does not predict price. Re-enable with --marketing-feed to collect more.
    ap.add_argument("--marketing-feed", dest="marketing_feed", action="store_true", default=False,
                    help="alert when any Robinhood-chain token pays for a DexScreener profile/boost (default OFF — net-negative in tracking)")
    ap.add_argument("--no-marketing-feed", dest="marketing_feed", action="store_false")
    ap.add_argument("--near", type=float, default=70.0)
    # NEAR-GRAD tier DISABLED by default as of 2026-07-18: outcome tracking over
    # ~450 alerts showed it net-negative at every horizon (-27% → -34% by 8h) and
    # its score was anti-predictive. It was also the biggest volume source
    # (~408/day). Re-enable with --neargrad to collect more / chase the rare
    # moonshot. Coin state (pct/price) is still updated either way.
    ap.add_argument("--neargrad", dest="neargrad", action="store_true", default=False,
                    help="emit NEAR-GRAD alerts (default OFF — net-negative in tracking)")
    ap.add_argument("--no-neargrad", dest="neargrad", action="store_false")
    # Launch discovery source. On-chain by default: pons.family went NXDOMAIN
    # ~2026-07-18 while the factory kept launching. `http` is the escape hatch
    # if the domain ever returns; it is not on the critical path otherwise.
    ap.add_argument("--discovery-source", choices=("rpc", "http"),
                    default=api.DISCOVERY_SOURCE,
                    help="where new launches come from (default: rpc / TokenLaunched events)")
    # Shadow-control sampling (#9): launches we evaluated and never confirmed,
    # tracked so the alerted ones have a base rate to be measured against.
    controls.add_args(ap)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    api.DISCOVERY_SOURCE = args.discovery_source

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)
    smart = load_smart()
    dep_tokens = load_deployer_tokens()   # deployer -> set(token); len() = launch count

    def dep_count(deployer):
        return len(dep_tokens.get(deployer, ()))
    dep_grads = {k.lower(): v for k, v in
                 (json.load(open(os.path.join(DATA, "deployer_grads.json")))
                  if os.path.exists(os.path.join(DATA, "deployer_grads.json")) else {}).items()}
    print(f"pons PRO scanner  rule: rebuyers>={args.rebuyers} & net>={args.net}ETH & snipers<={args.snipers} "
          f"& NOT(dev-spam) & net-hold {args.hold:.0f}s & social={'required' if args.require_social else 'off'}  "
          f"smart-wallets={len(smart)} (weighted)  neargrad={'on' if args.neargrad else 'off'}  "
          f"marketing-feed={'on' if args.marketing_feed else 'off'}  "
          f"discovery={args.discovery_source}  "
          f"-> {'DRY-RUN' if dry else f'Telegram {chat_id}'}", flush=True)

    coins = {}          # active/recent token -> CoinState
    registered_tokens = set()  # compact process-lifetime dedup after CoinState pruning
    near_sent = {}      # token -> ts
    sampler = controls.ControlSampler("pons.family", k=args.controls_k,
                                      bucket_s=args.controls_bucket_s,
                                      state_path=os.path.join(DATA, "control_slot.json"))
    prog_hist = defaultdict(list)  # token -> [(t, paired)]

    # CONFIRMED dedup persisted across restarts: a restart within a coin's
    # 15-min active window re-ingests its swaps from launch block, re-passes
    # the rule and would re-alert after the hold (same class of bug as flap's
    # near-grad board re-fire on 2026-07-18).
    conf_file = os.path.join(DATA, "confirmed_sent.txt")
    conf_sent = set()
    if os.path.exists(conf_file):
        conf_sent = {ln.strip().lower() for ln in open(conf_file) if ln.strip()}

    def mark_conf(token):
        conf_sent.add(token)
        try:
            with open(conf_file, "a") as f:
                f.write(token + "\n")
        except Exception:  # noqa: BLE001
            pass

    # Boxed so the periodic refresh can replace it. Startup is synchronous so a
    # --dry-run prints a real price immediately; the refresh below is not.
    ethusd = [ethprice.fetch()]
    print("ETH/USD " + ethusd[0].describe(), flush=True)
    missing = ethprice.unconfigured()
    if missing:
        print(f"  ⚠️ ETH/USD provider(s) unconfigured on this host: {', '.join(missing)}"
              f" — the chain is down to {len(ethprice.PROVIDERS) - len(missing)} provider(s)", flush=True)

    def refresh_eth():
        """Off the poll loop, deliberately. The dead pons.family lookup this
        replaced retried four times with sleeps and stalled discovery and the
        CONFIRMED path 6.1s every 5 minutes (#5). A provider that hangs must
        cost us a stale price, never a stalled scanner.

        fetch() is contractually non-raising, so there is no guard here: if it
        ever did raise, this thread dies with a traceback on stderr and the
        last good price keeps serving — louder than a silent `except: pass`."""
        ethusd[0] = ethprice.fetch()

    def dispatch(text, label, buttons=None, record=None):
        stamp = time.strftime("%H:%M:%S")
        if dry:
            print(f"[{stamp}] DRY {label}\n" + text, flush=True)
            return
        ok, info = telegram.send(text, token_tg, chat_id, buttons=buttons)
        if record and ok:
            # stash the sent message so the AI analyst can append its verdict
            # into the SAME bubble (edit-in-place) instead of a stray follow-up
            record["tg"] = {"msg_id": info if isinstance(info, int) else None,
                            "text": text, "buttons": buttons}
            outcomes.record_alert(**record)   # only record alerts that actually sent (no phantom outcomes)
        print(f"[{stamp}] {'sent -> ' + label if ok else 'send FAILED (' + label + '): ' + info}", flush=True)

    def register_launches():
        try:
            n = register_launch_records(
                api.latest(), coins, dep_tokens, registered_tokens, time.time())
            if n:
                # Discovery going quiet is what the 2026-07-18 outage looked
                # like from the outside; make it visible in the log. (#6 turns
                # this into an actual watchdog.)
                print(f"[{time.strftime('%H:%M:%S')}] +{n} launch{'es' if n > 1 else ''} "
                      f"({len(coins)} tracked)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  latest error: {e}", flush=True)

    def sample_control(now, active):
        """Take one active launch we have not confirmed as a control (#9).

        Since #3 pons discovers launches on-chain, so `coins` holds every
        launch on the pad, alerted or not — which is why the issue calls pons
        the cleanest source of controls we have. The pool is the coins under
        active evaluation, matching where a CONFIRMED alert is decided, and the
        features are the same CoinState measurements the rule reads."""
        # near_sent as well as conf_sent: a coin that already went out as
        # NEAR-GRAD was alerted on, so sampling it as a launch we did NOT alert
        # on would put one coin in both arms. That tier is default-off today,
        # which is exactly why the omission would go unnoticed until it wasn't.
        pool = [c for c in active if not c.confirmed and c.token not in conf_sent
                and c.token not in near_sent]
        c = sampler.choose(now, pool, key=lambda x: x.token)
        if c is None:
            return
        outcomes.record_control("pons.family", "ROBINHOOD",
                                str(c.symbol or c.token[:8]), c.token,
                                {"method": "dexscreener", "chainSlug": "robinhood",
                                 "address": c.token},
                                price0=c.price,
                                features=launch_features(c, dep_count(c.deployer)))

    def update_swaps(now):
        active = [c for c in coins.values() if c.is_active(now)]
        if not active:
            return
        sample_control(now, active)
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
                if c.token in conf_sent:      # already alerted before a restart
                    c.confirmed = True
                    continue
                # PRIOR launches = this deployer's other tokens (exclude the current one)
                prior = max(dep_count(c.deployer) - 1, 0)
                grads = dep_grads.get(c.deployer, 0)
                # anti-spam gate: serial deployer that never graduated = spam factory
                if prior > args.max_dev_launches and grads == 0:
                    c.confirmed = True  # stop re-checking, never alert
                    print(f"[{time.strftime('%H:%M:%S')}] SKIP spam-deployer "
                          f"{c.symbol or c.token[:8]} (dev {prior} prior, 0 grads)", flush=True)
                    continue
                c.pending_since = now
                c.fire_net = c.net_weth
                print(f"[{time.strftime('%H:%M:%S')}] PENDING {c.symbol or c.token[:8]} "
                      f"net={c.fire_net:.2f} — hold {args.hold:.0f}s", flush=True)

            # stage 2: hold elapsed -> confirm only if net did NOT collapse
            if c.pending_since is not None and (now - c.pending_since) >= args.hold:
                held = c.net_weth >= c.fire_net * args.hold_keep
                c.confirmed = True
                if not held:
                    print(f"[{time.strftime('%H:%M:%S')}] DROP pump-dump "
                          f"{c.symbol or c.token[:8]} (net {c.fire_net:.2f} -> {c.net_weth:.2f})",
                          flush=True)
                    continue
                soc = dex_socials(c.token, now)
                if args.require_social and (not soc.get("has") or soc.get("depth", 0) < args.min_socials):
                    print(f"[{time.strftime('%H:%M:%S')}] DROP no-social "
                          f"{c.symbol or c.token[:8]} (depth {soc.get('depth', 0)})", flush=True)
                    continue
                # soft gates — all default off; alerts display the values either way
                bs_ratio = c.n_buys / c.n_sells if c.n_sells else float("inf")
                if args.min_bs_ratio and bs_ratio < args.min_bs_ratio:
                    print(f"[{time.strftime('%H:%M:%S')}] DROP low-bs-ratio "
                          f"{c.symbol or c.token[:8]} ({bs_ratio:.1f} < {args.min_bs_ratio})", flush=True)
                    continue
                if args.min_liq_usd and soc.get("liq_usd") is not None and soc["liq_usd"] < args.min_liq_usd:
                    print(f"[{time.strftime('%H:%M:%S')}] DROP thin-liq "
                          f"{c.symbol or c.token[:8]} (${soc['liq_usd']:.0f})", flush=True)
                    continue
                if args.min_smart_score and c.smart_score < args.min_smart_score:
                    print(f"[{time.strftime('%H:%M:%S')}] DROP low-smart "
                          f"{c.symbol or c.token[:8]} (score {c.smart_score})", flush=True)
                    continue
                mark_conf(c.token)   # persisted BEFORE dispatch: restarts never re-alert
                paid = dex_paid(c.token, now)
                g = gmgn.snapshot("robinhood", c.token)   # one call: display + record
                dc = max(dep_count(c.deployer), 1)   # total launches by this deployer
                sc = score_confirmed(c, dc, soc, paid,
                                     holder_risk(c.token, c.pool, c.deployer, now))
                dispatch(fmt_confirmed(c, dc, args,
                                       c.fire_net, ethusd[0], now, soc, paid, g),
                         f"CONFIRMED {c.symbol or c.token[:8]}",
                         buttons=links(c.token, c.pool, soc),
                         record=dict(platform="pons.family", chain="ROBINHOOD", tier="CONFIRMED",
                                     symbol=c.symbol or c.token[:8], token=c.token, score=sc,
                                     track={"method": "dexscreener", "chainSlug": "robinhood", "address": c.token},
                                     price0=c.price, liq0=(soc or {}).get("liq_usd"), gmgn=g,
                                     # launch-time factors, for the score refit (Tier B backtest):
                                     # scores are opinions, these are the raw measurements.
                                     features=launch_features(c, dc)))

    nb_quiet_until = [0.0]   # boxed: back off recent-buys after it fails

    def check_neargrad(now):
        # recent-buys is the last pons.family dependency, and while that domain
        # is NXDOMAIN each call burns ~6s in urllib retries — inside the same
        # loop body as discovery, which stretched a 2s poll to ~11s and slowed
        # the CONFIRMED path this scanner exists for. Back off on failure rather
        # than dropping the call, so the coin state it feeds (pct/price) still
        # updates if the domain returns. #5 replaces the feed itself.
        if now < nb_quiet_until[0]:
            return
        try:
            feed = api.recent_buys()
        except Exception as e:  # noqa: BLE001
            nb_quiet_until[0] = now + 300
            print(f"  recent-buys error: {e} (backing off 5 min)", flush=True)
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
            if not args.neargrad:      # tier disabled: state updated above, but no alert
                continue
            if r.get("graduated") or pct < args.near:
                continue
            h = prog_hist[tok]
            vel = 0.0
            if len(h) >= 2 and h[-1][0] > h[0][0]:
                vel = (h[-1][1] - h[0][1]) / ((h[-1][0] - h[0][0]) / 60)
            if vel <= 0:
                continue
            # once per coin: the 600s re-fire spammed one coin up to 33× in 11h
            # and near-grad re-alerts added no value (outcome tracking, 2026-07-18).
            if tok in near_sent:
                continue
            sym = (coins[tok].symbol if tok in coins else None) or r.get("symbol") \
                or api.token_symbol(tok) or tok[:8]
            soc = dex_socials(tok, now)
            paid = dex_paid(tok, now)
            price_f = _f(price)
            sc = score_neargrad(pct, vel, soc, paid, holders(tok, now))
            dispatch(fmt_neargrad(tok, sym, pct, paired, vel, price_f, launched_at, ethusd[0], now, soc, paid),
                     f"NEAR-GRAD {sym or tok[:8]}",
                     buttons=links(tok, r.get("pool"), soc),
                     record=dict(platform="pons.family", chain="ROBINHOOD", tier="NEAR-GRAD",
                                 symbol=sym or tok[:8], token=tok, score=sc,
                                 track={"method": "dexscreener", "chainSlug": "robinhood", "address": tok},
                                 price0=price_f, liq0=(soc or {}).get("liq_usd")))
            near_sent[tok] = now   # mark AFTER dispatch: a format/send error re-arms, no permanent miss

    # --- DexScreener marketing feed: teams paying for a profile/boost on our chain.
    # Money spent on marketing is intent to push; the feed also surfaces coins from
    # OTHER Robinhood-chain launchpads (flap etc.) that pons/latest never sees.
    mkt_seen = set()
    mkt_seeded = set()   # which endpoints have had one successful fetch (seeded)

    def check_marketing(now):
        import urllib.request
        found = {}  # token -> note
        for url, kind in (("https://api.dexscreener.com/token-profiles/latest/v1", "profile"),
                          ("https://api.dexscreener.com/token-boosts/latest/v1", "boost")):
            try:
                req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0",
                                                           "accept": "application/json"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    items = json.loads(r.read())
            except Exception as e:  # noqa: BLE001
                print(f"  marketing feed error ({kind}): {e}", flush=True)
                continue
            first = kind not in mkt_seeded   # seed THIS endpoint on its first success
            for it in items or []:
                if it.get("chainId") != "robinhood":
                    continue
                tok = (it.get("tokenAddress") or "").lower()
                if not tok:
                    continue
                if first:
                    mkt_seen.add(tok)        # silently seed this endpoint's backlog
                    continue
                if tok in mkt_seen:
                    continue
                note = kind if kind == "profile" else f"boost x{it.get('totalAmount') or it.get('amount') or '?'}"
                found.setdefault(tok, []).append(note)
            mkt_seeded.add(kind)
        if not found:
            return
        for tok, notes in found.items():
            mkt_seen.add(tok)
            soc = dex_socials(tok, now)
            sym = (coins[tok].symbol if tok in coins else None) or api.token_symbol(tok) or (tok[:10] + "…")
            origin = "🐸 pons.family" if tok in coins else ("🦇 flap.sh" if tok.endswith("7777") else "❓ unknown launchpad")
            dispatch("\n".join([
                f"💰 <b>MARKETING</b> — <b>{html.escape(str(sym))}</b> · {origin} · ⛓ <b>ROBINHOOD</b>",
                f"team paid DexScreener: <b>{' + '.join(notes)}</b>",
                social_line(soc),
                f'<a href="{BLOCKSCOUT}{tok}">{tok[:12]}…</a>',
            ]), f"MARKETING {sym}", buttons=links(tok, None, soc),
                record=dict(platform="pons.family", chain="ROBINHOOD", tier="MARKETING",
                            symbol=str(sym), token=tok, score=None,
                            track={"method": "dexscreener", "chainSlug": "robinhood", "address": tok},
                            liq0=(soc or {}).get("liq_usd")))

    print("running… Ctrl-C to stop", flush=True)
    last_eth = [time.time()]
    last_mkt = [0.0]
    while True:
        try:
            now = time.time()
            if now - last_eth[0] > 300:      # refresh ETH price every 5 min
                last_eth[0] = now            # stamp first: a slow provider must not queue refreshes
                threading.Thread(target=refresh_eth, daemon=True).start()
            register_launches()
            update_swaps(now)
            pruned = prune_coins(coins, now)
            if pruned:
                print(f"[{time.strftime('%H:%M:%S')}] -{len(pruned)} stale "
                      f"({len(coins)} tracked)", flush=True)
            check_neargrad(now)
            if args.marketing_feed and now - last_mkt[0] > 75:  # 2 calls per pass, 60 rpm cap
                check_marketing(now)
                last_mkt[0] = now
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  loop error: {e}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
