"""Fake command-line tools for installer tests: a Python script plus a launcher that PATH lookup finds on every OS.

Each call appends [name, *args] as one JSON line to `log`. stdout is outputs.get("<arg1> <arg2>", "").
Exit code is 1 when "<arg1> <arg2>" is in `fail`, else 0.
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
sys.exit(1 if key in %(fail)r else 0)
'''


def make(bin_dir: Path, name: str, log: Path, outputs: Optional[dict] = None, fail: Iterable[str] = ()) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    py = bin_dir / (name + "_fake.py")
    py.write_text(SCRIPT % {"name": name, "log": str(log), "outputs": dict(outputs or {}), "fail": list(fail)},
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
