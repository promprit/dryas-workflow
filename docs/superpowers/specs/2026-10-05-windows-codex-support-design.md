# Windows and Codex support — design

Date: 2026-10-05
Status: approved in brainstorming, awaiting spec review
Scope: Part A (Windows support) and Part B (Codex as main harness: rules, MCP, and the safety and routing hooks). One plan; Part A tasks first, Part B builds on the portable installer from Part A.

# Part A — Windows support

## Goal

Make `dryas-workflow` a shareable install that works for other people on native Windows and WSL, in addition to macOS and Linux, with Claude Code as the harness. Existing macOS installs must keep working and upgrade cleanly by re-running the installer.

Success means:

- `install.ps1` on native Windows and `install.sh` on macOS, Linux and WSL install the same components (core, jev, ruflo, superpowers, design) from one code path.
- All hooks fire on every supported OS: scope lock, Jev gate and route, context watch, compaction and handoff, and the Ruflo hooks.
- The test suites pass in CI on macOS, Ubuntu and Windows.

## Constraints

- One implementation. No parallel `.sh` and `.ps1` logic.
- No runtime dependency on a particular shell. Hook commands must run whether Claude Code invokes them through bash, Git Bash or cmd.
- The installer never installs system packages (Python, Node, Git). It checks for them and reports what is missing.
- Billing rules are unchanged: no `ANTHROPIC_API_KEY`; Jev uses only `OPENROUTER_API_KEY` from the environment.
- Mac + Claude Code remains the primary platform and must not regress.

## Where the POSIX coupling is today

1. Hook commands in `claude/settings.fragment.json` call `/bin/sh "$HOME/..."` and `/usr/bin/python3`, and rely on the shell expanding `$HOME` at runtime.
2. Shell shims: `claude/hooks/pretool-chain.sh`, `claude/hooks/prompt-chain.sh` (and their copies in `claude/jev/hooks/`), and the Ruflo shims `claude/ruflo/run.sh`, `cli.sh`, `ns.sh`, which contain real logic (data root, git namespace, node fallback, `NODE_PATH`).
3. `claude/ruflo/mcp-shim/bin/cli.js` runs `/bin/sh` to source `ns.sh` for the namespace.
4. Installer: `install/install.sh` does preflight in sh; `install/dryas_install.py` hardcodes `PY = "/usr/bin/python3"`, detects tools with `/bin/sh -lc "command -v ..."`, and creates `ruflo/mcp-shim/dist` with `os.symlink`.
5. Command and skill text: `/usr/bin/python3 ...` in `claude/commands/tune.md`, `claude/commands/handoff.md` and `claude/skills/orchestrate/SKILL.md`.
6. `.githooks/pre-commit` is maintainer-only and stays sh (out of scope).

## Design

### Components

| Unit | Today | After |
|---|---|---|
| Hook entry | `/bin/sh pretool-chain.sh`, which calls python | `"<PY>" "<CD>/jev/chain.py" pretool` directly; the `.sh` hook shims are deleted |
| Ruflo hook runner | `run.sh` + `cli.sh` + `ns.sh` | `claude/ruflo/run.py` with subcommands `helper` and `cli`, plus `claude/ruflo/ns.py`; same contract (silent no-op, never exit 2) |
| mcp-shim namespace | `/bin/sh` sourcing `ns.sh` | inline JS `rufloNs()` in `cli.js` implementing the same algorithm |
| `dist` link | `os.symlink` | symlink on POSIX; directory junction on Windows (`_winapi.CreateJunction`, no admin or Developer Mode needed); link type stored in `.dryas-installed.json` |
| Interpreter | `/usr/bin/python3` | `sys.executable` of the Python running the installer, checked for ≥ 3.9, rendered as `PY` |
| Installer entry | `install.sh` with preflight in sh | preflight moves into `dryas_install.py preflight`; `install.sh` and a new `install.ps1` are thin wrappers (about 10 lines) that find a Python ≥ 3.9 and forward all arguments |
| Tool detection | `/bin/sh -lc "command -v ..."` | `shutil.which()`; `npm root -g` via `subprocess` with the resolved `npm` path (`npm.cmd` on Windows), never `shell=True` |
| Command text | `/usr/bin/python3 ~/.claude/...` in three `.md` files | `{{PY}}` and `{{CD}}` tokens rendered when the files are copied |

