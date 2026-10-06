# Compound commands in the Jev gate

Date: 2026-10-06. Status: approved in conversation, pending written-spec review. **Contested: yes** (security gate; `/interrogate` is mandatory).

## Goal

Stop sending compound Bash commands to the judge when every part is already allowlisted and the parts are joined only by safe syntax, so the judged share (GOV-M1) falls from about 72% toward 35–45% without letting any command skip the judge that would be judged today for a reason other than its joining syntax.

Evidence (gate log, all time): 6,129 judged of 8,480 tool calls. Bash 5,387; Edit 411; Write 331. Of judged Bash, 4,258 start with an allowlisted head; `cd` alone is 2,395, nearly all `cd X && …`. Full commands are not logged, so the saving is estimated, not measured. Edit and Write stay judged (out of scope).

## Unchanged rules

- `allowlisted(cmd, allowlist)` is not modified. Every part of a compound command must pass it on its own, with all existing checks (operator regex, `shlex` parsing, dangerous-flag prefixes `--output`, `--ext-diff`, `--textconv`, `--exec`, `-c`).
- Nothing is added to the allowlist.
- A skipped command gets no gate decision: normal permissions apply (governance rule 5, "gates never auto-allow", still holds).

## Splitter

`split_compound(cmd: str) -> Optional[List[str]]` in `claude/jev/gate.py`. Returns the parts, or `None` meaning "send to the judge". It scans character by character, tracking single and double quotes.

| Situation | Result |
| --- | --- |
| `&&`, `\|\|`, `;`, `\|` outside quotes | ends the current part |
| standalone word `2>&1`, `>/dev/null` or `2>/dev/null` outside quotes | removed from the part |
| any of `; & \| < > ( )`, backtick or `$(` inside quotes | `None` |
| any other `&`, `<`, `>`, `(`, `)`, backtick or `$(` outside quotes (includes `&>`, `>|`, `\|&`, `<(`, heredoc `<<`, trailing `&`, redirect to a file) | `None` |
| a backslash anywhere | `None` |
| newline or carriage return anywhere | `None` |
| unclosed quote at the end | `None` |
| an empty part (`ls &&`, `; ls`, `ls;;pwd`) | `None` |
| more than 8 parts | `None` |

"Standalone word" means delimited by start/end of the part or by spaces or tabs, outside quotes. Parts are returned stripped of surrounding whitespace.

`allowlisted_compound(cmd: str, allowlist: List[str]) -> Tuple[bool, int]` returns `(True, n)` only when `split_compound` returns parts and every part passes `allowlisted()`; otherwise `(False, 0)`.

`run()` uses `allowlisted_compound` for Bash when the threshold `gate.compound` is true, and plain `allowlisted` when it is false.

## Kill switch

New threshold `gate.compound`, boolean, default `true`, added to `DEFAULTS["gate"]` in `claude/jev/thresholds.py`. The existing type check makes `/tune apply gate.compound <value>` accept only a boolean. With `false`, gate behavior is exactly as before this change.

## Logging

The `gate` record for a skip gains `"parts": N` when `N > 1`. No other record changes. `/tune` and FlowObserve ignore unknown fields.

## Examples

| Command | Outcome |
| --- | --- |
| `cd /x && git status 2>&1 \| tail -3` | skipped (parts `cd /x`, `git status`, `tail -3`) |
| `cd x&&git status` | skipped |
| `git status 2>&1` | skipped (single command with an allowed redirect; judged today) |
| `ls \| sh` | judged (`sh` not allowlisted) |
| `cd /x && git push` | judged (`git push` not allowlisted) |
| `grep -r x . > out.txt` | judged (redirect to a file) |
| `git log --format="%h\|%s"` | judged (operator inside quotes) |
| `cat a; rm -rf b` | judged (`rm` not allowlisted) |
| `ls &` | judged (lone `&`) |
| `cat <(ls)` | judged |
| `ls \; pwd` | judged (backslash) |

## Codex

No change: the Codex hook runs the same `gate.py`.

## Testing

New file `claude/jev/tests/test_gate_compound.py`, test-first:

- A table of about 35 cases with expected `skip` or `judge`, covering every row of the splitter table and these adversarial inputs: `<(…)`, `>(…)`, `>|`, `&>`, `|&`, trailing `&`, tabs as separators, operators with no spaces, full-width `；`, `$'…'` quoting, nested quotes, `;;`, a 9-part chain, `2>&1` inside quotes, `>/dev/nullx`, `2>&1x`, `>& /dev/null`, empty command, whitespace-only command.
- Property: for every case that is skipped, each returned part passes `allowlisted()` alone and contains none of `; & | < > ( )`, backtick, `$(`, backslash or newline.
- Kill switch: with `gate.compound` false in a temp thresholds file, every compound case in the table is judged and single commands behave as before.
- Logging: a skipped compound command writes a `gate` record with `decision: "skipped"` and `parts` equal to the part count.
- Existing `claude/jev/tests/test_gate.py` and `test_thresholds.py` pass unchanged.

Full suite: `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests`.

## Review

The orchestrator runs `/interrogate` (two models, adversarial) before `/wreview`. Attack question: can any input make `split_compound` return parts such that bash would execute something other than those parts joined by `&&`, `||`, `;` or `|`, or make a part pass `allowlisted()` that bash would run differently?

## Documentation

- `docs/governance.md`: in the gate paragraph, one sentence: compound commands skip the judge only when every part is allowlisted and they are joined by `&&`, `||`, `;` or `|` (plus `2>&1`, `>/dev/null`, `2>/dev/null`); `gate.compound=false` turns this off.
- `docs/workflow.md`: the thresholds table's gate row gains `compound true`.
- `docs/metrics.md`: GOV-M1 "If out of range" gains: "If a compound-command skip looks wrong, set `gate.compound` to false and report the command."

## Success

After install, a week of `/tune` shows the judged share falling toward 35–45%. The test table, not live logs, shows that commands which must stay judged still are.

## Out of scope

Edit and Write judging; adding `sed`, `echo`, `for` or other heads; heredocs; any change to `allowlisted()`.

## Amendments after /interrogate (approved 2026-10-06)

/interrogate (Sonnet and Opus reviewers) found: shell expansion (`{a,b}`, `${x:-...}`, `${x:=...}`, `$'...'`) turns harmless words into banned flags like `--output`, in single commands (pre-existing on main) and across compound parts (new); a leading `cd` changes the directory later parts run in, so code-running heads (pytest, npm/pnpm test, swift test, git with repo config) could run in an outside directory; `str.strip()` removed characters bash keeps; `#` comments and `${...}` were not modelled. Amendments:

- Character allowlist for single and compound commands: a part (or a single command) skips the judge only if every character is in the plain set (ASCII letters, digits, space, tab, quotes and `. _ / = : @ % + , -`). This tightens the old single-command check; the deviation from "`allowlisted()` unchanged" is approved by the user, and the `allowlisted()` code itself is still unchanged.
- Parts are stripped with `strip(" \t")` only.
- Every `cd` target in a compound must resolve inside the session cwd, tracked across successive `cd` parts; one argument, not starting with `-`.
- `ls # x; pwd` is now judged.
