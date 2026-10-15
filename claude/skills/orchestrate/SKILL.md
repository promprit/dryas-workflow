---
name: orchestrate
description: Run a multi-step coding task as strong-tier orchestrator with fast-first executors (standard, strong, frontier on escalation), Jev routing/gates, Dryas memory and the Dryas process skills. Use when the user runs /orchestrate, asks to orchestrate or dispatch executors, or has approved a multi-step plan to execute. Not for single-file fixes or ordinary edits that do not ask for orchestration.
allowed-tools: Read, Edit, Write, Glob, Grep, Agent, ToolSearch, Skill(dryas:brainstorm), Skill(dryas:worktree), Skill(dryas:debug), Skill(dryas:verify), Skill(dryas:review-request), Skill(dryas:review-receive), Bash(git worktree:*), Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git branch:*), Bash(git merge:*), Bash(git merge-base:*), Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/planfile.py" section:*), Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/task_review.py" answer:*), mcp__plugin_dryas_jev__jev_judge, mcp__plugin_dryas_jev__log_override, mcp__plugin_dryas_jev__log_escalation, mcp__plugin_dryas_jev__log_dispatch, mcp__plugin_dryas_jev__log_merge, mcp__plugin_dryas_jev__log_review, mcp__plugin_dryas_jev__memory_search, mcp__plugin_dryas_jev__memory_store, mcp__plugin_dryas_jev__swarm_init, mcp__plugin_ruflo-core_ruflo__memory_search, mcp__plugin_ruflo-core_ruflo__memory_store, mcp__plugin_ruflo-core_ruflo__swarm_init, Bash(git add:*), Bash(git commit:*), Bash(grep:*), Read(~/.dryas/jev/thresholds.json), Bash(git rev-parse:*), Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/scope_audit.py":*), Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/preflight.py":*), Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/run_report.py":*), PushNotification
disable-model-invocation: true
---

# Orchestrate

Dryas MCP tools may be deferred — load them with ToolSearch (e.g. `select:mcp__plugin_dryas_jev__memory_search`) before first use.

## 0. Brainstorm first (always)
Unless the request points at an already-approved design/spec, invoke dryas:brainstorm first and finish its gates (design approved by the user) before step 1. Orchestration plans from the approved design, never from the raw request.

You (the strong tier) plan, dispatch, judge and integrate. You never edit project files yourself on a multi-step task. Jev answers narrow questions; you decide whenever Jev is below threshold, escalates, or is unavailable. Thresholds: `~/.dryas/jev/thresholds.json` (defaults in `${CLAUDE_PLUGIN_ROOT}/jev/thresholds.py`). Ruflo tool names: `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/ruflo-tools.md`. Exact Jev call shapes and question rules: `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/jev-questions.md`.

<!-- pstack-picks -->
Keep bulk output in executors and only summaries here (`${CLAUDE_PLUGIN_ROOT}/pstack/principles/guard-the-context-window.md`). Judge each report against the real artifact, not the self-report (`${CLAUDE_PLUGIN_ROOT}/pstack/principles/prove-it-works.md`).

<!-- /pstack-picks -->
**The user decides in brainstorm and plan; from step 1b on, nobody is asked.** Hooks never prompt during a run: they allow, or deny with a reason the executor can act on. You decide what an executor reports as `NEEDS DECISION`; only what you must not decide alone becomes a `NEEDS USER` item in the end report.

## 1. Memory first
Search Dryas memory (mcp__plugin_dryas_jev__memory_search, namespace = main repo folder name; with the Ruflo extra selected as the memory provider, use the tools in ruflo-tools.md instead) for tasks similar to the request. Take the top 3 outcomes and write them down as `Past: <what worked> / <what failed>` before planning. None found → say so.

## 1b. Preflight: the run must not need the user
Run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/preflight.py"` once, before the first `active.json`. It prints `{"ok", "mode", "now", "say"}`. Not ok: do not start; tell the user `say` word for word (it is written for someone who does not code) and stop. Ok: keep `now` as the run start for §8; if `say` is not empty, pass it on in one line; then tell the user in one plain line that the run has started and they can leave.

## 2. Plan as a file
1. Create a worktree with dryas:worktree. One agent per worktree: this session owns it alone. Never reuse a worktree another session is working in; parallel loops on the same project each get their own worktree and branch.
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

   If the plan has a `## Risky actions` section, copy it verbatim to the top of `.orchestrate/PLAN.md`, above the first task. The gate reads it there: during the run those commands are allowed without asking anyone (an exact entry, or a prefix ending in `*`).
<!-- pstack-picks -->
   When the approved design is performance work, every task that produces or reports a measured number gets the Done line: `numbers vetted per ${CLAUDE_PLUGIN_ROOT}/pstack/benchmark-checklist.md (verdict, run count, range, limiter)`.