### Rendering

`settings_merge.render()` currently substitutes placeholders only in `env`. It is extended to also substitute in every hook `command` string. The grammar stays `$NAME` / `${NAME}`; an unmapped placeholder is a hard error, as today.

Copied `.md` files use a separate token grammar, `{{PY}}` and `{{CD}}`, because their text legitimately contains shell variables such as `"$PWD"` that must stay literal. Only these two tokens are replaced; an unknown `{{NAME}}` is a hard error.

Rendered paths are absolute, use forward slashes and are double-quoted, for example `"C:/Users/ana/.claude/jev/chain.py"`. One string is then valid in bash, Git Bash and cmd, and no hook depends on runtime `$HOME` expansion.

New mapping keys: `PY` (interpreter) and `CD` (Claude directory). `HOME` and `DRYAS_DATA_ROOT` stay.

### Namespace algorithm (shared by `ns.py` and `cli.js`)

1. Start from `CLAUDE_PROJECT_DIR`, else the current directory.
2. Run `git -C <dir> rev-parse --path-format=absolute --git-common-dir`.
3. If the result's last component is `.git` (compare with `pathlib`/`path`, not string splitting, because Windows returns `C:/...`), the name is the basename of its parent. Otherwise the name is the basename of the start directory.
4. Replace every character outside `[A-Za-z0-9._-]` with `_`. Empty, `.` or `..` becomes `_unknown`.

### Upgrade path for existing installs

Re-running the installer moves existing users from the old hook strings to the new ones.

- Before merging, `install` compares the existing record with the new fragment. Recorded hook entries and env values that the new fragment no longer produces (for example `/bin/sh "$HOME/.claude/hooks/pretool-chain.sh"`) are removed with the existing undo logic; then the new fragment is merged. Entries the user edited by hand are not in the record, so they are left alone and reported as conflicts.
- Files listed in the record that are no longer shipped (`hooks/*.sh`, `ruflo/*.sh`) are deleted, and a recorded backup is restored if there is one.
- `verify` gains a check: no hook command in `settings.json` references `/bin/sh` or a file that does not exist.

### Runtime flow

Unchanged in meaning:

- Claude Code event → `"<PY>" chain.py <stage>` → scope lock → Jev → Ruflo stage → JSON on stdout.
- Ruflo hooks: `"<PY>" run.py helper <file> <args>` → resolve data root → namespace → `cd <root>/ruflo/<ns>` → spawn node. If the data root, the binary or the helper file is missing: drain stdin, exit 0.

### Error handling and edge cases

- **Python removed after install** (for example a deleted venv): the hook exits non-zero but not 2, so Claude Code shows a non-blocking error and the session continues. The next `verify` reports it.
- **Spaces in paths:** the Ruflo plugin splits `RUFLO_HOOK_CLI_OVERRIDE` on spaces, so a space in the path to `~/.claude` breaks Ruflo. This is common on Windows (`C:\Users\Ana Silva`). On Windows the installer renders the 8.3 short path (`GetShortPathNameW`). The same applies to the interpreter path when Python lives under a path with spaces (`C:\Program Files\Python312`). If no short name exists (8.3 names can be disabled per volume), preflight refuses the Ruflo component with a clear message suggesting `--no-ruflo`. This is the current behaviour, now applied on every OS.
- **Text encoding:** hook stdin is UTF-8, but Python on Windows reads it in the console code page, so every hook, chain stage and MCP command runs Python with `-X utf8`, and every installer read or write of a text file uses `encoding="utf-8"`.
- **Line endings:** add `.gitattributes` with `* text=auto eol=lf` and `*.ps1 text eol=crlf`, so Windows clones do not break Python, JS or the sh wrapper.
- **File modes:** `chmod 0o600`/`0o700` calls stay; on Windows they are effectively no-ops. Tests that assert modes skip that assertion on Windows.

