# Dryas as a Codex CLI plugin

Date: 2026-10-13. Status: implemented; Linux end-to-end verified with real Codex 0.162.1 and a mock model (hooks, rules, scope lock); manual real-model + Windows checks pending. Implementation decisions: [Amendments from the build](#amendments-from-the-build). Originally: approved for autonomous build (the user approved building it on 2026-10-12; decisions marked **[J]** were made by judgment while writing and are listed under [Decisions made by judgment](#decisions-made-by-judgment)). **Contested: no** (packaging, setup and paths; the scope lock and the Jev gate keep their deny behavior).

## Goal

Ship the Codex edition as a Codex CLI plugin, `dryas@dryas-workflow`, set up once per `CODEX_HOME`, the way the Claude Code edition ships as a plugin set up per Claude config dir. Success: `install.sh --harness codex` (or `both`) gives a `CODEX_HOME` the full Codex edition (rules, skills, scope lock, Jev gate, Jev route hint, Jev MCP, Ruflo MCP when selected), with its hooks trusted so they actually fire, and a Codex copy install from today migrates to it with no state lost.

## Problem

Today `install/codex_target.py` copies the Codex edition into four places: a block in `~/.codex/AGENTS.md`, skills in `~/.agents/skills/`, entries in `~/.codex/hooks.json`, and MCP servers registered with `codex mcp add`. Hooks and MCP run Python from a runtime-only copy in `~/.claude` (amendment [A2] of the Claude plugin spec). That has three problems:

1. **The hooks do not fire.** On Codex 0.162.1 every non-managed hook needs persisted trust. `hooks/list` reports today's `~/.codex/hooks.json` entries as `untrusted`, and untrusted hooks are skipped silently. So the scope lock, the Jev gate and the route hint are off until the user reviews them in the TUI `/hooks`, which nothing tells them to do.
2. **Codex keeps `~/.claude` alive.** The runtime copy exists only for Codex and drags the `keep_codex` logic into the Claude migration.
3. **Codex already offers the wrong plugin.** `codex plugin marketplace add <repo>` reads `.claude-plugin/marketplace.json` and offers the Claude edition, whose MCP server cannot start in Codex (`${DRYAS_PY:-python3}` stays literal).

## Codex facts this design relies on

From `scratchpad/codex-plugin-research.md` (Codex CLI 0.162.1, run; `openai/codex` main @ c308e12, read). Tags: [CLI] run, [source] read, [unverified].

- `codex plugin marketplace add <path>`, `codex plugin add NAME@MKT --json` (returns `{pluginId, installedPath, version, authPolicy}`), `codex plugin list --json` (`installed[]` with `pluginId`, `version`, `enabled`), `codex plugin remove`, `codex mcp list --json`, `codex debug prompt-input` (model-visible context, no model call). Everything lives under `CODEX_HOME`. [CLI]
- Marketplace lookup order under a root: `.agents/plugins/marketplace.json` first, `.claude-plugin/marketplace.json` later; the first match wins. Claude Code ignores `.agents/`. [source]
- Manifest: `.codex-plugin/plugin.json` (`name`, `version`, `description`, `interface`, ...); no `userConfig`, `dependencies`, `agents` or `commands`. Default component paths: `skills/`, `hooks/hooks.json`, `.mcp.json`. [source]
- **Install copies** the plugin to `$CODEX_HOME/plugins/cache/<mkt>/<plugin>/<version>/` and **drops symlinks**. Re-running `codex plugin add` refreshes the copy, even at the same version. [CLI]
- Hooks: same schema as `~/.codex/hooks.json`; stdin is Claude-shaped (`tool_name: "Bash" | "apply_patch"`, `tool_input`, `cwd`, `source`, `prompt`); the matcher `Edit`/`Write` also matches `apply_patch`. The hook env has `PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` (same value), `PLUGIN_DATA`, `CODEX_HOME`; the command runs through a shell. SessionStart `hookSpecificOutput.additionalContext` becomes a developer message. [CLI]
- **Trust**: each plugin hook needs `[hooks.state."<pluginId>:hooks/hooks.json:<event_snake>:<group>:<handler>"] trusted_hash = "sha256:..."`. The hash covers the normalized hook entry (event, matcher, command, timeout), not the script. Setup can trust exactly like the TUI: `codex app-server` (JSON-RPC over stdio, one JSON object per line, no `jsonrpc` header) → `initialize` → `initialized` → `hooks/list {cwds}` (each hook: `key`, `pluginId`, `source`, `trustStatus`, `currentHash`) → `config/batchWrite {edits: [{keyPath: "hooks.state", value: {<key>: {trusted_hash}}, mergeStrategy: "upsert"}], reloadUserConfig: true}`. `codex plugin remove` leaves the trust entries behind. [CLI]
- MCP (`.mcp.json`): no variable expansion; `PLUGIN_ROOT` is not in the server env; `"cwd": "."` plus relative `args` works; `command` is not run through a shell. `env_vars: [...]` forwards named variables from Codex's env. A user `[mcp_servers.<name>]` overrides a plugin server of the same name; `[plugins."<id>".mcp_servers.<name>] enabled = false` turns one off. [CLI]
- No instructions/AGENTS.md component: rules come from a SessionStart hook. [source]
- Not verified: Windows behavior (hook shell, `commandWindows` expansion, `python3`), how a user types a plugin skill in the TUI (`$dryas:orchestrate`?), what a Git-marketplace snapshot copies, a real-model run (the probe used a mock Responses server).

## Decisions

- **`codex/` is the plugin root**, self-contained, because the cache copy drops symlinks.
- **One source of truth stays `claude/`.** The runtime the Codex plugin needs from `claude/` is committed as real copies under `codex/`, written by `tools/sync_codex_plugin.py`; a CI test fails when a copy differs from its source.
- **`.agents/plugins/marketplace.json`** at the repo root lists `dryas` with `source: "./codex"`. Codex then shows the Codex edition; Claude Code keeps reading `.claude-plugin/marketplace.json`. Same marketplace name `dryas-workflow` and plugin name `dryas` in both: they live in different tools' config homes, so `dryas@dryas-workflow` never collides.
- **`--harness codex` now means the plugin.** The copy path (`install_codex`, the `~/.claude` runtime copy, `codex/hooks.fragment.json`) is removed, not fixed: hook trust is solved once, for the plugin.
- **Rules by SessionStart hook**: `jev/rules_inject.py --harness codex` returns `codex/AGENTS.md.template` as `additionalContext`. The `~/.codex/AGENTS.md` block goes away.
- **Setup per `CODEX_HOME`**: one dir per run (`--codex-dir`, default `$CODEX_HOME`, else `~/.codex`), like `--claude-dir`. Several Codex accounts = several runs.
- **Hook trust with consent**: setup shows the Dryas hooks and asks (`--yes` answers yes). Declined: nothing is trusted, setup prints how to review them in `/hooks`, and verify reports the hooks as not trusted.
- **Shared state unchanged**: `~/.dryas` and `chain.local.json` as for Claude. `accounts.json` gains `codex_dirs`; purge counts them.

## Layout and packaging

```
.agents/plugins/marketplace.json      # Codex reads this; Claude Code ignores it
codex/
  .codex-plugin/plugin.json           # name dryas, version = claude plugin version, interface
  AGENTS.md.template                  # rules source (read at run time by jev/rules_inject.py)
  hooks/hooks.json                    # SessionStart, UserPromptSubmit, PreToolUse
  .mcp.json                           # jev (cwd ".", relative args, env_vars)
  skills/<name>/SKILL.md              # orchestrate, wplan, wreview, commit, tune, interrogate, benchmark-checklist
  jev/      (synced copy)             # claude/jev/*.py, chain.json, thresholds.json; no tests/
  pstack/   (synced copy)             # claude/pstack/ (skills read its references)
```

- `.agents/plugins/marketplace.json`: `{"name": "dryas-workflow", "interface": {"displayName": "Dryas Workflow"}, "plugins": [{"name": "dryas", "source": "./codex", "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Coding"}]}`.
- `codex/.codex-plugin/plugin.json`: `name`, `version` (equal to `claude/.claude-plugin/plugin.json`; a shape test enforces it), `description`, `keywords`, `interface` (`displayName`, `shortDescription`, `developerName`, `category`, `websiteURL`, at most three `defaultPrompt`s). Component paths are left to the defaults.
- `codex/hooks/hooks.json` (command form from the decisions; `commandWindows` see Windows below):
  - `SessionStart`, matcher `startup|resume|clear|compact`: `"${DRYAS_PY:-python3}" -X utf8 "${PLUGIN_ROOT}/jev/rules_inject.py" --harness codex`, timeout 5.
  - `UserPromptSubmit`: `... "${PLUGIN_ROOT}/jev/chain.py" prompt --harness codex`, timeout 15.
  - `PreToolUse`, matcher `Bash|apply_patch|Edit|Write`: `... "${PLUGIN_ROOT}/jev/chain.py" pretool --harness codex`, timeout 20.
  These command lines are part of the trust hash, so they are frozen: a shape test pins them, and changing one means users must re-trust (setup does that on its next run, with consent).
- `codex/.mcp.json`: `{"mcpServers": {"jev": {"command": "python3", "args": ["-X", "utf8", "jev/jev_mcp.py"], "cwd": ".", "env_vars": ["OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY", "DRYAS_DATA_ROOT"]}}}`.
- **Ruflo stays a setup-registered server [J].** Its MCP shim lives in `~/.dryas/ruflo/mcp-shim` ([A4] of the Claude spec: the shim's `dist` link must not live in the plugin) and its env is machine-specific, and `.mcp.json` cannot expand either. Setup writes `[mcp_servers.ruflo]` (command `node`, args `[<data root>/ruflo/mcp-shim/bin/cli.js, "mcp", "start"]`, literal `RUFLO_*` env, no secrets) into its marked block in `config.toml`, and installs the shim with `ruflo_runtime.install`. Ruflo hooks stay Claude-only (as today).
- **Sync** (`tools/sync_codex_plugin.py`): copies `claude/jev/` (every file except `tests/`, `__pycache__`, `*.pyc`) to `codex/jev/` and `claude/pstack/` to `codex/pstack/`; removes files under those two targets that no longer have a source. `--check` prints each drifted path (missing, different, extra) and exits 1. Comparison ignores `\r\n` vs `\n` so a Windows checkout does not report drift. `install/tests/test_codex_plugin_sync.py` runs the check in CI. `CONTRIBUTING.md` says: edit `claude/`, run the sync, commit both.

## Rules and skills

- `jev/rules_inject.py` gains `--harness codex`: template `AGENTS.md.template` (next to `jev/`'s parent, so `codex/AGENTS.md.template` in the plugin), `<!-- pstack-picks -->` gated from `chain.local.json` `off` as for Claude, plus the skip line when pstack is off. `{{CD}}` in the template becomes the plugin root (forward slashes) at run time. The output ends with a paths line: `Dryas paths: <dryas-root> = <plugin root>, <dryas-py> = <interpreter>; substitute them in Dryas skill commands.`. The Claude form (no flag) is unchanged.
- **Skills use `<dryas-root>` and `<dryas-py>` [J].** Codex does not substitute a plugin root in skill bodies (Claude Code does, [A1]), and the cache path changes on every version. So skills write `"<dryas-py>" -X utf8 "<dryas-root>/jev/tune.py" report` and the model fills in the values the rules hook stated. State paths are literal: `~/.dryas/jev/thresholds.json`. The workflow reference is `~/.dryas/docs/dryas-workflow.md` (setup copies it, as for Claude).
- The two pstack skills always ship (a plugin cannot drop a skill per user). Each starts with: if the Dryas rules say pstack-picks is not installed, say so and stop.
- Skill mentions in the rules and docs become `$dryas:<skill>` (for example `$dryas:orchestrate`). The TUI syntax is unverified; the release check has a manual step for it.
- The rules stay under 8,000 bytes for every component combination (today's AGENTS.md test limit), well under any context cap.

## Runtime, Python and Windows

- macOS and Linux: hooks and MCP run `python3` (hooks honor `DRYAS_PY` when set in the shell Codex was started from). Setup checks that `python3` on PATH is 3.9 or newer, else it stops with a message (nothing changed).
- **MCP fallback**: when `python3` is not on PATH or is older than 3.9 (typical on Windows), setup writes a user `[mcp_servers.jev]` (absolute interpreter, absolute `jev_mcp.py` under the installed plugin, the same `env_vars`) into its marked block; it overrides the plugin server. The path names the installed version, so setup must re-run after each update (it must anyway, to refresh the cache).
- **Windows [J, unverified]**: hooks get `commandWindows`: `python -X utf8 "%PLUGIN_ROOT%\jev\chain.py" pretool --harness codex` (and the matching prompt and rules lines). Whether Codex expands `%PLUGIN_ROOT%` there, and which shell it uses, is unknown, so Windows is gated by a manual release-check step (hooks fire, rules arrive, `jev` connects), and the docs mark Codex on Windows as "verify with the release check". If the manual check fails, the follow-up is a Windows launcher; the Linux/macOS release does not wait for it.
- Jev key: Codex has no plugin option for secrets. Hooks read `OPENROUTER_API_KEY` from the shell Codex runs in, and the MCP server gets it via `env_vars`. `--openrouter-key` is ignored for Codex with a note: setup never writes a key into `config.toml` [J].

## `dryas setup` for Codex

New `install/codex_plugin_setup.py`, reusing `plugin_setup` (`data_root`, `write_chain_local`, `write_workflow_doc`, `add_account`/`remove_account` with a `key`), `dryas_install.run/capture/confirm`, `ruflo_runtime`, `claude_md_block.insert_block/remove_block`, and a new `install/codex_appserver.py`. Steps for one `CODEX_HOME`, all Codex calls with `CODEX_HOME=<dir>` in the child env:

1. **Preflight**: `codex` on PATH and `codex --version` ≥ 0.162.1 (the tested version), git, Python 3.9+, the `python3` check above; Node and npm when Ruflo is selected.
2. **Marketplace**: `codex plugin marketplace list --json`; when `dryas-workflow` is missing, `codex plugin marketplace add <clone>` and record `marketplace_added`. When it exists with another root, stop with an error naming both paths (nothing changed).
3. **Plugin**: `codex plugin add dryas@dryas-workflow --json` (also on re-runs: it refreshes the cache). Then `codex plugin list --json` must show it installed and enabled at the manifest version; otherwise stop before step 4.
4. **Config block**: one marked block in `config.toml` (`# >>> dryas plugin >>>` ... `# <<< dryas plugin <<<`) with the `[plugins."dryas@dryas-workflow".mcp_servers.jev] enabled = false` overlay when Jev is off, the Jev MCP fallback when needed, and `[mcp_servers.ruflo]` when Ruflo is on. The block is rewritten as a whole each run, so stale entries leave.
5. **Ruflo runtime** (when selected): `ruflo_runtime.install(repo, data_root, {}, RUFLO_CLI_DIST)` (the shim only; Codex runs no Ruflo hooks).
6. **Hook trust**: `codex app-server` → `hooks/list {cwds: [home]}` → Dryas hooks (`pluginId == "dryas@dryas-workflow"`) whose `trustStatus` is not `trusted`. None: done. Else list them (event and command), ask, and on yes `config/batchWrite` their `currentHash`es; record the keys and hashes. Declined or app-server failure: print `Open Codex and run /hooks to review the Dryas hooks; until then the scope lock and Jev hooks do not run.`
7. **Shared state**: `write_workflow_doc`, `write_chain_local` (FlowObserve left as it is; Codex does not run it), `add_account(root, cdx, "codex_dirs")`.
8. **Record**: `<CODEX_HOME>/.dryas-codex-plugin.json`: `components`, `version`, `plugin_root` (the `installedPath`), `marketplace_added`, `trusted` (`{key: hash}`), `toml` (the block record), `dir_created`.
9. **Superpowers hint**: as today, when no Superpowers skills are found.

Running setup twice changes nothing but the cache refresh. A version update with unchanged hook lines keeps trust; a changed line shows up as untrusted in step 6 and is re-trusted with consent.

### Migration from a Codex copy install

When `<CODEX_HOME>/.dryas-installed.json` exists (today's install), before step 2:

1. Components default from that record when the run gives no `--no-` flags.
2. `codex_target.uninstall_codex` (kept, slimmed to uninstall only): the `AGENTS.md` block, the `~/.agents/skills` copies (and restores of backed-up user skills), its `hooks.json` entries, its MCP servers (`codex mcp remove` or its own `config.toml` block). State is already in `~/.dryas`, so nothing moves.
3. The `~/.claude` runtime copy: when `~/.claude/.dryas-installed.json` exists and `migrate.is_copy_install(~/.claude)` is false (a Codex-only runtime copy), run `dryas_install.uninstall(~/.claude)`. When it is a live Claude copy install, leave it (the Claude migration handles it) and print that.

**Claude-only run with a legacy Codex install**: `--harness claude` would migrate `~/.claude` and pull the files today's Codex install runs. Instead of reinstalling them (`keep_codex`), the run stops before any change: `A Codex copy install uses ~/.claude; run install.sh --harness both to move Claude Code and Codex to their plugins.` [J]

### Verify (end of setup, and `verify` in run_cmd)

PASS/FAIL/SKIP lines per `CODEX_HOME`: plugin listed and enabled at the manifest version; Jev MCP server present in `codex mcp list --json` (when Jev is on); every Dryas hook `trusted` (app-server); `codex debug prompt-input` lists `dryas:orchestrate` (SKIP when the command fails); the rules hook prints SessionStart JSON; the scope lock denies an out-of-scope `apply_patch` through `<plugin_root>/jev/chain.py pretool --harness codex`; no legacy `.dryas-installed.json` left.

### Uninstall

`--uninstall --harness codex|both` per `CODEX_HOME`: `codex plugin remove dryas@dryas-workflow`; remove the recorded `hooks.state` tables (exact header match on recorded keys; a key not found is reported, never guessed); remove the marked block; `codex plugin marketplace remove dryas-workflow` only when setup added it; `remove_account(root, cdx, "codex_dirs")`; delete the record. A legacy record is uninstalled with `uninstall_codex` as before. With `--harness both`, Codex is uninstalled first so `--purge` sees the final account list. `--purge` refuses while any `claude_dirs` or `codex_dirs` remain, or a legacy Codex record exists.

## Release check

`tools/release_check.py`, `--codex-dir` repeatable (default `$CODEX_HOME`, else `~/.codex`). Per dir:

- `dryas plugin installed (Codex)`: `codex plugin list --json` shows it installed and enabled (SKIP without the `codex` CLI).
- `Codex hooks trusted`: app-server `hooks/list`, every Dryas hook `trusted` (SKIP without the CLI).
- `Codex plugin hooks run (<event>)`: each `hooks.json` command of the installed copy runs under `sh -c` with `PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT` set, a sample event on stdin, sandboxed state; PASS on exit 0 and empty or JSON stdout.
- `Scope lock (codex)`: `<plugin root>/jev/chain.py pretool --harness codex` denies an out-of-scope `apply_patch`.
- `legacy Codex copy install`: FAIL when `.dryas-installed.json` is still there.

New manual steps: (a) in Codex, a prompt shows a `Jev route:` line and asking "which workflow rules apply?" names Dryas (real model; the probe only used a mock); (b) type `$dryas:orchestrate` in the TUI and record the working syntax in `docs/install.md`; (c) out-of-scope edit denied in a real session; (d) Windows: the same three, plus `codex mcp list` shows `jev` connected.

## Error handling

- Hooks fail open as today, except the scope lock and the Jev gate (deny behavior unchanged). `chain.py` always exits 0.
- Setup stops before the config block, trust and shared state when the marketplace add, plugin add or plugin listing fails, so a `CODEX_HOME` is never half set up.
- App-server errors (spawn failure, timeout, error response) never fail setup; they end in the `/hooks` hint and a verify FAIL.
- A `config.toml` that does not parse as text blocks (unbalanced markers) is reported and left alone (existing `insert_block` behavior).

## Testing

All in the existing CI matrix (macOS, Ubuntu, Windows; Python 3.9 and 3.12). There is no Codex CLI in CI. `install/tests/fakecli.py` gains a fake `codex` that keeps state in `$CODEX_HOME/fake_codex.json` and implements `--version`, `plugin marketplace add|list|remove`, `plugin add|list|remove` (copying `codex/` into the cache path, symlinks dropped), `mcp list --json`, `debug prompt-input`, and `app-server` (JSONL loop: `initialize`, `hooks/list` built from the installed `hooks.json` with a sha256 of each normalized handler, `config/batchWrite` writing `[hooks.state."<key>"]` tables into `config.toml`).

- **Shape**: both marketplaces and the Codex manifest parse; versions equal; every `${PLUGIN_ROOT}` path in `hooks.json` and every relative MCP arg exists; hook command lines equal the pinned list; `.agents/plugins/marketplace.json` source is `./codex`.
- **Sync**: no drift; drift detection reports missing, different and extra files (temp tree); CRLF ignored.
- **Hook shell**: the Codex hook form runs under `sh` (Git Bash on Windows) with `PLUGIN_ROOT`.
- **Rules**: `--harness codex` output is the Codex template with `{{CD}}` resolved, pstack gating, the paths line, valid SessionStart JSON, under 8,000 bytes for every combination; the Claude form unchanged.
- **App-server**: pure request builders and `hook_entries` parsing (nested results, missing fields), `trust_params`; the runner against the fake (`list`, `trust`, timeout, error response).
- **Setup**: two `CODEX_HOME`s with the fake; every call carries its own `CODEX_HOME`; trust written only with consent; declined trust prints the hint and records nothing; Jev-off overlay and fallback block; second run is a no-op apart from `plugin add`; failure of `plugin add` stops before `config.toml` and `accounts.json`.
- **Migration**: a legacy fixture (made with today's `install_codex` output shape) loses its AGENTS block, skills, hooks entries and MCP servers; a Codex-only `~/.claude` runtime copy is removed; a live Claude copy install is kept; the Claude-only refusal changes nothing.
- **Uninstall/purge**: plugin removed, trust tables and block gone, marketplace removed only when added; purge refused while a `codex_dirs` entry remains.
- **Release check**: Codex lines with a fake-installed plugin.

## Docs

- `docs/install.md`: the Codex section rewritten: plugin plus setup per `CODEX_HOME`, `--codex-dir`, hook trust and consent (`--yes`), `/hooks` fallback, migration, update (`git pull` then re-run setup: the cache is a copy), uninstall, Windows status, `OPENROUTER_API_KEY` from the shell, minimum Codex 0.162.1.
- `docs/harnesses.md`: Codex row and section: plugin `dryas@dryas-workflow`; skills as `$dryas:<name>`; several Codex accounts.
- `README.md`: harness table row `Codex | Plugin dryas@dryas-workflow (install.sh --harness codex)`.
- `docs/roadmap.md`: tick "Codex plugin"; "Packaged plugins per harness" notes both.
- `docs/release-check.md`: the Codex lines and manual steps.
- `CONTRIBUTING.md`: the sync rule and the frozen hook command lines.

## Out of scope

- A Windows launcher for Codex hooks (only if the Windows manual check fails).
- Git-sourced marketplace installs (`codex plugin marketplace add promprit/dryas-workflow`): untested snapshot contents; the installer always adds the local clone.
- The Agent Plugins `plugin.json` format (would allow `${PLUGIN_ROOT}` in MCP config; not tested).
- Superpowers for Codex (hint only, as today).

## Decisions made by judgment

- **[J1] Ruflo MCP stays a setup-registered server**, not in `.mcp.json`: its shim and env live in the data root and `.mcp.json` cannot expand paths.
- **[J2] Skills name `<dryas-root>` / `<dryas-py>`**, filled from the rules hook's paths line, because Codex does not substitute a plugin root in skill text and the cache path changes per version.
- **[J3] Claude-only run with a legacy Codex install stops** with "use --harness both" instead of reinstalling the `~/.claude` runtime copy, so the copy path can be deleted.
- **[J4] No key in `config.toml`**: `--openrouter-key` is ignored for Codex with a note; the key comes from the shell.
- **[J5] Windows `commandWindows` uses cmd syntax and `python`**, shipped unverified behind a manual release-check gate.
- **[J6] Trust is written through the app-server; trust removal edits `config.toml` text** for the recorded keys only (the app-server has no verified delete).
- **[J7] Setup's own `config.toml` entries live in one marked block with new markers** (`dryas plugin`), so a half-migrated legacy block (`dryas-workflow` markers) is never confused with it.

## Amendments from the build

Decisions made while implementing (task reports in `.superpowers/cdx/`). Each keeps the design above; where it differs, this section wins.

- **[B1] Event names.** Codex 0.162.1's `hooks/list` names events in camelCase (`preToolUse`, `sessionStart`, `userPromptSubmit`); trust keys use snake_case. Verify and the release check compare event names with case and `_` ignored. (Task 3, Task 6)
- **[B2] Trust guard.** `codex_appserver.write_trust(..., plugin_id=ID)` refuses any entry of another plugin before it starts the app-server; the argument is optional so the signature stays compatible. Setup always passes it. (Task 3)
- **[B3] Config block ownership by table, not by marker.** `codex mcp add/remove` re-renders `[mcp_servers]` and drops or moves comment lines, so a lone marker is a normal state. Setup owns the tables it recorded (`toml_body`) plus its known tables the markers still enclose; it removes those and appends the block at the end. Tables Codex adds inside the markers (other MCP servers, `hooks.state`) stay. If a table setup would write already exists and is not Dryas's, setup warns and leaves `config.toml` alone. (Task 4)
- **[B4] Recorded trust is merged.** `trusted` in the record keeps earlier keys and adds every Dryas hook seen trusted, so uninstall can remove trust for hooks a plugin update dropped. A fresh decline still records nothing. (Task 5)
- **[B5] Verify.** The plugin line also fails when the listed version differs from the version setup recorded; `codex plugin list` is skipped when the Codex home does not exist (the real CLI errors there); the trust line names the missing or untrusted events and ends with the `/hooks` hint. (Task 5, Task 6)
- **[B6] Preflight.** The Codex version check runs only when `codex` is on PATH, so a missing CLI still reports "Missing: codex". On macOS and Linux `python3` must be 3.9+ (the installer stops otherwise); on Windows a missing `python` is a warning only, and setup falls back to the installer's Python for the Jev MCP server. (Task 6, Task 7)
- **[B7] Shared runtime copy.** During migration the `~/.claude` runtime copy is kept while another Codex home (`~/.codex` or `$CODEX_HOME`) still has a copy install that uses it; the run says to set up that home too. (Task 6)
- **[B8] Uninstall details.** The marketplace is removed only when setup added it and it is still listed (marketplaces are per Codex home, so none is shared). An empty `[hooks.state]` header is removed only when no `[hooks.state.*]` table is left. An emptied `config.toml` is deleted only when setup created it. If `codex plugin remove` fails, the record is still deleted (rc 0) with a warning that says how to remove the plugin by hand. Trust and the config block are removed in the order that leaves no empty header behind. (Task 7)
- **[B9] Release check.** Beyond the lines above: `Codex hooks trusted` also fails when an event the plugin ships is missing from `hooks/list`; a `Codex rules hook output` line checks that SessionStart prints the Dryas rules with the `Dryas paths:` line; the check does not run `codex plugin list` on a missing Codex home (so it never creates one). Hook lines run with `sh -c` on macOS and Linux, with `python3` from PATH and no `DRYAS_PY`, as Codex runs them; on Windows the check runs `commandWindows` in the Windows shell instead of skipping. (Task 8)
- **[B10] `--force`** no longer does anything: neither harness copies files. It is kept so older scripts still run. (Task 8)
