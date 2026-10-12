# Dryas as a Claude Code plugin

Date: 2026-10-12. Status: approved; amended by the plan (A1–A4), see [Amendments](#amendments). **Contested: no** (packaging and paths; the scope lock and Jev gate keep their deny behavior).

## Goal

Ship the Claude Code reference implementation as a plugin so it installs per Claude config dir. One person can run Dryas on several accounts (for example a personal and a Team account, side by side in T3 Code, each with its own `CLAUDE_CONFIG_DIR`) with one shared state store and FlowObserve working for all of them. Success: `install.sh --claude-dir <dir>` run against two config dirs gives both the full workflow (rules, hooks, scope lock, Jev chain, agents, commands, skills, Jev MCP), and `/tune` and FlowObserve see the work of both.

## Problem

The installer copies files into `~/.claude` and hardcodes that path (`install/run_cmd.py`: `cd = home / ".claude"`). A second config dir gets plain Claude Code: no rules, no hooks, no FlowObserve. State (`jev/logs`, `thresholds.json`, handoff, compact) also lives under `~/.claude/jev`, so it is tied to one account.

## Decisions (from the brainstorm)

- **Plugin plus a thin `dryas setup`.** The plugin carries everything a plugin can carry. `setup` writes only what a plugin cannot (`model`, `env`, `permissions`), installs the plugin and its optional companions into a target config dir, and migrates old installs. `install.sh` / `install.ps1` stay the entry point.
- **One shared state root**, `$DRYAS_DATA_ROOT` (default `~/.dryas`), for every account. Handoff and compact files are already keyed by session, so accounts never collide.
- **This repo is the marketplace.** One plugin, `dryas`.
- **Codex is unchanged.** `codex/` and the Codex installer path stay as they are.

## Plugin facts this design relies on

From the Claude Code plugin docs (code.claude.com/docs/en/plugins, read 2026-10-12):

- A plugin can ship `hooks/hooks.json`, `agents/`, `commands/`, `skills/`, `.mcp.json`. Hook processes get `CLAUDE_PLUGIN_ROOT` (the installed version dir; changes on every update) and `CLAUDE_PLUGIN_DATA`.
- A plugin `settings.json` honors only `agent` and `subagentStatusLine`. `env`, `permissions` and `model` are dropped.
- A `CLAUDE.md` in the plugin is not loaded. A SessionStart hook's `additionalContext` is injected as a system reminder, capped at 10,000 characters.
- `plugin.json` `dependencies` can name other plugins with a semver range. Cross-marketplace dependencies need `allowCrossMarketplaceDependenciesOn` in the root `marketplace.json`.
- `userConfig` with `sensitive: true` keeps a value in secure storage; hooks read it as `CLAUDE_PLUGIN_OPTION_<KEY>`. `claude plugin install` takes `--config KEY=VALUE` and needs `-y` without a TTY.
- Plugin hooks are enabled by installing the plugin; there is no per-hook approval. An org policy with `allowManagedHooksOnly` blocks them.
- Not documented: whether plugin storage follows `CLAUDE_CONFIG_DIR`. `setup` verifies it after install (see below).
- Plugin names starting with `claude-`, `anthropic-` or `cc-plugin-` are rejected.

## Layout and packaging

- `.claude-plugin/marketplace.json` at the repo root: one plugin `dryas`, source `./claude`, and `allowCrossMarketplaceDependenciesOn: ["claude-plugins-official"]`.
- `claude/.claude-plugin/plugin.json`: name `dryas`, version, `dependencies: [{"name": "superpowers", "marketplace": "claude-plugins-official", "version": "<tested range from components.json>"}]`, and `userConfig.openrouter_key` (`string`, `sensitive: true`).
- `claude/hooks/hooks.json`: the hooks of today's `settings.fragment.json` `core` and `jev` parts, with `$CD` replaced by `${CLAUDE_PLUGIN_ROOT}` and `$PY` by `${DRYAS_PY:-python3}`. Example:
  `"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/jev/chain.py" pretool`
- `claude/agents/`, `claude/commands/`, `claude/skills/` stay where they are and load as plugin parts.
- `claude/.mcp.json` registers the Jev MCP server (today `install/claude_mcp.py` registers it). It passes the key as `${user_config.openrouter_key}`.
- **Rules.** `claude/CLAUDE.md.template` stays the single source. A new SessionStart hook (`claude/jev/rules_inject.py`, matchers `startup`, `resume`, `clear`, `compact`) returns it as `additionalContext`, with the `<!-- pstack-picks -->` blocks resolved from the selected components. The existing `compact` and `clear` restore hooks keep running; the rules hook is a separate entry.
- `settings.fragment.json` keeps only what `setup` merges into user settings: `model`, `env`, `permissions`. Its hooks move to `hooks.json`.

## Runtime, paths and state

- **Python.** `setup` writes the interpreter it runs with to `env.DRYAS_PY` in the target `settings.json`. Hooks fall back to `python3` when it is unset. On Windows, Claude Code runs hook commands through Git Bash, so the same command line is expected to work; the first plan task proves this on the Windows CI runner before the rest is built. If it fails, a `claude/bin/dryas-py.cmd` launcher is added (otherwise out of scope).
- **State root.** New `claude/jev/paths.py`, the only place that knows the layout:
  - `data_root()` = `$DRYAS_DATA_ROOT` or `~/.dryas`
  - `jev/logs/`, `jev/thresholds.json`, `jev/handoff/`, `jev/compact/`, `chain.local.json`, `accounts.json`
  - `ruflo/` (unchanged layout, now also `ruflo/helpers/`)
  - `projects_dir()` = `$CLAUDE_CONFIG_DIR/projects`, falling back to `~/.claude/projects`
  
  `jevlog.py`, `thresholds.py`, `handoff_paths.py`, `handoff.py`, `compact_keep.py` and `context_watch.py` call it instead of hardcoding `~/.claude/jev/...`. The existing `JEV_*` env overrides still win, so current tests keep working.
- **Chain config.** `claude/jev/chain.json` in the plugin is read-only defaults. `chain.py` merges `~/.dryas/chain.local.json` on top by event and stage name; only `enabled` and `timeout` may be overridden. `$CD` and `$PY` in stage commands are resolved at run time from `CLAUDE_PLUGIN_ROOT` and `DRYAS_PY`. A missing local file means defaults; an unreadable one means defaults plus one warning line on stderr, never a block.
- **`/handoff` follows the account.** Reading transcripts through `projects_dir()` fixes `/handoff` on a second config dir.
- **Permissions.** `setup` writes allow rules with absolute paths into each target dir: `Read(~/.dryas/**)` and the `planfile.py`, `handoff.py save` and `tune.py report` commands under the installed plugin root. These replace the `~/.claude/jev/**` rules.

## `dryas setup`

Lives in `install/`, reusing `dryas_install.py`, `settings_merge.py`, `ruflo_helpers.py` and `platform_util.py`. `run_cmd.py` gains `--claude-dir` (default `$CLAUDE_CONFIG_DIR`, else `~/.claude`). Steps for one target dir, in order:

1. **Preflight.** Python 3.9+, git, the `claude` CLI; Node and npm when Ruflo is selected.
2. **Plugin install.** With `CLAUDE_CONFIG_DIR=<dir>` in the child env: `claude plugin marketplace add <repo or local path> --scope user`, then `claude plugin install dryas@dryas-workflow --scope user -y`, adding `--config openrouter_key=...` when `--openrouter-key` or `OPENROUTER_API_KEY` is given. Then verify that `<dir>/plugins/installed_plugins.json` lists `dryas`. If it does not, stop with an error naming the dir; settings are not touched.
3. **Optional companions.** Ruflo and the design plugins install per dir from `components.json`, as today, unless `--no-ruflo` / `--no-design`. The Ruflo npm package installs globally once.
4. **Settings merge.** `model`, `env` (`DRYAS_PY`, `DRYAS_DATA_ROOT`, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, the Ruflo vars) and `permissions` (allows above, Superpowers denies). Same rules as today: ask before editing, keep a backup, record exactly what was added.
5. **Ruflo helpers.** Generated and patched into `~/.dryas/ruflo/helpers/` once; skipped when present and current. Ruflo hook and env paths point there.
6. **Components.** Unselected components (`--no-jev`, `--no-ruflo`, `--no-pstack-picks`) become `enabled: false` stages in `chain.local.json` and are skipped by the rules hook. `--flowobserve` sets the FlowObserve stages to `enabled: true`.
7. **Accounts list.** Add the dir to `~/.dryas/accounts.json` (`{"claude_dirs": [...]}`).

### Migration from a copy install

When the target dir has an old install record:

1. Move `jev/logs/`, `jev/thresholds.json`, `jev/handoff/`, `jev/compact/` into `~/.dryas/jev/`. When a destination file exists (a second account migrated earlier), append logs and keep the newer `thresholds.json`, printing which one was kept.
2. Copy the user's stage settings from the old `jev/chain.json` into `chain.local.json` (the same name-match rule `render.chain_bytes` uses today).
3. Run the existing uninstall for that dir (copied files, the `CLAUDE.md` block, old settings entries, old `jev` MCP registration).
4. Run setup.

Data moves before anything is removed. Running setup twice is a no-op.

### Uninstall

`setup --uninstall --claude-dir <dir>` uninstalls the plugin (with `--keep-data`) and removes only the settings entries it recorded, from that dir only, and drops the dir from `accounts.json`. `~/.dryas` stays unless `--purge` is given and no other dir is listed in `accounts.json`.

## FlowObserve

- The FlowObserve chain stages run `$HOME/.flowobserve/bin/fo_hook.py`; `$HOME` is the same for every account, so one `chain.local.json` flag covers all of them.
- Escalations, Jev spend and per-stage timings come from the Dryas logs, now in one `~/.dryas/jev/logs` for all accounts.
- If FlowObserve's transcript reader only reads `~/.claude/projects`, it misses other dirs. Dryas publishes `~/.dryas/accounts.json` for it. The FlowObserve change itself is a follow-up in that repo.

## Error handling

- Hooks fail open as today, except the scope lock and the Jev gate, which keep their current deny behavior.
- A chain stage whose command still contains an unresolved `$CD` or `$PY` is skipped with one log line naming the stage.
- `setup` stops before the settings merge if the plugin install or its verification fails, so a dir is never half set up.
- If an org policy blocks plugin hooks (`allowManagedHooksOnly`), the release check reports that hooks did not fire; `docs/install.md` explains the cause.

## Testing

All in the existing CI matrix (macOS, Ubuntu, Windows; Python 3.9 and 3.12). There is no Claude CLI in CI; `install/tests/fakecli.py` records plugin calls and the env they ran with.

- **Plugin shape:** `plugin.json` and `marketplace.json` parse and have the required fields; every `${CLAUDE_PLUGIN_ROOT}` path in `hooks.json` and `.mcp.json` exists; the plugin name is allowed; the rendered rules stay under 10,000 characters for every component combination.
- **Windows hook command:** the `hooks.json` command line runs under Git Bash on the Windows runner (first plan task).
- **Paths:** `paths.py` defaults, `DRYAS_DATA_ROOT` override, `JEV_*` overrides winning, `projects_dir()` following `CLAUDE_CONFIG_DIR`.
- **Chain merge:** overrides by name, only `enabled` and `timeout` honored, broken local file falls back with a warning, unresolved placeholders skipped.
- **Rules hook:** output is the template with gated blocks resolved; valid SessionStart JSON.
- **Setup end to end:** two temp config dirs; plugin calls carry the right `CLAUDE_CONFIG_DIR`; each settings merge touches only its own dir; `accounts.json` lists both; verification failure stops before the merge.
- **Migration:** old install fixture moves to the new layout with logs and thresholds intact; second run is a no-op; second account merges logs.
- **Uninstall:** one dir removed, the other still set up; `~/.dryas` kept without `--purge`.
- **Portability:** `test_portability.py` updated: the `$PY` / `$CD` placeholder rule becomes the `${DRYAS_PY:-python3}` / `${CLAUDE_PLUGIN_ROOT}` rule for hook and MCP commands.

## Docs

- `docs/install.md`: Claude sections rewritten for plugin plus setup; `--claude-dir`, migration, uninstall, the `allowManagedHooksOnly` note.
- `docs/harnesses.md`: new "Several accounts (T3 Code, personal and team)" section.
- `README.md`: install block and "One source for the rules" bullet.
- `CONTRIBUTING.md`: portability rules for the new placeholders.
- `reference/README.md` conformance table: bindings that moved.
- `docs/release-check.md`: check that plugin hooks fire in each set-up dir.

## Out of scope

- FlowObserve reading `accounts.json` (FlowObserve repo).
- The Codex harness and its installer path.
- A Windows `.cmd` launcher, unless the Git Bash check fails.
- Publishing to an external marketplace.

## Amendments

The plan (`docs/superpowers/plans/2026-10-12-plugin-packaging.md`) fixed four things this spec missed:

- **[A1] Markdown tokens.** Agents, commands and skills used `{{CD}}` / `{{PY}}` tokens and `<!-- pstack-picks -->` blocks that the copy installer rendered. A plugin ships them raw. `{{CD}}` becomes `${CLAUDE_PLUGIN_ROOT}` (Claude Code substitutes it in plugin skill, command and agent bodies). `"{{PY}}" -X utf8` becomes a launcher, `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py"`, which runs `"${DRYAS_PY:-python3}" -X utf8 "$@"`. After substitution the Bash command holds only literal absolute paths, so permission rules can match it. `<!-- pstack-picks -->` blocks stay in the files; when pstack-picks is off, the rules hook adds one line telling Claude to skip them. Hardcoded `~/.claude/jev/...` and `~/.claude/skills/...` paths in Markdown are rewritten.
- **[A2] Codex still reads `~/.claude`.** Codex hooks and MCP point at `~/.claude/jev/*.py` and `~/.claude/ruflo/*`. To keep Codex unchanged, the copy install stays for `--harness codex|both`, but copies only runtime files (`jev/`, `ruflo/`, `pstack/`, and `docs/dryas-workflow.md`), never `agents/`, `commands/`, `skills/` (those would duplicate the plugin's).
- **[A3] Jev key in hooks.** `gate.py`, `route.py` and `compact_keep.py` call OpenRouter from hooks. Hooks get the plugin option as `CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY`, not `OPENROUTER_API_KEY`. The MCP server gets it as `DRYAS_OPENROUTER_KEY` through `env` in `.mcp.json` (not as `OPENROUTER_API_KEY`, so an empty option cannot hide the shell key). `jev_client.api_key()` reads `OPENROUTER_API_KEY` first, then `DRYAS_OPENROUTER_KEY`, then `CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY`, and ignores blank or unexpanded `${...}` values.
- **[A4] Ruflo stays in user settings.** Ruflo hooks are optional and point at helpers in `~/.dryas`, so they stay in the settings fragment that `setup` merges (not in `hooks.json`). The helpers and the MCP shim live in `~/.dryas/ruflo` (`helpers/`, `mcp-shim/`) because the shim's `dist` link must not be created inside the plugin (the repo clone). `ruflo/run.py` stays in the plugin.

Also changed during implementation:

- A malformed `chain.local.json` (wrong shapes) falls back to the defaults instead of breaking the chain.
- On Windows the `Read` allow rule for the data root uses the `//c/...` form.
- The executor agent is `dryas:executor`; the Jev MCP tools are `mcp__plugin_dryas_jev__*`.
- The workflow reference is `~/.dryas/docs/dryas-workflow.md` (setup copies it from `docs/workflow.md`); local notes move to `~/.dryas/docs/dryas-local.md`.
- The Codex runtime-only copy also gets the Ruflo runtime in the data root.
- `--purge` removes only the entries Dryas owns in `~/.dryas`, and only when no other account is listed in `accounts.json` (it refuses when that file is missing or unreadable).
