#!/usr/bin/env python3
"""SessionStart(compact) hook: re-inject the lines Jev kept (same engine as /handoff) before compaction."""
import json
import os
import sys
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CAP = 12000
STALE_SECONDS = 600  # Ignore files older than this


def run(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sid = event.get("session_id")
    if not sid or not isinstance(sid, str) or not sid.strip():
        return None
    try:
        from compact_keep import compact_dir, safe_name
        from handoff_paths import restore_context
        path = os.path.join(compact_dir(), safe_name(sid) + ".md")
        if time.time() - os.stat(path).st_mtime > STALE_SECONDS:
            return None
        with open(path, encoding="utf-8") as f:
            ctx = restore_context(f.read(), CAP)
    except Exception:
        return None
    if not ctx:
        return None
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        out = run(json.loads(raw) if raw.strip() else {})
        if out:
            sys.stdout.write(json.dumps(out))
    except Exception:
        pass
    sys.exit(0)
