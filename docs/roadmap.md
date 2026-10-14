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

## Phase 4: Jev judges the task, not every edit

Today the Jev gate judges every `Write` and `Edit`, each as a remote call with no context beyond the one diff. The next change moves the judgement to the task, and scores the starting tier from signals that are logged. Both are guesses about safety and cost, so each runs in shadow mode first (computed and logged next to today's behaviour, changing nothing) and is enforced only once the logs show it is right.

Order of work:

- [ ] **Spec first**, under `docs/specs/`: it changes the orchestrate skill, the `active.json` format, scope lock, the gate and the dispatch log.
- [ ] **Baseline.** Add a task id to each gate record so calls group by task, then log a few days of normal use: Jev calls per task, seconds waiting on the gate per task, per-edit deny and ask rate, escalation rate per task.
- [ ] **Scored starting tier, shadow.** At dispatch, compute locally from the plan task and the escalation log: size (files and lines in the scope), risk (paths touching auth, money, data, migrations), tests (the done check is a test). Write the signals, score and the tier it would pick into the dispatch record; dispatch as today. Compare score buckets with what actually escalated. Add a history signal (this task type escalated before) once the escalation log has volume.
- [ ] **Task-level judgement, shadow.** At dispatch, one Jev question: given this plan step, scope and done check, which files need per-edit review, and does the task need a stronger tier? It answers the review set and the doubt-band tier question in one call. Store the answer in `active.json`; keep judging every edit. Log a false-skip whenever a per-edit judge denies or asks on a file the task verdict would have skipped.
- [ ] **Enforce, on evidence.** Turn on the task-level skip when false-skips are near zero over a meaningful number of tasks, and the scored tier when its buckets predict escalation better than today's "stronger than the standard tier?" question. Each switch is a threshold in `thresholds.json`, reported by `/tune` and reversible.

Design rules:

- Fail safe on format: a missing, unreadable or older `active.json` review set means every edit is judged. No verdict never means skip.
- Classes that are always judged (`.git/`, dotfiles, CI config, build manifests, key files; the gate's `SENSITIVE_*` lists) stay judged whatever Jev said.
- Cheap local content signals (`subprocess`, `eval`, deletes, env and network access) still trigger a per-edit call inside a trusted scope, so an executor that drifts from its task is caught.
- The score sets the first rung of the ladder only; escalation still happens after a failure. Doubt rounds up. Weights are thresholds, not constants.

Done when: Jev calls per task down by at least half and gate wait per task down, escalation rate and review-found defects no worse than the baseline, and no enforced false-skip on a file that is always judged.

## Later: a repo map for Brainstorm and Plan

A cheap way for the orchestrator to see a large repo's structure without reading it. Separate from Phase 4: size and risk come from the plan's scope globs and path classes, not from the codebase.

- [ ] A structural map, not embeddings: file tree, top-level symbols (stdlib `ast` for Python, `ctags` when installed) and doc headings. Built on demand, cached by commit SHA so each worktree gets its own branch's map, injected at Brainstorm and Plan under a token cap. Stdlib only, per [CONTRIBUTING.md](../CONTRIBUTING.md).
- [ ] Measure planning turns and tokens with and without it, from the dispatch records. Only if the map is not enough on large repos, add semantic search as a pluggable component (off by default, like Ruflo).
- [ ] Say in [memory-model.md](memory-model.md) that a source index is not memory: derived, rebuildable, never authoritative, never in the memory layer (MEM-4 bars file contents there), and a missing index never blocks the loop (MEM-5).
