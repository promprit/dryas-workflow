---
description: Two-stage review (spec compliance, then code quality) of the current branch or worktree diff
argument-hint: [base-ref]
allowed-tools: Skill(dryas:review-request), Skill(dryas:review-receive), Read, Glob, Grep, Agent, Bash(git diff:*), Bash(git log:*), Bash(git merge-base:*), Bash(git rev-parse:*), mcp__plugin_dryas_jev__log_review
---
Use the dryas:review-request skill on the diff from the base ref "$ARGUMENTS" (if empty: the merge-base with the default branch) to HEAD. Stage 1: spec/plan compliance (PLAN.md or the named plan). Stage 2: code quality. Handle findings with the dryas:review-receive skill. The two stages run as two reviewers in parallel; report each stage's findings separately, ranked by severity within its own report. After each review round, call `mcp__plugin_dryas_jev__log_review` with task (the branch name), round (1 for the first review of this branch, +1 for each re-review) and the counts of critical, important and minor findings.
