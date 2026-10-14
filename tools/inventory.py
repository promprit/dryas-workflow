#!/usr/bin/env python3
"""No-loss inventory of the Dryas surface (owned core, plan 0).

  python tools/inventory.py --list             print the current entries
  python tools/inventory.py --write [--force]  store them as the 1.x baseline (reference/inventory-1.x.json)
  python tools/inventory.py --check            exit 1 if a baseline entry is gone and not mapped

An entry is "<kind>:<name>". Collectors read only the repo; Jev logs come from an empty temp dir.
reference/inventory-map.json maps a removed entry to the entry that replaces it, or to "extra:<component>"
when it lives on in an optional component listed in install/components.json."""
import argparse
import ast
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = "reference/inventory-1.x.json"
MAP = "reference/inventory-map.json"
EDITIONS = ("claude", "codex")
TOOL_TOKENS = ("memory_search", "memory_store", "swarm_init")
SKIP_DIRS = ("jev", "pstack", "tests", "__pycache__")  # codex/jev and codex/pstack are generated copies
_SPLIT = re.compile(r",\s*(?![^()]*\))")
_SCRIPT = re.compile(r"([\w.-]+\.(?:py|cjs|mjs))\"?((?:\s+[\w-]+)*)")
_SP = re.compile(r"\bsuperpowers:([a-z][a-z-]*)")


class InventoryError(Exception):
    pass


def _json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InventoryError("%s: %s" % (p.as_posix(), e))


def _front(p: Path) -> Dict[str, str]:
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    out = {}
    for line in text.split("---", 2)[1].splitlines():
        k, sep, v = line.partition(":")
        if sep:
            out[k.strip()] = v.strip()
    return out


def _manifests(repo: Path) -> Set[str]:
    out: Set[str] = set()
    for ed in EDITIONS:
        p = repo / ed / ".mcp.json"
        if p.exists():
            out |= {"mcp_server:%s:%s" % (ed, n) for n in _json(p).get("mcpServers", {})}
    pj = repo / "claude/.claude-plugin/plugin.json"
    if pj.exists():
        m = _json(pj)
        for d in m.get("dependencies", []):
            out.add("plugin_dep:claude:%s" % (d.get("name") if isinstance(d, dict) else d))
        out |= {"plugin_config:claude:%s" % k for k in m.get("userConfig", {})}
    return out


def _allowed(ed: str, owner: str, p: Path) -> Set[str]:
    raw = _front(p).get("allowed-tools", "")
    return {"allowed_tool:%s:%s:%s" % (ed, owner, t.strip()) for t in _SPLIT.split(raw) if t.strip()}


def _files(repo: Path) -> Set[str]:
    out: Set[str] = set()
    for p in sorted((repo / "claude/commands").glob("*.md")):
        out.add("command:claude:" + p.stem)
        out |= _allowed("claude", "command/" + p.stem, p)
    for ed in EDITIONS:
        for p in sorted((repo / ed / "skills").glob("*/SKILL.md")):
            out.add("skill:%s:%s" % (ed, p.parent.name))
            out |= _allowed(ed, "skill/" + p.parent.name, p)
    for p in sorted((repo / "claude/agents").glob("*.md")):
        out.add("agent:claude:" + p.stem)
    return out


def _refs(repo: Path) -> Set[str]:
    out: Set[str] = set()
    for ed in EDITIONS:
        base = repo / ed
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(base).parts
            if not p.is_file() or p.suffix not in (".md", ".template", ".json") or set(rel[:-1]) & set(SKIP_DIRS):
                continue
            text = p.read_text(encoding="utf-8")
            out |= {"skill_ref:%s:superpowers:%s" % (ed, s) for s in _SP.findall(text)}
            out |= {"tool_ref:%s:%s" % (ed, t) for t in TOOL_TOKENS if re.search(r"\b%s\b" % t, text)}
    return out


def _cmd_key(cmd: str) -> str:
    found = _SCRIPT.findall(cmd)
    if not found:
        return cmd.strip()
    name, args = found[-1]
    return (name + args).strip()


def _hook_entries(prefix: str, hooks: Optional[Dict[str, Any]]) -> Set[str]:
    out: Set[str] = set()
    for ev, groups in (hooks or {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                out.add("%s:%s:%s:%s" % (prefix, ev, g.get("matcher") or "*", _cmd_key(h.get("command", ""))))
    return out


def _hooks(repo: Path) -> Set[str]:
    out: Set[str] = set()
    for ed in EDITIONS:
        p = repo / ed / "hooks/hooks.json"
        if p.exists():
            out |= _hook_entries("plugin_hook:" + ed, _json(p).get("hooks"))
    chain = repo / "claude/jev/chain.json"
    if chain.exists():
        for event, stages in _json(chain).items():
            if isinstance(stages, list):
                out |= {"chain_stage:%s:%s:%s" % (event, s.get("name", "?"), s.get("component", "core")) for s in stages}
    frag = repo / "claude/settings.fragment.json"
    if frag.exists():
        for comp, body in _json(frag).items():
            out |= _hook_entries("settings_hook:" + comp, body.get("hooks"))
            for kind in ("allow", "deny", "ask"):
                out |= {"permission:%s:%s:%s" % (comp, kind, r) for r in body.get("permissions", {}).get(kind, [])}
            out |= {"env:%s:%s" % (comp, k) for k in body.get("env", {})}
            out |= {"setting:%s:%s" % (comp, k) for k in body if k not in ("hooks", "permissions", "env")}
    return out


def _components(repo: Path) -> Set[str]:
    p = repo / "install/components.json"
    return {"component:" + k for k in _json(p)} if p.exists() else set()


STATIC: Tuple[Callable[[Path], Set[str]], ...] = (_manifests, _files, _refs, _hooks, _components)
