---
name: interrogate
description: Adversarial review of a finished change by two reviewers on different models, then a lead verdict. Runs from the orchestrate skill's gated interrogate step or when the user types /interrogate. Not for routine review; /wreview covers that.
disable-model-invocation: true
---

# Interrogate

Two reviewers on different models challenge one change. The signal comes from model diversity, not personas. The deliverable is a verdict. Change nothing yourself.

## 1. Scope

Default: the diff from the merge-base with the default branch to HEAD, plus uncommitted changes in the worktree. Use the files or diff the user names instead, if any. Note the context files a reviewer needs to understand the change.

## 2. Intent

Write one paragraph stating the intent, from the approved design or spec, the PLAN.md goals and the commit messages. If you are unsure of the intent, ask the user before going on.

## 3. Reviewers

Read `{{CD}}/pstack/interrogate/reviewer-prompt.md` and fill it with the intent, the diff (or the exact command that prints it), `{{CD}}/pstack/interrogate/rubric.md` and `{{CD}}/pstack/interrogate/code-quality-review.md`. Both reviewers get the same filled prompt.

Inside `/orchestrate`, dispatch only after every build task has left `.orchestrate/active.json`. Add one section per reviewer to `.orchestrate/PLAN.md`:

```
## Task <N>: interrogate reviewer <A|B>
Goal: Adversarial review of the change; report findings only.
Scope:
(none: read-only review)
Done:
- Findings returned in the reviewer-prompt output format
Failing test first: none (review)
```

Put both ids in `.orchestrate/active.json`. The empty Scope makes the scope lock deny every edit. Dispatch both in one message with `subagent_type: executor`: reviewer A on the executor's default model, reviewer B on the next model on the ladder (the orchestrate skill names it), never the top rung. Remove both ids when they return.

Outside `/orchestrate`, dispatch the same two reviewers with "Do not edit any file" at the top of the prompt.

## 4. Synthesize

1. Parse all findings.
2. Consensus: a finding both reviewers raised independently is the highest signal.
3. Lone findings: still read them, weight them lower.
4. Deduplicate: merge findings that describe the same issue; note who raised it.
5. Disagreements: when one reviewer flags something the other explicitly clears, record both.

## 5. Lead judgment

You are the lead reviewer. Read `{{CD}}/pstack/interrogate/lead-judgment.md` and put every finding in one bucket: **Act on**, **Consider**, **Noted** or **Dismissed**, each with the reviewer(s) who raised it and a one-line rationale.

## Output

### Intent
> the paragraph from step 2

### Reviewers
- Reviewer A: default model, N findings
- Reviewer B: next model on the ladder, N findings

### Act On
### Consider
### Noted
### Dismissed
### Agreement Map

## After the verdict (inside `/orchestrate`)

Each Act On finding becomes a new PLAN.md task and goes through the TDD gate and dispatch like any task. Consider items go to the user in the final report.
