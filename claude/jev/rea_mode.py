#!/usr/bin/env python3
"""REA on demand: `dryas rea {on|off|status}` connects the REA MCP server for one project only.

  rea_mode.py on       add REA as a local-scope MCP server for this folder's git root (or the folder itself);
                       the next session there loads it: /exit, then claude --continue
  rea_mode.py off      remove that local-scope server
  rea_mode.py status   say where REA is connected: every session (user scope), this project, or nowhere
Setup installs REA's skill but leaves its server out of every session: 207 tool names, its instructions and a Node
process cost each session that never reverse engineers anything. Claude Code keys local scope by the real path of
the main repo root (a worktree shares its repo's entry), and reads $CLAUDE_CONFIG_DIR/.claude.json (else
~/.claude.json; install/platform_util.claude_global_config has the same rule, but the plugin cannot import install/)."""
import json
import os
import shutil
import subprocess
import sys
from typing import Callable, Dict, List, Optional

VERSION = "6.7.0"
SERVER = "rea"
RESTART = "REA loads in the next session here: /exit, then claude --continue (in this folder)."


def on_argv() -> List[str]:
    return ["claude", "mcp", "add", "--scope", "local", SERVER, "--", "npx", "-y", "rea-agents@" + VERSION, "mcp"]


def off_argv() -> List[str]:
    return ["claude", "mcp", "remove", "--scope", "local", SERVER]


def config_file(env: Dict[str, str]) -> str:
    cd = env.get("CLAUDE_CONFIG_DIR")
    return os.path.join(cd, ".claude.json") if cd else os.path.join(os.path.expanduser("~"), ".claude.json")


def project_key(cwd: str) -> str:
    """The main repo root (the parent of the shared .git, so worktrees map to their repo), else the folder."""
    try:
        r = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=cwd, capture_output=True, text=True, timeout=10)
        common = r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        common = ""
    if not common:
        return os.path.realpath(cwd)
    return os.path.dirname(os.path.realpath(os.path.join(cwd, common)))


def _same(a: str, b: str) -> bool:
    """Paths equal after realpath and normcase (Windows: slashes and drive-letter case may differ)."""
    n = lambda p: os.path.normcase(os.path.realpath(p.rstrip("/\\") or p))
    return n(a) == n(b)


def run_cmd(argv: List[str], cwd: str, env: Dict[str, str]) -> int:
    """Run argv with argv[0] found on env's PATH (PATHEXT on Windows, so claude.cmd works); 127 when missing."""
    exe = shutil.which(argv[0], path=env.get("PATH"))
    if exe is None:
        print("dryas rea: `%s` is not on PATH" % argv[0])
        return 127
    try:
        return subprocess.call([exe] + argv[1:], cwd=cwd, env=env)
    except OSError as e:
        print("dryas rea: could not run %s (%s)" % (argv[0], e))
        return 127


def _config(env: Dict[str, str]) -> dict:
    try:
        with open(config_file(env), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _has(servers: object) -> bool:
    return isinstance(servers, dict) and SERVER in servers


def user_scoped(env: Dict[str, str]) -> bool:
    """True when REA starts in every session of this account."""
    return _has(_config(env).get("mcpServers"))


def state(env: Dict[str, str], cwd: str) -> str:
    """"user" (every session), "project" (local scope here) or "off"."""
    d = _config(env)
    if _has(d.get("mcpServers")):
        return "user"
    projects = d.get("projects") if isinstance(d.get("projects"), dict) else {}
    root = project_key(cwd)
    on = any(_same(k, root) and isinstance(v, dict) and _has(v.get("mcpServers")) for k, v in projects.items())
    return "project" if on else "off"


def main(argv: List[str], env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None,
         run: Callable[..., int] = run_cmd) -> int:
    env = dict(os.environ) if env is None else env
    cwd = cwd or os.getcwd()
    argv = argv[1:] if argv[:1] == ["rea"] else argv  # dryas.cmd forwards its whole line
    cmd = argv[0] if argv else ""
    if cmd not in ("on", "off", "status"):
        print("usage: dryas rea {on|off|status}")
        return 2
    now, root = state(env, cwd), project_key(cwd)
    if cmd == "status":
        print({"user": "REA: on in every session (user scope)", "project": "REA: on in " + root,
               "off": "REA: off here; `dryas rea on` connects it for " + root}[now])
        return 0
    if now == "user":
        print("REA already starts in every session (user scope). To make it on demand: "
              "claude mcp remove --scope user rea, then `dryas rea on` where you need it.")
        return 0
    if cmd == "on":
        if now == "project":
            print("REA is already on in " + root)
            return 0
        rc = run(on_argv(), cwd=root, env=env)
        if rc == 0:
            print("REA is on in %s. %s" % (root, RESTART))
        return rc
    if now == "off":
        print("REA is already off in " + root)
        return 0
    return run(off_argv(), cwd=root, env=env)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
