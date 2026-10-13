"""Append-only JSONL logs for Jev stages. One short line per record; never raises."""
import json
import os
import sys
import time
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths


def log_dir() -> str:
    return paths.log_dir()


def append(name: str, record: Dict[str, Any]) -> None:
    try:
        d = log_dir()
        os.makedirs(d, exist_ok=True)
        rec = dict(record)
        rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        for key, env in (("session_id", "JEV_SESSION_ID"), ("cwd", "JEV_CWD")):
            v = os.environ.get(env)
            if v:
                rec.setdefault(key, v)
        line = (json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(os.path.join(d, name + ".jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line)  # single O_APPEND write: safe across parallel sessions
        finally:
            os.close(fd)
    except Exception:
        pass
