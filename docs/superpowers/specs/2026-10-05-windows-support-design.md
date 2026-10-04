# Windows support — design

Date: 2026-10-05
Status: approved in brainstorming, awaiting spec review
Sub-project: A of 2 (B = Codex as main harness, separate spec, built after this one)

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

## Out of scope

- Codex as main harness (sub-project B, its own spec).
- FlowObserve on Windows.
- `.githooks/pre-commit` (maintainer-only).
- Installing Python, Node or Git for the user.
