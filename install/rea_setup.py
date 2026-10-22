"""REA (rea-agents, reverse-engineering MCP + skill): the optional extra install, kept apart from thirdparty.
REA is not a Claude plugin: it is set up by its own CLI, pinned to VERSION, once per config dir (the caller passes
the env that targets it). Every failure is a warning: install() returns None and the Dryas install goes on.
Never runs `rea uninstall`, which acts on every client; removal is remove_argv + the recorded skill folder.
On demand (Claude Code): REA's setup registers its MCP server for every session; Dryas removes that registration,
so sessions that never reverse engineer anything pay nothing, and `dryas rea on` connects it per project."""
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import List, Optional

import dryas_install as di

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude" / "jev"))
import rea_mode  # noqa: E402

VERSION = rea_mode.VERSION
PKG = "rea-agents@" + VERSION
SKILL_NAME = "reverse-engineer-anything"
MIN_NODE = ((22, 19), (24, 11), (26, 0))
NODE_WARNING = ("warning: REA needs Node.js 22.19+, 24.11+ or 26+; skipped "
                "(install Node, then re-run with --with-rea).")


def _node_tuple(text: str) -> Optional[tuple]:
    m = re.match(r"\s*v?(\d+)\.(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def node_ok(capture=None, which=None) -> Optional[str]:
    """None when node and npx are on PATH and node meets MIN_NODE, else NODE_WARNING."""
    capture, which = capture or di.capture, which or shutil.which
    if not which("node") or not which("npx"):
        return NODE_WARNING
    rc, out = capture(["node", "--version"], timeout=30)
    v = _node_tuple(out) if rc == 0 else None
    if v is None:
        return NODE_WARNING
    major = v[0]
    for floor in MIN_NODE:
        if major == floor[0]:
            return None if v >= floor else NODE_WARNING
    return None if major > MIN_NODE[-1][0] else NODE_WARNING


def _npx(*args: str) -> List[str]:
    return ["npx", "-y", PKG] + list(args) + ["--format", "json"]


def setup_argv(client: str) -> List[str]:
    return _npx("setup", "--client", client, "--yes")


def dry_run_argv(client: str) -> List[str]:
    return _npx("setup", "--client", client, "--dry-run")


def doctor_argv(client: str) -> List[str]:
    return _npx("doctor", "--client", client, "--skill")


def remove_argv(client: str) -> List[str]:
    return ["codex", "mcp", "remove", "rea"] if client == "codex" else ["claude", "mcp", "remove", "--scope", "user", "rea"]


def _json(stdout: str) -> Optional[dict]:
    """The JSON object in stdout; npm may print notices first, so parse from the first '{'."""
    i = (stdout or "").find("{")
    if i < 0:
        return None
    try:
        d = json.loads(stdout[i:])
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def skill_dir_from_plan(stdout: str) -> Optional[str]:
    """The `target` of the install_skill action in `setup --dry-run --format json`."""
    d = _json(stdout)
    for a in (d or {}).get("plannedActions") or []:
        if isinstance(a, dict) and a.get("kind") == "install_skill" and isinstance(a.get("target"), str) and a["target"]:
            return a["target"]
    return None


def skill_state(stdout: str) -> Optional[str]:
    """identity.skill.state from `doctor --format json` (`aligned` when ready)."""
    s = (((_json(stdout) or {}).get("identity") or {}).get("skill") or {}).get("state")
    return s if isinstance(s, str) else None


def plan_summary(stdout: str) -> List[str]:
    """One readable line per planned action of `setup --dry-run --format json`; [] when nothing parses."""
    acts = (_json(stdout) or {}).get("plannedActions") or []
    return ["  %s %s: %s" % (a.get("operation") or "?", a.get("kind") or "?", a.get("target") or "?")
            for a in acts if isinstance(a, dict)]


def _config_skill_dir(env: dict) -> Optional[str]:
    """<config dir>/skills/SKILL_NAME when it exists: REA's dry run plans nothing once it is installed."""
    cd = (env or {}).get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    p = os.path.join(cd, "skills", SKILL_NAME)
    return p if os.path.isdir(p) else None


def on_demand(client: str, env: dict, ask: bool) -> None:
    """Claude Code only: remove REA's user-scope MCP registration (asking first when ask), so it starts only where
    `dryas rea on` connected it. A failure or a no is a printed line; never raises."""
    if client != "claude_code" or not rea_mode.user_scoped(env or {}):
        return
    if ask and not di.confirm("Make REA on demand (remove its MCP entry from every session)?"):
        print("kept REA in every session; `%s` makes it on demand" % " ".join(remove_argv(client)))
        return
    rc = di.run(remove_argv(client), env=env)
    if rc != 0:
        print("warning: could not remove REA's user-scope MCP entry (exit %d); run `%s`" % (rc, " ".join(remove_argv(client))))
        return
    print("REA is on demand: `dryas rea on` connects it in a project (then /exit and claude --continue)")


def install(client: str, env: dict, yes: bool, dry_run: bool, prior: Optional[dict] = None) -> Optional[dict]:
    """Show REA's dry run, ask (unless yes), run setup, check doctor. The record entry, or None (skipped/failed).
    A prior entry at VERSION whose doctor says aligned is kept as is: no plan, no prompt."""
    warn = node_ok()
    if warn:
        print(warn)
        return None
    if dry_run:
        print("would run: " + " ".join(setup_argv(client)))
        return None
    if isinstance(prior, dict) and prior.get("version") == VERSION:
        _, out = di.capture(doctor_argv(client), env=env, timeout=600)
        if skill_state(out) == "aligned":
            print("REA %s already set up; skipped" % VERSION)
            on_demand(client, env, ask=not yes)
            if prior.get("skill_dir") is None and client == "claude_code":
                return dict(prior, skill_dir=_config_skill_dir(env))
            return prior
    rc, plan = di.capture(dry_run_argv(client), env=env, timeout=600)
    if rc != 0:
        print("warning: REA dry run failed (exit %d); REA is optional, Dryas setup continues" % rc)
        return None
    print("REA will change:")
    print("\n".join(plan_summary(plan)) or plan.strip())
    if not yes and not di.confirm("Install REA?"):
        print("skipped REA")
        return None
    rc = di.run(setup_argv(client), env=env)
    if rc != 0:
        print("warning: REA setup failed (exit %d); REA is optional, Dryas setup continues" % rc)
        return None
    rc, out = di.capture(doctor_argv(client), env=env, timeout=600)
    state = skill_state(out)
    cmd = " ".join(doctor_argv(client))
    if state is None:
        print("warning: REA doctor gave no state (exit %d); run `%s`" % (rc, cmd))
    elif state != "aligned":
        print("warning: REA doctor reports the skill as %s; run `%s` to see why" % (state, cmd))
    on_demand(client, env, ask=False)  # part of the install the user just confirmed
    skill_dir = skill_dir_from_plan(plan)
    if skill_dir is None and isinstance(prior, dict):
        skill_dir = prior.get("skill_dir")
    if skill_dir is None and client == "claude_code":
        skill_dir = _config_skill_dir(env)
    return {"version": VERSION, "client": client, "skill_dir": skill_dir}


def safe_skill_dir(path: Optional[str], root) -> bool:
    """True only for a real directory (not a symlink) named SKILL_NAME whose real path is inside root."""
    if not path or not os.path.isabs(path) or os.path.basename(os.path.normpath(path)) != SKILL_NAME:
        return False
    if not os.path.isdir(path) or os.path.islink(path):
        return False
    return os.path.realpath(path).startswith(os.path.realpath(str(root)) + os.sep)


def remove_skill(entry: Optional[dict], root) -> str:
    """Delete the recorded skill folder when safe_skill_dir allows it; always returns a message, never raises."""
    path = entry.get("skill_dir") if isinstance(entry, dict) else None
    if not path:
        return "REA's skill folder was not recorded; remove its %s skill folder by hand" % SKILL_NAME
    if not safe_skill_dir(path, root):
        return "kept %s (not a plain %s folder inside %s); remove it by hand" % (path, SKILL_NAME, root)
    try:
        shutil.rmtree(path)
    except OSError as e:
        return "warning: could not remove %s (%s)" % (path, e)
    return "removed %s" % path
