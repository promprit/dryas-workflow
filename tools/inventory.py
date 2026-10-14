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


def _isolated(tmp: str) -> Dict[str, str]:
    return {"DRYAS_DATA_ROOT": tmp, "JEV_LOG_DIR": os.path.join(tmp, "jev", "logs"),
            "JEV_THRESHOLDS": os.path.join(tmp, "jev", "thresholds.json")}


def _load(path: Path, name: str) -> Any:
    """Import a repo module by path (its folder on sys.path while it loads, for sibling imports)."""
    d = str(path.parent)
    sys.path.insert(0, d)
    try:
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        raise InventoryError("%s: %s: %s" % (path.as_posix(), type(e).__name__, e))
    finally:
        sys.path.remove(d)


def _mcp_tools(repo: Path) -> Set[str]:
    m = _load(repo / "claude/jev/jev_mcp.py", "inventory_jev_mcp")
    out: Set[str] = set()
    for t in m.TOOLS:
        out.add("mcp_tool:jev:" + t["name"])
        out |= {"mcp_param:jev:%s.%s" % (t["name"], p) for p in t.get("inputSchema", {}).get("properties", {})}
    for file, strs, ints in m.LOG_TOOLS.values():
        out |= {"log:" + file} | {"log_field:%s:%s" % (file, f) for f in list(strs) + list(ints)}
    by_tool = {t["name"]: t for t in m.TOOLS}
    for tool, file in (("log_escalation", "escalations"), ("log_override", "overrides")):
        props = by_tool.get(tool, {}).get("inputSchema", {}).get("properties", {})
        out |= {"log:" + file} | {"log_field:%s:%s" % (file, p) for p in props}
    return out


def _flags(repo: Path) -> Set[str]:
    rc = _load(repo / "install/run_cmd.py", "inventory_run_cmd")
    with mock.patch.object(argparse.ArgumentParser, "parse_args", lambda self, *a, **k: self):
        parser = rc.parse([])  # parse() builds the parser; parse_args is patched to hand it back
    out = {"component:optional:" + c for c in rc.OPTIONAL}
    for action in parser._actions:
        for opt in action.option_strings:
            if opt.startswith("--") and opt != "--help":
                out.add("install_flag:" + opt)
                out |= {"install_flag:%s=%s" % (opt, c) for c in (action.choices or [])}
    return out


def _flat(prefix: str, d: Dict[str, Any], out: Set[str]) -> None:
    for k, v in d.items():
        if isinstance(v, dict):
            _flat(prefix + k + ".", v, out)
        else:
            out.add("threshold:" + prefix + k)


def _thresholds(repo: Path) -> Set[str]:
    th = _load(repo / "claude/jev/thresholds.py", "inventory_thresholds")
    out: Set[str] = set()
    _flat("", th.DEFAULTS, out)
    _flat("", _json(repo / "claude/jev/thresholds.json"), out)
    return out


def _dict_keys(node: Any, assigns: Dict[str, List[Any]], seen: Set[int]) -> Set[str]:
    if id(node) in seen:
        return set()
    seen.add(id(node))
    if isinstance(node, ast.Dict):
        return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "dict":
        keys = {kw.arg for kw in node.keywords if kw.arg}
        for a in node.args:
            keys |= _dict_keys(a, assigns, seen)
        return keys
    if isinstance(node, ast.Name):
        keys: Set[str] = set()
        for value in assigns.get(node.id, []):
            keys |= _dict_keys(value, assigns, seen)
        return keys
    return set()


def _logs(repo: Path) -> Set[str]:
    out = {"log_field:*:ts", "log_field:*:session_id", "log_field:*:cwd"}  # added by jevlog.append to every record
    for p in sorted((repo / "claude/jev").glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"), p.as_posix())
        for scope in [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            assigns: Dict[str, List[Any]] = {}
            for n in ast.walk(scope):
                if isinstance(n, ast.Assign):
                    for t in n.targets:
                        if isinstance(t, ast.Name):
                            assigns.setdefault(t.id, []).append(n.value)
            for n in ast.walk(scope):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "append"
                        and getattr(n.func.value, "id", "") == "jevlog" and n.args
                        and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                    name = n.args[0].value
                    out.add("log:" + name)
                    if len(n.args) > 1:
                        out |= {"log_field:%s:%s" % (name, k) for k in _dict_keys(n.args[1], assigns, set())}
    return out


def _tune(repo: Path) -> Set[str]:
    tmp = tempfile.mkdtemp()
    try:
        with mock.patch.dict(os.environ, _isolated(tmp)):
            os.makedirs(os.path.join(tmp, "jev", "logs"))
            tune = _load(repo / "claude/jev/tune.py", "inventory_tune")
            text = tune.render(tune.build(os.path.join(tmp, "jev", "logs")), [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out: Set[str] = set()
    for line in text.splitlines():
        if line.startswith("#"):
            out.add("tune_line:" + line.lstrip("#").strip())
        elif line.startswith("- ") and ":" in line:
            out.add("tune_line:" + line[2:].split(":", 1)[0].strip())
        elif line.startswith("| ") and "---" not in line:
            out.add("tune_line:table " + line.strip())
        elif line.startswith("PROPOSALS_JSON"):
            out.add("tune_line:PROPOSALS_JSON")
    return out


RUNTIME: Tuple[Callable[[Path], Set[str]], ...] = (_mcp_tools, _flags, _thresholds, _logs, _tune)


def collect(repo: Path = ROOT) -> List[str]:
    out: Set[str] = set()
    for c in STATIC + RUNTIME:
        out |= c(repo)
    return sorted(out)
