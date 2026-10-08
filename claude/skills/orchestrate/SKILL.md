---
name: orchestrate
description: Run a multi-step coding task as Opus orchestrator with Haiku-first executors (Sonnet, Opus, Fable on escalation), Jev routing/gates, Ruflo memory and Superpowers process. Use for /orchestrate or any multi-file task. Not for single-file fixes.
---

# Orchestrate

Ruflo and Jev MCP tools may be deferred — load them with ToolSearch (e.g. `select:mcp__plugin_ruflo-core_ruflo__memory_search`) before first use.

## 0. Brainstorm first (always)
Unless the request points at an already-approved design/spec, invoke superpowers:brainstorming first and finish its gates (design approved by the user) before step 1. Orchestration plans from the approved design, never from the raw request.

You (Opus) plan, dispatch, judge and integrate. You never edit project files yourself on a multi-step task. Jev answers narrow questions; you decide whenever Jev is below threshold, escalates, or is unavailable. Thresholds: `~/.claude/jev/thresholds.json` (defaults in `~/.claude/jev/thresholds.py`). Ruflo tool names: `~/.claude/skills/orchestrate/ruflo-tools.md`.

<!-- pstack-picks -->
Keep bulk output in executors and only summaries here (`{{CD}}/pstack/principles/guard-the-context-window.md`). Judge each report against the real artifact, not the self-report (`{{CD}}/pstack/principles/prove-it-works.md`).

<!-- /pstack-picks -->
## 1. Memory first
Search Ruflo memory (memory_search from ruflo-tools.md, namespace = project folder name) for tasks similar to the request. Take the top 3 outcomes and write them down as `Past: <what worked> / <what failed>` before planning. None found → say so.

## 2. Plan as a file
1. Create a worktree with superpowers:using-git-worktrees. One agent per worktree: this session owns it alone. Never reuse a worktree another session is working in; parallel loops on the same project each get their own worktree and branch.
2. Write `.orchestrate/PLAN.md` in the worktree, one section per task, exactly:

   ```
   ## Task <N>: <title>
   Goal: <one sentence>
   Scope:
   - <glob relative to worktree root>
   Done:
   - <verifiable criterion, incl. test command>
   Failing test first: <test file :: test name>
   ```

   Scopes of tasks that may run in parallel must not overlap.
<!-- pstack-picks -->
   When the approved design is performance work, every task that produces or reports a measured number gets the Done line: `numbers vetted per {{CD}}/pstack/benchmark-checklist.md (verdict, run count, range, limiter)`.
<!-- /pstack-picks -->
3. `.orchestrate/` is ignored globally (~/.config/git/ignore); never commit it.

## 3. Per-task Jev call (one call per task; batch when >5 tasks to triage)
`mcp__jev__jev_judge` with state `{task_section, test_file_exists: bool, last_test_run_tail, past_outcomes}` and questions:
- `executor` choice: `{coder, tester, reviewer, docs, none_of_these}`
- `specific` noul: "Is this task specific enough for an executor to finish without asking questions?"
- `failing_test_exists` noul: "Does a failing test for this task already exist?"
- `needs_opus` noul: "Does this task need a model stronger than Sonnet (cross-cutting refactor, or concurrency- or security-sensitive code)?"
- `needs_sonnet` noul (only when `dispatch.haiku_default` is true): "Does this task need a model stronger than Haiku (touches more than one file, non-mechanical logic, or test design beyond a single assertion)?"

Exact shape (criteria for `choice` is a map option -> description; `noul` criteria is {"true": ..., "false": ...}; `score` criteria is an ordered list of 2–10 level descriptions):
```json
{"state": {"task_section": "...", "test_file_exists": false, "last_test_run_tail": "", "past_outcomes": []},
 "questions": {
  "executor": {"type": "choice", "instructions": "Which kind of executor should take this .orchestrate/PLAN.md task (see `task_section`)?",
               "criteria": {"coder": "Writes or changes production code", "tester": "Writes the failing test first", "reviewer": "Reviews existing changes only", "docs": "Documentation only", "none_of_these": "None of these fits"}},
  "specific": {"type": "noul", "instructions": "Is the task in `task_section` specific enough for an executor to finish without asking questions?",
               "criteria": {"true": "Goal, scope and done-criteria are concrete", "false": "Something essential is missing or ambiguous"}},
  "failing_test_exists": {"type": "noul", "instructions": "Does a failing test for the task in `task_section` already exist (see `test_file_exists`, `last_test_run_tail`)?"},
  "needs_opus": {"type": "noul", "instructions": "Does the task in `task_section` need a model stronger than Sonnet (cross-cutting refactor, concurrency- or security-sensitive code)?"},
  "needs_sonnet": {"type": "noul", "instructions": "Does the task in `task_section` need a model stronger than Haiku (touches more than one file, non-mechanical logic, or test design beyond a single assertion)?"}}}
```
Omit `needs_sonnet` from the call when `dispatch.haiku_default` is false.
Question names are never sent to Jev, so each `instructions` must be self-contained and reference state by backticked field names.

