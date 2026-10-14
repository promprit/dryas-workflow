---
name: review-receive
description: Use when acting on review findings, before changing anything. Verify each finding against the code, ask when it is unclear, push back with evidence when it is wrong, fix in order of severity; no performative agreement.
---

# Review receive

Code review needs technical evaluation, not emotional performance.

**Core principle:** verify before implementing. Ask before assuming. Technical correctness over social comfort.

Use it for every review: the `$dryas:review-request` reviewer, `$dryas:wreview`, a pull request, or your human partner.

## Response pattern

```
WHEN receiving code review feedback:

1. READ: the complete feedback without reacting
2. UNDERSTAND: restate the requirement in your own words (or ask)
3. VERIFY: check it against the codebase as it is
4. EVALUATE: technically sound for THIS codebase?
5. RESPOND: technical acknowledgment or reasoned pushback
6. IMPLEMENT: one item at a time, test each
```

## Forbidden responses

**Never:**
- "You're absolutely right!" (an explicit instruction-file violation)
- "Great point!" / "Excellent feedback!" (performative)
- "Let me implement that now" (before verification)

**Instead:**
- Restate the technical requirement
- Ask clarifying questions
- Push back with technical reasoning if it is wrong
- Just start working (actions over words)

## Unclear feedback

```
IF any item is unclear:
  STOP: do not implement anything yet
  ASK for clarification on the unclear items

WHY: items may be related. Partial understanding = wrong implementation.
```

Example: your human partner says "Fix 1-6". You understand 1, 2, 3 and 6, not 4 and 5.
- Wrong: implement 1, 2, 3, 6 now, ask about 4 and 5 later.
- Right: "I understand items 1, 2, 3 and 6. I need clarification on 4 and 5 before proceeding."

## By source

### From the user

- **Trusted:** implement after understanding
- **Still ask** if the scope is unclear
- **No performative agreement**
- **Skip to action** or a technical acknowledgment

### From reviewers

Reviewers include the review-request reviewer, the judge (local or Jev, set by `judge.provider` in thresholds; see `docs/governance.md`), `$dryas:interrogate` panels and outside reviewers.

```
BEFORE implementing:
  1. Check: technically correct for THIS codebase?
  2. Check: does it break existing functionality?
  3. Check: is there a reason for the current implementation?
  4. Check: does it work on all platforms and versions?
  5. Check: does the reviewer understand the full context?

IF the suggestion seems wrong:
  push back with technical reasoning

IF you cannot easily verify it:
  say so: "I can't verify this without [X]. Should I [investigate/ask/proceed]?"

IF it conflicts with your human partner's prior decisions:
  stop and discuss with your human partner first
```

**Your human partner's rule:** "External feedback: be skeptical, but check carefully."

## YAGNI check

For "professional" features:

```
IF a reviewer suggests "implementing properly":
  grep the codebase for actual usage

  IF unused: "This endpoint isn't called. Remove it (YAGNI)?"
  IF used: then implement it properly
```

**Your human partner's rule:** "You and the reviewer both report to me. If we don't need this feature, don't add it."

## Order of fixes

```
FOR multi-item feedback:
  1. Clarify anything unclear FIRST
  2. Then implement in this order:
     - Blocking issues (breaks, security)
     - Simple fixes (typos, imports)
     - Complex fixes (refactoring, logic)
  3. Test each fix individually
  4. Verify no regressions
```

In Dryas: fix critical, then important findings before `$dryas:commit`; a re-review is a new `$dryas:wreview` round. When the strong tier decides against a finding the judge raised, log it with `log_override`.

## When to push back

Push back when:
- The suggestion breaks existing functionality
- The reviewer lacks the full context
- It violates YAGNI (an unused feature)
- It is technically incorrect for this stack
- Legacy or compatibility reasons exist
- It conflicts with your human partner's architectural decisions

**How to push back:**
- Use technical reasoning, not defensiveness
- Ask specific questions
- Reference working tests or code
- Involve your human partner if it is architectural

**If you are uncomfortable pushing back out loud:** name that tension, then tell your partner about the issue you have seen. They will appreciate your honesty.

## Acknowledging correct feedback

When the feedback IS correct:

- Good: "Fixed. [Brief description of what changed]"
- Good: "Good catch: [specific issue]. Fixed in [location]."
- Good: [just fix it and show it in the code]
- Bad: "You're absolutely right!"
- Bad: "Great point!"
- Bad: "Thanks for catching that!"
- Bad: "Thanks for [anything]"
- Bad: ANY expression of gratitude

**Why no thanks:** actions speak. Just fix it. The code itself shows you heard the feedback.

**If you catch yourself about to write "Thanks":** delete it. State the fix instead.

## Correcting your pushback

If you pushed back and were wrong:

- Good: "You were right: I checked [X] and it does [Y]. Implementing now."
- Good: "Verified this and you're correct. My initial understanding was wrong because [reason]. Fixing."
- Bad: a long apology
- Bad: defending why you pushed back
- Bad: over-explaining

State the correction factually and move on.

## Common mistakes

| Mistake | Fix |
|---|---|
| Performative agreement | State the requirement or just act |
| Blind implementation | Verify against the codebase first |
| Batch without testing | One at a time, test each |
| Assuming the reviewer is right | Check whether it breaks things |
| Avoiding pushback | Technical correctness over comfort |
| Partial implementation | Clarify all items first |
| Cannot verify, proceed anyway | State the limitation, ask for direction |

## Examples

**Performative agreement (bad):**
```
Reviewer: "Remove legacy code"
Bad: "You're absolutely right! Let me remove that..."
```

**Technical verification (good):**
```
Reviewer: "Remove legacy code"
Good: "Checking... build target is 10.15+, this API needs 13+. Need legacy for backward compat. Current impl has wrong bundle ID - fix it or drop pre-13 support?"
```

**YAGNI (good):**
```
Reviewer: "Implement proper metrics tracking with database, date filters, CSV export"
Good: "Grepped codebase - nothing calls this endpoint. Remove it (YAGNI)? Or is there usage I'm missing?"
```

**Unclear item (good):**
```
Your human partner: "Fix items 1-6"
You understand 1,2,3,6. Unclear on 4,5.
Good: "Understand 1,2,3,6. Need clarification on 4 and 5 before implementing."
```

## Thread replies

When replying to inline review comments on GitHub, reply in the comment thread (`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`), not as a top-level PR comment.
