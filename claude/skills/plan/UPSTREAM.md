# Upstream coverage: plan

Rows follow the grammar in [../UPSTREAM.md](../UPSTREAM.md).

## plan

Upstream: `writing-plans/`

| Upstream item | Where it lives |
|---|---|
| Writing Plans | plan/SKILL.md § Plan |
| Overview | plan/SKILL.md § Overview |
| Overview — zero context, document everything, bite-sized tasks | plan/SKILL.md § Overview |
| Overview — DRY, YAGNI, TDD, frequent commits | plan/SKILL.md § Overview |
| Overview — skilled developer, new to the toolset and domain, weak on test design | plan/SKILL.md § Overview |
| Overview — Announce at start | plan/SKILL.md § Overview |
| Overview — Context: worktree created at execution time | plan/SKILL.md § Overview; orchestrate: "Create a worktree" |
| Overview — Save plans to | plan/SKILL.md § Hand-off |
| Overview — user preferences override the plan location | plan/SKILL.md § Overview |
| Scope Check | plan/SKILL.md § Scope check |
| Scope Check — one plan per independent subsystem, each working and testable | plan/SKILL.md § Scope check |
| File Structure | plan/SKILL.md § File structure |
| File Structure — map files and responsibilities before tasks | plan/SKILL.md § File structure |
| File Structure — clear boundaries, one responsibility per file | plan/SKILL.md § File structure |
| File Structure — prefer smaller, focused files | plan/SKILL.md § File structure |
| File Structure — files that change together live together | plan/SKILL.md § File structure |
| File Structure — follow established patterns; split an unwieldy file you modify | plan/SKILL.md § File structure |
| File Structure — structure informs decomposition; self-contained tasks | plan/SKILL.md § File structure |
| Task Right-Sizing | plan/SKILL.md § Task right-sizing |
| Task Right-Sizing — fold setup into the task that needs it; split where a reviewer could reject one | plan/SKILL.md § Task right-sizing |
| Task Right-Sizing — each task ends with an independently testable deliverable | plan/SKILL.md § Task right-sizing |
| Bite-Sized Task Granularity | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — one action per step, 2-5 minutes | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — write the failing test | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — run it to make sure it fails | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — implement the minimal code | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — run the tests, make sure they pass | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — commit | plan/SKILL.md § Bite-sized steps |
| Plan Document Header | plan/SKILL.md § Plan header |
| Plan Document Header — every plan MUST start with the header | plan/SKILL.md § Plan header |
| Plan Document Header — For agentic workers line | plan/SKILL.md § Plan header |
| Plan Document Header — Goal, Architecture, Tech Stack | plan/SKILL.md § Plan header |
| Plan Document Header — Spec path; the spec travels with the plan | plan/SKILL.md § Plan header |
| Plan Document Header — Global Constraints section | plan/SKILL.md § Global constraints |
| Plan Document Header — Review Focus section | plan/SKILL.md § Review focus |
| Plan Document Header — Review Focus: silence in the spec is not permission to break | plan/SKILL.md § Review focus |
| Plan Document Header — Review Focus: pin each line with a test in the owning task | plan/SKILL.md § Review focus |
| Task Structure | plan/SKILL.md § Task format |
| Task Structure — Files: create, modify with line ranges, test | plan/SKILL.md § Task format |
| Task Structure — Interfaces: Consumes and Produces | plan/SKILL.md § Task format |
| Task Structure — Step 1 write the failing test (code) | plan/SKILL.md § Task format |
| Task Structure — Step 2 run test to verify it fails | plan/SKILL.md § Task format |
| Task Structure — Step 3 write minimal implementation | plan/SKILL.md § Task format |
| Task Structure — Step 4 run test to verify it passes | plan/SKILL.md § Task format |
| Task Structure — Step 5 commit | plan/SKILL.md § Task format |
| No Placeholders | plan/SKILL.md § No placeholders |
| No Placeholders — "TBD", "TODO", "implement later", "fill in details" | plan/SKILL.md § No placeholders |
| No Placeholders — "Add appropriate error handling" / validation / edge cases | plan/SKILL.md § No placeholders |
| No Placeholders — "Write tests for the above" | plan/SKILL.md § No placeholders |
| No Placeholders — "Similar to Task N" | plan/SKILL.md § No placeholders |
| No Placeholders — steps without how; code blocks required | plan/SKILL.md § No placeholders |
| No Placeholders — references to undefined types or functions | plan/SKILL.md § No placeholders |
| Self-Review | plan/SKILL.md § Self-review |
| Self-Review — a checklist you run yourself | plan/SKILL.md § Self-review |
| Self-Review — 1. Spec coverage | plan/SKILL.md § Self-review |
| Self-Review — 2. Placeholder scan | plan/SKILL.md § Self-review |
| Self-Review — 3. Type consistency | plan/SKILL.md § Self-review |
| Self-Review — 4. Review Focus | plan/SKILL.md § Self-review |
| Self-Review — fix inline; a requirement with no task gets a task | plan/SKILL.md § Self-review |
| Execution Handoff | plan/SKILL.md § Hand-off |
| Execution Handoff — link the plan, ask for review, wait before implementation | plan/SKILL.md § Hand-off |
| Execution Handoff — execution method already supplied: preserve it | plan/SKILL.md § Hand-off |
| Execution Handoff — no method supplied: offer Subagent-driven or Native | plan/SKILL.md § Hand-off |
| Execution Handoff — Subagent-driven: fresh executor and reviewer per task | plan/SKILL.md § Hand-off; orchestrate: "Give each executor ONLY its section" |
| Execution Handoff — Native: in-session execution | plan/SKILL.md § Hand-off |
| plan-document-reviewer-prompt.md | plan/plan-reviewer-prompt.md § Plan reviewer |
| plan-document-reviewer-prompt.md — what to check, calibration, output format | plan/plan-reviewer-prompt.md § Plan reviewer |
