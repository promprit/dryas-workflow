# Reference implementation

This repository is both the Dryas framework (`docs/`, `spec/`) and its reference implementation. This page maps each rule of the [specification](../spec/dryas-spec-v1.md) to the code that implements it, and doubles as the conformance table the spec asks for.

The bindings are declared in [dryas.yaml](dryas.yaml).

## Where the implementation lives

| Path | What |
| --- | --- |
| `claude/` | Claude Code edition, packaged as the plugin `dryas@dryas-workflow`: rules template, `hooks/hooks.json`, `.mcp.json`, commands, skills, `dryas:executor` agent, judge, Dryas memory and extras hooks |
| `codex/` | Codex edition, packaged as the Codex plugin `dryas@dryas-workflow` (marketplace `.agents/plugins/marketplace.json`): rules template (`AGENTS.md.template`), `hooks/hooks.json`, `.mcp.json`, skills; `codex/jev` and `codex/pstack` are generated from `claude/` by `tools/sync_codex_plugin.py` |
| `claude/jev/` | Harness-agnostic Python shared by both editions: scope lock, gate, local judge, Dryas memory, route, plan-file tools, handoff, logs |
| `install/` | Installer for both editions (`--harness claude|codex|both`): plugin setup per Claude config dir and per Codex home (`CODEX_HOME`) |
| `~/.dryas` | Shared state for every account (`$DRYAS_DATA_ROOT`): Jev logs, thresholds, handoffs, `chain.local.json`, `accounts.json`, the Dryas memory store (`dryas.db`), Ruflo runtime (extra) |

## Bindings

