# Haiku Economy Executor Tier Implementation Plan

> **For agentic workers:** run this plan with `/orchestrate` (Dryas Workflow). Each task's fenced header block (Goal, Scope, Done, Failing test first) is its `.orchestrate/PLAN.md` section; the Files, Interfaces and Steps below it are the detail the executor follows. Steps use checkbox (`- [ ]`) syntax. Executors do not commit; the orchestrator commits after review. `superpowers:subagent-driven-development` and `executing-plans` are denied in this workflow; do not use them.

**Goal:** Make Haiku the default executor tier below Sonnet, with a Jev skip-up question, a one-failure climb rule, a `/tune` climb-rate metric and a kill switch.

**Architecture:** Three new threshold keys in `claude/jev/thresholds.py` drive everything. `claude/jev/tune.py` reads dispatch and escalation logs to report ESC-M3 (Haiku → Sonnet climb rate over Haiku-started tasks) and Haiku share, and proposes turning the kill switch off when the rate is too high. The dispatch rule itself is prose in the orchestrate skill (the orchestrator passes `model: haiku`); `claude/agents/executor.md` stays `model: sonnet`.

**Tech Stack:** Python 3 stdlib, unittest/pytest; Markdown.

**Spec:** `docs/superpowers/specs/2026-10-08-haiku-economy-tier-design.md`

## Global Constraints

- Ladder: **Haiku → Sonnet → Opus → Fable → human**. Fable never starts a task. Haiku never reviews.
- `claude/agents/executor.md` is not changed (stays `model: sonnet`). Nothing under `claude/pstack/` is changed (`install/tests/test_pstack_content.py` forbids model names there).
- New threshold keys, exact: `escalation.haiku_failures_before_sonnet = 1` (int in [1, 5]), `escalation.haiku_climb_max = 0.35` (float in [0.0, 1.0]), `dispatch.haiku_default = True` (bool).
- Sonnet → Opus → Fable rules, thresholds (`sonnet_failures_before_opus 2`, `opus_failures_before_fable 1`, `executor_confidence_below 0.5`) and ESC-M1 are unchanged.
- `log_escalation` and `log_dispatch` schemas are unchanged.
- `/tune` only proposes `dispatch.haiku_default: false`; it never applies it.
- Python stdlib only. Files stay under 500 lines.
- Full suite: `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests` (baseline on `main`: all pass).

## Review Focus

1. **Task id mismatch between logs.** ESC-M3 joins `escalations` to `dispatch` by `task`. If the orchestrator logs a climb with a bare id (`3`) but the dispatch with `worktree-x:3`, the climb silently counts as zero. Owner: Task 3 states that `log_escalation.task` uses the same id as `log_dispatch.task`; Task 2 pins that an escalation whose task has no Haiku attempt-1 dispatch is not counted (`test_haiku_climb_rate_excludes_skip_ups`).
2. **A task re-dispatched on Sonnet after a Haiku failure** has two dispatch records (attempt 1 haiku, attempt 2 sonnet). It must count as Haiku-started. Owner: Task 2 (`test_haiku_climb_rate_excludes_skip_ups` includes the attempt-2 record).
3. **Two climb records for one task** (orchestrator logged twice) must count once, or the rate can exceed 100%. Owner: Task 2 (`test_haiku_climb_counts_task_once`).
4. **Kill switch already off.** `/tune` must not propose `haiku_default: false` when it is already false. Owner: Task 2 (`test_haiku_proposal_not_repeated_when_off`).
5. **`/tune apply dispatch.haiku_default 0`** (int, not bool) must be rejected, or Python truthiness turns the switch into a number. Owner: Task 1 (`test_haiku_default_must_be_bool`).

## Task order

```
Task 1 (thresholds) ─> Task 2 (tune + jev_mcp text)
Task 3 (orchestrate skill + rules template)
Task 4 (docs)
```

Tasks 1, 3 and 4 have disjoint scopes and can run in parallel. Task 2 needs Task 1's defaults.

## Follow-up outside this plan (raise with the user, do not do here)

