# Harnesses

## Claude Code

Supported. This is where the whole workflow runs: commands, agents, the scope lock hook and the Jev chain. See [Claude Code](https://docs.claude.com/en/docs/claude-code).

## Codex

Supported: rules, skills, MCP, and the safety and routing hooks. Install with `--harness codex` or `--harness both` (see [install.md](install.md)).

Codex gets: the `AGENTS.md` rules block; the skills `$orchestrate`, `$wplan`, `$wreview`, `$commit`, `$tune`, `$interrogate`, `$benchmark-checklist`; the scope lock (including `apply_patch` edits, which are checked file by file and denied when the patch cannot be read), the Jev gate and the Jev route hint (`escalate: yes/no` instead of `opus: yes/no`); the `jev` and `ruflo` MCP servers. With pstack picks, Codex runs the same root-cause, interrogate and cleanup steps; its interrogate panel is two Codex sub-agents (cheaper, then stronger).

Claude Code only: context-window warnings, compaction keep/restore, `/handoff`, the Ruflo hooks, the `executor` agent and the Sonnet → Opus → Fable ladder, FlowObserve, the read-only executor review panel (scope lock with an empty Scope). In Codex, use its own sub-agents and models: cheaper first, stronger on failure, every step logged with `log_escalation`.
