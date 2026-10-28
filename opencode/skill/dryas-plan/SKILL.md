---
name: dryas-plan
description: "Use when an approved design or spec needs an implementation plan, before touching code. Writes a plan of self-contained `## Task N:` sections (Goal, Scope, Done, Failing test first) that /orchestrate runs task by task. Used by /wplan."
---
<!-- dryas-managed -->

# Plan

## Overview

Write a complete implementation plan assuming the engineer has zero context for this codebase and questionable taste. Document everything they need: which files each task touches, the code, the tests, docs to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume a skilled developer who knows almost nothing about the toolset or the problem domain, and not much about good test design.

**Announce at start:** "I'm using the plan skill to write the implementation plan."

**Dryas binding:** each executor receives only its own `## Task N:` section (cut by planfile.py), plus the plan's Global Constraints, which `/orchestrate` passes with every dispatch. Write each section so it stands alone: Scope, Done and steps name every path and command it needs.

**Context:** the plan is written in the main checkout; at execution time `/orchestrate` creates the isolated worktree (the `dryas-worktree` skill).

**Save plans to:** see "Hand-off". User preferences for the plan location override the default.

## Scope check

If the spec covers several independent subsystems, it should have been split into sub-project specs during brainstorming. If it was not, suggest separate plans, one per subsystem. Each plan produces working, testable software on its own.

## File structure

Before defining tasks, map which files are created or modified and what each is responsible for. This is where decomposition decisions get locked in. When drawing the file map, read `<dryas-root>/../skill/dryas-plan/reference.md` § File structure guidance (one responsibility per file, focused files, files that change together live together, follow established patterns).

The map is done when every file a task touches is listed with its responsibility. This structure informs the task decomposition. Each task produces self-contained changes that make sense on their own.

## Task right-sizing

A task is the smallest unit that carries its own test cycle and is worth a fresh reviewer's gate. Fold setup, configuration, scaffolding and documentation steps into the task whose deliverable needs them; split only where a reviewer could meaningfully reject one task while approving its neighbor. Each task ends with an independently testable deliverable.

## Bite-sized steps

Each step is one action (2-5 minutes):
- "Write the failing test": a step.
- "Run it to make sure it fails": a step.
- "Implement the minimal code to make the test pass": a step.
- "Run the tests and make sure they pass": a step.
- "Commit": a step.

## Plan header

Every plan MUST start with this header:

```markdown
# <Feature> — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract; Interfaces and Steps follow. Steps use checkbox (`- [ ]`) syntax.

**Goal:** … **Architecture:** … **Tech Stack:** … **Spec:** <path to the approved spec>
```

Goal is one sentence on what this builds; Architecture is 2-3 sentences on the approach; Tech Stack names the key technologies and libraries; Spec is the path of the spec this plan implements (the plan argues from the spec, so the spec travels with it; executors read both). Then come "Global constraints" and "Review focus", then a `---` line and the tasks.

## Global constraints

A `## Global Constraints` section: the spec's project-wide requirements (version floors, dependency limits, naming and copy rules, platform requirements), one line each, with exact values copied verbatim from the spec. Every task's requirements implicitly include this section. When the spec's `## Lens` block has `Panel: design` or `Panel: design+product`, add the line `- Design checked by dryas-lens (Panel: <value>); UI tasks follow the lens page's changes: <link or path>` to Global Constraints.

## Review focus

A `## Review Focus` section: the five input classes or failure modes the spec implies but no task's tests exercise that are most likely to bite a person using this software, one line each, naming the input or condition and the behavior a reasonable person would expect, most likely first. The spec is a vision document: it says what the software must do, not everything it will meet, and its silence on an input is not permission for that input to break the program. Write the list here, once, with the spec in front of you. Then, for each line, add the test that pins it to the task that owns the code, in that task's own step style.

## Risky actions

If a task must run a command the gate would judge risky (deleting generated folders, resetting a test database, a force push the design calls for), list it in a `## Risky actions` section after Review Focus, one bullet each: - `<exact command, or a prefix ending in *>` — <one plain sentence: what it does, what could be lost, why the plan needs it>. Write the sentence for someone who does not code. Approving the plan approves these, so the run never stops to ask. No such command: leave the section out.

## Task format

Each task begins exactly as `.orchestrate/PLAN.md` expects; this command cuts it out for the executor:

````markdown
## Task N: <title>

Goal: <one sentence>
Scope:
- <glob relative to the worktree root>
Done:
- <verifiable criterion, with the test command>
Failing test first: <test file :: test name>   (or `none (review)` / `none (cleanup)`)

**Interfaces:**
- Consumes: <exact names and types from earlier tasks>
- Produces: <exact names and types later tasks rely on>

- [ ] **Step 1: Write the failing test.** <code>
- [ ] **Step 2: Run it to see it fail.** Run: <command>. Expected: <failure>
- [ ] **Step 3: Implement.** <code>
- [ ] **Step 4: Run the tests.** Run: <command>. Expected: PASS
- [ ] **Step 5: Commit** (explicit paths, conventional message) when the dispatch prompt allows it; otherwise report and the orchestrator commits.
````

A task that depends on a REA finding carries that finding's evidence in its own section; executors do not call REA.

When filling in Scope, Interfaces or the steps, read `<dryas-root>/../skill/dryas-plan/reference.md` § Task fields (exact paths, Consumes and Produces, what each step shows, non-overlapping Scope for parallel tasks).

## No placeholders

Every step contains the actual content the engineer needs: real code, exact commands, expected output. When scanning for placeholders, read `<dryas-root>/../skill/dryas-plan/reference.md` § Placeholder patterns; the plan is done when none of them appears.

## Self-review

After writing the complete plan, look at the spec with fresh eyes and check the plan against it. This is a checklist you run yourself:

1. **Spec coverage:** skim each section and requirement of the spec. Can you point to a task that implements it? List any gaps.
2. **Placeholder scan:** search the plan for the patterns in "No placeholders". Fix them.
3. **Type consistency:** do the types, signatures and property names in later tasks match those defined earlier? `clearLayers()` in Task 3 but `clearFullLayers()` in Task 7 is a bug.
4. **Review focus:** for each input class or failure mode the spec implies, is there a task whose tests exercise it? The five uncovered ones most likely to bite a person go in Review Focus, and each line there gets its test added to the owning task. An empty section means you checked and found none, not that you skipped the check.
5. **Risky actions:** every risky command a task's steps run is listed, each with its plain sentence.

Fix issues inline; no need to re-review, just fix and move on. A spec requirement with no task gets a task. The review is done when the five checks find nothing left to fix.

Also review the plan with `<dryas-root>/../skill/dryas-plan/plan-reviewer-prompt.md` when it has more than five tasks.

## Hand-off

Save the plan as `docs/plans/YYYY-MM-DD-<topic>.md`, commit it, link it, and ask the user to review it. The execution method in Dryas is always `/orchestrate <plan path>`: never offer another executor. Wait for the user's review before `/orchestrate`.

Ask: "Plan complete and saved to `docs/plans/<filename>.md`. Please review the plan. Does it capture what you want?" `/orchestrate` gives each task a fresh executor and a review gate before the next one starts, then a whole-branch review at the end; there is no in-session alternative to choose.
