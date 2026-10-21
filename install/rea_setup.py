"""REA (rea-agents, reverse-engineering MCP + skill): the optional extra install, kept apart from thirdparty.
REA is not a Claude plugin: it is set up by its own CLI, pinned to VERSION, once per config dir (the caller passes
the env that targets it). Every failure is a warning: install() returns None and the Dryas install goes on.
Never runs `rea uninstall`, which acts on every client; removal is remove_argv + the recorded skill folder."""
import json
import os
import re
import shutil
from typing import List, Optional

import dryas_install as di

VERSION = "6.7.0"
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


def install(client: str, env: dict, yes: bool, dry_run: bool) -> Optional[dict]:
    """Show REA's dry run, ask (unless yes), run setup, check doctor. The record entry, or None (skipped/failed)."""
    warn = node_ok()
    if warn:
        print(warn)
        return None
    if dry_run:
        print("would run: " + " ".join(setup_argv(client)))
        return None
    rc, plan = di.capture(dry_run_argv(client), env=env, timeout=600)
    if rc != 0:
        print("warning: REA dry run failed (exit %d); REA is optional, Dryas setup continues" % rc)
        return None
    print("REA setup plan (%s):" % " ".join(dry_run_argv(client)))
    print(plan.strip())
    if not yes and not di.confirm("Install REA?"):
        print("skipped REA")
        return None
    rc = di.run(setup_argv(client), env=env)
    if rc != 0:
        print("warning: REA setup failed (exit %d); REA is optional, Dryas setup continues" % rc)
        return None
    _, out = di.capture(doctor_argv(client), env=env, timeout=600)
    state = skill_state(out)
    if state != "aligned":
        print("warning: REA doctor reports the skill as %s; run `%s` to see why" % (state, " ".join(doctor_argv(client))))
    return {"version": VERSION, "client": client, "skill_dir": skill_dir_from_plan(plan)}


def safe_skill_dir(path: Optional[str]) -> bool:
    """True only for a real directory (not a symlink) named SKILL_NAME: the one folder uninstall may delete."""
    if not path or os.path.basename(os.path.normpath(path)) != SKILL_NAME:
        return False
    return os.path.isdir(path) and not os.path.islink(path)
