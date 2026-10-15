# Owned core, plan 0: the no-loss inventory — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract; Interfaces and Steps follow. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Snapshot every user-visible surface of Dryas 1.x into `reference/inventory-1.x.json`, and fail CI whenever a later change removes an entry without mapping it to a named equivalent.

**Architecture:** One stdlib script, `tools/inventory.py`, with one collector per surface. Each collector reads the repo (JSON manifests, Markdown front matter, Python modules loaded by path) and returns entries of the form `"<kind>:<name>"`. `--write` stores the sorted list once, from the 1.0.2 tree. `--check` compares the current tree against it, using `reference/inventory-map.json` for renamed or relocated entries. A unittest in `install/tests/` runs the check, so the existing CI matrix enforces it on every branch.

**Tech Stack:** Python 3.9+ stdlib (`ast`, `argparse`, `importlib`, `json`, `unittest.mock`), unittest classes run by pytest.

**Spec:** `docs/superpowers/specs/2026-10-14-owned-core-design.md` (section "Sub-project D", paragraph "No-loss inventory"; Decisions, "Additive only" and "Order").

## Global Constraints

- Python 3.9+ stdlib only. Tests are `unittest.TestCase` classes, run by `python -m pytest -q -rs claude/jev/tests install/tests claude/ruflo/tests` (the CI command). No `enterContext` (3.11+).
- CI matrix: macOS, Ubuntu, Windows × Python 3.9 and 3.12. Entries are names, never file paths. Files are written with `newline="\n"`.
- The snapshot is taken from the 1.0.2 tree (this branch's base, `cc4181a` plus the spec commits) **before any 2.0 change lands**. Plan 0 merges first.
- Collectors read the repo only. Jev logs and thresholds come from an empty temp dir (`JEV_LOG_DIR`, `DRYAS_DATA_ROOT` patched); the user's `~/.dryas` is never read.
- Additive only (spec): a 1.x entry may disappear from the tree only when `reference/inventory-map.json` maps it to an entry that exists now, or to `extra:<component>` where `<component>` is a key of `install/components.json`.
- Files stay under 500 lines.
- Commits: conventional (`feat(tools): …`, `test(tools): …`, `docs: …`), one per task minimum, explicit paths in `git add`, never push.

## Review Focus

1. **Someone regenerates the baseline to hide a loss** (`--write` on an existing snapshot): refuse without `--force` and say why. Pinned in Task 3.
2. **The snapshot differs between machines or runs** (set order, Windows line endings): output is sorted, and two collections are equal. Pinned in Task 3.
3. **A developer's own `~/.dryas`** (custom thresholds, real logs) leaks into the snapshot: collection is identical with a populated `DRYAS_DATA_ROOT`. Pinned in Task 2.
4. **Log code that reassigns a record from itself** (`rec = dict(rec, k=v)`): no recursion error, and both keys are found. Pinned in Task 2.
5. **A malformed manifest** (bad JSON in `chain.json`): `InventoryError` names the file, and the CLI exits 2. Pinned in Task 1.

## File map

Create:
- `tools/inventory.py` — collectors, `collect`, `check`, CLI.
- `install/tests/test_inventory.py` — tests for all three tasks.
- `reference/inventory-1.x.json` — the 1.x baseline (generated in Task 3).
- `reference/inventory-map.json` — `{}` at first; later plans add mappings.

Modify:
- `reference/README.md` — one section on the inventory (Task 3).
- `CONTRIBUTING.md` — one rule (Task 3).

---

## Task 1: Static collectors

Goal: `tools/inventory.py` collects the manifest, command, skill, agent, hook, chain-stage, settings-fragment, component and text-reference surfaces of both editions.
Scope:
- tools/inventory.py
- install/tests/test_inventory.py
Done:
- `python -m pytest -q install/tests/test_inventory.py` passes
Failing test first: install/tests/test_inventory.py :: StaticTest :: test_static_surfaces_of_this_repo

**Interfaces:**
- Produces: `class InventoryError(Exception)`; `ROOT: Path`; `SNAPSHOT = "reference/inventory-1.x.json"`; `MAP = "reference/inventory-map.json"`; `_json(p: Path) -> Any` (raises `InventoryError("<path>: <reason>")`); static collectors `_manifests`, `_files`, `_refs`, `_hooks`, `_components`, each `(repo: Path) -> Set[str]`; `STATIC: Tuple[Callable[[Path], Set[str]], ...]` holding those five, in that order.

Entry kinds produced in this task:

| Kind | Example |
|---|---|
| `mcp_server:<edition>:<name>` | `mcp_server:codex:jev` |
| `plugin_dep:claude:<name>` | `plugin_dep:claude:superpowers` |
| `plugin_config:claude:<key>` | `plugin_config:claude:openrouter_key` |
| `command:claude:<name>` | `command:claude:wplan` |
| `skill:<edition>:<name>` | `skill:codex:wplan` |
| `agent:claude:<name>` | `agent:claude:executor` |
| `allowed_tool:<edition>:<command\|skill>/<name>:<tool>` | `allowed_tool:claude:command/wplan:Skill(superpowers:writing-plans)` |
| `skill_ref:<edition>:superpowers:<skill>` | `skill_ref:claude:superpowers:brainstorming` |
| `tool_ref:<edition>:<token>` | `tool_ref:codex:memory_search` |
| `plugin_hook:<edition>:<Event>:<matcher>:<script args>` | `plugin_hook:codex:PreToolUse:Bash\|apply_patch\|Edit\|Write:chain.py pretool --harness codex` |
| `chain_stage:<event>:<name>:<component>` | `chain_stage:pretool:ruflo-pre-bash:ruflo` |
| `settings_hook:<component>:<Event>:<matcher>:<script args>` | `settings_hook:ruflo:PostToolUse:Write\|Edit\|MultiEdit:hook-handler.cjs post-edit` |
| `permission:<component>:<allow\|deny\|ask>:<rule>` | `permission:core:deny:Skill(superpowers:executing-plans)` |
| `env:<component>:<KEY>` | `env:ruflo:CLAUDE_FLOW_MEMORY_PATH` |
| `setting:<component>:<key>` | `setting:core:model` |
| `component:<name>` | `component:superpowers` |

- [ ] **Step 1: Write the failing tests** in `install/tests/test_inventory.py`:

```python
"""No-loss inventory (owned core, plan 0): every 1.x surface stays or is mapped."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import inventory as inv  # noqa: E402


def _static(repo):
    got = set()
    for c in inv.STATIC:
        got |= c(repo)
    return got


class StaticTest(unittest.TestCase):
    def test_static_surfaces_of_this_repo(self):
        got = _static(ROOT)
        for e in (
            "mcp_server:claude:jev", "mcp_server:codex:jev",
            "plugin_dep:claude:superpowers", "plugin_config:claude:openrouter_key",
            "command:claude:commit", "command:claude:wplan", "command:claude:orchestrate",
            "skill:claude:orchestrate", "skill:codex:wplan", "agent:claude:executor",
            "allowed_tool:claude:skill/orchestrate:mcp__plugin_ruflo-core_ruflo__swarm_init",
            "allowed_tool:claude:skill/orchestrate:Skill(superpowers:brainstorming)",
            "allowed_tool:claude:command/wplan:Skill(superpowers:writing-plans)",
            "skill_ref:claude:superpowers:brainstorming", "tool_ref:codex:memory_search",
            "plugin_hook:claude:PreToolUse:Bash|Edit|Write|MultiEdit|NotebookEdit:chain.py pretool",
            "plugin_hook:codex:PreToolUse:Bash|apply_patch|Edit|Write:chain.py pretool --harness codex",
            "plugin_hook:claude:PreCompact:*:compact_keep.py",
            "chain_stage:pretool:scope-lock:core", "chain_stage:pretool:ruflo-pre-bash:ruflo",
            "chain_stage:prompt:jev-route:jev",
            "settings_hook:ruflo:PostToolUse:Write|Edit|MultiEdit:hook-handler.cjs post-edit",
            "permission:core:deny:Skill(superpowers:executing-plans)",
            "env:ruflo:CLAUDE_FLOW_MEMORY_PATH", "setting:core:model",
            "component:ruflo", "component:superpowers", "component:design",
        ):
            self.assertIn(e, got)

    def test_allowed_tools_keep_parenthesised_commas(self):
        got = _static(ROOT)
        planfile = [e for e in got if e.startswith("allowed_tool:claude:skill/orchestrate:Bash(") and "planfile.py" in e]
        self.assertEqual(len(planfile), 1, planfile)

    def test_generated_codex_copies_are_not_scanned(self):
        self.assertFalse([e for e in _static(ROOT) if ":jev/" in e or ":pstack/" in e])


class MalformedTest(unittest.TestCase):
    def test_bad_json_names_the_file(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "claude/jev").mkdir(parents=True)
        (t / "claude/jev/chain.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(inv.InventoryError) as cm:
            inv._hooks(t)
        self.assertIn("chain.json", str(cm.exception))
```

- [ ] **Step 2: Run** `python -m pytest -q install/tests/test_inventory.py` → FAIL (`ModuleNotFoundError: No module named 'inventory'`).

- [ ] **Step 3: Implement** `tools/inventory.py` (static part):

```python
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
```

- [ ] **Step 4: Run** `python -m pytest -q install/tests/test_inventory.py` → 4 passed. If an expected entry is missing, print `sorted(_static(ROOT))` and fix the collector, not the expectation: the expectations are taken from the 1.0.2 files.

- [ ] **Step 5: Commit**

```bash
git add tools/inventory.py install/tests/test_inventory.py
git commit -m "feat(tools): static collectors for the no-loss inventory"
```

---

## Task 2: Runtime collectors

Goal: add the surfaces that live in Python: MCP tools and their parameters, Jev log names and fields, installer flags, thresholds, and `/tune` report lines; all read from the repo with the user's state isolated.
Scope:
- tools/inventory.py
- install/tests/test_inventory.py
Done:
- `python -m pytest -q install/tests/test_inventory.py` passes
Failing test first: install/tests/test_inventory.py :: RuntimeTest :: test_runtime_surfaces_of_this_repo

**Interfaces:**
- Consumes: Task 1 `InventoryError`, `_json`, `STATIC`.
- Produces: `_load(path: Path, name: str) -> module`; runtime collectors `_mcp_tools`, `_flags`, `_thresholds`, `_logs`, `_tune`, each `(repo: Path) -> Set[str]`; `RUNTIME: Tuple[...]` holding them; `collect(repo: Path = ROOT) -> List[str]` (sorted, `STATIC + RUNTIME`).

Entry kinds produced in this task: `mcp_tool:jev:<name>`, `mcp_param:jev:<tool>.<param>`, `log:<file>`, `log_field:<file>:<key>` (`log_field:*:<key>` for the keys `jevlog.append` adds to every record), `component:optional:<name>`, `install_flag:--<flag>` and `install_flag:--<flag>=<choice>`, `threshold:<section>.<key>`, `tune_line:<label>`.

- [ ] **Step 1: Write the failing tests** (append to `install/tests/test_inventory.py`):

```python
import os
from unittest import mock


class RuntimeTest(unittest.TestCase):
    def test_runtime_surfaces_of_this_repo(self):
        got = set(inv.collect(ROOT))
        for e in (
            "mcp_tool:jev:jev_judge", "mcp_tool:jev:log_dispatch", "mcp_param:jev:log_dispatch.attempt",
            "mcp_param:jev:log_override.jev_confidence",
            "log:gate", "log:route", "log:dispatch", "log:escalations", "log:overrides",
            "log_field:gate:decision", "log_field:gate:via", "log_field:route:route_conf",
            "log_field:dispatch:task", "log_field:review:critical", "log_field:escalations:to_model",
            "log_field:*:ts", "log_field:*:session_id",
            "component:optional:ruflo", "component:optional:superpowers",
            "install_flag:--no-ruflo", "install_flag:--no-superpowers", "install_flag:--no-jev",
            "install_flag:--openrouter-key", "install_flag:--no-flowobserve", "install_flag:--harness=codex",
            "threshold:gate.min_confidence", "threshold:dispatch.haiku_default",
            "threshold:escalation.opus_failures_before_fable",
            "tune_line:Jev calibration", "tune_line:Tool calls", "tune_line:Haiku->Sonnet climb rate (healthy at or under escalation.haiku_climb_max)",
            "tune_line:Swarm vs plain token ratio", "tune_line:Proposals (apply only after approval)",
            "tune_line:PROPOSALS_JSON",
        ):
            self.assertIn(e, got)

    def test_collect_is_sorted_and_stable(self):
        a = inv.collect(ROOT)
        self.assertEqual(a, sorted(a))
        self.assertEqual(a, inv.collect(ROOT))

    def test_user_state_does_not_leak(self):
        before = inv.collect(ROOT)
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "jev/logs").mkdir(parents=True)
        (t / "jev/thresholds.json").write_text(json.dumps({"gate": {"mine_only": 1}}), encoding="utf-8")
        (t / "jev/logs/gate.jsonl").write_text('{"decision":"allow","mine_only":1}\n', encoding="utf-8")
        with mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": str(t), "JEV_LOG_DIR": str(t / "jev/logs")}):
            self.assertEqual(inv.collect(ROOT), before)


class LogFieldTest(unittest.TestCase):
    def test_self_reassigned_record_is_followed_without_recursion(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "claude/jev").mkdir(parents=True)
        (t / "claude/jev/x.py").write_text(
            "import jevlog\n"
            "def f(extra):\n"
            "    rec = {'a': 1}\n"
            "    rec = dict(rec, b=2, **extra)\n"
            "    jevlog.append('x', rec)\n", encoding="utf-8")
        got = inv._logs(t)
        self.assertIn("log:x", got)
        self.assertIn("log_field:x:a", got)
        self.assertIn("log_field:x:b", got)
```

- [ ] **Step 2: Run** `python -m pytest -q install/tests/test_inventory.py` → FAIL (`AttributeError: module 'inventory' has no attribute 'collect'`).

- [ ] **Step 3: Implement** (append to `tools/inventory.py`, after `STATIC`):

```python
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
```

The thresholds collector reads `DEFAULTS` and the shipped `thresholds.json` only; `thresholds.py` loads the user's file lazily inside its functions, which this collector never calls. `_isolated` sets the three variables `claude/jev/paths.py` reads (`DRYAS_DATA_ROOT`, `JEV_LOG_DIR`, `JEV_THRESHOLDS`); `test_user_state_does_not_leak` is the proof.

- [ ] **Step 4: Run** `python -m pytest -q install/tests/test_inventory.py` → 8 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/inventory.py install/tests/test_inventory.py
git commit -m "feat(tools): runtime collectors for the no-loss inventory"
```

---

## Task 3: Baseline, map, check and CI

Goal: write the 1.x baseline once, add the map, add `--check`, and make CI fail on any unmapped loss; document the rule.
Scope:
- tools/inventory.py
- install/tests/test_inventory.py
- reference/inventory-1.x.json
- reference/inventory-map.json
- reference/README.md
- CONTRIBUTING.md
Done:
- `python -m pytest -q -rs claude/jev/tests install/tests claude/ruflo/tests` passes
- `python tools/inventory.py --check` exits 0 and prints `0 problems`
Failing test first: install/tests/test_inventory.py :: CheckTest :: test_repo_has_no_unmapped_loss

**Interfaces:**
- Consumes: Task 2 `collect(repo) -> List[str]`; Task 1 `_json`, `SNAPSHOT`, `MAP`, `InventoryError`.
- Produces: `check(snapshot: Iterable[str], current: Iterable[str], mapping: Dict[str, str], extras: Iterable[str]) -> List[str]` (problem lines, empty when clean); `main(argv: Optional[List[str]] = None) -> int` (0 ok, 1 problems or refused write, 2 collector error). Problem line prefixes: `lost: `, `stale map: `, `unknown map entry: `.

- [ ] **Step 1: Write the failing tests** (append):

```python
class CheckTest(unittest.TestCase):
    def test_repo_has_no_unmapped_loss(self):
        self.assertEqual(inv.main(["--check"]), 0, "run: python tools/inventory.py --check")

    def test_lost_entry_fails(self):
        self.assertEqual(inv.check(["a:1", "a:2"], ["a:1"], {}, []), ["lost: a:2"])

    def test_mapped_entry_passes_only_when_target_exists(self):
        self.assertEqual(inv.check(["a:2"], ["b:2"], {"a:2": "b:2"}, []), [])
        self.assertEqual(inv.check(["a:2"], [], {"a:2": "b:2"}, []), ["lost: a:2 -> b:2, target missing"])

    def test_extra_mapping_needs_a_listed_component(self):
        self.assertEqual(inv.check(["a:2"], [], {"a:2": "extra:ruflo"}, ["ruflo"]), [])
        self.assertEqual(inv.check(["a:2"], [], {"a:2": "extra:nope"}, ["ruflo"]),
                         ["lost: a:2 -> extra:nope, no such optional component"])

    def test_map_stays_honest(self):
        self.assertEqual(inv.check(["a:1"], ["a:1"], {"a:1": "b:1"}, []), ["stale map: a:1 still exists"])
        self.assertEqual(inv.check([], [], {"z:9": "b:1"}, []), ["unknown map entry: z:9"])

    def test_write_refuses_to_replace_the_baseline(self):
        self.assertEqual(inv.main(["--write"]), 1)

    def test_baseline_is_the_current_1x_surface(self):
        data = json.loads((ROOT / inv.SNAPSHOT).read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "1.0.2")
        self.assertEqual(data["entries"], sorted(data["entries"]))
        self.assertGreater(len(data["entries"]), 150)

    def test_baseline_has_unix_newlines(self):
        self.assertNotIn(b"\r\n", (ROOT / inv.SNAPSHOT).read_bytes())

    def test_collector_error_exits_2(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "claude/jev").mkdir(parents=True)
        (t / "claude/jev/chain.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(inv.main(["--list", "--repo", str(t)]), 2)
```

- [ ] **Step 2: Run** `python -m pytest -q install/tests/test_inventory.py` → FAIL (`AttributeError: module 'inventory' has no attribute 'main'`).

- [ ] **Step 3: Implement** (append to `tools/inventory.py`):

```python
def check(snapshot: Iterable[str], current: Iterable[str], mapping: Dict[str, str], extras: Iterable[str]) -> List[str]:
    snap, cur, ext = set(snapshot), set(current), set(extras)
    problems: List[str] = []
    for e in sorted(snap):
        target = mapping.get(e)
        if e in cur:
            if target is not None:
                problems.append("stale map: %s still exists" % e)
        elif target is None:
            problems.append("lost: %s" % e)
        elif target.startswith("extra:"):
            if target[len("extra:"):] not in ext:
                problems.append("lost: %s -> %s, no such optional component" % (e, target))
        elif target not in cur:
            problems.append("lost: %s -> %s, target missing" % (e, target))
    problems += ["unknown map entry: %s" % k for k in sorted(set(mapping) - snap)]
    return problems


def _version(repo: Path) -> str:
    return str(_json(repo / "claude/.claude-plugin/plugin.json").get("version", ""))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="inventory", description="No-loss inventory of the Dryas surface.")
    mode = ap.add_mutually_exclusive_group(required=True)
    for m in ("list", "write", "check"):
        mode.add_argument("--" + m, action="store_true")
    ap.add_argument("--force", action="store_true", help="with --write: rebuild the baseline (only from a 1.x tree)")
    ap.add_argument("--repo", default=str(ROOT))
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    try:
        cur = collect(repo)
        if a.list:
            print("\n".join(cur))
            return 0
        snap = repo / SNAPSHOT
        if a.write:
            if snap.exists() and not a.force:
                print("inventory: %s is the 1.x baseline and already exists; --force rebuilds it, "
                      "and only from a 1.x tree" % SNAPSHOT, file=sys.stderr)
                return 1
            with open(snap, "w", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"version": _version(repo), "entries": cur}, indent=1) + "\n")
            print("inventory: wrote %d entries to %s" % (len(cur), SNAPSHOT))
            return 0
        base = _json(snap)["entries"]
        mp = repo / MAP
        mapping = _json(mp) if mp.exists() else {}
        problems = check(base, cur, mapping, _json(repo / "install/components.json").keys())
    except InventoryError as e:
        print("inventory: %s" % e, file=sys.stderr)
        return 2
    for p in problems:
        print(p)
    print("inventory: %d baseline entries, %d problems" % (len(base), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Generate the baseline and the empty map** (on this 1.0.2 tree, before any 2.0 change):

```bash
python tools/inventory.py --write
printf '{}\n' > reference/inventory-map.json
python tools/inventory.py --check
```

Expected: `inventory: wrote N entries to reference/inventory-1.x.json` with N > 150, then `inventory: N baseline entries, 0 problems`. Open the baseline and skim it: every kind from the two tables above appears, and no entry contains a home-directory path.

- [ ] **Step 5: Document.** Add to `reference/README.md`, after the "Bindings" table:

```markdown
## No-loss inventory

`reference/inventory-1.x.json` lists every user-visible surface of Dryas 1.x: MCP tools and parameters, commands, skills, agents, allowed tools, plugin and settings hooks, chain stages, permissions, env keys, installer flags, thresholds, Jev log fields and `/tune` report lines. `python tools/inventory.py --check` (run by `install/tests/test_inventory.py` in CI) fails when one of them disappears unless `reference/inventory-map.json` maps it to the entry that replaces it, or to `extra:<component>` when it lives on in an optional component. The baseline is written once and never regenerated to make a check pass.
```

Add to `CONTRIBUTING.md`, in its list of rules:

```markdown
- Nothing is removed without a replacement: if `python tools/inventory.py --check` reports `lost:`, add the equivalent or map the entry in `reference/inventory-map.json` (see [reference/README.md](reference/README.md#no-loss-inventory)). Never rebuild `reference/inventory-1.x.json` to make the check pass.
```

- [ ] **Step 6: Run the full suite** `python -m pytest -q -rs claude/jev/tests install/tests claude/ruflo/tests` → all pass (518 before plus the new inventory tests). Also run `python tools/sync_codex_plugin.py --check` → no drift (this plan touches neither `claude/jev` nor `claude/pstack`).

- [ ] **Step 7: Commit**

```bash
git add tools/inventory.py install/tests/test_inventory.py reference/inventory-1.x.json reference/inventory-map.json reference/README.md CONTRIBUTING.md
git commit -m "feat(tools): 1.x no-loss baseline and inventory check in CI"
```

---

## Self-review (done while writing)

- **Spec coverage.** Spec, "No-loss inventory": the snapshot covers MCP tools (Task 2), slash commands, skills and agents (Task 1), hook stages and settings hooks (Task 1), installer flags (Task 2), `thresholds.json` keys (Task 2), JSONL record fields (Task 2) and `/tune` report lines (Task 2). The spec lists these plus allowed tools, permissions and env keys, which Task 1 also collects because the additive-only rule covers them. "Each entry exists in 2.0 or maps to a named equivalent" is `check` (Task 3). "Runs in CI on every sub-project branch" is `test_repo_has_no_unmapped_loss` in `install/tests`, which `ci.yml` already runs on three OSes. "Lands first" is the Global Constraints line plus Step 4's timing.
- **Placeholders.** None. Entry strings in the tests were checked against the 1.0.2 files (hooks, deny rules, `inputSchema`, plugin version, `paths.py` variable names, `/tune` output on empty logs).
- **Type consistency.** `STATIC`/`RUNTIME` are tuples of `(Path) -> Set[str]`; `collect` returns `List[str]`; `check` takes iterables and a `Dict[str, str]` and returns `List[str]`; `main` returns `int`. Names match across tasks.
- **Review Focus.** Each of the five lines has a test in its owning task: refused `--write` (Task 3), sorted and stable (Task 2) plus Unix newlines (Task 3), user-state isolation (Task 2), self-reassigned records (Task 2), malformed JSON (Task 1 for the error, Task 3 for exit code 2).
