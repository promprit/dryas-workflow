#!/usr/bin/env python3
"""SessionStart(clear|startup) hook: seed the fresh context with the Jev-scored handoff, then delete it.
Only a file < 30 min old whose header cwd matches the event cwd is used.
On startup only a handoff saved with /handoff move (header move=1) is used. Never raises."""
import json
import os
import sys
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STALE_SECONDS = 1800


def run(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        from handoff_paths import handoff_path, move_path, parse_header, project_root, restore_context
        source = event.get("source")
        if source not in (None, "clear", "startup"):
            return None
        cwd = event.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            return None
        startup = source == "startup"
        paths = [move_path(cwd)] if startup else [handoff_path(cwd), move_path(cwd)]
        root = None
        for path in paths:
            try:
                st = os.stat(path)
            except OSError:
                continue
            if time.time() - st.st_mtime > STALE_SECONDS:
                if startup:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            meta = parse_header(text.split("\n", 1)[0])
            ctx = restore_context(text)
            if not meta or not ctx or (startup and not meta.get("move")):
                continue
            if root is None:
                root = project_root(cwd)
            if meta["cwd"] != root:
                continue
            os.unlink(path)
            return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}
        return None
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
