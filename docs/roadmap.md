# Roadmap

Dryas is a method first. The tooling follows it, not the other way round.

## Phase 1: the framework (now)

Make the method readable without the tools.

- [x] Why Dryas exists and what it solves: [why-dryas.md](why-dryas.md)
- [x] Five-layer architecture and the loop: [architecture.md](architecture.md)
- [x] One doc per layer: [memory](memory-model.md), [governance](governance.md), [execution](execution-model.md), [escalation](escalation-model.md), [review](review-model.md)
- [x] Adoption guide: [adoption-guide.md](adoption-guide.md)
- [x] Reference map from method to implementation: [reference/](../reference/README.md)
- [x] Worked examples: [examples/](../examples/README.md)

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
