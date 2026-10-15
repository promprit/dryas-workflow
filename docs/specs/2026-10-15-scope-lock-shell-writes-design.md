# Unattended orchestration: design

Date: 2026-10-15. Status: draft for review. Branch: `feat/scope-shell-writes`.
Contested: yes (changes how GOV-2 is enforced during a run, turns Jev-gate asks into denies while a task is active, adds a plan section the gate reads, and changes the scope log record that `/tune` reads).

## 1. Principle and goal

**The user decides in brainstorm and plan; `/orchestrate` then runs without them.** Critical questions belong in the design and plan rounds. During a run, nothing asks the user about mechanics (a shell command, Write versus Edit, a scratch file). Every hook either decides (allow, or deny with a reason the agent can act on) or hands the matter to the orchestrator. What truly needs the user goes into one report at the end.

Success:

- **Zero prompts per run**, measured: `/tune` reports prompts per run, and the regression corpus (section 9) gives 0 asks.
- Scope enforcement is no weaker than today's ask: out-of-scope shell writes are denied before they run when the target is readable, and caught at task return when it is not.
- Each run ends with numbers and stored lessons that the next plan reads (section 7).
- Full test suite passes in all three editions; `tools/release_check.py` passes.

## 2. Evidence (2026-10-13..15)

- Scope lock: 77 asks in about 4 hours after 48b2336 (19:36-23:45 on 2026-10-15), all for executor shell writes. Jev gate: about 7 asks that day (`rm`, `git reset --hard`, `python3`).
- All executor Bash commands in both accounts' transcripts for 3 days: 18,978; 2,597 (14%) look like writes to `prescreen.writes`, so each one asks.

| Cause | Share | Notes |
| --- | --- | --- |
| Detector false positives | large | `=> {` and `> ` in heredoc bodies and quoted code read as redirects; words in commit messages (`split`, `install`) read as commands |
| Inline interpreter edits | ~36% | `python3 - <<EOF ... open(p).write`, `python3 -c`, `node -e`, `perl -pi -e`, although executor rules prefer Edit/Write |
| Readable-target writes | rest | `sed -i FILE`, `> FILE`, `cp`/`mv`, `mkdir`, `touch`, `rm`, `tee`; many into the session scratchpad |

`git add`/`git commit` and formatters through `pnpm`/`npx` never ask today.

## 3. Decisions (approved in brainstorm)

1. Executor shell writes never ask. Readable targets are checked before the run (B); everything is checked at task return (C).
2. Writes into the current session's own scratchpad are allowed; `/tmp` and build directories in general are not exempt.
3. Out-of-scope changes are sent back to the executor to revert; nothing is reverted automatically.
4. During a run, a Jev-gate "ask" becomes a deny with a reason, except for actions the approved plan lists (D).
5. The planner proposes the risky actions a plan expects; approving the plan approves them. The user writes nothing extra.
6. `/orchestrate` checks before starting that the run cannot prompt; if it could, it does not start and says what to change. It never changes settings itself.
7. One report and one push notification when the run ends or stops; a blocked task is reported as not done.
8. Ponytail: the smallest mechanism that holds. No per-command snapshots, no new hook kind.

## 4. Design

