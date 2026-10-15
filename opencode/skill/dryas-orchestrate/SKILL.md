---
name: dryas-orchestrate
description: "Run a multi-step coding task as the orchestrator with fast-first executors (standard, strong, frontier on escalation), Jev routing and gates, Dryas memory and the Dryas process skills. Use when the user runs /orchestrate, asks to orchestrate or dispatch executors, or has approved a multi-step plan to execute. Not for single-file fixes or ordinary edits."
---
<!-- dryas-managed -->
# Orchestrate (OpenCode)

`<dryas-root>` and `<dryas-py>` are given in the Dryas rules ("Dryas paths:"). If they are missing, the Dryas plugin did not load: tell the user to re-run `install.sh --harness opencode` and stop. Jev and memory are tools of the `jev` MCP server (`jev_jev_judge`, `jev_log_dispatch`, `jev_memory_search`, ...). Exact Jev call shapes: `<dryas-root>/../skill/dryas-orchestrate/jev-questions.md`. Thresholds: `~/.dryas/jev/thresholds.json`.

**Tiers.** Executors are the subagents `dryas-executor-fast`, `dryas-executor-standard`, `dryas-executor-strong` and `dryas-executor-frontier`; setup chose the model behind each. Logs, Jev questions and thresholds keep the slot names: fast = `haiku`, standard = `sonnet`, strong = `opus`, frontier = `fable`. Use the slot name in every `tier`, `from_model` and `to_model` field.

You plan, dispatch, judge and integrate. You never edit project files yourself on a multi-step task. Jev answers narrow questions; you decide whenever Jev is below threshold, escalates or is unavailable, and call `jev_log_override` when you differ.

<!-- pstack-picks -->
Keep bulk output in executors and only summaries here (`<dryas-root>/pstack/principles/guard-the-context-window.md`). Judge each report against the real artifact, not the self-report (`<dryas-root>/pstack/principles/prove-it-works.md`).
<!-- /pstack-picks -->

