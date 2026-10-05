#!/usr/bin/env python3
"""Ruflo hook runner (replaces run.sh and cli.sh). Never blocks a hook: always exits 0.

  run.py helper <cmd> <helper-file> [args...]   run one lifted Ruflo hook helper (cmd is usually "node")
  run.py cli [args...]                          run the pinned ruflo CLI (target of RUFLO_HOOK_CLI_OVERRIDE)

Silent no-op (stdin drained) when the data root, the command, the helper or the CLI is missing.
The child's stdout passes through; its exit code is dropped. RUFLO_DATA_MODE=cwd (default) runs the
child in <data root>/ruflo/<namespace> and sets RUFLO_DATA_ROOT there; =env runs in place.
`cli` prefers `node $RUFLO_JS` (portable) and falls back to RUFLO_BIN / `ruflo` on PATH.
"""
import os
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ns  # noqa: E402


def _drain() -> int:
    try:
        sys.stdin.buffer.read()
    except Exception:
        pass
    return 0


def _node() -> Optional[str]:
    found = shutil.which("node")
    if found:
        return found
    fb = os.environ.get("RUFLO_NODE_FALLBACK", "")
    return fb if fb and os.path.isfile(fb) and os.access(fb, os.X_OK) else None


def _resolve(cmd: str) -> Optional[str]:
    return _node() if cmd == "node" else shutil.which(cmd)


def _node_modules() -> str:
    nm = os.environ.get("RUFLO_NODE_MODULES", "")
    if nm:
        return nm
    rb = shutil.which("ruflo")
    if not rb:
        return ""
    d = os.path.dirname(rb)
    for cand in (os.path.join(d, "..", "lib", "node_modules", "ruflo", "node_modules"),  # POSIX npm prefix
                 os.path.join(d, "node_modules", "ruflo", "node_modules")):          # Windows %APPDATA%\npm
        if os.path.isdir(cand):
            return cand
    return ""


def _data_dir(root: str) -> Optional[str]:
    d = os.path.join(root, "ruflo", ns.ruflo_ns())
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    return d


def _call(argv: List[str], cwd: Optional[str], env: Dict[str, str]) -> int:
    try:
        sys.stdout.flush()
        subprocess.call(argv, cwd=cwd, env=env)
    except OSError:
        pass
    return 0


def helper(args: List[str]) -> int:
    root = ns.ruflo_root()
    if root is None or len(args) < 2:
        return _drain()
    exe = _resolve(args[0])
    if not exe or not os.path.isfile(args[1]):
        return _drain()
    env = dict(os.environ, RUFLO_NO_AUTO_ENABLE="1")
    nm = _node_modules()
    if nm and os.path.isdir(nm):
        env["NODE_PATH"] = nm + (os.pathsep + env["NODE_PATH"] if env.get("NODE_PATH") else "")
    cwd = None
    if env.get("RUFLO_DATA_MODE", "cwd") == "cwd":
        cwd = _data_dir(root)
        if cwd is None:
            return _drain()
        env["RUFLO_DATA_ROOT"] = cwd
    return _call([exe] + args[1:], cwd, env)


def cli(args: List[str]) -> int:
    root = ns.ruflo_root()
    if root is None:
        return _drain()
    js, node = os.environ.get("RUFLO_JS", ""), _node()
    if js and os.path.isfile(js) and node:
        argv = [node, js]
    else:
        b = os.environ.get("RUFLO_BIN") or shutil.which("ruflo") or ""
        if not b or not os.path.isfile(b):
            return _drain()
        argv = [b]
    d = _data_dir(root)
    if d is None:
        return _drain()
    # a CLI start must never autostart the background daemon (headless claude sessions cost tokens)
    env = dict(os.environ, RUFLO_NO_AUTO_ENABLE="1", RUFLO_DAEMON_AUTOSTART="0", CLAUDE_FLOW_CWD=d)
    return _call(argv + args, d, env)


def main(argv: List[str]) -> int:
    try:
        if len(argv) > 1 and argv[1] == "helper":
            return helper(argv[2:])
        if len(argv) > 1 and argv[1] == "cli":
            return cli(argv[2:])
        return _drain()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
