---
name: orchestrate
description: Run a multi-step coding task with a plan file, scope-locked workers, Jev routing and gates, and Ruflo memory. Use for $orchestrate or any multi-file task. Not for single-file fixes.
---

# Orchestrate (Codex)

0. **Brainstorm first.** Plan only from a design the user approved.
1. **Memory.** Call `memory_search` (server `ruflo`, namespace = main repo folder name) for similar tasks. Write the top 3 as `Past: <what worked> / <what failed>`, or say none were found.
2. **Plan as a file.** Create a git worktree for the work (`git worktree add ../<repo>-<topic> -b <branch>`). One agent per worktree: this session owns it alone; parallel loops each get their own worktree and branch. Write `.orchestrate/PLAN.md` there, one section per task:

   ```
   ## Task <N>: <title>
   Goal: <one sentence>
   Scope:
   - <glob relative to worktree root>
   Done:
   - <verifiable criterion, incl. test command>
   Failing test first: <test file :: test name>
   ```

   Tasks that may run in parallel must not have overlapping scopes. Never commit `.orchestrate/`.
3. **Ask Jev per task.** Call `jev_judge` (server `jev`) with state `{task_section, test_file_exists, last_test_run_tail, past_outcomes}` and questions `specific` (noul: is the task specific enough to finish without questions?), `failing_test_exists` (noul) and `needs_stronger_model` (noul: cross-cutting refactor, concurrency- or security-sensitive code?). Each question's `instructions` must stand alone and name state fields in backticks. Below threshold or unavailable: you decide; when you differ from Jev, call `log_override`. When one call covers several tasks, name each question `<question>.<task>` (for example `needs_stronger_model.t3`); $tune groups calls by the part before the dot.
4. **Test first.** If a failing test does not confidently exist, get it written and failing for the right reason before any implementation.
5. **Dispatch.** Write `.orchestrate/active.json` = `{"active": [<task ids>]}`; this arms the scope-lock hook. Delete it on every exit path. Give each worker only its own section: `"{{PY}}" -X utf8 "{{CD}}/jev/planfile.py" section .orchestrate/PLAN.md <N>` (PowerShell: prefix `& `) plus the absolute worktree path. Use Codex sub-agents when available (independent tasks in parallel); otherwise do the tasks yourself, one at a time. Workers start on a cheaper model; `needs_stronger_model` or your judgment picks the stronger one, after `log_escalation`. After every dispatch, including retries and doing a task yourself, call `log_dispatch` (task as "<worktree branch>:<plan task id>", tier as the model name, role, attempt starting at 1).
6. **On return.** Check each Done criterion against the report. A failure is retried once on the same model, then moved to the stronger model (`log_escalation` with task, reason, decided_by, from_model, to_model). If the strongest model fails too, stop and report to the user. Store each outcome with `memory_store`.
<!-- pstack-picks -->
6b. **Root cause, review, cleanup.** Before moving a failed task to the stronger model, find the root cause (Superpowers' systematic-debugging if installed, else `{{CD}}/pstack/principles/fix-root-causes.md`); a plan defect is fixed in the plan and retried on the same model (at most once per model; after that, move up). Start the next part only after every build task has left `.orchestrate/active.json`. Ask Jev `needs_interrogate` (noul: "Does the change described in `design_summary` and `diff_stat` restructure how components fit together, change an interface other modules depend on, or carry `contested: true`?"); if true at ≥ `interrogate.min_confidence`, the user asked, or the approved design marked the change contested, run `$interrogate`. Then, unless the diff is documentation only, run one cleanup task on the diff's files following `{{CD}}/pstack/cleanup.md`, tests rerun, before `$wreview`. Review and cleanup tasks (`Failing test first: none (review)` or `none (cleanup)`) skip the test-first step (item 4). When the approved design is performance work, tasks that report a measured number get the Done line `numbers vetted per {{CD}}/pstack/benchmark-checklist.md`. When you give a worker its section, include the four principle lines from `{{CD}}/pstack/principles/` (fix root causes, prove it works, test behavior, subtract before you add) in its prompt.
<!-- /pstack-picks -->
7. **Finish.** Delete `.orchestrate/active.json`, run `$wreview`, verify (run the tests and read the output), then `$commit`. Merge locally with `git merge --no-ff` only after review and verification; never push; call `log_merge` (task and branch = the worktree branch, tasks_merged = task sections in the plan, cost_usd if known); remove the worktree. Name the harness (Codex) and the models used in the plan and the commit body.
