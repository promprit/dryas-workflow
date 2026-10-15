# Scope lock for shell writes: design

Date: 2026-10-15. Status: draft for review. Branch: `feat/scope-shell-writes`.
Contested: yes (changes how GOV-2 is enforced, turns a PostToolUse stage from observe-only into one that gives feedback, and changes the scope log record that `/tune` reads).

## 1. Goal

While an `/orchestrate` task is active, an executor's shell command that looks like it writes files asks the user (`scope_lock._bash`). After 48b2336 removed the ask for the orchestrator's own commands, executors still produced 77 asks in about 4 hours (2026-10-15, 19:36-23:45), against 2 Jev-gate asks in the same window. Almost every one was approved without changes, so the ask costs attention and protects little.

Goal: **no scope-lock asks for executor shell writes on Claude Code and OpenCode**, with scope enforcement that is at least as strong as the ask it replaces, and a guard so the noise cannot creep back unnoticed.

Success:

- The regression corpus (section 7) produces 0 asks and 0 false denies.
- An executor that writes outside its Scope through the shell is still stopped: denied before the command runs when the target is readable, or told to revert after it runs when it is not.
- `/tune` reports scope asks, denies and post-run violations per day as separate numbers.
- Full test suite passes in all three editions; `tools/release_check.py` passes.

## 2. Evidence

All executor (subagent) Bash commands in both accounts' transcripts from the last 3 days, run through `prescreen.writes`: 18,978 commands, 2,597 write-like (14%). Each one asks while a task is active.

| Cause | Share | Notes |
| --- | --- | --- |
| Detector false positives | large | `=> {` and `> ` inside heredoc bodies and quoted code read as redirects (the top redirect "targets" are `{`, empty, `({`, `=`, `,`); words in commit messages (`split`, `install`) read as commands |
| Inline interpreter edits | ~36% | `python3 - <<EOF ... open(p).write`, `python3 -c`, `node -e`, `perl -pi -e`; executors use these although their rules say to prefer Edit/Write |
| Readable-target writes | rest | `sed -i FILE`, `> FILE`, `cp`/`mv`, `mkdir`, `touch`, `rm`, `tee`; many target the session scratchpad |

`git add` and `git commit` already never ask (`prescreen.writes` is False for them); formatters run through `pnpm`/`npx` (`biome --write`, `prettier --write`) also do not ask.

## 3. Decisions (approved round 1)

1. Executor shell writes never ask on Claude Code and OpenCode. Enforcement moves to a pre-run target check (B) and a post-run change check (C).
2. Writes into the **current session's own scratchpad** are allowed. `/tmp` and build directories in general are not exempt (the earlier decline of a general exemption stands).
3. A post-run violation tells the agent to revert and is logged; nothing is reverted automatically.
4. Codex (no worker identity): A and B apply; C only logs. Codex keeps asking for write-like commands B cannot resolve, because there the main session and workers look the same.

## 4. Design

### A. Detector accuracy (`prescreen.py`)

`writes(cmd)` stops reading code and prose as shell:

- Heredoc bodies (`<<[-]WORD ... WORD`, quoted or not) are removed before the redirect and command-word scans. The command that consumes the heredoc is still scanned (`python3 - <<EOF` stays an inline-interpreter write; `cat > f <<EOF` stays a redirect to `f`).
- `=>`, `->`, `>=` and `>` inside quoted text or `$(...)` arithmetic are not redirects. The redirect scan runs on the quote-masked copy only.
- `_WRITE_PATTERNS` command words match only at command position (start of a simple command, after an operator or a prefix like `env`/`sudo`), not anywhere in the text. Quote-obfuscation (`r''m`, `"rm"`) is still caught through the normalised copy at command position.
- `risky()` (the Jev gate prescreen) is unchanged: it is a denylist and must keep erring toward True.

### B. Pre-run target check (`scope_lock._bash`, new `shellwrites.py`)

A new pure module `shellwrites.py` turns a command into the files it writes, or reports that it cannot tell:

`targets(cmd, cwd) -> (paths: list[str], unknown: bool)`

- Splits into simple commands on unquoted `;`, `&&`, `||`, `|`, newline; tracks `cd <literal>` (and `cd -` / `pushd` as unknown) so later relative paths resolve correctly.
- Readable forms: `sed -i[SUFFIX] ... FILES` (script is the first non-option argument unless `-e`/`-f` is given; `-f` makes it unknown), `perl -[0]pi[.bak] -e SCRIPT FILES`, redirects `>`, `>>`, `&>`, `>|` and `tee [-a] FILES`, `cp`/`mv`/`ln`/`install` (destination; with `-t DIR` the directory), `mkdir`, `touch`, `rm`, `rmdir`, `truncate` (all operands), `git checkout -- PATHS` / `git restore PATHS`.
- Anything else that `writes()` flags is unknown: inline interpreter code, scripts, `$VAR`, `$(...)`, globs, `~user`, `xargs`, `find -exec`, package installs.

Decision for an executor (`agent_id` present) while a task is active:

| Targets | Decision |
| --- | --- |
| Command contains `.orchestrate` | deny (unchanged) |
| Any readable target outside the union Scope and not in the session scratchpad | **deny**, reason names the path and the Scope; the agent can use Edit/Write or stay in scope |
| All readable targets in Scope or scratchpad, nothing unknown | allow (no output) |
| Some part unknown | allow; C checks the result |

