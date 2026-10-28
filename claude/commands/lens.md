---
description: Run the lens review (design panel or product panel) and write the lens page
argument-hint: [design|product]
allowed-tools: Skill(dryas:lens), Skill(impeccable), Skill(impeccable:impeccable), Skill(ui-ux-pro-max), Skill(ui-ux-pro-max:ui-ux-pro-max), Skill(artifact-design), Artifact, Read, Glob, Grep, Write, Edit
disable-model-invocation: true
---
Use the dryas:lens skill for: $ARGUMENTS. "design" runs the design panel, "product" (or "3 lens") the product panel; nothing else picks the panel from context.
