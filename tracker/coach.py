"""Exit coach — the missing half of the trade (redesign-v2 P4).

The tracker proved that entries alone leave half the money on the table:
flap winners peak at median +517% but sit at +263% by 4h. Nobody said "take
profit". This daemon follows every OPEN alert (age < 8h, has Telegram
metadata) by re-pricing it every ~2.5 min via the same per-method snapshot
dispatch tracker/track.py uses, and fires each milestone ONCE:

    🎯 2x   ret >= +100%                        -> bubble edit + reply ping
    🚀 5x   ret >= +400%                        -> bubble edit + reply ping
    ⚠️ retrace  was >=2x, gave back half of peak -> bubble edit + reply ping
    💀 dead ret <= -70% and age >= 30m          -> bubble edit only (no rush)

Bubble edits go through telegram.append_to_alert (shared journal with the AI
analyst — the two daemons grow the same message without wiping each other).
Reply pings actually notify (edits don't), because a 2x is actionable NOW.

Every milestone is journaled to data/coach_events.jsonl so the coach itself
gets judged later (does sell-half-at-2x beat holding to 4h? the data will
say). State survives restarts in data/coach_state.json.

Detect + advise only. It never trades.

Usage:
    python3 tracker/coach.py --dry-run     # print milestones, no Telegram
    python3 tracker/coach.py               # live (LaunchAgent: com.sunrise.coach)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "pons"))
sys.path.insert(0, HERE)
import telegram  # noqa: E402
import track as trk  # noqa: E402   (take_snapshot: per-method price dispatch)

DATA = os.path.join(HERE, "data")
ALERTS = os.path.join(DATA, "alerts.jsonl")
STATE = os.path.join(DATA, "coach_state.json")
EVENTS = os.path.join(DATA, "coach_events.jsonl")

WINDOW_S = 8 * 3600       # how long an alert stays coached
DEAD_MIN_AGE = 30 * 60    # don't call 💀 on launch wicks


def _num(x):
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def base_of(a):
    """(baseline value, metric) — same convention as report/analyze."""
    if _num(a.get("price0")):
        return _num(a["price0"]), "price"
    if _num(a.get("mcap0")):
        return _num(a["mcap0"]), "mcap"
    return None, None


def age_str(sec):
    return f"{sec/3600:.1f}h" if sec >= 3600 else f"{sec/60:.0f}m"


def log_event(**kw):
    try:
        with open(EVENTS, "a") as f:
            f.write(json.dumps({"t": time.time(), **kw}, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def check_milestones(st, ret, age_s):
    """Pure decision: which milestones fire now. st holds peak + fired list."""
    fired = []
    peak = st.get("peak")
    st["peak"] = ret if peak is None else max(peak, ret)
    done = st.setdefault("done", [])
    if "x2" not in done and ret >= 1.0:
        fired.append("x2")
    if "x5" not in done and ret >= 4.0:
        fired.append("x5")
    if ("retrace" not in done and "x2" in done + fired
            and st["peak"] >= 1.0 and (1 + ret) <= 0.5 * (1 + st["peak"])):
        fired.append("retrace")
    if "dead" not in done and ret <= -0.7 and age_s >= DEAD_MIN_AGE and st["peak"] < 1.0:
        fired.append("dead")
    done.extend(fired)
    return fired


def milestone_texts(m, sym, ret, peak, age_s):
    """(bubble_line, ping_text|None)"""
    a = age_str(age_s)
    if m == "x2":
        return (f"\n🎯 <b>2x</b> +{ret*100:.0f}% @{a} — take initials out",
                f"🎯 <b>{sym}</b> ถึง <b>2x</b> (+{ret*100:.0f}% ใน {a}) — พิจารณาเอาทุนออก")
    if m == "x5":
        return (f"\n🚀 <b>5x</b> +{ret*100:.0f}% @{a}",
                f"🚀 <b>{sym}</b> ถึง <b>5x</b> (+{ret*100:.0f}% ใน {a})")
    if m == "retrace":
        return (f"\n⚠️ gave back half from peak (peak +{peak*100:.0f}%, now +{ret*100:.0f}%)",
                f"⚠️ <b>{sym}</b> ย่อครึ่งจาก peak (+{peak*100:.0f}% → +{ret*100:.0f}%) — พิจารณาปิดที่เหลือ")
    if m == "dead":
        return (f"\n💀 {ret*100:.0f}% from entry @{a} — likely done", None)
    return (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=150.0)
    ap.add_argument("--max-per-loop", type=int, default=80)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)
    try:
        state = json.load(open(STATE))
    except Exception:  # noqa: BLE001
        state = {}
    print(f"exit coach  window {WINDOW_S//3600}h · milestones 2x/5x/retrace/dead  "
          f"-> {'DRY-RUN' if dry else f'Telegram {chat_id}'}", flush=True)

    while True:
        try:
            now = time.time()
            rows = []
            if os.path.exists(ALERTS):
                for ln in open(ALERTS, "rb"):
                    try:
                        a = json.loads(ln)
                    except Exception:  # noqa: BLE001
                        continue
                    if (now - a.get("t", 0) < WINDOW_S and (a.get("tg") or {}).get("msg_id")
                            and a.get("track")):
                        rows.append(a)
            rows = sorted(rows, key=lambda a: -a["t"])[:args.max_per_loop]
            for a in rows:
                aid = f"{a['t']:.0f}:{a.get('token')}"
                st = state.setdefault(aid, {})
                if len(st.get("done", [])) >= 3:
                    continue
                base, metric = base_of(a)
                if base is None:              # alert had no price0/mcap0 (e.g. flap
                    base, metric = st.get("base"), st.get("metric")
                snap = trk.take_snapshot(a["track"]) or {}
                if base is None:
                    # adopt the first sighting as baseline (metric pinned in
                    # state so later loops never flip price<->mcap) and start
                    # measuring from the NEXT loop
                    for mtr in ("price", "mcap"):
                        v = _num(snap.get(mtr))
                        if v:
                            st["base"], st["metric"] = v, mtr
                            break
                    continue
                cur = _num(snap.get(metric))
                if not cur:
                    continue
                ret = cur / base - 1
                age_s = now - a["t"]
                for m in check_milestones(st, ret, age_s):
                    sym = a.get("symbol") or "?"
                    line, ping = milestone_texts(m, sym, ret, st.get("peak") or ret, age_s)
                    log_event(kind=m, id=aid, sym=sym, tier=a.get("tier"),
                              ret=round(ret, 3), peak=round(st.get("peak") or ret, 3),
                              age_s=int(age_s))
                    if dry:
                        print(f"[{time.strftime('%H:%M:%S')}] {sym} {m} ret {ret*100:+.0f}%"
                              f" -> {line.strip()}", flush=True)
                        continue
                    ok, _ = telegram.append_to_alert(a, line, token_tg, chat_id)
                    if ping:
                        telegram.send(ping, token_tg, chat_id,
                                      reply_to=(a.get("tg") or {}).get("msg_id"))
                    print(f"[{time.strftime('%H:%M:%S')}] {sym}: {m} ret {ret*100:+.0f}% "
                          f"({'bubble+ping' if ping else 'bubble'}{'' if ok else ' EDIT-FAILED'})",
                          flush=True)
                time.sleep(0.15)      # be gentle across price APIs
            # prune state for closed alerts
            state = {k: v for k, v in state.items()
                     if float(k.split(":")[0]) > now - WINDOW_S - 3600}
            try:
                json.dump(state, open(STATE, "w"))
            except Exception:  # noqa: BLE001
                pass
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  loop error: {e}", flush=True)
            time.sleep(15)


if __name__ == "__main__":
    main()