The session scratchpad on Claude is `/private/tmp/claude-<uid>/<encoded-launch-dir>/<session_id>/scratchpad`. The launch directory can differ from the event's `cwd`, so the match is: after `realpath`, the path lies under a directory of the form `/private/tmp/claude-<own uid>/<one component>/<event session_id>/scratchpad` (the `session_id` from the hook input must equal that component exactly; subagents carry their parent's `session_id`). OpenCode and Codex have no scratchpad convention; nothing is exempt there.

Paths are compared with `check()`, which already handles worktree escape, `.orchestrate` and case. Out-of-worktree targets other than the scratchpad are denied, which is stricter than today's ask.

Codex: same table, except "some part unknown" keeps today's ask.

### C. Post-run change check (new `scope_post.py`)

A PostToolUse stage on `Bash` for executors while a task is active:

- **Before** (in `scope_lock._bash`, only when B returned "allow" for an executor command): record `git status --porcelain=v1 -z --untracked-files=all` paths of the worktree that are outside the union Scope, keyed by `tool_use_id`, in `~/.dryas/jev/state/scope_pre/<tool_use_id>.json` (pruned after 1 hour). Cost is one `git status`; the stage timeout stays 3 s and a git failure skips C for that call (logged as `post_skipped`).
- **After**: run the same `git status`; new out-of-scope paths (present now, absent before) are violations. Paths in `.orchestrate/` count as violations for executors.
- On a violation (Claude Code): output `{"decision": "block", "reason": "scope lock: this command changed files outside the scope of task(s) N: a, b. Revert them (git checkout -- / rm for new files) and make the change with Edit/Write inside your Scope."}`. Claude Code shows the reason to the agent; the command has already run, so this is feedback, not a veto.
- OpenCode: `tool.execute.after` appends the same reason to `output.output`.
- Codex: log only.
- Every violation is logged to `scope.jsonl` as `{"decision": "violation", "paths": [...], "task": [...]}`.

Parallel executors share one worktree; a change one executor makes in its own scope is inside the union and is not a violation, which matches how `check()` treats Edit/Write today. A change made concurrently by another executor outside the union between the two snapshots would be blamed on this command; that is acceptable because it is still a real violation that needs reverting.

### D. Chain change

`chain.json` gets a `feedback: true` flag for post stages. `chain.observe()` keeps ignoring output for observe stages; for a `feedback` stage it collects the first non-empty JSON output and `chain.main` prints it. Only `scope-post` uses it. Order in `post`: `scope-post` first, then the observe stages. Mirrored in `codex/jev/chain.py` and `opencode/dryas/jev/chain.py`, and the OpenCode plugin reads the post result.

### E. Keeping it fixed

- **Regression corpus**: `claude/jev/tests/fixtures/scope_shell_corpus.jsonl`, about 200 real executor commands from 2026-10-13..15, with paths rewritten to a fixture worktree, commit messages and code bodies trimmed, no secrets (run through `redact.py` and reviewed by hand). Each line carries the expected outcome (`allow`, `deny`, `post`). A test asserts the corpus gives 0 asks for executors.
- **Log detail**: every scope record gets `rule` (which detector or B rule fired) and `kind` (`ask`, `deny`, `violation`, `post_skipped`), so a new noise source shows up by name.
- **`/tune`**: `delivery()` splits `scope_denials` into `scope_asks`, `scope_denies` and `scope_violations` (today it counts every scope row, asks included, as a denial). The weekly report shows asks per day and the top `rule` values.
- **Executor rules**: `claude/agents/executor.md` (synced to Codex and OpenCode) adds one line: inline interpreter edits are checked after the fact and an out-of-scope change must be reverted; prefer Edit/Write.

## 5. GOV-2 wording

`spec/dryas-spec-v1.md` GOV-2 is unchanged (it already allows listing shell writes as a known limit). `reference/README.md` GOV-2 row becomes: "Hook denies Edit/Write outside scope; shell writes with readable targets are denied outside scope, other shell writes are checked after they run (agent told to revert). Writes outside the worktree by inline code are a known limit. Codex: unresolvable shell writes ask." Status stays `partial` in all three columns.

## 6. Out of scope

- Automatic revert.
- Sandboxing or blocking interpreter code.
- Changing the Jev gate or `risky()`.
- The orchestrator's own shell writes (already not asked since 48b2336).

## 7. Testing

- `prescreen.writes`: heredoc bodies, arrow functions, quoted messages, command-position words, obfuscation still caught.
- `shellwrites.targets`: each readable form, `cd` tracking, unknown cases, `-f` scripts, globs.
- `scope_lock._bash`: the decision table per harness, scratchpad match and near-miss (`scratchpad2`, other session id, symlink).
- `scope_post`: no change, in-scope change, out-of-scope new and modified files, `.orchestrate`, git failure, missing pre-snapshot.
- `chain`: feedback stage output is printed; observe stage output still ignored; a crashing feedback stage prints nothing.
- Corpus test (section 4 E).
- Three-edition parity test for `scope_lock.py`, `prescreen.py`, `shellwrites.py`, `scope_post.py` (existing parity checks extended).

## 8. Rollout

Ship as a minor release. After merge, upgrade the plugin cache in both accounts (`claude plugin marketplace update dryas-workflow`, `claude plugin update dryas@dryas-workflow`, `install/install.sh --yes --claude-dir <dir>`) and restart sessions; otherwise nothing changes locally. Check the next day's `/tune` scope asks.
