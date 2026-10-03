# Install

```
git clone https://github.com/promprit/dryas-workflow
cd dryas-workflow
./install/install.sh
```

The installer asks before it changes anything. Use `--dry-run` first to see what it would do.

## Components

| Component | What it adds | Upstream |
| --- | --- | --- |
| Workflow core | Agents, commands, hooks and the scope lock in `~/.claude` | this repo |
| Jev | Gating and routing hooks, with the [TypeSafe skills](https://github.com/typesafe-ai/skills) | `--no-jev` skips |
| Ruflo | Orchestration and memory ([ruvnet/ruflo](https://github.com/ruvnet/ruflo), pinned 3.51.0) | `--no-ruflo` skips |
| Superpowers | Process skills ([obra/superpowers](https://github.com/obra/superpowers), pinned 6.4.1) | `--no-superpowers` skips |
| Design skills | [Impeccable](https://github.com/pbakaus/impeccable) (pinned 4.3.1) and [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | `--no-design` skips |

You need [Claude Code](https://docs.claude.com/en/docs/claude-code) installed first.

## Flags

| Flag | Effect |
| --- | --- |
| `--no-jev` | Do not install Jev |
| `--no-ruflo` | Do not install Ruflo |
| `--no-superpowers` | Do not install Superpowers |
| `--no-design` | Do not install Impeccable or UI UX Pro Max |
| `--yes` | Answer yes to prompts |
| `--force` | Overwrite existing files |
| `--dry-run` | Print the plan, change nothing |
| `--uninstall` | Remove what the installer added |

`--yes` does not skip the settings merge confirmation. The installer always asks before it edits `~/.claude/settings.json`.

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

## Verify

The installer ends with a verify step. It checks that each installed file is in place, that the settings entries exist, and that the Jev tests pass. The Jev tests need `pytest`. If `pytest` is missing, install it (`python3 -m pip install pytest`) and re-run the installer.

## Upgrade

Pull the repo and run `./install/install.sh` again. Existing files are kept unless you pass `--force`.

## Uninstall

```
./install/install.sh --uninstall
```

This removes exactly what the installer added, and only the settings entries it added. A backup of your settings from before the merge is kept. Use it as a manual fallback if something looks wrong.

## Troubleshooting

- **Jev shows `JevUnavailable`.** Apps launched from the GUI do not read your shell profile, so they do not see `OPENROUTER_API_KEY`. Launch Claude Code from a terminal, or set the variable in the app's environment.
- **`HOME` contains a space.** Ruflo does not handle this. Install with `--no-ruflo`.
- **My edited file was not replaced.** Existing files are kept unless you pass `--force`.
