# Dryas as a Claude Code Plugin — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Claude Code edition as a plugin (`dryas@dryas-workflow`) plus a thin `setup` so `install.sh --claude-dir <dir>` sets up any Claude config dir, with one shared state root `~/.dryas`.

**Architecture:** `claude/` becomes the plugin root (manifest, `hooks/hooks.json`, `.mcp.json`; agents, commands, skills load as plugin parts). Every Jev runtime path goes through one new module, `claude/jev/paths.py`. The installer gains `install/plugin_setup.py` (install plugin with `CLAUDE_CONFIG_DIR=<dir>`, merge `model`/`env`/`permissions`, write `chain.local.json` and `accounts.json`) and `install/migrate.py` (copy install → plugin). Codex keeps today's copy install into `~/.claude`, reduced to runtime files.

**Tech Stack:** Python 3.9+ stdlib, `unittest` (run with pytest), POSIX sh / PowerShell entry scripts, Claude Code plugin manifests (JSON).

**Spec:** `docs/superpowers/specs/2026-10-12-plugin-packaging-design.md`

## Spec amendments (found while planning; confirm before Task 1)

The spec missed four things. This plan fixes them as follows; each is marked **[A1]–[A4]** where it is used.

- **[A1] Markdown tokens.** Agents, commands and skills use `{{CD}}` / `{{PY}}` tokens and `<!-- pstack-picks -->` blocks that the copy installer rendered. A plugin ships them raw. Fix: `{{CD}}` becomes `${CLAUDE_PLUGIN_ROOT}` (Claude Code substitutes it in plugin skill, command and agent bodies). `"{{PY}}" -X utf8` becomes a launcher, `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py"`, a `#!/usr/bin/env sh` script that runs `"${DRYAS_PY:-python3}" -X utf8 "$@"`. After substitution the Bash command holds only literal absolute paths, so permission rules can match it. `<!-- pstack-picks -->` blocks stay in the files; when pstack-picks is off, the rules hook adds one line telling Claude to skip them. Hardcoded `~/.claude/jev/...` and `~/.claude/skills/...` paths in Markdown are rewritten.
- **[A2] Codex still reads `~/.claude`.** `codex_target.py` points Codex hooks and MCP at `~/.claude/jev/*.py` and `~/.claude/ruflo/*`. To keep Codex unchanged, the copy install stays for `--harness codex|both`, but copies only runtime files (`jev/`, `ruflo/`, `pstack/`), never `agents/`, `commands/`, `skills/` (those would duplicate the plugin's).
- **[A3] Jev key in hooks.** `gate.py`, `route.py`, `compact_keep.py` call OpenRouter from hooks. Hooks get the plugin option as `CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY`, not `OPENROUTER_API_KEY`. `jev_client` reads both (shell env first). The MCP server gets it via `env` in `.mcp.json`.
- **[A4] Ruflo stays in user settings.** Ruflo hooks are optional and point at helpers in `~/.dryas`, so they stay in the settings fragment that `setup` merges (not in `hooks.json`). The MCP shim (`ruflo/mcp-shim`) is copied to `~/.dryas/ruflo/mcp-shim` because its `dist` link must not be created inside the plugin (the repo clone).

Two facts this plan relies on, from the docs check on 2026-10-12 (re-checked in Task 1 and the release check):
- A local-path marketplace plugin loads in place, so `installPath` is `<repo>/claude` and stable. `setup` reads `installPath` from `installed_plugins.json` and uses it for `$CD` in settings, so a copied/versioned install also works until the next update (re-run setup after updating).
- Absolute paths in `Read(...)` rules need a leading `//`; `~/` works for the default root.

## Global Constraints

- Python 3.9+ stdlib only; tests are `unittest` classes run by `python -m pytest -q claude/jev/tests install/tests claude/ruflo/tests`.
- CI matrix: macOS, Ubuntu, Windows × Python 3.9, 3.12. No Claude CLI in CI; use `install/tests/fakecli.py`.
- Plugin name `dryas`, marketplace name `dryas-workflow`. Names starting `claude-`, `anthropic-`, `cc-plugin-` are rejected.
- State root: `$DRYAS_DATA_ROOT`, default `~/.dryas`. Existing `JEV_*` env overrides still win.
- Hook command form: `"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/jev/<script>.py" [args]`.
- Rules injected by SessionStart stay under 10,000 characters for every component combination.
- Hooks fail open, except scope lock and Jev gate (keep deny behavior). `chain.py` always exits 0.
- `setup` never touches settings when the plugin install or its verification fails.
- Portability: no `/bin/sh`, `/bin/bash`, `/usr/bin/env bash`, `shell=True`, literal `"/tmp/"` in shipped files (`install/tests/test_portability.py`).
- Codex (`codex/`, `codex_target.py`) behavior is unchanged.
- Commits: conventional (`feat(...)`, `fix(...)`, `test(...)`, `docs(...)`), one per task minimum.

## File map

Create:
- `claude/.claude-plugin/plugin.json` — plugin manifest.
- `.claude-plugin/marketplace.json` — repo is the marketplace.
- `claude/hooks/hooks.json` — core + jev hooks, plus the rules hook.
- `claude/.mcp.json` — Jev MCP server.
- `claude/bin/dryas-py` — sh launcher for Markdown commands [A1].
- `claude/jev/paths.py` — the only module that knows the state layout.
- `claude/jev/gating.py` — `gate_blocks` (moved from `install/render.py` so the plugin can use it).
- `claude/jev/rules_inject.py` — SessionStart hook: rules as `additionalContext`.
- `install/plugin_setup.py` — `setup` and `uninstall` for one config dir.
- `install/migrate.py` — copy install → plugin.
- `install/ruflo_runtime.py` — helpers and MCP shim into `~/.dryas/ruflo` [A4].
- Tests: `claude/jev/tests/test_paths.py`, `claude/jev/tests/test_rules_inject.py`, `claude/jev/tests/test_chain_local.py`, `install/tests/test_plugin_shape.py`, `install/tests/test_hook_shell.py`, `install/tests/test_plugin_setup.py`, `install/tests/test_migrate.py`, `install/tests/test_ruflo_runtime.py`.

Modify:
- `claude/jev/{jevlog,thresholds,handoff_paths,handoff,compact_keep,context_watch,jev_client,chain}.py`, `claude/jev/chain.json`
- `claude/settings.fragment.json`, `claude/CLAUDE.md.template`, `claude/agents/executor.md`, `claude/commands/{handoff,tune,orchestrate}.md`, `claude/skills/{orchestrate,interrogate,benchmark-checklist}/SKILL.md`
- `install/{render,dryas_install,run_cmd}.py`, `install/install.sh`, `install/install.ps1`, `tools/release_check.py`
- Tests touching the old Claude copy path: `install/tests/{test_run_cmd,test_dryas_install,test_e2e_install,test_pstack_install,test_portability,test_shipped_files}.py` (update, never delete assertions without replacing them).
- Docs: `docs/install.md`, `docs/harnesses.md`, `README.md`, `CONTRIBUTING.md`, `reference/README.md`, `docs/release-check.md`, `docs/roadmap.md`.

---

### Task 1: Prove the hook command line runs under Git Bash (Windows gate)

The spec makes this the first task: if it fails on the Windows runner, stop and report (a `.cmd` launcher would then come into scope).

**Files:**
- Create: `install/tests/test_hook_shell.py`
- Create: `claude/bin/dryas-py`

**Interfaces:**
- Produces: `claude/bin/dryas-py` (executable, mode 755), contract: `dryas-py <script> [args]` == `"${DRYAS_PY:-python3}" -X utf8 <script> [args]`.
- Produces: `test_hook_shell.find_bash() -> Optional[str]` (reused by Task 5's shape test).

- [ ] **Step 1: Write the failing test**

```python
# install/tests/test_hook_shell.py
"""The plugin's hook and launcher command lines run under the shell Claude Code uses:
sh -c on macOS/Linux, Git Bash on Windows."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
HOOK = '"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/jev/echo_hook.py" pretool'
LAUNCH = '"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/echo_hook.py" pretool'
ECHO = "import sys, json\nprint(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read(), 'utf8': sys.flags.utf8_mode}))\n"


def find_bash() -> Optional[str]:
    """Git Bash on Windows (never WSL's System32 bash), sh elsewhere."""
    if os.name != "nt":
        return shutil.which("sh")
    for cand in (shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe"):
        if cand and "system32" not in cand.lower() and os.path.isfile(cand):
            return cand
    return None


def fwd(p) -> str:
    return str(p).replace("\\", "/")


class HookShellTest(unittest.TestCase):
    def setUp(self):
        self.sh = find_bash()
        if not self.sh:
            self.skipTest("no sh / Git Bash")
        self.root = Path(tempfile.mkdtemp(prefix="dryas plugin "))  # space on purpose
        (self.root / "jev").mkdir()
        (self.root / "jev" / "echo_hook.py").write_text(ECHO, encoding="utf-8")
        (self.root / "bin").mkdir()
        shutil.copy2(str(ROOT / "claude" / "bin" / "dryas-py"), str(self.root / "bin" / "dryas-py"))

    def tearDown(self):
        shutil.rmtree(str(self.root), ignore_errors=True)

    def _run(self, cmd: str, py: Optional[str]):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=fwd(self.root))
        env.pop("DRYAS_PY", None)
        if py:
            env["DRYAS_PY"] = fwd(py)
        p = subprocess.run([self.sh, "-c", cmd], input="{\"x\": 1}", capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        import json
        return json.loads(p.stdout)

    def test_hook_form_with_dryas_py(self):
        out = self._run(HOOK, sys.executable)
        self.assertEqual(out["argv"], ["pretool"])
        self.assertEqual(out["stdin"], "{\"x\": 1}")
        self.assertEqual(out["utf8"], 1)

    def test_launcher_form_with_dryas_py(self):
        out = self._run(LAUNCH, sys.executable)
        self.assertEqual(out["argv"], ["pretool"])
        self.assertEqual(out["utf8"], 1)

    def test_hook_form_falls_back_to_python3(self):
        if not shutil.which("python3"):
            self.skipTest("no python3 on PATH")
        self.assertEqual(self._run(HOOK, None)["argv"], ["pretool"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q install/tests/test_hook_shell.py`
Expected: FAIL / ERROR — `FileNotFoundError` for `claude/bin/dryas-py`.

- [ ] **Step 3: Write the launcher**

```sh
#!/usr/bin/env sh
# Dryas launcher for commands Claude runs from plugin Markdown: the interpreter setup chose (DRYAS_PY), UTF-8 mode.
exec "${DRYAS_PY:-python3}" -X utf8 "$@"
```

Save as `claude/bin/dryas-py`, then: `chmod 755 claude/bin/dryas-py && git add --chmod=+x claude/bin/dryas-py`.

- [ ] **Step 4: Run tests to verify they pass locally**

Run: `python -m pytest -q install/tests/test_hook_shell.py install/tests/test_portability.py`
Expected: PASS (portability: `#!/usr/bin/env sh` hits no banned pattern).

- [ ] **Step 5: Commit, push the branch, and check the Windows CI jobs**

```bash
git add install/tests/test_hook_shell.py claude/bin/dryas-py
git commit -m "test(plugin): prove hook and launcher command lines run under sh and Git Bash"
git push -u origin feat/plugin-packaging
```

Read the `windows-latest` jobs (both Python versions) for `test_hook_shell.py`. **Gate:** all three tests must PASS there (not SKIP). If they fail or skip on Windows, stop and report to the user with the job log; do not start Task 2.

---

### Task 2: `paths.py` — one state root for every account

**Files:**
- Create: `claude/jev/paths.py`
- Create: `claude/jev/tests/test_paths.py`
- Modify: `claude/jev/jevlog.py:8-9`, `claude/jev/handoff_paths.py:14-15`, `claude/jev/handoff.py:35-36`, `claude/jev/compact_keep.py:20-21`, `claude/jev/context_watch.py:22-23`, `claude/jev/thresholds.py:37-47,152-164`

**Interfaces:**
- Produces (all return `str`, never raise):
  - `paths.data_root()` — `$DRYAS_DATA_ROOT` or `~/.dryas`
  - `paths.jev_dir()` — `<root>/jev`
  - `paths.log_dir()` — `$JEV_LOG_DIR` or `<root>/jev/logs`
  - `paths.thresholds_file()` — `$JEV_THRESHOLDS` or `<root>/jev/thresholds.json`
  - `paths.handoff_dir()` — `$JEV_HANDOFF_DIR` or `<root>/jev/handoff`
  - `paths.compact_dir()` — `$JEV_COMPACT_DIR` or `<root>/jev/compact`
  - `paths.chain_local()` — `$JEV_CHAIN_LOCAL` or `<root>/chain.local.json`
  - `paths.accounts_file()` — `<root>/accounts.json`
  - `paths.ruflo_dir()` — `<root>/ruflo`
  - `paths.projects_dir()` — `$JEV_PROJECTS_DIR`, else `$CLAUDE_CONFIG_DIR/projects`, else `~/.claude/projects`
  - `paths.plugin_root()` — `$CLAUDE_PLUGIN_ROOT`, else the parent of `claude/jev/`
  - `paths.python()` — `$DRYAS_PY`, else `sys.executable`
- `thresholds.path()` keeps its name; it now means the user file. Shipped `claude/jev/thresholds.json` becomes read-only defaults layered under it.

- [ ] **Step 1: Write the failing tests**

```python
# claude/jev/tests/test_paths.py
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths

HOME = os.path.expanduser("~")
CLEAN = {k: v for k, v in os.environ.items()
         if not k.startswith("JEV_") and k not in ("DRYAS_DATA_ROOT", "CLAUDE_CONFIG_DIR", "CLAUDE_PLUGIN_ROOT", "DRYAS_PY")}


class PathsTest(unittest.TestCase):
    def test_defaults(self):
        with mock.patch.dict(os.environ, CLEAN, clear=True):
            root = os.path.join(HOME, ".dryas")
            self.assertEqual(paths.data_root(), root)
            self.assertEqual(paths.log_dir(), os.path.join(root, "jev", "logs"))
            self.assertEqual(paths.thresholds_file(), os.path.join(root, "jev", "thresholds.json"))
            self.assertEqual(paths.handoff_dir(), os.path.join(root, "jev", "handoff"))
            self.assertEqual(paths.compact_dir(), os.path.join(root, "jev", "compact"))
            self.assertEqual(paths.chain_local(), os.path.join(root, "chain.local.json"))
            self.assertEqual(paths.accounts_file(), os.path.join(root, "accounts.json"))
            self.assertEqual(paths.ruflo_dir(), os.path.join(root, "ruflo"))
            self.assertEqual(paths.projects_dir(), os.path.join(HOME, ".claude", "projects"))
            self.assertEqual(paths.python(), sys.executable)
            self.assertTrue(os.path.isfile(os.path.join(paths.plugin_root(), "jev", "paths.py")))

    def test_data_root_override(self):
        d = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, dict(CLEAN, DRYAS_DATA_ROOT=d), clear=True):
            self.assertEqual(paths.log_dir(), os.path.join(d, "jev", "logs"))
            self.assertEqual(paths.chain_local(), os.path.join(d, "chain.local.json"))

    def test_jev_overrides_win(self):
        env = dict(CLEAN, DRYAS_DATA_ROOT="/r", JEV_LOG_DIR="/l", JEV_THRESHOLDS="/t.json", JEV_HANDOFF_DIR="/h",
                   JEV_COMPACT_DIR="/c", JEV_PROJECTS_DIR="/p", JEV_CHAIN_LOCAL="/cl.json")
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual((paths.log_dir(), paths.thresholds_file(), paths.handoff_dir(), paths.compact_dir(),
                              paths.projects_dir(), paths.chain_local()),
                             ("/l", "/t.json", "/h", "/c", "/p", "/cl.json"))

    def test_projects_dir_follows_config_dir(self):
        with mock.patch.dict(os.environ, dict(CLEAN, CLAUDE_CONFIG_DIR="/acct/team"), clear=True):
            self.assertEqual(paths.projects_dir(), os.path.join("/acct/team", "projects"))

    def test_plugin_root_and_python_from_env(self):
        with mock.patch.dict(os.environ, dict(CLEAN, CLAUDE_PLUGIN_ROOT="/plug", DRYAS_PY="/py"), clear=True):
            self.assertEqual((paths.plugin_root(), paths.python()), ("/plug", "/py"))


class ModulesUsePathsTest(unittest.TestCase):
    """Every state path in jev/ comes from paths.py (no hardcoded ~/.claude/jev)."""

    def test_no_hardcoded_claude_jev(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        hits = []
        for n in sorted(os.listdir(here)):
            if n.endswith(".py") and n != "paths.py":
                with open(os.path.join(here, n), encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if "~/.claude/jev" in line or "~/.claude/projects\")" in line:
                            hits.append("%s:%d" % (n, i))
        self.assertEqual(hits, [])

    def test_modules_delegate(self):
        import compact_keep, context_watch, handoff, handoff_paths, jevlog, thresholds
        d = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, dict(CLEAN, DRYAS_DATA_ROOT=d), clear=True):
            self.assertEqual(jevlog.log_dir(), paths.log_dir())
            self.assertEqual(handoff_paths.handoff_dir(), paths.handoff_dir())
            self.assertEqual(compact_keep.compact_dir(), paths.compact_dir())
            self.assertEqual(handoff.projects_dir(), paths.projects_dir())
            self.assertEqual(context_watch._state_dir(), os.path.join(paths.handoff_dir(), ".warned"))
            self.assertEqual(thresholds.path(), paths.thresholds_file())


class ThresholdLayersTest(unittest.TestCase):
    """DEFAULTS <- shipped jev/thresholds.json <- user file; /tune writes only the user file."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, dict(CLEAN, DRYAS_DATA_ROOT=self.d), clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_shipped_defaults_apply_without_user_file(self):
        import thresholds
        self.assertIn("cd", thresholds.load()["gate"]["allowlist"])  # "cd" is only in the shipped file

    def test_set_value_creates_user_file_and_keeps_shipped(self):
        import json, thresholds
        thresholds.set_value("gate.min_confidence", 0.8)
        with open(paths.thresholds_file(), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"gate": {"min_confidence": 0.8}})
        th = thresholds.load()
        self.assertEqual(th["gate"]["min_confidence"], 0.8)
        self.assertIn("cd", th["gate"]["allowlist"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q claude/jev/tests/test_paths.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'paths'`.

- [ ] **Step 3: Write `paths.py`**

```python
# claude/jev/paths.py
"""The one place that knows where Dryas keeps state. Shared by every Claude config dir (account):
$DRYAS_DATA_ROOT (default ~/.dryas). JEV_* env overrides win. Never raises."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def data_root() -> str:
    return os.environ.get("DRYAS_DATA_ROOT") or os.path.join(os.path.expanduser("~"), ".dryas")


def jev_dir() -> str:
    return os.path.join(data_root(), "jev")


def _env_or(var: str, default: str) -> str:
    return os.environ.get(var) or default


def log_dir() -> str:
    return _env_or("JEV_LOG_DIR", os.path.join(jev_dir(), "logs"))


def thresholds_file() -> str:
    return _env_or("JEV_THRESHOLDS", os.path.join(jev_dir(), "thresholds.json"))


def handoff_dir() -> str:
    return _env_or("JEV_HANDOFF_DIR", os.path.join(jev_dir(), "handoff"))


def compact_dir() -> str:
    return _env_or("JEV_COMPACT_DIR", os.path.join(jev_dir(), "compact"))


def chain_local() -> str:
    return _env_or("JEV_CHAIN_LOCAL", os.path.join(data_root(), "chain.local.json"))


def accounts_file() -> str:
    return os.path.join(data_root(), "accounts.json")


def ruflo_dir() -> str:
    return os.path.join(data_root(), "ruflo")


def projects_dir() -> str:
    """Transcripts of the account this hook runs for."""
    if os.environ.get("JEV_PROJECTS_DIR"):
        return os.environ["JEV_PROJECTS_DIR"]
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    return os.path.join(cfg, "projects") if cfg else os.path.join(os.path.expanduser("~"), ".claude", "projects")


def plugin_root() -> str:
    return os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)


def python() -> str:
    return os.environ.get("DRYAS_PY") or sys.executable
```

- [ ] **Step 4: Point the modules at it**

In each module add `import paths` next to its other local imports (they already `sys.path.insert(0, <jev dir>)` or live in it; `jevlog.py` and `handoff_paths.py` have no path insert, so add `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` and `import sys` first). Then replace the bodies:

```python
# jevlog.py
def log_dir() -> str:
    return paths.log_dir()

# handoff_paths.py
def handoff_dir() -> str:
    return paths.handoff_dir()

# handoff.py
def projects_dir() -> str:
    return paths.projects_dir()

# compact_keep.py
def compact_dir() -> str:
    return paths.compact_dir()

# context_watch.py
def _state_dir() -> str:
    return os.path.join(paths.handoff_dir(), ".warned")
```

Also fix the `handoff.py` docstring line `Verified against ~/.claude/projects` → `Verified against <config dir>/projects`.

`thresholds.py` — layered read, user-only write:

```python
SHIPPED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thresholds.json")


def path() -> str:
    """The user's overrides (written by /tune). Shipped defaults live in SHIPPED, read-only."""
    return paths.thresholds_file()


def _read(p: str) -> Dict[str, Any]:
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_file() -> Dict[str, Any]:
    """Shipped defaults with the user's file on top, section by section."""
    out = {k: dict(v) for k, v in _read(SHIPPED).items() if isinstance(v, dict)}
    for section, values in _read(path()).items():
        if isinstance(values, dict):
            out.setdefault(section, {}).update(values)
    return out
```

In `set_value`, read and write only the user file, creating its folder:

```python
def set_value(dotted: str, value: Any) -> None:
    data = _read(path())
    keys = dotted.split(".")
    node = data
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value
    p = path()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p) or ".", prefix=".thresholds-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, p)
```

Update the module docstring: `Defaults here and in the shipped thresholds.json; user overrides in ~/.dryas/jev/thresholds.json (written by /tune after approval).`

- [ ] **Step 5: Run the whole Jev suite**

Run: `python -m pytest -q claude/jev/tests`
Expected: PASS. If `test_thresholds.py` tests set `JEV_THRESHOLDS` to a temp file and expect `set_value` to keep keys that only the shipped file has, update them to the layered rule (user file holds only user keys); keep every other assertion.

- [ ] **Step 6: Commit**

```bash
git add claude/jev/paths.py claude/jev/tests/test_paths.py claude/jev/{jevlog,handoff_paths,handoff,compact_keep,context_watch,thresholds}.py claude/jev/tests/test_thresholds.py
git commit -m "feat(jev): one state root (~/.dryas) through paths.py; transcripts follow CLAUDE_CONFIG_DIR"
```

---

### Task 3: Jev key from the plugin option [A3]

**Files:**
- Modify: `claude/jev/jev_client.py:53-55`
- Test: `claude/jev/tests/test_jev_client.py`

**Interfaces:**
- Produces: `jev_client.api_key() -> str` — `OPENROUTER_API_KEY`, else `CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY`, stripped; `""` when neither.

- [ ] **Step 1: Write the failing tests** (append to `test_jev_client.py`)

```python
class ApiKeyTest(unittest.TestCase):
    def test_shell_key_wins(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": " a ", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": "b"}):
            self.assertEqual(jev_client.api_key(), "a")

    def test_plugin_option_fallback(self):
        env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
        env["CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY"] = "b"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(jev_client.api_key(), "b")

    def test_none(self):
        env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY")}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(jev_client.api_key(), "")
```

(Add `from unittest import mock` and `import os` at the top if missing.)

- [ ] **Step 2: Run** `python -m pytest -q claude/jev/tests/test_jev_client.py` — Expected: FAIL, `AttributeError: ... no attribute 'api_key'`.

- [ ] **Step 3: Implement**

```python
def api_key() -> str:
    """Shell env first; the plugin's sensitive option (exported to hook processes) second. Never stored."""
    return (os.environ.get("OPENROUTER_API_KEY") or os.environ.get("CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY") or "").strip()
```

and at the old line 53: `key = api_key()`. Update the module docstring line 3: `The key comes from OPENROUTER_API_KEY or the plugin option CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY at call time and is never stored.`

- [ ] **Step 4: Run** `python -m pytest -q claude/jev/tests` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add claude/jev/jev_client.py claude/jev/tests/test_jev_client.py
git commit -m "feat(jev): read the OpenRouter key from the plugin option when the shell has none"
```

---

### Task 4: Chain defaults + `chain.local.json`, placeholders resolved at run time

**Files:**
- Modify: `claude/jev/chain.py:23-60,186-215`, `claude/jev/chain.json` (ruflo stage paths)
- Create: `claude/jev/tests/test_chain_local.py`

**Interfaces:**
- Consumes: `paths.chain_local()`, `paths.plugin_root()`, `paths.python()`, `paths.data_root()` (Task 2).
- Produces:
  - `chain.local.json` format (written by `plugin_setup`, Task 8):
    ```json
    {"off": ["pstack-picks"], "stages": {"pretool": {"flowobserve": {"enabled": true}}, "prompt": {"jev-route": {"enabled": false, "timeout": 8}}}}
    ```
  - `chain.load_local() -> dict` (`{}` when missing; `{}` plus one stderr warning when unreadable).
  - `chain.apply_local(stages: list, event: str, local: dict) -> list` — copies of stages with only `enabled` / `timeout` overridden by name.
  - `chain.placeholders() -> Dict[str, str]` — `{"CD": plugin_root, "PY": python, "DRYAS_DATA_ROOT": data_root}` with forward slashes.
  - `_expand(s)` resolves `$CD`, `$PY`, `$DRYAS_DATA_ROOT` (bare or braced) before `expandvars`.

- [ ] **Step 1: Write the failing tests**

```python
# claude/jev/tests/test_chain_local.py
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chain

STAGES = [{"name": "scope-lock", "cmd": ["$PY", "$CD/jev/scope_lock.py"], "timeout": 3},
          {"name": "flowobserve", "enabled": False, "cmd": ["$PY", "$HOME/x.py"], "timeout": 1}]


class ApplyLocalTest(unittest.TestCase):
    def test_overrides_only_enabled_and_timeout_by_name(self):
        local = {"stages": {"pretool": {"flowobserve": {"enabled": True, "timeout": 9, "cmd": ["evil"]},
                                        "scope-lock": {"match": ".*"}}}}
        out = chain.apply_local(STAGES, "pretool", local)
        self.assertEqual(out[1]["enabled"], True)
        self.assertEqual(out[1]["timeout"], 9)
        self.assertEqual(out[1]["cmd"], ["$PY", "$HOME/x.py"])
        self.assertNotIn("match", out[0])
        self.assertFalse(STAGES[1]["enabled"])  # inputs untouched

    def test_bad_types_ignored(self):
        local = {"stages": {"pretool": {"flowobserve": {"enabled": "yes", "timeout": -1}}}}
        out = chain.apply_local(STAGES, "pretool", local)
        self.assertEqual((out[1]["enabled"], out[1]["timeout"]), (False, 1))

    def test_other_event_untouched(self):
        local = {"stages": {"prompt": {"flowobserve": {"enabled": True}}}}
        self.assertFalse(chain.apply_local(STAGES, "pretool", local)[1]["enabled"])


class LoadLocalTest(unittest.TestCase):
    def test_missing_is_empty_and_silent(self):
        with mock.patch.dict(os.environ, {"JEV_CHAIN_LOCAL": os.path.join(tempfile.mkdtemp(), "none.json")}), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(chain.load_local(), {})
            self.assertEqual(err.getvalue(), "")

    def test_broken_warns_once_and_falls_back(self):
        p = os.path.join(tempfile.mkdtemp(), "chain.local.json")
        with open(p, "w") as f:
            f.write("{nope")
        with mock.patch.dict(os.environ, {"JEV_CHAIN_LOCAL": p}), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(chain.load_local(), {})
            self.assertEqual(err.getvalue().count("\n"), 1)
            self.assertIn("chain.local.json", err.getvalue())


class PlaceholderTest(unittest.TestCase):
    def test_cd_py_data_root_resolved(self):
        env = {"CLAUDE_PLUGIN_ROOT": "/plug", "DRYAS_PY": "/py", "DRYAS_DATA_ROOT": "/data"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(chain._expand("$CD/jev/x.py"), "/plug/jev/x.py")
            self.assertEqual(chain._expand("${PY}"), "/py")
            self.assertEqual(chain._expand("$DRYAS_DATA_ROOT/ruflo/helpers/h.cjs"), "/data/ruflo/helpers/h.cjs")

    def test_unresolved_is_none(self):
        self.assertIsNone(chain._expand("$NOT_A_VAR_XYZ/x"))

    def test_unresolved_stage_skipped_and_logged(self):
        logs = tempfile.mkdtemp()
        st = {"name": "weird", "cmd": ["$NOT_A_VAR_XYZ/x"], "timeout": 1}
        with mock.patch.dict(os.environ, {"JEV_LOG_DIR": logs}):
            self.assertEqual(chain._run(st, "{}"), (None, "", ""))
        with open(os.path.join(logs, "chain.jsonl"), encoding="utf-8") as f:
            rec = json.loads(f.readline())
        self.assertEqual((rec["stage"], rec["skipped"]), ("weird", "unresolved placeholder"))


class LoadStagesMergesLocalTest(unittest.TestCase):
    def test_load_stages_applies_local(self):
        d = tempfile.mkdtemp()
        cfg, loc = os.path.join(d, "chain.json"), os.path.join(d, "chain.local.json")
        with open(cfg, "w") as f:
            json.dump({"pretool": STAGES}, f)
        with open(loc, "w") as f:
            json.dump({"stages": {"pretool": {"flowobserve": {"enabled": True}}}}, f)
        with mock.patch.dict(os.environ, {"JEV_CHAIN_CONFIG": cfg, "JEV_CHAIN_LOCAL": loc}):
            self.assertTrue(chain.load_stages("pretool")[1]["enabled"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m pytest -q claude/jev/tests/test_chain_local.py` — Expected: FAIL, `AttributeError: module 'chain' has no attribute 'apply_local'`.

- [ ] **Step 3: Implement in `chain.py`**

Add `import paths` after `import jevlog`. Replace `load_stages` and `_expand`, and add the helpers:

```python
_PH = re.compile(r"\$(?:\{(CD|PY|DRYAS_DATA_ROOT)\}|(CD|PY|DRYAS_DATA_ROOT)(?![A-Za-z0-9_]))")


def placeholders() -> Dict[str, str]:
    fwd = lambda p: p.replace("\\", "/")
    return {"CD": fwd(paths.plugin_root()), "PY": fwd(paths.python()), "DRYAS_DATA_ROOT": fwd(paths.data_root())}


def load_local() -> Dict[str, Any]:
    p = paths.chain_local()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            v = json.load(f)
        if not isinstance(v, dict):
            raise ValueError("not an object")
        return v
    except (OSError, ValueError) as e:
        sys.stderr.write("dryas: ignoring %s (%s); using chain defaults\n" % (p, str(e).splitlines()[0][:80]))
        return {}


def apply_local(stages: List[Dict[str, Any]], event: str, local: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Copies of stages with the user's enabled/timeout applied by stage name. Nothing else can be overridden."""
    over = ((local.get("stages") or {}).get(event) or {}) if isinstance(local, dict) else {}
    out = []
    for st in stages:
        st = dict(st)
        o = over.get(st.get("name")) if isinstance(over, dict) else None
        if isinstance(o, dict):
            if isinstance(o.get("enabled"), bool):
                st["enabled"] = o["enabled"]
            t = o.get("timeout")
            if isinstance(t, (int, float)) and not isinstance(t, bool) and 0 < t <= 120:
                st["timeout"] = t
        out.append(st)
    return out


def load_stages(kind: str, harness: str = "claude") -> List[Dict[str, Any]]:
    try:
        with open(config_path(), encoding="utf-8") as f:
            stages = list(json.load(f).get(kind, []))
    except (OSError, ValueError):
        return []
    stages = apply_local([s for s in stages if isinstance(s, dict)], kind, load_local())
    return [s for s in stages if harness in s.get("harness", ["claude"])]


def _expand(s: str) -> Optional[str]:
    ph = placeholders()
    s = _PH.sub(lambda m: ph[m.group(1) or m.group(2)], s)
    out = os.path.expanduser(os.path.expandvars(s))
    return None if "$" in out else out
```

In `_run`, log the skip:

```python
    cmd = [_expand(c) for c in raw_cmd]
    if any(c is None for c in cmd):
        jevlog.append("chain", {"stage": str(stage.get("name", "?")), "skipped": "unresolved placeholder"})
        return None, "", ""
```

Note: `$HOME` in the flowobserve stage still resolves through `expandvars`. Codex's copy install renders `chain.json` with absolute paths at install time (Task 9), so it never reaches the placeholder code.

- [ ] **Step 4: Ruflo stage helper path [A4]** — in `claude/jev/chain.json`, the `ruflo-pre-bash` stage: change `"$CD/ruflo/helpers/hook-handler.cjs"` to `"$DRYAS_DATA_ROOT/ruflo/helpers/hook-handler.cjs"`. Keep `"$CD/ruflo/run.py"` (run.py ships in the plugin).

- [ ] **Step 5: Run** `python -m pytest -q claude/jev/tests install/tests/test_dryas_install.py` — Expected: PASS. `render.chain_bytes` already maps `DRYAS_DATA_ROOT`, so the Codex copy render keeps working.

- [ ] **Step 6: Commit**

```bash
git add claude/jev/chain.py claude/jev/chain.json claude/jev/tests/test_chain_local.py
git commit -m "feat(chain): read-only defaults plus chain.local.json; resolve \$CD/\$PY at run time"
```

---

### Task 5: Rules hook and plugin packaging

**Files:**
- Create: `claude/jev/gating.py`, `claude/jev/rules_inject.py`, `claude/jev/tests/test_rules_inject.py`
- Create: `claude/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `claude/hooks/hooks.json`, `claude/.mcp.json`
- Create: `install/tests/test_plugin_shape.py`
- Modify: `install/render.py:1-30` (import `gate_blocks` from `gating`)

**Interfaces:**
- Produces: `gating.GATED`, `gating.gate_blocks(text, comps) -> str` (same behavior as today's `render.gate_blocks`; `render.py` re-exports both names).
- Produces: `rules_inject.build(template: str, off: List[str]) -> str` — `gate_blocks(template, ALL - off)`, plus `SKIP_LINE` when `pstack-picks` is off.
- Produces: `rules_inject.ALL = ("core", "jev", "ruflo", "superpowers", "design", "pstack-picks")`.
- Produces: `PLUGIN_NAME = "dryas"`, `MARKETPLACE = "dryas-workflow"` (repeated as literals in Task 8).

- [ ] **Step 1: Write the failing tests**

```python
# claude/jev/tests/test_rules_inject.py
import io
import itertools
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import rules_inject

TEMPLATE = os.path.join(os.path.dirname(HERE), "CLAUDE.md.template")


class RulesInjectTest(unittest.TestCase):
    def text(self):
        with open(TEMPLATE, encoding="utf-8") as f:
            return f.read()

    def test_all_on_keeps_pstack_block_without_markers(self):
        out = rules_inject.build(self.text(), [])
        self.assertNotIn("<!-- pstack-picks -->", out)
        self.assertNotIn(rules_inject.SKIP_LINE, out)
        self.assertIn("pstack", out)

    def test_pstack_off_drops_block_and_adds_skip_line(self):
        out = rules_inject.build(self.text(), ["pstack-picks"])
        self.assertNotIn("<!-- pstack-picks -->", out)
        self.assertIn(rules_inject.SKIP_LINE, out)

    def test_under_cap_for_every_combination(self):
        opt = ["jev", "ruflo", "superpowers", "design", "pstack-picks"]
        for n in range(len(opt) + 1):
            for off in itertools.combinations(opt, n):
                self.assertLess(len(rules_inject.build(self.text(), list(off))), 10000, off)

    def test_main_emits_sessionstart_json(self):
        d = tempfile.mkdtemp()
        loc = os.path.join(d, "chain.local.json")
        with open(loc, "w") as f:
            json.dump({"off": ["pstack-picks"]}, f)
        with mock.patch.dict(os.environ, {"JEV_CHAIN_LOCAL": loc}), \
                mock.patch("sys.stdin", io.StringIO('{"source":"startup"}')), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            rules_inject.main()
        hso = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "SessionStart")
        self.assertIn(rules_inject.SKIP_LINE, hso["additionalContext"])

    def test_main_silent_when_template_missing(self):
        with mock.patch.object(rules_inject, "TEMPLATE", "/no/such/file"), \
                mock.patch("sys.stdin", io.StringIO("{}")), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            rules_inject.main()
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
```

```python
# install/tests/test_plugin_shape.py
"""The plugin and marketplace manifests, hooks and MCP config are well formed and point at shipped files."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "claude"
BANNED_PREFIX = ("claude-", "anthropic-", "cc-plugin-")
ROOT_REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"'\s]+)")


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


class PluginShapeTest(unittest.TestCase):
    def test_marketplace(self):
        m = load(ROOT / ".claude-plugin" / "marketplace.json")
        self.assertEqual(m["name"], "dryas-workflow")
        self.assertIn("owner", m)
        self.assertEqual([p["name"] for p in m["plugins"]], ["dryas"])
        self.assertEqual(m["plugins"][0]["source"], "./claude")
        self.assertIn("claude-plugins-official", m["allowCrossMarketplaceDependenciesOn"])

    def test_plugin_manifest(self):
        p = load(PLUGIN / ".claude-plugin" / "plugin.json")
        self.assertEqual(p["name"], "dryas")
        self.assertFalse(p["name"].startswith(BANNED_PREFIX))
        self.assertRegex(p["version"], r"^\d+\.\d+\.\d+$")
        dep = [d for d in p["dependencies"] if d["name"] == "superpowers"][0]
        self.assertEqual(dep["marketplace"], "claude-plugins-official")
        tested = load(ROOT / "install" / "components.json")["superpowers"]["plugin_tested"]
        self.assertEqual(dep["version"], ">=" + tested)
        self.assertTrue(p["userConfig"]["openrouter_key"]["sensitive"])

    def test_hooks_point_at_shipped_files(self):
        h = load(PLUGIN / "hooks" / "hooks.json")["hooks"]
        cmds = [x["command"] for groups in h.values() for g in groups for x in g["hooks"]]
        self.assertTrue(cmds)
        for c in cmds:
            self.assertTrue(c.startswith('"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/'), c)
            for rel in ROOT_REF.findall(c):
                self.assertTrue((PLUGIN / rel).is_file(), rel)

    def test_hook_events(self):
        h = load(PLUGIN / "hooks" / "hooks.json")["hooks"]
        self.assertEqual(sorted(h), ["PreCompact", "PreToolUse", "SessionStart", "UserPromptSubmit"])
        ss = {g.get("matcher"): [x["command"] for x in g["hooks"]] for g in h["SessionStart"]}
        self.assertTrue(any("rules_inject.py" in c for c in ss["startup|resume|clear|compact"]))
        self.assertTrue(any("compact_restore.py" in c for c in ss["compact"]))
        self.assertTrue(any("handoff_restore.py" in c for c in ss["clear"]))

    def test_mcp(self):
        m = load(PLUGIN / ".mcp.json")["mcpServers"]["jev"]
        self.assertEqual(m["env"]["OPENROUTER_API_KEY"], "${user_config.openrouter_key}")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/jev/jev_mcp.py", m["args"])
        self.assertTrue((PLUGIN / "jev" / "jev_mcp.py").is_file())

    def test_markdown_has_no_install_tokens(self):
        """[A1] the plugin ships Markdown unrendered: no {{CD}}/{{PY}}, no ~/.claude/jev or ~/.claude/skills."""
        hits = []
        for f in sorted(PLUGIN.rglob("*.md")) + [PLUGIN / "CLAUDE.md.template"]:
            if "tests" in f.parts or f.name in ("NOTICE.md", "UPSTREAM.md"):
                continue
            t = f.read_text(encoding="utf-8")
            for bad in ("{{CD}}", "{{PY}}", "~/.claude/jev", "~/.claude/skills"):
                if bad in t:
                    hits.append("%s: %s" % (f.relative_to(ROOT), bad))
        self.assertEqual(hits, [])

    def test_launcher_is_executable_in_git(self):
        import subprocess
        out = subprocess.run(["git", "ls-files", "-s", "claude/bin/dryas-py"], cwd=str(ROOT),
                             capture_output=True, text=True).stdout
        self.assertTrue(out.startswith("100755"), out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m pytest -q claude/jev/tests/test_rules_inject.py install/tests/test_plugin_shape.py` — Expected: FAIL (`No module named 'rules_inject'`, missing manifests).

- [ ] **Step 3: Move `gate_blocks`**

Create `claude/jev/gating.py` with the exact `GATED`, `_MARK` and `gate_blocks` code now in `install/render.py` lines 8–31 (module docstring: `"""<!-- NAME --> ... <!-- /NAME --> blocks in shipped text, kept or dropped by selected components."""`, imports `re`, `typing.Iterable, Tuple`). In `install/render.py` delete those lines and add:

```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude" / "jev"))
from gating import GATED, gate_blocks  # noqa: E402,F401  (shared with the plugin's rules hook)
```

Run `python -m pytest -q install/tests` — Expected: PASS (behavior unchanged).

- [ ] **Step 4: Write `rules_inject.py`**

```python
#!/usr/bin/env python3
"""SessionStart hook (startup, resume, clear, compact): Dryas rules as additionalContext.
A plugin's CLAUDE.md is not loaded, so CLAUDE.md.template is injected here, with <!-- pstack-picks --> blocks
resolved from chain.local.json "off". Fails silent (no output) on any error."""
import json
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
from gating import gate_blocks  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CLAUDE.md.template")
ALL = ("core", "jev", "ruflo", "superpowers", "design", "pstack-picks")
SKIP_LINE = ("pstack-picks is not installed: in Dryas skills and agents, skip any text between "
             "<!-- pstack-picks --> and <!-- /pstack-picks -->.")


def build(template: str, off: List[str]) -> str:
    text = gate_blocks(template, [c for c in ALL if c not in off]).strip()
    return text + ("\n\n" + SKIP_LINE if "pstack-picks" in off else "") + "\n"


def _off() -> List[str]:
    try:
        with open(paths.chain_local(), encoding="utf-8") as f:
            off = json.load(f).get("off", [])
        return [str(x) for x in off] if isinstance(off, list) else []
    except (OSError, ValueError, AttributeError):
        return []


def main() -> None:
    try:
        sys.stdin.read()
        with open(TEMPLATE, encoding="utf-8") as f:
            ctx = build(f.read(), _off())
    except Exception:
        return
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
```

- [ ] **Step 5: Write the manifests**

`.claude-plugin/marketplace.json`:

```json
{
  "name": "dryas-workflow",
  "owner": {"name": "Promprit"},
  "allowCrossMarketplaceDependenciesOn": ["claude-plugins-official"],
  "plugins": [
    {"name": "dryas", "source": "./claude", "description": "Dryas Workflow for Claude Code: rules, scope lock, Jev chain, agents, commands and skills."}
  ]
}
```

`claude/.claude-plugin/plugin.json`:

```json
{
  "name": "dryas",
  "version": "1.0.0",
  "description": "Dryas Workflow for Claude Code: rules, scope lock, Jev chain, agents, commands and skills.",
  "dependencies": [{"name": "superpowers", "marketplace": "claude-plugins-official", "version": ">=6.4.2"}],
  "userConfig": {
    "openrouter_key": {"type": "string", "title": "OpenRouter API key", "description": "Used by Jev. Leave empty to use OPENROUTER_API_KEY from your shell.", "sensitive": true, "required": false}
  }
}
```

`claude/hooks/hooks.json` — the `core` hooks of today's `settings.fragment.json` with `"$PY"` → `"${DRYAS_PY:-python3}"` and `$CD` → `${CLAUDE_PLUGIN_ROOT}`, same timeouts, plus the rules entry:

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "*", "hooks": [{"type": "command", "command": "\"${DRYAS_PY:-python3}\" -X utf8 \"${CLAUDE_PLUGIN_ROOT}/jev/chain.py\" pretool", "timeout": 20}]}
    ],
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "\"${DRYAS_PY:-python3}\" -X utf8 \"${CLAUDE_PLUGIN_ROOT}/jev/chain.py\" prompt", "timeout": 15}]}
    ],
    "SessionStart": [
      {"matcher": "startup|resume|clear|compact", "hooks": [{"type": "command", "command": "\"${DRYAS_PY:-python3}\" -X utf8 \"${CLAUDE_PLUGIN_ROOT}/jev/rules_inject.py\"", "timeout": 5}]},
      {"matcher": "compact", "hooks": [{"type": "command", "command": "\"${DRYAS_PY:-python3}\" -X utf8 \"${CLAUDE_PLUGIN_ROOT}/jev/compact_restore.py\"", "timeout": 5}]},
      {"matcher": "clear", "hooks": [{"type": "command", "command": "\"${DRYAS_PY:-python3}\" -X utf8 \"${CLAUDE_PLUGIN_ROOT}/jev/handoff_restore.py\"", "timeout": 5}]}
    ],
    "PreCompact": [
      {"hooks": [{"type": "command", "command": "\"${DRYAS_PY:-python3}\" -X utf8 \"${CLAUDE_PLUGIN_ROOT}/jev/compact_keep.py\"", "timeout": 30}]}
    ]
  }
}
```

`claude/.mcp.json`:

```json
{
  "mcpServers": {
    "jev": {
      "command": "python3",
      "args": ["-X", "utf8", "${CLAUDE_PLUGIN_ROOT}/jev/jev_mcp.py"],
      "env": {"OPENROUTER_API_KEY": "${user_config.openrouter_key}"}
    }
  }
}
```

Note on `command`: MCP stdio servers are not run through a shell, so `${DRYAS_PY:-python3}` does not expand. `python3` is the documented default; Task 8's `setup` registers nothing extra for MCP. On Windows, where `python3` may be absent, `setup` verifies `python3 --version` and warns with the fix (`py -3` alias / install) — see Task 8 Step 3 `_mcp_python_warning`. Release check (Task 11) reports whether the jev MCP server connects.

- [ ] **Step 6: Run** `python -m pytest -q claude/jev/tests/test_rules_inject.py install/tests/test_plugin_shape.py` — Expected: PASS except `test_markdown_has_no_install_tokens` (fixed in Task 6). Also re-run `install/tests/test_hook_shell.py`.

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin claude/.claude-plugin claude/hooks claude/.mcp.json claude/jev/gating.py claude/jev/rules_inject.py claude/jev/tests/test_rules_inject.py install/render.py install/tests/test_plugin_shape.py
git commit -m "feat(plugin): manifests, hooks.json, Jev MCP and a SessionStart rules hook"
```