| Layer | Abstract role | Bound to |
| --- | --- | --- |
| Memory | Project memory | Dryas memory (`claude/jev/memdb.py`, `memstore.py`, served by the `jev` MCP server: `memory_search`, `memory_store`); alternative: [Ruflo](https://github.com/ruvnet/ruflo) with `--memory ruflo` (latest; tested 3.53.0) |
| Memory | Session memory | `claude/jev/handoff.py`, `compact_keep.py`, `compact_restore.py` |
| Governance | Judge and gate | The local judge (`local_judge.py`, deterministic rules, no key) or [Jev](https://github.com/typesafe-ai/skills) via OpenRouter (`--judge jev`), through `gate.py`, `route.py`, `jev_mcp.py`; `judge.provider` is `auto` unless set |
| Governance | Scope lock | `claude/jev/scope_lock.py` |
| Governance | Hook order | `claude/jev/chain.py`, `chain.json`, local choices in `~/.dryas/chain.local.json` |
| Execution | Process skills | The Dryas skills `dryas:brainstorm`, `dryas:worktree`, `dryas:tdd`, `dryas:verify`, `dryas:debug` (`claude/skills/`); alternative: [Superpowers](https://github.com/obra/superpowers) with `--with-superpowers` |
| Execution | Orchestrator | `/orchestrate` (`claude/skills/orchestrate/`) on the `strong` tier |
| Execution | Executor | `claude/agents/executor.md` (`dryas:executor`) on the `standard` tier |
| Execution | Design specialists | [Impeccable](https://github.com/pbakaus/impeccable), [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) |
| Escalation | Ladder and log | fast → standard → strong → frontier, `mcp__plugin_dryas_jev__log_escalation` |
| Review | Review and gates | `/wreview`, `/interrogate`, pstack cleanup, `/benchmark-checklist`, `/commit` |
| Harness | Rules binding | SessionStart hook `claude/jev/rules_inject.py` (injects `claude/CLAUDE.md.template`); Codex: the same hook with `--harness codex` (injects `codex/AGENTS.md.template`) |
| Harness | Hooks binding | Plugin `claude/hooks/hooks.json`; Codex: plugin `codex/hooks/hooks.json`, trusted by setup after consent (or in `/hooks`) |
| Harness | MCP binding | Plugin `claude/.mcp.json` (the `jev` MCP server, with the memory tools); Codex: plugin `codex/.mcp.json`, plus setup's `config.toml` block for the `python3` fallback and, with the Ruflo extra, Ruflo |
| Harness | Skills binding | Plugin `claude/skills/` and `claude/commands/`; Codex: plugin `codex/skills/` (`$dryas:<name>`) |
| Harness | State | `~/.dryas` (`$DRYAS_DATA_ROOT`), shared by every Claude config dir and Codex |
| Harness | Cloud sessions | `dryas cloud` (`tools/dryas_cloud.py`) copies the core into a repo (`.dryas/`, `.claude/`); [cloud-bindings.json](cloud-bindings.json) lists each component as copied, opt-in or excluded, with the reason |

## No-loss inventory

`reference/inventory-1.x.json` lists every user-visible surface of Dryas 1.x: MCP tools and parameters, commands, skills, agents, allowed tools, plugin and settings hooks, chain stages, permissions, env keys, installer flags, thresholds, Jev log fields and `/tune` report lines. `python tools/inventory.py --check` (run by `install/tests/test_inventory.py` in CI) fails when one of them disappears unless `reference/inventory-map.json` maps it to the entry that replaces it, or to `extra:<component>` when it lives on in an optional component. The baseline is written once and never regenerated to make a check pass.

## Conformance

`met` / `partial` / `not met` for the Claude Code (CC) and Codex (CX) editions.

| Rule | CC | CX | How |
| --- | --- | --- | --- |
| WF-1 | met | met | `/orchestrate` skill; `$dryas:orchestrate` in Codex |
| WF-2 | met | met | Brainstorm-first rule in the always-loaded rules; `dryas:brainstorm` |
| WF-3 | met | met | `dryas:brainstorm` writes the design doc before orchestration |
| WF-4 | met | met | Rules: single-file fix runs plainly; review still applies |
| WF-5 | met | met | `claude/CLAUDE.md.template`, injected by the plugin's SessionStart hook; `codex/AGENTS.md.template`, injected by the Codex plugin's SessionStart hook |
| MEM-1 | met | met | One project-memory layer: Dryas memory (`dryas.db`), or Ruflo when chosen with `--memory ruflo`, never both. On Codex through the `jev` MCP memory tools |
| MEM-2 | met | met | Namespace = main repo folder name |
| MEM-3 | met | met | Orchestrate skill: `memory_search` first, `memory_store` on return; Claude Code's `mem-task` hook also records the outcome, Codex stores only when the agent calls `memory_store` |
| MEM-4 | met | met | Outcomes only; `memory_store` refuses secret-shaped values and file contents (`memstore.py`, `redact.py`); the same tool on both |
| MEM-5 | met | met | Claude Code: `memhooks.py` stages are observe-only, exit 0 and are budgeted at 2 s, on `memdb.py` that degrades instead of failing. Codex: the memory tools return a degraded result rather than an error (`memory_mcp.py`); it has no memory hooks to block |
| MEM-6 | met | not met | `/handoff` and compaction hooks are Claude Code only; Codex has no memory hooks (`mem-session-start` and the other memory stages are Claude Code only), so nothing is recorded or restored for it unless the agent calls the tools |
| GOV-1 | met | met | `Scope:` in each plan section |
| GOV-2 | partial | partial | Hook denies Edit/Write (and Codex `apply_patch`); shell-command edits are a known limit |
| GOV-3 | met | met | Rule in always-loaded rules |
| GOV-4 | met | met | Rule in always-loaded rules; installer dry-runs and backs up |
| GOV-5 | met | met | `/commit` never pushes |
| GOV-6 | met | met | The judge (local or Jev) answers only; thresholds in `~/.dryas/jev/thresholds.json` |
| GOV-7 | met | met | `gate.py` never allows, with either judge; fails to no decision |
| GOV-8 | met | met | Jev MCP `log_override` (`mcp__plugin_dryas_jev__log_override` in Claude Code) |
| GOV-9 | met | met | `/tune` proposes; human approves each change |
| GOV-10 | met | met | Only the optional OpenRouter key (needed for `--judge jev` only), from `OPENROUTER_API_KEY` or the plugin option (Claude Code secure storage), never written by Dryas; `redact.py` |
| GOV-11 | met | met | `chain.py` runs `chain.json` stages in order: scope lock, gate, memory, observer. The memory stages are Claude Code only |
| EXE-1 | met | met | `dryas:worktree` |
| EXE-2 | met | met | `.orchestrate/PLAN.md`, globally git-ignored |
| EXE-3 | met | met | `planfile.py section` |
| EXE-4 | met | met | TDD gate in orchestrate; tester executor |
| EXE-5 | met | partial | Rule in orchestrate skill; Codex without sub-agents does tasks itself, one at a time |
| EXE-6 | met | met | `executor.md` rule 5 |
| EXE-7 | met | met | `executor.md` report block |
| EXE-8 | met | met | The `swarm_init` ledger (hierarchical) on the `jev` server; Codex sub-agents |
| ESC-1 | met | met | `executor.md` `model: sonnet`; Codex cheaper model first |
| ESC-2 | met | met | `thresholds.json` `escalation` |
| ESC-3 | met | met | Orchestrate skill |
| ESC-4 | met | met | pstack picks: systematic-debugging before each climb |
| ESC-5 | met | met | Jev MCP `log_escalation` (`mcp__plugin_dryas_jev__log_escalation` in Claude Code) |
| ESC-6 | met | met | Orchestrate skill |
| REV-1 | met | met | `/wreview` / `$wreview` |
| REV-2 | met | met | Two-stage review |
| REV-3 | met | met | `dryas:verify` |
| REV-4 | met | met | `/interrogate` / `$interrogate` |
| REV-5 | met | met | Orchestrate finish step |
| REV-6 | met | met | `/benchmark-checklist` |

Operational detail for all of this is in [docs/workflow.md](../docs/workflow.md).
