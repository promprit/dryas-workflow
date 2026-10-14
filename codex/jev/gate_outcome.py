#!/usr/bin/env python3
"""PostToolUse observe stage `gate-outcome`: log the tool_use_id of a Bash call that ran.

A local `ask` whose tool_use_id shows up here ran, so the user approved it (/tune allowlist proposals).
Observe-only: prints nothing, never raises, always exits 0."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAX_STDIN = 1024 * 1024


def main() -> None:
    event = json.loads(sys.stdin.read(MAX_STDIN))
    # PostToolUseFailure shares the `post` chain; a failed call (possibly a refused ask) is not an approval.
    if isinstance(event, dict) and isinstance(event.get("tool_use_id"), str) \
            and event.get("hook_event_name") != "PostToolUseFailure":
        import jevlog
        jevlog.append("outcomes", dict(tool_use_id=event["tool_use_id"][:64], tool="Bash"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
