"""Tiny Telegram Bot API sender (stdlib only).

Credentials are read from, in order:
  1. env vars  TELEGRAM_BOT_TOKEN  /  TELEGRAM_CHAT_ID
  2. config file  analysis/pons/data/telegram.json  {"token": "...", "chat_id": "..."}

Never hard-code the token — it's a secret. The config file should stay out of git
(see .gitignore note in the pons README).
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "data", "telegram.json")
ENV = os.path.join(HERE, ".env")


def _load_dotenv(path):
    """Minimal KEY=VALUE parser (no dependency). Returns a dict; ignores blanks/#."""
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_creds():
    # 1) real env vars win
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    cid = os.environ.get("TELEGRAM_CHAT_ID")
    # 2) .env file next to the scripts
    if not (tok and cid):
        env = _load_dotenv(ENV)
        tok = tok or env.get("TELEGRAM_BOT_TOKEN")
        cid = cid or env.get("TELEGRAM_CHAT_ID")
    if tok and cid:
        return tok, str(cid)
    # 3) json config fallback
    if os.path.exists(CFG):
        d = json.load(open(CFG))
        return d.get("token"), str(d.get("chat_id"))
    return None, None


def send(text, token=None, chat_id=None, timeout=10, parse_mode="HTML",
         disable_preview=True, buttons=None):
    """Send a message. Returns (ok: bool, info: str).

    buttons: optional inline keyboard as a list of rows, each row a list of
    (label, url) tuples -> rendered as clickable URL buttons under the message.
    """
    if token is None or chat_id is None:
        token, chat_id = load_creds()
    if not token or not chat_id:
        return False, "no credentials (set env TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID or data/telegram.json)"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": "true" if disable_preview else "false",
    }
    if buttons:
        payload["reply_markup"] = json.dumps({
            "inline_keyboard": [[{"text": lbl, "url": u} for lbl, u in row] for row in buttons]
        })
    data = urllib.parse.urlencode(payload).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
            body = json.loads(r.read())
            return bool(body.get("ok")), body.get("description", "sent")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("description", str(e))
        except Exception:  # noqa: BLE001
            msg = str(e)
        return False, f"HTTP {e.code}: {msg}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


if __name__ == "__main__":
    # quick credential test: python3 analysis/pons/telegram.py
    ok, info = send("✅ pons scanner: Telegram wired up.")
    print("OK" if ok else "FAIL", "-", info)
