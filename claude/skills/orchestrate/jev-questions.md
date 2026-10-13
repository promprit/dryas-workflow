# Jev question shapes (consumed by the orchestrate skill)

Reference for the `mcp__plugin_dryas_jev__jev_judge` calls the orchestrate skill makes. The operative steps are in `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/SKILL.md`; this file holds the exact call shapes and the question rules.

## Question rules (typesafe skill)
One narrow judgment per question; named JSON fields in state; every choice has `none_of_these`; batch independent questions into one call; never ask Jev to write code or plans. When one call covers several tasks, name each question `<question>.<task>` (for example `needs_opus.t3`); /tune groups calls by the part before the dot.

Question names are never sent to Jev, so each `instructions` must be self-contained and reference state by backticked field names.

## Per-task call (SKILL.md §3)
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

## On-return call (SKILL.md §6)
State `{task_section, executor_report}`; questions `done` (noul) and `risk` (score). `risk` is a score question whose criteria is the list ["routine", "worth a look", "incident"].

## Interrogate gate (SKILL.md §7b)
```json
{"state": {"design_summary": "...", "diff_stat": "...", "files_touched": [], "contested": false},
 "questions": {
  "needs_interrogate": {"type": "noul", "instructions": "Does the change described in `design_summary` and `diff_stat` restructure how components fit together, change an interface other modules depend on, or carry `contested: true`?",
                        "criteria": {"true": "Architectural or contested change", "false": "Contained change with no shared-interface impact"}}}}
```
