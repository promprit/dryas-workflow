---
name: verify
description: Use before claiming work is done, fixed or passing, and before $dryas:commit or any merge. Run the command that proves the claim, read its full output, then state the result with the evidence; evidence before assertions, always.
---
On Codex: verify means run the tests and read the output; name the harness (Codex) and the models used in the commit body.

# Verify

Evidence before claims, always.

Violating the letter of this rule is violating its spirit.

## Iron law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you have not run the verification command in this message, you cannot claim it passes.

## Gate function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: what command proves this claim?
2. RUN: execute the FULL command (fresh, complete)
3. READ: the full output; check the exit code; count failures
4. VERIFY: does the output confirm the claim?
   - NO: state the actual status, with the evidence
   - YES: state the claim, WITH the evidence
5. ONLY THEN: make the claim

Skip any step = lying, not verifying
```

## Common failures

| Claim | Requires | Not sufficient |
|---|---|---|
| Tests pass | Test command output: 0 failures | A previous run, "should pass" |
| Linter clean | Linter output: 0 errors | A partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | The original symptom, tested: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | The test passes once |
| Agent completed | The VCS diff shows the changes | The agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red flags

STOP when you notice:
- "should", "probably", "seems to"
- Satisfaction before verification ("Great!", "Perfect!", "Done!" and the like)
- About to commit, push or open a PR without verification
- Trusting an agent's success report
- Relying on partial verification
- Thinking "just this once"
- Tired and wanting the work over
- **ANY wording that implies success without having run the verification**

## Rationalizations

| Excuse | Reality |
|---|---|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence is not evidence |
| "Just this once" | No exceptions |
| "Linter passed" | A linter is not a compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion is not an excuse |
| "Partial check is enough" | Partial proves nothing |
| "Different words, so the rule doesn't apply" | Spirit over letter |

## Key patterns

**Tests:**
```
OK:  [run the test command] [see: 34/34 pass] "All tests pass"
NO:  "Should pass now" / "Looks correct"
```

**Regression tests (red-green):**
```
OK:  write -> run (pass) -> revert the fix -> run (MUST FAIL) -> restore -> run (pass)
NO:  "I've written a regression test" (without red-green verification)
```

**Build:**
```
OK:  [run the build] [see: exit 0] "Build passes"
NO:  "Linter passed" (a linter does not check compilation)
```

**Requirements:**
```
OK:  re-read the plan -> make a checklist -> verify each item -> report gaps or completion
NO:  "Tests pass, phase complete"
```

**Agent delegation:**
```
OK:  agent reports success -> check the VCS diff -> verify the changes -> report the actual state
NO:  trust the agent's report
```

## When to apply

ALWAYS before:
- ANY variation of a success or completion claim
- ANY expression of satisfaction
- ANY positive statement about the state of the work
- Committing, opening a PR, completing a task
- Moving to the next task
- Delegating to agents

The rule covers exact phrases, paraphrases and synonyms, implications of success, and ANY communication that suggests completion or correctness.

In Dryas: after `$dryas:wreview` and before `$dryas:commit` on every orchestrated branch, before every merge, and before reporting an executor's task done. A performance number also passes `<dryas-root>/pstack/benchmark-checklist.md` when pstack picks are on.
