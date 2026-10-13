#!/usr/bin/env python3
"""SessionStart(clear) hook: seed the fresh context with the Jev-scored handoff, then delete it.
Only a file < 30 min old whose header cwd matches the event cwd is used. Never raises."""
import json
import os
import sys
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STALE_SECONDS = 1800


def run(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        from handoff_paths import handoff_path, parse_header, project_root, restore_context
        if event.get("source") not in (None, "clear"):
            return None
        cwd = event.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            return None
        path = handoff_path(cwd)
        if time.time() - os.stat(path).st_mtime > STALE_SECONDS:
            return None
        with open(path, encoding="utf-8") as f:
            text = f.read()
        meta = parse_header(text.split("\n", 1)[0])
        ctx = restore_context(text)
        if not meta or meta["cwd"] != project_root(cwd) or not ctx:
            return None
        os.unlink(path)
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}
    except Exception:
        return None


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        ev = json.loads(raw) if raw.strip() else {}
        out = run(ev if isinstance(ev, dict) else {})
        if out:
            sys.stdout.write(json.dumps(out))
    except Exception:
        pass
    sys.exit(0)
