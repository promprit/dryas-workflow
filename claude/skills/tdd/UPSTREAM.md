# Upstream coverage: tdd

Rows follow the grammar in [../UPSTREAM.md](../UPSTREAM.md).

## tdd

Upstream: `test-driven-development/`

| Upstream item | Where it lives |
|---|---|
| Test-Driven Development (TDD) | tdd/SKILL.md § TDD |
| Overview | tdd/SKILL.md § TDD |
| Overview — test first, watch it fail, minimal code to pass | tdd/SKILL.md § TDD |
| Overview — core principle: didn't watch it fail, don't know it tests the right thing | tdd/SKILL.md § TDD |
| Overview — violating the letter is violating the spirit | tdd/SKILL.md § TDD |
| When to Use | tdd/SKILL.md § When to use |
| When to Use — always: new features, bug fixes, refactoring, behavior changes | tdd/SKILL.md § When to use |
| When to Use — exceptions (ask your human partner): throwaway prototypes, generated code, configuration files | tdd/SKILL.md § When to use |
| When to Use — "skip TDD just this once" is rationalization | tdd/SKILL.md § When to use |
| When to Use — executor section names its first test in Failing test first (Dryas) | tdd/SKILL.md § When to use; executor: "Test first. If the section names a failing test, run it and confirm it fails for the right reason before writing code." |
| When to Use — tester dispatched first, coder starts from that failing test (Dryas) | tdd/SKILL.md § When to use; executor: "If you are dispatched as a tester, write that failing test and stop once it fails correctly."; orchestrate: "confirm the test fails for the right reason, then dispatch the coder" |
| When to Use — none (review) and none (cleanup) sections skip it (Dryas) | tdd/SKILL.md § When to use; orchestrate: "Review and cleanup tasks (`Failing test first: none (review)` or `none (cleanup)`) skip this gate" |
| The Iron Law | tdd/SKILL.md § Iron law |
| The Iron Law — no production code without a failing test first | tdd/SKILL.md § Iron law |
| The Iron Law — code before the test: delete it, start over | tdd/SKILL.md § Iron law |
| The Iron Law — no exceptions: don't keep it as reference | tdd/SKILL.md § Iron law |
| The Iron Law — no exceptions: don't adapt it while writing tests | tdd/SKILL.md § Iron law |
| The Iron Law — no exceptions: don't look at it | tdd/SKILL.md § Iron law |
| The Iron Law — no exceptions: delete means delete | tdd/SKILL.md § Iron law |
| The Iron Law — implement fresh from tests | tdd/SKILL.md § Iron law |
| Red-Green-Refactor | tdd/SKILL.md § Red, green, refactor |
| Red-Green-Refactor — cycle diagram (red, verify red, green, verify green, refactor, next) | tdd/SKILL.md § Red, green, refactor |
| RED - Write Failing Test | tdd/SKILL.md § Red: write a failing test |
| RED - Write Failing Test — one minimal test showing what should happen | tdd/SKILL.md § Red: write a failing test |
| RED - Write Failing Test — good example (retries 3 times) | tdd/SKILL.md § Red: write a failing test |
| RED - Write Failing Test — bad example (vague name, tests the mock) | tdd/SKILL.md § Red: write a failing test |
| RED - Write Failing Test — requirements: one behavior, clear name, real code | tdd/SKILL.md § Red: write a failing test |
| Verify RED - Watch It Fail | tdd/SKILL.md § Verify red |
| Verify RED - Watch It Fail — mandatory, never skip; run the test | tdd/SKILL.md § Verify red; executor: "run it and confirm it fails for the right reason" |
| Verify RED - Watch It Fail — confirm: fails, not errors | tdd/SKILL.md § Verify red |
| Verify RED - Watch It Fail — confirm: failure message is expected | tdd/SKILL.md § Verify red |
| Verify RED - Watch It Fail — confirm: fails because the feature is missing, not typos | tdd/SKILL.md § Verify red |
| Verify RED - Watch It Fail — test passes: testing existing behavior, fix the test | tdd/SKILL.md § Verify red |
| Verify RED - Watch It Fail — test errors: fix and re-run until it fails correctly | tdd/SKILL.md § Verify red |
| GREEN - Minimal Code | tdd/SKILL.md § Green: minimal code |
| GREEN - Minimal Code — simplest code to pass the test | tdd/SKILL.md § Green: minimal code; executor: "Minimal change that meets Done." |
| GREEN - Minimal Code — good example (just enough) | tdd/SKILL.md § Green: minimal code |
| GREEN - Minimal Code — bad example (over-engineered options, YAGNI) | tdd/SKILL.md § Green: minimal code |
| GREEN - Minimal Code — no features, refactors or improvements beyond the test | tdd/SKILL.md § Green: minimal code; executor: "No refactors, renames or extras outside the goal." |
| Verify GREEN - Watch It Pass | tdd/SKILL.md § Verify green |
| Verify GREEN - Watch It Pass — mandatory; run the test | tdd/SKILL.md § Verify green; executor: "Run the tests named in Done before reporting." |
| Verify GREEN - Watch It Pass — confirm: test passes | tdd/SKILL.md § Verify green |
| Verify GREEN - Watch It Pass — confirm: other tests still pass | tdd/SKILL.md § Verify green |
| Verify GREEN - Watch It Pass — confirm: output pristine | tdd/SKILL.md § Verify green |
| Verify GREEN - Watch It Pass — test fails: fix code, not test | tdd/SKILL.md § Verify green |
| Verify GREEN - Watch It Pass — other tests fail: fix now | tdd/SKILL.md § Verify green |
| Verify GREEN - Watch It Pass — other tests means the project's suite; run the project's test command | tdd/SKILL.md § Verify green |
| Verify GREEN - Watch It Pass — scope bounds the deliverable, not the verification | tdd/SKILL.md § Verify green |
| Verify GREEN - Watch It Pass — every failure seen goes in the report by name; omission falsifies it | tdd/SKILL.md § Verify green; executor: "Never claim a pass you did not see." |
| REFACTOR - Clean Up | tdd/SKILL.md § Refactor |
| REFACTOR - Clean Up — after green only: remove duplication, improve names, extract helpers | tdd/SKILL.md § Refactor |
| REFACTOR - Clean Up — keep tests green, add no behavior | tdd/SKILL.md § Refactor |
| Repeat | tdd/SKILL.md § Repeat |
| Good Tests | tdd/SKILL.md § Good tests |
| Good Tests — minimal: one thing; "and" in the name, split it | tdd/SKILL.md § Good tests |
| Good Tests — clear: name describes behavior | tdd/SKILL.md § Good tests |
| Good Tests — shows intent: demonstrates the desired API | tdd/SKILL.md § Good tests |
| Good Tests — read writing-good-tests.md when writing or changing any test | tdd/SKILL.md § Good tests |
| Good Tests — name the production change that would make the test fail | tdd/SKILL.md § Good tests; executor: "name the defect a test must catch" |
| Good Tests — assert on real behavior, never on mock behavior | tdd/SKILL.md § Good tests; executor: "assert the required result through the public interface" |
| Good Tests — test-only code in test utilities | tdd/SKILL.md § Good tests |
| Good Tests — understand a dependency's side effects before mocking | tdd/SKILL.md § Good tests |
| Common Rationalizations | tdd/SKILL.md § Rationalizations |
| Common Rationalizations — "Too simple to test" | tdd/SKILL.md § Rationalizations |
| Common Rationalizations — "I'll test after" | tdd/SKILL.md § Rationalizations |
| Common Rationalizations — "Tests after achieve same goals (spirit not ritual)" | tdd/SKILL.md § Rationalizations |
| Common Rationalizations — "Already manually tested" | tdd/SKILL.md § Rationalizations |
| Common Rationalizations — "Deleting X hours is wasteful" | tdd/SKILL.md § Rationalizations |
| Common Rationalizations — "Keep as reference, write tests first" | tdd/SKILL.md § Rationalizations |
| Common Rationalizations — "Need to explore first" | tdd/SKILL.md § Rationalizations |
| Common Rationalizations — "Test hard = design unclear" | tdd/SKILL.md § Rationalizations |
| Common Rationalizations — "TDD will slow me down" | tdd/SKILL.md § Rationalizations |
| Common Rationalizations — "Manual test faster" | tdd/SKILL.md § Rationalizations |
| Common Rationalizations — "Existing code has no tests" | tdd/SKILL.md § Rationalizations |
| Red Flags - STOP and Start Over | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — code before test | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — test after implementation | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — test passes immediately | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — can't explain why the test failed | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — tests added "later" | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — rationalizing "just this once" | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — "I already manually tested it" | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — "Tests after achieve the same purpose" | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — "It's about spirit not ritual" | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — "Keep as reference" or "adapt existing code" | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — "Already spent X hours, deleting is wasteful" | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — "TDD is dogmatic, I'm being pragmatic" | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — "This is different because..." | tdd/SKILL.md § Red flags |
| Red Flags - STOP and Start Over — all mean: delete code, start over with TDD | tdd/SKILL.md § Red flags |
| Example: Bug Fix | tdd/SKILL.md § Example: bug fix |
| Example: Bug Fix — red, verify red, green, verify green, refactor (empty email) | tdd/SKILL.md § Example: bug fix |
| Verification Checklist | tdd/SKILL.md § Checklist |
| Verification Checklist — every new function or method has a test | tdd/SKILL.md § Checklist |
| Verification Checklist — watched each test fail before implementing | tdd/SKILL.md § Checklist |
| Verification Checklist — each test failed for the expected reason | tdd/SKILL.md § Checklist |
| Verification Checklist — wrote minimal code to pass each test | tdd/SKILL.md § Checklist |
| Verification Checklist — all tests pass | tdd/SKILL.md § Checklist |
| Verification Checklist — output pristine | tdd/SKILL.md § Checklist |
| Verification Checklist — tests use real code (mocks only if unavoidable) | tdd/SKILL.md § Checklist |
| Verification Checklist — edge cases and errors covered | tdd/SKILL.md § Checklist |
| Verification Checklist — can't check all boxes: you skipped TDD, start over | tdd/SKILL.md § Checklist |
| When Stuck | tdd/SKILL.md § When stuck |
| When Stuck — don't know how to test: wished-for API, assertion first, ask | tdd/SKILL.md § When stuck |
| When Stuck — test too complicated: simplify the interface | tdd/SKILL.md § When stuck |
| When Stuck — must mock everything: dependency injection | tdd/SKILL.md § When stuck |
| When Stuck — test setup huge: extract helpers, simplify design | tdd/SKILL.md § When stuck |
| Debugging Integration | tdd/SKILL.md § With debug; debug/SKILL.md § Phase 4: Fix |
| Debugging Integration — bug found: failing test reproducing it, follow the cycle | tdd/SKILL.md § With debug |
| Debugging Integration — never fix bugs without a test | tdd/SKILL.md § With debug |
| Final Rule | tdd/SKILL.md § Final rule |
| Final Rule — production code: test exists and failed first; otherwise not TDD | tdd/SKILL.md § Final rule |
| Final Rule — no exceptions without your human partner's permission | tdd/SKILL.md § Final rule |
| writing-good-tests.md | tdd/writing-good-tests.md § Writing good tests |
| writing-good-tests.md — load when writing tests, adding mocks or test helpers | tdd/writing-good-tests.md § Writing good tests |
| writing-good-tests.md — Overview: names the break, exercises the real thing | tdd/writing-good-tests.md § Overview |
| writing-good-tests.md — Principle 1: Name the Break | tdd/writing-good-tests.md § Principle 1: Name the break |
| writing-good-tests.md — Principle 1: derive expectations independently (mirror assertion) | tdd/writing-good-tests.md § Principle 1: Name the break |
| writing-good-tests.md — Principle 1: no change detectors | tdd/writing-good-tests.md § Principle 1: Name the break |
| writing-good-tests.md — Principle 1: behavior, not text (writing-skills/ for agent documents) | tdd/writing-good-tests.md § Principle 1: Name the break |
| writing-good-tests.md — Principle 1: your code, not the framework | tdd/writing-good-tests.md § Principle 1: Name the break |
| writing-good-tests.md — Principle 1: Gate Function | tdd/writing-good-tests.md § Gate function: before the test body |
| writing-good-tests.md — Principle 2: Exercise the Real Thing | tdd/writing-good-tests.md § Principle 2: Exercise the real thing |
| writing-good-tests.md — Principle 2: the mock earns no assertions | tdd/writing-good-tests.md § Principle 2: Exercise the real thing |
| writing-good-tests.md — Principle 2: mock at the right level | tdd/writing-good-tests.md § Principle 2: Exercise the real thing |
| writing-good-tests.md — Principle 2: make doubles specific | tdd/writing-good-tests.md § Principle 2: Exercise the real thing |
| writing-good-tests.md — Principle 2: mirror real data completely | tdd/writing-good-tests.md § Principle 2: Exercise the real thing |
| writing-good-tests.md — Principle 2: production classes carry production methods only | tdd/writing-good-tests.md § Principle 2: Exercise the real thing |
| writing-good-tests.md — Principle 2: prefer real components over complex mocks | tdd/writing-good-tests.md § Principle 2: Exercise the real thing |
| writing-good-tests.md — Principle 2: Gate Function | tdd/writing-good-tests.md § Gate function: before a mock |
| writing-good-tests.md — Tests Ship With the Implementation | tdd/writing-good-tests.md § Tests ship with the implementation |
| writing-good-tests.md — The Mutation Check | tdd/writing-good-tests.md § The mutation check |
| writing-good-tests.md — Quick Reference | tdd/writing-good-tests.md § Quick reference |
| writing-good-tests.md — Warning Signs | tdd/writing-good-tests.md § Warning signs |