---

### Task 6: Plugin Markdown — no install-time tokens [A1]

**Files:**
- Modify: `claude/agents/executor.md`, `claude/commands/{handoff,tune,orchestrate}.md`, `claude/skills/{orchestrate,interrogate,benchmark-checklist}/SKILL.md`, `claude/CLAUDE.md.template`
- Modify: tests that assert rendered Markdown: `install/tests/{test_pstack_install,test_pstack_loop,test_pstack_review_fixes,test_shipped_files,test_dryas_install}.py`

**Interfaces:**
- Consumes: `claude/bin/dryas-py` (Task 1).
- Rewrite rules (apply everywhere under `claude/` except `pstack/NOTICE.md`, `pstack/UPSTREAM.md`, tests):
  - `"{{PY}}" -X utf8 "{{CD}}/` → `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/`
  - remaining `{{CD}}` → `${CLAUDE_PLUGIN_ROOT}`
  - `~/.claude/jev/thresholds.json` → `~/.dryas/jev/thresholds.json`
  - `~/.claude/jev/thresholds.py` → `${CLAUDE_PLUGIN_ROOT}/jev/thresholds.py`
  - `~/.claude/jev/logs` → `~/.dryas/jev/logs`; other `~/.claude/jev/<x>` → `${CLAUDE_PLUGIN_ROOT}/jev/<x>` for code, `~/.dryas/jev/<x>` for state
  - `~/.claude/skills/orchestrate/ruflo-tools.md` → `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/ruflo-tools.md`
  - `CLAUDE.md.template`: it is injected as context, not substituted, so use plain words: "the Dryas plugin folder" for code paths and `~/.dryas/...` for state.