FlowObserve (`projects/flowobserve`) hardcodes the ladder: `server/src/reducer.ts:182` maps `model === "sonnet" ? "build" : "escalate"`, `:273` advances stage on `e.model === "sonnet"`, `:281` defaults pending models to `"sonnet"`, and `server/src/queries.ts:56` sets `build: "sonnet"`. After this change, Haiku executor dispatches would show as the Escalate stage. That needs its own change in the FlowObserve repo.

---

### Task 1: Threshold keys for the Haiku tier

```
## Task 1: Threshold keys for the Haiku tier
Goal: Add haiku_failures_before_sonnet, haiku_climb_max and haiku_default to thresholds with validation.
Scope:
- claude/jev/thresholds.py
- claude/jev/tests/test_thresholds.py
Done:
- python3 -m pytest -q claude/jev/tests/test_thresholds.py passes
- python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests passes
Failing test first: claude/jev/tests/test_thresholds.py :: ThresholdsTest::test_haiku_defaults
```

**Files:**
- Modify: `claude/jev/thresholds.py` (`DEFAULTS["dispatch"]`, `DEFAULTS["escalation"]` and its comment, the `_failures_before_` clause in `validate`)
- Test: `claude/jev/tests/test_thresholds.py`

**Interfaces:**
- Produces: `thresholds.load()["escalation"]["haiku_failures_before_sonnet"] -> int` (1); `thresholds.load()["escalation"]["haiku_climb_max"] -> float` (0.35); `thresholds.load()["dispatch"]["haiku_default"] -> bool` (True). `thresholds.validate(dotted, value) -> Optional[str]` accepts and range-checks them.

- [ ] **Step 1: Write the failing tests.** Add these methods to class `ThresholdsTest` in `claude/jev/tests/test_thresholds.py`:

```python
    def test_haiku_defaults(self):
        t = thresholds.load()
        self.assertEqual(t["escalation"]["haiku_failures_before_sonnet"], 1)
        self.assertEqual(t["escalation"]["haiku_climb_max"], 0.35)
        self.assertIs(t["dispatch"]["haiku_default"], True)
        self.assertEqual(t["escalation"]["sonnet_failures_before_opus"], 2)
        self.assertEqual(t["escalation"]["opus_failures_before_fable"], 1)

    def test_failures_before_keys_range(self):
        for key in ("escalation.haiku_failures_before_sonnet",
                    "escalation.sonnet_failures_before_opus",
                    "escalation.opus_failures_before_fable"):
            self.assertIsNone(thresholds.validate(key, 1), key)
            self.assertIsNone(thresholds.validate(key, 5), key)
            self.assertIsNotNone(thresholds.validate(key, 0), key)
            self.assertIsNotNone(thresholds.validate(key, 6), key)
            self.assertIsNotNone(thresholds.validate(key, 1.5), key)
            self.assertIsNotNone(thresholds.validate(key, True), key)

    def test_haiku_climb_max_range(self):
        self.assertIsNone(thresholds.validate("escalation.haiku_climb_max", 0.5))
        self.assertIsNone(thresholds.validate("escalation.haiku_climb_max", 0.0))
        self.assertIsNone(thresholds.validate("escalation.haiku_climb_max", 1.0))
        self.assertIsNotNone(thresholds.validate("escalation.haiku_climb_max", 1.2))
        self.assertIsNotNone(thresholds.validate("escalation.haiku_climb_max", -0.1))
        self.assertIsNotNone(thresholds.validate("escalation.haiku_climb_max", "0.3"))

    def test_haiku_default_must_be_bool(self):
        self.assertIsNone(thresholds.validate("dispatch.haiku_default", False))
        self.assertIsNone(thresholds.validate("dispatch.haiku_default", True))
        self.assertIsNotNone(thresholds.validate("dispatch.haiku_default", 0))
        self.assertIsNotNone(thresholds.validate("dispatch.haiku_default", "false"))
```

- [ ] **Step 2: Run to verify they fail.**

Run: `python3 -m pytest -q claude/jev/tests/test_thresholds.py -k "haiku or failures_before"`
Expected: FAIL (`KeyError: 'haiku_failures_before_sonnet'`, and "Unknown key" for the validate tests).

- [ ] **Step 3: Implement.** In `claude/jev/thresholds.py`, change the two `DEFAULTS` entries:

