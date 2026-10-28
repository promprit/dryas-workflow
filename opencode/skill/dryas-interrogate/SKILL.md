---
name: dryas-interrogate
description: "Adversarial review of a finished change by two reviewers on different tiers, then a lead verdict. Runs from the orchestrate skill's gated interrogate step or when the user types /interrogate. Not for routine review; /wreview covers that."
---
<!-- dryas-managed -->
# Interrogate (OpenCode)

If the Dryas rules say pstack-picks is not installed, say so and stop. Change nothing yourself; the deliverable is a verdict.

1. **Scope.** The diff from the merge-base with the default branch to HEAD plus uncommitted changes, or what the user names.
2. **Intent.** One paragraph from the approved design or spec, the plan goals and the commit messages. Unsure: ask the user.
3. **Reviewers.** Fill `<dryas-root>/pstack/interrogate/reviewer-prompt.md` with the intent, the diff (or the command that prints it), `<dryas-root>/pstack/interrogate/rubric.md` and `<dryas-root>/pstack/interrogate/code-quality-review.md`. Each reviewer's subagent dispatch description starts with `devils-advocate: ` (for example `devils-advocate: interrogate A`). Inside `/orchestrate`, start only after every build task has left `.orchestrate/active.json`, and add one section per reviewer to `.orchestrate/PLAN.md`:

   ```
   ## Task <N>: interrogate reviewer <A|B>
   Goal: Adversarial review of the change; report findings only.
   Scope:
   (none: read-only review)
   Done:
   - Findings returned in the reviewer-prompt output format
   Failing test first: none (review)
   ```

   Put both ids in `.orchestrate/active.json`; the empty Scope makes the scope lock deny every edit. Dispatch both with the task tool in one message: reviewer A as `dryas-executor-standard`, reviewer B as `dryas-executor-strong`. Never the frontier tier. Remove both ids when they return. Outside `/orchestrate`, dispatch the same two with "Do not edit any file" at the top of the prompt.
4. **Synthesize.** Consensus findings first, lone findings weighted lower, duplicates merged with who raised them, disagreements recorded.
5. **Lead judgment.** Follow `<dryas-root>/pstack/interrogate/lead-judgment.md`: every finding goes in Act on, Consider, Noted or Dismissed, with who raised it and a one-line reason. End with an Agreement Map. Inside `/orchestrate`, each Act on item becomes a new plan task.
