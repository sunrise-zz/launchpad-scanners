"""AI second-opinion daemon — Hermes Agent DD on freshly fired alerts.

The scanners stay deterministic (their ~44s detection edge must never wait on
an LLM). This daemon runs BEHIND them: it tails tracker/data/alerts.jsonl,
and for each new alert in --tiers it invokes Hermes Agent headlessly with the
`memecoin-dd` skill (agent/skill/memecoin-dd/SKILL.md, symlinked into
~/.hermes/skills/). The agent runs GMGN forensics via pons/gmgn.py, checks
the X account quality and the narrative, then must end with a strict block:

    VERDICT: BUY-WATCH | NEUTRAL | AVOID
    CONF: 0-100
    WHY1..3: cited facts

The parsed verdict is (a) posted to the same Telegram chat as a follow-up and
(b) appended to tracker/data/agent_verdicts.jsonl so `report.py --by-verdict`
can measure whether AI verdicts actually add precision over the heuristic
score — the same collected-then-refit discipline as every other signal here.
Until that lift is proven, verdicts are advisory.

Needs: `hermes` installed with a model provider authed (e.g.
`hermes auth add nous`), and the memecoin-dd skill visible to Hermes.

Usage:
    python3 agent/analyst.py --dry-run          # print verdicts, no Telegram
    python3 agent/analyst.py --backfill 2       # also process last 2 matching alerts
    python3 agent/analyst.py                    # live (LaunchAgent: com.sunrise.analyst)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "pons"))
import telegram  # noqa: E402

ALERTS = os.path.join(REPO, "tracker", "data", "alerts.jsonl")
VERDICTS = os.path.join(REPO, "tracker", "data", "agent_verdicts.jsonl")
HERMES = os.path.expanduser("~/.local/bin/hermes")

# A tier entry may carry a minimum score as "TIER:55" — FLAP EARLY fires ~73/day
# (too chatty to DD all of them), but its score>=55 slice is ~18/day and flap is
# the proven-profitable source, so those earn a second opinion.
DEFAULT_TIERS = "CONFIRMED,TRENCH EARLY,TRENCH GRAD,FLAP EARLY:55"
VERDICT_EMOJI = {"BUY-WATCH": "🟢", "NEUTRAL": "⚪️", "AVOID": "⛔"}
BLOCKSCOUT = "https://robinhoodchain.blockscout.com/token/"


def alert_id(a):
    return f"{a['t']:.0f}:{a.get('token')}"


def build_prompt(a):
    """The alert row IS the briefing; the skill holds the method."""
    return (
        "A launch scanner just fired this alert (JSON below). Follow the "
        "memecoin-dd skill: verify with GMGN forensics (pons/gmgn.py via "
        "terminal, cwd is the repo), judge the X account and narrative, then "
        "END with the mandatory VERDICT block.\n\n"
        f"ALERT:\n{json.dumps(a, ensure_ascii=False)}\n"
    )


VERDICT_RE = re.compile(
    r"VERDICT:\s*(BUY-WATCH|NEUTRAL|AVOID)\s*.*?CONF:\s*(\d+)", re.S | re.I)
WHY_RE = re.compile(r"WHY\d:\s*(.+)")


def parse_verdict(text):
    """Parse the LAST verdict block in the transcript. None if absent."""
    matches = list(VERDICT_RE.finditer(text or ""))
    if not matches:
        return None
    m = matches[-1]
    whys = [w.strip() for w in WHY_RE.findall(text[m.start():])][:3]
    return {"verdict": m.group(1).upper(), "conf": min(int(m.group(2)), 100), "whys": whys}


def run_hermes(prompt, model, timeout):
    """One headless Hermes run. Returns (ok, text, secs)."""
    if not os.path.exists(HERMES):
        return False, "hermes binary not found", 0.0
    cmd = [HERMES, "chat", "-q", prompt, "-s", "memecoin-dd",
           "--toolsets", "web,terminal,skills"]
    if model:
        cmd += ["--model", model]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd=REPO)
        out = (r.stdout or "") + ("\n" + r.stderr if r.returncode != 0 else "")
        return r.returncode == 0, out, time.time() - t0
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s", time.time() - t0
    except Exception as e:  # noqa: BLE001
        return False, str(e), time.time() - t0


def record(row):
    try:
        os.makedirs(os.path.dirname(VERDICTS), exist_ok=True)
        with open(VERDICTS, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def fmt_msg(a, v):
    sym = html.escape(str(a.get("symbol") or "?"))
    emoji = VERDICT_EMOJI.get(v["verdict"], "❔")
    lines = [
        f"🤖 <b>AI-DD</b> — <b>{sym}</b> · {html.escape(a.get('tier') or '?')} "
        f"· {html.escape(a.get('platform') or '?')}",
        f"{emoji} <b>{v['verdict']}</b> · conf {v['conf']}",
    ]
    lines += [f"• {html.escape(w)}" for w in v["whys"]]
    tok = a.get("token") or ""
    if tok.startswith("0x"):
        lines.append(f'<a href="{BLOCKSCOUT}{tok}">{tok[:12]}…</a>')
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", default=DEFAULT_TIERS,
                    help=f"comma-separated tiers to analyze (default: {DEFAULT_TIERS})")
    ap.add_argument("--model", default=os.environ.get("HERMES_ANALYST_MODEL") or None,
                    help="override Hermes model for DD runs (else Hermes default)")
    ap.add_argument("--timeout", type=float, default=300.0, help="per-DD hermes timeout (s)")
    ap.add_argument("--backfill", type=int, default=0,
                    help="also process the last N matching alerts on startup")
    ap.add_argument("--poll", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    tiers = {}   # tier -> min score (0 = all)
    for t in args.tiers.split(","):
        t = t.strip()
        if not t:
            continue
        name, _, minsc = t.rpartition(":")
        if name and minsc.isdigit():
            tiers[name.strip()] = int(minsc)
        else:
            tiers[t] = 0

    def want(a):
        tier = a.get("tier")
        return tier in tiers and (a.get("score") or 0) >= tiers[tier]

    token_tg, chat_id = telegram.load_creds()
    dry = args.dry_run or not (token_tg and chat_id)
    print(f"AI analyst  tiers={tiers}  model={args.model or '(hermes default)'}  "
          f"hermes={'ok' if os.path.exists(HERMES) else 'MISSING'}  "
          f"-> {'DRY-RUN' if dry else f'Telegram {chat_id}'}", flush=True)

    def handle(a):
        aid = alert_id(a)
        sym = a.get("symbol") or "?"
        print(f"[{time.strftime('%H:%M:%S')}] DD {sym} ({a.get('tier')}) …", flush=True)
        ok, text, secs = run_hermes(build_prompt(a), args.model, args.timeout)
        v = parse_verdict(text) if ok else None
        row = {"t": time.time(), "id": aid, "token": a.get("token"), "symbol": sym,
               "tier": a.get("tier"), "platform": a.get("platform"),
               "score": a.get("score"), "ok": bool(v), "secs": round(secs, 1),
               "model": args.model}
        if v:
            row.update(v)
            record(row)
            msg = fmt_msg(a, v)
            if dry:
                print(msg, flush=True)
            else:
                sent, info = telegram.send(msg, token_tg, chat_id)
                print(f"[{time.strftime('%H:%M:%S')}] {sym}: {v['verdict']} conf {v['conf']} "
                      f"({secs:.0f}s) {'sent' if sent else 'send FAILED: ' + info}", flush=True)
        else:
            row["error"] = (text or "")[-400:]
            record(row)
            print(f"[{time.strftime('%H:%M:%S')}] {sym}: DD failed ({secs:.0f}s) — "
                  f"{(text or '')[-200:].strip()}", flush=True)

    # start at EOF (optionally replaying the last N matching rows). All offsets
    # are BYTE offsets (binary reads) — symbols can be non-ASCII (e.g. "橙子").
    pending = []
    pos = 0
    if os.path.exists(ALERTS):
        pos = os.path.getsize(ALERTS)
        if args.backfill:
            rows = []
            for ln in open(ALERTS, "rb"):
                try:
                    rows.append(json.loads(ln))
                except Exception:  # noqa: BLE001
                    pass
            pending = [a for a in rows if want(a)][-args.backfill:]

    print("running… Ctrl-C to stop", flush=True)
    while True:
        try:
            for a in pending:
                handle(a)
            pending = []
            if os.path.exists(ALERTS):
                size = os.path.getsize(ALERTS)
                if size < pos:      # rotated/truncated
                    pos = 0
                if size > pos:
                    with open(ALERTS, "rb") as f:
                        f.seek(pos)
                        chunk = f.read()
                    # only consume complete lines; a partial tail re-reads next poll
                    upto = chunk.rfind(b"\n") + 1
                    pos += upto
                    for ln in chunk[:upto].splitlines():
                        try:
                            a = json.loads(ln)
                        except Exception:  # noqa: BLE001
                            continue
                        if want(a):
                            pending.append(a)
            time.sleep(args.poll)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  loop error: {e}", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