```python
    "dispatch": {"min_confidence": 0.7, "haiku_default": True},
    # Ladder: haiku -> sonnet -> opus -> fable. Fable only after the Opus executor also failed.
    # haiku_climb_max: /tune proposes dispatch.haiku_default false above this Haiku->Sonnet climb rate.
    "escalation": {"executor_confidence_below": 0.5, "haiku_failures_before_sonnet": 1,
                   "sonnet_failures_before_opus": 2, "opus_failures_before_fable": 1, "haiku_climb_max": 0.35},
```

In `validate`, replace the clause

```python
    if key.endswith("_failures_before_") or key.endswith("_failures_before_opus") or key.endswith("_failures_before_fable"):
```

with

```python
    if re.search(r"_failures_before_(sonnet|opus|fable)$", key):
```

(keep its body), and add next to the `keep_min` check:

```python
    if key == "haiku_climb_max" and (value < 0.0 or value > 1.0):
        return f"{dotted} must be a float in [0.0, 1.0]"
```

`re` is already imported. The bool check for `haiku_default` comes from the existing `_type_check` (a bool default accepts only bool).

- [ ] **Step 4: Run to verify they pass.**

Run: `python3 -m pytest -q claude/jev/tests/test_thresholds.py`
Expected: all pass.

- [ ] **Step 5: Full suite.**

Run: `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests`
Expected: all pass.

---

### Task 2: `/tune` ESC-M3, Haiku share, kill-switch proposal; `log_escalation` text

```
## Task 2: /tune ESC-M3, Haiku share and kill-switch proposal
Goal: Report the Haiku->Sonnet climb rate and Haiku share, propose dispatch.haiku_default false above haiku_climb_max, and fold needs_sonnet names.
Scope:
- claude/jev/tune.py
- claude/jev/tests/test_tune.py
- claude/jev/jev_mcp.py
Done:
- python3 -m pytest -q claude/jev/tests/test_tune.py passes
- python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests passes
- grep -n "haiku -> sonnet -> opus -> fable" claude/jev/jev_mcp.py prints one line
Failing test first: claude/jev/tests/test_tune.py :: TuneTest::test_haiku_climb_rate_excludes_skip_ups
```

**Files:**
- Modify: `claude/jev/tune.py` (`CANONICAL`, `delivery()`, `proposals()`, `render()`)
- Modify: `claude/jev/jev_mcp.py` (the `log_escalation` description string only)
- Test: `claude/jev/tests/test_tune.py`

**Interfaces:**
- Consumes: Task 1's `thresholds.load()["escalation"]["haiku_climb_max"]` and `["dispatch"]["haiku_default"]`.
- Produces: `tune.build()["delivery"]` gains `haiku_tasks: int`, `haiku_share: Optional[float]`, `haiku_climb_rate: Optional[float]`, `haiku_climb_reasons: Dict[str, int]`. `tune.proposals()` may return `{"key": "dispatch.haiku_default", "old": True, "new": False, "why": str}`. `tune.canonical("needs_sonnet.<task>") == "needs_sonnet"`.

- [ ] **Step 1: Write the failing tests.** Add these methods to class `TuneTest` in `claude/jev/tests/test_tune.py`:

