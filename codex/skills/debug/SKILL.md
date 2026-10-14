---
name: debug
description: Use on any bug, test failure or unexpected behavior, before proposing a fix, and before $dryas:orchestrate climbs a task to a stronger tier. Root cause first (feedback loop, then four phases); no fix by guessing.
---

# Debug

ALWAYS find the root cause before attempting a fix. A symptom fix is a failure.

Violating the letter of this process is violating the spirit of debugging.

## Iron law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you have not completed Phase 1, you cannot propose a fix. Complete each phase before the next.

## When to use

Any technical issue: test failures, bugs in production, unexpected behavior, performance problems, build failures, integration issues.

**ESPECIALLY when:** under time pressure (emergencies make guessing tempting); "just one quick fix" seems obvious; you have already tried several fixes; a previous fix did not work; you do not fully understand the issue.

**Do not skip it when:** the issue seems simple (simple bugs have root causes too); you are in a hurry (rushing guarantees rework); a manager wants it fixed NOW (systematic is faster than thrashing).

In Dryas: `$dryas:orchestrate` runs this before every climb (fast → standard → strong → frontier) on the failing reports, read only. If the root cause is a plan defect (scope too narrow, Done vague or wrong, missing context), the fix is in that task's section of `.orchestrate/PLAN.md` and the task is re-dispatched on the same model; that is not a climb. Executors run Phase 1 before reporting a failure. When inside an executor (no user channel, no commits): put the ranked hypotheses and the confirmed one in your report instead of showing them to the user or writing a commit message; the orchestrator relays and commits.

## Feedback loop first

Before any hypothesis, build a loop that shows the bug: one command, fast (seconds), deterministic, failing on the bug. Write the command down; every later step re-runs it. Without such a loop, say what blocks it and stop there; no hypotheses yet.

Throughout: redact secrets (keys, tokens, passwords, connection strings) in any output you show; print `SET` or `UNSET`, never the value.

## Phase 1: Root cause

BEFORE attempting ANY fix:

1. **Read error messages carefully.** Do not skip past errors or warnings; they often contain the exact solution. Read stack traces completely. Note line numbers, file paths, error codes.
2. **Reproduce consistently.** The feedback loop is the reproduction: it triggers the bug every time with exact steps. Not reproducible: gather more data, do not guess.
3. **Check recent changes.** What changed that could cause this? The diff, recent commits, new dependencies, config changes, environment differences.
4. **Gather evidence in multi-component systems.** When the system has several components (CI → build → signing, API → service → database), instrument each boundary BEFORE proposing fixes: log what enters and exits each component, verify config propagation, check state at each layer; run once, find WHERE it breaks, then investigate that component. When instrumenting, read `<dryas-root>/skills/debug/reference.md` § Multi-layer evidence for the pattern and a worked example.
5. **Trace data flow.** When the error is deep in the call stack, use the backward tracing technique in `<dryas-root>/skills/debug/root-cause-tracing.md`. Quick version: where does the bad value originate? What called this with it? Keep tracing up to the source. Fix at the source, not at the symptom.

Tag every temporary debug log line with a unique prefix (for example `DBG-<topic>:`). Phase 1 ends when you can say WHAT fails and WHERE.

## Phase 2: Pattern analysis

Find the pattern before fixing:

1. **Find working examples.** Locate similar working code in the same codebase. What works that is like what is broken?
2. **Compare against references.** If you are implementing a pattern, read the reference implementation COMPLETELY. Do not skim; read every line. Understand the pattern fully before applying it.
3. **Identify differences.** What differs between working and broken? List every difference, however small. Do not assume "that can't matter".
4. **Understand dependencies.** What other components does this need? What settings, config, environment? What assumptions does it make?

Phase 2 ends on a written list of differences.

## Phase 3: Hypothesis and test

Scientific method:

1. **Rank your hypotheses.** Write 3-5 ranked, falsifiable hypotheses ("I think X is the root cause because Y"), each with the prediction that would confirm or kill it, and show them to the user before testing. Be specific, not vague.
2. **Test one at a time.** Test them in rank order with the loop. For each, make the SMALLEST possible change that tests it. One variable at a time. Do not fix several things at once.
3. **Verify before continuing.** The prediction held: Phase 4. It failed: cross that hypothesis off and test the next; when the list is used up, form NEW ones. Do NOT add more fixes on top.
4. **When you don't know.** Say "I don't understand X". Do not pretend to know. Ask for help. Research more.

Phase 3 ends on one confirmed hypothesis.

## Phase 4: Fix

Fix the root cause, not the symptom:

1. **Create a failing test case.** The simplest possible reproduction: an automated test if possible, a one-off test script if there is no framework. You MUST have it before fixing. Use the `$dryas:tdd` skill to write a proper failing test.
2. **Implement a single fix.** Address the root cause you identified. ONE change at a time. No "while I'm here" improvements, no bundled refactoring.
3. **Verify the fix.** Does the test pass now? Does the feedback loop pass? Are no other tests broken? Use the `$dryas:verify` skill before claiming success.
4. **Clean up.** Remove every debug log line before reporting the fix: a search for the prefix returns zero hits. Record the confirmed hypothesis in the fix's commit message.
5. **If the fix doesn't work.** STOP. Count the fixes you have tried. Fewer than 3: return to Phase 1 and re-analyze with the new information. 3 or more: STOP and question the architecture (step 6). Do NOT attempt fix #4 without an architectural discussion.
6. **If 3+ fixes failed: question the architecture.** The pattern of an architectural problem: each fix reveals new shared state, coupling or a problem in a different place; fixes need "massive refactoring" to implement; each fix creates new symptoms elsewhere. STOP and question fundamentals: is this pattern fundamentally sound? Are we sticking with it through sheer inertia? Should we refactor the architecture rather than keep fixing symptoms? **Discuss with your human partner before attempting more fixes.** This is not a failed hypothesis; it is a wrong architecture.

## Red flags

If you catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- "Pattern says X but I'll adapt it differently"
- "Here are the main problems: [a list of fixes without investigation]"
- Proposing solutions before tracing the data flow
- **"One more fix attempt" (when already tried 2+)**
- **Each fix reveals a new problem in a different place**

ALL of these mean: STOP. Return to Phase 1. If 3+ fixes failed, question the architecture (Phase 4, step 6).

## More

- When your human partner redirects you ("Stop guessing", "We're stuck?"), read `<dryas-root>/skills/debug/reference.md` § Signals from the user.
- When tempted to skip a step, read `<dryas-root>/skills/debug/reference.md` § Rationalizations.
- When you want the phases on one table, read `<dryas-root>/skills/debug/reference.md` § Quick reference.
- When the investigation points to an environmental, timing or external cause, read `<dryas-root>/skills/debug/reference.md` § No root cause found.

## Supporting techniques

Part of this process, in this folder:

- When the bad value comes from deep in the call stack, or a test pollutes shared state: `<dryas-root>/skills/debug/root-cause-tracing.md`.
- After finding the root cause, to add validation at every layer: `<dryas-root>/skills/debug/defense-in-depth.md`.
- When a test waits on an arbitrary timeout: `<dryas-root>/skills/debug/condition-based-waiting.md`.

Principle: `<dryas-root>/pstack/principles/fix-root-causes.md`.
