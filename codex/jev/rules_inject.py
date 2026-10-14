#!/usr/bin/env python3
"""SessionStart hook (startup, resume, clear, compact): Dryas rules as additionalContext.
A plugin's CLAUDE.md is not loaded, so CLAUDE.md.template is injected here, with <!-- pstack-picks --> blocks
resolved from chain.local.json "off". With --harness codex it injects AGENTS.md.template instead, with {{CD}}
resolved to the plugin root and a "Dryas paths:" line naming <dryas-root> and <dryas-py> for the skills.
On resume the context is injected again on purpose: additionalContext is not part of the saved transcript.
For Claude Code, when the account's settings.json lacks the deny rules of settings.fragment.json (setup not run),
one line says so, since the Superpowers overlap rules are then missing.
Fails silent (no output) on any error."""
import json
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
from gating import gate_blocks  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = {"claude": "CLAUDE.md.template", "codex": "AGENTS.md.template"}
PATHS_LINE = "Dryas paths: <dryas-root> = %s, <dryas-py> = %s. Substitute them in Dryas skill commands."
ALL = ("core", "jev", "ruflo", "superpowers", "design", "pstack-picks")
SKIP_LINE = ("pstack-picks is not installed: in Dryas skills and agents, skip any block wrapped in "
             "pstack-picks HTML comment markers (an opening and a closing one).")
SETUP_LINE = ("Dryas setup has not been run for this Claude config dir (run install/install.sh from the Dryas "
              "repo): the Superpowers overlap deny rules are missing, so the disabled Superpowers skills may still "
              "trigger; do not use them.")


def harness(argv: List[str]) -> str:
    if "--harness" in argv:
        i = argv.index("--harness")
        if i + 1 < len(argv) and argv[i + 1] in TEMPLATES:
            return argv[i + 1]
    return "claude"


def build(template: str, off: List[str], harness: str = "claude", root: str = "", py: str = "") -> str:
    text = gate_blocks(template, [c for c in ALL if c not in off]).strip()
    if harness == "codex":
        text = text.replace("{{CD}}", root) + "\n\n" + PATHS_LINE % (root, py)
    return text + ("\n\n" + SKIP_LINE if "pstack-picks" in off else "") + "\n"


def _off() -> List[str]:
    try:
        with open(paths.chain_local(), encoding="utf-8") as f:
            off = json.load(f).get("off", [])
        return [str(x) for x in off] if isinstance(off, list) else []
    except (OSError, ValueError, AttributeError):
        return []


def _fwd(p: str) -> str:
    return p.replace("\\", "/")


def settings_file() -> str:
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(cfg, "settings.json")


def setup_missing(settings: str, fragment: str) -> bool:
    """True when settings.json lacks a deny rule of the fragment's core component, or does not exist (setup writes
    it). False on any other error: the line is a hint, never a nag on doubt."""
    try:
        with open(fragment, encoding="utf-8") as f:
            want = json.load(f)["core"]["permissions"]["deny"]
        if not os.path.isfile(settings):
            return True
        with open(settings, encoding="utf-8") as f:
            perms = json.load(f).get("permissions") or {}
        deny = perms.get("deny") if isinstance(perms, dict) else None
        return not set(want) <= set(deny if isinstance(deny, list) else [])
    except Exception:
        return False


def main(argv: List[str]) -> None:
    h = harness(argv)
    try:
        sys.stdin.read()
        with open(os.path.join(os.path.dirname(HERE), TEMPLATES[h]), encoding="utf-8") as f:
            ctx = build(f.read(), _off(), h, _fwd(os.path.dirname(HERE)), _fwd(paths.python()))
        if h == "claude" and setup_missing(settings_file(), os.path.join(os.path.dirname(HERE), "settings.fragment.json")):
            ctx += "\n" + SETUP_LINE + "\n"
    except Exception:
        return
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        pass
    sys.exit(0)