```python
    def _haiku_logs(self, started, climbed, skip_ups=0, reason="missed edge case"):
        disp = [{"task": "w:%d" % i, "tier": "haiku", "role": "coder", "attempt": 1} for i in range(started)]
        disp += [{"task": "w:%d" % i, "tier": "sonnet", "role": "coder", "attempt": 2} for i in range(climbed)]
        disp += [{"task": "s:%d" % i, "tier": "sonnet", "role": "coder", "attempt": 1} for i in range(skip_ups)]
        esc = [{"task": "w:%d" % i, "reason": reason, "decided_by": "opus",
                "from_model": "haiku", "to_model": "sonnet"} for i in range(climbed)]
        esc += [{"task": "s:%d" % i, "reason": "skip-up: multi-file", "decided_by": "jev",
                 "from_model": "haiku", "to_model": "sonnet"} for i in range(skip_ups)]
        write(self.d, "dispatch", disp)
        write(self.d, "escalations", esc)

    def test_haiku_climb_rate_excludes_skip_ups(self):
        self._haiku_logs(started=4, climbed=1, skip_ups=2)
        d = tune.build()["delivery"]
        self.assertEqual(d["tasks_dispatched"], 6)
        self.assertEqual(d["haiku_tasks"], 4)
        self.assertAlmostEqual(d["haiku_share"], round(4 / 6, 4))
        self.assertAlmostEqual(d["haiku_climb_rate"], 0.25)
        self.assertEqual(d["haiku_climb_reasons"], {"missed edge case": 1})

    def test_haiku_climb_counts_task_once(self):
        write(self.d, "dispatch", [{"task": "w:1", "tier": "haiku", "role": "coder", "attempt": 1},
                                   {"task": "w:2", "tier": "haiku", "role": "coder", "attempt": 1}])
        write(self.d, "escalations", [{"task": "w:1", "reason": "a", "from_model": "haiku", "to_model": "sonnet"},
                                      {"task": "w:1", "reason": "a", "from_model": "haiku", "to_model": "sonnet"}])
        self.assertAlmostEqual(tune.build()["delivery"]["haiku_climb_rate"], 0.5)

    def test_haiku_metrics_na_without_haiku(self):
        write(self.d, "dispatch", [{"task": "s:1", "tier": "sonnet", "role": "coder", "attempt": 1}])
        rep = tune.build()
        d = rep["delivery"]
        self.assertEqual((d["haiku_tasks"], d["haiku_climb_rate"]), (0, None))
        self.assertEqual(d["haiku_share"], 0.0)
        out = tune.render(rep, [])
        self.assertIn("Haiku->Sonnet climb rate", out)
        self.assertIn("n/a", out.split("Haiku->Sonnet climb rate", 1)[1].splitlines()[0])

    def test_haiku_metrics_empty_logs(self):
        d = tune.build()["delivery"]
        self.assertEqual((d["haiku_tasks"], d["haiku_share"], d["haiku_climb_rate"]), (0, None, None))

    def _haiku_props(self):
        return [p for p in tune.proposals(tune.build(), thresholds.load()) if p["key"] == "dispatch.haiku_default"]

    def test_haiku_proposal_fires_above_max(self):
        self._haiku_logs(started=25, climbed=9)          # 0.36
        p = self._haiku_props()
        self.assertEqual(len(p), 1)
        self.assertEqual((p[0]["old"], p[0]["new"]), (True, False))
        self.assertIn("missed edge case", p[0]["why"])

    def test_haiku_proposal_not_at_max(self):
        self._haiku_logs(started=20, climbed=7)          # 0.35, not above
        self.assertEqual(self._haiku_props(), [])

    def test_haiku_proposal_needs_ten_tasks(self):
        self._haiku_logs(started=9, climbed=9)           # 100% but only 9 tasks
        self.assertEqual(self._haiku_props(), [])

    def test_haiku_proposal_not_repeated_when_off(self):
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump({"dispatch": {"haiku_default": False}}, f)
        self._haiku_logs(started=10, climbed=10)
        self.assertEqual(self._haiku_props(), [])

    def test_needs_sonnet_canonical(self):
        for raw in ("needs_sonnet.3", "needs_sonnet.worktree-x:3", "needs_sonnet_t2", "t4_needs_sonnet"):
            self.assertEqual(tune.canonical(raw), "needs_sonnet", raw)
```

- [ ] **Step 2: Run to verify they fail.**

Run: `python3 -m pytest -q claude/jev/tests/test_tune.py -k "haiku or needs_sonnet"`
Expected: FAIL (`KeyError: 'haiku_tasks'`; canonical returns `needs_sonnet_t2` unchanged).

- [ ] **Step 3: Implement `CANONICAL`.** In `claude/jev/tune.py`:

```python
CANONICAL = ("executor", "specific", "failing_test_exists", "needs_opus", "needs_sonnet", "needs_stronger_model",
             "done", "risk", "safe_to_commit", "needs_interrogate")
```

- [ ] **Step 4: Implement the metrics in `delivery()`.** After the line `climbs = _steps(esc, "opus", "sonnet")["count"]`, add:

