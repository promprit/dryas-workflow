# Metrics logging and /tune calibration fixes

Date: 2026-10-06. Status: approved in conversation, pending written-spec review.

## Goal

Make the planned KPIs in `docs/metrics.md` live, and fix two calibration defects in `/tune`, so the operating model's Metrics dimension is backed by logs rather than by-hand checks.

In scope (project 1 of 2):

1. Log the planned metrics: `scope`, `dispatch`, `review` and `merge` records, reported by `/tune`.
2. Drop no-op `/tune` proposals (new value equals old value).
3. Canonical judge question names, so calibration groups calls correctly.
4. Filter the Sonnet→Opus count on `from_model == "sonnet"` (same defect as the Fable fix in `6555fb8`).

Out of scope: compound-command gating in `gate.py` (project 2, own spec and `/interrogate`); time windows for `/tune` (it reads all-time logs).

## Records

All records go through `jevlog.append(name, record)`, which adds `ts` (and `session_id` / `cwd` when set), writes one line with a single `O_APPEND` write, and never raises.

| Log file | Fields | Written by | When |
| --- | --- | --- | --- |
| `scope` | `task` (list of active task ids from `.orchestrate/active.json`), `path`, `decision` = `"deny"` | `claude/jev/scope_lock.py` | Every edit the lock denies, after the deny decision is made |
| `dispatch` | `task`, `tier` (`sonnet` / `opus` / `fable`), `role` (`coder` / `tester` / `reviewer` / `docs`), `attempt` (int ≥ 1) | MCP tool `log_dispatch` | Orchestrate §5 and §7, every executor dispatch including re-dispatches |
| `review` | `task` (branch name), `critical`, `important`, `minor` (ints ≥ 0), `round` (int ≥ 1) | MCP tool `log_review` | `/wreview`, once per review round |
| `merge` | `task` (branch name), `branch`, `tasks_merged` (int ≥ 0), `cost_usd` (number, optional) | MCP tool `log_merge` | Orchestrate §8, after the local merge |

Rules:

- `scope` logging must not change the lock's decision. It runs after the deny is chosen; any logging failure is swallowed by `jevlog`. Allowed edits write nothing.
- The three MCP tools follow `log_escalation`: declared in `tools/list` with an `inputSchema`, required fields checked, strings and ints coerced, and a call with a missing or invalid required field returns a tool error and writes nothing.
- `task` stays free text, as in `escalations`. No run id.
- `cost_usd` is optional because no component can read Claude-side cost automatically. The orchestrator fills it from `/cost` or the session cost notice when it has one.
- FlowObserve needs no change: its parser reads any `*.jsonl` with a `ts` and classifies unknown files as kind `other`.

## /tune report

`build()` gains these keys; `render()` prints each line with its healthy range from `metrics.md`.

| Report line | Computation | KPI |
| --- | --- | --- |
| Tasks dispatched | distinct `task` in `dispatch` where `attempt == 1` | denominator |
| Scope-lock denials per task (healthy 0–1) | count of `scope` records ÷ tasks dispatched | GOV-M4 |
| Sonnet→Opus climb rate (healthy under 20%) | `escalations` with `from_model == "sonnet"` and `to_model == "opus"` ÷ tasks dispatched | ESC-M1 |
| Median review rounds per branch (healthy ≤ 1) | max `round` per `task` in `review`, then the median | REV-M1 |
| Merges without a review (should be 0) | `merge` records whose `task` has no `review` record | L1 check |
| Cost per merged task | Σ `cost_usd` ÷ Σ `tasks_merged` over merges that have `cost_usd`; plus "N of M merges had no cost" | EXE-M3 |

- Any ratio with a zero denominator prints `n/a`.
- Malformed records (wrong types, missing fields) are skipped, as the existing parsers do.
- The existing "Escalations sonnet->opus" line uses the `from_model == "sonnet"` filter.
- No new automatic proposals: these KPIs are judged by a human.

