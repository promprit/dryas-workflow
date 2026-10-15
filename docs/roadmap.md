# Roadmap

Dryas is a method first. The tooling follows it, not the other way round.

## Positioning

**The Dryas Workflow Framework: a target operating model for AI-assisted software delivery.**

The scope is deliberate: software delivery, not every use of AI in an organisation. What Dryas defines for each operating-model dimension, and where: [operating-model.md](operating-model.md). Status per dimension:

| Dimension | Status |
| --- | --- |
| Process | Covered |
| Governance and decision rights | Covered |
| Technology (as roles, not products) | Covered |
| Controls and risk | Covered for delivery |
| Cost | Covered for delivery |
| Scale within a team | Covered |
| People and organisation | Covered |
| Metrics | Covered (EXE-M3 cost is entered by hand) |
| Current → target transition | Covered |

## Phase 1: the framework (now)

Make the method readable without the tools, and complete it as an operating model.

- [x] Why Dryas exists and what it solves: [why-dryas.md](why-dryas.md)
- [x] Five-layer architecture and the loop: [architecture.md](architecture.md)
- [x] One doc per layer: [memory](memory-model.md), [governance](governance.md), [execution](execution-model.md), [escalation](escalation-model.md), [review](review-model.md)
- [x] Adoption guide: [adoption-guide.md](adoption-guide.md)
- [x] Reference map from method to implementation: [reference/](../reference/README.md)
- [x] Worked examples: [examples/](../examples/README.md)
- [x] Human roles, separation rules, a RACI across the loop and the skills each role needs: [roles.md](roles.md)
- [x] KPIs with a definition, healthy range, source log, cadence and live/planned status: [metrics.md](metrics.md)
- [x] Log the planned metrics: scope, dispatch, review and merge records, reported by /tune ([metrics.md](metrics.md#logging-records))
- [x] One page mapping layers, roles and metrics onto the operating-model dimensions: [operating-model.md](operating-model.md)
- [x] Maturity levels L0–L4, each earned by its metrics: [adoption-guide.md](adoption-guide.md#maturity-levels)
- [x] Re-lead README and why-dryas.md with "target operating model for AI-assisted software delivery"

## Phase 2: the specification and manifest

Make the method portable.

- [x] Draft specification with numbered MUST / SHOULD rules: [spec/dryas-spec-v1.md](../spec/dryas-spec-v1.md)
- [x] `dryas.yaml` manifest format, and the manifest for this repo: [reference/dryas.yaml](../reference/dryas.yaml)
- [ ] Gather feedback; freeze spec 1.0
- [ ] Have the installer read `dryas.yaml` instead of flags and `components.json`
- [ ] A conformance checker that reads a manifest and an installed tree and reports rule by rule

## Phase 3: editions

Only once the spec is stable.

- [x] Claude Code edition (this repo's `claude/`)
- [x] Codex edition (this repo's `codex/`, partial conformance, see [harnesses.md](harnesses.md))
- [x] Codex plugin (`dryas@dryas-workflow` from `codex/`)
- [ ] Pi, OpenCode, Roo and Cursor editions (later), by anyone, against the spec
- [ ] Packaged plugins per harness, generated from the manifest (Claude Code and Codex done: plugin dryas@dryas-workflow)

## Phase 4: the owned core

Dryas 2.0 owns its core: no third-party plugin is required, and the extras stay optional. Providers are slots (`judge: local | jev`, `memory: dryas | ruflo | none`, `process: dryas | superpowers`), chosen at install ([install.md](install.md#flags)). Delivered as sub-projects, each merged in turn:

- [x] **0, inventory.** `tools/inventory.py --check` and `reference/inventory-map.json`: nothing a 1.x install has disappears without a mapped replacement.
- [x] **A1, judge providers.** The `local` judge (deterministic rules, no key) next to Jev, with the shadow comparison and fallback logged.
- [x] **A2, task-level judge.** The review set, the score, the scored start tier and the Done-when check, all in shadow and off by default.
- [x] **B, Dryas memory.** `~/.dryas/dryas.db` with search, consolidation and `dryas memory import-ruflo`, served by the `jev` MCP server.
- [x] **C, Dryas process skills.** `dryas:brainstorm`, `dryas:worktree`, `dryas:tdd`, `dryas:review-request`, `dryas:review-receive`, `dryas:verify`, `dryas:plan` and `dryas:debug`, each mapped to its upstream in `UPSTREAM.md`.
- [x] **D, integration.** The memory stages and `gate-outcome` in the hook chain, background consolidation, the installer flags and the `dryas` command, the legacy cleanup, `/tune` judge and memory lines, the judge scorecard (`reference/judge-corpus/`), `/retro`, `GLOSSARY.md` and `.out-of-scope/`.
- [x] **E, cloud sessions.** `dryas cloud init | check | update | remove` commits a pinned copy of the Dryas core into a repo so claude.ai/code cloud sessions run the workflow with the local judge and no key ([cloud-sessions.md](cloud-sessions.md)).

Task-level judgement runs shadow-then-enforce: it is computed and logged next to today's behaviour, and enforced only once the logs show it is right. A2's finding: `review.task_skip` usually reports "no evidence", because build files are always judged and plain edits inside the working folder are already skipped. The value is in the per-task numbers, the scored start tier and the Done-when check. Rules in [governance.md](governance.md#task-level-judgement).

- [ ] **Enforce, on evidence.** Turn on `review.task_skip` and `dispatch.scored_tier` only when `/tune` proposes them, each a threshold in `thresholds.json`, reported and reversible.
- [ ] **Flip judges.** Move an install from `--judge jev` to `--judge local` when `/tune` shows the local judge agreeing, and grow the corpus from the disagreements it lists.

Design rules:

- Fail safe on format: a missing, unreadable or older `active.json` review set means every edit is judged. No verdict never means skip.
- Classes that are always judged (`.git/`, dotfiles, CI config, build manifests, key files; the gate's `SENSITIVE_*` lists) stay judged whatever the judge said.
- Cheap local content signals (`subprocess`, `eval`, deletes, env and network access) still trigger a per-edit call inside a trusted scope, so an executor that drifts from its task is caught.
- The score sets the first rung of the ladder only; escalation still happens after a failure. Doubt rounds up. Weights are thresholds, not constants.

Done when: Jev calls per task down by at least half and gate wait per task down, escalation rate and review-found defects no worse than the baseline, and no enforced false-skip on a file that is always judged.

## Later: a repo map for Brainstorm and Plan

A cheap way for the orchestrator to see a large repo's structure without reading it. Separate from Phase 4: size and risk come from the plan's scope globs and path classes, not from the codebase.

- [ ] A structural map, not embeddings: file tree, top-level symbols (stdlib `ast` for Python, `ctags` when installed) and doc headings. Built on demand, cached by commit SHA so each worktree gets its own branch's map, injected at Brainstorm and Plan under a token cap. Stdlib only, per [CONTRIBUTING.md](../CONTRIBUTING.md).
- [ ] Measure planning turns and tokens with and without it, from the dispatch records. Only if the map is not enough on large repos, add semantic search as a pluggable component (off by default; Ruflo is now an optional extra).
- [ ] Say in [memory-model.md](memory-model.md) that a source index is not memory: derived, rebuildable, never authoritative, never in the memory layer (MEM-4 bars file contents there), and a missing index never blocks the loop (MEM-5).

## Later: an OpenCode edition (parked 2026-10-15)

Parked until after 2.0. Estimate: 3–5 days of build to reach the Codex edition's level (partial conformance), after a half-day spike. Most of Dryas carries over unchanged: OpenCode reads `AGENTS.md` (the Codex template plus a harness block), skills and commands are markdown (one more render target in `tools/sync_codex_plugin.py`), the `jev` MCP server runs as a local stdio server (memory, judge and logging as-is), and per-agent models give the tier table.

- [ ] Spike (half a day): confirm OpenCode's plugin events before and after a tool call, whether a plugin can ask the user or only block (if only block, the local judge's `ask` becomes a deny with a reason on OpenCode), and whether the acting agent's identity reaches the plugin (the scope lock needs it; Codex does not provide it).
- [ ] Hook shim (1–2 days): a small plugin, run by OpenCode itself (no Node for the user), that maps tool events to the hook JSON `claude/jev/chain.py` reads, like `codex_event.py` does for Codex.
- [ ] Installer target (about 1 day): `--harness opencode` writes OpenCode's config (MCP server, plugin, agents, commands), with uninstall and a `tools/release_check.py` check.
- [ ] Executor and orchestration (half a day to a day): map `dryas:executor` and the fast → standard → strong → frontier ladder onto OpenCode agents and subagents.
- [ ] Tests, docs and conformance (about 1 day): mock-event tests like the Codex ones, an OpenCode column in [harnesses.md](harnesses.md) and the conformance table, a CI job.
