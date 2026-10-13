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

Today the Jev gate judges every `Write` and `Edit`, each as a remote call with no context beyond the one diff. The next change moves the judgement to the task:

- [ ] When the orchestrator dispatches a task, ask Jev once: given this plan step, file scope and done check, which files need per-edit review? Store the answer in `active.json` next to the scope.
- [ ] Scope lock reads that set on each edit: files in it go to the gate, the rest are allowed locally. One Jev call per task instead of one per edit.
- [ ] Keep the fallbacks. Edits outside any task still use the path filter and the gate. Classes that are always judged (`.git/`, dotfiles, CI config, secrets-adjacent files) stay judged whatever Jev said. Cheap local content signals (`subprocess`, `eval`, deletes, env and network access) still trigger a per-edit call inside a trusted scope, so an executor that drifts from its task is caught.
- [ ] Log one dispatch record per task with Jev's verdict, for `/tune` and [metrics.md](metrics.md).
- [ ] Score the starting tier from signals you can see and log, computed locally at dispatch: size (files and lines in the task scope), risk (paths touching auth, money, data, migrations), tests (the task has a done check a test can verify) and history (this task type escalated before, from the escalation log). The score sets the first rung of the ladder only; escalation still happens after a failure. Jev is asked only inside a doubt band around each line, and doubt rounds up. Write the signals, score and starting tier into the dispatch record so `/tune` can report the escalation rate per score bucket and move the bands; the weights are thresholds, not constants.
- [ ] Spec first, under `docs/specs/`, since it changes the orchestrate skill, the `active.json` format, scope lock, the gate and the dispatch log.
