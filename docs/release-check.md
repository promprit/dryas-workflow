# Release check

Run this after installing Dryas Workflow on a new machine (Windows, WSL, macOS or Linux). It checks that the plugin is installed in each Claude config dir, that its hooks run and that the scope lock blocks out-of-scope edits. It never changes your Claude or Codex folders or `~/.dryas`: the hooks it runs get a temporary folder for their logs, handoffs, compaction notes, data root and `chain.local.json` (empty, so optional local stages such as FlowObserve stay off), and no OpenRouter key. Only the Jev route check calls OpenRouter, when a key is set, and its logs also go to a temporary folder.

## Run it

    python tools/release_check.py
    python tools/release_check.py --claude-dir ~/.claude --claude-dir ~/.claude-team

On Windows use `py tools\release_check.py`. Options: `--claude-dir` (repeat it once per account; default `~/.claude`) and `--codex-dir` (default `$CODEX_HOME` or `~/.codex`).

Each line starts with PASS, FAIL, SKIP or WARN. The exit code is 1 if any line is FAIL, otherwise 0.

## What the checks mean

- Environment: your OS, Python, and whether `git`, `claude`, `codex` and `node` are on PATH. It says whether an OpenRouter key is set in this shell, never its value.
- `plugin manifests valid`: runs `claude plugin validate` on the repo's marketplace and on `claude/`. Skipped when `claude` is not on PATH.

Then, for each `--claude-dir`, under a `Claude Code: <dir>` heading:

- `dryas plugin installed`: `dryas@dryas-workflow` is listed in `<dir>/plugins/installed_plugins.json`. FAIL means setup was not run for that dir.
- `plugin hooks run (<event>)`, one line each for PreToolUse, UserPromptSubmit, SessionStart and PreCompact: every command of that event in the installed plugin's `hooks/hooks.json` is run the way Claude Code runs it (`bash -c`, with `CLAUDE_PLUGIN_ROOT`, `DRYAS_PY` and `CLAUDE_CONFIG_DIR` set) with a sample event. It passes when each exits 0 and prints nothing or JSON. On Windows it needs Git Bash; without it the lines are SKIP.
- `Scope lock (claude)`: in a temporary worktree whose plan allows only `src/feature/**`, a write to `src/other.ts` must be denied by the plugin's `jev/chain.py`.
- `Jev route`: with an OpenRouter key in this shell (`OPENROUTER_API_KEY`, `DRYAS_OPENROUTER_KEY` or `CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY`), a sample prompt must produce a `Jev ` line. Skipped without one. A key stored only as the plugin option is visible only inside Claude Code; manual step 1 covers it.
- Ruflo (when setup installed it for that dir): the data folder (`DRYAS_DATA_ROOT` or `~/.dryas`) exists and is writable, `ruflo/helpers/hook-handler.cjs` is in it, and the plugin's Ruflo helper runner exits quietly (run against a temporary data folder). Skipped otherwise.

Codex, last:

- Codex hooks: every hook command the installer added to `hooks.json` is run with a sample event (uses `commandWindows` on Windows). Output that is not JSON shows a WARN. Skipped if Codex was not installed.
- `Scope lock (codex)`: the same scope test through `apply_patch`.

## Manual checks (needs the app open)

1. In Claude Code, send any prompt. The reply context shows a `Jev route:` line (when a key is set).
2. In a scratch git repo, run `/orchestrate` on a tiny task, or create `.orchestrate/PLAN.md` and `active.json` by hand. Ask Claude to write a file outside the Scope. The scope lock denies it.
3. In Codex, ask it to edit a file outside the Scope (apply_patch). It is denied.
4. Report the output of the script and these steps in an issue.
5. In each account's Claude Code, run `/plugin` and check dryas is enabled. If hooks did not fire, check for `allowManagedHooksOnly` in managed settings ([install.md](install.md#hooks-blocked-by-policy)).
6. Run `/tune` and `/handoff` once in each account. Both must run without a permission prompt.

With several accounts, do steps 1, 2, 5 and 6 in each, and check that `~/.dryas/jev/logs/calls.jsonl` grows from both.
