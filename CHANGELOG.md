# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## 2.0.1 - 2026-10-15

### Fixed

- **Timing test flake.** The memory hook's locked-store test measures the lock wait against the same hook run unlocked, so slow interpreter start-up on a CI runner no longer fails it; a hard 8 s check still catches a hang.

## 2.0.0 - 2026-10-15

Dryas 2.0 owns its core. The judge, the memory and the process skills ship in this repo with no third-party dependency, no Node and no key; Ruflo, Superpowers and the Jev model stay as optional extras. The change is additive: every 1.x tool, flag, hook, skill and record keeps working.

### Added

- **Local judge and providers.** A deterministic judge (`judge: local`) decides gate and routing questions with no key and no network. Provider slots: `judge: local | jev`, `judge.shadow: local | jev | none`, `memory: dryas | ruflo | none`, `process: dryas | superpowers`.
- **Task-level judgement, in shadow.** The judge can score and review a whole task instead of every edit. All switches are off by default; `/tune` reports the evidence before anything is turned on.
- **Dryas memory** and its tools on the existing `jev` MCP server (same name, same six tools). Memory stages join the hook chain in GOV-11 order (scope lock, gate, memory, observer); each is observe-only, exits 0 and is budgeted at 2 s.
- **Background consolidation.** Memory consolidates outside the hook budget, per namespace, with a lock whose stale holder is taken over, a heartbeat, a retry marker and failure backoff.
- **`dryas memory`** command (`claude/bin/dryas`, `dryas.cmd` on Windows): `dryas memory import-ruflo`, `dryas memory consolidate` and `dryas memory stats`.
- **Eight Dryas process skills** (brainstorm, plan, tdd, debug, verify, review-request, review-receive, worktree), so the process no longer needs Superpowers.
- **Installer flags** `--judge local|jev`, `--with-ruflo`, `--with-superpowers`, `--with-design`. Aliases keep working: `--no-jev` means `--judge local`; `--no-ruflo`, `--no-superpowers` and `--no-design` keep their meaning; `--openrouter-key` implies `--judge jev`. Preflight needs Python 3.9+ only; Node, npm and the path-with-spaces check apply only with Ruflo.
- **Judge scorecard.** A labelled corpus (`reference/judge-corpus/`) and `tools/judge_score.py --check` measure the local judge in CI. The scorecard downgrades a deny to an ask where the corpus allows it and counts a missed deny as a failure.
- **`/tune` additions:** judge disagreements as corpus candidates, allowlist proposals from approved asks (read-only commands only; a dangerous or destructive prefix is never proposed and `/tune apply gate.allowlist` refuses one typed by hand), lines changed per task (overall and by start tier), and memory counts. Gate outcomes are recorded in process.
- **`/retro`**, `GLOSSARY.md` and `.out-of-scope/` decision records.
- **Surgical changes.** Executors trace every changed line to the task; the review checks flag unrelated hunks.
- **Dryas in cloud sessions** (`dryas cloud init | check | update | remove`, also `install.sh --repo` and `install.ps1 -Repo`). It writes a pinned, version-stamped copy of the Dryas core into a GitHub repo: the runtime in `.dryas/`, the skills, commands and executor agent in `.claude/`, the hooks, `.mcp.json`, the rules block and the ignore lines. A claude.ai/code cloud session on that repo then runs the workflow with the local judge, no key and no network. Every run is a dry run until `--yes`. Hand edits are kept unless you pass `--force`, and `remove` takes out exactly what Dryas added. `.dryas/jev/cloud_check.py` (and `/dryas-cloud check`) checks a copy for drift, Mac paths, non-stdlib scripts, licences and NOTICE lines, in a session or in CI. Options: `--with-design`, `--with-own`, `--prefix`, and opt-in redacted session notes with `--persist-memory`. `reference/cloud-bindings.json` lists every core component as copied, opt-in or excluded. See `docs/cloud-sessions.md`.
- **CI:** a no-Node install and end-to-end loop on three operating systems, and the Ruflo tests in their own job on three operating systems. A no-Node check shim keeps the Ruflo path honest.

### Changed

- **Fresh-install defaults:** judge `local`, memory `dryas`, process `dryas`; design plugins stay installed by default. On upgrade an install keeps its current providers until you flip them.
- **Executor rule 5:** commit your own task only when the dispatch prompt allows it; never push, merge or create worktrees.
- **Templates** rewritten as a measured rules pass: `claude/CLAUDE.md.template` went from 4047 to 3247 bytes and `codex/AGENTS.md.template` from 2462 to 2388 bytes. `docs/template-coverage.md` maps every pre-2.0 rule to where it lives now, and a size budget test pins them.
- **Docs and repositioning:** the workflow, memory, governance, install, harness and roadmap docs describe the owned core; the README calls Dryas a target operating model plugin; the spec's section 9.2 example manifest and `reference/dryas.yaml` show the new providers.
- **Allowlist hardening:** user allowlist entries the local judge flags as dangerous or destructive are dropped at load.
- **`--no-jev` means `--judge local`:** the gate stays on with the local judge. A flag-less rerun of a 1.x `--no-jev` install keeps its gates off.
- **Uninstall legacy cleanup** of the Ruflo extra is opt-in, never runs under `--yes`, and removes only what setup recorded.
- **GitHub repo description** (applied 2026-10-15): "Dryas: a target operating model plugin for AI software delivery — framework, draft spec and a reference implementation with its own judge, memory and process skills for Claude Code and Codex." Topics added: ai-software-delivery, target-operating-model, code-review, developer-tools, llm-governance.

### Kept (optional extras)

