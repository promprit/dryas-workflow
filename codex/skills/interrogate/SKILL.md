---
name: interrogate
description: Adversarial review of a finished change by two reviewers on different models, then a lead verdict. Use for $interrogate or the gated interrogate step of $orchestrate; not for routine review ($wreview covers that).
---

# Interrogate (Codex)

1. **Scope.** The diff from the merge-base with the default branch to HEAD plus uncommitted changes, or what the user names.
2. **Intent.** One paragraph from the approved design, the plan goals and the commit messages. Unsure: ask the user.
3. **Reviewers.** Fill `{{CD}}/pstack/interrogate/reviewer-prompt.md` with the intent, the diff, `{{CD}}/pstack/interrogate/rubric.md` and `{{CD}}/pstack/interrogate/code-quality-review.md`. Inside `$orchestrate`, start only after every build task has left `.orchestrate/active.json`. Add one plan section per reviewer, each with this shape:

```
Scope:
(none: read-only review)
Failing test first: none (review)
```

Put both ids in `.orchestrate/active.json` so the scope-lock hook denies every edit, and remove them when the reviewers return. Run two Codex sub-agents with the same prompt: one on a cheaper model, one on a stronger model. They never edit files. Without sub-agents, run one review pass yourself with that prompt and say so in the verdict.
4. **Synthesize.** Consensus findings first, lone findings weighted lower, duplicates merged, disagreements recorded.
5. **Lead judgment.** Follow `{{CD}}/pstack/interrogate/lead-judgment.md`. Buckets: Act On, Consider, Noted, Dismissed, each with who raised it and a one-line reason. End with an Agreement Map.
6. Change nothing. Inside `$orchestrate`, each Act On item becomes a new plan task.
