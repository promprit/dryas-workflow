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

## Dryas memory

The reference implementation's memory layer is Dryas's own (`memory: dryas`, the default). Ruflo memory stays available as the `--memory ruflo` provider, and `--memory none` turns memory off.

- **Store.** One SQLite file in WAL mode, `~/.dryas/dryas.db` (`DRYAS_DB` or `DRYAS_DATA_ROOT` moves it), stdlib `sqlite3`. Tables: `memory` (the records), `edits`, `tasks`, `sessions`, `patterns`, `access`, `forgotten` and `kv`. A newer database than this Dryas opens read-only.
- **Search.** FTS5 when this SQLite build has it, a LIKE fallback otherwise (MEM-5: writes keep working either way, and the index is rebuilt when FTS5 returns). Results come with a reason string. Ranking: the share of query terms matched, then the PageRank of the memory graph and how often a memory was used. Learned patterns whose key mentions a query term come back with the results.
- **Namespaces.** The main repo folder name, the same rule as Ruflo's, so both agree.
- **Writes.** `memory_store` takes kinds `outcome`, `fact` and `retro`. MEM-4 checks refuse a secret-shaped value, over-long text and file contents. The tools on the `jev` MCP server are `memory_search`, `memory_store`, `memory_list`, `memory_forget` and `swarm_init`.
- **Archive.** Imported hook noise is kept as kind `archive`; search skips it unless the call passes `include_archive`.
- **Hooks fill it** (observe-only, Claude Code): `mem-edit`, `mem-task`, `mem-session-start`, `mem-session-end`; see [workflow.md §5](workflow.md). Codex has no memory hooks and uses the tools only.
- **Consolidation** (dedupe, the memory graph, PageRank, learned patterns) runs at session end inside the hook while its stage budget allows (2 s per stage; an event may run two stages). When it would overrun, the namespace is marked pending and a detached `dryas memory consolidate` (run it as `<plugin root>/bin/dryas memory consolidate`) finishes it outside the hook budget. A lock file beside the store keeps runs from overlapping (a second run exits at once, and a stale lock is taken over), and the next session start retries a pending marker. `/tune` reports the skipped and background runs, and the session-start rules add a warning line after repeated skips with no finished background run.
- **Migration.** `dryas memory import-ruflo` reads a Ruflo memory read-only into the store. It is idempotent, exits non-zero if a source row is missing afterwards, and leaves `~/.dryas/ruflo` in place. `dryas memory stats` counts rows per namespace and kind.

Session memory is Dryas's own `/handoff` and compaction hooks. Details: [workflow.md §6–7](workflow.md).
