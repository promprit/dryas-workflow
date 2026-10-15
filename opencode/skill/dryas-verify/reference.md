# Verify reference

Read the section the pointer in `SKILL.md` names; nothing here is needed on every turn.

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
