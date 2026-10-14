---
name: debug
description: Use on any bug, test failure or unexpected behavior, before proposing a fix, and before /orchestrate climbs a task to a stronger tier. Root cause first (four phases); no fix by guessing.
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

**ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You have already tried several fixes
- A previous fix did not work
- You do not fully understand the issue

**Do not skip it when:**
- The issue seems simple (simple bugs have root causes too)
- You are in a hurry (rushing guarantees rework)
- A manager wants it fixed NOW (systematic is faster than thrashing)

In Dryas: `/orchestrate` runs this before every climb (fast → standard → strong → frontier) on the failing reports, read only. If the root cause is a plan defect (scope too narrow, Done vague or wrong, missing context), the fix is in that task's section of `.orchestrate/PLAN.md` and the task is re-dispatched on the same model; that is not a climb. Executors run Phase 1 before reporting a failure.

## Phase 1: Root cause

BEFORE attempting ANY fix:

1. **Read error messages carefully.** Do not skip past errors or warnings; they often contain the exact solution. Read stack traces completely. Note line numbers, file paths, error codes.
2. **Reproduce consistently.** Can you trigger it reliably? What are the exact steps? Does it happen every time? Not reproducible: gather more data, do not guess.
3. **Check recent changes.** What changed that could cause this? The diff, recent commits, new dependencies, config changes, environment differences.
4. **Gather evidence in multi-component systems.** When the system has several components (CI → build → signing, API → service → database), add diagnostic instrumentation BEFORE proposing fixes:
   ```
   For EACH component boundary:
     - log what data enters the component
     - log what data exits it
     - verify environment/config propagation
     - check state at each layer

   Run once to gather evidence showing WHERE it breaks
   THEN analyze the evidence to find the failing component
   THEN investigate that component
   ```
   Example (multi-layer system):
   ```bash
   # Layer 1: workflow
   echo "=== Secrets available in workflow: ==="
   echo "IDENTITY: ${IDENTITY:+SET}${IDENTITY:-UNSET}"
   # Layer 2: build script
   echo "=== Env vars in build script: ==="
   env | grep IDENTITY || echo "IDENTITY not in environment"
   # Layer 3: signing script
   echo "=== Keychain state: ==="
   security list-keychains
   security find-identity -v
   # Layer 4: actual signing
   codesign --sign "$IDENTITY" --verbose=4 "$APP"
   ```
   This reveals which layer fails (secrets → workflow ✓, workflow → build ✗).
5. **Trace data flow.** When the error is deep in the call stack, use the backward tracing technique in `${CLAUDE_PLUGIN_ROOT}/skills/debug/root-cause-tracing.md`. Quick version: where does the bad value originate? What called this with it? Keep tracing up to the source. Fix at the source, not at the symptom.

## Phase 2: Pattern analysis

Find the pattern before fixing:

1. **Find working examples.** Locate similar working code in the same codebase. What works that is like what is broken?
2. **Compare against references.** If you are implementing a pattern, read the reference implementation COMPLETELY. Do not skim; read every line. Understand the pattern fully before applying it.
3. **Identify differences.** What differs between working and broken? List every difference, however small. Do not assume "that can't matter".
4. **Understand dependencies.** What other components does this need? What settings, config, environment? What assumptions does it make?

## Phase 3: Hypothesis and test

Scientific method:

1. **Form a single hypothesis.** State it clearly: "I think X is the root cause because Y". Write it down. Be specific, not vague.
2. **Test minimally.** Make the SMALLEST possible change that tests the hypothesis. One variable at a time. Do not fix several things at once.
3. **Verify before continuing.** It worked: Phase 4. It did not: form a NEW hypothesis. Do NOT add more fixes on top.
4. **When you don't know.** Say "I don't understand X". Do not pretend to know. Ask for help. Research more.

## Phase 4: Fix

Fix the root cause, not the symptom:

1. **Create a failing test case.** The simplest possible reproduction: an automated test if possible, a one-off test script if there is no framework. You MUST have it before fixing. Use the `dryas:tdd` skill to write a proper failing test.
2. **Implement a single fix.** Address the root cause you identified. ONE change at a time. No "while I'm here" improvements, no bundled refactoring.
3. **Verify the fix.** Does the test pass now? Are no other tests broken? Is the issue actually resolved? Use the `dryas:verify` skill before claiming success.
4. **If the fix doesn't work.** STOP. Count the fixes you have tried. Fewer than 3: return to Phase 1 and re-analyze with the new information. 3 or more: STOP and question the architecture (step 5). Do NOT attempt fix #4 without an architectural discussion.
5. **If 3+ fixes failed: question the architecture.** The pattern of an architectural problem: each fix reveals new shared state, coupling or a problem in a different place; fixes need "massive refactoring" to implement; each fix creates new symptoms elsewhere. STOP and question fundamentals: is this pattern fundamentally sound? Are we sticking with it through sheer inertia? Should we refactor the architecture rather than keep fixing symptoms? **Discuss with your human partner before attempting more fixes.** This is not a failed hypothesis; it is a wrong architecture.

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

ALL of these mean: STOP. Return to Phase 1. If 3+ fixes failed, question the architecture (Phase 4, step 5).

## Signals from the user

Your human partner's redirections that mean you are doing it wrong:
- "Is that not happening?": you assumed without verifying.
- "Will it show us...?": you should have added evidence gathering.
- "Stop guessing": you are proposing fixes without understanding.
- "Ultra-think this": question fundamentals, not just symptoms.
- "We're stuck?" (frustrated): your approach is not working.

When you see these: STOP. Return to Phase 1.

## Rationalizations

| Excuse | Reality |
|---|---|
| "Issue is simple, don't need process" | Simple issues have root causes too. The process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | The first fix sets the pattern. Do it right from the start. |
| "I'll write the test after confirming the fix works" | Untested fixes don't stick. Test first proves it. |
| "Multiple fixes at once saves time" | You can't isolate what worked, and it causes new bugs. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I see the problem, let me fix it" | Seeing symptoms is not understanding the root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = an architectural problem. Question the pattern; don't fix again. |

## Quick reference

| Phase | Key activities | Success criteria |
|---|---|---|
| **1. Root cause** | Read errors, reproduce, check changes, gather evidence | Understand WHAT and WHY |
| **2. Pattern** | Find working examples, compare | Differences identified |
| **3. Hypothesis** | Form a theory, test minimally | Confirmed, or a new hypothesis |
| **4. Fix** | Create a test, fix, verify | Bug resolved, tests pass |

## No root cause found

If systematic investigation shows the issue is truly environmental, timing-dependent or external:

1. You have completed the process.
2. Document what you investigated.
3. Implement appropriate handling (retry, timeout, error message).
4. Add monitoring or logging for future investigation.

But: 95% of "no root cause" cases are incomplete investigation.

## Supporting techniques

Part of this process, in this folder:

- `${CLAUDE_PLUGIN_ROOT}/skills/debug/root-cause-tracing.md`: trace a bug backward through the call stack to the original trigger; find the test that pollutes shared state.
- `${CLAUDE_PLUGIN_ROOT}/skills/debug/defense-in-depth.md`: add validation at every layer after finding the root cause.
- `${CLAUDE_PLUGIN_ROOT}/skills/debug/condition-based-waiting.md`: replace arbitrary timeouts with condition polling.

Principle: `${CLAUDE_PLUGIN_ROOT}/pstack/principles/fix-root-causes.md`.
