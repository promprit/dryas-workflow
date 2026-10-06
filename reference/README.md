# Reference implementation

This repository is both the Dryas framework (`docs/`, `spec/`) and its reference implementation. This page maps each rule of the [specification](../spec/dryas-spec-v1.md) to the code that implements it, and doubles as the conformance table the spec asks for.

The bindings are declared in [dryas.yaml](dryas.yaml).

## Where the implementation lives

| Path | What |
| --- | --- |
| `claude/` | Claude Code edition: rules template, commands, skills, `executor` agent, Jev and Ruflo hooks |
| `codex/` | Codex edition: `AGENTS.md` template, skills, hooks fragment |
| `claude/jev/` | Harness-agnostic Python shared by both editions: scope lock, gate, route, plan-file tools, handoff, logs |
| `install/` | Installer for both editions (`--harness claude|codex|both`) |

## Bindings

| Layer | Abstract role | Bound to |
| --- | --- | --- |
| Memory | Project memory | [Ruflo](https://github.com/ruvnet/ruflo) (latest; tested 3.53.0) (`memory_search`, `memory_store`) |
| Memory | Session memory | `claude/jev/handoff.py`, `compact_keep.py`, `compact_restore.py` |
| Governance | Judge and gate | [Jev](https://github.com/typesafe-ai/skills) via OpenRouter (`gate.py`, `route.py`, `jev_mcp.py`) |
| Governance | Scope lock | `claude/jev/scope_lock.py` |
| Governance | Hook order | `claude/jev/chain.py`, `chain.json` |
| Execution | Process skills | [Superpowers](https://github.com/obra/superpowers) (brainstorming, worktrees, TDD, verification) |
| Execution | Orchestrator | `/orchestrate` (`claude/skills/orchestrate/`) on Opus |
| Execution | Executor | `claude/agents/executor.md` on Sonnet |
| Execution | Design specialists | [Impeccable](https://github.com/pbakaus/impeccable), [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) |
| Escalation | Ladder and log | Sonnet → Opus → Fable, `mcp__jev__log_escalation` |
| Review | Review and gates | `/wreview`, `/interrogate`, pstack cleanup, `/benchmark-checklist`, `/commit` |

## Conformance

`met` / `partial` / `not met` for the Claude Code (CC) and Codex (CX) editions.

| Rule | CC | CX | How |
| --- | --- | --- | --- |
| WF-1 | met | met | `/orchestrate` skill; `$orchestrate` in Codex |
| WF-2 | met | met | Brainstorm-first rule in the always-loaded rules; Superpowers brainstorming |
| WF-3 | met | met | Superpowers brainstorming writes the design doc before orchestration |
| WF-4 | met | met | Rules: single-file fix runs plainly; review still applies |
| WF-5 | met | met | `claude/CLAUDE.md.template`, `codex/AGENTS.md.template`, rendered by the installer |
| MEM-1 | met | met | Ruflo is the only memory layer |
| MEM-2 | met | met | Namespace = main repo folder name |
| MEM-3 | met | met | Orchestrate skill: `memory_search` first, `memory_store` on return |
| MEM-4 | met | met | Outcomes only; redaction in `redact.py` |
| MEM-5 | met | met | `claude/ruflo/run.py` makes hooks silent no-ops when data root is missing |
| MEM-6 | met | not met | `/handoff` and compaction hooks are Claude Code only |
| GOV-1 | met | met | `Scope:` in each plan section |
| GOV-2 | partial | partial | Hook denies Edit/Write (and Codex `apply_patch`); shell-command edits are a known limit |
| GOV-3 | met | met | Rule in always-loaded rules |
| GOV-4 | met | met | Rule in always-loaded rules; installer dry-runs and backs up |
| GOV-5 | met | met | `/commit` never pushes |
| GOV-6 | met | met | Jev MCP answers only; thresholds in `thresholds.json` |
| GOV-7 | met | met | `gate.py` never allows; fails to no decision |
| GOV-8 | met | met | `mcp__jev__log_override` |
| GOV-9 | met | met | `/tune` proposes; human approves each change |
| GOV-10 | met | met | Only `OPENROUTER_API_KEY`, from the environment; `redact.py` |
| GOV-11 | met | met | `chain.py` runs `chain.json` stages in order |
| EXE-1 | met | met | Superpowers using-git-worktrees |
| EXE-2 | met | met | `.orchestrate/PLAN.md`, globally git-ignored |
| EXE-3 | met | met | `planfile.py section` |
| EXE-4 | met | met | TDD gate in orchestrate; tester executor |
| EXE-5 | met | partial | Rule in orchestrate skill; Codex without sub-agents does tasks itself, one at a time |
| EXE-6 | met | met | `executor.md` rule 5 |
| EXE-7 | met | met | `executor.md` report block |
| EXE-8 | met | met | Ruflo hierarchical swarm; Codex sub-agents |
| ESC-1 | met | met | `executor.md` `model: sonnet`; Codex cheaper model first |
| ESC-2 | met | met | `thresholds.json` `escalation` |
| ESC-3 | met | met | Orchestrate skill |
| ESC-4 | met | met | pstack picks: systematic-debugging before each climb |
| ESC-5 | met | met | `mcp__jev__log_escalation` |
| ESC-6 | met | met | Orchestrate skill |
| REV-1 | met | met | `/wreview` / `$wreview` |
| REV-2 | met | met | Two-stage review |
| REV-3 | met | met | Superpowers verification-before-completion |
| REV-4 | met | met | `/interrogate` / `$interrogate` |
| REV-5 | met | met | Orchestrate finish step |
| REV-6 | met | met | `/benchmark-checklist` |

Operational detail for all of this is in [docs/workflow.md](../docs/workflow.md).
