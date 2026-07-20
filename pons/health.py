"""Atomic feed-ingest heartbeats shared by the live scanners and watchdog."""
from __future__ import annotations

import json
import os
import time

_LAST_WRITTEN = {}


def is_record_list(value):
    """Return True for a feed list whose rows are all JSON objects."""
    return isinstance(value, list) and all(isinstance(row, dict) for row in value)


def write(path, row):
    """Atomically write JSON state. Return False instead of raising."""
    path = os.fspath(path)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(row, f, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except Exception:  # noqa: BLE001
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def touch(path, scanner, now=None, detail=None, min_interval=15):
    """Record one successful feed ingest. Never interrupt the scanner loop."""
    stamp = time.time() if now is None else float(now)
    key = os.fspath(path)
    if stamp - _LAST_WRITTEN.get(key, float("-inf")) < min_interval:
        return True
    row = {"scanner": scanner, "t": stamp, "pid": os.getpid()}
    if detail is not None:
        row["detail"] = detail
    ok = write(path, row)
    if ok:
        _LAST_WRITTEN[key] = stamp
    return ok


def read(path):
    """Read a heartbeat, returning None for missing or malformed state."""
    try:
        with open(path) as f:
            row = json.load(f)
        return row if isinstance(row, dict) else None
    except (OSError, ValueError, TypeError):
        return None