```python
    # ESC-M3: a task is Haiku-started when its attempt-1 dispatch had tier haiku. Skip-ups (Jev needs_sonnet)
    # have a sonnet attempt-1 dispatch, so their haiku->sonnet records do not count.
    first_tier: Dict[str, Any] = {}
    for r in dispatch:
        if r.get("task") is not None and _int(r.get("attempt")) == 1:
            first_tier.setdefault(str(r["task"]), r.get("tier"))
    haiku_tasks = {t for t, tier in first_tier.items() if tier == "haiku"}
    haiku_climbs = [r for r in esc if isinstance(r, dict) and r.get("from_model") == "haiku"
                    and r.get("to_model") == "sonnet" and str(r.get("task")) in haiku_tasks]
    haiku_climbed = {str(r.get("task")) for r in haiku_climbs}
```

and add these entries to the returned dict, after `"climb_rate"`:

```python
        "haiku_tasks": len(haiku_tasks),
        "haiku_share": round(len(haiku_tasks) / n, 4) if n else None,
        "haiku_climb_rate": round(len(haiku_climbed) / len(haiku_tasks), 4) if haiku_tasks else None,
        "haiku_climb_reasons": dict(Counter(str(r.get("reason")) for r in haiku_climbs)),
```

- [ ] **Step 5: Implement the proposal.** In `proposals()`, before the final `return`, add:

```python
    d = rep.get("delivery") or {}
    rate, started = d.get("haiku_climb_rate"), d.get("haiku_tasks") or 0
    if rate is not None and started >= 10 and th["dispatch"].get("haiku_default", False):
        cap = th["escalation"]["haiku_climb_max"]
        if rate > cap:
            out.append({"key": "dispatch.haiku_default", "old": True, "new": False,
                        "why": "Haiku->Sonnet climb rate %.0f%% over %d Haiku-started tasks (max %.0f%%); reasons: %s"
                               % (rate * 100, started, cap * 100, json.dumps(d.get("haiku_climb_reasons") or {}))})
```

Order matters: the module-level `TH` dict and the hand-built reports at the bottom of `test_tune.py` have no `delivery` and no `escalation` section. With no Haiku data, `rate` is `None` and the thresholds are never read, so those tests keep passing unchanged. Do not edit `TH`.

- [ ] **Step 6: Implement the report lines.** In `render()`, insert after the `"- Sonnet->Opus climb rate ..."` entry of `delivery_lines`:

```python
        "- Haiku share of first dispatches: %s (%d Haiku-started tasks)" % (
            "n/a" if d["haiku_share"] is None else "%.0f%%" % (d["haiku_share"] * 100), d["haiku_tasks"]),
        "- Haiku->Sonnet climb rate (healthy at or under escalation.haiku_climb_max): %s %s" % (
            "n/a" if d["haiku_climb_rate"] is None else "%.0f%%" % (d["haiku_climb_rate"] * 100),
            json.dumps(d["haiku_climb_reasons"])),
```

- [ ] **Step 7: Update the `log_escalation` description** in `claude/jev/jev_mcp.py`:

```python
        "description": ("Record one escalation step with its reason. Ladder: haiku -> sonnet -> opus -> fable; fable only after an "
                        "Opus executor failed the same task. Required for every step."),
```

- [ ] **Step 8: Run to verify they pass.**

Run: `python3 -m pytest -q claude/jev/tests/test_tune.py`
Expected: all pass (new and existing).

- [ ] **Step 9: Full suite.**

Run: `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests`
Expected: all pass.

---

### Task 3: Orchestrate skill, command and rules template

```
## Task 3: Orchestrate skill, command and rules template
Goal: Write the Haiku start-tier rule, needs_sonnet question, Haiku climb rule and shared task-id rule into the orchestrate skill, its command and the CLAUDE.md template.
Scope:
- claude/skills/orchestrate/SKILL.md
- claude/commands/orchestrate.md
- claude/CLAUDE.md.template
Done:
- grep -n "needs_sonnet" claude/skills/orchestrate/SKILL.md shows the §3 bullet, the §3 JSON entry and the §5 start-tier rule
- grep -n "Sonnet → Opus → Fable\|model sonnet from its frontmatter" claude/skills/orchestrate/SKILL.md claude/CLAUDE.md.template prints nothing
- python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests passes
Failing test first: none (docs)
```

