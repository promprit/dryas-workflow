---
name: tdd
description: Use when implementing any feature or bug fix, executors included, before writing implementation code. Write the failing test first, watch it fail for the right reason, write the minimal code to pass, then refactor.
---

# TDD

Write the test first. Watch it fail. Write the minimal code to pass.

**Core principle:** if you did not watch the test fail, you do not know if it tests the right thing.

Violating the letter of the rules is violating the spirit of the rules.

## When to use

**Always:** new features, bug fixes, refactoring, behavior changes.

**Exceptions (ask your human partner):** throwaway prototypes, generated code, configuration files.

Thinking "skip TDD just this once"? Stop. That is rationalization (when tempted, read `<dryas-root>/skills/tdd/reference.md` § Rationalizations).

In Dryas: an executor's section names its first test in `Failing test first:`; write or confirm that test, run it, and see it fail for the right reason before any implementation. If `$dryas:orchestrate` dispatched a tester first, the coder starts from that failing test. Sections marked `none (review)` or `none (cleanup)` skip this skill.

## Iron law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Wrote code before the test? Delete it. Start over. **No exceptions:** do not keep it as "reference"; do not "adapt" it while writing tests; do not look at it; delete means delete. Implement fresh from tests. Period.

## Red, green, refactor

The cycle:

```
RED (write a failing test) -> verify it fails correctly
    wrong failure -> back to RED
GREEN (minimal code) -> verify it passes, all green
    not passing -> back to GREEN
REFACTOR (clean up) -> verify it stays green
-> next test, back to RED
```

For good and bad code at each step, read `<dryas-root>/skills/tdd/reference.md` § Red and green examples; for one full cycle on a bug, § Example: bug fix.

### Red: write a failing test

Write one minimal test showing what should happen. **Requirements:** one behavior; a clear name; real code (no mocks unless unavoidable).

### Verify red

**MANDATORY. Never skip.** Run the test (for example `npm test path/to/test.test.ts`, `python3 -m pytest -q path/to/test_x.py`). Confirm:
- The test fails (not errors)
- The failure message is the expected one
- It fails because the feature is missing (not because of typos)

**Test passes?** You are testing existing behavior. Fix the test. **Test errors?** Fix the error, re-run until it fails correctly.

### Green: minimal code

Write the simplest code that passes the test. Do not add features, refactor other code, or "improve" beyond the test (no options no test asked for: YAGNI).

### Verify green

**MANDATORY.** Run the test again. Confirm:
- The test passes
- Other tests still pass
- The output is pristine (no errors, warnings)

**Test fails?** Fix the code, not the test. **Other tests fail?** Fix them now.

**"Other tests" means the project's suite, not just your file.** A green run of the test you wrote is not a green suite. Before you call the change done, run the project's test command (bare `pytest`, `npm test`, `cargo test`, whatever the repo uses) even when your task named only one test file. A scope statement in your task bounds the deliverable, not your verification. Any failure that run shows, including one you did not cause, goes in your report by name; a red test you watched scroll past and did not mention is a report falsified by omission.

### Refactor

After green only: remove duplication, improve names, extract helpers. Keep the tests green. Do not add behavior.

### Repeat

Next failing test for the next feature.

## Good tests

| Quality | Good | Bad |
|---|---|---|
| **Minimal** | One thing. "and" in the name? Split it. | `test('validates email and domain and whitespace')` |
| **Clear** | The name describes the behavior | `test('test1')` |
| **Shows intent** | Demonstrates the desired API | Obscures what the code should do |

When writing or changing any test, read `<dryas-root>/skills/tdd/writing-good-tests.md` for the rules that keep tests honest:
- Name the production change that would make the test fail, before writing it
- Assert on real behavior, never on mock behavior
- Keep test-only code in test utilities, out of production classes
- Understand a dependency's side effects before mocking it

Principle: `<dryas-root>/pstack/principles/test-behavior-not-implementation.md`.

## Red flags

STOP and start over on any of these:
- Code before test
- Test after implementation
- Test passes immediately
- Cannot explain why the test failed
- Tests added "later"
- Rationalizing "just this once"
- "I already manually tested it"
- "Tests after achieve the same purpose"
- "It's about spirit not ritual"
- "Keep as reference" or "adapt existing code"
- "Already spent X hours, deleting is wasteful"
- "TDD is dogmatic, I'm being pragmatic"
- "This is different because..."

**All of these mean: delete the code. Start over with TDD.**

## Checklist

Before marking work complete:

- [ ] Every new function or method has a test
- [ ] Watched each test fail before implementing
- [ ] Each test failed for the expected reason (feature missing, not a typo)
- [ ] Wrote the minimal code to pass each test
- [ ] All tests pass
- [ ] Output pristine (no errors, warnings)
- [ ] Tests use real code (mocks only if unavoidable)
- [ ] Edge cases and errors covered

Cannot check all boxes? You skipped TDD. Start over. When you cannot see how to test something, read `<dryas-root>/skills/tdd/reference.md` § When stuck.

## With debug

Bug found? Write a failing test reproducing it, then follow the cycle. The test proves the fix and prevents a regression. Find the root cause first with the `$dryas:debug` skill. Never fix bugs without a test.

## Final rule

```
Production code -> a test exists and failed first
Otherwise       -> not TDD
```

No exceptions without your human partner's permission.
