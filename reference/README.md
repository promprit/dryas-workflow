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

`met` / `partial` / `not met` for the Claude Code (CC), Codex (CX) and OpenCode (OC) editions.

| Rule | CC | CX | OC | How |
| --- | --- | --- | --- | --- |
| WF-1 | met | met | met | `/orchestrate` skill; `$dryas:orchestrate` in Codex. OpenCode: `/orchestrate` command and `dryas-orchestrate` skill |
| WF-2 | met | met | met (headless `opencode run` cannot approve) | Brainstorm-first rule in the always-loaded rules; `dryas:brainstorm`. OpenCode: the rules and `dryas-brainstorm` ask the user for approval; a gate `ask` blocks until the user replies `dryas allow <code>` |
| WF-3 | met | met | met | `dryas:brainstorm` writes the design doc before orchestration. OpenCode: `dryas-brainstorm` skill |
| WF-4 | met | met | met | Rules: single-file fix runs plainly; review still applies. OpenCode: the rules, injected by the plugin |
| WF-5 | met | met | met | `claude/CLAUDE.md.template`, injected by the plugin's SessionStart hook; `codex/AGENTS.md.template`, injected by the Codex plugin's SessionStart hook. OpenCode: `dryas.ts` injects `opencode/dryas/AGENTS.md.template` through the system-prompt hook |
| MEM-1 | met | met | met | One project-memory layer: Dryas memory (`dryas.db`), or Ruflo when chosen with `--memory ruflo`, never both. On Codex through the `jev` MCP memory tools. OpenCode: through the `jev` MCP memory tools (`jev_memory_search`, `jev_memory_store`) |
| MEM-2 | met | met | met | Namespace = main repo folder name. OpenCode: same tools |
| MEM-3 | met | met | met | Orchestrate skill: `memory_search` first, `memory_store` on return; Claude Code's `mem-task` hook also records the outcome, Codex stores only when the agent calls `memory_store`. OpenCode: `dryas-orchestrate` skill calls the memory tools; no `mem-task` hook, so the outcome is stored only when the agent calls `jev_memory_store` |
| MEM-4 | met | met | met | Outcomes only; `memory_store` refuses secret-shaped values and file contents (`memstore.py`, `redact.py`); the same tool on both. OpenCode: same `memory_store` refusal |
| MEM-5 | met | met | met | Claude Code: `memhooks.py` stages are observe-only, exit 0 and are budgeted at 2 s, on `memdb.py` that degrades instead of failing. Codex: the memory tools return a degraded result rather than an error (`memory_mcp.py`); it has no memory hooks to block. OpenCode: the memory tools degrade instead of failing; there are no memory hooks to block |
| MEM-6 | met | not met | partial: plan 2 | `/handoff` and compaction hooks are Claude Code only; Codex has no memory hooks (`mem-session-start` and the other memory stages are Claude Code only), so nothing is recorded or restored for it unless the agent calls the tools. OpenCode: memory hook stages, compaction keep/restore and `/handoff` are not on OpenCode yet |
| GOV-1 | met | met | met | `Scope:` in each plan section. OpenCode: `Scope:` in each plan section |
| GOV-2 | partial | partial | partial | Hook denies Edit/Write (and Codex `apply_patch`); shell-command edits are a known limit. OpenCode: `dryas.ts` throws in `tool.execute.before` for edit, write and patch tools; shell-command edits are a known limit |
| GOV-3 | met | met | met | Rule in always-loaded rules. OpenCode: rule in the injected rules |
| GOV-4 | met | met | met (headless `opencode run` cannot approve) | Rule in always-loaded rules; installer dry-runs and backs up. OpenCode: rule in the injected rules; installer dry-runs, and setup never edits `opencode.json`; an `ask` needs the user's `dryas allow <code>` |
| GOV-5 | met | met | met | `/commit` never pushes. OpenCode: `/commit` never pushes |
| GOV-6 | met | met | met | The judge (local or Jev) answers only; thresholds in `~/.dryas/jev/thresholds.json`. OpenCode: the same judge and thresholds |
| GOV-7 | met | met | met (headless `opencode run` cannot approve) | `gate.py` never allows, with either judge; fails to no decision. OpenCode: `dryas.ts` blocks a gate `ask` with a reason and a 4-hex code and never allows by itself; only the user's `dryas allow <code>` in a root session allows that call once. It never changes OpenCode's permission settings; a failure gives no decision |
| GOV-8 | met | met | met | Jev MCP `log_override` (`mcp__plugin_dryas_jev__log_override` in Claude Code). OpenCode: `jev_log_override` on the `jev` MCP server |
| GOV-9 | met | met | met | `/tune` proposes; human approves each change. OpenCode: `/tune` proposes; human approves |
| GOV-10 | met | met | met | Only the optional OpenRouter key (needed for `--judge jev` only), from `OPENROUTER_API_KEY` or the plugin option (Claude Code secure storage), never written by Dryas; `redact.py`. OpenCode: same key handling and `redact.py` |
| GOV-11 | met | met | partial: plan 2 | `chain.py` runs `chain.json` stages in order: scope lock, gate, memory, observer. The memory stages are Claude Code only. OpenCode: `dryas.ts` runs scope lock then gate through the chain; the memory stages arrive in plan 2 |
| EXE-1 | met | met | met | `dryas:worktree`. OpenCode: `dryas-worktree` skill |
| EXE-2 | met | met | met | `.orchestrate/PLAN.md`, globally git-ignored. OpenCode: same plan file |
| EXE-3 | met | met | met | `planfile.py section`. OpenCode: `planfile.py section` |
| EXE-4 | met | met | met | TDD gate in orchestrate; tester executor. OpenCode: `dryas-orchestrate` skill |
| EXE-5 | met | partial | met | Rule in orchestrate skill; Codex without sub-agents does tasks itself, one at a time. OpenCode: `dryas-orchestrate` skill dispatches `dryas-executor-<tier>` subagents |
| EXE-6 | met | met | met | `executor.md` rule 5. OpenCode: executor agent files carry the rule |
| EXE-7 | met | met | met | `executor.md` report block. OpenCode: executor agent files carry the report block |
| EXE-8 | met | met | met | The `swarm_init` ledger (hierarchical) on the `jev` server; Codex sub-agents. OpenCode: `jev_swarm_init` ledger; scope lock per executor subagent |
| ESC-1 | met | met | met | `executor.md` `model: sonnet`; Codex cheaper model first. OpenCode: `dryas-executor-fast` first; models from `--tier-*` |
| ESC-2 | met | met | met | `thresholds.json` `escalation`. OpenCode: same `thresholds.json` |
| ESC-3 | met | met | met | Orchestrate skill. OpenCode: `dryas-orchestrate` skill |
| ESC-4 | met | met | met | pstack picks: systematic-debugging before each climb. OpenCode: same pstack picks |
| ESC-5 | met | met | met | Jev MCP `log_escalation` (`mcp__plugin_dryas_jev__log_escalation` in Claude Code). OpenCode: `jev_log_escalation` |
| ESC-6 | met | met | met | Orchestrate skill. OpenCode: `dryas-orchestrate` skill |
| REV-1 | met | met | met | `/wreview` / `$wreview`. OpenCode: `/wreview` command |
| REV-2 | met | met | met | Two-stage review. OpenCode: two-stage review |
| REV-3 | met | met | met | `dryas:verify`. OpenCode: `dryas-verify` skill |
| REV-4 | met | met | met | `/interrogate` / `$interrogate`. OpenCode: `/interrogate` command |
| REV-5 | met | met | met | Orchestrate finish step. OpenCode: `dryas-orchestrate` finish step |
| REV-6 | met | met | met | `/benchmark-checklist`. OpenCode: `dryas-benchmark-checklist` skill |

Operational detail for all of this is in [docs/workflow.md](../docs/workflow.md).
