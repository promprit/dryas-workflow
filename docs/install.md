# Install

```
git clone https://github.com/promprit/dryas-workflow
cd dryas-workflow
./install/install.sh
```

On Windows, use `.\install\install.ps1` (see [Windows](#windows-native)).

The installer asks before it changes anything. Use `--dry-run` first to see what it would do.

## Claude Code: plugin plus setup

For Claude Code, Dryas is a plugin, `dryas@dryas-workflow`, served from your clone (the repo is its own marketplace). The installer runs setup for one Claude config dir:

1. `claude plugin marketplace add <clone>` and `claude plugin install dryas@dryas-workflow`, both with `CLAUDE_CONFIG_DIR` set to that dir. The plugin brings the rules (injected at session start), the hooks, the scope lock, the Jev chain, the Jev MCP server, the agents, commands and skills.
2. The third-party components you selected (Ruflo, Superpowers, design skills).
3. A merge into that dir's `settings.json`: model, env and permission rules only (plus the Ruflo hooks when Ruflo is on). It asks first.
4. Shared state in `~/.dryas`: the workflow reference (`docs/dryas-workflow.md`), `chain.local.json` (which optional stages are on) and `accounts.json` (the config dirs set up so far).

If the plugin install or its check fails, setup stops before it touches `settings.json`.

### Several accounts

Run setup once per config dir. The default dir is `$CLAUDE_CONFIG_DIR`, else `~/.claude`:

```
./install/install.sh                                # ~/.claude
./install/install.sh --claude-dir ~/.claude-team    # a second account
```

Both accounts share one `~/.dryas` (logs, thresholds, handoffs). See [harnesses.md](harnesses.md#several-accounts-t3-code-personal-and-team).

Claude Code runs the plugin in place from your clone (`<clone>/claude`), so `git pull` updates it for every account; the change takes effect at the next session start or after `/reload-plugins`. Re-run setup for each dir after you move the clone (the permission rules name the clone's path) or when you change components or the settings setup merges.

Component choices are shared: the `--no-` flags write `~/.dryas/chain.local.json`, which every account and Codex read. Setup warns when a run changes them while another account or a Codex install uses them.

### FlowObserve

`--flowobserve` turns on the FlowObserve stage of the Jev chain (it runs `~/.flowobserve/bin/fo_hook.py`, observe-only). Without the flag, a setting you already have is kept; new installs leave it off.

### The OpenRouter key

Jev calls OpenRouter. The recommended way to give it the key is your shell profile (`export OPENROUTER_API_KEY=...`): the hooks and the Jev MCP server read `OPENROUTER_API_KEY` first, and setup does nothing with it.

Only if you pass `--openrouter-key KEY` does setup also store the key as the plugin option `openrouter_key`, which Claude Code keeps in its secure storage and hands to the hooks and the Jev MCP server. That helps when Claude Code is started from the GUI, which does not read your shell profile. The flag puts the key on the `claude plugin install` command line, so other processes on this machine can see it briefly while that command runs.

### Migration from a copy install

Earlier versions copied files into `~/.claude`. When setup finds such an install in the target dir, it migrates it first:

1. State moves to `~/.dryas`: `jev/logs`, `jev/handoff` and `jev/compact` are merged in, your `/tune` values in `thresholds.json` (only those that differ from the shipped defaults) move to `~/.dryas/jev/thresholds.json`, and `docs/dryas-local.md` is copied to `~/.dryas/docs/dryas-local.md`. Stages you turned on or off in `jev/chain.json` carry over to `chain.local.json`.
2. Only then is the copy install removed, exactly as `--uninstall` used to remove it.
3. Setup installs the plugin as above.

Data always moves before anything is removed. If removal fails, re-run the installer: state is not merged twice (the data root records which dirs were merged in `jev/.migrated.json`). A second run on a migrated dir is a no-op for the migration.

If Codex also uses that dir's runtime files, a plain `--harness claude` run puts them back after the migration so Codex keeps working.

### Uninstall and purge

```
./install/install.sh --uninstall                              # ~/.claude only
./install/install.sh --uninstall --claude-dir ~/.claude-team  # one other dir
./install/install.sh --uninstall --purge                      # last account: also remove ~/.dryas
```

`--uninstall` works on one config dir: it runs `claude plugin uninstall dryas@dryas-workflow` there, removes only the settings entries setup added, and drops that dir from `~/.dryas/accounts.json`. It leaves the shared `~/.dryas` state (logs, thresholds, handoffs, the Ruflo runtime) in place by design, since other accounts or Codex may use it. Superpowers was installed as a dependency of the plugin; `claude plugin prune` (same `CLAUDE_CONFIG_DIR`) removes it when nothing else needs it.

`--purge` also removes the entries Dryas owns in `~/.dryas` (`accounts.json`, `chain.local.json`, `docs`, `jev`, `ruflo`), and only when no other account is listed in `accounts.json` and no Codex install uses it (uninstall Codex first, or in the same run with `--harness both`). That deletes your Jev logs, your `/tune` thresholds, saved handoffs and Ruflo memory. It keeps your notes in `~/.dryas/docs/dryas-local.md`. It refuses when `accounts.json` is missing or unreadable or the dir's record cannot be read (that dir then stays listed), and it never removes files Dryas did not create.

With `--harness codex` or `both`, `--uninstall` also removes the Codex install.

### Hooks blocked by policy

Plugin hooks run as soon as the plugin is installed; there is no per-hook approval. An organization policy with `allowManagedHooksOnly` in managed settings blocks them. Then the rules, the scope lock and the Jev chain do not run, even though `/plugin` shows dryas as enabled. Ask your admin to allow the plugin's hooks.

## Components

| Component | What it adds | Upstream |
| --- | --- | --- |
| Workflow core | The `dryas` plugin: rules, agents, commands, hooks and the scope lock | this repo |
| Jev | Gating and routing hooks, with the [TypeSafe skills](https://github.com/typesafe-ai/skills) | `--no-jev` skips |
| Ruflo | Orchestration and memory ([ruvnet/ruflo](https://github.com/ruvnet/ruflo), latest; tested 3.53.0) | `--no-ruflo` skips |
| Superpowers | Process skills ([obra/superpowers](https://github.com/obra/superpowers), from the `claude-plugins-official` marketplace; tested 6.4.2) | Required by the plugin; `--no-superpowers` only drops Dryas's superpowers rules |
| Design skills | [Impeccable](https://github.com/pbakaus/impeccable) (latest; tested 4.5.0) and [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | `--no-design` skips |
| pstack picks | Interrogate review, cleanup, benchmark checklist and principles, adapted from [pstack-claude](https://github.com/michael-denyer/pstack-claude) (see NOTICE.md) | `--no-pstack-picks` skips |

Dryas installs the latest version of each component. If Dryas's Ruflo patches do not apply to the latest Ruflo, the installer falls back to the tested version. A weekly CI job checks the latest Ruflo.

You need [Claude Code](https://docs.claude.com/en/docs/claude-code), the Codex CLI, or both, installed first.

## Flags

| Flag | Effect |
| --- | --- |
| `--no-jev` | Do not install Jev |
| `--no-ruflo` | Do not install Ruflo |
| `--no-superpowers` | Superpowers is a required dependency of the plugin and is installed anyway; this flag only leaves out Dryas's superpowers deny rules and stages (Codex never installs it) |
| `--no-design` | Do not install Impeccable or UI UX Pro Max |
| `--no-pstack-picks` | Do not install the pstack picks |
| `--yes` | Run the third-party install commands without asking |
| `--force` | Replace the Codex copy's files (originals are backed up first) |
| `--dry-run` | Print the plan and the settings diff, change nothing (skips third-party installs and verify) |
| `--uninstall` | Remove Dryas from one Claude config dir (and the Codex install with `--harness codex\|both`) |
| `--purge` | With `--uninstall`: also remove Dryas's entries in `~/.dryas` (logs, `/tune` thresholds, handoffs; keeps `dryas-local.md`) when no other account uses it |
| `--preflight-only` | Run the prerequisite checks and stop |
| `--harness claude\|codex\|both` | Choose what to install for. Claude Code is the default |
| `--claude-dir DIR` | The Claude config dir to set up (default `$CLAUDE_CONFIG_DIR`, else `~/.claude`) |
| `--flowobserve` | Turn on the FlowObserve stage |
| `--openrouter-key KEY` | Also store the key as the plugin option (explicit only; see [the key](#the-openrouter-key)) |

`--yes` does not skip the settings merge confirmation. The installer always asks before it edits a config dir's `settings.json`.

## Windows (native)

Prerequisites: Python 3.9 or newer (python.org installer or `winget install Python.Python.3.12`), Git for Windows, Node.js 20+ (for Ruflo), and the Claude Code and/or Codex CLI.

Claude Code runs plugin hooks with Git Bash, so Git for Windows must be installed. The Jev MCP server starts with `python3`: make sure `python3` resolves on your PATH (enable the `python3` app alias or add Python to PATH). Setup warns when it does not (when Jev is selected).

```powershell
git clone https://github.com/promprit/dryas-workflow.git
cd dryas-workflow
.\install\install.ps1
```

If PowerShell refuses to run scripts: `powershell -ExecutionPolicy Bypass -File .\install\install.ps1`.
If your user folder or Python path contains a space and Windows has no short (8.3) name for it, Ruflo and the Codex hooks cannot be installed. The installer says so and suggests `--no-ruflo` / `--harness claude`.

## WSL

Inside WSL, follow the Linux steps (`./install/install.sh`). WSL and native Windows installs are separate: each has its own home folder.

## Codex

`--harness codex` installs for Codex only, `--harness both` for Claude Code and Codex. Codex hooks and MCP servers still run from a runtime-only copy in `~/.claude` (`jev/`, `ruflo/`, `pstack/` and `docs/dryas-workflow.md`; no agents, commands or skills, which would duplicate the plugin's). For Codex the installer also adds a rules block to `~/.codex/AGENTS.md` (or `$CODEX_HOME`), the skills `$orchestrate`, `$wplan`, `$wreview`, `$commit` and `$tune` to `~/.agents/skills`, the scope-lock / Jev gate / Jev route hooks to `~/.codex/hooks.json`, and the `jev` and `ruflo` MCP servers (via `codex mcp add`, or a marked block in `config.toml`). Superpowers for Codex is not installed; the installer tells you if it is missing.

## Existing files

Files of the Codex runtime copy that already exist are kept unless you pass `--force`. With `--force`, the originals are backed up to `~/.claude/.dryas-backup-<timestamp>/` first. For Claude Code, setup changes only the config dir's `settings.json` (after asking) and Dryas's own files in `~/.dryas`.

## The API key

Jev calls OpenRouter. Put the key in your shell profile:

```
export OPENROUTER_API_KEY=...
```

The installer never asks for the key and never writes it to a file. For Claude Code it can also be stored as a plugin option; see [The OpenRouter key](#the-openrouter-key).

## Data root

Workflow data lives under `~/.dryas`, shared by every account: Jev logs, thresholds, handoffs, compaction notes, `chain.local.json`, `accounts.json`, the workflow reference, and Ruflo (its memory, helpers and MCP shim). Set `DRYAS_DATA_ROOT` to move it:

```
export DRYAS_DATA_ROOT=/path/to/data
```

Ruflo data goes to `$DRYAS_DATA_ROOT/ruflo/<namespace>`.

The Ruflo helpers are generated locally by `ruflo init` and patched (data root, no background npx), not shipped in the repo. They and the Ruflo MCP shim live in `$DRYAS_DATA_ROOT/ruflo` (`helpers/`, `mcp-shim/`).

## Verify

The installer ends with a verify step for the config dir. Each check prints `PASS`, `FAIL` or `SKIP`:

- **dryas@dryas-workflow listed**: `claude plugin list --json` for that dir lists the plugin; the path shown is the folder it runs from (your clone's `claude/`).
- **dryas loads without errors**: the plugin is enabled and Claude Code reports no load errors, such as a missing `superpowers` dependency. Setup adds the `claude-plugins-official` marketplace (`anthropics/claude-plugins-official`) and installs `superpowers@claude-plugins-official` before the plugin; if this fails, run those two steps by hand and re-run setup.
- **rules hook prints SessionStart JSON**: the plugin's rules hook runs and injects the rules.
- **scope lock blocks an out-of-scope write**: a write outside an active task's scope is denied in a temporary folder.
- **Jev tests**: runs the tests in the installed plugin's `jev/tests` with the Python the installer was started with. They need `pytest`. If `pytest` is missing the check prints `SKIP (install pytest to run the Jev tests)`; install it (`python3 -m pip install pytest`) and re-run the installer.

With Codex, the Codex checks follow. For a fuller check on a real machine, including several config dirs, see [release-check.md](release-check.md).

It ends with `verify: N failed`. The installer exits non-zero if any check failed.

## Upgrade

`git pull` in the clone updates the plugin itself: Claude Code runs it from the clone. Run `./install/install.sh` again, once per config dir, to refresh the settings it merged (needed when a release changes them, when you change components, or after moving the clone). The Codex runtime copy is updated too; your own files there are still kept unless you pass `--force`. You can add a component you skipped earlier (for example, re-run without `--no-ruflo`). For Claude Code, a `--no-` flag on a re-run turns that component's stages off in `chain.local.json` and drops its settings entries. For the Codex copy, re-running with --no-pstack-picks (or any --no- flag) after a full install does not remove that component; use --uninstall.

`~/.dryas/jev/thresholds.json` is yours (`/tune` changes it); setup never overwrites it. The shipped `jev/chain.json` in the plugin is read-only; your stage choices live in `~/.dryas/chain.local.json` and keep their settings across re-runs.

## Uninstall

```
./install/install.sh --uninstall
```

For Claude Code this removes the plugin and the settings entries setup added in one config dir; see [Uninstall and purge](#uninstall-and-purge). For Codex (`--harness codex|both`) it removes exactly what the installer added: the runtime copy's files and folders, the Codex hooks, skills and MCP servers, and the `AGENTS.md` block. Files replaced with `--force` are restored from their backup. A backup of your settings from before the merge (`<config dir>/settings.json.dryas-bak-<timestamp>`) is kept, and its path is printed. Use it as a manual fallback if something looks wrong.

Uninstall removes only settings values that still match what the installer wrote. A value changed afterwards, by you or by Claude Code itself (for example it may rewrite `"model": "opus"` to `"opus[1m]"`), counts as your edit and is kept.

## Troubleshooting

- **dryas fails to load (`/plugin` shows an error).** Usually the `superpowers` dependency: run `claude plugin marketplace add anthropics/claude-plugins-official` and `claude plugin install superpowers@claude-plugins-official` with the same `CLAUDE_CONFIG_DIR`, then re-run setup.
- **Jev shows `JevUnavailable`.** Apps launched from the GUI do not read your shell profile, so they do not see `OPENROUTER_API_KEY`. Launch Claude Code from a terminal, set the variable in the app's environment, or store the key as the plugin option (`--openrouter-key`).
- **Hooks do not fire.** Run `/plugin` and check that dryas is enabled. If it is, look for `allowManagedHooksOnly` in managed settings ([Hooks blocked by policy](#hooks-blocked-by-policy)). On Windows, check that Git for Windows is installed.
- **Permission prompts for `/tune` or `/handoff`.** The allow rules name the folder the plugin runs from (your clone's `claude/`). Re-run setup for that config dir after moving the clone.
- **`HOME` contains a space.** Ruflo does not handle this. Install with `--no-ruflo`.
- **My edited file was not replaced.** Existing files are kept unless you pass `--force`.