<!-- /pstack-picks -->
3. `.orchestrate/` is ignored globally (~/.config/git/ignore); never commit it.

## 3. Per-task Jev call (one call per task; batch when >5 tasks to triage)
`mcp__plugin_dryas_jev__jev_judge` with state `{task_section, test_file_exists: bool, last_test_run_tail, past_outcomes}` and questions:
- `executor` choice: `{coder, tester, reviewer, docs, none_of_these}`
- `specific` noul: "Is this task specific enough for an executor to finish without asking questions?"
- `failing_test_exists` noul: "Does a failing test for this task already exist?"
- `needs_opus` noul: "Does this task need a model stronger than Sonnet (cross-cutting refactor, or concurrency- or security-sensitive code)?"
- `needs_sonnet` noul (only when `dispatch.haiku_default` is true): "Does this task need a model stronger than Haiku (touches more than one file, non-mechanical logic, or test design beyond a single assertion)?"

Exact call shape: `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/jev-questions.md` (omit `needs_sonnet` when `dispatch.haiku_default` is false).

Run tests with paths relative to the worktree when possible; if the project's venv lives only in the main checkout, use its absolute path.

Any name in `escalate`, or Jev unavailable → you decide that item. Whenever your decision differs from Jev's answer, call `mcp__plugin_dryas_jev__log_override`.

## 4. TDD gate
If `failing_test_exists` is not confidently true: dispatch a **tester** executor first for that task, confirm the test fails for the right reason, then dispatch the coder.
<!-- pstack-picks -->
Review and cleanup tasks (`Failing test first: none (review)` or `none (cleanup)`) skip this gate and the §3 Jev call; their executor role is fixed (reviewer or coder).
<!-- /pstack-picks -->

## 5. Dispatch
1. Open the task ledger once (mcp__plugin_dryas_jev__swarm_init with topology "hierarchical"); the log_dispatch record stays the ledger of record.
2. Write `.orchestrate/active.json` = `{"active": [<task ids being dispatched now>], "base": {"<N>": "<sha>"}}`, where the sha is `git rev-parse HEAD` taken just before that task's first dispatch (kept for re-dispatches; §5.6 `git diff --numstat <base>..HEAD` and §6 read it from here), before dispatching; this arms the scope lock. On EVERY exit path — success, failure handed to the user (§7.3/§7.4), user abort, or any error — delete `.orchestrate/active.json` before stopping; the scope lock stays armed while it exists.
3. Give each executor ONLY its section: `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/planfile.py" section .orchestrate/PLAN.md <N>` plus the plan's Global Constraints section, when the plan document has one, plus the absolute worktree path. Never the whole plan. The dispatch prompt allows the executor to commit its own task: explicit paths, a conventional message whose subject ends with `(task <N>)`, and the report ends with `COMMITS: <sha>...` or `COMMITS: none`; never push, merge or create worktrees. Name the test-first and debugging skills in the prompt: `${CLAUDE_PLUGIN_ROOT}/skills/tdd/SKILL.md` and `${CLAUDE_PLUGIN_ROOT}/skills/debug/SKILL.md` (executors read them; they have no Skill tool).
4. Dispatch with the Agent tool, `subagent_type: dryas:executor`. Pick the start tier per task, first match wins:
   1. `needs_opus` true at confidence ≥ threshold, or your own judgment → `model: opus`, after `mcp__plugin_dryas_jev__log_escalation` (from_model sonnet, to_model opus, reason "skip-up: <why>", whatever `dispatch.haiku_default` says, so ESC-M1 counts it the same way as before the fast tier; the skip-up reason tells observers it is a start tier, not a climb).
   2. `dispatch.haiku_default` false → no `model` (standard tier from the agent's frontmatter). Do not ask `needs_sonnet`.
   3. `needs_sonnet` true at confidence ≥ threshold, or your own judgment → no `model` (standard tier), after `mcp__plugin_dryas_jev__log_escalation` (from_model haiku, to_model sonnet, reason "skip-up: <why>").
   4. Otherwise → `model: haiku`.
   Independent tasks go out in one message, in parallel. Never dispatch the frontier tier here: it is only reached through §7. Review, interrogate and cleanup dispatches (§7b) never use the fast tier: they start on the standard tier (no `model`) and log no skip-up.
5. Every `log_dispatch` and `log_escalation` call for a task uses the same task id: "<worktree branch>:<PLAN.md task id>", e.g. worktree-feat:3. `/tune` joins the two logs on it.
6. Right after every dispatch (first or re-dispatch, any tier) call `mcp__plugin_dryas_jev__log_dispatch` with task (the §5.5 id), tier (haiku, sonnet, opus or fable), role (coder, tester, reviewer or docs), attempt (1 for the first dispatch of that task, then +1 per re-dispatch), and the score, score_tier and task_type of the §5.7 answer. When it returns, call log_dispatch again with the same task, tier, role and attempt, phase "return", tokens and duration_ms from the Agent result's usage (total tokens, duration in ms) and agent_id (the Agent result's agent id), leaving out what the result does not have. Also pass `lines` = added + deleted lines of the task's commit (`git diff --numstat <base>..HEAD`) in that return record.
7. Task review (owned core A2). Before writing `.orchestrate/active.json` (§5.2), run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/task_review.py" answer .orchestrate/PLAN.md <N>` for each task being dispatched, and write the file as `{"active": [<ids>], "review_version": 1, "review": {"<N>": <that task's "entry">}}`. Only you write it; the scope lock denies executors `.orchestrate/`. The gate logs the task verdict next to every judged edit and judges every edit until `review.task_skip` is on; files outside the entry, always-judged files and edits with risky content stay judged even then. The start tier stays §5.4 unless `dispatch.scored_tier` is true: then start on the entry's `tier` (`haiku` → `model: haiku`; `sonnet` → no `model`, after the haiku→sonnet skip-up `log_escalation`; `opus` → `model: opus`, after the sonnet→opus skip-up). Both switches are flipped only with `/tune apply` after `/tune` proposes them.

