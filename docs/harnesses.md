# Harnesses

| Harness | Status |
| --- | --- |
| Claude Code | Supported: plugin `dryas@dryas-workflow` |
| Codex | Supported: plugin `dryas@dryas-workflow` |
| Pi, OpenCode, Roo, Cursor | Later |


## Claude Code

Supported. This is where the whole workflow runs: commands, agents, the scope lock hook and the Jev chain. It ships as the plugin `dryas@dryas-workflow`, set up per Claude config dir (see [install.md](install.md#claude-code-plugin-plus-setup)). See [Claude Code](https://docs.claude.com/en/docs/claude-code).

## Codex

Supported: rules, skills, MCP (including the memory tools), and the safety and routing hooks. Conformance is partial: full memory-tool parity, but the memory hook stages are not wired for Codex in 2.0 (Codex does run a SessionStart hook, for the rules, so this is a choice pinned by a test, not a missing capability). It ships as a Codex plugin with the same id, `dryas@dryas-workflow` (the `codex/` folder), set up once per Codex home (`CODEX_HOME`) with `install.sh --harness codex` or `--harness both` (see [install.md](install.md#codex-plugin-plus-setup)).

Codex gets: the rules, injected at session start by a SessionStart hook (Codex plugins have no rules file); the plugin skills `$dryas:orchestrate`, `$dryas:wplan`, `$dryas:wreview`, `$dryas:commit`, `$dryas:tune`, `$dryas:interrogate`, `$dryas:benchmark-checklist` (the prefixed form is how Codex lists plugin skills; whether the TUI also takes the short form, such as `$interrogate`, is a manual release check step); the scope lock (including `apply_patch` edits, which are checked file by file and denied when the patch cannot be read), the Jev gate and the Jev route hint (`escalate: yes/no` instead of `opus: yes/no`); the `jev` MCP server from the plugin, which now carries the Dryas memory tools (`memory_search`, `memory_store`, `memory_list`, `memory_forget`, `swarm_init`), and the `ruflo` MCP server from setup only when the Ruflo extra is on. Codex runs plugin hooks only once they are trusted: setup trusts the Dryas hooks after you agree, otherwise trust them in Codex's `/hooks`. With pstack picks, Codex runs the same root-cause, interrogate and cleanup steps; its interrogate panel is two Codex sub-agents (cheaper, then stronger).

The memory hook stages are not wired for Codex in 2.0, so `mem-session-start` is Claude Code only, like every other memory stage: Codex reaches Dryas memory through the MCP tools and writes to it only when the agent calls `memory_store`. That is the line between memory-tool parity and the hook-driven recording that Claude Code adds.

Claude Code only: context-window warnings, compaction keep/restore, `/handoff`, the memory stages (`mem-edit`, `mem-task`, `mem-session-start`, `mem-session-end`) and `gate-outcome`, the Ruflo hooks (extra), the `dryas:executor` agent and the fast → standard → strong → frontier ladder on Claude Code models, FlowObserve, the read-only executor review panel (scope lock with an empty Scope). In Codex, use its own sub-agents and the models configured there (see the tier table in [workflow.md §3](workflow.md)): `fast` tier first, a higher tier on failure, every step logged with `log_escalation`.

## Several accounts (T3 Code, personal and team)

You can run Dryas on several Claude Code accounts side by side, for example a personal and a Team account in T3 Code. Each account has its own config dir. `~/.claude` needs no setting; for any other dir, such as `~/.claude-team`, set `CLAUDE_CONFIG_DIR` to that dir. Run setup once for each:

```
./install/install.sh
./install/install.sh --claude-dir ~/.claude-team
```

Each dir gets the plugin and its own settings merge. All accounts share one state root, `~/.dryas`: Jev logs, `/tune` thresholds, handoffs, `chain.local.json`, the Dryas memory store (`dryas.db`) and, with the extra, the Ruflo runtime. So `/tune` sees the work of every account. Component choices are shared the same way: `chain.local.json` is one file, so a `--no-` flag on one account's setup run turns that component's stages off for every account and for Codex (setup prints a warning naming them). `~/.dryas/accounts.json` lists the config dirs set up so far; uninstall removes a dir from it, and `--purge` only clears `~/.dryas` (logs, thresholds, handoffs; your `dryas-local.md` stays) once no account is left and no Codex home uses it.

Several Codex accounts work the same way: each has its own Codex home (`CODEX_HOME`, for example `~/.codex` and `~/.codex-work`), set up once each with `--codex-dir`. Each home gets its own plugin copy, hook trust and config block, and all share `~/.dryas` (`accounts.json` lists them under `codex_dirs`).

FlowObserve reads the Jev logs in `~/.dryas/jev/logs`, so it sees escalations and spend from every account. Its transcript reader still looks in `~/.claude` only; reading transcripts from other config dirs is a FlowObserve follow-up.

## Later

Pi, OpenCode, Roo and Cursor are planned, not started. Each needs an edition written against the [specification](../spec/dryas-spec-v1.md).