## Testing

- Existing pytest suites (`claude/jev/tests`, `install/tests`) must pass on all three operating systems. POSIX-only assumptions found along the way are fixed.
- `claude/ruflo/test_run.sh` is ported to pytest (`test_run.py`): no-op contract, namespace, node fallback, data root.
- One shared vectors file, `claude/ruflo/ns_cases.json` (plain repo, worktree, bare repo, non-git directory, unusual characters), is used by both the `ns.py` tests and `test_mcp.cjs`, so the Python and JS implementations cannot drift.
- Installer tests: rendering of hook commands and `.md` placeholders; junction vs symlink recorded correctly; upgrade from an old-format record fixture (stale `.sh` hooks and files removed, user-added hooks kept).
- Hook-string smoke test: render the settings, then run each hook `command` through the platform shells (bash on POSIX; cmd and Git Bash on Windows) with a sample event. Each must exit 0 and print valid JSON or nothing.

### CI

GitHub Actions matrix: `macos-latest`, `ubuntu-latest`, `windows-latest` × Python 3.9 and 3.12, with Node 20 for `test_mcp.cjs`. Each job runs the test suites, an installer `--dry-run`, and a real install into a temporary `HOME`/`USERPROFILE`. The `claude` and `ruflo` CLIs are replaced by fake shims on `PATH`, so plugin and MCP registration are exercised without network or authentication.

### Manual release check

Cannot be automated; done once before release by the maintainer or a tester: run Claude Code on native Windows and in WSL after installing. Confirm that hooks fire, the Jev route line appears, and Ruflo memory is written under the data root.

## Documentation

- `docs/install.md`: a Windows section (prerequisites: Python ≥ 3.9, Git for Windows, Node; run `.\install\install.ps1`) and a WSL note (follow the Linux steps).
- `README.md`: CI status badge; mention Windows support.
- `~/.claude/DryasWorkflow.md` (and its backup) only if a user-visible rule changes.

## Out of scope (Part A)

- FlowObserve on Windows: its hook, Node server (launchd today) and installer live in the separate `flowobserve` repo and get their own spec there. This repo only guarantees the `flowobserve` chain stage is portable (rendered `"<PY>" -X utf8 <HOME>/.flowobserve/bin/fo_hook.py`, no shell).
- `.githooks/pre-commit` (maintainer-only).
- Installing Python, Node or Git for the user.

# Part B — Codex as main harness (rules, MCP, safety and routing hooks)

## Goal

People who use Codex (CLI, IDE extension or desktop app) as their main agent get the Dryas Workflow process rules, the workflow commands as Codex skills, and the Jev and Ruflo MCP servers, from the same installer, on every OS Part A supports.

## Codex facts this design relies on (checked 2026-10-05)

- Config: `~/.codex/config.toml`, or `$CODEX_HOME/config.toml` when `CODEX_HOME` is set. MCP servers are `[mcp_servers.<name>]` tables with `command`, `args`, `env`; `codex mcp add` writes them. The CLI, IDE extension and desktop app share this file.
- Global instructions: `$CODEX_HOME/AGENTS.md` (default `~/.codex/AGENTS.md`); `AGENTS.override.md` wins if present. Combined instructions are capped at 32 KiB by default (`project_doc_max_bytes`).
- Skills: user-level skills live in `~/.agents/skills/<name>/SKILL.md`, with the same `name` / `description` frontmatter as Claude skills. Invoked with `$name`, from `/skills`, or chosen automatically by description.
- Hooks: `$CODEX_HOME/hooks.json` (or inline `[hooks]` in `config.toml`), same shape as Claude Code: event → list of `{matcher, hooks: [{type: "command", command, timeout}]}`. Events include `PreToolUse` and `UserPromptSubmit`. Stdin JSON carries `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`, plus `tool_name` / `tool_input` (PreToolUse) or `prompt` (UserPromptSubmit). Output contract matches Claude Code: `hookSpecificOutput.permissionDecision: "deny"` with `permissionDecisionReason`, `hookSpecificOutput.additionalContext`, `{"decision": "block", "reason"}`, or exit code 2. File edits arrive as `tool_name: "apply_patch"` with the patch text in `tool_input.command`. Default timeout 600 s. Hooks can be disabled with `[features] hooks = false`.

