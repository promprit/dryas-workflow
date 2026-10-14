---
name: review-request
description: Use when a task or branch is done and before any merge. Requests a two-stage review of the diff from two fresh reviewers in parallel, spec compliance and code quality, with findings ranked by severity.
---

# Review request

Have fresh reviewers check the work before problems cascade. Each reviewer gets precisely crafted context for its evaluation, never your session's history: that keeps it on the work product, not your thought process.

**Core principle:** review early, review often.

## When

**Mandatory:**
- After each task when a plan is executed by sub-agents
- After completing a major feature
- Before any merge to the base branch (`$dryas:orchestrate` runs `$dryas:wreview` on the worktree diff before `$dryas:commit` and the merge)

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing a complex bug

## How

1. **Get the range.** The base is the ref you were given, else the merge-base with the default branch (or `HEAD~1` for a single-commit task); the head is `HEAD`:
   ```bash
   BASE_SHA=$(git merge-base origin/main HEAD)   # or: git rev-parse HEAD~1
   HEAD_SHA=$(git rev-parse HEAD)
   ```
   Done when both SHAs resolve.
2. **Dispatch the two reviewers** (see Two stages) with the prompt in `<dryas-root>/skills/review-request/reviewer-prompt.md`, its placeholders filled:
   - `[STAGE]`: `1` (spec compliance) or `2` (code quality), one per reviewer
   - `[DESCRIPTION]`: a brief summary of what you built
   - `[PLAN_OR_REQUIREMENTS]`: what it should do (`.orchestrate/PLAN.md`, the named plan or spec, the task text, or the requirements)
   - `[BASE_SHA]`: the starting commit
   - `[HEAD_SHA]`: the ending commit
   On Codex: run the two reviewers as Codex sub-agents in parallel when available; otherwise review twice yourself, one fresh pass per stage, and still report them separately. Change nothing unless asked.
   Done when two reports are back, one per stage.
3. **Act on the findings** with the `$dryas:review-receive` skill:
   - Fix critical issues immediately
   - Fix important issues before proceeding
   - Note minor issues for later
   - Push back if the reviewer is wrong (with reasoning)

Report findings ranked by severity (critical, important, minor) with file:line. The reviewers change nothing unless asked. After each round `$dryas:wreview` logs the counts with `log_review`.

## Two stages

Run the two stages as two reviewers in parallel, each given the diff and its own brief:

1. **Spec compliance** against `.orchestrate/PLAN.md` or the named plan or spec. List every requirement that is missing, partial or wrong; flag deviations so the implementer can confirm whether they were intentional, and say so when the plan itself is at fault. Behavior the spec is silent on is judged by what a reasonable user would expect.
2. **Code quality.** Correctness bugs first, then error handling, then tests (real behavior, not mocks; edge cases), then readability. Architecture, security and production readiness belong here too.

Present the two reports separately, as returned: do not merge or re-rank them. The reviewer enforces the standards: the implementer worked under context pressure, so the reviewer reports what is missing instead of assuming it was intended. Each finding is checked against the code before it is reported: no finding on code the reviewer did not read.

For a worked round (SHAs, dispatch, reports, fixes), read `<dryas-root>/skills/review-request/reference.md` § Example.

## Rationalizations

| Excuse | Reality |
|---|---|
| "I'll just review the diff myself instead of dispatching a reviewer" | You are the coordinator: reviewing the diff inline burns the context window you need to keep driving the work. Dispatch reviewers: the diff and the evaluation live in their context, and only the findings come back to you. (Codex without sub-agents is the one exception, above.) |
| "The reviewer needs my whole session history to understand the change" | Hand it precisely crafted context, never your session's history. That keeps the reviewer on the work product, not your thought process. |

## Red flags

**Never:**
- Skip review because "it's simple"
- Ignore critical issues
- Proceed with unfixed important issues
- Argue with valid technical feedback

**If the reviewer is wrong:**
- Push back with technical reasoning
- Show code or tests that prove it works
- Request clarification

The template: `<dryas-root>/skills/review-request/reviewer-prompt.md`.
