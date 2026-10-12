# Harnesses

## Claude Code

Supported. This is where the whole workflow runs: commands, agents, the scope lock hook and the Jev chain. It ships as the plugin `dryas@dryas-workflow`, set up per Claude config dir (see [install.md](install.md#claude-code-plugin-plus-setup)). See [Claude Code](https://docs.claude.com/en/docs/claude-code).

## Codex

Supported: rules, skills, MCP, and the safety and routing hooks. Install with `--harness codex` or `--harness both` (see [install.md](install.md)).

Codex gets: the `AGENTS.md` rules block; the skills `$orchestrate`, `$wplan`, `$wreview`, `$commit`, `$tune`, `$interrogate`, `$benchmark-checklist`; the scope lock (including `apply_patch` edits, which are checked file by file and denied when the patch cannot be read), the Jev gate and the Jev route hint (`escalate: yes/no` instead of `opus: yes/no`); the `jev` and `ruflo` MCP servers. With pstack picks, Codex runs the same root-cause, interrogate and cleanup steps; its interrogate panel is two Codex sub-agents (cheaper, then stronger).

Claude Code only: context-window warnings, compaction keep/restore, `/handoff`, the Ruflo hooks, the `dryas:executor` agent and the Haiku → Sonnet → Opus → Fable ladder, FlowObserve, the read-only executor review panel (scope lock with an empty Scope). In Codex, use its own sub-agents and models: cheaper first, stronger on failure, every step logged with `log_escalation`.

## Several accounts (T3 Code, personal and team)

You can run Dryas on several Claude Code accounts side by side, for example a personal and a Team account in T3 Code. Each account has its own config dir (`CLAUDE_CONFIG_DIR`, for example `~/.claude` and `~/.claude-team`). Run setup once for each:

```
./install/install.sh
./install/install.sh --claude-dir ~/.claude-team
```

Each dir gets the plugin and its own settings merge. All accounts share one state root, `~/.dryas`: Jev logs, `/tune` thresholds, handoffs, `chain.local.json` and the Ruflo runtime. So `/tune` sees the work of every account. Component choices are shared the same way: `chain.local.json` is one file, so a `--no-` flag on one account's setup run turns that component's stages off for every account and for Codex (setup prints a warning naming them). `~/.dryas/accounts.json` lists the config dirs set up so far; uninstall removes a dir from it, and `--purge` only clears `~/.dryas` (logs, thresholds, handoffs; your `dryas-local.md` stays) once no account is left and no Codex install uses it.

FlowObserve reads the Jev logs in `~/.dryas/jev/logs`, so it sees escalations and spend from every account. Its transcript reader still looks in `~/.claude` only; reading transcripts from other config dirs is a FlowObserve follow-up.