- [ ] **Step 1: See the failing test** — `python -m pytest -q install/tests/test_plugin_shape.py::PluginShapeTest::test_markdown_has_no_install_tokens` — Expected: FAIL listing every hit.

- [ ] **Step 2: Rewrite** with the rules above. Use `grep -rn '{{\|~/\.claude' claude --include=*.md --include=*.template` until it lists only `NOTICE.md`/`UPSTREAM.md`. Example result for `claude/commands/handoff.md:8`:

```
"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/handoff.py" save --cwd "$PWD"
```

and `claude/commands/tune.md:4`:

```
1. Run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/tune.py" report`.
```

- [ ] **Step 3: Update Markdown assertions in installer tests.** Tests that render a skill/agent through `render.rendered` and assert `{{CD}}` became an absolute path now assert the file contains `${CLAUDE_PLUGIN_ROOT}/pstack/...` instead. Keep every gating assertion (`<!-- pstack-picks -->` blocks dropped when off) — `render.rendered` still gates Markdown for the Codex copy (Task 9). Fixture files under `install/tests/fixtures/pre_pstack/` are old releases: do not edit them.

- [ ] **Step 4: Run** `python -m pytest -q claude/jev/tests install/tests` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add claude install/tests
git commit -m "feat(plugin): Markdown uses \${CLAUDE_PLUGIN_ROOT} and the dryas-py launcher; state paths under ~/.dryas"
```

