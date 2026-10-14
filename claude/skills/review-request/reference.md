# Review request reference

Read the section the pointer in `SKILL.md` names; nothing here is needed on every turn.

## Example

```
[Just completed Task 2: Add verification function]

You: Requesting a review before proceeding.

BASE_SHA=$(git log --oneline | grep "Task 1" | head -1 | awk '{print $1}')
HEAD_SHA=$(git rev-parse HEAD)

[Dispatch two reviewers in parallel]
  STAGE: 1 | 2
  DESCRIPTION: Added verifyIndex() and repairIndex() with 4 issue types
  PLAN_OR_REQUIREMENTS: Task 2 of .orchestrate/PLAN.md
  BASE_SHA: a7981ec
  HEAD_SHA: 3df7661

[Stage 1 reviewer returns]:
  Stage 1: all Task 2 requirements present
  Assessment: Ready to proceed

[Stage 2 reviewer returns]:
  Strengths: Clean architecture, real tests
  Issues:
    Important: Missing progress indicators (indexer.ts:130)
    Minor: Magic number (100) for reporting interval (indexer.ts:88)
  Assessment: Ready to proceed with fixes

You: [Show both reports as returned, fix progress indicators]
[Continue to Task 3]
```
