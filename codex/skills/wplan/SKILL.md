---
name: wplan
description: Write an implementation plan for an approved design, in the plan-file format that $dryas:orchestrate runs. Use for $dryas:wplan.
---

Use the `$dryas:plan` skill to write the plan for the approved design. The plan uses `## Task N:` sections with Goal, Scope (globs), Done and Failing test first, so `$dryas:orchestrate` can run it task by task. Save it under the project's `docs/plans/` (or `docs/superpowers/plans/` if the project uses that). When it is written, hand off to `$dryas:orchestrate` with the plan path.
