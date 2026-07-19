"""Virtuals Protocol scanner — AI-agent launches on Base (+ dormant Solana).

app.virtuals.io launches AI-agent tokens on a bonding curve (UNDERGRAD) that
graduates to a Uniswap LP once the curve reserve reaches 42k VIRTUAL
(tiers 21k/42k/100k — /api/geneses/parameters). Backend api2.virtuals.io is a
fully open Strapi: plain urllib, no Cloudflare, standard query syntax.

Unlike the Robinhood-chain launchpads, the API hands us premium per-agent
fields in the LIST response: mindshare (attention score), holderCount +
holderCountPercent24h, devHoldingPercentage, top10HolderPercentage, volume24h,
totalValueLocked (= curve reserve in VIRTUAL → graduation progress), socials,
isVerified/isDevCommitted, launchInfo (anti-sniper tax, launch mode).

Quirks (verified 2026-07-17):
  - filters[status] is silently ignored -> filter client-side
    (on-curve = preToken set & tokenAddress null).
  - the createdAt feed contains duplicate rows -> dedupe by id.
  - launch rate ~100/day on BASE; SOLANA dormant since 2026-06 (cheap 10-min poll).

Alert tiers (every alert carries a ⛓ chain tag):
  🐣 EARLY      young agent crossing the traction bar (holders + curve reserve),
                gated on dev%/top10% concentration
  🔥 NEAR-GRAD  curve reserve >= --near% of graduation (catches agents born
                before the scanner started too, via the volume board)

The traction bar is a v1 heuristic — every launch/alert/expiry is logged to
data/events.jsonl to refit thresholds once outcomes accumulate.

Detect + rank + alert only. It never trades.

Usage:
    python3 virtuals/scan.py --dry-run
    python3 virtuals/scan.py            # live -> Telegram (pons/.env creds)
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
sys.path.insert(0, os.path.join(HERE, "..", "pons"))   # telegram sender + alert format
import alertfmt  # noqa: E402
import controls  # noqa: E402
import outcomes  # noqa: E402
import telegram  # noqa: E402

DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

API = "https://api2.virtuals.io/api"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Accept": "application/json", "Origin": "https://app.virtuals.io",
      "Referer": "https://app.virtuals.io/"}
GRAD_RESERVE = 42_000            # default graduation tier (VIRTUAL)
CHAINS = {"BASE": 30, "SOLANA": 600}   # chain -> poll interval (s); Solana is dormant


def api_get(path, **params):
    """GET api2.virtuals.io. Returns parsed JSON or None (never raises)."""
    qs = urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(f"{API}/{path}?{qs}", headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        print(f"  api error {path}: {e}", flush=True)
        return None


def list_virtuals(chain, sort, page_size=25, **extra):
    d = api_get("virtuals", **{"filters[chain]": chain, "sort": sort,
                               "pagination[pageSize]": page_size, **extra})
    if d is None:                 # API failure — distinguish from a genuine empty list
        return None
    return d.get("data") or []


def log_event(kind, **kw):
    try:
        with open(os.path.join(DATA, "events.jsonl"), "a") as f:
            f.write(json.dumps({"t": time.time(), "kind": kind, **kw}) + "\n")
    except Exception:  # noqa: BLE001
        pass


def human(x, unit=""):
    if x is None:
        return "?"
    x = float(x)
    if x >= 1_000_000:
        return f"{x/1e6:.1f}M{unit}"
    if x >= 1_000:
        return f"{x/1e3:.0f}K{unit}"
    return f"{x:.0f}{unit}"


def on_curve(r):
    """Still bonding: has a curve token, no LP token yet."""
    return bool(r.get("preToken")) and not r.get("tokenAddress")


def progress_pct(r):
    tvl = r.get("totalValueLocked")
    try:
        return 100.0 * float(tvl) / GRAD_RESERVE
    except (TypeError, ValueError):
        return 0.0


def links(r):
    vid = r.get("id")
    tok = r.get("tokenAddress") or r.get("preToken") or ""
    rows = [[("🤖 virtuals", f"https://app.virtuals.io/virtuals/{vid}")]]
    if tok and (r.get("chain") or "").upper() == "BASE":
        rows[0].append(("📈 DexScreener", f"https://dexscreener.com/base/{tok}"))
    return rows


def fnum(r, key, default=0.0):
    try:
        return float(r.get(key) or default)
    except (TypeError, ValueError):
        return default


def launch_features(r, now=None, born=None):
    """Raw launch-time measurements for one virtuals alert (#7).

    Mirrors pons/alert_pro.py launch_features: measurements only, never scores,
    and None means "not measured" — distinct from 0.

    Deliberately does NOT use fnum(): that defaults to 0.0 so the cohort pass
    can't crash on one of Strapi's stringified numerics, which would report
    every agent Strapi declined to describe as having 0% dev holdings and 0
    holders — the most flattering possible reading of a total absence of data.
    outcomes.num() keeps the same string coercion but returns None instead.

    `born` is when this scanner first saw the agent, so age is None for the
    NEAR-GRAD tier, which scans a volume board that includes agents born before
    the scanner started.
    """
    soc = r.get("socials") or {}
    channels = {k.upper(): v for k, v in soc.items()}
    return dict(
        socials_n=sum(1 for v in soc.values() if v),
        # feed_* rather than has_*: row["gmgn"] carries GMGN's own has_x/has_tg/
        # has_web, measured independently. Distinct names keep both readable if
        # the refit ever flattens f and gmgn into one vector.
        feed_has_x=bool(channels.get("TWITTER")), feed_has_tg=bool(channels.get("TELEGRAM")),
        feed_has_web=bool(channels.get("WEBSITE")),
        verified=bool(r.get("isVerified")), dev_committed=bool(r.get("isDevCommitted")),
        dev_pct=outcomes.num(r.get("devHoldingPercentage")),
        top10_pct=outcomes.num(r.get("top10HolderPercentage")),
        feed_holders=outcomes.num(r.get("holderCount")),
        holders_24h_pct=outcomes.num(r.get("holderCountPercent24h")),
        vol24h=outcomes.num(r.get("volume24h")),
        liq=outcomes.num(r.get("liquidityUsd")),
        mcap_virtual=outcomes.num(r.get("mcapInVirtual")),
        price_24h_pct=outcomes.num(r.get("priceChangePercent24h")),
        mindshare=outcomes.num(r.get("mindshare")),
        tvl=outcomes.num(r.get("totalValueLocked")),
        progress=round(progress_pct(r), 4),
        age_s=round(now - born, 2) if (now is not None and born is not None) else None,
    )


def score_agent(r, tier_base, progress):
    """Heuristic 0-100 from the premium list fields. Base per tier; quality,
    momentum and concentration shift it. v1 judgment weights — refit later."""
    s = float(tier_base)
    s += min(max(progress - 70, 0), 30) * 0.4 if tier_base == 40 else 0   # near-grad ramp
    # Recalibrated 2026-07-19 against a REAL died-control (wave 22): 69 graduated
    # vs 346 on-curve agents >48h old that never graduated. socials/dev-flags are
    # set at launch, so unlike holder counts they are NOT age-confounded.
    s += 10 if r.get("isVerified") else 0        # 6% grad vs 0% died — zero FPs
    s += 10 if r.get("isDevCommitted") else 0    # 12% grad vs 0% died — zero FPs
    s += 6 if fnum(r, "mindshare") > 0 else 0
    s += 6 if fnum(r, "holderCountPercent24h") >= 10 else 0
    s += 5 if fnum(r, "volume24h") >= 10_000 else 0
    dev = fnum(r, "devHoldingPercentage")
    s += 5 if dev < 10 else (-6 if dev >= 15 else 0)
    # NO top10 penalty on virtuals: graduated agents sit at ~72% top10 (wave 20),
    # so concentration here is native to the platform and the old `-6 if t10>=80`
    # was penalising winners. Deliberately unscored.
    # Also deliberately unscored: antiSniperTax (13% grad vs 98% died looks like a
    # huge signal but is a TEMPORAL CONFOUND — it became the default launch config
    # recently, so it mostly dates a coin). See wave 22.
    # socials = the dominant separator found on ANY of our platforms: 96% grad vs
    # 2% died. Treated as a near-gate, not a +2-per-channel bit.
    soc = r.get("socials") or {}
    n_soc = sum(1 for v in soc.values() if v) if isinstance(soc, dict) else 0
    s += (12 + min(n_soc - 1, 2) * 3) if n_soc else -20
    return alertfmt.clamp(s)


def pros_cons(r, lead):
    """Shared pros/cons split from the quality fields; `lead` is the tier's
    headline pro line (traction or progress)."""
    pros = [lead]
    bits = []
    if r.get("isVerified"):
        bits.append("✅ verified")
    if r.get("isDevCommitted"):
        bits.append("🤝 dev-committed")
    if fnum(r, "mindshare") > 0:
        bits.append(f"🧠 mindshare {r.get('mindshare')}")
    soc = r.get("socials") or {}
    if isinstance(soc, dict) and any(soc.values()):
        bits.append("🔗 " + "·".join(sorted(k for k, v in soc.items() if v)[:3]))
    if bits:
        pros.append(" · ".join(bits))
    cons = []
    dev = fnum(r, "devHoldingPercentage")
    t10 = fnum(r, "top10HolderPercentage")
    if dev >= 15:
        cons.append(f"dev holds {dev:.0f}%")
    if t10 >= 80:
        cons.append(f"top10 {t10:.0f}%")
    if isinstance(soc, dict) and not any(soc.values()):
        cons.append("no socials")
    return pros, cons


def agent_link(r):
    return f'<a href="https://app.virtuals.io/virtuals/{r.get("id")}">agent #{r.get("id")}</a>'


def track_of(r):
    """How the tracker should follow this agent later. Graduated agents have a
    real tokenAddress on a DEX; on-curve ones are only priced by the Virtuals API."""
    tok = r.get("tokenAddress")
    chain = (r.get("chain") or "").upper()
    if tok and chain in ("BASE", "SOLANA"):
        return {"method": "dexscreener", "chainSlug": chain.lower(), "address": tok}
    return {"method": "virtuals", "id": r.get("id")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=30.0, help="BASE new-agent poll (s)")
    ap.add_argument("--watch-hours", type=float, default=48.0,
                    help="how long a new agent stays in the tracked cohort")
    # v1 heuristic bar — on-curve traction is sparse (3 on-curve agents in the
    # top-50 volume board when probed); refit from data/events.jsonl later.
    ap.add_argument("--min-holders", type=int, default=25)
    ap.add_argument("--min-reserve", type=float, default=1000.0,
                    help="curve reserve (VIRTUAL) to qualify as EARLY (~2.4%% progress)")
    ap.add_argument("--max-dev-pct", type=float, default=30.0)
    ap.add_argument("--max-top10-pct", type=float, default=95.0)
    ap.add_argument("--near", type=float, default=70.0, help="NEAR-GRAD progress %%")
    # Shadow-control sampling (#9): agents we watched and passed over, tracked
    # so the alerted ones have a base rate to be measured against.
    controls.add_args(ap)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)
    print(f"virtuals scanner  chains={'/'.join(CHAINS)}  bar: holders>={args.min_holders} "
          f"& reserve>={args.min_reserve:.0f}V & dev<={args.max_dev_pct:.0f}% "
          f"near>={args.near:.0f}% of {GRAD_RESERVE}V  "
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

    tracked = {}      # id -> {"born": ts, "row": latest row, "early": bool}
    sampler = controls.ControlSampler("virtuals.io", k=args.controls_k,
                                      bucket_s=args.controls_bucket_s,
                                      state_path=os.path.join(DATA, "control_slot.json"))
    near_sent = set() # agent ids alerted NEAR-GRAD (once each)
    seeded = [False]  # first createdAt pass registers without alerting backlog
    near_seeded = [False]  # first volume-board pass suppresses near-grad backlog

    def poll_new(chain, now):
        rows = list_virtuals(chain, "createdAt:desc")
        if rows is None:            # API failure — do NOT let this count as "seeded"
            return False
        for r in rows:
            aid = r.get("id")
            if aid is None or aid in tracked or not on_curve(r):
                continue
            # pre-existing agents at startup are context: mark BOTH tiers done so
            # they never replay as backlog (the seeded flag used to gate only the
            # log line, so every qualifying agent alerted on each restart).
            pre = not seeded[0]
            tracked[aid] = {"born": now, "row": r, "early": pre}
            if pre:
                near_sent.add(aid)   # also suppress a startup NEAR-GRAD replay
            else:
                log_event("launch", id=aid, chain=r.get("chain"), sym=r.get("symbol"))
                print(f"[{time.strftime('%H:%M:%S')}] new agent {r.get('symbol')} ({chain})", flush=True)
        return True

    def refresh_cohort(now):
        """Batch-refresh tracked agents by id (25 per call), prune the old."""
        ids = [aid for aid, t in tracked.items()
               if (now - t["born"]) <= args.watch_hours * 3600]
        for aid in set(tracked) - set(ids):
            t = tracked.pop(aid)
            if not t["early"]:
                r = t["row"]
                log_event("expired", id=aid, sym=r.get("symbol"),
                          holders=r.get("holderCount"), tvl=r.get("totalValueLocked"))
        for i in range(0, len(ids), 25):
            chunk = ids[i:i + 25]
            params = {f"filters[id][$in][{j}]": v for j, v in enumerate(chunk)}
            d = api_get("virtuals", **{"pagination[pageSize]": 25, **params})
            for r in (d or {}).get("data") or []:
                aid = r.get("id")
                if aid in tracked:
                    tracked[aid]["row"] = r

    def sample_control(now):
        """Take one on-curve agent we have not alerted on as a control (#9).

        Drawn from the same watched cohort EARLY alerts come from, so a control
        enters the tracker at a comparable point in an agent's life. Agents
        seeded at startup are excluded: they were marked done rather than
        evaluated, so we never actually passed on them."""
        pool = [(aid, t) for aid, t in tracked.items()
                if not t["early"] and on_curve(t["row"])]
        picked = sampler.choose(now, pool, key=lambda x: x[0])
        if picked is None:
            return
        aid, t = picked
        r = t["row"]
        outcomes.record_control("virtuals.io", (r.get("chain") or "?").upper(),
                                str(r.get("symbol") or aid),
                                r.get("tokenAddress") or r.get("preToken") or str(aid),
                                track_of(r),
                                mcap0=r.get("mcapInVirtual"), liq0=r.get("liquidityUsd"),
                                features=launch_features(r, now=now, born=t["born"]))

    def check_candidates(now):
        sample_control(now)
        for aid, t in tracked.items():
            r = t["row"]
            if t["early"] or not on_curve(r):
                continue
            # fnum() throughout: Strapi returns several numerics as strings, and a
            # raw `"30" < 25` comparison would raise and abort the whole cohort pass.
            holders = fnum(r, "holderCount")
            tvl = fnum(r, "totalValueLocked")
            if holders < args.min_holders or tvl < args.min_reserve:
                continue
            t["early"] = True     # one shot, decided before the gates
            dev = fnum(r, "devHoldingPercentage")
            t10 = fnum(r, "top10HolderPercentage")
            if dev > args.max_dev_pct or t10 > args.max_top10_pct:
                log_event("skip_concentration", id=aid, sym=r.get("symbol"), dev=dev, top10=t10)
                print(f"[{time.strftime('%H:%M:%S')}] SKIP concentration {r.get('symbol')} "
                      f"(dev {dev:.0f}% top10 {t10:.0f}%)", flush=True)
                continue
            prog = progress_pct(r)
            age_h = (now - t["born"]) / 3600
            score = score_agent(r, 45, prog)
            pros, cons = pros_cons(r, f"👥 <b>{holders}</b> holders (Δ24h {r.get('holderCountPercent24h')}%) "
                                      f"· 💰 reserve {human(tvl, 'V')} · 📊 {prog:.0f}% · ⏱️ {age_h:.1f}h")
            stats = [f"vol24h {human(r.get('volume24h'), '$')} · liq {human(r.get('liquidityUsd'), '$')} "
                     f"· Δprice24h {r.get('priceChangePercent24h')}%"]
            body = alertfmt.compose(score, "🐣", "VIRTUALS EARLY",
                                    f"{html.escape(str(r.get('symbol') or '?'))} {html.escape(str(r.get('name') or ''))}".strip(),
                                    "🤖 virtuals.io", (r.get("chain") or "?").upper(),
                                    pros, cons, stats, agent_link(r))
            log_event("early_alert", id=aid, chain=r.get("chain"), sym=r.get("symbol"),
                      holders=holders, tvl=tvl, progress=prog)
            dispatch(body, f"VIRTUALS EARLY {r.get('symbol')}", buttons=links(r),
                     record=dict(platform="virtuals.io", chain=(r.get("chain") or "?").upper(),
                                 tier="VIRTUALS EARLY", symbol=str(r.get("symbol") or aid),
                                 token=r.get("tokenAddress") or r.get("preToken") or str(aid),
                                 score=score, track=track_of(r),
                                 mcap0=r.get("mcapInVirtual"), liq0=r.get("liquidityUsd"),
                                 features=launch_features(r, now=now, born=t["born"])))

    def check_neargrad(now):
        """Volume board scan: catches curves nearing graduation even if they were
        born before this scanner started."""
        rows = list_virtuals("BASE", "volume24h:desc", page_size=50)
        if rows is None:
            return
        for r in rows:
            aid = r.get("id")
            if aid is None or aid in near_sent or not on_curve(r):
                continue
            prog = progress_pct(r)
            if prog < args.near:
                continue
            near_sent.add(aid)
            if not near_seeded[0]:
                continue    # first pass after startup: suppress the board's backlog
            score = score_agent(r, 40, prog)
            pros, cons = pros_cons(r, f"📊 <b>{prog:.0f}%</b> to grad ({human(r.get('totalValueLocked'), 'V')}"
                                      f"/{GRAD_RESERVE//1000}KV) · 👥 {r.get('holderCount')} holders")
            stats = [f"vol24h {human(r.get('volume24h'), '$')} · mcap {human(r.get('mcapInVirtual'), 'V')} "
                     f"· Δ24h {r.get('priceChangePercent24h')}%"]
            body = alertfmt.compose(score, "🔥", "VIRTUALS NEAR-GRAD",
                                    html.escape(str(r.get("symbol") or "?")),
                                    "🤖 virtuals.io", (r.get("chain") or "?").upper(),
                                    pros, cons, stats, agent_link(r))
            log_event("neargrad_alert", id=aid, chain=r.get("chain"),
                      sym=r.get("symbol"), progress=prog)
            dispatch(body, f"VIRTUALS NEAR-GRAD {r.get('symbol')}", buttons=links(r),
                     record=dict(platform="virtuals.io", chain=(r.get("chain") or "?").upper(),
                                 tier="VIRTUALS NEAR-GRAD", symbol=str(r.get("symbol") or aid),
                                 token=r.get("tokenAddress") or r.get("preToken") or str(aid),
                                 score=score, track=track_of(r),
                                 mcap0=r.get("mcapInVirtual"), liq0=r.get("liquidityUsd"),
                                 features=launch_features(r)))

    print("running… Ctrl-C to stop", flush=True)
    last = {"BASE": 0.0, "SOLANA": 0.0, "cohort": 0.0, "near": 0.0}
    while True:
        try:
            now = time.time()
            base_ok = sol_ok = True
            if now - last["BASE"] >= args.interval:
                base_ok = poll_new("BASE", now)
                last["BASE"] = now
            if now - last["SOLANA"] >= CHAINS["SOLANA"]:
                sol_ok = poll_new("SOLANA", now)
                last["SOLANA"] = now
            # only mark seeded once a poll actually succeeded, else a startup API
            # blip would make the next good poll replay the whole backlog as new
            if not seeded[0] and base_ok and sol_ok:
                seeded[0] = True
                print(f"seeded {len(tracked)} existing on-curve agents (no backlog alerts)", flush=True)
            if seeded[0] and now - last["cohort"] >= 60:
                refresh_cohort(now)
                check_candidates(now)
                last["cohort"] = now
            if seeded[0] and now - last["near"] >= 300:
                check_neargrad(now)
                near_seeded[0] = True   # subsequent passes may alert; first only seeds
                last["near"] = now
            time.sleep(5)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  loop error: {e}", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
