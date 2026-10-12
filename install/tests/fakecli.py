"""Fake command-line tools for installer tests: a Python script plus a launcher that PATH lookup finds on every OS.

Each call appends [name, *args] as one JSON line to `log`. stdout is outputs.get("<arg1> <arg2>", "").
Exit code is 1 when "<arg1> <arg2>" is in `fail`, else 0.
plugin_list=True: `plugin list --json` prints the plugins in $CLAUDE_CONFIG_DIR/plugins/installed_plugins.json the way
the real CLI does (readFromFolder: $FAKE_READ_FROM or the installPath; errors: $FAKE_PLUGIN_ERRORS, a JSON list;
$FAKE_MISSING_DEP: a dependency id reported unsatisfied while it is not in installed_plugins.json).
"""
import json
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional

SCRIPT = '''import json, sys
with open(%(log)r, "a", encoding="utf-8") as f:
    f.write(json.dumps([%(name)r] + sys.argv[1:]) + "\\n")
key = " ".join(sys.argv[1:3])
sys.stdout.write(%(outputs)r.get(key, ""))
%(epilogue)s
sys.exit(1 if key in %(fail)r else 0)
'''

PLUGIN_LIST = '''
import os as _os
if sys.argv[1:3] == ["plugin", "list"] and "plugin list" not in %(fail)r:
    try:
        with open(_os.path.join(_os.environ.get("CLAUDE_CONFIG_DIR", ""), "plugins", "installed_plugins.json"),
                  encoding="utf-8") as _f:
            _d = json.load(_f)
    except (OSError, ValueError):
        _d = {}
    _out = []
    _dep = _os.environ.get("FAKE_MISSING_DEP")
    _dep = _dep if _dep and _dep not in _d.get("plugins", {}) else None
    for _id, _es in _d.get("plugins", {}).items():
        for _e in _es:
            _errs = json.loads(_os.environ.get("FAKE_PLUGIN_ERRORS") or "[]")
            _out.append({"id": _id, "version": _e.get("version"), "scope": "user", "enabled": True,
                         "installPath": _e.get("installPath"),
                         "readFromFolder": _os.environ.get("FAKE_READ_FROM") or _e.get("installPath"),
                         "errors": _errs + (["Dependency " + _dep + " is not installed"] if _dep else []),
                         "errorDetails": [{"type": "dependency-unsatisfied", "dependency": _dep}] if _dep else []})
    sys.stdout.write(json.dumps(_out))
'''


def make(bin_dir: Path, name: str, log: Path, outputs: Optional[dict] = None, fail: Iterable[str] = (),
         epilogue: str = "", plugin_list: bool = False) -> Path:
    """`epilogue`: extra Python lines run after logging, before the exit."""
    if plugin_list:
        epilogue = epilogue + PLUGIN_LIST % {"fail": list(fail)}
    bin_dir.mkdir(parents=True, exist_ok=True)
    py = bin_dir / (name + "_fake.py")
    py.write_text(SCRIPT % {"name": name, "log": str(log), "outputs": dict(outputs or {}), "fail": list(fail),
                             "epilogue": epilogue},
                  encoding="utf-8")
    if os.name == "nt":
        launcher = bin_dir / (name + ".cmd")
        launcher.write_text('@"%s" "%s" %%*\r\n' % (sys.executable, py), encoding="utf-8")
    else:
        launcher = bin_dir / name
        launcher.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, py), encoding="utf-8")
        launcher.chmod(0o755)
    return launcher


def calls(log: Path) -> List[List[str]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
