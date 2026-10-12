# Release check

Run this after installing Dryas Workflow on a new machine (Windows, WSL, macOS or Linux). It checks that the plugin is installed in each Claude config dir and each Codex home, that its hooks run (and, in Codex, are trusted) and that the scope lock blocks out-of-scope edits. It never changes your Claude or Codex folders or `~/.dryas` (the `codex` CLI it calls may write its own logs in the Codex home): the hooks it runs get a temporary folder for their logs, handoffs, compaction notes, data root and `chain.local.json` (empty, so optional local stages such as FlowObserve stay off), and no OpenRouter key. Only the Jev route check calls OpenRouter, when a key is set, and its logs also go to a temporary folder.

Before tagging a release: bump claude/.claude-plugin/plugin.json version (and the marketplace.json plugin entry) if any shipped plugin content changed, and `codex/.codex-plugin/plugin.json` if the Codex plugin changed. Run `python tools/sync_codex_plugin.py --check` first: it fails when `codex/jev` or `codex/pstack` drifted from `claude/`.

## Run it

    python tools/release_check.py
    python tools/release_check.py --claude-dir ~/.claude --claude-dir ~/.claude-team
    python tools/release_check.py --codex-dir ~/.codex --codex-dir ~/.codex-work

On Windows use `py tools\release_check.py`. Options: `--claude-dir` (repeat it once per account; default `~/.claude`) and `--codex-dir` (repeat it once per Codex home; default `$CODEX_HOME` or `~/.codex`).

Each line starts with PASS, FAIL, SKIP or WARN. The exit code is 1 if any line is FAIL, otherwise 0.

## What the checks mean

- Environment: your OS, Python, and whether `git`, `claude`, `codex` and `node` are on PATH. It says whether an OpenRouter key is set in this shell, never its value.
- `plugin manifests valid`: runs `claude plugin validate` on the repo's marketplace and on `claude/`. Skipped when `claude` is not on PATH.

Then, for each `--claude-dir`, under a `Claude Code: <dir>` heading:

- `dryas plugin installed`: `claude plugin list --json` (with `CLAUDE_CONFIG_DIR=<dir>`) lists `dryas@dryas-workflow`; the path shown is the folder it runs from (`readFromFolder`, your clone's `claude/`). Without a working `claude` it falls back to `<dir>/plugins/installed_plugins.json`. FAIL means setup was not run for that dir.
- `dryas loads without errors`: the plugin is enabled and reports no load errors (for example a missing `superpowers` dependency). Skipped when `claude` is not on PATH.
- `plugin hooks run (<event>)`, one line each for PreToolUse, UserPromptSubmit, SessionStart and PreCompact: every command of that event in the installed plugin's `hooks/hooks.json` is run the way Claude Code runs it (`bash -c`, with `CLAUDE_PLUGIN_ROOT`, `DRYAS_PY` and `CLAUDE_CONFIG_DIR` set) with a sample event. It passes when each exits 0 and prints nothing or JSON. On Windows it needs Git Bash; without it the lines are SKIP.
- `Scope lock (claude)`: in a temporary worktree whose plan allows only `src/feature/**`, a write to `src/other.ts` must be denied by the plugin's `jev/chain.py`.
- `Jev route`: with an OpenRouter key in this shell (`OPENROUTER_API_KEY`, `DRYAS_OPENROUTER_KEY` or `CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY`), a sample prompt must produce a `Jev ` line. Skipped without one. A key stored only as the plugin option is visible only inside Claude Code; manual step 1 covers it.
- Ruflo (when setup installed it for that dir): the data folder (`DRYAS_DATA_ROOT` or `~/.dryas`) exists and is writable, `ruflo/helpers/hook-handler.cjs` is in it, and the plugin's Ruflo helper runner exits quietly (run against a temporary data folder). Skipped otherwise.

Then, for each `--codex-dir`, under a `Codex: <dir>` heading:

- `legacy Codex copy install`: FAIL while the old copy install's record (`.dryas-installed.json`) is still in that home; re-run `install.sh --harness codex` to migrate it.
- `dryas plugin installed (Codex)`: `codex plugin list --json` (with `CODEX_HOME=<dir>`) lists `dryas@dryas-workflow` as installed and enabled; the detail shows its version. FAIL means setup was not run for that home. Skipped when `codex` is not on PATH; the remaining Codex lines need it.
- `Codex hooks trusted`: Codex's own hook list (`codex app-server`, `hooks/list`) shows every Dryas hook as trusted, and lists each event the plugin ships (SessionStart, UserPromptSubmit, PreToolUse). FAIL until you trust them: re-run setup and answer yes, or run `/hooks` in Codex.
- `Codex plugin hooks run (<event>)`, one line each for SessionStart, UserPromptSubmit and PreToolUse: every command of that event in the installed copy's `hooks/hooks.json` (`$CODEX_HOME/plugins/cache/dryas-workflow/dryas/<version>/`) is run the way Codex runs it, with `PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT` and `CODEX_HOME` set, and a sample event: `sh -c` on the `command` line on macOS and Linux (with `python3` from your PATH, as Codex runs it), `commandWindows` in the Windows shell on Windows. It passes when each exits 0 and prints nothing or JSON.
- `Codex rules hook output`: the SessionStart output carries the Dryas rules and the `Dryas paths:` line.
- `Scope lock (codex)`: the same scope test as for Claude Code, through `apply_patch`, with the installed copy's `jev/chain.py --harness codex`.

## Manual checks (needs the app open)

1. In Claude Code, send any prompt. The reply context shows a `Jev route:` line (when a key is set).
2. In a scratch git repo, run `/orchestrate` on a tiny task, or create `.orchestrate/PLAN.md` and `active.json` by hand. Ask Claude to write a file outside the Scope. The scope lock denies it.
3. In Codex (each Codex home): send a prompt; the context shows a `Jev route:` line (with `OPENROUTER_API_KEY` set). Ask "which workflow rules apply here?"; the answer names the Dryas Workflow. Ask it to edit a file outside the Scope (apply_patch): it is denied.
4. Report the output of the script and these steps in an issue.
5. In each account's Claude Code, run `/plugin` and check dryas is enabled. If hooks did not fire, check for `allowManagedHooksOnly` in managed settings ([install.md](install.md#hooks-blocked-by-policy)).
6. Run `/tune` and `/handoff` once in each account. Both must run without a permission prompt.
7. Codex: type `$dryas:orchestrate` in the TUI and note the syntax that works (record it in [install.md](install.md#codex-plugin-plus-setup) if it differs). On Windows also: steps 3 and 7, and `codex mcp list` shows `jev`.

Steps 3 and 7 are the parts of the Codex plugin no automated test covers: a real model run with the hooks firing, how the TUI takes a plugin skill, and Windows (the `commandWindows` hook lines and `python`).

With several accounts, do steps 1, 2, 5 and 6 in each, and check that `~/.dryas/jev/logs/calls.jsonl` grows from both.

On Windows, also check step 6 closely: the `/tune` and `/handoff` allow rules are written twice, with the plugin path in forward-slash form (`C:/...`) and in backslash form (`C:\...`), because Claude Code may substitute `${CLAUDE_PLUGIN_ROOT}` either way. If either command still prompts, copy the exact command from the prompt into the issue report.