---

### Task 7: Ruflo runtime in the data root [A4] and the new settings fragment

**Files:**
- Create: `install/ruflo_runtime.py`, `install/tests/test_ruflo_runtime.py`
- Modify: `claude/settings.fragment.json`

**Interfaces:**
- Consumes: `ruflo_helpers.patched_helpers(ruflo_bin) -> Dict[str, Tuple[bytes, int]]`, `platform_util.make_dir_link(target, dest) -> str`, `platform_util.read_dir_link`, `platform_util.same_path`.
- Produces: `ruflo_runtime.install(repo: Path, root: Path, helpers: Dict[str, Tuple[bytes, int]], cli_dist: str) -> List[str]` — writes `<root>/ruflo/helpers/<name>` (only when content differs), copies `claude/ruflo/mcp-shim/bin/cli.js` to `<root>/ruflo/mcp-shim/bin/cli.js`, links `<root>/ruflo/mcp-shim/dist` → `cli_dist` (relinks when the target changed). Returns the list of paths written (empty on a no-op re-run).
- Produces: fragment placeholders used by Task 8's mapping: `$CD` (plugin installPath), `$CD_SAFE`, `$DATA_RULE` (`~/.dryas`, or `/` + the absolute root so the rule reads `Read(//abs/root/**)`), `$DRYAS_DATA_ROOT`, `$PY`, `$PY_SAFE`, Ruflo detect keys.

- [ ] **Step 1: Write the failing tests**

