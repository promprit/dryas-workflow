# Phase 4: the owned core

Date: 2026-10-14. Status: approved by Promprit on 2026-10-14 on the condition that nothing is lost (additive only); awaiting plans. Umbrella spec for Dryas 2.0: one spec, one plan per sub-project (A–D), one worktree per plan, merged one at a time. Supersedes the Phase 4 section of [roadmap.md](../../roadmap.md) ("Jev judges the task, not every edit"), which becomes sub-project A. **Contested: no** (the spec's numbered rules do not change; this project swaps the bindings underneath them).

## Goal

A fresh `install/install.sh` on a machine with Python 3.9+ and nothing else (no Node, no npm, no API key) gives a working Dryas loop on Claude Code and on Codex. Every function the loop exercises today through Ruflo, Superpowers and the Jev model has a Dryas-owned equivalent with a test. The Jev model stays available as an upgrade behind the same interface. Ships as Dryas 2.0 when sub-projects A–D have merged.

## Problem

Dryas is positioned as a target operating model and a spec, yet its Claude Code edition hard-requires one third-party plugin (Superpowers, declared in `claude/.claude-plugin/plugin.json`), installs four more by default (the Ruflo plugins, which register several hundred MCP tools per session while the rules call three), needs Node and npm for them, and routes every gate decision through a remote model behind an API key. Concretely:

1. **Superpowers** is the only hard dependency. The Codex edition can only say "use Superpowers if installed", so it is "partial conformance". New editions (Pi, OpenCode, Roo, Cursor) would each need their own port. Upstream skills change under the user between sessions.
2. **Ruflo** is the memory and learning layer. What the loop uses from it is small (`memory_search`, `memory_store`, `swarm_init`, five hook helpers), but the install is the most fragile part of setup: a global npm package, patched helpers, a sandboxed `ruflo init`, a refusal on paths with spaces, and 204 MB of state under `~/.dryas/ruflo`, of which about 150 rows are project outcomes and 34,000 are hook noise.
3. **Jev** is called per edit, each call seeing only one diff. Without a key (`--no-jev`) the loop has no gates at all.
4. **Rust was considered and dropped** (2026-10-14): faster hooks, but a toolchain or per-platform signed binaries would reintroduce the dependency this project removes, and it would rewrite 2,500 tested lines of gate code. The contracts below are language-neutral so a hot-path binary stays possible later.

## Facts this design relies on

Read from `origin/docs/phase4-plan` on 2026-10-14.

- `spec/dryas-spec-v1.md` names no vendor in any numbered rule (WF, MEM, GOV, EXE, ESC, REV). Vendors appear only in the §9.2 example manifest. §9.1 allows `memory: provider: none`. GOV-10: credentials only in the environment. GOV-11: hook order scope lock → gate → memory → observers.
- Superpowers skills the rules invoke: `brainstorming`, `using-git-worktrees`, `systematic-debugging`, `verification-before-completion` (orchestrate), `writing-plans` (wplan), `requesting-code-review`, `receiving-code-review` (wreview). Five more are denied in `settings.fragment.json` because `/orchestrate` replaces them. `agents/executor.md` states test-first practice itself.
- Ruflo MCP tools used: `memory_search`, `memory_store`, `swarm_init` (orchestrate skill and command). Nothing reads the swarm entry; `log_dispatch` already records every dispatch.
- Ruflo hooks the loop runs (all via `claude/ruflo/run.py helper node …`): chain stage `ruflo-pre-bash` (observe-only danger scan); settings-fragment hooks PostToolUse `post-edit` (edit metric + `intelligence.recordEdit`), SubagentStop `post-task`, SessionStart `session-restore` and `auto-memory-hook.mjs import`, SessionEnd `session-end` (consolidate + persist), PreCompact manual/auto `session-end`. Ruflo's own route hook is already dropped.
- Ruflo state: `~/.dryas/ruflo/memory/agentdb-memory.db` has 34,693 `memory_entries`; by namespace `commands` 29,835, `feedback` 4,456, project namespaces about 150 in total. Learning tables (episodes, patterns, trajectories, skills) are empty in both databases. Session start reports 9 patterns and 9 edges.
- Codex edition: Ruflo is an MCP server only (`[mcp_servers.ruflo]` through the shim); Superpowers is never installed; `tools/sync_codex_plugin.py` copies `claude/jev` and `claude/pstack` and checks shared tokens in hand-written skills.
- Jev: `claude/jev/jev_client.py` calls `typesafe/jev-1.13` at OpenRouter's System One endpoint; questions today are per-edit and per-Bash safety (`gate.py`), route and tier (`route.py`), safe to commit (`/commit`), `needs_interrogate` (`/orchestrate`). `--no-jev` disables the gate and route stages in `chain.local.json`.
- Baseline on the branch: `pytest claude/jev/tests` 518 passed.

## Decisions

- **One Python core, stdlib only.** The Jev MCP server (`claude/jev/jev_mcp.py`) becomes the Dryas server; all hooks stay Python; Node and npm leave the install. `CONTRIBUTING.md`'s stdlib rule holds.
- **Language-neutral contracts.** The SQLite schema, the JSONL record formats, the hook stdin/stdout protocol and the CLI subcommands are the interfaces. A later hot-path binary may replace a stage behind them; nothing in 2.0 depends on Python function signatures across components.
- **Providers are manifest slots**: `judge: local | jev` (default `local` on a fresh install), `judge.shadow: local | jev | none`, `memory: dryas | ruflo | none` (default `dryas`), `process: dryas | superpowers` (default `dryas`). Design plugins stay optional as today.
- **The spec does not change.** `spec/dryas-spec-v1.md` keeps every rule and number; only §9.2's example manifest is updated. Conformance of both editions is re-stated in `docs/harnesses.md`.
- **Additive only (2026-10-14).** Nothing an existing install has today disappears: every tool, flag, hook, skill and record keeps working, either through a Dryas-owned equivalent (the parity tables, each row with a test) or by staying installable as an optional extra. Ruflo, Superpowers and the design plugins remain installable with `--with-ruflo`, `--with-superpowers`, `--with-design`, and coexist with the Dryas core when present; Ruflo's other tools are not rebuilt, since no rule or hook calls them, but they are not taken away either. On upgrade an existing install keeps its current providers (`judge: jev` when a key is set, Ruflo memory when it was selected) until the user flips them; a fresh install defaults to the owned core.
- **Jev JSONL logs stay JSONL.** They are FlowObserve's contract and `/tune`'s input. New fields only; FlowObserve's reducer is updated in step.
- **Shadow before enforce.** Any judgement that changes safety or cost runs in shadow (computed and logged next to the deciding answer) and is switched on by a threshold once `/tune` shows it is right. Each switch is reversible.
- **Order.** The no-loss inventory (see sub-project D) lands first, as its own small plan, so every later branch is checked against it. Then sub-projects A, B and C, which are independent (non-overlapping scope globs; parallel worktrees allowed). D integrates and releases.

## Sub-project A: the judge

**Interface.** `judge(question, state) -> {answer, confidence, provider, reasons}` in one module, `claude/jev/judge.py`. Callers (`gate.py`, `route.py`, `/commit`, `/orchestrate`, `/tune`) never see the provider. Questions: `edit_safe`, `bash_safe`, `route`, `needs_sonnet`, `needs_opus`, `safe_to_commit`, `needs_interrogate` (as today), plus `task_review` (new): given a plan step, its scope globs and done check, which files in scope need per-edit review, and which tier starts the task.

**Providers.**

- `local`: deterministic, no network, a few ms. Signals: path classes (the gate's existing `SENSITIVE_*` lists, dotfiles, CI config, build manifests, key files), content signals (`subprocess`, `eval`, `exec`, deletes, env reads, network calls), the Bash danger scan (absorbs Ruflo `pre-bash`: `rm -rf /`, root deletes with expansion, fork bombs, encoded PowerShell), scope membership from the lock, and the Phase 4 score: size (files and lines in scope), risk (path classes), tests (the done check runs a test), history (escalations for this task type, from the escalation log, used only once `history.min_tasks` is met).
- `jev`: the existing OpenRouter client, used when `judge: jev` and a key is present (GOV-10).

**Doubt band.** Any answer below its threshold returns `ask`; the hook hands the decision to the strong tier in the session, as today. The local judge never returns `allow` for a sensitive class: it returns `ask`. Fail safe on format: a missing, unreadable or older `active.json` review set means every edit is judged.

**Shadow mode.** `judge.shadow` names a second provider whose answer is logged next to the deciding one, same task id, never acted on. Recommended path for an existing install: `judge: jev, shadow: local` for a few weeks, then `judge: local, shadow: jev` or `none`. `/tune` reports agreement per question, false-skips on `task_review`, Jev calls per task and gate wait per task, and proposes the flip.

**Task-level judgement** (the roadmap's Phase 4, with its gaps closed):

1. Baseline: a `task_id` on every gate, dispatch, review and merge record; `/tune` reports calls per task, wait per task, deny and ask rate per edit, escalation rate per task, review findings per task.
2. Scored starting tier, shadow: the local score and the tier it would pick are written into the dispatch record; dispatch proceeds as today. `/tune` compares score buckets with actual escalations.
3. Task review set, shadow: at dispatch the orchestrator asks `task_review`; the answer is written to `active.json` by the orchestrator only (executors have no tool that writes it; the scope lock denies edits to it). Every edit is still judged; a false-skip is logged whenever a per-edit answer is `deny` or `ask` on a file the task verdict would have skipped.
4. Enforce, on evidence: `review.task_skip` turns the skip on when `false_skips <= review.max_false_skip_rate` over `review.min_tasks`; `dispatch.scored_tier` turns the score on when its buckets predict escalation better than the current tier question over `dispatch.min_tasks`. Defaults in `thresholds.json`: `min_tasks 50`, `max_false_skip_rate 0.01`, `history.min_tasks 30`. Always-judged classes stay judged whatever any provider said. Content signals still trigger a per-edit judgement inside a trusted scope.

**Records.** One verdict record per question: `ts, task_id, question, provider, answer, confidence, shadow_provider, shadow_answer, wall_ms, reasons`. Same JSONL files as today.

**Done when:** Jev calls per task at least halved and gate wait per task down against the baseline; escalation rate and review-found defects no worse; no enforced false-skip on an always-judged file; `judge: local` passes the full loop with no key set.

## Sub-project B: memory and learning

**Store.** `~/.dryas/dryas.db`, SQLite in WAL mode, stdlib `sqlite3`, owned by the Dryas server and the memory hooks. Full-text search through FTS5 where the build has it, with a `LIKE` fallback so a missing FTS5 degrades (MEM-5). Namespace = main repo folder name (`claude/ruflo/ns.py` moves to `claude/jev/ns.py`).

Tables: `memory(id, ns, kind, title, body, tags, task_id, commit, source, created, accessed, hits)`, `memory_fts`, `edits(session, task_id, file, ok, ts)`, `tasks(task_id, ns, title, scope, tier_start, tier_end, outcome, started, ended)`, `sessions(id, ns, started, ended, summary)`, `patterns(ns, kind, key, value, support, updated)`.

**Parity table.**

| Ruflo today | Dryas 2.0 | Test |
|---|---|---|
| `memory_search` (top 3 outcomes, ns = main repo) | Same tool name on the Dryas server, same namespace rule; results carry matching `patterns` rows with a reason string | Stored row comes back; another ns returns nothing |
| `memory_store` (outcome after task) | Same tool, plus `task_id` and `commit`; MEM-4 at write time: `redact.py` patterns reject secrets, a size cap and diff markers reject file contents | Secret and diff bodies refused; outcome stored |
| `swarm_init` | Kept as a tool on the Dryas server: it opens a `tasks` row (topology, task, scope) and returns a swarm id, so existing rules and skills keep working; the dispatch record stays the ledger of record | Call returns an id and a `tasks` row exists; `sync_codex_plugin.py --check` passes |
| `pre-bash` danger scan | `bash_safe` in the local judge (A) | Danger patterns deny |
| `post-edit` | PostToolUse stage writes an `edits` row | One row per edit, failure flagged |
| `post-task` (SubagentStop) | `tasks` row closed with outcome and tier | Row updated |
| `session-restore` / `session-end` / PreCompact persist | `sessions` row at start; summary at end and at compaction. Context restore stays with `compact_keep.py` and `/handoff` | Start and end rows; compaction writes a summary |
| `auto-memory-hook.mjs import` | SessionStart indexes the Claude memory dir (`MEMORY.md` and its files) as read-only `note` entries keyed by path and mtime | A note becomes searchable; unchanged files skipped |
| `session-end` consolidate (dedupe, edges, PageRank) | Session-end consolidate: dedupe by content hash, co-access and co-edit edges, PageRank over those edges (stdlib, about 50 lines), plus per-file failure rate, co-edited file sets and tier-that-solved-it per task type. These are the `patterns` rows `memory_search` returns and the history signal the local judge reads | Two sessions of edits yield the expected rows and ranks |

Ranking keeps PageRank over the memory graph and adds the explainable statistics; every result carries a reason string. Nothing in today's recall goes away.

**MCP tools** on the Dryas server: `memory_search`, `memory_store`, `memory_list`, `memory_forget`. Same tools on Codex, from the same server: the Codex edition reaches full memory parity.

**Migration.** `dryas memory import-ruflo` opens `agentdb-memory.db` read-only and imports every row (`source = ruflo`, original namespace and timestamps kept, embeddings kept as a blob for a later semantic provider). Project namespaces (about 150 rows) become normal memory; `commands` and `feedback` (about 34,000 rows) are imported as kind `archive`, searchable with `memory_search(include_archive=true)` but left out of default recall so they don't drown it. The import is idempotent and verifies row counts per namespace. `~/.dryas/ruflo` is left in place; uninstall offers its removal, never by default.

## Sub-project C: process skills

Eight Dryas skills under `claude/skills/`, rewritten in Dryas vocabulary (tiers, Jev questions, scope lock, worktrees, `.orchestrate/PLAN.md`), each holding process only; `CLAUDE.md.template` and `AGENTS.md.template` point to them instead of restating them.

| Superpowers 6.4.1 | Dryas skill | Used by |
|---|---|---|
| brainstorming | `brainstorm` | orchestrate, always first |
| using-git-worktrees | `worktree` | orchestrate |
| systematic-debugging | `debug` | orchestrate, executor |
| verification-before-completion | `verify` | orchestrate, commit, merge |
| writing-plans | `plan` | wplan |
| requesting-code-review | `review-request` | wreview |
| receiving-code-review | `review-receive` | wreview |
| (executor test-first practice) | `tdd` | executor |

The "brainstorm first, always" hard gate stays, with the same three paths (spike, bounded, architectural). Credit: a NOTICE.md entry and `claude/skills/UPSTREAM.md` naming the upstream commit and the skill each derives from, the pstack pattern. `plugin.json` drops the hard dependency; Superpowers stays installable with `--with-superpowers` and coexists with the Dryas skills (the rules point at the Dryas skills; the deny list for the five overlapping Superpowers skills stays as today and only matters when Superpowers is present; every other Superpowers skill remains usable). The Dryas skills become shared source: `sync_codex_plugin.py` copies them to `codex/skills/`; every Codex-specific instruction in today's hand-written Codex skills is carried over as a harness block in the shared source, and `--check` fails if one is missing.

**No content lost in a rewrite.** Each rewritten skill ships with a coverage table in `claude/skills/UPSTREAM.md`: every step, rule, red flag and checklist item of the upstream skill, mapped to where it lives in the Dryas skill (or to the template rule that already states it). A row without a target fails review. Rewrites may shorten wording, never drop a rule.

## Sub-project D: integration and release

**Hook chain.** `chain.json`: `jev-gate` and `jev-route` keep their names and scripts and become provider-agnostic; `ruflo-pre-bash` stays as the optional `ruflo` component's stage (off unless `--with-ruflo`); new memory stages, all Python, are added for the `dryas` memory provider: PostToolUse `mem-edit`, SubagentStop `mem-task`, SessionStart `mem-session-start` (session row, note import), SessionEnd and PreCompact `mem-session-end`. The settings-fragment Ruflo block stays as the optional `ruflo` component. Order per GOV-11: scope lock → gate → memory → observer. Every memory stage is observe-only, exits 0, and is budgeted at 2 s.

**MCP server.** The `jev` server keeps its name and its tools (`jev_judge`, `log_dispatch`, `log_escalation`, `log_review`, `log_merge`, `log_override`), so no allow list or rule changes; `memory_search`, `memory_store`, `memory_list`, `memory_forget` and `swarm_init` are added to it. Both editions' `.mcp.json` already point at it. The Codex `[mcp_servers.ruflo]` block is written only with `--with-ruflo`. A rename to `dryas` is a later, separate change.

**Installer and manifest.** Added: `--judge local|jev`, `--with-ruflo`, `--with-superpowers`, `--with-design`. Kept as aliases: `--no-jev` = `--judge local`; `--no-ruflo`, `--no-superpowers` keep their meaning (the extra is not installed, which is now the default on a fresh install, since the core has owned equivalents); the design plugins have no owned equivalent, so they **stay installed by default** as today and `--no-design` keeps its meaning; `--openrouter-key` implies `--judge jev`; `--no-pstack-picks` unchanged. Preflight needs Python 3.9+ only; Node, npm and the path-with-spaces check apply only with `--with-ruflo`. `components.json` keeps `ruflo` and `superpowers` as optional extras; `dryas.yaml` and spec §9.2 show the new bindings. `write_chain_local` records the `judge` and `memory` providers; on upgrade it keeps whatever the install has now. Uninstall offers, never runs unasked, a legacy cleanup: the Ruflo plugins, the global `ruflo` package and `~/.dryas/ruflo`, each listed and confirmed. The Phase 2 item "installer reads `dryas.yaml`" stays a separate task.

**Docs.** `workflow.md`, `architecture.md`, `memory-model.md`, `governance.md` (judge providers), `install.md`, `harnesses.md` (Codex now full conformance), `roles.md` if a role's skill list changes, both templates, `claude/skills/orchestrate/ruflo-tools.md` kept and re-titled as the optional Ruflo reference, `CHANGELOG.md` 2.0.0, `roadmap.md` Phase 4 rewritten to this shape. `~/.dryas/docs/dryas-workflow.md` regenerates from the repo at setup.

**No-loss inventory.** Before any sub-project starts, `tools/inventory.py` snapshots 1.x into `reference/inventory-1.x.json`: every MCP tool, slash command, skill, agent, hook stage and settings hook, installer flag, `thresholds.json` key, JSONL record field and `/tune` report line. A test asserts that each entry exists in 2.0 or maps to a named equivalent in the parity tables. It runs in CI on every sub-project branch, so a loss fails the build rather than a review.

**Release.** Version 2.0.0. `tools/release_check.py` gains a no-Node check (install into a temp config dir with Node absent from PATH). CI runs the install and the end-to-end loop on macOS, Linux and Windows without Node.

**Cut-over for an existing install.** Run setup for 2.0 with `--judge jev` (shadow `local` is the default when a key is present), run `dryas memory import-ruflo`, accept the legacy cleanup, keep working. Flip to `--judge local` when `/tune` proposes it.

## Error handling

- Local judge: any exception in a signal → that signal is `unknown` and the answer is `ask`, logged with the traceback summary. Never `allow` on error.
- Jev provider unavailable (no key, timeout, HTTP error): the deciding answer comes from `local` for that call and the record says so; no retry inside a hook.
- Memory DB locked or missing: hooks log one line and exit 0; MCP tools return an empty result with `degraded: true` (MEM-5). Schema migration runs on server start and is idempotent; a newer schema than the code knows is read-only.
- `active.json` malformed or from an older version: every edit judged.
- Note import: unreadable or oversized files skipped with a count, never an error.

## Testing

- Unit tests per module in `claude/jev/tests` (pytest, stdlib). The local judge's signals and score are table-driven; thresholds are fixtures.
- One parity test per row of the tables in A, B and C, named after the row.
- Shadow records: a replayed log with known disagreements yields the expected `/tune` agreement, false-skip and proposal output.
- FlowObserve: golden replay of spool files containing the new record fields passes in `projects/flowobserve` before D merges.
- End to end: install 2.0 into a temp HOME with Node removed from PATH, then run a scripted loop (prompt → dispatch → edit → commit gate) on the Claude edition with the mock hook stdin used by the existing tests, and on Codex with the mock Responses server from the Codex plugin spec.
- Migration: `import-ruflo` against a fixture copy of `agentdb-memory.db` imports the project rows and skips the noise.
- `release_check.py` passes on all three platforms.

## Out of scope

- Rebuilding any Ruflo function the loop does not call (embeddings, federation, wasm agents, browser, GitHub, neural, cost tracker).
- Replacing the design plugins; they stay optional.
- The repo map for Brainstorm and Plan (roadmap "Later"), and the installer reading `dryas.yaml` (Phase 2).
- Removing the Jev model. It remains a provider; the decision to make `local` the default on a given machine is `/tune`'s, on data.
- A compiled hot-path hook. Allowed later behind the contracts above, not built here.

## Effort

A 6–9 days of work plus a baseline week and 2–4 weeks of shadow data; B 4–6; C 3–5; D 3–4. About 3–4 weeks of build in parallel worktrees, 6 weeks start to finish.
