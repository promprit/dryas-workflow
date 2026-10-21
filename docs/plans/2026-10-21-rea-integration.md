# REA integration — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract; Interfaces and Steps follow. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Dryas installs REA (`rea-agents@6.7.0`, reverse-engineering MCP + skill) as an optional extra per account, and brainstorm recommends it when a request depends on software we do not have the source for.
**Architecture:** A new stdlib module `install/rea_setup.py` owns every REA command (Node check, dry run, setup, doctor, removal). `run_cmd.py` selects it (`OPTIONAL`, `FRESH`, `--no-rea`/`--with-rea`); `plugin_setup.py` and `codex_plugin_setup.py` call it after the plugin third-party step and record `rec["rea"]`; uninstall reuses the existing extras flow. Rules: one template line, a brainstorm reference paragraph, one plan-skill line, docs.
**Tech Stack:** Python 3.9 stdlib, `unittest` run by `python3 -m pytest`, Markdown. External CLI: `npx -y rea-agents@6.7.0` (never called in tests).
**Spec:** `docs/specs/2026-10-21-rea-integration-design.md`

## Global Constraints

- Pinned package: `rea-agents@6.7.0`; constants `VERSION = "6.7.0"`, `PKG = "rea-agents@6.7.0"` live only in `install/rea_setup.py`.
- Node floor: major 22 needs >= 22.19, major 24 needs >= 24.11, 26 or later passes; 23, 25 and anything below 22 fail.
- REA output flag is `--format json` (never `--json`).
- REA never goes through `run_cmd.thirdparty` or `install/components.json`; `components.json` is unchanged.
- Nothing about REA is stored in `rec["thirdparty"]`; its record is `rec["rea"] = {"version": "6.7.0", "client": "claude_code"|"codex", "skill_dir": "<path>" | null}`.
- Never run `rea uninstall` (it acts on every client). No argv in code or tests may contain `["rea-agents@6.7.0", "uninstall"]` or start with `["rea", "uninstall"]`.
- Env for REA on a Claude dir is `plugin_setup.child_env(cd)` (it already unsets `CLAUDE_CONFIG_DIR` for the default `~/.claude`).
- A REA failure (Node, dry run, setup, doctor) is a warning; it never changes the installer's exit code.
- No hook, no chain stage: REA must not appear in `chain.local.json`'s `"off"` list.
- Tests never touch the network or a real account: stub `dryas_install.run`/`capture`/`confirm` and `shutil.which`.
- Python files stay under 500 lines when new; `plugin_setup.py` (832) and `codex_plugin_setup.py` (664) only get the minimal call sites.
- Test command for the suite: `python3 -m pytest -q install/tests` (from the worktree root).

## Review Focus