```python
# install/tests/test_ruflo_runtime.py
import json, os, shutil, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ruflo_runtime

REPO = HERE.parents[1]


class RufloRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.dist = Path(tempfile.mkdtemp())
        self.helpers = {"hook-handler.cjs": (b"// h\n", 0o755), "auto-memory-hook.mjs": (b"// a\n", 0o644)}

    def tearDown(self):
        shutil.rmtree(str(self.root), ignore_errors=True)
        shutil.rmtree(str(self.dist), ignore_errors=True)

    def test_first_install_writes_helpers_shim_and_link(self):
        wrote = ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist))
        r = self.root / "ruflo"
        self.assertEqual((r / "helpers" / "hook-handler.cjs").read_bytes(), b"// h\n")
        self.assertEqual((r / "mcp-shim" / "bin" / "cli.js").read_bytes(),
                         (REPO / "claude" / "ruflo" / "mcp-shim" / "bin" / "cli.js").read_bytes())
        self.assertTrue(os.path.isdir(str(r / "mcp-shim" / "dist")))
        self.assertEqual(len(wrote), 4)

    def test_second_run_is_noop(self):
        ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist))
        self.assertEqual(ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist)), [])

    def test_changed_helper_rewritten(self):
        ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist))
        self.helpers["hook-handler.cjs"] = (b"// h2\n", 0o755)
        wrote = ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist))
        self.assertEqual([Path(w).name for w in wrote], ["hook-handler.cjs"])

    def test_no_dist_skips_link(self):
        ruflo_runtime.install(REPO, self.root, self.helpers, "")
        self.assertFalse(os.path.lexists(str(self.root / "ruflo" / "mcp-shim" / "dist")))


class FragmentTest(unittest.TestCase):
    def test_core_has_no_hooks_and_new_rules(self):
        frag = json.loads((REPO / "claude" / "settings.fragment.json").read_text(encoding="utf-8"))
        self.assertNotIn("hooks", frag["core"])
        self.assertNotIn("hooks", frag.get("jev", {}))
        allow = frag["core"]["permissions"]["allow"]
        self.assertIn("Read($DATA_RULE/**)", allow)
        self.assertIn('Bash("$CD/bin/dryas-py" "$CD/jev/planfile.py":*)', allow)
        self.assertEqual(frag["core"]["env"]["DRYAS_PY"], "$PY")
        self.assertEqual(frag["core"]["env"]["DRYAS_DATA_ROOT"], "$DRYAS_DATA_ROOT")

    def test_ruflo_points_at_data_root(self):
        frag = json.loads((REPO / "claude" / "settings.fragment.json").read_text(encoding="utf-8"))["ruflo"]
        text = json.dumps(frag)
        self.assertNotIn("$CD/ruflo/helpers", text)
        self.assertNotIn("$CD/ruflo/mcp-shim", text)
        self.assertIn("$DRYAS_DATA_ROOT/ruflo/helpers/hook-handler.cjs", text)
        self.assertEqual(frag["env"]["RUFLO_MCP_CLI_OVERRIDE"], "$DRYAS_DATA_ROOT/ruflo/mcp-shim/bin/cli.js")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m pytest -q install/tests/test_ruflo_runtime.py` — Expected: FAIL (`No module named 'ruflo_runtime'`).

- [ ] **Step 3: Implement `install/ruflo_runtime.py`**

```python
"""Ruflo runtime in the shared data root (~/.dryas/ruflo): patched helpers and the MCP shim with its dist link.
Shared by every Claude config dir; rewritten only when content or the link target changed."""
import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

import platform_util as pu


def _write(dest: Path, data: bytes, mode: int, wrote: List[str]) -> None:
    if dest.is_file() and dest.read_bytes() == data:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    if os.name != "nt":
        os.chmod(str(dest), mode)  # portable-ok: guarded; keeps helper exec bit
    wrote.append(str(dest))


def install(repo: Path, root: Path, helpers: Dict[str, Tuple[bytes, int]], cli_dist: str) -> List[str]:
    base, wrote = Path(root) / "ruflo", []
    for name, (data, mode) in sorted(helpers.items()):
        _write(base / "helpers" / name, data, mode, wrote)
    src = Path(repo) / "claude" / "ruflo" / "mcp-shim" / "bin" / "cli.js"
    _write(base / "mcp-shim" / "bin" / "cli.js", src.read_bytes(), 0o755, wrote)
    link = base / "mcp-shim" / "dist"
    if cli_dist:
        cur = pu.read_dir_link(str(link))
        if cur is None or not pu.same_path(cur, cli_dist):
            if os.path.lexists(str(link)):
                pu.remove_path(str(link))
            pu.make_dir_link(cli_dist, str(link))
            wrote.append(str(link))
    return wrote
```

- [ ] **Step 4: Rewrite `claude/settings.fragment.json`**

- `core`: delete `hooks`. Set:
  ```json
  "env": {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "75", "DRYAS_PY": "$PY", "DRYAS_DATA_ROOT": "$DRYAS_DATA_ROOT"},
  "permissions": {"allow": [
    "Read($DATA_RULE/**)",
    "Bash(\"$CD/bin/dryas-py\" \"$CD/jev/planfile.py\":*)",
    "Bash(\"$CD/bin/dryas-py\" \"$CD/jev/handoff.py\" save:*)",
    "Bash(\"$CD/bin/dryas-py\" \"$CD/jev/tune.py\" report)"
  ]}
  ```
- `jev`: keep `permissions.allow` but change `"mcp__jev"` to `"mcp__plugin_dryas_jev"` (plugin MCP servers are named `plugin_<plugin>_<server>`). Grep `claude/` Markdown for `mcp__jev` and rename to `mcp__plugin_dryas_jev` in the same commit.
- `ruflo`: remove `DRYAS_DATA_ROOT` from its `env` (now in core). In every hook command replace `"$CD/ruflo/helpers/` with `"$DRYAS_DATA_ROOT/ruflo/helpers/`. Set `"RUFLO_MCP_CLI_OVERRIDE": "$DRYAS_DATA_ROOT/ruflo/mcp-shim/bin/cli.js"`. Keep `"RUFLO_HOOK_CLI_OVERRIDE": "$PY_SAFE -X utf8 $CD_SAFE/ruflo/run.py cli"` (run.py is in the plugin; `$CD` is the installPath, stable for the local marketplace).
- `superpowers`: unchanged.

- [ ] **Step 5: Run** `python -m pytest -q install/tests` — Expected: `test_ruflo_runtime.py` PASS. Old copy-install tests that render the fragment for the Claude harness now fail on `$DATA_RULE`; leave them failing until Task 9 replaces that path (note the failing names in the commit body).

  Codex check: `codex_target.servers` builds the ruflo MCP server from `mapping["CD"] + "/ruflo/mcp-shim/bin/cli.js"` — the Codex copy still ships `ruflo/mcp-shim` in `~/.claude`, so Codex is unchanged.

- [ ] **Step 6: Commit**

```bash
git add install/ruflo_runtime.py install/tests/test_ruflo_runtime.py claude/settings.fragment.json claude
git commit -m "feat(install): Ruflo helpers and MCP shim in ~/.dryas; fragment keeps only model, env, permissions"
```

---

### Task 8: `plugin_setup.py` — set up one config dir

**Files:**
- Create: `install/plugin_setup.py`, `install/tests/test_plugin_setup.py`
- Modify: `install/dryas_install.py:37-41` (`run` gains `env`), `install/run_cmd.py:73-110` (`thirdparty` takes `claude_dir`, `env`)
- Modify: `install/tests/test_run_cmd.py` (thirdparty calls)

**Interfaces:**
- Consumes: `dryas_install.run(argv, cwd=None, env=None) -> int`, `dryas_install.apply_settings(repo, cd, comps, rec, home, ts, mapping, dry, yes, comps_all) -> bool`, `dryas_install._mapping`, `dryas_install.detect`, `ruflo_helpers.patched_helpers`, `ruflo_runtime.install`, `run_cmd.thirdparty(comps, yes, claude_dir, env, table_path=None) -> int`.
- Produces:
  - `PLUGIN = "dryas"`, `MARKET = "dryas-workflow"`, `RECORD = ".dryas-plugin.json"`
  - `claude_dir(arg: Optional[str]) -> Path` — arg, else `$CLAUDE_CONFIG_DIR`, else `~/.claude`
  - `child_env(cd: Path) -> Dict[str, str]` — `os.environ` + `CLAUDE_CONFIG_DIR=<cd>`
  - `install_path(cd: Path) -> Optional[str]` — `installPath` of `dryas@dryas-workflow` in `<cd>/plugins/installed_plugins.json`
  - `write_chain_local(root: Path, comps: List[str], flowobserve: bool) -> None`
  - `add_account(root: Path, cd: Path) -> None`, `remove_account(root: Path, cd: Path) -> List[str]` (remaining)
  - `setup(repo: Path, cd: Path, comps: List[str], yes: bool, key: str, flowobserve: bool, dry: bool = False) -> int`
  - `uninstall(cd: Path, purge: bool) -> int` (Task 10 fills in)

- [ ] **Step 1: Write the failing tests**

```python
# install/tests/test_plugin_setup.py
import json, os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import fakecli
import plugin_setup as ps

REPO = HERE.parents[1]
INSTALLED = {"version": 2, "plugins": {"dryas@dryas-workflow": [{"scope": "user", "installPath": "", "version": "1.0.0"}]}}


class Env:
    """Temp HOME, data root, two config dirs and a fake `claude` that records CLAUDE_CONFIG_DIR."""

    def __init__(self, tc):
        self.t = Path(tempfile.mkdtemp())
        tc.addCleanup(shutil.rmtree, str(self.t), True)
        self.home, self.root = self.t / "home", self.t / "home" / ".dryas"
        self.a, self.b = self.t / "acct-a", self.t / "acct-b"
        self.log = self.t / "calls.jsonl"
        bin_dir = self.t / "bin"
        fakecli.make(bin_dir, "claude", self.log)
        # fake `claude plugin install` writes installed_plugins.json into $CLAUDE_CONFIG_DIR
        py = bin_dir / "claude_fake.py"
        py.write_text(py.read_text(encoding="utf-8") + (
            "import os\n"
            "if sys.argv[1:3] == ['plugin', 'install'] and os.environ.get('FAKE_NO_RECORD') != '1':\n"
            "    d = os.path.join(os.environ['CLAUDE_CONFIG_DIR'], 'plugins'); os.makedirs(d, exist_ok=True)\n"
            "    rec = %r\n"
            "    rec['plugins']['dryas@dryas-workflow'][0]['installPath'] = %r\n"
            "    open(os.path.join(d, 'installed_plugins.json'), 'w').write(json.dumps(rec))\n"
            "with open(%r, 'a') as f: f.write(json.dumps(os.environ.get('CLAUDE_CONFIG_DIR')) + '\\n')\n"
        ) % (INSTALLED, str(REPO / "claude"), str(self.t / "envs.jsonl")), encoding="utf-8")
        tc.enterContext(mock.patch.dict(os.environ, {
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "HOME": str(self.home),
            "USERPROFILE": str(self.home), "DRYAS_DATA_ROOT": str(self.root)}))
        self.home.mkdir()

    def calls(self):
        return fakecli.calls(self.log)

    def envs(self):
        p = self.t / "envs.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


COMPS = ["core", "jev"]


class SetupTest(unittest.TestCase):
    def test_claude_dir_resolution(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/cfg"}):
            self.assertEqual(ps.claude_dir(None), Path("/cfg"))
            self.assertEqual(ps.claude_dir("/x"), Path("/x"))
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(ps.claude_dir(None), Path.home() / ".claude")

    def test_two_accounts(self):
        e = Env(self)
        for cd in (e.a, e.b):
            self.assertEqual(ps.setup(REPO, cd, COMPS, yes=True, key="", flowobserve=False), 0)
        self.assertEqual(set(e.envs()), {str(e.a), str(e.b)})
        installs = [c for c in e.calls() if c[1:3] == ["plugin", "install"]]
        self.assertEqual([c[3] for c in installs], ["dryas@dryas-workflow"] * 2)
        self.assertTrue(all("-y" in c and "--scope" in c for c in installs))
        for cd in (e.a, e.b):
            s = json.loads((cd / "settings.json").read_text())
            self.assertEqual(s["env"]["DRYAS_DATA_ROOT"], str(e.root).replace("\\", "/"))
            self.assertIn("DRYAS_PY", s["env"])
            self.assertTrue(any("/jev/planfile.py" in r for r in s["permissions"]["allow"]))
            self.assertNotIn("hooks", s)
            self.assertTrue((cd / ps.RECORD).exists())
        self.assertEqual(json.loads((e.root / "accounts.json").read_text())["claude_dirs"], [str(e.a), str(e.b)])

    def test_key_passed_as_config(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="sk-1", flowobserve=False)
        inst = [c for c in e.calls() if c[1:3] == ["plugin", "install"]][0]
        self.assertIn("--config", inst)
        self.assertIn("openrouter_key=sk-1", inst)

    def test_verification_failure_stops_before_settings(self):
        e = Env(self)
        with mock.patch.dict(os.environ, {"FAKE_NO_RECORD": "1"}):
            self.assertEqual(ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False), 1)
        self.assertFalse((e.a / "settings.json").exists())
        self.assertFalse((e.root / "accounts.json").exists())

    def test_chain_local_components(self):
        e = Env(self)
        ps.setup(REPO, e.a, ["core", "jev"], yes=True, key="", flowobserve=True)
        loc = json.loads((e.root / "chain.local.json").read_text())
        self.assertEqual(sorted(loc["off"]), ["design", "pstack-picks", "ruflo", "superpowers"])
        self.assertTrue(loc["stages"]["pretool"]["flowobserve"]["enabled"])
        self.assertFalse(loc["stages"]["pretool"]["ruflo-pre-bash"]["enabled"])
        self.assertNotIn("jev-gate", loc["stages"]["pretool"])

    def test_second_run_is_noop(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        before = (e.a / "settings.json").read_text()
        self.assertEqual(ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False), 0)
        self.assertEqual((e.a / "settings.json").read_text(), before)
        self.assertEqual(json.loads((e.root / "accounts.json").read_text())["claude_dirs"], [str(e.a)])


if __name__ == "__main__":
    unittest.main()
```