## 6. On return
For each report, first run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/scope_audit.py" .orchestrate/PLAN.md <N> --base <base of N> <COMMITS shas>` in the worktree. `ok: false` means the task is not done: first add the exact revert commands to `.orchestrate/approved.json` (`git checkout -- <path>` for each tracked file in `outside`; the gate denies discards during a run unless approved), then re-dispatch it on the same model with "revert these files: <outside> (run exactly `git checkout -- <path>` if tracked, delete the file if new), then make the change with Edit/Write inside your Scope". That re-run is not a climb; a second audit failure on the task counts as a failure (§7). Then one `jev_judge` call with state `{task_section, executor_report}`:
- `done` noul: "Are all done-criteria met according to the report?"
- `risk` score: `["routine", "worth a look", "incident"]`

Only an incident, a failure or an escalation reaches you in full; otherwise log one summary line per task. Remove a task id from `active.json` only when that task is finished or handed to the user; a task being re-dispatched stays active. If an executor reports `SCOPE: need <path> because <reason>`, you (main thread) decide; if justified, add the glob to that task's Scope in .orchestrate/PLAN.md (the scope lock lets only the main thread edit .orchestrate/PLAN.md), then re-dispatch.

`NEEDS DECISION: <command> because <reason>` means the gate denied a risky command during the run, and nobody is asked: you decide. Approve only when the command is needed for the task, stays inside the worktree, and can be undone or only touches generated or test data. To approve, add `{"cmd": "<exact command>", "task": "<N>", "reason": "<one line>"}` to `.orchestrate/approved.json` (`{"commands": [...]}`; create it if missing), call `mcp__plugin_dryas_jev__log_override` (question "run_ask", Jev "ask", yours "allow", the reason), and re-dispatch. Otherwise re-dispatch with a safer way, or make it a `NEEDS USER` item: the task stays not done, its id leaves `active.json`, and the run carries on with the other tasks. Your own risky commands follow the same rule. The gate never lets approved.json cover a push, a deploy or cloud command, or a delete outside the worktree: only an exact entry in the plan's Risky actions can.

Store the outcome (mcp__plugin_dryas_jev__memory_store, kind outcome, with task_id and the commit): task title, what worked, what failed.

## 7. Escalation
Ladder: **fast → standard → strong → frontier**. The frontier tier is used only when the strong tier also could not do the task.
Every `mcp__plugin_dryas_jev__log_escalation` call passes all five fields: task, reason, decided_by ("jev" or "opus"), from_model, to_model.
First standard-tier failure: re-dispatch once more on standard with the failure details; the second standard failure escalates to strong.
Each re-dispatch is logged with `mcp__plugin_dryas_jev__log_dispatch` (§5.6).
<!-- pstack-picks -->
Before each climb (fast → standard, standard → strong, strong → frontier), run dryas:debug with `${CLAUDE_PLUGIN_ROOT}/pstack/principles/fix-root-causes.md` on the failing reports. Read only; do not edit project files. If the root cause is a plan defect (scope too narrow, Done vague or wrong, missing context), fix that task section in `.orchestrate/PLAN.md` and re-dispatch on the same model: that is not a climb and the failure count stays. Do this at most once per model; a second failure on that model climbs. Otherwise climb, and put the root cause in the re-dispatch prompt and in the `log_escalation` reason.
<!-- /pstack-picks -->
1. A fast-tier executor that fails done-criteria `escalation.haiku_failures_before_sonnet` times (1), or reports CONFIDENCE below `escalation.executor_confidence_below`, is re-dispatched with no `model` (standard tier). Call `mcp__plugin_dryas_jev__log_escalation` first (from haiku, to sonnet, with the reason). From there the standard-tier rules below apply, starting at zero standard failures.
<!-- pstack-picks -->
   A plan-defect re-run on the fast tier after the root-cause step above is not a climb; it is the one same-model re-run, like any tier.
