# Review model

**Purpose:** prove the work before it merges, and keep shipping a human act.

## Rules

1. **Review is mandatory.** No multi-step change merges without review.
2. **Two stages, in order.**
   1. *Spec compliance:* does the diff do what the approved design and plan said, and nothing else?
   2. *Code quality:* is it correct, minimal, tested and readable?
3. **Verification before completion.** Tests named in the done criteria are run and seen to pass before anything is called done. A claimed pass that was not observed is a failure.
4. **Adversarial review for contested work.** Architectural or contested changes get a two-model panel; a lead judges, and accepted findings become new tasks.
5. **Cleanup pass.** After the build, one cheap task removes slop and stale comments from the files the diff touched, and tests rerun. Docs-only diffs skip it.
6. **Measured claims are vetted.** A performance number is checked against a benchmark checklist before it is reported.
7. **Commit is gated, push is human.** The commit step asks the judge "safe to commit?" and the orchestrator decides below threshold. Agents commit; they never push, release or publish without a human.
8. **Merge order.** Review, then verification, then merge. Never the other way round.

## Review checklist

- Does every changed file fall inside some task's scope?
- Does every done criterion have a test that was run?
- Is there anything in the diff the design did not ask for?
- Did any escalation happen, and is its root cause addressed?
- Is anything outward-facing (push, release, settings) waiting on a human?

## Reference binding

`/wreview` (two-stage), `superpowers:verification-before-completion`, `/interrogate` (pstack picks, gated by the judge's `needs_interrogate`), the pstack cleanup task, `/benchmark-checklist`, `/commit` (Jev-gated, never pushes). Details: [workflow.md §4 steps 8b–9](workflow.md).
