# Execution model

**Purpose:** turn an approved design into small, verifiable tasks done by cheap agents that cannot collide.

## Roles

| Role | Does | Never does |
| --- | --- | --- |
| **Orchestrator** | Brainstorms, plans, dispatches, integrates, decides when the judge is unsure | Edits project files itself on multi-step work |
| **Executor** | Does exactly one task section, test first, inside its scope | Edits its plan, commits, pushes, merges, spawns agents |
| **Tester** | An executor that writes the failing test and stops | Writes the fix |

## Rules

1. **Plan as a file.** The plan lives in the worktree (not in chat), one section per task:
   ```
   ## Task N: <title>
   Goal: ...
   Scope:
   - <glob>
   Done:
   - <criterion incl. test command>
   Failing test first: <file :: test>
   ```
   The plan file is scratch: never committed.
2. **Worktree per loop.** Multi-step work runs in its own git worktree and branch.
3. **Need-to-know dispatch.** Each executor gets only its own task section and the worktree path, never the whole plan.
4. **Test first.** If no failing test exists, a tester goes first; the coder runs only after that test fails for the right reason.
5. **Parallel when independent.** Tasks with non-overlapping scopes may run in parallel.
6. **Cheapest capable executor.** Executors start on the cheap tier (see [escalation-model.md](escalation-model.md)).
7. **Minimal change.** No refactors, renames or extras outside the goal. Remove code the change makes dead.
8. **Fixed report.** Every executor ends with:
   ```
   CHANGED: <file list>
   TESTS: <commands run> -> <pass/fail counts>
   DONE-CRITERIA: <each criterion: met|not met>
   CONFIDENCE: <0.0-1.0>
   UNRESOLVED: <anything open, or none>
   ```
9. **Summaries up, detail on exception.** Routine returns become one line for the orchestrator. Only failures, incidents and escalations reach it in full.

## Executor principles

- **Fix root causes.** Reproduce first; never add a guard that only silences a symptom.
- **Prove it works.** Check the real artifact, not a proxy.
- **Test behavior.** Assert the required result through the public interface.
- **Subtract before you add.** No speculative options or guards.

## Specialist rules

Work in a specialist domain carries its own required skills. In the reference implementation, any design work (UI, UX, layout, visual style, on-screen copy) uses both design skills while designing and again as a review pass.

## Reference binding

`/orchestrate` (skill), the `executor` agent (`model: sonnet`), Superpowers worktrees and TDD, `planfile.py` for section extraction, Ruflo hierarchical swarm for parallel dispatch. Details: [workflow.md §4](workflow.md).
