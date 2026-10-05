---
name: wplan
description: Write an implementation plan for an approved design, in the plan-file format that $orchestrate runs. Use for $wplan.
---

Use Superpowers' writing-plans skill if it is installed. The plan uses `## Task N:` sections with Goal, Scope (globs), Done and Failing test first, so `$orchestrate` can run it task by task. Save it under the project's `docs/plans/` (or `docs/superpowers/plans/` if the project uses that). When it is written, hand off to `$orchestrate` with the plan path.