0. **Brainstorm first.** Unless the request points at an approved design, load the `dryas-brainstorm` skill and finish its gates.
1. **Memory.** `jev_memory_search` (namespace = the main repo's folder name) for similar tasks. Write the top 3 as `Past: <what worked> / <what failed>`, or say none were found.
2. **Plan as a file.** Create the worktree with the `dryas-worktree` skill; one agent per worktree. Write `.orchestrate/PLAN.md` there, one section per task:

   ```
   ## Task <N>: <title>
   Goal: <one sentence>
   Scope:
   - <glob relative to worktree root>
   Done:
   - <verifiable criterion, incl. test command>
   Failing test first: <test file :: test name>
   ```

   Tasks that may run in parallel must not have overlapping Scope. Never commit `.orchestrate/`.
<!-- pstack-picks -->
   When the approved design is performance work, a task that reports a measured number gets the Done line `numbers vetted per <dryas-root>/pstack/benchmark-checklist.md (verdict, run count, range, limiter)`.
<!-- /pstack-picks -->
3. **Ask Jev per task.** `jev_jev_judge` with state `{task_section, test_file_exists, last_test_run_tail, past_outcomes}` and questions `executor` (choice: coder, tester, reviewer, docs, none_of_these), `specific` (noul: specific enough to finish without questions?), `failing_test_exists` (noul), `needs_opus` (noul: does the task need the strong tier: cross-cutting refactor, or concurrency- or security-sensitive code?) and, only when `dispatch.haiku_default` is true, `needs_sonnet` (noul: does it need more than the fast tier: more than one file, non-mechanical logic, or test design beyond one assertion?). One call for several tasks names each question `<question>.<task>`.
4. **Test first.** If `failing_test_exists` is not confidently true, dispatch a tester first and confirm the test fails for the right reason, then the coder. Review and cleanup tasks (`Failing test first: none (review)` or `none (cleanup)`) skip this step and step 3.
5. **Dispatch.**
   1. Open the task ledger once: `jev_swarm_init` (topology "hierarchical").
   2. For each task run `"<dryas-py>" -X utf8 "<dryas-root>/jev/task_review.py" answer .orchestrate/PLAN.md <N>`, then write `.orchestrate/active.json` = `{"active": [<ids>], "review_version": 1, "review": {"<N>": <that task's "entry">}}`. This arms the scope lock, which tells each executor's subagent session apart from yours. Delete the file on every exit path.
   3. Give each executor only its section (`"<dryas-py>" -X utf8 "<dryas-root>/jev/planfile.py" section .orchestrate/PLAN.md <N>`), the plan's Global Constraints section when there is one, the absolute worktree path, leave to commit its own task (explicit paths, conventional message; never push, merge or create worktrees), and the paths `<dryas-root>/../skill/dryas-tdd/SKILL.md` and `<dryas-root>/../skill/dryas-debug/SKILL.md`.
   4. Dispatch with the task tool, `subagent_type` = `dryas-executor-<tier>`. Start tier, first match wins: `needs_opus` true at confidence ≥ threshold, or your judgment → strong, after `jev_log_escalation` (from `sonnet`, to `opus`, reason "skip-up: <why>"); `dispatch.haiku_default` false → standard; `needs_sonnet` true, or your judgment → standard, after `jev_log_escalation` (from `haiku`, to `sonnet`, reason "skip-up: <why>"); otherwise fast. With `dispatch.scored_tier` true, start on the review entry's `tier` instead. Never start on frontier. Review, interrogate and cleanup dispatches start on standard. Independent tasks go out together.
   5. Right after every dispatch call `jev_log_dispatch` (task "<worktree branch>:<N>", tier as the slot name, role, attempt from 1, and the review entry's score, score_tier and task_type). When it returns, call it again with phase "return", tokens and duration_ms when known, and `lines` from `git diff --numstat <base>..HEAD`.
6. **On return.** `jev_jev_judge` with state `{task_section, executor_report}`: `done` (noul: all done-criteria met?) and `risk` (score: routine, worth a look, incident). Remove a task id from `active.json` only when it is finished or handed to the user. On `SCOPE: need <path> because <reason>` you decide; if justified, add the glob to that task's Scope in `.orchestrate/PLAN.md` and re-dispatch. Store the outcome with `jev_memory_store` (kind outcome, task_id, commit).
7. **Escalation.** fast → standard → strong → frontier; frontier only after strong fails. Every climb calls `jev_log_escalation` first with task, reason, decided_by, from_model and to_model; every re-dispatch calls `jev_log_dispatch`. Fast fails `escalation.haiku_failures_before_sonnet` times, or reports CONFIDENCE below `escalation.executor_confidence_below` → standard. Standard fails `escalation.sonnet_failures_before_opus` times → strong. Strong fails `escalation.opus_failures_before_fable` times → frontier, once. Frontier fails → the user, with every tier's report.
<!-- pstack-picks -->
   Before each climb, run the `dryas-debug` skill with `<dryas-root>/pstack/principles/fix-root-causes.md` on the failing report (read only). A plan defect is fixed in `.orchestrate/PLAN.md` and re-run on the same tier, at most once per tier.
7b. **Interrogate, then cleanup.** After every build task has left `.orchestrate/active.json`, ask `needs_interrogate` (noul: "Does the change described in `design_summary` and `diff_stat` restructure how components fit together, change an interface other modules depend on, or carry `contested: true`?"). If true at ≥ `interrogate.min_confidence`, the user asked, or the approved design says Contested: yes, load the `dryas-interrogate` skill. Then, unless the diff is documentation only, add one cleanup task (Scope = the diff's files, `Failing test first: none (cleanup)`, Done = `follow <dryas-root>/pstack/cleanup.md; behavior unchanged; <project test command> passes`) on standard.
<!-- /pstack-picks -->
8. **Finish.** Delete `.orchestrate/active.json`. Review with the `dryas-review-request` skill and handle findings with `dryas-review-receive`; call `jev_log_review` after each round. Run `dryas-verify`. Commit by reading `<dryas-root>/../command/commit.md` and following it. Merge locally with `git merge --no-ff` only after review and verification; never push. Call `jev_log_merge` (task and branch = the worktree branch, tasks_merged, cost_usd when known) and tell the user about any warning it returns. Remove the worktree.
