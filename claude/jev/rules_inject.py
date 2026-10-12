#!/usr/bin/env python3
"""SessionStart hook (startup, resume, clear, compact): Dryas rules as additionalContext.
A plugin's CLAUDE.md is not loaded, so CLAUDE.md.template is injected here, with <!-- pstack-picks --> blocks
resolved from chain.local.json "off". Fails silent (no output) on any error."""
import json
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
from gating import gate_blocks  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CLAUDE.md.template")
ALL = ("core", "jev", "ruflo", "superpowers", "design", "pstack-picks")
SKIP_LINE = ("pstack-picks is not installed: in Dryas skills and agents, skip any block wrapped in "
             "pstack-picks HTML comment markers (an opening and a closing one).")


def build(template: str, off: List[str]) -> str:
    text = gate_blocks(template, [c for c in ALL if c not in off]).strip()
    return text + ("\n\n" + SKIP_LINE if "pstack-picks" in off else "") + "\n"


def _off() -> List[str]:
    try:
        with open(paths.chain_local(), encoding="utf-8") as f:
            off = json.load(f).get("off", [])
        return [str(x) for x in off] if isinstance(off, list) else []
    except (OSError, ValueError, AttributeError):
        return []


def main() -> None:
    try:
        sys.stdin.read()
        with open(TEMPLATE, encoding="utf-8") as f:
            ctx = build(f.read(), _off())
    except Exception:
        return
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
