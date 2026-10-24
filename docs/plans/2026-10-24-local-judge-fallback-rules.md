# Local judge fallback rules — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract. Not approved for execution yet: brainstorm the rule shapes first (dryas:brainstorm).

**Goal:** The local judge stops allowing the commands Jev asked about or denied in the 2026-10-24 `/tune` disagreements (destructive `rm`, `chmod -R`, `osascript` deletes, `ditto` into `~/Library`, `zsh -c` wrappers, moving shell configs). Today `local_judge.gate_answers` falls back to `prescreen:risky` with p_safe 0.8 and no decision, which allows them.
**Why it matters:** projects on the local judge only (`.dryas-judge`, e.g. VOID) get no Jev check, so these commands run unasked there.
**Evidence:** 7 corpus rows added 2026-10-24 (`reference/judge-corpus/commands.jsonl`, their notes contain "tune 2026-10-24"); baseline `missed_dangerous` raised 14 -> 21 for those rows only.

## Global Constraints

- Python 3.9 stdlib only in `claude/jev/`.
- No release worse than the last: the new rules must not add asks on the corpus `safe` rows (`needless_asks` stays 0), and a replay of the local-judge projects' gate logs must show no more asks per task than 2.5.0 (`tools/compare_v1.py`). Asks only fire in local-judge projects; Jev-judged sessions are unchanged.

## Task 1: destructive fallback rules in the local judge

**Goal:** `local_judge.destructive` returns a rule name (decision `ask`) for the 7 new corpus rows.
**Scope:** `claude/jev/local_judge.py`, `claude/jev/tests/test_local_judge*.py`, `reference/judge-corpus/SCORECARD.md`, `reference/judge-corpus/baseline.json`.
**Done:** `python3 tools/judge_score.py --check` passes with `missed_dangerous` back to 14 or lower and `needless_asks` 0; baseline rewritten with `--write --baseline`; full `claude/jev/tests` green.
**Failing test first:** a test asserting `gate_answers("Bash", "rm -r ~/Projects/app")["decision"] == "ask"` (and one per new row) fails on main.
