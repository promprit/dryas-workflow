# Memory model

**Purpose:** carry outcomes across sessions so the same mistake is not paid for twice.

## Rules

1. **One memory layer.** There is exactly one place where learned outcomes live. Harness memory, plugin memory and ad-hoc notes do not compete with it. Two memories drift; one memory can be trusted.
2. **Namespaced per project.** Memory is keyed by the main repository (not the worktree), so parallel loops on one project share what they learn and different projects never leak into each other.
3. **Read before planning.** Before a plan is written, the orchestrator searches memory for the task and writes down the top past outcomes: what worked, what failed.
4. **Write after each task.** When a task returns, its outcome (goal, result, escalations, root cause if it failed) is stored.
5. **Outcomes, not transcripts.** Memory stores short, decision-relevant records. Code, secrets and full logs never go in.
6. **Memory degrades silently.** If memory is unavailable, the loop still runs; it just plans without history. A missing memory never blocks work.

## Session memory is separate

Dryas also manages the *context window* of a single session, which is a different problem:

- **Handoff before clear.** Near the context limit, the session saves the items worth keeping (recent user messages, files touched, latest test results, commits, and judge-scored excerpts), clears, and restores them.
- **Compaction safety net.** If the harness compacts on its own, the same keep/drop selection is re-injected after the compaction summary.

Session memory is short-lived (minutes to hours, one project). Project memory is long-lived (the life of the repo).

## What to store

| Store | Do not store |
| --- | --- |
| Task goal and outcome (passed, failed, escalated) | File contents or diffs |
| Which model finally solved it, and why lower rungs failed | API keys, tokens, credentials |
| Root causes found | Full transcripts |
| Approaches rejected during brainstorm, and why | Personal data |

## Reference binding

Ruflo is the memory layer: `memory_search` before planning, `memory_store` after each task, namespace = main repo folder name, data under `$DRYAS_DATA_ROOT/ruflo`. Session memory is Dryas's own `/handoff` and compaction hooks. Details: [workflow.md §6–7](workflow.md).