<!-- /pstack-picks -->
2. A standard-tier executor that fails done-criteria `escalation.sonnet_failures_before_opus` times (2), or reports CONFIDENCE below `escalation.executor_confidence_below`, is re-dispatched with `model: opus`. Call `mcp__plugin_dryas_jev__log_escalation` first (from sonnet, to opus, with the reason).
3. If the strong executor succeeds, stop: no frontier.
4. Only if the strong executor fails `escalation.opus_failures_before_fable` times (1), or reports CONFIDENCE below the threshold, re-dispatch once with `model: fable`, after `mcp__plugin_dryas_jev__log_escalation` (from opus, to fable, reason naming what the strong tier could not resolve). If the frontier tier is unavailable, stop and report to the user.
5. A frontier failure comes to the user with every tier's report.

<!-- pstack-picks -->
## 7b. Interrogate (gated), then cleanup
Start only after every build task has left `.orchestrate/active.json`.

1. One `mcp__plugin_dryas_jev__jev_judge` call with state `{design_summary, diff_stat, files_touched, contested}` and the noul question "needs_interrogate": "Does the change described in `design_summary` and `diff_stat` restructure how components fit together, change an interface other modules depend on, or carry `contested: true`?" (exact shape in jev-questions.md).
2. Run `${CLAUDE_PLUGIN_ROOT}/skills/interrogate/SKILL.md` (read it and follow it) when Jev says true at confidence ≥ `interrogate.min_confidence`, when the user asked, or when the approved design marked the change contested. Below threshold, escalated or Jev unavailable: you decide; call `mcp__plugin_dryas_jev__log_override` when you differ. Reviewer A runs on the executor's default (standard tier), reviewer B with `model: opus`. Never put the top rung on the panel. Act On findings become new tasks (§3-§6).
3. Cleanup: unless the diff touches documentation only, add one task with Scope = the files in the diff, `Failing test first: none (cleanup)`, and Done = `follow ${CLAUDE_PLUGIN_ROOT}/pstack/cleanup.md; behavior unchanged; <project test command> passes`. Dispatch it on the standard tier (no `model`) with `active.json`, like any task otherwise.

<!-- /pstack-picks -->
## 8. Finish
If every task left is `NEEDS USER` or blocked, skip review and merge: go straight to the report below. Delete `.orchestrate/active.json`. Review the worktree diff with the `dryas:review-request` skill (three-stage, reports kept separate) and handle findings with `dryas:review-receive`; after each review round call `mcp__plugin_dryas_jev__log_review` (task = the worktree branch, round, counts of critical, important and minor findings). Then run `dryas:verify`. Then commit by reading `${CLAUDE_PLUGIN_ROOT}/commands/commit.md` and following its Jev-gated steps (the same pattern as interrogate in §7b). Merge only after review and verification pass: merge the worktree branch locally into the base branch (git merge --no-ff), never push; then call `mcp__plugin_dryas_jev__log_merge` with task and branch (the worktree branch name), tasks_merged (the number of task sections in .orchestrate/PLAN.md) and cost_usd when you have the session cost from /cost or a cost notice; if `log_merge` replies with a warning (no review recorded for the branch), tell the user; then remove the worktree.

**Report, once.** Run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/run_report.py" <worktree> <run start from §1b>`. Write the report in plain words first, for someone who does not code: how many parts are done; each part not done and why; each `NEEDS USER` item as a question with your recommended answer. Then a `Details` heading: the counts (`prompts` should be 0), commits, branch, files. Store one `memory_store` lesson (kind outcome) per recurring cause you saw, for example "executors edited files through inline code N times" (the `inline_code` count) or "the plan missed the risky action X"; put proposals (a Risky actions default, a new detector case) in the report, never apply them. Then send one PushNotification (load it with ToolSearch `select:PushNotification`) with one plain sentence: done, or stopped and why.

## Question rules
Full rules in `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/jev-questions.md`: one narrow judgment per question, named JSON fields in state, every choice has `none_of_these`, batch independent questions into one call. When one call covers several tasks, name each question `<question>.<task>` (for example `needs_opus.t3`); /tune groups calls by the part before the dot.
