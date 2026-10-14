# Upstream coverage: review-request

Rows follow the grammar in [../UPSTREAM.md](../UPSTREAM.md).

## review-request

Upstream: `requesting-code-review/`

| Upstream item | Where it lives |
|---|---|
| Requesting Code Review | review-request/SKILL.md § Review request |
| Requesting Code Review — dispatch a reviewer to catch issues before they cascade | review-request/SKILL.md § Review request |
| Requesting Code Review — crafted context, never your session's history | review-request/SKILL.md § Review request |
| Requesting Code Review — core principle: review early, review often | review-request/SKILL.md § Review request |
| When to Request Review | review-request/SKILL.md § When |
| When to Request Review — mandatory: after each task in sub-agent-driven development | review-request/SKILL.md § When |
| When to Request Review — mandatory: after completing a major feature | review-request/SKILL.md § When |
| When to Request Review — mandatory: before merge to main | review-request/SKILL.md § When; orchestrate: "Review the worktree diff with the `dryas:review-request` skill" |
| When to Request Review — optional: when stuck | review-request/SKILL.md § When |
| When to Request Review — optional: before refactoring | review-request/SKILL.md § When |
| When to Request Review — optional: after fixing a complex bug | review-request/SKILL.md § When |
| How to Request | review-request/SKILL.md § How |
| How to Request — 1. Get git SHAs (HEAD~1 or merge-base, HEAD) | review-request/SKILL.md § How |
| How to Request — 2. Dispatch code reviewer sub-agent with code-reviewer.md | review-request/SKILL.md § How; review-request/reviewer-prompt.md § Reviewer prompt |
| How to Request — 2. placeholders: description, plan or requirements, base SHA, head SHA | review-request/SKILL.md § How; review-request/reviewer-prompt.md § Reviewer prompt |
| How to Request — 2. Claude dispatch: executor agent, role reviewer (Dryas) | review-request/SKILL.md § How |
| How to Request — 2. Codex: sub-agent or a fresh pass yourself, change nothing unless asked (Dryas) | review-request/SKILL.md § How |
| How to Request — 3. Act on feedback | review-request/SKILL.md § How; review-receive/SKILL.md § Order of fixes |
| How to Request — 3. fix critical issues immediately | review-request/SKILL.md § How |
| How to Request — 3. fix important issues before proceeding | review-request/SKILL.md § How |
| How to Request — 3. note minor issues for later | review-request/SKILL.md § How |
| How to Request — 3. push back if the reviewer is wrong, with reasoning | review-request/SKILL.md § How; review-receive/SKILL.md § When to push back |
| How to Request — findings ranked by severity with file:line; log_review per round (Dryas) | review-request/SKILL.md § How |
| How to Request — two stages, spec compliance then code quality (Dryas) | review-request/SKILL.md § Two stages; review-request/reviewer-prompt.md § Stage 1: spec compliance; review-request/reviewer-prompt.md § Stage 2: code quality |
| How to Request — two reviewers in parallel, one per stage, each with its own brief (Dryas) | review-request/SKILL.md § Two stages; review-request/SKILL.md § How; review-request/reviewer-prompt.md § Reviewer prompt |
| How to Request — present the two reports separately; do not merge or re-rank (Dryas) | review-request/SKILL.md § Two stages |
| How to Request — the reviewer enforces the standards; reports what is missing, assumes nothing intended (Dryas) | review-request/SKILL.md § Two stages; review-request/reviewer-prompt.md § Reviewer prompt |
| Example | review-request/reference.md § Example; review-request/SKILL.md § Two stages |
| Example — after Task 2: SHAs, dispatch, reviewer returns, fix, continue | review-request/reference.md § Example |
| Common Rationalizations | review-request/SKILL.md § Rationalizations |
| Common Rationalizations — "I'll just review the diff myself instead of dispatching a reviewer" | review-request/SKILL.md § Rationalizations |
| Common Rationalizations — "The reviewer needs my whole session history" | review-request/SKILL.md § Rationalizations |
| Red Flags | review-request/SKILL.md § Red flags |
| Red Flags — never: skip review because "it's simple" | review-request/SKILL.md § Red flags |
| Red Flags — never: ignore critical issues | review-request/SKILL.md § Red flags |
| Red Flags — never: proceed with unfixed important issues | review-request/SKILL.md § Red flags |
| Red Flags — never: argue with valid technical feedback | review-request/SKILL.md § Red flags |
| Red Flags — reviewer wrong: push back with technical reasoning | review-request/SKILL.md § Red flags |
| Red Flags — reviewer wrong: show code or tests that prove it works | review-request/SKILL.md § Red flags |
| Red Flags — reviewer wrong: request clarification | review-request/SKILL.md § Red flags |
| Red Flags — see template at code-reviewer.md | review-request/SKILL.md § Red flags |
| code-reviewer.md | review-request/reviewer-prompt.md § Reviewer prompt |
| code-reviewer.md — use when dispatching; purpose | review-request/reviewer-prompt.md § Reviewer prompt |
| code-reviewer.md — role: senior code reviewer | review-request/reviewer-prompt.md § Reviewer prompt |
| code-reviewer.md — What Was Implemented | review-request/reviewer-prompt.md § What was implemented |
| code-reviewer.md — Requirements / Plan | review-request/reviewer-prompt.md § Requirements or plan |
| code-reviewer.md — Git Range to Review | review-request/reviewer-prompt.md § Git range to review |
| code-reviewer.md — The spec is a vision document | review-request/reviewer-prompt.md § The spec is a vision document |
| code-reviewer.md — Declined to judge | review-request/reviewer-prompt.md § Declined to judge |
| code-reviewer.md — Read-Only Review | review-request/reviewer-prompt.md § Read-only review |
| code-reviewer.md — You Do Not Dispatch Subagents | review-request/reviewer-prompt.md § You do not dispatch sub-agents |
| code-reviewer.md — What to Check: plan alignment | review-request/reviewer-prompt.md § Stage 1: spec compliance |
| code-reviewer.md — What to Check: code quality | review-request/reviewer-prompt.md § Stage 2: code quality |
| code-reviewer.md — What to Check: architecture | review-request/reviewer-prompt.md § Stage 2: code quality |
| code-reviewer.md — What to Check: testing | review-request/reviewer-prompt.md § Stage 2: code quality |
| code-reviewer.md — What to Check: production readiness | review-request/reviewer-prompt.md § Stage 2: code quality |
| code-reviewer.md — Calibration: actual severity; acknowledge strengths | review-request/reviewer-prompt.md § Calibration |
| code-reviewer.md — Calibration: flag plan deviations; say so when the plan is at fault | review-request/reviewer-prompt.md § Stage 1: spec compliance |
| code-reviewer.md — Output Format | review-request/reviewer-prompt.md § Output format |
| code-reviewer.md — Output Format: Strengths | review-request/reviewer-prompt.md § Strengths |
| code-reviewer.md — Output Format: Issues (Critical, Important, Minor) | review-request/reviewer-prompt.md § Issues |
| code-reviewer.md — Output Format: per issue file:line, what, why, how | review-request/reviewer-prompt.md § Output format |
| code-reviewer.md — Output Format: Recommendations | review-request/reviewer-prompt.md § Recommendations |
| code-reviewer.md — Output Format: Assessment (ready to merge, reasoning) | review-request/reviewer-prompt.md § Assessment |
| code-reviewer.md — Critical Rules: do | review-request/reviewer-prompt.md § Critical rules |
| code-reviewer.md — Critical Rules: don't | review-request/reviewer-prompt.md § Critical rules |
| code-reviewer.md — Placeholders | review-request/reviewer-prompt.md § Reviewer prompt |
| code-reviewer.md — Reviewer returns | review-request/reviewer-prompt.md § Reviewer prompt |
| code-reviewer.md — Example Output | review-request/reviewer-prompt.md § Example output |
