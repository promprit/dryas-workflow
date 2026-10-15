---
name: dryas-review-request
description: "Use when a task or branch is done and before any merge. Requests a three-stage review of the diff from three fresh reviewers in parallel, spec compliance, code quality and over-engineering, with findings ranked by severity."
---
<!-- dryas-managed -->

# Review request

Have fresh reviewers check the work before problems cascade. Each reviewer gets precisely crafted context for its evaluation, never your session's history: that keeps it on the work product, not your thought process.

**Core principle:** review early, review often.

## When

**Mandatory:**
- After each task when a plan is executed by sub-agents
- After completing a major feature
- Before any merge to the base branch (inside `/orchestrate`, the finish step reviews the worktree diff before the commit and the merge)

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
2. **Dispatch the three reviewers** (see Three stages) with the prompt in `<dryas-root>/../skill/dryas-review-request/reviewer-prompt.md`, its placeholders filled:
   - `[STAGE]`: `1` (spec compliance), `2` (code quality) or `3` (over-engineering), one per reviewer
   - `[DESCRIPTION]`: a brief summary of what you built
   - `[PLAN_OR_REQUIREMENTS]`: what it should do (`.orchestrate/PLAN.md`, the named plan or spec, the task text, or the requirements)
   - `[BASE_SHA]`: the starting commit
   - `[HEAD_SHA]`: the ending commit
   Done when three reports are back, one per stage.
3. **Act on the findings** with the `dryas-review-receive` skill:
   - Fix critical issues immediately
   - Fix important issues before proceeding
   - Note minor issues for later
   - Push back if the reviewer is wrong (with reasoning)

Report findings ranked by severity (critical, important, minor) with file:line. The reviewers change nothing unless asked. In Dryas: inside `/orchestrate`, the finish step runs this skill (then review-receive, then verify) and calls `jev_log_review` after each round; outside it, `/wreview` runs this skill and logs the round.

## Three stages

Run the three stages as three reviewers in parallel, each given the diff and its own brief:

1. **Spec compliance** against `.orchestrate/PLAN.md` or the named plan or spec. List every requirement that is missing, partial or wrong; flag deviations so the implementer can confirm whether they were intentional, and say so when the plan itself is at fault. Behavior the spec is silent on is judged by what a reasonable user would expect.
2. **Code quality.** Correctness bugs first, then error handling, then tests (real behavior, not mocks; edge cases), then readability. Architecture, security and production readiness belong here too.
3. **Over-engineering** (see Stage 3).

Present the three reports separately, as returned: do not merge or re-rank them. The reviewer enforces the standards: the implementer worked under context pressure, so the reviewer reports what is missing instead of assuming it was intended. Each finding is checked against the code before it is reported: no finding on code the reviewer did not read.

## Stage 3: over-engineering

The reviewer flags speculative abstraction (layers, hooks or generality no current caller needs), an unused option or parameter, a wrapper around the stdlib that adds nothing, a new dependency where the stdlib would do, and code that a reuse of existing repo code would have avoided. Each finding uses the same format and severities as stages 1 and 2 and cites the rung of the minimum-code ladder (`dryas-executor` rule 3) it skipped: YAGNI, reuse, stdlib, native feature, existing dependency, one-liner.

- Unrelated change: a hunk that does not trace to the task or plan step (refactor, rename, reformat, drive-by fix). Report it as an "unrelated change" finding, Important, naming the hunk.

For a worked round (SHAs, dispatch, reports, fixes), read `<dryas-root>/../skill/dryas-review-request/reference.md` § Example.

## Rationalizations

| Excuse | Reality |
|---|---|
| "I'll just review the diff myself instead of dispatching a reviewer" | You are the coordinator: reviewing the diff inline burns the context window you need to keep driving the work. Dispatch reviewers: the diff and the evaluation live in their context, and only the findings come back to you. (OpenCode without sub-agents is the one exception, above.) |
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

The template: `<dryas-root>/../skill/dryas-review-request/reviewer-prompt.md`.
