#!/usr/bin/env python3
"""Preflight for an unattended run (/orchestrate §1b): can this session run the plan without asking the user?

  preflight.py   prints {"ok": bool, "mode": str, "now": ISO time, "say": plain-language text}; exit 0

Reads the newest calls.jsonl record for this working directory from the last 120 s (the chain logs one per tool
call, with Claude Code's permission_mode, just before this script runs). ok when the mode is auto or
bypassPermissions: in any other mode executor shell commands can prompt, and they cannot be known in advance.
No record with a mode (Codex, OpenCode, or no log): mode "unknown", ok, and "say" is a one-line warning.
"""
import json
import os
import sys
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog

WINDOW_S = 120
OK_MODES = {"auto", "bypassPermissions"}
SAY_NOT_OK = ("This session can stop to ask you for permission while it works, so it would not finish on its own. "
              "Press Shift+Tab until the bottom line says auto mode (or restart Claude in auto mode), then run "
              "/orchestrate again.")
SAY_UNKNOWN = ("I could not check whether this session can ask you for permission while it works; if it does, "
               "the run will wait for you.")


def _epoch(ts: str) -> Optional[float]:
    try:
        return time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return None


def check(cwd: str, now: Optional[float] = None) -> Dict[str, Any]:
    now = time.time() if now is None else now
    here = os.path.realpath(cwd)
    mode = "unknown"
    try:
        with open(os.path.join(jevlog.log_dir(), "calls.jsonl"), encoding="utf-8") as f:
            lines = f.readlines()[-500:]
    except OSError:
        lines = []
    for line in reversed(lines):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        t = _epoch(str(r.get("ts", ""))) if isinstance(r, dict) else None
        if t is None or now - t > WINDOW_S or os.path.realpath(str(r.get("cwd", ""))) != here:
            continue
        mode = str(r.get("permission_mode") or "unknown")
        break
    ok = mode in OK_MODES or mode == "unknown"
    say = "" if mode in OK_MODES else (SAY_UNKNOWN if mode == "unknown" else SAY_NOT_OK)
    return {"ok": ok, "mode": mode, "now": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)), "say": say}


if __name__ == "__main__":
    sys.stdout.write(json.dumps(check(os.getcwd())) + "\n")
    sys.exit(0)
