# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## 1.0.0 - Unreleased

### Added

- **Claude Code plugin** `dryas@dryas-workflow`, served from this repo as its own marketplace (`.claude-plugin/marketplace.json`, plugin in `claude/`). It is a community plugin, not part of `claude-plugins-official`.
  - Setup runs once per Claude config dir (`--claude-dir`, default `$CLAUDE_CONFIG_DIR` or `~/.claude`): it adds the marketplace, installs the plugin and merges model, env and permission rules into that dir's `settings.json` after asking.
  - Superpowers is a plugin dependency, installed from `claude-plugins-official`.
  - The always-loaded rules are injected by a SessionStart hook instead of a block in `CLAUDE.md`.
  - Claude Code runs the plugin in place from the clone, so `git pull` updates every account at its next session.
- **Codex plugin** with the same id, `dryas@dryas-workflow`, for Codex 0.162.1 or newer: served from the `.agents/plugins/marketplace.json` marketplace (plugin in `codex/`).
  - `install/install.sh --harness codex` (or `--harness both`) sets up one Codex home per run (`--codex-dir`, default `$CODEX_HOME` or `~/.codex`).
  - Hook trust with consent: setup lists the Dryas hooks that are not trusted yet and trusts exactly those only after you agree (`--yes` answers yes); otherwise trust them in Codex with `/hooks`.
  - One marked block in that home's `config.toml` for the Ruflo MCP server, `--no-jev` and the Jev MCP fallback; setup never writes a key there.
  - Codex runs a copy of the plugin: re-run setup for each Codex home after `git pull`.
- **Shared state in `~/.dryas`** for every Claude config dir and Codex home: Jev logs, `/tune` thresholds, handoffs, the workflow reference, `chain.local.json` (component choices) and `accounts.json` (the dirs and homes set up so far). Your notes live in `~/.dryas/docs/dryas-local.md` and are never touched.
- **Several accounts** side by side (for example personal and team, or T3 Code): run setup once per config dir or Codex home; all share `~/.dryas`.
- **Uninstall and purge.** `--uninstall` removes Dryas from one config dir or Codex home: the plugin, only the settings entries, config tables and hook trust that setup recorded, and that entry in `accounts.json`; `~/.dryas` stays. `--purge` on the last account also removes the entries Dryas owns in `~/.dryas` (it keeps `docs/dryas-local.md` and refuses while another account or Codex home is listed).
- `--flowobserve` / `--no-flowobserve` turn the FlowObserve stages of the Jev chain on or off (Claude Code only; with neither flag an existing choice is kept, new installs leave it off).
- `tools/release_check.py` checks an install on this machine, read-only, per Claude config dir (`--claude-dir`, repeatable) and per Codex home (`--codex-dir`, repeatable), including the plugin manifests.
- Jev is bring-your-own-key: set `OPENROUTER_API_KEY` in your shell (Claude Code can also keep it in secure storage with `--openrouter-key`). Without a key, Jev checks are skipped and the workflow still runs.

### Changed

- **Migration from the copy install.** Setup finds an earlier Claude Code copy install in `~/.claude`, moves its state to `~/.dryas` first (logs, handoffs, thresholds you changed, stage choices, local notes) and only then removes it. Re-running resumes; nothing is merged twice.
- **Migration from the Codex copy install.** Setup for a Codex home removes the old `AGENTS.md` block, skills in `~/.agents/skills`, `hooks.json` entries and MCP servers after the plugin is added, then the runtime copy in `~/.claude` once no other Codex home uses it (its state moves to `~/.dryas` first).

### Known limits

- Codex and Claude Code on native Windows are partly unverified: the Codex plugin was verified end to end on Linux with real Codex 0.162.1 and a mock model; real-model and Windows checks are still manual.
- The scope lock covers the file-edit tools (for example Edit, Write and `apply_patch`); writes made by shell commands are not covered.
- Hook command lines in `codex/hooks/hooks.json` are frozen: Codex trusts each hook by a hash of its entry, so a change needs a version bump and setup asks to trust it again.
