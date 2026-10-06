# Install

```
git clone https://github.com/promprit/dryas-workflow
cd dryas-workflow
./install/install.sh
```

On Windows, use `.\install\install.ps1` (see [Windows](#windows-native)).

The installer asks before it changes anything. Use `--dry-run` first to see what it would do.

## Components

| Component | What it adds | Upstream |
| --- | --- | --- |
| Workflow core | Agents, commands, hooks and the scope lock in `~/.claude` | this repo |
| Jev | Gating and routing hooks, with the [TypeSafe skills](https://github.com/typesafe-ai/skills) | `--no-jev` skips |
| Ruflo | Orchestration and memory ([ruvnet/ruflo](https://github.com/ruvnet/ruflo), latest; tested 3.53.0) | `--no-ruflo` skips |
| Superpowers | Process skills ([obra/superpowers](https://github.com/obra/superpowers), latest; tested 6.4.2) | `--no-superpowers` skips |
| Design skills | [Impeccable](https://github.com/pbakaus/impeccable) (latest; tested 4.5.0) and [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | `--no-design` skips |
| pstack picks | Interrogate review, cleanup, benchmark checklist and principles, adapted from [pstack-claude](https://github.com/michael-denyer/pstack-claude) (see NOTICE.md) | `--no-pstack-picks` skips |

Dryas installs the latest version of each component. If Dryas's Ruflo patches do not apply to the latest Ruflo, the installer falls back to the tested version. A weekly CI job checks the latest Ruflo.

You need [Claude Code](https://docs.claude.com/en/docs/claude-code), the Codex CLI, or both, installed first.

## Flags

| Flag | Effect |
| --- | --- |
| `--no-jev` | Do not install Jev |
| `--no-ruflo` | Do not install Ruflo |
| `--no-superpowers` | Do not install Superpowers |
| `--no-design` | Do not install Impeccable or UI UX Pro Max |
| `--no-pstack-picks` | Do not install the pstack picks |
| `--yes` | Run the third-party install commands without asking |
| `--force` | Replace your existing files (originals are backed up first) |
| `--dry-run` | Print the plan and the settings diff, change nothing (skips third-party installs and verify) |
| `--uninstall` | Remove what the installer added (both the Claude and the Codex install) |
| `--preflight-only` | Run the prerequisite checks and stop |
| `--harness claude\|codex\|both` | Choose what to install for. Claude Code is the default |

`--yes` does not skip the settings merge confirmation. The installer always asks before it edits `~/.claude/settings.json`.

## Windows (native)

Prerequisites: Python 3.9 or newer (python.org installer or `winget install Python.Python.3.12`), Git for Windows, Node.js 20+ (for Ruflo), and the Claude Code and/or Codex CLI.

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

`--harness codex` installs for Codex only, `--harness both` for Claude Code and Codex. For Codex the installer adds a rules block to `~/.codex/AGENTS.md` (or `$CODEX_HOME`), the skills `$orchestrate`, `$wplan`, `$wreview`, `$commit` and `$tune` to `~/.agents/skills`, the scope-lock / Jev gate / Jev route hooks to `~/.codex/hooks.json`, and the `jev` and `ruflo` MCP servers (via `codex mcp add`, or a marked block in `config.toml`). Superpowers for Codex is not installed; the installer tells you if it is missing.

## Existing files

Files that already exist are kept unless you pass `--force`. With `--force`, the originals are backed up to `~/.claude/.dryas-backup-<timestamp>/` first.

## The API key

Jev calls OpenRouter. Put the key in your shell profile:

```
export OPENROUTER_API_KEY=...
```

The installer never asks for the key and never writes or stores it.

## Data root

Workflow data (for example Ruflo memory) lives under `~/.dryas`. Set `DRYAS_DATA_ROOT` to move it:

```
export DRYAS_DATA_ROOT=/path/to/data
```

Ruflo data goes to `$DRYAS_DATA_ROOT/ruflo/<namespace>`.

The Ruflo helpers are generated locally by `ruflo init` and patched (data root, no background npx), not shipped in the repo.

## Verify

The installer ends with a verify step. Each check prints `PASS`, `FAIL` or `SKIP`:

- **Jev tests**: runs the tests in `~/.claude/jev/tests` with the Python the installer was started with. They need `pytest`. If `pytest` is missing the check prints `SKIP (install pytest to run the Jev tests)`; install it (`python3 -m pip install pytest`) and re-run the installer.
- **jev MCP server registered** (only with Jev): `claude mcp list` shows `jev:`.
- **scope lock blocks an out-of-scope write**: a write outside an active task's scope is denied in a temporary folder.

It ends with `verify: N failed`. The installer exits non-zero if any check failed.

## Upgrade

Pull the repo and run `./install/install.sh` again. Files the installer added before are updated. Your own files are still kept unless you pass `--force`. You can add a component you skipped earlier (for example, re-run without `--no-ruflo`); one `--uninstall` later removes everything from all runs. Re-running with --no-pstack-picks (or any --no- flag) after a full install does not remove that component; use --uninstall.

After the first install, `~/.claude/jev/thresholds.json` is yours (`/tune` changes it); re-installing never overwrites it. Optional stages you enabled yourself in `jev/chain.json` (for example an observer) keep their settings.

## Uninstall

```
./install/install.sh --uninstall
```

This removes exactly what the installer added: its files and folders, the Dryas block in `CLAUDE.md`, only the settings entries it added, the `jev` MCP registration, and the data root if it created it and it is still empty. Files replaced with `--force` are restored from their backup. A backup of your settings from before the merge (`~/.claude/settings.json.dryas-bak-<timestamp>`) is kept, and its path is printed. Use it as a manual fallback if something looks wrong.

Uninstall removes only settings values that still match what the installer wrote. A value changed afterwards, by you or by Claude Code itself (for example it may rewrite `"model": "opus"` to `"opus[1m]"`), counts as your edit and is kept.

## Troubleshooting

- **Jev shows `JevUnavailable`.** Apps launched from the GUI do not read your shell profile, so they do not see `OPENROUTER_API_KEY`. Launch Claude Code from a terminal, or set the variable in the app's environment.
- **`HOME` contains a space.** Ruflo does not handle this. Install with `--no-ruflo`.
- **My edited file was not replaced.** Existing files are kept unless you pass `--force`.