(`enterContext` needs Python 3.11; on 3.9 use `p = mock.patch.dict(...); p.start(); tc.addCleanup(p.stop)` — write it that way.)

- [ ] **Step 2: Run** `python -m pytest -q install/tests/test_plugin_setup.py` — Expected: FAIL (`No module named 'plugin_setup'`).

- [ ] **Step 3: Implement**

`dryas_install.run`:

```python
def run(argv: List[str], cwd=None, env: Optional[dict] = None) -> int:
    try:
        return subprocess.call(pu.resolve_argv(argv), cwd=cwd, env=env)
    except OSError:
        return 127
```

`run_cmd.thirdparty` — signature `thirdparty(comps, yes, claude_dir: Path, env: Optional[dict] = None, table_path=None)`; run each argv with `di.run(argv, env=env)`; read `Path(claude_dir) / "plugins" / "installed_plugins.json"`. Skip `superpowers` commands (now a plugin dependency) but keep its version warning. Update `test_run_cmd.py` callers from `home=...` to `claude_dir=<home>/.claude`.

`install/plugin_setup.py`:

```python
"""Set up Dryas in one Claude config dir: install the plugin, merge model/env/permissions, shared state in ~/.dryas.

  setup(repo, cd, comps, ...)   one dir; run once per account (install.sh --claude-dir <dir>)
  uninstall(cd, purge)          that dir only; ~/.dryas stays unless purge and no other account is listed
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import dryas_install as di
import platform_util as pu
import ruflo_helpers
import ruflo_runtime
import run_cmd

PLUGIN, MARKET = "dryas", "dryas-workflow"
ID = PLUGIN + "@" + MARKET
RECORD = ".dryas-plugin.json"
OPTIONAL = ("jev", "ruflo", "superpowers", "design", "pstack-picks")


def claude_dir(arg: Optional[str]) -> Path:
    return Path(arg or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def data_root() -> Path:
    return Path(os.environ.get("DRYAS_DATA_ROOT") or Path.home() / ".dryas")


def child_env(cd: Path) -> Dict[str, str]:
    return dict(os.environ, CLAUDE_CONFIG_DIR=str(cd))


def install_path(cd: Path) -> Optional[str]:
    try:
        data = json.loads((Path(cd) / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        entries = data.get("plugins", {}).get(ID, [])
        paths = [e.get("installPath") for e in entries if isinstance(e, dict) and e.get("installPath")]
        return paths[0] if paths else None
    except (OSError, ValueError, AttributeError):
        return None


def _load_json(p: Path, default):
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v, type(default)) else default
    except (OSError, ValueError):
        return default


def _save_json(p: Path, v) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=2) + "\n", encoding="utf-8")


def write_chain_local(root: Path, comps: List[str], flowobserve: bool) -> None:
    """Unselected components: disabled stages and listed in "off". Keeps the user's own stage entries."""
    p = Path(root) / "chain.local.json"
    loc = _load_json(p, {})
    loc["off"] = sorted(c for c in OPTIONAL if c not in comps)
    chain = json.loads((Path(__file__).resolve().parents[1] / "claude" / "jev" / "chain.json").read_text(encoding="utf-8"))
    stages = loc.setdefault("stages", {})
    for event, sts in chain.items():
        for st in sts:
            comp, name = st.get("component"), st.get("name")
            if comp == "flowobserve":
                stages.setdefault(event, {}).setdefault(name, {})["enabled"] = bool(flowobserve)
            elif comp and comp != "core":
                ev = stages.setdefault(event, {})
                if comp in comps:
                    ev.get(name, {}).pop("enabled", None)
                    if name in ev and not ev[name]:
                        del ev[name]
                else:
                    ev.setdefault(name, {})["enabled"] = False
    _save_json(p, loc)


def add_account(root: Path, cd: Path) -> None:
    p = Path(root) / "accounts.json"
    acc = _load_json(p, {})
    dirs = [d for d in acc.get("claude_dirs", []) if isinstance(d, str)]
    if str(cd) not in dirs:
        dirs.append(str(cd))
    acc["claude_dirs"] = dirs
    _save_json(p, acc)


def remove_account(root: Path, cd: Path) -> List[str]:
    p = Path(root) / "accounts.json"
    acc = _load_json(p, {})
    dirs = [d for d in acc.get("claude_dirs", []) if isinstance(d, str) and d != str(cd)]
    if p.exists():
        acc["claude_dirs"] = dirs
        _save_json(p, acc)
    return dirs


def _mcp_python_warning() -> Optional[str]:
    if pu.which("python3"):
        return None
    return ("warning: the Jev MCP server starts with `python3`, which is not on your PATH. "
            "Install Python 3 so `python3` resolves (on Windows: enable the python3 alias or add it to PATH).")


def _mapping(cd: Path, plugin_root: str, comps: List[str]) -> Dict[str, str]:
    root = data_root()
    m = di._mapping(comps, Path.home(), Path(plugin_root))  # CD = the installed plugin, not the config dir
    default = pu.same_path(str(root), str(Path.home() / ".dryas"))
    m.update({"DRYAS_DATA_ROOT": pu.fwd(root), "DATA_RULE": "~/.dryas" if default else "/" + pu.fwd(root).lstrip("/")})
    return m


def setup(repo: Path, cd: Path, comps: List[str], yes: bool, key: str, flowobserve: bool, dry: bool = False) -> int:
    repo, cd, root = Path(repo).resolve(), Path(cd), data_root()
    env = child_env(cd)
    steps = [["claude", "plugin", "marketplace", "add", str(repo), "--scope", "user"],
             ["claude", "plugin", "install", ID, "--scope", "user", "-y"] + (["--config", "openrouter_key=" + key] if key else [])]
    for argv in steps:
        shown = [a if not a.startswith("openrouter_key=") else "openrouter_key=***" for a in argv]
        print("CLAUDE_CONFIG_DIR=%s %s" % (cd, " ".join(shown)))
        if dry:
            continue
        rc = di.run(argv, env=env)
        if rc != 0:
            print("error: `%s` failed (exit %d); %s not changed" % (" ".join(shown[:4]), rc, cd))
            return rc
    if dry:
        return 0
    plugin_root = install_path(cd)
    if not plugin_root:
        print("error: %s is not listed in %s; settings not changed" % (ID, cd / "plugins" / "installed_plugins.json"))
        return 1
    rc = run_cmd.thirdparty([c for c in comps if c in ("ruflo", "design", "superpowers")], yes, cd, env)
    if rc:
        return rc
    mapping = _mapping(cd, plugin_root, comps)
    if "ruflo" in comps:
        try:
            helpers = ruflo_helpers.patched_helpers(mapping.get("RUFLO_BIN", ""))
        except ruflo_helpers.HelperError as e:
            print("error: Ruflo helpers: %s" % getattr(e, "detail", e))
            return 1
        ruflo_runtime.install(repo, root, helpers, mapping.get("RUFLO_CLI_DIST", ""))
    rec_path = cd / RECORD
    rec = _load_json(rec_path, {}) or {"components": [], "settings_backup": None,
                                      "settings": {"env": {}, "allow": [], "deny": [], "hooks": [], "top": {}}}
    ok = di.apply_settings(repo, cd, comps, rec, Path.home(), mapping=mapping, yes=yes,
                           comps_all=sorted(set(rec.get("components", [])) | set(comps)))
    if not ok:
        return 1
    rec["components"] = sorted(set(comps))
    rec["plugin_root"] = plugin_root
    _save_json(rec_path, rec)
    write_chain_local(root, comps, flowobserve)
    add_account(root, cd)
    warn = _mcp_python_warning() if "jev" in comps else None
    if warn:
        print(warn)
    print("Dryas set up in %s (plugin at %s, state in %s)" % (cd, plugin_root, root))
    return 0


def uninstall(cd: Path, purge: bool) -> int:
    raise NotImplementedError  # Task 10
```

`apply_settings` reads `rec["settings"]`, writes `settings_backup` / `settings_created`; `RECORD` is separate from the copy installer's `.dryas-installed.json` so Task 9's migration can tell them apart. `apply_settings` renders the whole `comps` fragment through `mapping`; `superpowers` deny rules are included when selected.

