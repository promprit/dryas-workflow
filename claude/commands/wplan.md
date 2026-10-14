---
description: Write an implementation plan in the Dryas plan format
argument-hint: <what to plan>
allowed-tools: Skill(dryas:plan), Read, Glob, Grep, Write
---
Use the dryas:plan skill to write the plan for: $ARGUMENTS. Save it under the project's docs/plans/ (or Dev/docs/plans/ for workspace-level work). When the plan is done, do not offer subagent-driven-development or executing-plans (they are disabled here); hand off to `/orchestrate` with the plan path.
