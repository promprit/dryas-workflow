---
description: Run the lens review (design panel or product panel) and write the lens page
argument-hint: [design|product]
allowed-tools: Skill(dryas:lens), Artifact, Read, Glob, Grep, Write, Bash(open:*)
disable-model-invocation: true
---
Use the dryas:lens skill for: $ARGUMENTS. "design" runs the design panel, "product" (or "3 lens") the product panel; nothing else picks the panel from context.