- [ ] **Step 4: Run** `python -m pytest -q install/tests/test_plugin_setup.py install/tests/test_run_cmd.py` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add install/plugin_setup.py install/tests/test_plugin_setup.py install/dryas_install.py install/run_cmd.py install/tests/test_run_cmd.py
git commit -m "feat(install): plugin setup per Claude config dir with shared ~/.dryas state"
```

---

### Task 9: Migration, entry wiring and the Codex runtime copy [A2]

**Files:**
- Create: `install/migrate.py`, `install/tests/test_migrate.py`
- Modify: `install/run_cmd.py` (`parse`, `main`), `install/dryas_install.py` (`_plan_files` gains `runtime_only`; `install` passes it when `claude=False`), `install/install.sh`, `install/install.ps1` (usage lines)
- Modify: `install/tests/{test_e2e_install,test_dryas_install,test_pstack_install}.py`

**Interfaces:**
- Consumes: `plugin_setup.setup`, `dryas_install.uninstall(cd) -> int`, `dryas_install.load_record`, `dryas_install.RECORD`.
- Produces:
  - `migrate.is_copy_install(cd: Path) -> bool` — `.dryas-installed.json` exists and records Claude parts (`claude_md` true, or a recorded hook containing `/jev/chain.py`, or `"jev" in mcp`).
  - `migrate.move_state(cd: Path, root: Path) -> List[str]` — messages; moves `jev/logs/*`, `jev/thresholds.json`, `jev/handoff/*`, `jev/compact/*` into `<root>/jev/`.
  - `migrate.stage_settings(cd: Path) -> Dict[str, Dict[str, dict]]` — `{event: {name: {"enabled": bool}}}` from the old `jev/chain.json` for non-core stages.
  - `migrate.migrate(cd: Path, root: Path) -> int` — steps 1–3 of the spec (setup is step 4, run by the caller).
  - `_plan_files(repo, comps, runtime_only=False)`; `RUNTIME = ("jev/", "ruflo/", "pstack/")`.
  - CLI: `install.sh [--claude-dir DIR] [--flowobserve] [--openrouter-key KEY] ...` (key also from `OPENROUTER_API_KEY`).

Rules for old thresholds: the old file `<cd>/jev/thresholds.json` held the shipped defaults plus `/tune` edits. Keep only keys that differ from the shipped `claude/jev/thresholds.json` (so the new user file holds only real overrides). When the destination exists, keep the newer file by mtime and print `kept <path> (newer); ignored <other>`.

- [ ] **Step 1: Write the failing tests**

```python
# install/tests/test_migrate.py
import json, os, shutil, sys, tempfile, time, unittest
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import migrate

REPO = HERE.parents[1]


def old_install(cd: Path, log_line: str, tune_value: float, flowobserve_on: bool):
    (cd / "jev" / "logs").mkdir(parents=True)
    (cd / "jev" / "handoff").mkdir()
    (cd / "jev" / "logs" / "calls.jsonl").write_text(log_line + "\n", encoding="utf-8")
    (cd / "jev" / "handoff" / "proj-abc.md").write_text("h\n", encoding="utf-8")
    shipped = json.loads((REPO / "claude" / "jev" / "thresholds.json").read_text(encoding="utf-8"))
    shipped["gate"]["min_confidence"] = tune_value
    (cd / "jev" / "thresholds.json").write_text(json.dumps(shipped), encoding="utf-8")
    chain = json.loads((REPO / "claude" / "jev" / "chain.json").read_text(encoding="utf-8"))
    for st in chain["pretool"] + chain["prompt"]:
        if st["name"] == "flowobserve":
            st["enabled"] = flowobserve_on
    (cd / "jev" / "chain.json").write_text(json.dumps(chain), encoding="utf-8")
    (cd / ".dryas-installed.json").write_text(json.dumps({
        "components": ["core", "jev"], "files": {}, "dirs": [], "claude_md": True, "mcp": [],
        "settings": {"env": {}, "allow": [], "deny": [], "hooks": [["PreToolUse", "*", "x/jev/chain.py pretool"]], "top": {}},
        "settings_backup": None}), encoding="utf-8")


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.t), True)
        self.root = self.t / "dryas"
        self.a, self.b = self.t / "a", self.t / "b"
        p = mock.patch.object(migrate.di, "run", lambda argv, cwd=None, env=None: 0)
        p.start()
        self.addCleanup(p.stop)

    def test_detects_copy_install_only(self):
        self.a.mkdir()
        self.assertFalse(migrate.is_copy_install(self.a))
        old_install(self.a, '{"x":1}', 0.8, True)
        self.assertTrue(migrate.is_copy_install(self.a))
        # a Codex-only copy (no CLAUDE.md block, no chain hook, no jev MCP) is not a Claude install
        rec = json.loads((self.a / ".dryas-installed.json").read_text())
        rec.update(claude_md=False, settings={"env": {}, "allow": [], "deny": [], "hooks": [], "top": {}})
        (self.a / ".dryas-installed.json").write_text(json.dumps(rec))
        self.assertFalse(migrate.is_copy_install(self.a))

    def test_moves_state_and_keeps_only_real_overrides(self):
        old_install(self.a, '{"x":1}', 0.8, True)
        self.assertEqual(migrate.migrate(self.a, self.root), 0)
        self.assertEqual((self.root / "jev" / "logs" / "calls.jsonl").read_text(), '{"x":1}\n')
        self.assertTrue((self.root / "jev" / "handoff" / "proj-abc.md").exists())
        self.assertEqual(json.loads((self.root / "jev" / "thresholds.json").read_text()),
                         {"gate": {"min_confidence": 0.8}})
        self.assertFalse((self.a / ".dryas-installed.json").exists())  # old uninstall ran

    def test_stage_settings_carried(self):
        old_install(self.a, '{"x":1}', 0.8, True)
        migrate.migrate(self.a, self.root)
        loc = json.loads((self.root / "chain.local.json").read_text())
        self.assertTrue(loc["stages"]["pretool"]["flowobserve"]["enabled"])

    def test_second_account_appends_logs_and_keeps_newer_thresholds(self):
        old_install(self.a, '{"a":1}', 0.8, False)
        old_install(self.b, '{"b":2}', 0.9, False)
        migrate.migrate(self.a, self.root)
        os.utime(str(self.b / "jev" / "thresholds.json"), (time.time() + 60,) * 2)
        migrate.migrate(self.b, self.root)
        self.assertEqual((self.root / "jev" / "logs" / "calls.jsonl").read_text(), '{"a":1}\n{"b":2}\n')
        self.assertEqual(json.loads((self.root / "jev" / "thresholds.json").read_text())["gate"]["min_confidence"], 0.9)

    def test_second_run_noop(self):
        old_install(self.a, '{"x":1}', 0.8, True)
        migrate.migrate(self.a, self.root)
        before = (self.root / "jev" / "logs" / "calls.jsonl").read_text()
        self.assertFalse(migrate.is_copy_install(self.a))
        self.assertEqual(migrate.migrate(self.a, self.root), 0)
        self.assertEqual((self.root / "jev" / "logs" / "calls.jsonl").read_text(), before)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m pytest -q install/tests/test_migrate.py` — Expected: FAIL (`No module named 'migrate'`).

- [ ] **Step 3: Implement `install/migrate.py`**

```python
"""Copy install (files in <config dir>) -> plugin. Data moves before anything is removed; a second run is a no-op."""
import json
import os
import shutil
from pathlib import Path
from typing import Dict, List

import dryas_install as di

STATE_DIRS = ("logs", "handoff", "compact")
SHIPPED = Path(__file__).resolve().parents[1] / "claude" / "jev" / "thresholds.json"


def is_copy_install(cd: Path) -> bool:
    p = Path(cd) / di.RECORD
    if not p.exists():
        return False
    rec = di.load_record(Path(cd))
    hooks = rec.get("settings", {}).get("hooks", [])
    return bool(rec.get("claude_md")) or "jev" in rec.get("mcp", []) or \
        any("/jev/chain.py" in str(h[-1]).replace("\\", "/") for h in hooks if h)


def _merge_tree(src: Path, dst: Path, msgs: List[str]) -> None:
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        out = dst / f.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and f.suffix == ".jsonl":
            with open(str(out), "ab") as o:
                o.write(f.read_bytes())
            msgs.append("appended %s" % out)
        elif out.exists():
            msgs.append("kept %s (already present); ignored %s" % (out, f))
        else:
            shutil.copy2(str(f), str(out))


def _overrides(old: dict, shipped: dict) -> dict:
    out = {}
    for sec, vals in old.items():
        if isinstance(vals, dict):
            diff = {k: v for k, v in vals.items() if shipped.get(sec, {}).get(k) != v}
            if diff:
                out[sec] = diff
    return out


def move_state(cd: Path, root: Path) -> List[str]:
    src, dst, msgs = Path(cd) / "jev", Path(root) / "jev", []
    for d in STATE_DIRS:
        if (src / d).is_dir():
            _merge_tree(src / d, dst / d, msgs)
    old = src / "thresholds.json"
    if old.is_file():
        try:
            data = _overrides(json.loads(old.read_text(encoding="utf-8")), json.loads(SHIPPED.read_text(encoding="utf-8")))
        except ValueError:
            data = None
        new = dst / "thresholds.json"
        if data is None:
            msgs.append("ignored unreadable %s" % old)
        elif new.exists() and new.stat().st_mtime >= old.stat().st_mtime:
            msgs.append("kept %s (newer); ignored %s" % (new, old))
        elif data:
            new.parent.mkdir(parents=True, exist_ok=True)
            new.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            os.utime(str(new), (old.stat().st_mtime,) * 2)
            msgs.append("moved your /tune values to %s" % new)
    return msgs


def stage_settings(cd: Path) -> Dict[str, Dict[str, dict]]:
    try:
        old = json.loads((Path(cd) / "jev" / "chain.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: Dict[str, Dict[str, dict]] = {}
    for event, stages in old.items():
        for st in stages if isinstance(stages, list) else []:
            if isinstance(st, dict) and st.get("component") not in (None, "core") and isinstance(st.get("enabled", True), bool):
                out.setdefault(event, {})[st["name"]] = {"enabled": st.get("enabled", True)}
    return out


def migrate(cd: Path, root: Path) -> int:
    cd, root = Path(cd), Path(root)
    if not is_copy_install(cd):
        return 0
    print("Migrating the copy install in %s to the plugin" % cd)
    for m in move_state(cd, root):
        print("  " + m)
    stages = stage_settings(cd)
    if stages:
        p = root / "chain.local.json"
        loc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        for event, by_name in stages.items():
            for name, v in by_name.items():
                loc.setdefault("stages", {}).setdefault(event, {}).setdefault(name, {}).update(v)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(loc, indent=2) + "\n", encoding="utf-8")
    return di.uninstall(cd)
```

Note: `di.uninstall` also runs `claude mcp remove --scope user jev` without `CLAUDE_CONFIG_DIR`. Change that one call in `dryas_install.uninstall` to `run([...], env=dict(os.environ, CLAUDE_CONFIG_DIR=str(cd)))` so it removes the registration from the right account.

Order with `write_chain_local` (Task 8): migrate writes stage settings first; `setup` then applies the component choices on top (a component the user deselected now wins over the old file; `flowobserve` keeps the migrated value unless `--flowobserve` was given — change `write_chain_local` to only set flowobserve when `flowobserve` is True or the stage has no entry yet).

- [ ] **Step 4: Codex runtime-only copy** — in `dryas_install.py`:

```python
RUNTIME = ("jev/", "ruflo/", "pstack/")


def _plan_files(repo: Path, comps: List[str], runtime_only: bool = False):
    ...  # existing loop; after the COMPONENT_DIRS check add:
        if runtime_only and not rel.startswith(RUNTIME):
            continue
    ...  # and only yield docs/dryas-workflow.md when not runtime_only
```

Thread `runtime_only=not claude` through `copy_files` → `_plan_files` and `_remove_stale_files` (so a later Codex-only run removes the agents/commands/skills an old copy install left, via the existing stale-file logic). `install(..., claude=False)` is the only caller with `claude=False`.

- [ ] **Step 5: Wire `run_cmd.py`**

`parse` adds `--claude-dir`, `--flowobserve` (store_true), `--openrouter-key` (default `os.environ.get("OPENROUTER_API_KEY", "")`), `--purge` (store_true). `main` becomes:

```python
def main(argv: Optional[List[str]] = None) -> int:
    import codex_target as ct
    import dryas_install as di
    import migrate
    import plugin_setup as ps
    a = parse(list(sys.argv[1:] if argv is None else argv))
    repo, home = Path(a.repo).resolve(), Path.home()
    cd = ps.claude_dir(a.claude_dir)
    copy_cd = home / ".claude"  # Codex reads its runtime copy here (unchanged)
    comps = components(a)
    want_claude, want_codex = a.harness in ("claude", "both"), a.harness in ("codex", "both")
    if a.harness == "codex" and not a.uninstall and ("superpowers" in comps or "design" in comps):
        print("note: superpowers and design are Claude Code plugins; skipped for Codex.")
    if a.uninstall:
        rc = ct.uninstall_codex(ct.codex_dir(), home, di.run) if want_codex else 0
        rc = rc or (di.uninstall(copy_cd) if want_codex else 0)
        return rc or (ps.uninstall(cd, a.purge) if want_claude else 0)
    probs = preflight(comps, a.harness, cd)
    if probs:
        print("\n".join(probs))
        return 1
    if a.preflight_only:
        print("preflight ok")
        return 0
    if want_claude and not a.dry_run:
        rc = migrate.migrate(cd, ps.data_root())
        if rc:
            return rc
    if want_claude:
        rc = ps.setup(repo, cd, comps, yes=a.yes, key=a.openrouter_key, flowobserve=a.flowobserve, dry=a.dry_run)
        if rc:
            return rc
    if want_codex:
        rc = di.install(repo, copy_cd, comps, home=home, force=a.force, dry=a.dry_run, yes=a.yes, claude=False)
        if rc:
            return rc
        mapping = di.mapping_for(comps, home, copy_cd)
        renv = di.ruflo_env(repo, mapping) if "ruflo" in comps else {}
        rc = ct.install_codex(repo, ct.codex_dir(), home, comps, mapping, renv, di.run, force=a.force, dry=a.dry_run)
        if rc:
            return rc
    if a.dry_run:
        return 0
    fails = ps.verify(cd, comps) if want_claude else 0
    if want_codex:
        fails += ct.verify_codex(ct.codex_dir(), home, comps, di.capture, copy_cd)
    return 1 if fails else 0
```

Add `--uninstall` behavior note: `--harness claude --uninstall` touches only `cd`.

Preflight for Ruflo spaces now checks the data root, not the config dir: in `preflight`, replace `pu.space_free(claude_dir)` in the Ruflo branch with `pu.space_free(Path(os.environ.get("DRYAS_DATA_ROOT") or Path.home() / ".dryas"))`, and keep the Codex branch on `claude_dir` (pass `home / ".claude"` for it). The ruflo `RUFLO_HOOK_CLI_OVERRIDE` also uses `$CD_SAFE` (the plugin path), so check `pu.space_free(repo / "claude")` too.

Add `plugin_setup.verify(cd, comps) -> int` (PASS/FAIL lines like `di.verify`):
- `dryas@dryas-workflow listed in <cd>/plugins/installed_plugins.json`
- `rules hook prints SessionStart JSON` — run `[PY, "-X", "utf8", <installPath>/jev/rules_inject.py]` with `{}` on stdin; parse `hookSpecificOutput.additionalContext`.
- `scope lock blocks an out-of-scope write` — reuse the body of `di.verify`'s smoke test, running `<installPath>/jev/chain.py pretool` with `CLAUDE_PLUGIN_ROOT=<installPath>`, `DRYAS_PY=<PY>`, `JEV_CHAIN_LOCAL=<tmp>/none.json`, `JEV_LOG_DIR=<tmp>/logs`. Move that smoke body into a helper `di.scope_smoke(chain_py: Path, env_extra: dict) -> bool` and call it from both.
- Jev tests: same as `di.verify` but against `<installPath>/jev/tests`.

Update `install.sh` / `install.ps1` usage comments to list `--claude-dir DIR`, `--flowobserve`, `--openrouter-key KEY`, `--purge`.

- [ ] **Step 6: Update the e2e/installer tests**

`test_e2e_install.py`, `test_dryas_install.py`, `test_pstack_install.py`: tests that drive `run_cmd.main` with the Claude harness and assert copied files in `<home>/.claude` now assert the plugin path: fake `claude` records `plugin marketplace add` / `plugin install` with `CLAUDE_CONFIG_DIR`, `settings.json` has `DRYAS_PY` and no `hooks`, `~/.dryas/accounts.json` lists the dir. Tests that call `di.install(...)` directly with `claude=True` test the legacy copy path, which now only migration's uninstall needs: switch them to `claude=False` and assert runtime-only files (no `agents/`, `commands/`, `skills/`), or delete them only where a `test_migrate.py` / `test_plugin_setup.py` test covers the same behavior (list each deleted test name and its replacement in the commit body).

- [ ] **Step 7: Run** `python -m pytest -q claude/jev/tests install/tests claude/ruflo/tests && node claude/ruflo/tests/test_ns.cjs` — Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add install claude
git commit -m "feat(install): --claude-dir setup with migration from copy installs; Codex keeps a runtime-only copy"
```

---

### Task 10: Uninstall one account

**Files:**
- Modify: `install/plugin_setup.py` (`uninstall`)
- Test: `install/tests/test_plugin_setup.py` (add `UninstallTest`)

**Interfaces:**
- Consumes: `RECORD`, `remove_account`, `child_env`, `settings_merge.unmerge`, `settings_merge.load_settings`.
- Produces: `uninstall(cd: Path, purge: bool) -> int`.

- [ ] **Step 1: Write the failing tests** (append to `test_plugin_setup.py`)

```python
class UninstallTest(unittest.TestCase):
    def test_one_dir_removed_other_kept(self):
        e = Env(self)
        for cd in (e.a, e.b):
            ps.setup(REPO, cd, COMPS, yes=True, key="", flowobserve=False)
        self.assertEqual(ps.uninstall(e.a, purge=True), 0)
        un = [c for c in e.calls() if c[1:3] == ["plugin", "uninstall"]]
        self.assertEqual(len(un), 1)
        self.assertIn("--keep-data", un[0])
        self.assertEqual(e.envs()[-1], str(e.a))
        s = json.loads((e.a / "settings.json").read_text()) if (e.a / "settings.json").exists() else {}
        self.assertNotIn("DRYAS_PY", s.get("env", {}))
        self.assertIn("DRYAS_PY", json.loads((e.b / "settings.json").read_text())["env"])
        self.assertEqual(json.loads((e.root / "accounts.json").read_text())["claude_dirs"], [str(e.b)])
        self.assertTrue(e.root.exists())  # another account still listed: purge refused

    def test_purge_last_account(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        ps.uninstall(e.a, purge=True)
        self.assertFalse(e.root.exists())

    def test_keep_data_without_purge(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        ps.uninstall(e.a, purge=False)
        self.assertTrue((e.root / "chain.local.json").exists())

    def test_nothing_to_uninstall(self):
        e = Env(self)
        e.a.mkdir()
        self.assertEqual(ps.uninstall(e.a, purge=False), 0)
```

- [ ] **Step 2: Run** `python -m pytest -q install/tests/test_plugin_setup.py::UninstallTest` — Expected: FAIL (`NotImplementedError`).

- [ ] **Step 3: Implement**

```python
def uninstall(cd: Path, purge: bool) -> int:
    import settings_merge as sm
    cd, root = Path(cd), data_root()
    rec_path = cd / RECORD
    if not rec_path.exists():
        print("nothing to uninstall in %s" % cd)
        return 0
    rec = _load_json(rec_path, {})
    spath = cd / "settings.json"
    cur = sm.load_settings(spath)  # malformed settings.json aborts before anything is removed
    rc = di.run(["claude", "plugin", "uninstall", ID, "--scope", "user", "--keep-data"], env=child_env(cd))
    if rc != 0:
        print("warning: `claude plugin uninstall` failed (exit %d); remove %s by hand with /plugin" % (rc, ID))
    if spath.exists():
        new = sm.unmerge(cur, rec.get("settings", {}))
        if rec.get("settings_created") and new == {}:
            spath.unlink()
        elif new != cur:
            spath.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
    rec_path.unlink()
    left = remove_account(root, cd)
    if purge and not left and root.is_dir():
        shutil.rmtree(str(root))
        print("removed %s" % root)
    elif purge and left:
        print("kept %s: still used by %s" % (root, ", ".join(left)))
    print("uninstalled Dryas from %s" % cd)
    if rec.get("settings_backup"):
        print("settings backup from before the merge (manual fallback): %s" % rec["settings_backup"])
    return 0
```

Add `import shutil` at the top of `plugin_setup.py`. The marketplace entry is left registered (harmless; other accounts may share it).

- [ ] **Step 4: Run** `python -m pytest -q install/tests` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add install/plugin_setup.py install/tests/test_plugin_setup.py
git commit -m "feat(install): uninstall Dryas from one config dir; purge ~/.dryas only for the last account"
```

---

### Task 11: Release check, portability rule, docs

**Files:**
- Modify: `tools/release_check.py`, `install/tests/test_release_check.py`
- Modify: `install/tests/test_portability.py`, `CONTRIBUTING.md`
- Modify: `docs/install.md`, `docs/harnesses.md`, `README.md`, `reference/README.md`, `docs/release-check.md`, `docs/roadmap.md`, `docs/why-dryas.md` (the "Not a plugin" bullet)
- Modify: `docs/superpowers/specs/2026-10-12-plugin-packaging-design.md` (Status line + the [A1]–[A4] amendments)

**Interfaces:**
- Consumes: `plugin_setup.install_path(cd)`, `test_hook_shell.find_bash()` (copy the 8-line function into `release_check.py`; tools/ must not import tests).
- Produces: release check lines `PASS|FAIL|SKIP  plugin hooks run (<event>)` per `--claude-dir`, and `--claude-dir` repeatable (`action="append"`).

- [ ] **Step 1: Write the failing tests**

In `install/tests/test_release_check.py` add a test that builds a temp config dir whose `plugins/installed_plugins.json` points `dryas@dryas-workflow` at `<repo>/claude`, runs `release_check.main(["--claude-dir", <dir>, "--codex-dir", <empty tmp>])` with `JEV_LOG_DIR`/`DRYAS_DATA_ROOT` in a temp dir and `OPENROUTER_API_KEY` unset, captures stdout, and asserts lines `PASS  plugin hooks run (PreToolUse)`, `PASS  plugin hooks run (SessionStart)`. Add a second test: a dir with no `installed_plugins.json` prints `FAIL  dryas plugin installed`.

In `install/tests/test_portability.py` add:

```python
    def test_plugin_commands_use_plugin_placeholders(self):
        """Hook and MCP commands name the plugin root and DRYAS_PY, never installer placeholders."""
        import json
        hooks = json.loads((ROOT / "claude" / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        for groups in hooks.values():
            for g in groups:
                for h in g["hooks"]:
                    self.assertNotRegex(h["command"], r'"\$PY"|\$CD\b|\{\{')
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}/", h["command"])
                    self.assertIn("${DRYAS_PY:-python3}", h["command"])
        mcp = json.loads((ROOT / "claude" / ".mcp.json").read_text(encoding="utf-8"))
        for srv in mcp["mcpServers"].values():
            self.assertFalse(any("$CD" in a or "{{" in a for a in srv["args"]))
```

- [ ] **Step 2: Run** `python -m pytest -q install/tests/test_release_check.py install/tests/test_portability.py` — Expected: release check tests FAIL, portability PASS (already true from Task 5; it guards regressions).

- [ ] **Step 3: Implement the release check**

In `tools/release_check.py`: make `--claude-dir` `action="append"` (default `[str(Path.home() / ".claude")]` when none given). For each dir: read `installPath` the same way as `plugin_setup.install_path` (inline helper `_install_path(cd)`; `FAIL dryas plugin installed` when missing). With `bash = find_bash()` (SKIP when None), for each event in `SAMPLES` take the `hooks.json` commands of that event and run `[bash, "-c", cmd]` with `env = dict(os.environ, CLAUDE_PLUGIN_ROOT=fwd(installPath), DRYAS_PY=fwd(sys.executable), CLAUDE_CONFIG_DIR=str(cd))`, the sample as stdin, timeout = the hook timeout; PASS when exit code is 0 and stdout is empty or valid JSON. Keep the existing scope-lock and Jev-route checks, pointing their `chain` path at `<installPath>/jev/chain.py`. Point `ruflo()` at `<installPath>/ruflo/run.py` and additionally check `<data root>/ruflo/helpers/hook-handler.cjs` exists when Ruflo is set up. Add to `MANUAL`:
  `5. In each account's Claude Code, run /plugin and check dryas is enabled; if hooks did not fire, check for allowManagedHooksOnly in managed settings (docs/install.md).`
  `6. Run /tune and /handoff once in each account; both must run without a permission prompt.`

- [ ] **Step 4: Docs** (write each change; keep the repo's plain style)
  - `docs/install.md`: replace the Claude sections: plugin + setup; `install.sh --claude-dir <dir>` run once per account (example with two dirs); `--flowobserve`, `--openrouter-key` (stored by Claude Code in secure storage, else `OPENROUTER_API_KEY`); migration from a copy install (what moves, that data moves before removal, that a second run is a no-op); `--uninstall` (one dir) and `--purge`; Windows needs Git Bash for hooks and `python3` on PATH for the Jev MCP server; re-run setup after moving the clone or updating the plugin; `allowManagedHooksOnly` blocks plugin hooks.
  - `docs/harnesses.md`: new section "Several accounts (T3 Code, personal and team)": one `CLAUDE_CONFIG_DIR` per account, one `~/.dryas`, `accounts.json`, FlowObserve note (reads `~/.dryas/jev/logs`; transcript reader for other dirs is a FlowObserve follow-up).
  - `README.md`: install block shows `install/install.sh` then `install/install.sh --claude-dir ~/.claude-team`; "One source for the rules" bullet says the rules are injected by the plugin at session start.
  - `CONTRIBUTING.md`: portability rules: plugin hook commands use `"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/..."`; plugin Markdown uses `${CLAUDE_PLUGIN_ROOT}` and `bin/dryas-py`; `{{CD}}`/`$CD` stay for the settings fragment and Codex only; state paths only through `claude/jev/paths.py`.
  - `reference/README.md` conformance table: rules binding → SessionStart hook; hooks binding → plugin `hooks/hooks.json`; MCP binding → plugin `.mcp.json`; state → `~/.dryas`.
  - `docs/release-check.md`: the new per-dir lines and manual steps 5–6.
  - `docs/roadmap.md`: tick "Packaged plugins per harness" for Claude Code only (Codex still open): `- [ ] Packaged plugins per harness, generated from the manifest (Claude Code done: plugin dryas@dryas-workflow)`.
  - `docs/why-dryas.md`: change the "Not a plugin" bullet to say the Claude Code edition ships as a plugin, but Dryas is a spec with one binding per harness.
  - Spec: set `Status: approved; amended by the plan (A1–A4)` and add a short "Amendments" section copying [A1]–[A4] from this plan.

- [ ] **Step 5: Run the full suite and the public-docs tests**

Run: `python -m pytest -q claude/jev/tests install/tests claude/ruflo/tests && node claude/ruflo/tests/test_ns.cjs`
Expected: PASS (`test_public_docs.py` and `test_framework_docs.py` guard doc wording; fix wording they flag, never loosen them).

- [ ] **Step 6: Commit and push**

```bash
git add tools install/tests CONTRIBUTING.md docs README.md reference
git commit -m "docs(plugin): install per config dir, several accounts, release check per dir"
git push -u origin feat/plugin-packaging
```

Check CI on all six jobs. Then hand over the manual release check (needs a real Claude Code): two config dirs set up, `/plugin` shows dryas in both, a prompt shows the `Jev route:` line in both, an out-of-scope write is denied in both, `/tune` and `/handoff` run without prompts, `~/.dryas/jev/logs/calls.jsonl` grows from both.

---

## Self-review (done while writing)

- Spec coverage: layout/packaging (T5), rules hook (T5, T6), runtime/paths/state (T2), Python/Windows (T1, T5 MCP note), chain config (T4), `/handoff` follows the account (T2 `projects_dir`), permissions (T7, T8 mapping with installPath), setup steps 1–7 (T8, T9 preflight), migration (T9), uninstall (T10), FlowObserve (`$HOME` stage unchanged, logs via T2, `accounts.json` T8, docs T11), error handling (T4 unresolved skip, T8 stop before merge, T11 `allowManagedHooksOnly`), testing list (T1–T11), docs (T11). Out of scope items untouched.
- Placeholders: none left.
- Names: `paths.*`, `chain.apply_local/load_local/placeholders`, `rules_inject.build/SKIP_LINE/ALL`, `plugin_setup.{claude_dir,data_root,child_env,install_path,write_chain_local,add_account,remove_account,setup,uninstall,verify,RECORD,ID}`, `migrate.{is_copy_install,move_state,stage_settings,migrate}`, `ruflo_runtime.install`, `run_cmd.thirdparty(comps, yes, claude_dir, env)`, `di.run(argv, cwd, env)`, `di.scope_smoke(chain_py, env_extra)` — used consistently across tasks.
