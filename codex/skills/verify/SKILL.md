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

## When to apply

ALWAYS before:
- ANY variation of a success or completion claim
- ANY expression of satisfaction
- ANY positive statement about the state of the work
- Committing, opening a PR, completing a task
- Moving to the next task
- Delegating to agents

The rule covers exact phrases, paraphrases and synonyms, implications of success, and ANY communication that suggests completion or correctness.

In Dryas: after the review round and before the commit on every orchestrated branch (inside `$dryas:orchestrate`, the finish step runs it after review-receive and calls `log_review` after each round; outside it, the round is logged by `$dryas:wreview`), before every merge, and before reporting an executor's task done. A performance number also passes `<dryas-root>/pstack/benchmark-checklist.md` when pstack picks are on.

## Reference

- When an excuse to skip the gate comes to mind, read `<dryas-root>/skills/verify/reference.md` § Rationalizations.
- When you are unsure what evidence a tests, regression, build, requirements or delegation claim needs, read `<dryas-root>/skills/verify/reference.md` § Key patterns.
