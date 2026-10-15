# Upstream coverage: debug

Rows follow the grammar in [../UPSTREAM.md](../UPSTREAM.md).

## debug

Upstream: `systematic-debugging/`

| Upstream item | Where it lives |
|---|---|
| Overview | debug/SKILL.md § Debug |
| Overview — core principle: root cause before fixes; symptom fixes are failure | debug/SKILL.md § Debug; executor: "Fix root causes" |
| Overview — violating the letter is violating the spirit | debug/SKILL.md § Debug |
| The Iron Law | debug/SKILL.md § Iron law |
| The Iron Law — no fixes without root cause investigation first | debug/SKILL.md § Iron law |
| The Iron Law — Phase 1 incomplete: no fix proposals | debug/SKILL.md § Iron law |
| When to Use | debug/SKILL.md § When to use |
| When to Use — any technical issue (test failures, production bugs, unexpected behavior, performance, build, integration) | debug/SKILL.md § When to use |
| When to Use — ESPECIALLY: under time pressure | debug/SKILL.md § When to use |
| When to Use — ESPECIALLY: one quick fix seems obvious | debug/SKILL.md § When to use |
| When to Use — ESPECIALLY: already tried multiple fixes | debug/SKILL.md § When to use |
| When to Use — ESPECIALLY: previous fix didn't work | debug/SKILL.md § When to use |
| When to Use — ESPECIALLY: don't fully understand the issue | debug/SKILL.md § When to use |
| When to Use — don't skip: issue seems simple | debug/SKILL.md § When to use |
| When to Use — don't skip: in a hurry | debug/SKILL.md § When to use |
| When to Use — don't skip: manager wants it fixed NOW | debug/SKILL.md § When to use |
| When to Use — before an escalation climb; plan defects fixed in PLAN.md (Dryas) | debug/SKILL.md § When to use; orchestrate: "Before each climb" |
| The Four Phases | debug/SKILL.md § Iron law |
| The Four Phases — complete each phase before the next | debug/SKILL.md § Iron law |
| Phase 1: Root Cause Investigation | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 1. Read error messages carefully | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 2. Reproduce consistently; not reproducible, gather data | debug/SKILL.md § Phase 1: Root cause; debug/SKILL.md § Feedback loop first |
| Phase 1: Root Cause Investigation — feedback loop first: one fast deterministic command that fails on the bug; none, say what blocks it and stop (Dryas) | debug/SKILL.md § Feedback loop first |
| Phase 1: Root Cause Investigation — redact secrets in any output shown (Dryas) | debug/SKILL.md § Feedback loop first; debug/reference.md § Multi-layer evidence |
| Phase 1: Root Cause Investigation — tag temporary debug lines with a unique prefix (Dryas) | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 3. Check recent changes | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 4. Gather evidence in multi-component systems | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 4. instrument each boundary, run once, analyze, investigate | debug/SKILL.md § Phase 1: Root cause; debug/reference.md § Multi-layer evidence |
| Phase 1: Root Cause Investigation — 4. multi-layer example | debug/reference.md § Multi-layer evidence |
| Phase 1: Root Cause Investigation — 5. Trace data flow | debug/SKILL.md § Phase 1: Root cause; debug/root-cause-tracing.md § The tracing process |
| Phase 1: Root Cause Investigation — 5. quick version: origin, caller, trace up, fix at source | debug/SKILL.md § Phase 1: Root cause |
| Phase 2: Pattern Analysis | debug/SKILL.md § Phase 2: Pattern analysis |
| Phase 2: Pattern Analysis — 1. Find working examples | debug/SKILL.md § Phase 2: Pattern analysis |
| Phase 2: Pattern Analysis — 2. Compare against references, read completely | debug/SKILL.md § Phase 2: Pattern analysis |
| Phase 2: Pattern Analysis — 3. Identify differences, however small | debug/SKILL.md § Phase 2: Pattern analysis |
| Phase 2: Pattern Analysis — 4. Understand dependencies | debug/SKILL.md § Phase 2: Pattern analysis |
| Phase 3: Hypothesis and Testing | debug/SKILL.md § Phase 3: Hypothesis and test |
| Phase 3: Hypothesis and Testing — 1. Form a single hypothesis | debug/SKILL.md § Phase 3: Hypothesis and test |
| Phase 3: Hypothesis and Testing — 3-5 ranked falsifiable hypotheses with predictions, shown to the user, tested in rank order (Dryas) | debug/SKILL.md § Phase 3: Hypothesis and test |
| Phase 3: Hypothesis and Testing — 2. Test minimally, one variable at a time | debug/SKILL.md § Phase 3: Hypothesis and test |
| Phase 3: Hypothesis and Testing — 3. Verify before continuing; no fixes on top | debug/SKILL.md § Phase 3: Hypothesis and test |
| Phase 3: Hypothesis and Testing — 4. When you don't know | debug/SKILL.md § Phase 3: Hypothesis and test |
| Phase 4: Implementation | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 1. Create a failing test case (test-driven-development/ skill) | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 2. Implement a single fix; no while-I'm-here, no bundled refactoring | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 3. Verify the fix (verification-before-completion/ skill) | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — remove debug lines (prefix search finds none); confirmed hypothesis in the commit message (Dryas) | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 4. Fix doesn't work: count; under 3 back to Phase 1; 3+ stop | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 5. 3+ fixes failed: question the architecture | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 5. signs of an architectural problem | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 5. question fundamentals; discuss with your human partner | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 5. not a failed hypothesis, a wrong architecture | debug/SKILL.md § Phase 4: Fix |
| Red Flags - STOP and Follow Process | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Quick fix for now, investigate later" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Just try changing X and see if it works" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Add multiple changes, run tests" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Skip the test, I'll manually verify" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "It's probably X, let me fix that" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "I don't fully understand but this might work" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Pattern says X but I'll adapt it differently" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Here are the main problems" without investigation | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — proposing solutions before tracing data flow | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "One more fix attempt" after 2+ | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — each fix reveals a new problem elsewhere | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — all mean return to Phase 1; 3+ failed, question the architecture | debug/SKILL.md § Red flags |
| your human partner's Signals You're Doing It Wrong | debug/reference.md § Signals from the user; debug/SKILL.md § More |
| your human partner's Signals You're Doing It Wrong — "Is that not happening?" | debug/reference.md § Signals from the user; debug/SKILL.md § More |
| your human partner's Signals You're Doing It Wrong — "Will it show us...?" | debug/reference.md § Signals from the user; debug/SKILL.md § More |
| your human partner's Signals You're Doing It Wrong — "Stop guessing" | debug/reference.md § Signals from the user; debug/SKILL.md § More |
| your human partner's Signals You're Doing It Wrong — "Ultra-think this" | debug/reference.md § Signals from the user; debug/SKILL.md § More |
| your human partner's Signals You're Doing It Wrong — "We're stuck?" | debug/reference.md § Signals from the user; debug/SKILL.md § More |
| your human partner's Signals You're Doing It Wrong — stop, return to Phase 1 | debug/reference.md § Signals from the user; debug/SKILL.md § More |
| Common Rationalizations | debug/reference.md § Rationalizations; debug/SKILL.md § More |
| Common Rationalizations — "Issue is simple, don't need process" | debug/reference.md § Rationalizations; debug/SKILL.md § More |
| Common Rationalizations — "Emergency, no time for process" | debug/reference.md § Rationalizations; debug/SKILL.md § More |
| Common Rationalizations — "Just try this first, then investigate" | debug/reference.md § Rationalizations; debug/SKILL.md § More |
| Common Rationalizations — "I'll write test after confirming fix works" | debug/reference.md § Rationalizations; debug/SKILL.md § More |
| Common Rationalizations — "Multiple fixes at once saves time" | debug/reference.md § Rationalizations; debug/SKILL.md § More |
| Common Rationalizations — "Reference too long, I'll adapt the pattern" | debug/reference.md § Rationalizations; debug/SKILL.md § More |
| Common Rationalizations — "I see the problem, let me fix it" | debug/reference.md § Rationalizations; debug/SKILL.md § More |
| Common Rationalizations — "One more fix attempt" (after 2+ failures) | debug/reference.md § Rationalizations; debug/SKILL.md § More |
| Quick Reference | debug/reference.md § Quick reference; debug/SKILL.md § More |
| Quick Reference — four phases: key activities and success criteria | debug/reference.md § Quick reference; debug/SKILL.md § More |
| When Process Reveals "No Root Cause" | debug/reference.md § No root cause found; debug/SKILL.md § More |
| When Process Reveals "No Root Cause" — 1. you've completed the process | debug/reference.md § No root cause found; debug/SKILL.md § More |
| When Process Reveals "No Root Cause" — 2. document what you investigated | debug/reference.md § No root cause found; debug/SKILL.md § More |
| When Process Reveals "No Root Cause" — 3. appropriate handling (retry, timeout, error message) | debug/reference.md § No root cause found; debug/SKILL.md § More |
| When Process Reveals "No Root Cause" — 4. monitoring or logging | debug/reference.md § No root cause found; debug/SKILL.md § More |
| When Process Reveals "No Root Cause" — 95% are incomplete investigation | debug/reference.md § No root cause found; debug/SKILL.md § More |
| Supporting Techniques | debug/SKILL.md § Supporting techniques |
| Supporting Techniques — root-cause-tracing, defense-in-depth, condition-based-waiting | debug/SKILL.md § Supporting techniques |
| Supporting Techniques — fix-root-causes principle (Dryas) | debug/SKILL.md § Supporting techniques |
| root-cause-tracing.md | debug/root-cause-tracing.md § Root cause tracing |
| root-cause-tracing.md — Overview, core principle | debug/root-cause-tracing.md § Overview |
| root-cause-tracing.md — When to Use (flowchart, use when) | debug/root-cause-tracing.md § When to use |
| root-cause-tracing.md — The Tracing Process 1-5 | debug/root-cause-tracing.md § The tracing process |
| root-cause-tracing.md — Adding Stack Traces (instrument, stderr in tests, run and capture, analyze) | debug/root-cause-tracing.md § Adding stack traces |
| root-cause-tracing.md — Finding Which Test Causes Pollution | debug/root-cause-tracing.md § Find the polluter |
| root-cause-tracing.md — Real Example: Empty projectDir | debug/root-cause-tracing.md § Real example: empty projectDir |
| root-cause-tracing.md — Key Principle (flowchart, never fix just the symptom) | debug/root-cause-tracing.md § Key principle |
| root-cause-tracing.md — Stack Trace Tips | debug/root-cause-tracing.md § Stack trace tips |
| root-cause-tracing.md — Real-World Impact | debug/root-cause-tracing.md § Real-world impact |
| defense-in-depth.md | debug/defense-in-depth.md § Defense-in-depth validation |
| defense-in-depth.md — Overview, core principle | debug/defense-in-depth.md § Overview |
| defense-in-depth.md — Why Multiple Layers | debug/defense-in-depth.md § Why multiple layers |
| defense-in-depth.md — Layer 1: Entry Point Validation | debug/defense-in-depth.md § Layer 1: Entry point validation |
| defense-in-depth.md — Layer 2: Business Logic Validation | debug/defense-in-depth.md § Layer 2: Business logic validation |
| defense-in-depth.md — Layer 3: Environment Guards | debug/defense-in-depth.md § Layer 3: Environment guards |
| defense-in-depth.md — Layer 4: Debug Instrumentation | debug/defense-in-depth.md § Layer 4: Debug instrumentation |
| defense-in-depth.md — Applying the Pattern 1-4 | debug/defense-in-depth.md § Applying the pattern |
| defense-in-depth.md — Example from Session | debug/defense-in-depth.md § Example from a session |
| defense-in-depth.md — Key Insight | debug/defense-in-depth.md § Key insight |
| condition-based-waiting.md | debug/condition-based-waiting.md § Condition-based waiting |
| condition-based-waiting.md — Overview, core principle | debug/condition-based-waiting.md § Overview |
| condition-based-waiting.md — When to Use (flowchart, use when, don't use when) | debug/condition-based-waiting.md § When to use |
| condition-based-waiting.md — Core Pattern | debug/condition-based-waiting.md § Core pattern |
| condition-based-waiting.md — Quick Patterns | debug/condition-based-waiting.md § Quick patterns |
| condition-based-waiting.md — Implementation (waitFor) | debug/condition-based-waiting.md § Implementation |
| condition-based-waiting.md — Implementation: domain helpers in the example file | debug/condition-based-waiting.md § Implementation |
| condition-based-waiting.md — Common Mistakes (too fast, no timeout, stale data) | debug/condition-based-waiting.md § Common mistakes |
| condition-based-waiting.md — When Arbitrary Timeout IS Correct | debug/condition-based-waiting.md § When an arbitrary timeout IS correct |
| condition-based-waiting.md — Real-World Impact | debug/condition-based-waiting.md § Real-world impact |
| condition-based-waiting-example.ts | extra:superpowers |
| find-polluter.sh | debug/root-cause-tracing.md § Find the polluter |
| CREATION-LOG.md | extra:superpowers |
| test-academic.md | extra:superpowers |
| test-pressure-1.md | extra:superpowers |
| test-pressure-2.md | extra:superpowers |
| test-pressure-3.md | extra:superpowers |
