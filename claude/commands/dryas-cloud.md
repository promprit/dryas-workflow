---
description: Check, set up, update or remove the Dryas copy that makes this repo work in claude.ai/code cloud sessions
argument-hint: check | init | update | remove [options]
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/cloud_check.py":*), Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas" cloud:*), Bash(git status:*)
disable-model-invocation: true
---
Subcommand and options: $ARGUMENTS (none means `check`).

- `check`: from the repo root, run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/cloud_check.py" --repo "$PWD"` and report each line it prints; exit 0 means the copy is intact. Fix nothing yourself: a drift line is a hand edit, which the user keeps or replaces with `update --force`.
- `init`, `update`, `remove`: these need a Dryas checkout, so they never run inside a cloud session. If `${CLAUDE_PLUGIN_ROOT}/bin/dryas` does not exist, say so, name the command for a machine with Dryas (`dryas cloud <subcommand> --repo <path>`, or `install/install.sh --repo <path>` for init) and stop. Otherwise run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas" cloud <subcommand> --repo "$PWD"` with the user's options and without `--yes`, show the dry run, and ask before running it again with `--yes`. It never commits: show the `git add` and `git commit` lines it prints and leave the commit to the user.
