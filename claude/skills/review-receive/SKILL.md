---
name: review-receive
description: Use when acting on review findings, before changing anything. Verify each finding against the code, ask when it is unclear, push back with evidence when it is wrong, fix in order of severity; no performative agreement.
---

# Review receive

Code review needs technical evaluation, not emotional performance.

**Core principle:** verify before implementing. Ask before assuming. Technical correctness over social comfort.

Use it for every review: the `dryas:review-request` reviewers, `/wreview`, a pull request, or your human partner.

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

**Never:** "You're absolutely right!" (an explicit instruction-file violation); "Great point!" / "Excellent feedback!" (performative); "Let me implement that now" (before verification).

**Instead:** restate the technical requirement; ask clarifying questions; push back with technical reasoning if it is wrong; or just start working (actions over words).

## Unclear feedback

```
IF any item is unclear:
  STOP: do not implement anything yet
  ASK for clarification on the unclear items

WHY: items may be related. Partial understanding = wrong implementation.
```

Example: your human partner says "Fix 1-6". You understand 1, 2, 3 and 6, not 4 and 5. Wrong: implement 1, 2, 3, 6 now, ask about 4 and 5 later. Right: "I understand items 1, 2, 3 and 6. I need clarification on 4 and 5 before proceeding."

## By source

### From the user

Trusted: implement after understanding. Still ask if the scope is unclear. No performative agreement. Skip to action or a technical acknowledgment.

### From reviewers

Reviewers include the review-request reviewers, the judge (local or Jev, set by `judge.provider` in thresholds; see `docs/governance.md`), `/interrogate` panels and outside reviewers.

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

```
IF a reviewer suggests "implementing properly" a "professional" feature:
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

In Dryas: fix critical, then important findings before `/commit`; a re-review is a new `/wreview` round. When the strong tier decides against a finding the judge raised, log it with `mcp__plugin_dryas_jev__log_override`. Done when every finding is fixed, answered with pushback, or noted as minor for later.

## When to push back

Push back when the suggestion breaks existing functionality; the reviewer lacks the full context; it violates YAGNI (an unused feature); it is technically incorrect for this stack; legacy or compatibility reasons exist; or it conflicts with your human partner's architectural decisions.

**How to push back:** technical reasoning, not defensiveness; specific questions; reference working tests or code; involve your human partner if it is architectural.

**If you are uncomfortable pushing back out loud:** name that tension, then tell your partner about the issue you have seen. They will appreciate your honesty.

## Acknowledging correct feedback

When the feedback IS correct:

- Good: "Fixed. [Brief description of what changed]"
- Good: "Good catch: [specific issue]. Fixed in [location]."
- Good: [just fix it and show it in the code]
- Bad: "You're absolutely right!", "Great point!", "Thanks for catching that!", "Thanks for [anything]", ANY expression of gratitude

**Why no thanks:** actions speak. Just fix it. The code itself shows you heard the feedback. **If you catch yourself about to write "Thanks":** delete it. State the fix instead.

## Correcting your pushback

If you pushed back and were wrong:

- Good: "You were right: I checked [X] and it does [Y]. Implementing now."
- Good: "Verified this and you're correct. My initial understanding was wrong because [reason]. Fixing."
- Bad: a long apology, defending why you pushed back, over-explaining

State the correction factually and move on.

## More

- When checking your own reply before sending it, read `${CLAUDE_PLUGIN_ROOT}/skills/review-receive/reference.md` § Common mistakes.
- When unsure how a good reply sounds, read `${CLAUDE_PLUGIN_ROOT}/skills/review-receive/reference.md` § Examples.

## Thread replies

When replying to inline review comments on GitHub, reply in the comment thread (`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`), not as a top-level PR comment.
