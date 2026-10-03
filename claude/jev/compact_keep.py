#!/usr/bin/env python3
"""PreCompact hook (manual and auto): runs the same Jev scoring engine as /handoff (handoff.build_handoff:
all items, always-kept lines, scored window, fallback) and saves the result keyed by session id for
compact_restore.py to re-inject after Claude Code's own compaction. Never blocks compaction."""
import hashlib
import json
import os
import re
import sys
import tempfile
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import handoff
import jevlog
import thresholds
from jev_client import judge


def compact_dir() -> str:
    return os.environ.get("JEV_COMPACT_DIR", os.path.expanduser("~/.claude/jev/compact"))


def safe_name(sid: str) -> str:
    """Generate a collision-resistant filename from session_id.

    Uses 64-char limit on sanitized name plus 12-char hash suffix to prevent collisions
    (e.g., a/b and a_b, or empty session_id).
    """
    if not sid or not isinstance(sid, str):
        return ""
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", sid)[:64]
    h = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:12]
    return f"{sanitized}-{h}" if sanitized else f"unknown-{h}"


def run(event: Dict[str, Any], judge_fn=judge) -> int:
    """Returns the number of kept lines (0 when nothing was saved)."""
    path = event.get("transcript_path")
    sid = event.get("session_id")

    if not sid or not isinstance(sid, str) or not sid.strip():
        return 0
    if not path or not os.path.isfile(path):
        return 0

    try:
        cdir = compact_dir()
        os.makedirs(cdir, mode=0o700, exist_ok=True)
        target = os.path.join(cdir, safe_name(sid) + ".md")
        try:
            os.unlink(target)  # never leave a stale file from an earlier compaction
        except OSError:
            pass
        cwd = event.get("cwd") if isinstance(event.get("cwd"), str) and event.get("cwd") else os.getcwd()
        text, st = handoff.build_handoff(path, cwd, judge_fn, keep_min=thresholds.load()["compact"]["keep_above"],
                                      deadline_s=20)
        if not text:
            return 0
        handoff.write_private(target, text)
        jevlog.append("compact", {"kept": st["kept"], "of": st["total"], "scored": st["scored"], "jev_ok": st["jev_ok"],
                                  "chunks": st.get("chunks"), "input_tokens": st.get("input_tokens"), "cost": st.get("cost")})
        return st["kept"]
    except Exception as e:
        jevlog.append("compact", {"kept": 0, "error": type(e).__name__})
        return 0


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        run(json.loads(raw) if raw.strip() else {})
    except Exception:
        pass
    sys.exit(0)