**Files:**
- Modify: `claude/skills/orchestrate/SKILL.md` (frontmatter description, §3, §5.4–5.6, §7)
- Modify: `claude/commands/orchestrate.md` (description)
- Modify: `claude/CLAUDE.md.template` (Model policy block)

**Interfaces:**
- Consumes: threshold names from Task 1 (`dispatch.haiku_default`, `escalation.haiku_failures_before_sonnet`).
- Produces: the rule that `log_escalation.task` equals `log_dispatch.task` (Task 2's ESC-M3 depends on it).

Keep the `<!-- pstack-picks -->` / `<!-- /pstack-picks -->` markers exactly where they are; only edit text inside them as shown.

- [ ] **Step 1: SKILL.md frontmatter.** Line 3: replace `with Sonnet executors` with `with Haiku-first executors (Sonnet, Opus, Fable on escalation)`.

- [ ] **Step 2: SKILL.md §3.** After the `needs_opus` bullet add:

```markdown
- `needs_sonnet` noul (only when `dispatch.haiku_default` is true): "Does this task need a model stronger than Haiku (touches more than one file, non-mechanical logic, or test design beyond a single assertion)?"
```

In the JSON block, add after the `needs_opus` entry (add a comma to the end of the `needs_opus` line, and move the closing `}}}` to the new line):

```json
  "needs_sonnet": {"type": "noul", "instructions": "Does the task in `task_section` need a model stronger than Haiku (touches more than one file, non-mechanical logic, or test design beyond a single assertion)?"}}}
```

- [ ] **Step 3: SKILL.md §5 items 4–6.** Replace items 4 and 5 with:

```markdown
4. Dispatch with the Agent tool, `subagent_type: executor`. Pick the start tier per task, first match wins:
   1. `needs_opus` true at confidence ≥ threshold, or your own judgment → `model: opus`, after `mcp__jev__log_escalation` (from_model haiku if `dispatch.haiku_default` is true, else sonnet; to_model opus).
   2. `dispatch.haiku_default` false → no `model` (Sonnet from the agent's frontmatter). Do not ask `needs_sonnet`.
   3. `needs_sonnet` true at confidence ≥ threshold, or your own judgment → no `model` (Sonnet), after `mcp__jev__log_escalation` (from_model haiku, to_model sonnet, reason "skip-up: <why>").
   4. Otherwise → `model: haiku`.
   Independent tasks go out in one message, in parallel. Never dispatch Fable here: Fable is only reached through §7. Review and interrogate dispatches (§7b) never use Haiku.
5. Every `log_dispatch` and `log_escalation` call for a task uses the same task id: "<worktree branch>:<PLAN.md task id>", e.g. worktree-feat:3. `/tune` joins the two logs on it.
```

In item 6, change `tier (sonnet, opus or fable)` to `tier (haiku, sonnet, opus or fable)` and replace `with task ("<worktree branch>:<PLAN.md task id>", e.g. worktree-feat:3, so ids stay unique across runs)` with `with task (the §5.5 id)`.

- [ ] **Step 4: SKILL.md §7.** Replace `Ladder: **Sonnet → Opus → Fable**.` with `Ladder: **Haiku → Sonnet → Opus → Fable**.` Inside the pstack-picks block replace `Before each climb (Sonnet → Opus, Opus → Fable)` with `Before each climb (Haiku → Sonnet, Sonnet → Opus, Opus → Fable)`. Add a new item 0 before item 1:

```markdown
0. A Haiku executor that fails done-criteria `escalation.haiku_failures_before_sonnet` times (1), or reports CONFIDENCE below `escalation.executor_confidence_below`, is re-dispatched with no `model` (Sonnet). Call `mcp__jev__log_escalation` first (from haiku, to sonnet, with the reason). From there the Sonnet rules below apply, starting at zero Sonnet failures.
```

Change the line `First Sonnet failure: re-dispatch once more on Sonnet with the failure details; the second Sonnet failure escalates to Opus.` to `First Sonnet failure: re-dispatch once more on Sonnet with the failure details; the second Sonnet failure escalates to Opus. Haiku gets no second try (item 0).` Change item 4 `with all three reports` to `with every tier's report`.

- [ ] **Step 5: `claude/commands/orchestrate.md`.** Description line becomes:

```
description: Run a multi-step task with the Opus orchestrator, Haiku-first executors and Jev gates
```

- [ ] **Step 6: `claude/CLAUDE.md.template` Model policy block.** Replace the Executors and Escalation ladder lines with:

```markdown
- Executors: Haiku first. `/orchestrate` passes `model: haiku` unless Jev's `needs_sonnet` or `needs_opus` (or Opus judgment) starts the task higher; `~/.claude/agents/executor.md` stays Sonnet so review dispatches never run on Haiku. Kill switch: `dispatch.haiku_default` in `~/.claude/jev/thresholds.json`.
- Escalation ladder: Haiku → Sonnet → Opus → Fable. A task Haiku fails once goes to Sonnet; a task Sonnet can't finish goes to an Opus executor; Fable is used only if the Opus executor also fails that task. Stop at the first success. Every step is logged with its reason via `mcp__jev__log_escalation`.
```

- [ ] **Step 7: Verify.** Run the Done greps and the full suite; expected as listed in the task header.

---

### Task 4: Workflow docs, metrics and framework spec

```
## Task 4: Workflow docs, metrics and framework spec
Goal: Update workflow, escalation model, metrics, architecture, README and the framework spec to the four-tier ladder and ESC-M3.
Scope:
- docs/workflow.md
- docs/escalation-model.md
- docs/metrics.md
- docs/architecture.md
- README.md
- spec/dryas-spec-v1.md
Done:
- grep -rnE "Sonnet → Opus → Fable|Sonnet, then Opus, then Fable|sonnet -> opus -> fable|\[sonnet, opus, fable\]" docs/workflow.md docs/escalation-model.md docs/architecture.md README.md spec/dryas-spec-v1.md prints nothing
- grep -n "ESC-M3" docs/metrics.md prints one table row
- python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests passes
Failing test first: none (docs)
```

**Files:**
- Modify: `docs/workflow.md` (§3 and the thresholds table)
- Modify: `docs/escalation-model.md`
- Modify: `docs/metrics.md` (Escalation table)
- Modify: `docs/architecture.md` (Execution and Escalation rows)
- Modify: `README.md` (Build/Escalate bullets near line 49 and the ladder bullet near line 56)
- Modify: `spec/dryas-spec-v1.md` (`execution` and `escalation` blocks)

**Interfaces:**
- Consumes: threshold names and values from Task 1; the ESC-M3 definition from Task 2.

- [ ] **Step 1: `docs/workflow.md` §3.** Replace the bullets "Executors run on Sonnet by default." through the `needs_opus` sub-bullet with:

```markdown
- **Executors start on Haiku by default.** `/orchestrate` passes `model: haiku`; `~/.claude/agents/executor.md` stays `model: sonnet`, so review dispatches never run on Haiku. Kill switch: `dispatch.haiku_default` (false = every task starts on Sonnet, as before).
- **The ladder is Haiku → Sonnet → Opus → Fable.**
  1. A Haiku executor that fails done-criteria once, or reports confidence below 0.5, is re-run on **Sonnet**.
  2. A Sonnet executor that fails done-criteria twice, or reports confidence below 0.5, is re-run on **Opus**.
  3. If Opus solves it, stop. **No Fable.**
  4. Only if the Opus executor also fails is the task re-run once on **Fable**.
  5. If Fable fails too, the task goes to you with every tier's report.
  - Jev's per-task `needs_sonnet` answer can start an executor on Sonnet, and `needs_opus` on Opus. Nothing starts a task on Fable directly.
```

In the "Root cause before each climb" bullet, replace `Before Sonnet → Opus and Opus → Fable` with `Before Haiku → Sonnet, Sonnet → Opus and Opus → Fable`. In the thresholds table, the rows become:

```markdown
  | dispatch | min_confidence 0.7, haiku_default true |
  | escalation | executor_confidence_below 0.5, haiku_failures_before_sonnet 1, sonnet_failures_before_opus 2, opus_failures_before_fable 1, haiku_climb_max 0.35 (`/tune` proposes haiku_default false above it over ≥10 Haiku-started tasks) |
```

- [ ] **Step 2: `docs/escalation-model.md`.** Diagram becomes:

```
economy tier ──fail──► cheap tier ──fail──► strong tier ──fail──► frontier tier ──fail──► human
 (Haiku)                (Sonnet)             (Opus)                (Fable)                (all reports)
```

Replace `the reference implementation binds them to Sonnet, Opus and Fable.` with `the reference implementation binds them to Haiku, Sonnet, Opus and Fable.` Rule 1 becomes: `**Start at the bottom.** Every task starts on the economy tier, unless the judge says it needs the cheap or strong tier. Nothing starts on the frontier tier. If the economy tier is switched off, tasks start on the cheap tier.` Rule 7: add `never the economy tier or` before `the frontier tier`. Add table rows `| Economy-tier failures before the cheap tier | 1 |` (first row) and `| Economy-tier climb rate above which the tune proposes switching it off | 0.35 over ≥10 tasks |` (last row), and rename `Judge confidence to trust a needs_opus answer` to `Judge confidence to trust a needs_sonnet or needs_opus answer`. In "Reference binding", replace the first sentence with: `Executors start on Haiku (the orchestrate skill passes model: haiku; claude/agents/executor.md stays Sonnet for review dispatches); the orchestrate skill re-runs on Sonnet, Opus and then Fable.`

- [ ] **Step 3: `docs/metrics.md`.** Add after the ESC-M2 row:

```markdown
| ESC-M3 | Economy-tier climb rate | Haiku → Sonnet climbs ÷ tasks whose attempt-1 dispatch was on Haiku. Skip-ups (Jev `needs_sonnet` before any Haiku attempt) are excluded; each task counts once. | At or under 35% (`escalation.haiku_climb_max`) | `escalations`, `dispatch` | Weekly | live | Read the logged reasons. Above the max over ≥10 Haiku-started tasks, `/tune` proposes `dispatch.haiku_default: false`. |
```

In the `dispatch` row of the log table, change the KPI column `GOV-M4, ESC-M1` to `GOV-M4, ESC-M1, ESC-M3`.

- [ ] **Step 4: `docs/architecture.md`.** In the Execution row (line 25), replace `` `executor` agent on Sonnet, git worktrees `` with `` `executor` agent (Haiku first; Sonnet default for reviews), git worktrees ``. In the Escalation row (line 26), replace `Sonnet → Opus → Fable` with `Haiku → Sonnet → Opus → Fable`.

- [ ] **Step 5: `README.md`.** Replace:
- `- **Build**: Sonnet executors do each task inside a git worktree.` → `- **Build**: Haiku executors do each task inside a git worktree; harder tasks start on Sonnet or Opus.`
- `- **Escalate**: if Sonnet cannot finish a task, Opus tries it. Fable is used only if Opus also fails.` → `- **Escalate**: if Haiku fails a task, Sonnet tries it; then Opus. Fable is used only if Opus also fails.`
- `- **Escalation ladder.** Sonnet, then Opus, then Fable. Each step is logged with a reason.` → `- **Escalation ladder.** Haiku, then Sonnet, then Opus, then Fable. Each step is logged with a reason.`

- [ ] **Step 6: `spec/dryas-spec-v1.md`.** In `execution`, `executor: sonnet` → `executor: haiku` and add `review_executor: sonnet` below it. In `escalation`:

```yaml
  ladder: [haiku, sonnet, opus, fable]
  climb_after_failures: {haiku: 1, sonnet: 2, opus: 1}
```

- [ ] **Step 7: Verify.** Run the Done greps and the full suite; expected as listed in the task header.

---

## After all tasks

1. Interrogate gate (§7b of the orchestrate skill) and cleanup task as usual.
2. `/wreview`, then superpowers:verification-before-completion, then merge to `main`.
3. Ask the user before running `install/install.sh` (it rewrites the installed `~/.claude/CLAUDE.md` block and skill copies).
4. Raise the FlowObserve follow-up (above) with the user.
5. Merge note: branch `worktree-gate-prescreen` also edits `claude/jev/thresholds.py`, `tune.py` and `docs/workflow.md`; whichever merges second resolves the conflict.
