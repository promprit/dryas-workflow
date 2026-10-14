---
name: orchestrate
description: Run a multi-step coding task with a plan file, scope-locked workers, Jev routing and gates, and Ruflo memory. Use when the user runs $orchestrate, asks to orchestrate or dispatch workers, or has approved a multi-step plan to execute. Not for single-file fixes or ordinary edits that do not ask for orchestration.
---

# Orchestrate (Codex)

0. **Brainstorm first.** Run `$dryas:brainstorm`; plan only from a design the user approved.
1. **Memory.** Call `memory_search` (server `ruflo`, namespace = main repo folder name) for similar tasks. Write the top 3 as `Past: <what worked> / <what failed>`, or say none were found.
2. **Plan as a file.** Create a git worktree for the work with `$dryas:worktree`. One agent per worktree: this session owns it alone; parallel loops each get their own worktree and branch. Write `.orchestrate/PLAN.md` there, one section per task:

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
5. **Dispatch.** Write `.orchestrate/active.json` = `{"active": [<task ids>]}`; this arms the scope-lock hook. Delete it on every exit path. Give each worker only its own section: `"{{PY}}" -X utf8 "{{CD}}/jev/planfile.py" section .orchestrate/PLAN.md <N>` (PowerShell: prefix `& `) plus the plan's Global Constraints section, when the plan document has one, plus the absolute worktree path. Name `{{CD}}/skills/tdd/SKILL.md` and `{{CD}}/skills/debug/SKILL.md` in its prompt. Use Codex sub-agents when available (independent tasks in parallel); otherwise do the tasks yourself, one at a time. Workers start on a cheaper model; `needs_stronger_model` or your judgment picks the stronger one, after `log_escalation`. Right after every dispatch, including retries and doing a task yourself, call `log_dispatch` (task as "<worktree branch>:<plan task id>", tier as the model name, role, attempt starting at 1).
6. **On return.** Check each Done criterion against the report. A failure is retried once on the same model, then moved to the stronger model (`log_escalation` with task, reason, decided_by, from_model, to_model). If the strongest model fails too, stop and report to the user. Store each outcome with `memory_store`.
6a. **Task review and usage (for step 5).** Before writing `.orchestrate/active.json`, run `"{{PY}}" -X utf8 "{{CD}}/jev/task_review.py" answer .orchestrate/PLAN.md <N>` for each task; write the file as `{"active": [<ids>], "review_version": 1, "review": {"<N>": <that task's "entry">}}` (only you write it; Codex workers carry no worker identity, so the scope lock cannot tell them from the main session; `review.task_skip` is never enforced for them). Keep the model choice of step 5 unless `dispatch.scored_tier` is true: then start on the entry's `tier`. Every dispatch-time `log_dispatch` of the task also passes the answer's score, score_tier and task_type. When the sub-agent returns, call `log_dispatch` again with the same task, tier, role and attempt, phase "return", plus tokens and duration_ms when it reports its usage.
7. **Finish.** Delete `.orchestrate/active.json`, review the worktree diff with `$dryas:review-request` (three-stage, reports kept separate) and handle findings with `$dryas:review-receive`; after each review round call `log_review` (task = the worktree branch, round, counts of critical, important and minor findings); then run `$dryas:verify`; then commit by reading `<dryas-root>/skills/commit/SKILL.md` and following its steps (the Claude edition reads commands/commit.md). Merge locally with `git merge --no-ff` only after review and verification; never push; call `log_merge` (task and branch = the worktree branch, tasks_merged = task sections in the plan, cost_usd if known); if it replies with a warning (no review recorded for the branch), tell the user; remove the worktree. Name the harness (Codex) and the models used in the plan and the commit body.