## Design

### Installer target

- New flag `--harness claude|codex|both`, default `claude` (existing behaviour unchanged).
- Codex target directory: `$CODEX_HOME` if set, else `~/.codex`. Skills target: `~/.agents/skills`.
- Reuses the Part A installer core: same `.dryas-installed.json` record format (one record per target directory), same uninstall, same `{{PY}}` / `{{CD}}` rendering, same preflight. Preflight for the Codex target requires the `codex` CLI on `PATH`.
- Components for Codex: `core` (AGENTS.md block, skills), `jev` (MCP server), `ruflo` (MCP server). `superpowers` and `design` are not installed for Codex (see below); passing them with `--harness codex` prints a note and is otherwise ignored.

### AGENTS.md block

- `install/claude_md_block.py` is generalised to take a target path and template, keeping the same start/end markers logic. It inserts or replaces one marker-delimited block in `~/.codex/AGENTS.md` (creating the file if missing) and removes it cleanly on uninstall.
- Template: `codex/AGENTS.md.template`. Content: the process rules that apply in any harness (Dryas Workflow §1 and §16: brainstorm first, worktree per multi-step task, plan as a file, TDD, two-stage review, verification before completion, commit only after review, never push without asking), the Jev and Ruflo usage rules, and a pointer to the full workflow reference. It must stay well under the 32 KiB cap; a test asserts the rendered block is under 8 KiB.

### Skills

- New folder `codex/skills/` with `orchestrate`, `wreview`, `wplan`, `commit` and `tune`, each a `SKILL.md` in the shared format, copied to `~/.agents/skills/<name>/`.
- Bodies are adapted from the Claude versions where they name Claude-only features: Codex uses its own sub-agent mechanism instead of the Agent tool and the `executor` agent; the model rule is "cheaper model first, escalate on failure", with every escalation logged via the `jev` MCP tool `log_escalation`; commit messages and plans name the harness. Python calls use `{{PY}}` / `{{CD}}` like the Claude versions.
- No `handoff` skill: `handoff.py` scores Claude Code transcripts, so it has nothing to read in a Codex session.
- A skill directory that already exists and is not in the record is skipped and reported, unless `--force` (same rule as Claude files).

### MCP servers

- `jev`: command `{{PY}}`, args `[<CD>/jev/jev_mcp.py]`, where `<CD>` is the Claude directory installed by Part A (Jev code is installed once and shared by both harnesses; `--harness codex` alone still installs the Jev files under the Claude directory).
- `ruflo`: command `node`, args `[<CD>/ruflo/mcp-shim/bin/cli.js, mcp, start]`, with the same `DRYAS_DATA_ROOT` and Ruflo env values as the Claude settings fragment.
- Written with `codex mcp add <name> -- <command> <args...>` (env via its flags). If `codex mcp add` is missing or fails, the installer writes the table itself between `# >>> dryas-workflow >>>` / `# <<< dryas-workflow <<<` markers in `config.toml`, never touching anything outside the markers. The method used is stored in the record; uninstall uses `codex mcp remove` or removes the marked region accordingly.
- Billing rule unchanged: no `ANTHROPIC_API_KEY` is written; Jev reads only `OPENROUTER_API_KEY` from the environment.

### Hooks (safety and routing)

Only the scope lock, the Jev gate and the Jev route run under Codex. Context watch, compaction keep and restore, handoff restore, the Ruflo hooks and FlowObserve stay Claude Code only, because they read Claude Code transcripts or Claude-shaped events.