## No-op proposals

`proposals()` drops any proposal whose `new` equals `old`.

## Canonical question names

- Skill text (orchestrate §3 and §6, Claude and Codex): when one `jev_judge` call covers several tasks, each question is named `<question>.<task>`, e.g. `needs_opus.t3`.
- `tune.canonical(name)`:
  1. Take the part before the first `.`.
  2. If it is one of the canonical names (`executor`, `specific`, `failing_test_exists`, `needs_opus`, `done`, `risk`, `safe_to_commit`, `needs_interrogate`), return it.
  3. Otherwise strip a task affix (`t<N>_` prefix, `_t<N>` / `_<N>` / `<N>` suffix, `_any` / `_all` / `_kind` suffix) and map the near-miss `failing_tests_exist` and `failing_test` to `failing_test_exists`; return the result if it is canonical.
  4. Otherwise return the name unchanged. Ambiguous names (`opus4`, `t1_opus`, `other_needs_opus`) are not guessed.
- `build()` groups `mcp` answers and `overrides` by `canonical()`.

## Skill and command text

Claude (`claude/skills/orchestrate/SKILL.md`, `claude/commands/wreview.md`) and Codex (`codex/skills/orchestrate/SKILL.md`, `codex/skills/wreview/SKILL.md`), kept in step:

- Orchestrate §3/§6: the `<question>.<task>` naming rule.
- Orchestrate §5 and §7: call `mcp__jev__log_dispatch` right after each dispatch.
- Orchestrate §8: call `mcp__jev__log_merge` after the local merge.
- `/wreview`: call `mcp__jev__log_review` once per review round with the counts by severity.

## Documentation

- `docs/metrics.md`: GOV-M4, ESC-M1, REV-M1 become live; EXE-M3 becomes partial (cost entered by hand); "Planned logging" becomes "Logging records" and says which component writes each.
- `docs/adoption-guide.md`: L1's "every merged change had a review" is checked by `/tune`; design approval stays a by-hand check. L2 and L3 lose their "by hand until logged" notes.
- `docs/roadmap.md`: tick "Log the planned metrics"; Metrics status becomes Covered with the EXE-M3 caveat.
- `docs/operating-model.md`: no change; it states no status (status lives in the roadmap).

## Testing

TDD in `claude/jev/tests` and `install/tests`:

- `test_scope_lock.py`: a denied edit writes one `scope` record with the active task ids and path; an allowed edit writes none; a log directory that cannot be written still denies.
- `test_jev_mcp.py`: `log_dispatch`, `log_review`, `log_merge` appear in `tools/list`, write valid records, and reject calls missing a required field without writing.
- `test_tune.py`: each new report key on sample logs; `n/a` on empty logs; no-op proposal dropped; `canonical()` on every legacy shape listed above; Sonnet→Opus count ignores records not from Sonnet.
- `install/tests`: existing shipped-file and docs tests pass; a test asserts both editions' orchestrate skill texts mention `log_dispatch` and `log_merge`, and both `wreview` texts mention `log_review`.

Full suite: `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests`.

## Task split for /orchestrate

| Task | Scope | Depends on |
| --- | --- | --- |
| 1. Scope-lock logging | `claude/jev/scope_lock.py`, `claude/jev/tests/test_scope_lock.py` | none |
| 2. MCP logging tools | `claude/jev/jev_mcp.py`, `claude/jev/tests/test_jev_mcp.py` | none |
| 3. /tune report, canonical names, filters | `claude/jev/tune.py`, `claude/jev/tests/test_tune.py` | none |
| 4. Skill and command text | orchestrate and wreview texts for both editions, one new install test | 2 |
| 5. Docs | `docs/metrics.md`, `docs/adoption-guide.md`, `docs/roadmap.md` | 1–3 |

Tasks 1–3 run in parallel; their scopes do not overlap.
