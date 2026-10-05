---
name: wreview
description: Two-stage review (spec compliance, then code quality) of the current branch or worktree diff. Use for $wreview before any merge.
---

Review the diff from the given base ref (default: the merge-base with the default branch) to HEAD.

1. **Spec compliance.** Compare against `.orchestrate/PLAN.md` or the named plan or spec. List every requirement that is missing, partial or wrong.
2. **Code quality.** Correctness bugs first, then error handling, tests and readability. Check each finding against the code before reporting it.

Report findings ranked by severity with file:line. Change nothing unless asked. If Superpowers' requesting-code-review skill is installed, follow it.