- The default account `~/.claude`: REA must run with `CLAUDE_CONFIG_DIR` unset, or it writes `~/.claude/.claude.json`, which Claude never reads. (Task 3 test `test_default_dir_unsets_config_dir`.)
- An account where REA was installed by hand before this change (this Mac's four accounts): `--with-rea` re-runs setup, which REA reports as `aligned`, and records it; nothing breaks on the existing registration. (Task 1 test `test_install_records_when_already_present`.)
- The dry-run JSON with no `install_skill` action, or garbage stdout (npm notices mixed in): `skill_dir` is `null` and uninstall then deletes nothing. (Task 1 tests `test_skill_dir_missing_action`, `test_skill_dir_garbage`.)
- A recorded `skill_dir` that is a symlink, a file, or a path whose last part is not `reverse-engineer-anything`: uninstall must not delete it. (Task 3 test `test_remove_skill_dir_refuses_unsafe`.)
- Running the installer without `--yes` and answering no: nothing from REA runs except the dry run, nothing is recorded, and the Dryas install still succeeds. (Task 1 test `test_install_declined`.)

---

## Task 1: `install/rea_setup.py` module

Goal: One stdlib module that checks Node, builds REA's argv, runs the dry run, setup and doctor, and returns the record entry or None, never raising.
Scope:
- install/rea_setup.py
- install/tests/test_rea_setup.py
Done:
- `python3 -m pytest -q install/tests/test_rea_setup.py` passes
- `python3 -m pytest -q install/tests` has no new failure
Failing test first: install/tests/test_rea_setup.py :: ReaSetupTest.test_node_versions

**Interfaces:**
- Consumes: `dryas_install.run(argv, env=None) -> int`, `dryas_install.capture(argv, input_text=None, env=None, timeout=None) -> (int, str)`, `dryas_install.confirm(prompt) -> bool` (prompt shows `[y/N]`).
- Produces (module `rea_setup`):
  - `VERSION = "6.7.0"`, `PKG = "rea-agents@6.7.0"`, `SKILL_NAME = "reverse-engineer-anything"`, `MIN_NODE = ((22, 19), (24, 11), (26, 0))`
  - `NODE_WARNING: str`
  - `node_ok(capture=None, which=None) -> Optional[str]` — `None` when fine, else `NODE_WARNING`
  - `setup_argv(client: str) -> List[str]`, `dry_run_argv(client: str) -> List[str]`, `doctor_argv(client: str) -> List[str]`
  - `skill_dir_from_plan(stdout: str) -> Optional[str]`
  - `skill_state(stdout: str) -> Optional[str]`
  - `install(client: str, env: dict, yes: bool, dry_run: bool) -> Optional[dict]`
  - `remove_argv(client: str) -> List[str]` — `["claude", "mcp", "remove", "--scope", "user", "rea"]` for `claude_code`, `["codex", "mcp", "remove", "rea"]` for `codex`
  - `safe_skill_dir(path: Optional[str]) -> bool`

- [ ] **Step 1: Write the failing tests.** Create `install/tests/test_rea_setup.py`:

```python
import json, os, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import dryas_install as di
import rea_setup as rs

PLAN = json.dumps({"status": "planned", "plannedActions": [
    {"kind": "configure_client", "target": "/h/.claude-x/.claude.json"},
    {"kind": "install_skill", "target": "/h/.claude-x/skills/reverse-engineer-anything"}]})
DOCTOR_OK = json.dumps({"identity": {"skill": {"state": "aligned"}, "registrations": []}})
DOCTOR_BAD = json.dumps({"identity": {"skill": {"state": "missing"}}})


class Fake:
    """Stands in for dryas_install: records argv and env, answers from a table keyed by REA subcommand."""
    def __init__(self, setup_rc=0, plan=PLAN, doctor=DOCTOR_OK, answer=True):
        self.calls, self.setup_rc, self.plan, self.doctor, self.answer = [], setup_rc, plan, doctor, answer
        self.asked = []

    def capture(self, argv, input_text=None, env=None, timeout=None):
        self.calls.append((list(argv), env))
        if "--dry-run" in argv:
            return 0, self.plan
        if "doctor" in argv:
            return 0, self.doctor
        return 1, ""

    def run(self, argv, cwd=None, env=None):
        self.calls.append((list(argv), env))
        return self.setup_rc

    def confirm(self, prompt):
        self.asked.append(prompt)
        return self.answer


class ReaSetupTest(unittest.TestCase):
    def setUp(self):
        self.orig = (di.run, di.capture, di.confirm, rs.node_ok)
        rs.node_ok = lambda *a, **k: None

    def tearDown(self):
        di.run, di.capture, di.confirm, rs.node_ok = self.orig

    def use(self, fake):
        di.run, di.capture, di.confirm = fake.run, fake.capture, fake.confirm
        return fake

    def test_node_versions(self):
        node_ok = self.orig[3]
        which = lambda n: "/bin/" + n
        for v, ok in (("v22.18.0", False), ("v22.19.0", True), ("v23.4.0", False), ("v24.10.9", False),
                      ("v24.11.0", True), ("v25.1.0", False), ("v26.0.0", True), ("v30.2.1", True),
                      ("v20.11.0", False), ("garbage", False)):
            got = node_ok(capture=lambda argv, **k: (0, v + "\n"), which=which)
            self.assertEqual(got is None, ok, v)
        self.assertEqual(node_ok(capture=lambda argv, **k: (0, "v24.14.1"), which=lambda n: ""), rs.NODE_WARNING)
        self.assertEqual(node_ok(capture=lambda argv, **k: (1, ""), which=which), rs.NODE_WARNING)

    def test_argv(self):
        self.assertEqual(rs.setup_argv("claude_code"),
                         ["npx", "-y", "rea-agents@6.7.0", "setup", "--client", "claude_code", "--yes", "--format", "json"])
        self.assertEqual(rs.dry_run_argv("codex"),
                         ["npx", "-y", "rea-agents@6.7.0", "setup", "--client", "codex", "--dry-run", "--format", "json"])
        self.assertEqual(rs.doctor_argv("claude_code"),
                         ["npx", "-y", "rea-agents@6.7.0", "doctor", "--client", "claude_code", "--skill", "--format", "json"])
        self.assertEqual(rs.remove_argv("claude_code"), ["claude", "mcp", "remove", "--scope", "user", "rea"])
        self.assertEqual(rs.remove_argv("codex"), ["codex", "mcp", "remove", "rea"])

    def test_skill_dir_from_plan(self):
        self.assertEqual(rs.skill_dir_from_plan(PLAN), "/h/.claude-x/skills/reverse-engineer-anything")

    def test_skill_dir_missing_action(self):
        self.assertIsNone(rs.skill_dir_from_plan(json.dumps({"status": "planned", "plannedActions": []})))

    def test_skill_dir_garbage(self):
        self.assertIsNone(rs.skill_dir_from_plan("npm notice New minor version\n"))
        self.assertIsNone(rs.skill_dir_from_plan(""))
        self.assertIsNone(rs.skill_dir_from_plan(json.dumps({"plannedActions": [{"kind": "install_skill"}]})))
        self.assertIsNone(rs.skill_dir_from_plan(json.dumps(["x"])))

    def test_skill_dir_after_npm_noise(self):
        self.assertEqual(rs.skill_dir_from_plan("npm warn deprecated x\n" + PLAN),
                         "/h/.claude-x/skills/reverse-engineer-anything")

    def test_skill_state(self):
        self.assertEqual(rs.skill_state(DOCTOR_OK), "aligned")
        self.assertEqual(rs.skill_state(DOCTOR_BAD), "missing")
        self.assertIsNone(rs.skill_state("x"))

    def test_install_yes(self):
        f = self.use(Fake())
        env = {"CLAUDE_CONFIG_DIR": "/h/.claude-x"}
        entry = rs.install("claude_code", env, yes=True, dry_run=False)
        self.assertEqual(entry, {"version": "6.7.0", "client": "claude_code",
                                 "skill_dir": "/h/.claude-x/skills/reverse-engineer-anything"})
        self.assertEqual(f.asked, [])
        argvs = [c[0] for c in f.calls]
        self.assertEqual(argvs, [rs.dry_run_argv("claude_code"), rs.setup_argv("claude_code"), rs.doctor_argv("claude_code")])
        self.assertTrue(all(c[1] is env for c in f.calls))

    def test_install_asks_after_dry_run(self):
        f = self.use(Fake())
        self.assertIsNotNone(rs.install("claude_code", {}, yes=False, dry_run=False))
        self.assertEqual(f.asked, ["Install REA?"])
        self.assertEqual(f.calls[0][0], rs.dry_run_argv("claude_code"))

    def test_install_declined(self):
        f = self.use(Fake(answer=False))
        self.assertIsNone(rs.install("claude_code", {}, yes=False, dry_run=False))
        self.assertEqual([c[0] for c in f.calls], [rs.dry_run_argv("claude_code")])

    def test_install_dry_run_runs_nothing(self):
        f = self.use(Fake())
        self.assertIsNone(rs.install("claude_code", {}, yes=True, dry_run=True))
        self.assertEqual(f.calls, [])

    def test_install_setup_fails(self):
        self.use(Fake(setup_rc=3))
        self.assertIsNone(rs.install("claude_code", {}, yes=True, dry_run=False))

    def test_install_node_missing(self):
        f = self.use(Fake())
        rs.node_ok = lambda *a, **k: rs.NODE_WARNING
        self.assertIsNone(rs.install("claude_code", {}, yes=True, dry_run=False))
        self.assertEqual(f.calls, [])

    def test_install_doctor_not_aligned_still_records(self):
        self.use(Fake(doctor=DOCTOR_BAD))
        entry = rs.install("claude_code", {}, yes=True, dry_run=False)
        self.assertEqual(entry["skill_dir"], "/h/.claude-x/skills/reverse-engineer-anything")

    def test_install_no_skill_in_plan(self):
        self.use(Fake(plan="not json"))
        self.assertEqual(rs.install("claude_code", {}, yes=True, dry_run=False)["skill_dir"], None)

    def test_install_records_when_already_present(self):
        # REA installed by hand earlier: its dry run plans an update, setup is idempotent and succeeds
        plan = json.dumps({"status": "planned", "plannedActions": [
            {"kind": "install_skill", "operation": "update", "target": "/h/.claude/skills/reverse-engineer-anything"}]})
        self.use(Fake(plan=plan))
        self.assertEqual(rs.install("claude_code", {}, yes=True, dry_run=False)["skill_dir"],
                         "/h/.claude/skills/reverse-engineer-anything")

    def test_safe_skill_dir(self):
        with tempfile.TemporaryDirectory() as t:
            good = Path(t) / "skills" / "reverse-engineer-anything"
            good.mkdir(parents=True)
            other = Path(t) / "skills" / "other"
            other.mkdir()
            link = Path(t) / "link" / "reverse-engineer-anything"
            link.parent.mkdir()
            os.symlink(str(good), str(link))
            afile = Path(t) / "f" / "reverse-engineer-anything"
            afile.parent.mkdir()
            afile.write_text("x")
            self.assertTrue(rs.safe_skill_dir(str(good)))
            for p in (str(other), str(link), str(afile), None, "", str(Path(t) / "missing" / "reverse-engineer-anything")):
                self.assertFalse(rs.safe_skill_dir(p), p)

    def test_never_uninstalls_globally(self):
        src = (HERE.parent / "rea_setup.py").read_text(encoding="utf-8")
        self.assertNotIn('"uninstall"', src)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_rea_setup.py`. Expected: `ModuleNotFoundError: No module named 'rea_setup'`.
- [ ] **Step 3: Implement.** Create `install/rea_setup.py`:

```python
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
```

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q install/tests/test_rea_setup.py && python3 -m pytest -q install/tests`. Expected: PASS (no new failures).
- [ ] **Step 5: Commit** `install/rea_setup.py install/tests/test_rea_setup.py`: `feat(install): rea_setup module for the REA extra (task 1)`.

## Task 2: Select `rea` (`--no-rea`, `--with-rea`, fresh default)

Goal: `rea` is an optional component, on for fresh installs, kept off on upgrades unless `--with-rea`, with one `WITH` tuple replacing the hard-coded `with_*` lists; the cloud edition never selects it.
Scope:
- install/run_cmd.py
- install/install.sh
- install/install.ps1
- install/tests/test_providers_install.py
- install/tests/test_run_cmd.py
- install/tests/test_rea_select.py
Done:
- `python3 -m pytest -q install/tests/test_rea_select.py install/tests/test_providers_install.py install/tests/test_run_cmd.py` passes
- `grep -n '("ruflo", "superpowers", "design")' install/run_cmd.py` prints nothing
- `python3 -m pytest -q install/tests` has no failure other than ones Task 3 owns (`test_plugin_setup.py` "off" list) — list any in the report
Failing test first: install/tests/test_rea_select.py :: ReaSelectTest.test_fresh_includes_rea

**Interfaces:**
- Consumes: `run_cmd.parse(argv)`, `run_cmd.select(a, recorded)`, `run_cmd.components(a)`.
- Produces: `run_cmd.OPTIONAL` ends with `"rea"`; `run_cmd.FRESH` includes `"rea"`; `run_cmd.WITH = ("ruflo", "superpowers", "design", "rea")`; `run_cmd.NO_STAGES = ("rea",)` (components with no chain stage; Task 3 uses it); `a.with_rea`, `a.no_rea`.

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_rea_select.py`:

```python
import sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "tools"))
import run_cmd


class ReaSelectTest(unittest.TestCase):
    def sel(self, argv, recorded=None):
        return run_cmd.select(run_cmd.parse(argv), recorded)

    def test_fresh_includes_rea(self):
        self.assertIn("rea", self.sel([]))

    def test_no_rea(self):
        self.assertNotIn("rea", self.sel(["--no-rea"]))

    def test_upgrade_without_record_keeps_it_off(self):
        self.assertNotIn("rea", self.sel([], ["core", "jev", "memory", "design"]))

    def test_with_rea_on_upgrade(self):
        self.assertIn("rea", self.sel(["--with-rea"], ["core", "jev", "memory"]))

    def test_upgrade_keeps_recorded(self):
        self.assertIn("rea", self.sel([], ["core", "jev", "memory", "rea"]))

    def test_with_and_no_contradict(self):
        with self.assertRaises(SystemExit):
            run_cmd.parse(["--with-rea", "--no-rea"])

    def test_constants(self):
        self.assertEqual(run_cmd.WITH, ("ruflo", "superpowers", "design", "rea"))
        self.assertEqual(run_cmd.NO_STAGES, ("rea",))
        self.assertIn("rea", run_cmd.OPTIONAL)

    def test_cloud_never_selects_rea(self):
        src = (HERE.parents[1] / "tools" / "dryas_cloud.py").read_text(encoding="utf-8")
        self.assertNotIn("--with-rea", src)
        self.assertNotIn('"rea"', src)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_rea_select.py`. Expected: `test_fresh_includes_rea` fails (`'rea' not found`), `test_constants` fails with `AttributeError: ... 'WITH'`.
- [ ] **Step 3: Implement.** In `install/run_cmd.py`:
  - `OPTIONAL = ("jev", "memory", "ruflo", "superpowers", "design", "pstack-picks", "rea")`
  - `FRESH = ("jev", "memory", "design", "pstack-picks", "rea")`
  - Add below `FRESH`: `WITH = ("ruflo", "superpowers", "design", "rea")  # --with-<c> flags` and `NO_STAGES = ("rea",)  # optional components with no chain stage (kept out of chain.local.json "off")`
  - Replace every literal `("ruflo", "superpowers", "design")` in the file with `WITH` (the `parse` loop adding `--with-*`, the contradiction loop, `select`, and the `no_flags` expression in `main`). Run `grep -n '"ruflo", "superpowers", "design"' install/run_cmd.py` until it prints nothing.
  - Update the usage docstring line 4 and `install/install.sh` line 3 / `install/install.ps1` line 2 usage comments: add `[--no-rea] [--with-rea]` after `[--no-design]`.
  - The Codex/OpenCode note in `main`: change the condition to also cover OpenCode REA: after the existing note add
    ```python
    if a.harness == "opencode" and not a.uninstall and "rea" in comps:
        print("note: REA is not set up for OpenCode; skipped.")
    ```
- [ ] **Step 4: Update the expected lists in existing tests.** In `install/tests/test_run_cmd.py::test_components` and `install/tests/test_providers_install.py` (fresh-default expectations at lines ~28 and ~32), append `"rea"` where the fresh defaults are listed, in the order `components()`/`select()` returns them (run the test once to read the actual order). `--no-design` and upgrade cases that pass a recorded list stay unchanged.
- [ ] **Step 5: Run the tests.** Run: `python3 -m pytest -q install/tests/test_rea_select.py install/tests/test_providers_install.py install/tests/test_run_cmd.py`. Expected: PASS. Then `python3 -m pytest -q install/tests` and report remaining failures by name.
- [ ] **Step 6: Commit** the Scope paths: `feat(install): rea component selection, --no-rea/--with-rea (task 2)`.

## Task 3: Wire REA into Claude setup and uninstall

Goal: `plugin_setup.setup` runs `rea_setup.install` for a selected `rea`, records `rec["rea"]` and `rea` in components only on success; uninstall offers `claude mcp remove --scope user rea` through the existing extras flow and deletes only a safe recorded skill folder; `rea` never enters chain.local.json's `"off"`.
Scope:
- install/plugin_setup.py
- install/tests/test_rea_wiring.py
- install/tests/test_plugin_setup.py
- install/tests/test_e2e_install.py
Done:
- `python3 -m pytest -q install/tests/test_rea_wiring.py install/tests/test_plugin_setup.py install/tests/test_install_uninstall.py` passes
- `python3 -m pytest -q install/tests` passes
Failing test first: install/tests/test_rea_wiring.py :: ReaWiringTest.test_extras_offer_mcp_remove

**Interfaces:**
- Consumes: `rea_setup.install(client, env, yes, dry_run) -> Optional[dict]`, `rea_setup.remove_argv("claude_code")`, `rea_setup.safe_skill_dir(path)`; `run_cmd.NO_STAGES`; existing `plugin_setup.extras_commands(rec, last_account)`, `plugin_setup._remove_extras(cd, rec, extras)`, `plugin_setup.child_env(cd)`, `plugin_setup.setup(repo, cd, comps, yes, ...)`.
- Produces: `plugin_setup.rea_step(cd, comps, rec, yes, dry) -> None` (mutates `rec`); `extras_commands` includes `rea_setup.remove_argv("claude_code")` when `rec.get("rea")` is a dict; `_remove_extras` removes `rec["rea"]["skill_dir"]` when that argv was run and `safe_skill_dir` is true, else prints the manual step.

- [ ] **Step 1: Write the failing tests.** Create `install/tests/test_rea_wiring.py`:

```python
import json, os, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import dryas_install as di
import plugin_setup as ps
import rea_setup as rs
import run_cmd

RM = ["claude", "mcp", "remove", "--scope", "user", "rea"]


class ReaWiringTest(unittest.TestCase):
    def setUp(self):
        self.orig = (rs.install, di.run)
        self.calls = []

    def tearDown(self):
        rs.install, di.run = self.orig

    def test_extras_offer_mcp_remove(self):
        self.assertIn(RM, ps.extras_commands({"rea": {"version": "6.7.0", "client": "claude_code", "skill_dir": None}}, False))
        self.assertNotIn(RM, ps.extras_commands({}, False))
        self.assertNotIn(RM, ps.extras_commands({"rea": "junk"}, False))

    def test_rea_step_records_on_success(self):
        rs.install = lambda client, env, yes, dry_run: self.calls.append((client, env, yes, dry_run)) or \
            {"version": "6.7.0", "client": client, "skill_dir": "/x/skills/reverse-engineer-anything"}
        rec = {"components": ["core"]}
        cd = Path(tempfile.mkdtemp())
        ps.rea_step(cd, ["core", "rea"], rec, yes=True, dry=False)
        self.assertEqual(rec["rea"]["skill_dir"], "/x/skills/reverse-engineer-anything")
        self.assertEqual(self.calls[0][0], "claude_code")
        self.assertEqual(self.calls[0][1], ps.child_env(cd))
        self.assertNotIn("thirdparty", rec)

    def test_rea_step_failure_drops_component(self):
        rs.install = lambda *a, **k: None
        rec = {}
        comps = ["core", "rea"]
        ps.rea_step(Path(tempfile.mkdtemp()), comps, rec, yes=True, dry=False)
        self.assertNotIn("rea", rec)
        self.assertNotIn("rea", comps)

    def test_rea_step_not_selected(self):
        rs.install = lambda *a, **k: self.fail("must not run")
        rec = {}
        ps.rea_step(Path(tempfile.mkdtemp()), ["core"], rec, yes=True, dry=False)
        self.assertEqual(rec, {})

    def test_default_dir_unsets_config_dir(self):
        saved = os.environ.get("CLAUDE_CONFIG_DIR")
        try:
            for value in (None, str(Path.home() / ".claude-other")):
                if value is None:
                    os.environ.pop("CLAUDE_CONFIG_DIR", None)
                else:
                    os.environ["CLAUDE_CONFIG_DIR"] = value
                self.assertNotIn("CLAUDE_CONFIG_DIR", ps.child_env(Path.home() / ".claude"), value)
            self.assertEqual(ps.child_env(Path.home() / ".claude-x")["CLAUDE_CONFIG_DIR"], str(Path.home() / ".claude-x"))
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = saved

    def test_remove_skill_dir(self):
        di.run = lambda argv, cwd=None, env=None: 0
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "skills" / "reverse-engineer-anything"
            d.mkdir(parents=True)
            ps._remove_extras(Path(t), {"rea": {"skill_dir": str(d)}}, [RM])
            self.assertFalse(d.exists())

    def test_remove_skill_dir_refuses_unsafe(self):
        di.run = lambda argv, cwd=None, env=None: 0
        with tempfile.TemporaryDirectory() as t:
            real = Path(t) / "real" / "reverse-engineer-anything"
            real.mkdir(parents=True)
            link = Path(t) / "skills" / "reverse-engineer-anything"
            link.parent.mkdir()
            os.symlink(str(real), str(link))
            other = Path(t) / "skills" / "keep-me"
            other.mkdir()
            for p in (str(link), str(other)):
                ps._remove_extras(Path(t), {"rea": {"skill_dir": p}}, [RM])
            self.assertTrue(real.exists() and other.exists() and os.path.islink(str(link)))

    def test_keep_extras_removes_nothing(self):
        di.run = lambda argv, cwd=None, env=None: self.fail("ran %s" % argv)
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "skills" / "reverse-engineer-anything"
            d.mkdir(parents=True)
            ps._remove_extras(Path(t), {"rea": {"skill_dir": str(d)}}, [])
            self.assertTrue(d.exists())

    def test_off_list_excludes_rea(self):
        self.assertIn("rea", run_cmd.NO_STAGES)
        src = (HERE.parent / "plugin_setup.py").read_text(encoding="utf-8")
        self.assertIn("NO_STAGES", src)

    def test_no_global_uninstall(self):
        for c in ps.extras_commands({"rea": {"skill_dir": None}}, True):
            self.assertNotEqual(c[:2], ["rea", "uninstall"])
            self.assertNotIn("rea-agents@6.7.0", c)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_rea_wiring.py`. Expected: `test_extras_offer_mcp_remove` fails (`RM` not in list); `rea_step` tests fail with `AttributeError: module 'plugin_setup' has no attribute 'rea_step'`.
- [ ] **Step 3: Implement** in `install/plugin_setup.py`:
  - Import at the top with the other install imports: `import rea_setup`.
  - Add next to `shown`:
    ```python
    def rea_step(cd: Path, comps: List[str], rec: dict, yes: bool, dry: bool) -> None:
        """REA (not a plugin, so not thirdparty): set up for cd when selected; on success record rec["rea"],
        else drop "rea" from comps so the record does not claim it."""
        if "rea" not in comps:
            return
        entry = rea_setup.install("claude_code", child_env(cd), yes, dry)
        if entry:
            rec["rea"] = entry
        elif not (dry and isinstance(rec.get("rea"), dict)):
            comps.remove("rea")
    ```
  - In `setup`, right after the `rc = run_cmd.thirdparty(...)` block and its `if rc:` return (before `mapping = _mapping(...)`), call `rea_step(cd, comps, rec, yes, dry)`. Make sure the `comps` list written to `rec["components"]` later is the same list object (or recomputed after this call), so a failed REA leaves `rea` out of the record. Read how `rec["components"]` is assigned in `setup` and keep it after `rea_step`.
  - `extras_commands`: after building `out` from `ran`, add
    ```python
    if isinstance(rec.get("rea"), dict):
        out.append(rea_setup.remove_argv("claude_code"))
    ```
  - `_remove_extras`: after the loop that runs `extras`, add
    ```python
    rea = rec.get("rea") if isinstance(rec.get("rea"), dict) else None
    if rea and rea_setup.remove_argv("claude_code") in extras:
        sd = rea.get("skill_dir")
        if rea_setup.safe_skill_dir(sd):
            shutil.rmtree(str(sd), onerror=_rm_error)
            print("removed %s" % sd)
        elif sd:
            print("kept %s (not a plain %s folder); remove it by hand" % (sd, rea_setup.SKILL_NAME))
        else:
            print("REA's skill folder was not recorded; remove <config dir>/skills/%s by hand" % rea_setup.SKILL_NAME)
    ```
    The existing `left = [c for c in extras_commands(rec, False) if c not in extras]` then already prints the REA removal command when `--keep-extras` left it.
  - Chain "off" list (line ~163): `loc["off"] = sorted(c for c in OPTIONAL if c not in comps and c not in run_cmd.NO_STAGES)`.
- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q install/tests/test_rea_wiring.py install/tests/test_plugin_setup.py install/tests/test_install_uninstall.py`. Expected: PASS (`test_chain_local_components` stays `["design", "pstack-picks", "ruflo", "superpowers"]` thanks to `NO_STAGES`). Then `python3 -m pytest -q install/tests`. Expected: PASS. In `install/tests/test_e2e_install.py` add `"--no-rea"` next to its existing `"--no-design"` (line ~51) so it never reaches the real `npx`. Then `grep -n "run_cmd.main\|ps.setup(" install/tests/*.py` and check each call: one that passes fresh defaults (no explicit component list) and is not stubbing `rea_setup.install` gets `--no-rea` (or a `rea_setup.install = lambda *a, **k: None` stub in its setUp); name each in the report.
- [ ] **Step 5: Commit** the Scope paths : `feat(install): set up and uninstall REA per Claude account (task 3)`.

## Task 4: Codex wiring

Goal: `--harness codex|both|all` sets up REA for the Codex home with `--client codex` and records it in the Codex record; Codex uninstall offers `codex mcp remove rea` and the safe skill folder.
Scope:
- install/codex_plugin_setup.py
- install/run_cmd.py
- install/tests/test_rea_codex.py
Done:
- `python3 -m pytest -q install/tests/test_rea_codex.py install/tests/test_codex_plugin_setup.py` passes
- `python3 -m pytest -q install/tests` passes
Failing test first: install/tests/test_rea_codex.py :: ReaCodexTest.test_setup_runs_codex_client

**Interfaces:**
- Consumes: `rea_setup.install("codex", env, yes, dry_run)`, `rea_setup.remove_argv("codex")`, `rea_setup.safe_skill_dir`; `codex_plugin_setup.setup(repo, cdx, comps, yes, dry=False) -> int`, `codex_plugin_setup.RECORD`.
- Produces: `codex_plugin_setup.codex_env(cdx) -> dict` (os.environ with `CODEX_HOME=str(cdx)`, if no such helper exists already; reuse an existing one if present); Codex record key `"rea"` with the same entry shape; `codex_plugin_setup.rea_extras(cdx) -> List[List[str]]` (`[rea_setup.remove_argv("codex")]` when the Codex record has a dict `"rea"`, else `[]`); `codex_plugin_setup.uninstall(cdx: Path, extras: Optional[List[List[str]]] = None) -> int` (new keyword, default keeps today's behaviour).

- [ ] **Step 1: Read first.** Read `install/codex_plugin_setup.py` `setup` (line ~424) and its uninstall function to find where the record is saved and where removal commands run. Run `codex mcp --help` if `codex` is on PATH and confirm `remove <name>` exists; if `codex` is not installed (as on the authoring Mac), keep `["codex", "mcp", "remove", "rea"]` and say so in the report.
- [ ] **Step 2: Write the failing test.** Create `install/tests/test_rea_codex.py` in the style of `install/tests/test_codex_plugin_setup.py` (copy its temp Codex home fixture). Tests:
  - `test_setup_runs_codex_client`: stub `rea_setup.install` to record `(client, env)` and return `{"version": "6.7.0", "client": "codex", "skill_dir": None}`; run the Codex setup path with `comps` containing `"rea"`; assert client `"codex"`, `env["CODEX_HOME"] == str(cdx)`, and the saved Codex record has `rec["rea"]["client"] == "codex"`.
  - `test_setup_failure_not_recorded`: stub returns `None`; record has no `"rea"` and its components exclude `"rea"`.
  - `test_uninstall_offers_codex_remove`: a Codex record with `"rea"` makes the uninstall's removal list contain `["codex", "mcp", "remove", "rea"]`, run with `CODEX_HOME` set; a safe skill folder is deleted, an unsafe one kept (same cases as Task 3).
- [ ] **Step 3: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_rea_codex.py`. Expected: the setup test fails (`rea_setup.install` never called).
- [ ] **Step 4: Implement.**
  - `codex_plugin_setup.setup`: first line `comps = list(comps)` (never mutate the caller's list). After its plugin step and before the record is saved: if `"rea"` in `comps`, `entry = rea_setup.install("codex", codex_env(cdx), yes, dry)`; on an entry set `rec["rea"] = entry`, else `comps.remove("rea")` before the components are recorded.
  - `run_cmd.main` setup path (line ~345): pass `list(codex_comps)` to `cps.setup`, so a Codex REA decline or failure cannot drop `rea` from the Claude run's `comps` under `--harness both|all`.
  - `run_cmd.main` uninstall path: after the `if want_claude:` extras block, add a Codex block:
    ```python
    cextras = cps.rea_extras(cdx) if want_codex else []
    if cextras and a.keep_extras:
        print("kept REA for Codex; to remove it: %s" % "; ".join("CODEX_HOME=%s %s" % (cdx, " ".join(c)) for c in cextras))
        cextras = []
    elif cextras:
        print("Third-party tools setup installed for %s (kept with --keep-extras):" % cdx)
        for argv in cextras:
            print("  CODEX_HOME=%s %s" % (cdx, " ".join(argv)))
        if not (a.yes or di.confirm("Remove them too?")):
            cextras = []
    ```
    and change the call to `cps.uninstall(cdx, extras=cextras)`.
  - `codex_plugin_setup.uninstall(cdx, extras=None)`: read the record before it is deleted; for each argv in `extras or []` run `di.run(argv, env=codex_env(cdx))` (non-zero exit: warning, go on); when `rea_setup.remove_argv("codex")` was among them, delete `rec["rea"]["skill_dir"]` only if `rea_setup.safe_skill_dir` is true, else print the manual step (same messages as Task 3's `_remove_extras`).
  - Add to `test_rea_codex.py`: `test_shared_comps_not_mutated` — call `cps.setup` with a list containing `"rea"` and `rea_setup.install` stubbed to return `None`; assert the caller's list still contains `"rea"`. `test_keep_extras_codex` — through `run_cmd.main(["--uninstall", "--harness", "codex", "--keep-extras", "--yes", "--codex-dir", str(cdx)])` (with the other side effects stubbed as `test_codex_plugin_setup.py` does), no `codex mcp remove` runs.
- [ ] **Step 5: Run the tests.** Run: `python3 -m pytest -q install/tests/test_rea_codex.py install/tests/test_codex_plugin_setup.py && python3 -m pytest -q install/tests`. Expected: PASS.
- [ ] **Step 6: Commit** the Scope paths: `feat(install): REA for Codex homes (task 4)`.

## Task 5: Release check

Goal: `tools/release_check.py` reports REA's state for each Claude dir whose record has `rea`: PASS when doctor says `aligned`, WARN otherwise, SKIP when not recorded; never a FAIL.
Scope:
- tools/release_check.py
- install/tests/test_release_check.py
Done:
- `python3 -m pytest -q install/tests/test_release_check.py` passes
- `python3 -m pytest -q install/tests` passes
Failing test first: install/tests/test_release_check.py :: ReleaseCheckReaTest.test_rea_aligned_passes

**Interfaces:**
- Consumes: `rea_setup.doctor_argv("claude_code")`, `rea_setup.skill_state(stdout)`; `release_check.RECORD`; the report object `rep` with `rep.say(status, label, detail)` (statuses: `"PASS"`, `"FAIL"`, `"SKIP"`, `"WARN"`; a `"WARN"` is not counted in `rep.fails`); `pu.claude_env(cd)` for the env.
- Produces: `release_check.rea(rep, cd, env, capture=None) -> None`, called in `_checks` right after `ruflo(...)`.

- [ ] **Step 1: Write the failing test.** Append class `ReleaseCheckReaTest` to `install/tests/test_release_check.py`, following how that file builds `rep` and imports `release_check` (read its top). Cases, each with a temp `cd`:
  - no `.dryas-plugin.json` or no `"rea"` key → one `SKIP` line `"REA"`, `capture` never called.
  - `{"rea": {...}}` and `capture` returning `(0, '{"identity": {"skill": {"state": "aligned"}}}')` → `PASS`.
  - `capture` returning `(0, '{"identity": {"skill": {"state": "missing"}}}')` → `WARN`, detail contains `missing`; `rep.fails` unchanged.
  - `capture` raising `OSError` or returning `(1, "")` → `WARN`; `rep.fails` unchanged.
  - `capture` receives `rea_setup.doctor_argv("claude_code")`.
- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_release_check.py -k Rea`. Expected: `AttributeError: module 'release_check' has no attribute 'rea'`.
- [ ] **Step 3: Implement.** In `tools/release_check.py`, add after `ruflo`:

```python
def rea(rep, cd, env, capture=None):
    """REA is an optional extra: report its doctor state; never a FAIL."""
    try:
        rec = json.loads((cd / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if not isinstance(rec, dict) or not isinstance(rec.get("rea"), dict):
        return rep.say("SKIP", "REA", "not set up in %s" % cd)
    import rea_setup
    argv = rea_setup.doctor_argv("claude_code")
    try:
        rc, out = (capture or _capture)(argv, env=pu.claude_env(cd, env))
    except OSError as ex:
        rc, out = 1, str(ex)
    state = rea_setup.skill_state(out) if rc == 0 else None
    if state == "aligned":
        return rep.say("PASS", "REA skill and MCP ready", "")
    rep.say("WARN", "REA skill and MCP ready", "doctor says %s; run `%s`" % (state or "nothing (exit %s)" % rc, " ".join(argv)))
```

  plus this helper above it:

```python
def _capture(argv, env=None):
    try:
        r = subprocess.run(argv, capture_output=True, universal_newlines=True, encoding="utf-8", env=env, timeout=600)
    except subprocess.TimeoutExpired:
        return 1, ""
    return r.returncode, r.stdout
```

  `rea_setup` must be importable because `install/` is on `sys.path` (check how `release_check` imports `platform_util as pu` and do the same). Call `rea(rep, cd, env)` in `_checks` right after the `ruflo(...)` call.
- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q install/tests/test_release_check.py && python3 -m pytest -q install/tests`. Expected: PASS.
- [ ] **Step 5: Commit** the Scope paths: `feat(release-check): report REA state for accounts that have it (task 5)`.

## Task 6: Workflow rules and skills

Goal: The template rule, the brainstorm "investigate with REA first" approach, the plan-skill evidence line, and their Codex/OpenCode renders.
Scope:
- claude/CLAUDE.md.template
- codex/AGENTS.md.template
- claude/skills/brainstorm/reference.md
- claude/skills/plan/SKILL.md
- codex/skills/**
- opencode/**
- install/tests/test_template_budget.py
- install/tests/test_rea_rules.py
Done:
- `python3 -m pytest -q install/tests/test_rea_rules.py install/tests/test_template_budget.py` passes
- `python3 tools/sync_codex_plugin.py --check` exits 0
- `python3 -m pytest -q install/tests` passes
Failing test first: install/tests/test_rea_rules.py :: ReaRulesTest.test_template_rule

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the template line text below (Task 7's docs quote it).

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_rea_rules.py`:

```python
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
LINE = "- Reverse-engineering work (how software you don't have the source for does something): use REA; brainstorm says when it recommends it, the user can decline."


class ReaRulesTest(unittest.TestCase):
    def read(self, p):
        return (ROOT / p).read_text(encoding="utf-8")

    def test_template_rule(self):
        for p, anchor in (("claude/CLAUDE.md.template", "- Design work"), ("codex/AGENTS.md.template", "- Brainstorm first")):
            t = self.read(p)
            self.assertIn(LINE, t, p)
            self.assertLess(t.index(anchor), t.index(LINE), p)

    def test_brainstorm_offers_rea(self):
        t = self.read("claude/skills/brainstorm/reference.md")
        sect = t.split("Exploring approaches")[1].split("\n## ")[0]
        for want in ("investigate with REA first", "install.sh --with-rea", "evidence"):
            self.assertIn(want, sect)

    def test_plan_carries_evidence(self):
        self.assertIn("REA finding", self.read("claude/skills/plan/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_rea_rules.py`. Expected: 3 failures (`LINE` not found, etc.).
- [ ] **Step 3: Implement.**
  - `claude/CLAUDE.md.template`: insert `LINE` (exact text above) as a new line directly after the line starting `- Design work (UI/UX`. In `codex/AGENTS.md.template` (it has no design line) insert it directly after the line starting `- Brainstorm first`.
  - `install/tests/test_template_budget.py`: the Claude template was 3523 bytes against a 3526 budget. Measure with `wc -c claude/CLAUDE.md.template codex/AGENTS.md.template` after the edit and set `BUDGET["claude/CLAUDE.md.template"]` to the new size rounded up to the next multiple of 50, keeping Codex's 2575 if it still fits; update the comment to `# measured <new claude> and <new codex> on 2026-10-21 (REA rule added); claude has no headroom by design`. This is a deliberate budget raise for an approved rule: say so in the report.
  - `claude/skills/brainstorm/reference.md` § Exploring approaches: append this paragraph:
    > **Software we don't have the source for.** When the request depends on how an app, binary, APK, Electron app or website we do not own behaves ("how does X do Y", "copy this feature from that app"), one proposed approach is "investigate with REA first" (the `rea` MCP tools and the `reverse-engineer-anything` skill), and you say why it fits; your partner can decline. REA's findings, with their evidence and stated limitations, go into the design artifact: the written spec, the in-chat design, or the spike's findings. If the `rea` MCP tools are not in this session, say so and give the install command (`install/install.sh --with-rea`, then restart) instead of failing; the other approaches stay on the table.
  - `claude/skills/plan/SKILL.md`, at the end of § Task format (after the fenced task template, before § No placeholders): add one line: `A task that depends on a REA finding carries that finding's evidence in its own section; executors do not call REA.`
  - Run `python3 tools/sync_codex_plugin.py` (it also renders `opencode/` via `sync_opencode.py`) so `codex/skills` and `opencode/` pick up the process-skill changes; then `python3 tools/sync_codex_plugin.py --check`.
- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q install/tests/test_rea_rules.py install/tests/test_template_budget.py && python3 tools/sync_codex_plugin.py --check && python3 -m pytest -q install/tests`. Expected: PASS, exit 0.
- [ ] **Step 5: Commit** the changed Scope paths: `feat(workflow): REA rule, brainstorm REA approach, plan evidence line (task 6)`.

## Task 7: Docs

Goal: `docs/workflow.md` and `docs/install.md` describe the REA extra, its flags, prerequisite, uninstall and the brainstorm behaviour; the launch-docs flag list includes the new flags.
Scope:
- docs/workflow.md
- docs/install.md
- install/tests/test_launch_docs.py
- install/tests/test_rea_docs.py
Done:
- `python3 -m pytest -q install/tests/test_rea_docs.py install/tests/test_launch_docs.py` passes
- `python3 -m pytest -q install/tests` passes
Failing test first: install/tests/test_rea_docs.py :: ReaDocsTest.test_install_doc

**Interfaces:**
- Consumes: the template line from Task 6; flags `--no-rea`, `--with-rea` from Task 2; record `rec["rea"]` and removal commands from Tasks 3-4.
- Produces: none.

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_rea_docs.py`:

```python
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


class ReaDocsTest(unittest.TestCase):
    def test_install_doc(self):
        t = (ROOT / "docs/install.md").read_text(encoding="utf-8")
        for want in ("--no-rea", "--with-rea", "rea-agents", "6.7.0", "22.19", "claude mcp remove --scope user rea",
                     "rea uninstall", "reverse-engineer-anything"):
            self.assertIn(want, t, want)

    def test_workflow_doc(self):
        t = (ROOT / "docs/workflow.md").read_text(encoding="utf-8")
        self.assertIn("**Reverse-engineering work.**", t)
        self.assertLess(t.index("**Design work.**"), t.index("**Reverse-engineering work.**"))
        self.assertIn("| MCP `rea` + skill `reverse-engineer-anything` |", t)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_rea_docs.py`. Expected: 2 failures.
- [ ] **Step 3: Implement.**
  - `docs/workflow.md` §4 step 1, a new paragraph right after the **Design work.** paragraph:
    > **Reverse-engineering work.** When a request depends on how software we don't have the source for behaves (an app, binary, APK, Electron app or website), brainstorm proposes "investigate with REA first" and says why; you can decline. REA ([morluto/rea](https://github.com/morluto/rea), installed by setup as an optional extra) returns findings with evidence and limitations, which go into the spec or the in-chat design. Executors never call REA: a task that needs a finding carries its evidence in its plan section.
  - `docs/workflow.md` tools table (the one with the `skills `impeccable`, `ui-ux-pro-max`` row): add the row `| MCP `rea` + skill `reverse-engineer-anything` | Reverse engineering of software without source; optional extra (§4 step 1) |`.
  - `docs/install.md`:
    - In the components table next to the Design skills row: `| REA | [rea-agents](https://github.com/morluto/rea) 6.7.0 (pinned): MCP server `rea` + skill `reverse-engineer-anything`, per Claude config dir (and Codex home with `--harness codex|both|all`); not for OpenCode or cloud. Needs Node.js 22.19+, 24.11+ or 26+ (else skipped with a warning). Setup shows REA's own dry run and asks before it changes the account's config; REA backs the config up to `.claude.json.rea.backup`. | `--no-rea` skips |`
    - In the third-party table near line 146 the same in one line, and in the flags table: `| `--no-rea` | Do not set up REA |` and `| `--with-rea` | Add REA on an upgrade that does not have it |`.
    - In the uninstall paragraph (line ~71) and the `--keep-extras` row (line ~173): REA is removed per config dir with `claude mcp remove --scope user rea` (Codex: `codex mcp remove rea`) plus the recorded `reverse-engineer-anything` skill folder; `rea uninstall` is never run because it removes REA from every client; `--keep-extras` leaves REA and prints the commands.
  - `install/tests/test_launch_docs.py` line ~44: add `"--no-rea"` and `"--with-rea"` to the flag tuple it checks.
- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q install/tests/test_rea_docs.py install/tests/test_launch_docs.py && python3 -m pytest -q install/tests`. Expected: PASS.
- [ ] **Step 5: Commit** the Scope paths: `docs: REA extra in workflow and install docs (task 7)`.
