"""pons.family 1-second scanner with Telegram alerts.

Polls the pons momentum feed every second, tracks each coin's climb toward the
4.2 ETH graduation threshold, and pushes a Telegram message the moment a coin
starts CLIMBING or gets NEAR-GRAD. Detect + alert only — it never trades.

Credentials: env TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID, or data/telegram.json.
With no credentials it runs in dry-run mode (prints the messages instead).

Usage:
    python3 analysis/pons/alert.py                 # live, 1s, Telegram (or dry-run)
    python3 analysis/pons/alert.py --dry-run       # force print-only
    python3 analysis/pons/alert.py --test          # send one test message and exit
    python3 analysis/pons/alert.py --interval 1 --min-vel 0.1 --near 70
"""
from __future__ import annotations

import argparse
import html
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import api  # noqa: E402
import telegram  # noqa: E402
from scan import Tracker, load_reputation, load_launch_seed, parse_ts  # noqa: E402

BLOCKSCOUT = "https://robinhoodchain.blockscout.com/token/"
RE_ALERT_COOLDOWN = 180   # don't re-send the same token+level within this many seconds


def eta_minutes(paired, vel_per_min):
    if vel_per_min <= 0:
        return None
    remaining = api.GRAD_THRESHOLD_ETH - paired
    if remaining <= 0:
        return 0.0
    return remaining / vel_per_min


def fmt_alert(level, tok, m, vel):
    sym = html.escape(str(m.get("symbol") or tok[:8]))
    pct = m.get("pct", 0)
    paired = m.get("paired", 0.0)
    price = m.get("price")
    eta = eta_minutes(paired, vel)
    emoji = "🔥" if level == "NEAR-GRAD" else "🚀"
    lines = [
        f"{emoji} <b>{level}</b> — <b>{sym}</b>",
        f"progress <b>{pct:.0f}%</b> · {paired:.2f}/{api.GRAD_THRESHOLD_ETH} ETH",
        f"vel <b>{vel:+.2f}</b> ETH/min" + (f" · ETA ~{eta:.1f}m" if eta is not None else ""),
    ]
    if price:
        lines.append(f"price ${price:.8f}")
    lines.append(f'<a href="{BLOCKSCOUT}{tok}">{tok[:12]}…</a>')
    return "\n".join(lines)


def decide(tok, tr, min_vel, near_pct):
    m = tr.meta.get(tok, {})
    pct = m.get("pct", 0.0)
    vel = tr.velocity(tok)
    if m.get("graduated"):
        return None
    if pct >= near_pct and vel > 0:
        return "NEAR-GRAD"
    if vel >= min_vel and pct >= 10:
        return "CLIMBING"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--min-vel", type=float, default=0.10, help="ETH/min climb to trigger CLIMBING")
    ap.add_argument("--near", type=float, default=70.0, help="progress %% for NEAR-GRAD")
    ap.add_argument("--fresh-min", type=float, default=45.0, help="only alert coins younger than this (min), unless near-grad")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    if args.test:
        ok, info = telegram.send("✅ pons scanner: Telegram wired up.")
        print("OK" if ok else "FAIL", "-", info)
        return

    token, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token and chat_id)
    mode = "DRY-RUN (printing)" if dry else f"Telegram chat {chat_id}"
    print(f"pons alert loop  interval={args.interval}s  min_vel={args.min_vel}ETH/min  "
          f"near={args.near}%  -> {mode}")
    if dry and not args.dry_run:
        print("  (no credentials found — set TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID or data/telegram.json)")

    rep = load_reputation()
    tr = Tracker(seed=load_launch_seed())
    last_sent = {}   # token -> (level, ts)

    def dispatch(text, label):
        stamp = time.strftime("%H:%M:%S")
        if dry:
            print("---\n" + text.replace("<b>", "").replace("</b>", "")
                  .replace("<a href=\"", "").replace("\">", " ").replace("</a>", ""))
            return
        ok, info = telegram.send(text, token, chat_id)
        if ok:
            print(f"[{stamp}] sent -> {label}", flush=True)
        else:
            print(f"[{stamp}] telegram send FAILED ({label}): {info}", flush=True)

    def poll():
        now = time.time()
        try:
            for L in api.latest():
                tr.note_launch(L)
        except Exception as e:  # noqa: BLE001
            print(f"  latest error: {e}")
        try:
            for r in api.recent_buys():
                tr.note_buy(r, now)
        except Exception as e:  # noqa: BLE001
            print(f"  recent-buys error: {e}")
            return

        fresh_secs = args.fresh_min * 60
        for tok, m in list(tr.meta.items()):
            if m.get("pct", 0) <= 0 or m.get("graduated"):
                continue
            lvl = decide(tok, tr, args.min_vel, args.near)
            if not lvl:
                continue
            lt = parse_ts(m.get("launchedAt"))
            age = (now - lt) if lt else None
            if lvl == "CLIMBING" and age is not None and age > fresh_secs:
                continue  # stale climber; NEAR-GRAD always passes
            prev = last_sent.get(tok)
            # send on first alert, on escalation to NEAR-GRAD, or after cooldown
            escalate = prev and prev[0] == "CLIMBING" and lvl == "NEAR-GRAD"
            if prev and not escalate and (now - prev[1]) < RE_ALERT_COOLDOWN and prev[0] == lvl:
                continue
            last_sent[tok] = (lvl, now)
            sym = m.get("symbol") or tok[:8]
            dispatch(fmt_alert(lvl, tok, m, tr.velocity(tok)), f"{lvl} {sym}")

    print("running… Ctrl-C to stop")
    while True:
        try:
            poll()
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped")
            break
        except Exception as e:  # noqa: BLE001
            print(f"  loop error: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()
