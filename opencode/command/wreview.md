---
description: "Three-stage review (spec compliance, code quality, over-engineering) of the current branch or worktree diff. Use for /wreview before any merge."
---
<!-- dryas-managed -->
Review the diff from the given base ref (default: the merge-base with the default branch) to HEAD.

1. **Spec compliance.** Compare against `.orchestrate/PLAN.md` or the named plan or spec. List every requirement that is missing, partial or wrong.
2. **Code quality.** Correctness bugs first, then error handling, tests and readability. Check each finding against the code before reporting it.
3. **Over-engineering.** Flag speculative abstraction, an unused option or parameter, a wrapper around the stdlib that adds nothing, a new dependency where the stdlib would do, and code that reusing existing repo code would have avoided; name the minimum-code ladder rung each skipped.

Run the three stages as three reviewers in parallel (sub-agents when available), and report each stage's findings separately.

Report findings ranked by severity with file:line. Change nothing unless asked. Follow `dryas-review-request`; handle findings with `dryas-review-receive`.

After each review round, call `jev_log_review` with task (the branch name), round (1 for the first review of this branch, +1 for each re-review) and the counts of critical, important and minor findings.

Arguments: $ARGUMENTS
