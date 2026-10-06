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
| Metrics | Partial (model defined; some KPIs need new logging) |
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
- [ ] Log the planned metrics: `scope`, `dispatch`, `review` and `merge` records ([metrics.md](metrics.md#planned-logging)), and report them in `/tune`
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
- [ ] OpenCode, Roo, Cursor editions, by anyone, against the spec
- [ ] Packaged plugins per harness, generated from the manifest
