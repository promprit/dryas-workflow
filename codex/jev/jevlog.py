"""Append-only JSONL logs for Jev stages. One short line per record; never raises.

The log dir is private (0o700). A file over MAX_BYTES is rotated to <name>.jsonl.1 (one backup kept)."""
import json
import os
import sys
import time
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths


MAX_BYTES = 5 * 1024 * 1024


def log_dir() -> str:
    return paths.log_dir()


def _rotate(path: str) -> None:
    try:
        if os.path.getsize(path) > MAX_BYTES:
            os.replace(path, path + ".1")  # atomic; a parallel session at worst rotates a near-empty file
    except OSError:
        pass


def append(name: str, record: Dict[str, Any]) -> None:
    try:
        d = log_dir()
        if not os.path.isdir(d):
            os.makedirs(d, mode=0o700, exist_ok=True)
            os.chmod(d, 0o700)  # portable-ok: POSIX file privacy; no-op on Windows
        rec = dict(record)
        rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        for key, env in (("session_id", "JEV_SESSION_ID"), ("cwd", "JEV_CWD")):
            v = os.environ.get(env)
            if v:
                rec.setdefault(key, v)
        line = (json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        path = os.path.join(d, name + ".jsonl")
        _rotate(path)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line)  # single O_APPEND write: safe across parallel sessions
        finally:
            os.close(fd)
    except Exception:
        pass
