---
name: review-request
description: Use when a task or branch is done and before any merge. Requests a two-stage review of the diff from a fresh reviewer, spec compliance first and code quality second, with findings ranked by severity.
---

# Review request

Have a fresh reviewer check the work before problems cascade. The reviewer gets precisely crafted context for its evaluation, never your session's history: that keeps it on the work product, not your thought process.

**Core principle:** review early, review often.

## When

**Mandatory:**
- After each task when a plan is executed by sub-agents
- After completing a major feature
- Before any merge to the base branch (`/orchestrate` runs `/wreview` on the worktree diff before `/commit` and the merge)

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
2. **Dispatch the reviewer** with the prompt in `${CLAUDE_PLUGIN_ROOT}/skills/review-request/reviewer-prompt.md`, its placeholders filled:
   - `[DESCRIPTION]`: a brief summary of what you built
   - `[PLAN_OR_REQUIREMENTS]`: what it should do (`.orchestrate/PLAN.md`, the named plan or spec, the task text, or the requirements)
   - `[BASE_SHA]`: the starting commit
   - `[HEAD_SHA]`: the ending commit
<!-- claude -->
   Dispatch the reviewer with the Agent tool (`subagent_type: "dryas:executor"`, role reviewer) and give it `${CLAUDE_PLUGIN_ROOT}/skills/review-request/reviewer-prompt.md` filled in.
<!-- /claude -->
<!-- codex -->
   On Codex: use a Codex sub-agent for the reviewer when available; otherwise review the diff yourself in a fresh pass, following the reviewer prompt. Change nothing unless asked.
<!-- /codex -->
3. **Act on the findings** with the `dryas:review-receive` skill:
   - Fix critical issues immediately
   - Fix important issues before proceeding
   - Note minor issues for later
   - Push back if the reviewer is wrong (with reasoning)

Report findings ranked by severity (critical, important, minor) with file:line. The reviewer changes nothing unless asked. After each round `/wreview` logs the counts with `mcp__plugin_dryas_jev__log_review`.

## Two stages

The reviewer works in two stages, in order, and reports both:

1. **Spec compliance.** Check the diff against `.orchestrate/PLAN.md` or the named plan or spec. List every requirement that is missing, partial or wrong; flag deviations so the implementer can confirm whether they were intentional, and say so when the plan itself is at fault. Behavior the spec is silent on is judged by what a reasonable user would expect.
2. **Code quality.** Correctness bugs first, then error handling, then tests (real behavior, not mocks; edge cases), then readability. Architecture, security and production readiness belong here too.

Check each finding against the code before reporting it: no finding on code the reviewer did not read.

## Example

```
[Just completed Task 2: Add verification function]

You: Requesting a review before proceeding.

BASE_SHA=$(git log --oneline | grep "Task 1" | head -1 | awk '{print $1}')
HEAD_SHA=$(git rev-parse HEAD)

[Dispatch the reviewer]
  DESCRIPTION: Added verifyIndex() and repairIndex() with 4 issue types
  PLAN_OR_REQUIREMENTS: Task 2 of .orchestrate/PLAN.md
  BASE_SHA: a7981ec
  HEAD_SHA: 3df7661

[Reviewer returns]:
  Strengths: Clean architecture, real tests
  Stage 1: all Task 2 requirements present
  Issues:
    Important: Missing progress indicators (indexer.ts:130)
    Minor: Magic number (100) for reporting interval (indexer.ts:88)
  Assessment: Ready to proceed

You: [Fix progress indicators]
[Continue to Task 3]
```

## Rationalizations

| Excuse | Reality |
|---|---|
| "I'll just review the diff myself instead of dispatching a reviewer" | You are the coordinator: reviewing the diff inline burns the context window you need to keep driving the work. Dispatch a reviewer: the diff and the evaluation live in its context, and only the findings come back to you. (Codex without sub-agents is the one exception, above.) |
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

The template: `${CLAUDE_PLUGIN_ROOT}/skills/review-request/reviewer-prompt.md`.