"During a run" means `.orchestrate/active.json` exists with a non-empty `active` list (today's `task_active`).

### A. Detector accuracy (`prescreen.writes`)

- Heredoc bodies (`<<[-]WORD ... WORD`, quoted or not) are removed before scanning; the consuming command is still scanned (`python3 - <<EOF` stays an inline-interpreter write, `cat > f <<EOF` stays a redirect to `f`).
- Redirects are found on the quote-masked copy only, so `=>`, `->`, `>=` inside quotes are not redirects.
- `_WRITE_PATTERNS` command words match at command position only (start of a simple command, after an operator or a prefix such as `env`, `sudo`, `time`). Quote obfuscation (`r''m`, `"rm"`) is still caught through the normalised copy at command position.
- `risky()` (the gate prescreen) is unchanged.

### B. Pre-run target check (`scope_lock._bash`, new `shellwrites.py`)

`shellwrites.targets(cmd, cwd) -> (paths, unknown)` is a pure function:

- Splits into simple commands on unquoted `;`, `&&`, `||`, `|`, newline; follows `cd <literal>` (`cd -`, `pushd`, `cd $X` make the rest unknown).
- Readable forms: `sed -i[SUFFIX] [-e S]... FILES` (the first non-option argument is the script unless `-e` is given; `-f` makes it unknown); `perl -[0]pi[.bak] -e S FILES`; redirects `>`, `>>`, `&>`, `>|`; `tee [-a] FILES`; `cp`/`mv`/`ln`/`install` destination (`-t DIR` → DIR); `mkdir`, `touch`, `rm`, `rmdir`, `truncate` operands; `git checkout -- PATHS`, `git restore PATHS`.
- Anything else `writes()` flags is unknown (interpreter code, scripts, `$VAR`, `$(...)`, globs, `~user`, `xargs`, `find -exec`, package installs).

For a write-like command during a run, in this order (the main session on Claude and OpenCode stays unchecked, as since 48b2336):

| Case | Decision |
| --- | --- |
| Executor command names `.orchestrate` | deny (unchanged) |
| A readable target is outside the union Scope and not in the session scratchpad | deny: "scope lock: `<path>` is outside the scope of task(s) N; use Edit/Write inside your Scope or report `SCOPE: need <path> because <reason>`" |
| Otherwise (all readable targets allowed, or some part unknown) | allow, no output; C checks the result |

Same table on all three harnesses. On Codex the main session is not exempt (no worker identity), so the orchestrator's readable out-of-scope targets are denied there too; its `.orchestrate` writes stay allowed through `check()`.

Session scratchpad (Claude only): after `realpath`, the path lies under `/private/tmp/claude-<own uid>/<one component>/<event session_id>/scratchpad` (the `session_id` from the hook input; subagents carry their parent's). OpenCode and Codex exempt nothing.

Readable targets are compared with `check()`, which already handles worktree escape, `.orchestrate` and case. A readable target outside the worktree (not the scratchpad) is denied.

### C. Scope audit at task return (new `scope_audit.py`)

Replaces the ask for what B cannot read. Deterministic, no model call, run by the orchestrator in orchestrate §6 for every executor report before `jev_judge`:

`dryas-py jev/scope_audit.py .orchestrate/PLAN.md <N> <base-sha> [<commit-sha>...]`

- Files changed by the task's commits (`git diff --name-only <base>..<sha>` for each reported commit; `<base>` is HEAD when the task was dispatched, recorded by the orchestrator) must match task N's Scope.
- Uncommitted changes and untracked files (`git status --porcelain -z --untracked-files=all`) must match the union Scope of all active tasks (another running executor's work is not this task's fault).
- `.orchestrate/` is never a valid executor change.
- Output: JSON `{"ok": bool, "outside": [paths]}`; exit 0 either way, so it never blocks the orchestrator's shell.

When `ok` is false, the task is not done: the orchestrator re-dispatches it on the same model with "revert these files: … (`git checkout -- <path>` for tracked, delete for new); make the change with Edit/Write inside your Scope". This is not a climb. A second audit failure on the same task is handled like any failure (§7 ladder). Each failure is logged to `scope.jsonl` as `{"kind": "violation", "task": N, "paths": [...]}`.

Known limit (stated in GOV-2): inline code that writes outside the worktree, other than the scratchpad, is not seen by A, B or C.

### D. Jev gate during a run (`gate.py`) and planned risky actions

- While a run is active, `gate.decide` turns "ask" into "deny" with reason "Jev gate: looks destructive (<reason>); denied during an unattended run. Find a safer way, or report `NEEDS USER: <action> because <reason>`". The orchestrator, too, receives the deny rather than a prompt.
- **Planned risky actions.** The plan header gets an optional section `Risky actions:` listing exact commands or command prefixes ending in `*` (for example `rm -rf dist`, `pnpm db:reset*`). `/wplan` proposes it from the tasks; the user approves it with the plan. During a run the gate allows a command that matches an entry exactly or by prefix, as a whole simple command (a match inside `a && b` covers only that part; every other part is judged as usual). Matches are logged with `"rule": "planned"`.
- `planfile.py` parses the section; a malformed section is ignored (nothing pre-approved), never fatal.
- Outside a run the gate behaves as today.

### E. Preflight (`/orchestrate` §1, new `preflight.py`)

Before writing `active.json` for the first time, the orchestrator runs `dryas-py jev/preflight.py`:

- Reads the session's Claude Code `permission_mode` from the latest hook event the chain logged for this `session_id` (the chain records it in `calls.jsonl`; verify at plan time that Claude Code passes `permission_mode` in hook input).
- `ok` when the mode is `auto`, `acceptEdits` with every plan command covered by `permissions.allow`, or `bypassPermissions`; otherwise it lists what would prompt.
- Not `ok`: the orchestrator does not start; it tells the user what to change (for example "start the session in auto mode") while they are still there. It never edits settings.
- OpenCode and Codex: the check reads their permission config where available; where it cannot tell, it reports "unknown" and the run starts with a one-line warning.

### F. End of run

- **One report**: done tasks; tasks not done and why; denied actions and `NEEDS USER` items; numbers (prompts, denies, violations, climbs, median lines per task).
- **One push notification** when the run ends or stops (PushNotification where the harness has it).
- A run whose remaining tasks are all blocked by denies stops, writes the report and notifies; it does not wait.

### G. Plain language for every user-facing moment

The user may not read code. Everything this design shows the user is written so a non-programmer can decide:

- **Risky actions in the plan**: each entry has a plain sentence next to the command: what it does, what could be lost, why the plan needs it (for example "`rm -rf dist`: deletes the build folder; it is rebuilt automatically, nothing of yours is lost"). The user approves the sentences; the command is there for whoever wants it.
- **Preflight**: says what to do, not what is wrong in settings terms (for example "Restart Claude and press Shift+Tab until the bottom line says auto mode, then run /orchestrate again").
- **End report**: leads with outcomes in plain words ("3 of 4 parts are done; the payment part is waiting for you because it needs to delete the test database"). Numbers, paths and commits come after, under a "Details" heading.
- **Notification**: one sentence, plain words.
- The brainstorm and plan questions already follow this (one decision per question, a recommended answer); `/wplan` checks the Risky actions sentences in its self-review.

## 5. Executor rules

`claude/agents/executor.md` (synced to Codex and OpenCode) adds: "Edit files with Edit/Write. Shell edits that touch files outside your Scope are denied or sent back at task return. Never run a destructive command the plan's Risky actions do not list; report `NEEDS USER: <action> because <reason>` instead."

## 6. Logging

Every `scope.jsonl` record gets `kind` (`ask`, `deny`, `violation`) and `rule` (the detector or B rule that fired); gate records get `"rule": "planned"` or `"run_deny"` where D applied. `tune.delivery` splits today's `scope_denials` (which counts asks too) into `scope_asks`, `scope_denies`, `scope_violations`, and adds `run_prompts` (asks of any stage while a run was active).

## 7. Getting better after every run

At the end of a run the orchestrator:

1. Stores one `memory_store` lesson per recurring cause, kind `outcome`, for example "executor used `python3 - <<EOF` 14 times" or "plan missed risky action `rm -rf dist`". `memory_search` surfaces it when the next plan is written.
2. Puts proposals into the report, never applies them: an action denied in two runs becomes a suggested `Risky actions` default for similar plans; a new detector false positive becomes a corpus candidate. The user accepts them later through `/retro` or `/wplan`.

## 8. GOV-2 wording

`spec/dryas-spec-v1.md` GOV-2 is unchanged. `reference/README.md` GOV-2 row: "Hook denies Edit/Write outside scope; shell writes with readable targets are denied outside scope; every task's changes are audited against its scope at return and sent back if outside. Writes outside the worktree by inline code are a known limit." Status stays `partial`.

## 9. Testing

- `prescreen.writes`: heredoc bodies, arrow functions, quoted messages, command-position words; obfuscation still caught; `risky()` results unchanged on its existing tests.
- `shellwrites.targets`: each readable form, `cd` tracking, unknown cases.
- `scope_lock._bash`: decision table per harness; scratchpad match and near misses (`scratchpad2`, other session id, symlink out).
- `scope_audit`: in scope, committed out of scope, uncommitted out of scope, another task's in-scope file, `.orchestrate`, bad sha.
- `gate`: ask→deny during a run, unchanged outside; planned exact and prefix match; compound command; malformed section.
- `preflight`: each mode; missing log.
- **Regression corpus** `claude/jev/tests/fixtures/scope_shell_corpus.jsonl`: about 200 real executor commands from 2026-10-13..15, paths rewritten to a fixture worktree, code bodies and messages trimmed, run through `redact.py` and checked by hand (its own plan task). Each line has the expected B outcome; the test asserts 0 asks.
- Three-edition parity for every changed or new module (existing parity checks extended).

## 10. Out of scope

Automatic revert; sandboxing interpreter code; changing `risky()`; per-command post-run checks; asking the orchestrator's own Claude-side shell writes (unchanged since 48b2336).

## 11. Rollout

Minor release. After merge, upgrade the plugin cache in both accounts (`claude plugin marketplace update dryas-workflow`, `claude plugin update dryas@dryas-workflow`, `install/install.sh --yes --claude-dir <dir>`) and restart sessions. Check the next run's report: prompts should be 0.