Run tests with paths relative to the worktree when possible; if the project's venv lives only in the main checkout, use its absolute path.

Any name in `escalate`, or Jev unavailable → you decide that item. Whenever your decision differs from Jev's answer, call `mcp__jev__log_override`.

## 4. TDD gate
If `failing_test_exists` is not confidently true: dispatch a **tester** executor first for that task, confirm the test fails for the right reason, then dispatch the coder.
<!-- pstack-picks -->
Review and cleanup tasks (`Failing test first: none (review)` or `none (cleanup)`) skip this gate and the §3 Jev call; their executor role is fixed (reviewer or coder).
<!-- /pstack-picks -->

## 5. Dispatch
1. Initialise the Ruflo swarm once (swarm_init from ruflo-tools.md). Call it with topology "hierarchical" (the plugin default is hierarchical-mesh).
2. Write `.orchestrate/active.json` = `{"active": [<task ids being dispatched now>]}` before dispatching; this arms the scope lock. On EVERY exit path — success, failure handed to the user (§7.3/§7.4), user abort, or any error — delete `.orchestrate/active.json` before stopping; the scope lock stays armed while it exists.
3. Give each executor ONLY its section: `"{{PY}}" -X utf8 "{{CD}}/jev/planfile.py" section .orchestrate/PLAN.md <N>` plus the absolute worktree path. Never the whole plan.
4. Dispatch with the Agent tool, `subagent_type: executor`. Pick the start tier per task, first match wins:
   1. `needs_opus` true at confidence ≥ threshold, or your own judgment → `model: opus`, after `mcp__jev__log_escalation` (from_model sonnet, to_model opus, whatever `dispatch.haiku_default` says, so ESC-M1 counts it the same way as before Haiku).
   2. `dispatch.haiku_default` false → no `model` (Sonnet from the agent's frontmatter). Do not ask `needs_sonnet`.
   3. `needs_sonnet` true at confidence ≥ threshold, or your own judgment → no `model` (Sonnet), after `mcp__jev__log_escalation` (from_model haiku, to_model sonnet, reason "skip-up: <why>").
   4. Otherwise → `model: haiku`.
   Independent tasks go out in one message, in parallel. Never dispatch Fable here: Fable is only reached through §7. Review, interrogate and cleanup dispatches (§7b) never use Haiku: they start on Sonnet (no `model`) and log no skip-up.
5. Every `log_dispatch` and `log_escalation` call for a task uses the same task id: "<worktree branch>:<PLAN.md task id>", e.g. worktree-feat:3. `/tune` joins the two logs on it.
6. Right after every dispatch (first or re-dispatch, any tier) call `mcp__jev__log_dispatch` with task (the §5.5 id), tier (haiku, sonnet, opus or fable), role (coder, tester, reviewer or docs) and attempt (1 for the first dispatch of that task, then +1 per re-dispatch).

## 6. On return
For each report, one `jev_judge` call with state `{task_section, executor_report}`:
- `done` noul: "Are all done-criteria met according to the report?"
- `risk` score: `["routine", "worth a look", "incident"]`

Note: `risk` is a score question whose criteria is the list ["routine", "worth a look", "incident"]. Question names are never sent to Jev, so each `instructions` must be self-contained and reference state by backticked field names.

Only an incident, a failure or an escalation reaches you in full; otherwise log one summary line per task. Remove a task id from `active.json` only when that task is finished or handed to the user; a task being re-dispatched stays active. If an executor reports `SCOPE: need <path> because <reason>`, you (main thread) decide; if justified, add the glob to that task's Scope in .orchestrate/PLAN.md (the scope lock lets only the main thread edit .orchestrate/PLAN.md), then re-dispatch. Store the outcome in Ruflo memory (memory_store, same namespace): task title, what worked, what failed.

## 7. Escalation
Ladder: **Haiku → Sonnet → Opus → Fable**. Fable is used only when Opus also could not do the task.
Every `mcp__jev__log_escalation` call passes all five fields: task, reason, decided_by ("jev" or "opus"), from_model, to_model.
First Sonnet failure: re-dispatch once more on Sonnet with the failure details; the second Sonnet failure escalates to Opus.
Each re-dispatch is logged with `mcp__jev__log_dispatch` (§5.6).
<!-- pstack-picks -->
Before each climb (Haiku → Sonnet, Sonnet → Opus, Opus → Fable), run superpowers:systematic-debugging with `{{CD}}/pstack/principles/fix-root-causes.md` on the failing reports. Read only; do not edit project files. If the root cause is a plan defect (scope too narrow, Done vague or wrong, missing context), fix that task section in `.orchestrate/PLAN.md` and re-dispatch on the same model: that is not a climb and the failure count stays. Do this at most once per model; a second failure on that model climbs. Otherwise climb, and put the root cause in the re-dispatch prompt and in the `log_escalation` reason.
<!-- /pstack-picks -->
1. A Haiku executor that fails done-criteria `escalation.haiku_failures_before_sonnet` times (1), or reports CONFIDENCE below `escalation.executor_confidence_below`, is re-dispatched with no `model` (Sonnet). Call `mcp__jev__log_escalation` first (from haiku, to sonnet, with the reason). From there the Sonnet rules below apply, starting at zero Sonnet failures.
<!-- pstack-picks -->
   A plan-defect re-run on Haiku after the root-cause step above is not a climb; it is the one same-model re-run, like any tier.
<!-- /pstack-picks -->
2. A Sonnet executor that fails done-criteria `escalation.sonnet_failures_before_opus` times (2), or reports CONFIDENCE below `escalation.executor_confidence_below`, is re-dispatched with `model: opus`. Call `mcp__jev__log_escalation` first (from sonnet, to opus, with the reason).
3. If the Opus executor succeeds, stop: no Fable.
4. Only if the Opus executor fails `escalation.opus_failures_before_fable` times (1), or reports CONFIDENCE below the threshold, re-dispatch once with `model: fable`, after `mcp__jev__log_escalation` (from opus, to fable, reason naming what Opus could not resolve). If Fable is unavailable, stop and report to the user.
5. A Fable failure comes to the user with every tier's report.

<!-- pstack-picks -->
## 7b. Interrogate (gated), then cleanup
Start only after every build task has left `.orchestrate/active.json`.

1. One `mcp__jev__jev_judge` call:
```json
{"state": {"design_summary": "...", "diff_stat": "...", "files_touched": [], "contested": false},
 "questions": {
  "needs_interrogate": {"type": "noul", "instructions": "Does the change described in `design_summary` and `diff_stat` restructure how components fit together, change an interface other modules depend on, or carry `contested: true`?",
                        "criteria": {"true": "Architectural or contested change", "false": "Contained change with no shared-interface impact"}}}}
```
2. Run `{{CD}}/skills/interrogate/SKILL.md` (read it and follow it) when Jev says true at confidence ≥ `interrogate.min_confidence`, when the user asked, or when the approved design marked the change contested. Below threshold, escalated or Jev unavailable: you decide; call `mcp__jev__log_override` when you differ. Reviewer A runs on the executor's default (Sonnet), reviewer B with `model: opus`. Never put the top rung on the panel. Act On findings become new tasks (§3-§6).
3. Cleanup: unless the diff touches documentation only, add one task with Scope = the files in the diff, `Failing test first: none (cleanup)`, and Done = `follow {{CD}}/pstack/cleanup.md; behavior unchanged; <project test command> passes`. Dispatch it on Sonnet (no `model`) with `active.json`, like any task otherwise.

<!-- /pstack-picks -->
## 8. Finish
Delete `.orchestrate/active.json`. Run `/wreview` on the worktree diff, then superpowers:verification-before-completion, then `/commit`. Merge only after review and verification pass: merge the worktree branch locally into the base branch (git merge --no-ff), never push; then call `mcp__jev__log_merge` with task and branch (the worktree branch name), tasks_merged (the number of task sections in .orchestrate/PLAN.md) and cost_usd when you have the session cost from /cost or a cost notice; then remove the worktree.

## Question rules (typesafe skill)
One narrow judgment per question; named JSON fields in state; every choice has `none_of_these`; batch independent questions into one call; never ask Jev to write code or plans. When one call covers several tasks, name each question `<question>.<task>` (for example `needs_opus.t3`); /tune groups calls by the part before the dot.
