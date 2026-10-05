# Release check

Run this after installing Dryas Workflow on a new machine (Windows, WSL, macOS or Linux). It checks that the installed hooks run and that the scope lock blocks out-of-scope edits. It only reads your Claude and Codex folders; it writes only to temporary folders.

## Run it

    python tools/release_check.py

On Windows use `py tools\release_check.py`. Options: `--claude-dir` (default `~/.claude`) and `--codex-dir` (default `$CODEX_HOME` or `~/.codex`).

Each line starts with PASS, FAIL, SKIP or WARN. The exit code is 1 if any line is FAIL, otherwise 0.

## What the checks mean

- Environment: your OS, Python, and whether `git`, `claude`, `codex` and `node` are on PATH. It says whether `OPENROUTER_API_KEY` is set, never its value.
- Claude hooks: every hook command the installer added to `settings.json` is run with a sample event. It passes when it exits 0. Output that is not JSON shows a WARN.
- Codex hooks: the same for `hooks.json` (uses `commandWindows` on Windows). Skipped if Codex was not installed.
- Scope lock: in a temporary worktree whose plan allows only `src/feature/**`, a write to `src/other.ts` must be denied. Done for Claude, and for Codex (apply_patch) if installed.
- Jev route: with `OPENROUTER_API_KEY` set, a sample prompt must produce a `Jev ` line. Skipped without the key.
- Ruflo: the data folder (`DRYAS_DATA_ROOT` or `~/.dryas`) exists and is writable, and the Ruflo helper exits quietly. Skipped if Ruflo is not installed.

## Manual checks (needs the app open)

1. In Claude Code, send any prompt. The reply context shows a `Jev route:` line (when the key is set).
2. In a scratch git repo, run `/orchestrate` on a tiny task, or create `.orchestrate/PLAN.md` and `active.json` by hand. Ask Claude to write a file outside the Scope. The scope lock denies it.
3. In Codex, ask it to edit a file outside the Scope (apply_patch). It is denied.
4. Report the output of the script and these steps in an issue.
