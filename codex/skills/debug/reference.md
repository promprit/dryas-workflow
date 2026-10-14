# Debug reference

Read the section the pointer in `SKILL.md` names; nothing here is needed on every turn.

## Multi-layer evidence

When the system has several components (CI → build → signing, API → service → database), add diagnostic instrumentation BEFORE proposing fixes:

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

Example (multi-layer system; every line carries the debug prefix, and secrets print only as SET or UNSET):

```bash
# Layer 1: workflow
echo "DBG-sign: === Secrets available in workflow: ==="
echo "DBG-sign: IDENTITY: ${IDENTITY:+SET}${IDENTITY:-UNSET}"
# Layer 2: build script
echo "DBG-sign: === Env vars in build script: ==="
env | grep -q IDENTITY && echo "DBG-sign: IDENTITY in environment" || echo "DBG-sign: IDENTITY not in environment"
# Layer 3: signing script
echo "DBG-sign: === Keychain state: ==="
security list-keychains
security find-identity -v
# Layer 4: actual signing
codesign --sign "$IDENTITY" --verbose=4 "$APP"
```

This reveals which layer fails (secrets → workflow ✓, workflow → build ✗).

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
| **3. Hypothesis** | Rank theories, test one at a time | Confirmed, or a new hypothesis |
| **4. Fix** | Create a test, fix, verify | Bug resolved, tests pass |

## No root cause found

If systematic investigation shows the issue is truly environmental, timing-dependent or external:

1. You have completed the process.
2. Document what you investigated.
3. Implement appropriate handling (retry, timeout, error message).
4. Add monitoring or logging for future investigation.

But: 95% of "no root cause" cases are incomplete investigation.