- **Ruflo** (`--with-ruflo`, `--memory ruflo`): memory and coordination tools. An upgrade of an install that has Ruflo keeps Ruflo memory.
- **Superpowers** (`--with-superpowers`): the rules point at the Dryas skills even when it is installed.
- **Design plugins** (installed by default; `--no-design` skips them).
- **The Jev model** (`--judge jev`): the remote judge through OpenRouter, still needing `OPENROUTER_API_KEY`.

### Upgrade

Cut-over from 1.x, as in `docs/install.md`:

1. Run `install.sh --judge jev --memory dryas`. Memory switches to Dryas; Ruflo stays as an extra unless you pass `--no-ruflo`. The local judge stays as shadow so `/tune` can compare the two.
2. Run `dryas memory import-ruflo`. It copies your Ruflo memory into `dryas.db` read-only, is safe to repeat, and leaves `~/.dryas/ruflo` in place.
3. The legacy cleanup is offered by `--uninstall`, not by setup.
4. Keep working: Ruflo and Superpowers keep running as extras until you drop them.
5. Flip to `--judge local` when `/tune` proposes it.

A rerun with no flags changes nothing about your providers or extras.

## 1.0.2 - 2026-10-13

### Fixed

- **Scope lock fails closed.** While a task is active, a scope-lock stage that times out, crashes or returns unreadable output now denies the edit instead of letting it through; malformed hook input is denied too. The stage is marked `fail_closed` in `chain.json`.
- **Shell writes under scope lock.** With a task active, a Bash command that writes files (`rm`, `mv`, `cp`, `tee`, `sed -i`, redirects, mutating git subcommands, package installs) now asks for confirmation and is logged; the file scope never covered shell writes before. Non-writing commands are unaffected.
- **Jev gate covers `MultiEdit` and `NotebookEdit`**, which skipped the judge before.
- **Redaction** covers `gho_`/`ghu_`/`ghs_`/`ghr_` tokens, `sk_live_`/`sk_test_`, `glpat-`, `hf_`, `npm_`, and `token:`/`secret:` forms; `PGPASSWORD=x` now redacts to `PGPASSWORD=[REDACTED]`.
- **`--yes`** answers every question, as the code always did; the docs said otherwise. `--uninstall` and `--purge` now list what they will remove and ask first (`--yes` skips).
- **Uninstall** offers to remove the third-party plugins setup installed (Ruflo plugins, Impeccable, UI UX Pro Max) and the global `ruflo` npm package when no other account uses it; `--keep-extras` keeps them. Marketplaces are never removed; the commands are printed.
- A missing Node.js now says only Ruflo needs it and suggests `--no-ruflo`.
- `claude/bin/dryas-py` falls back to `python` when `python3` is absent (Windows Git Bash).
- A Codex `apply_patch` touching several files reaches the Jev gate with every path, so a sensitive file in the patch is still judged. Build and packaging file names match case-insensitively and by prefix (`Dockerfile.dev`, `requirements-dev.txt`, `build.gradle.kts`). The log directory is made private on upgrade too, not only when created. A file tool call with no path is denied while a task is active.

### Changed

- **Less latency per tool call.** The PreToolUse hook matches only `Bash|Edit|Write|MultiEdit|NotebookEdit` instead of every tool, so Read, Grep, Glob and MCP calls no longer start Python. Edits to ordinary files inside the project skip the remote judge; `.git/`, dotfiles, CI config, build manifests, scripts and key files are still judged. `jev_client` is imported only when a call is made, and one deadline covers the whole request.
- **Jev input is labelled untrusted.** The gate and handoff send commands, paths and session items under `untrusted_*` fields with an instruction to judge them as data.
- `calls.jsonl` rotates at 5 MB (one backup, `calls.jsonl.1`); the log directory is created with mode 0700.
- Commands and skills declare `allowed-tools`, so they work and prompt less without the setup script. The executor agent gets `Grep` and `Glob`.
- The orchestrate skill triggers on `/orchestrate`, a request to dispatch executors or an approved multi-step plan rather than any multi-file task; its Jev question reference moved to `skills/orchestrate/jev-questions.md`.
- The SessionStart rules add one line when the Dryas deny rules are missing from `settings.json`, that is when the plugin was added without running setup.
- `tools/sync_codex_plugin.py --check` and CI also check the skills shared by both editions for drift.
- `tools/release_check.py` and a CI test fail when the plugin, marketplace, Codex plugin, Jev MCP server and CHANGELOG versions disagree.
- Roadmap: Phase 4, Jev judges the task instead of every edit.

## 1.0.1 - 2026-10-13

### Fixed

- **Default Claude config dir.** Setup, uninstall and `tools/release_check.py` no longer set `CLAUDE_CONFIG_DIR` when running `claude` for the default config dir `~/.claude`. `CLAUDE_CONFIG_DIR` stays set only if you exported it for `~/.claude` itself; one exported for another dir is ignored for `~/.claude`. With it set, Claude Code reads `~/.claude/.claude.json` instead of `~/.claude.json`, so your user-scope MCP servers were invisible to the installer and a stub `~/.claude/.claude.json` was created.
  - Setup now removes a user-scope `jev` MCP server left by the old copy install when the `jev_mcp.py` it runs no longer exists. This also covers custom config dirs such as `~/.claude-team`, where the old entry usually lives in `~/.claude.json`. Your own `jev` server is never touched.
  - `release_check` warns (does not fail) about such a stale `jev` entry and about a stub `~/.claude/.claude.json` (safe to delete after checking it holds nothing you need).

## 1.0.0 - 2026-10-13

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
