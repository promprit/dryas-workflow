#!/usr/bin/env python3
"""Hook entry of a repo copy of Dryas (`dryas cloud`, owned core E). The repo's .claude/settings.json runs

  "${DRYAS_PY:-python3}" -X utf8 "$CLAUDE_PROJECT_DIR/.dryas/jev/cloud_hook.py" <script.py> [args...]

for every hook the plugin's hooks.json has (rules_inject.py aside: the CLAUDE.md block carries the rules). It points
CLAUDE_PLUGIN_ROOT at the copy and DRYAS_DATA_ROOT at <copy>/state, sets DRYAS_NOTES_DIR when the repo keeps memory
notes (<copy>/memory/notes), turns off bytecode files, then runs jev/<script.py> in this process with its arguments.

Outside a cloud session (CLAUDE_CODE_REMOTE is not true), on a machine where Dryas is installed for the user
(~/.dryas/chain.local.json exists), the plugin's own hooks already run, so this entry does nothing.
DRYAS_CLOUD_HOOKS=1 forces it on, DRYAS_CLOUD_HOOKS=0 off.

It is the only place a hook gets these variables: the copy puts no env into .claude/settings.json, where it would
also reach the plugin's own hooks on a machine with the plugin installed.
It never fails a tool call: an internal error exits 0, and for the PreToolUse chain it answers "ask".
The script's own exit code is kept (the plugin runs the same script directly)."""
import json
import os
import runpy
import sys
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASK = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                              "permissionDecisionReason": "[dryas-cloud] the Dryas hook chain could not run; "
                                                          "confirm this call yourself"}}


def remote() -> bool:
    return os.environ.get("CLAUDE_CODE_REMOTE", "").strip().lower() == "true"


def wanted() -> bool:
    force = os.environ.get("DRYAS_CLOUD_HOOKS", "").strip()
    if force in ("0", "1"):
        return force == "1"
    if remote():
        return True
    return not os.path.isfile(os.path.join(os.path.expanduser("~"), ".dryas", "chain.local.json"))


def _script(name: str) -> str:
    if not name.endswith(".py") or os.path.basename(name) != name or name == os.path.basename(__file__):
        raise ValueError("not a hook script: %r" % name[:64])
    path = os.path.join(HERE, name)
    if not os.path.isfile(path):
        raise ValueError("no such hook script: %r" % name[:64])
    return path


def main(argv: List[str]) -> int:
    name, args = (argv[1] if len(argv) > 1 else ""), argv[2:]
    pretool = name == "chain.py" and args[:1] == ["pretool"]
    try:
        if not wanted():
            return 0
        path = _script(name)
        os.environ["CLAUDE_PLUGIN_ROOT"] = ROOT
        os.environ["DRYAS_DATA_ROOT"] = os.path.join(ROOT, "state")
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"  # inherited by the chain's stage processes
        sys.dont_write_bytecode = True
        notes = os.path.join(ROOT, "memory", "notes")
        if os.path.isdir(notes):
            os.environ["DRYAS_NOTES_DIR"] = notes
        os.makedirs(os.environ["DRYAS_DATA_ROOT"], exist_ok=True)
        sys.argv = [path] + args
        sys.path.insert(0, HERE)
        runpy.run_path(path, run_name="__main__")
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0
    except Exception:
        if pretool:
            sys.stdout.write(json.dumps(ASK))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
