---
description: Two-stage review (spec compliance, then code quality) of the current branch or worktree diff
argument-hint: [base-ref]
---
Use superpowers:requesting-code-review on the diff from the base ref "$ARGUMENTS" (if empty: the merge-base with the default branch) to HEAD. Stage 1: spec/plan compliance (PLAN.md or the named plan). Stage 2: code quality. Handle findings with superpowers:receiving-code-review. Report findings ranked by severity.
