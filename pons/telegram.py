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
import time
import urllib.error
import urllib.parse
import urllib.request

TG_MAX = 4096   # Telegram hard message-length cap

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
        cid = d.get("chat_id")
        # str(None) -> "None" is truthy and slips past the send() guard, failing
        # later with an opaque "chat not found"; keep it None so the guard fires.
        return d.get("token"), (str(cid) if cid is not None else None)
    return None, None


def send(text, token=None, chat_id=None, timeout=10, parse_mode="HTML",
         disable_preview=True, buttons=None, reply_to=None, edit_id=None):
    """Send a message. Returns (ok: bool, info).

    On success `info` is the Telegram message_id (int) — callers can store it
    to later edit the message in place (see edit()) or reply-thread to it.
    On failure `info` is an error string (all existing callers only use info
    in their failure branch, so the type split is safe).

    buttons: optional inline keyboard as a list of rows, each row a list of
    (label, url) tuples -> rendered as clickable URL buttons under the message.
    reply_to: optional message_id to thread this message under.
    edit_id: internal — edit that message_id in place instead of sending.
    """
    if token is None or chat_id is None:
        token, chat_id = load_creds()
    if not token or not chat_id:
        return False, "no credentials (set env TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID or data/telegram.json)"
    if len(text) > TG_MAX:
        text = text[:TG_MAX - 1] + "…"    # 400 "message is too long" would drop it entirely
    url = f"https://api.telegram.org/bot{token}/{'editMessageText' if edit_id else 'sendMessage'}"

    def _post(pm):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true" if disable_preview else "false",
        }
        if edit_id:
            payload["message_id"] = edit_id
        elif reply_to:
            payload["reply_to_message_id"] = reply_to
            payload["allow_sending_without_reply"] = "true"   # original gone -> plain send
        if pm:
            payload["parse_mode"] = pm
        if buttons:
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": [[{"text": lbl, "url": u} for lbl, u in row] for row in buttons]
            })
        data = urllib.parse.urlencode(payload).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
            body = json.loads(r.read())
            ok = bool(body.get("ok"))
            res = body.get("result")
            mid = res.get("message_id") if isinstance(res, dict) else None
            return ok, (mid if ok and mid else body.get("description", "sent"))

    # Up to 3 attempts: honour 429 retry_after, retry 5xx/network, and on an HTML
    # parse error fall back to plain text so the alert still arrives in some form.
    pm = parse_mode
    for attempt in range(3):
        try:
            return _post(pm)
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read())
                msg = err.get("description", str(e))
            except Exception:  # noqa: BLE001
                err, msg = {}, str(e)
            if e.code == 429:
                wait = (err.get("parameters") or {}).get("retry_after", 2)
                time.sleep(min(wait, 15) + 0.5)
                continue
            if e.code == 400 and "parse entities" in msg and pm:
                pm = None            # retry once as plain text
                continue
            if 500 <= e.code < 600 and attempt < 2:
                time.sleep(1.5)
                continue
            return False, f"HTTP {e.code}: {msg}"
        except Exception as e:  # noqa: BLE001
            if attempt < 2:
                time.sleep(1.5)
                continue
            return False, str(e)
    return False, "exhausted retries"


def edit(text, message_id, token=None, chat_id=None, buttons=None, **kw):
    """Edit a previously sent message in place (append the AI verdict without a
    new chat bubble). Same return contract as send(). Telegram does NOT
    re-notify on edits, so this never double-pings."""
    return send(text, token, chat_id, buttons=buttons, edit_id=message_id, **kw)


if __name__ == "__main__":
    # quick credential test: python3 analysis/pons/telegram.py
    ok, info = send("✅ pons scanner: Telegram wired up.")
    print("OK" if ok else "FAIL", "-", info)