- **Install:** the installer merges two entries into `$CODEX_HOME/hooks.json` with `settings_merge.merge` (the `hooks` shape is identical) and records them; uninstall removes exactly those entries with `settings_merge.unmerge`, deleting the file if the installer created it and it ends up empty.
  - `PreToolUse`, matcher `Bash|apply_patch|Edit|Write`: `"<PY>" "<CD>/jev/chain.py" pretool --harness codex`, timeout 20.
  - `UserPromptSubmit`: `"<PY>" "<CD>/jev/chain.py" prompt --harness codex`, timeout 15.
  - Each entry also carries `commandWindows`, built from the space-free (8.3) forms of the interpreter and Claude directory and left unquoted, because Codex on Windows may run hook commands through PowerShell, where a quoted path is a string, not a command. If no space-free form exists, preflight refuses `--harness codex|both` on Windows and suggests `--harness claude`.
- **Normalizer:** new module `claude/jev/codex_event.py`, used by `chain.py` when `--harness codex` is passed.
  - `apply_patch`: parse the headers `*** Add File: <path>`, `*** Update File: <path>`, `*** Delete File: <path>` and `*** Move to: <path>` (CRLF tolerated). Each touched path (including both source and destination of a move) becomes one synthetic event `{"tool_name": "Write", "tool_input": {"file_path": <path>, "content": <that file's hunk text>}, "cwd": <cwd>}`. The pretool chain runs once per synthetic event; the strictest decision wins (deny > ask > none), and the reason names the file.
  - **Fail closed:** a patch that cannot be parsed, or has no file headers, is denied with reason `[codex-patch] unparseable apply_patch`.
  - `Bash`, `Edit`, `Write` and every other tool pass through unchanged.
- **Stage selection:** each stage in `chain.json` may carry `"harness": [...]`; a missing key means `["claude"]`. `scope-lock`, `jev-gate` and `jev-route` get `["claude", "codex"]`. `chain.py` skips stages whose list does not contain the current harness (default `claude`).
- **Route wording:** `chain.py` sets `DRYAS_HARNESS` in the stage environment. When it is `codex`, `route.py` prints `escalate: yes|no (<conf>)` instead of `opus: yes|no (<conf>)`; the Jev question and the log fields are unchanged.

### Superpowers for Codex

The installer does not install Superpowers for Codex. It checks whether Superpowers' skills are present under `~/.agents/skills` (or Codex's plugin locations) and, if not, prints Superpowers' documented Codex install step. Nothing is fetched from third parties for the Codex target.

### Docs

- `docs/harnesses.md`: Codex moves from "Coming" to supported (rules + MCP), with a clear list of what Codex users do not get.
- `docs/install.md`: `--harness` flag, Codex prerequisites.
- `~/.claude/DryasWorkflow.md` §16 and its backup: updated to say the installer sets up Codex.

## Testing (Part B)

- Fake `codex` CLI on `PATH` that records `mcp add` / `mcp remove` calls, plus a variant that fails so the TOML fallback runs.
- AGENTS.md block: insert into missing file, insert into existing file with user content, replace on re-install, remove on uninstall leaving user content byte-identical; rendered block size under 8 KiB.
- Skills copy and uninstall; existing unrecorded skill directory skipped without `--force`.
- `config.toml` fallback: marked region added, re-install idempotent, uninstall restores the file byte-identical to before.
- `--harness both`: one run produces both targets; uninstall removes both.
- Patch parser: add, update, delete, move, multi-file, CRLF line endings, no headers, garbage input.
- Chain under `--harness codex`: an `apply_patch` touching one in-scope and one out-of-scope file is denied naming the out-of-scope file; an unparseable patch is denied; a Claude-only stage (context-watch) does not run; `DRYAS_HARNESS=codex` makes `route.py` print `escalate:`.
- `hooks.json` merge: created when missing, merged next to user hooks, re-install idempotent, uninstall leaves user hooks byte-identical.
- Without `--harness`, `chain.py` behaves exactly as before (existing tests unchanged).
- Runs in the same three-OS CI matrix as Part A.

## Out of scope (Part B)

- Codex context watch, compaction keep and restore, handoff restore and Ruflo hooks (need a Codex transcript reader and Codex-shaped Ruflo handlers; possible follow-up).
- FlowObserve for Codex sessions.
- The Sonnet → Opus → Fable ladder and the `executor` agent (Claude Code-specific).
- Installing Superpowers, impeccable or ui-ux-pro-max for Codex.
