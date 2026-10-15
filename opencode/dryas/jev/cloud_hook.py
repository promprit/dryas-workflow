#!/usr/bin/env python3
"""Hook entry of a repo copy of Dryas (`dryas cloud`, owned core E). The repo's .claude/settings.json runs

  "${DRYAS_PY:-python3}" -X utf8 "$CLAUDE_PROJECT_DIR/.dryas/jev/cloud_hook.py" <script.py> [args...]

for every hook the plugin's hooks.json has (rules_inject.py aside: the CLAUDE.md block carries the rules). It points
CLAUDE_PLUGIN_ROOT at the copy and DRYAS_DATA_ROOT at <copy>/state, sets DRYAS_NOTES_DIR when the repo keeps memory
notes (<copy>/memory/notes), turns off bytecode files, then runs jev/<script.py> in this process with its arguments.

Outside a cloud session (CLAUDE_CODE_REMOTE is not true), on a machine where Dryas is installed for the user
(its chain.local.json exists, or the plugin registry lists dryas@), the plugin's own hooks already run, so this entry does nothing.
DRYAS_CLOUD_HOOKS=1 forces it on, DRYAS_CLOUD_HOOKS=0 off.

It is the only place a hook gets these variables: the copy puts no env into .claude/settings.json, where it would
also reach the plugin's own hooks on a machine with the plugin installed.
It never fails a tool call: an internal error exits 0, drops whatever the script had printed, and for the PreToolUse
chain answers only "ask". The script's own exit code is kept as the interpreter would give it (the plugin runs the same
script directly): sys.exit(None) is 0, an int passes through, any other value goes to stderr and exits 1."""
import io
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
    return not _plugin_active()


def _plugin_active() -> bool:
    """Dryas is set up for the user: its chain.local.json exists (JEV_CHAIN_LOCAL, else $DRYAS_DATA_ROOT, else ~/.dryas;
    read before main() points DRYAS_DATA_ROOT at the copy) or a Claude plugin registry lists dryas@..."""
    home = os.path.expanduser("~")
    local = os.environ.get("JEV_CHAIN_LOCAL") or os.path.join(
        os.environ.get("DRYAS_DATA_ROOT") or os.path.join(home, ".dryas"), "chain.local.json")
    if os.path.isfile(local):
        return True
    dirs = [os.path.join(home, ".claude")]
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        dirs.append(os.environ["CLAUDE_CONFIG_DIR"])
    for d in dirs:
        try:
            with open(os.path.join(d, "plugins", "installed_plugins.json"), encoding="utf-8") as f:
                plugins = json.load(f).get("plugins", {})
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(plugins, dict) and any(str(k).startswith("dryas@") for k in plugins):
            return True
    return False


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
        real, buf = sys.stdout, io.StringIO()
        sys.stdout = buf  # held back: a crash halfway must not leave half a JSON answer
        try:
            runpy.run_path(path, run_name="__main__")
            code = 0
        except SystemExit as e:
            code = _exit_code(e.code)
        finally:
            sys.stdout = real
        real.write(buf.getvalue())
        return code
    except Exception:
        if pretool:
            sys.stdout.write(json.dumps(ASK))
        return 0


def _exit_code(code: object) -> int:
    """What the interpreter itself would exit with for sys.exit(code)."""
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    sys.stderr.write("%s\n" % code)
    return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
