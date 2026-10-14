# Upstream coverage: review-receive

Rows follow the grammar in [../UPSTREAM.md](../UPSTREAM.md).

## review-receive

Upstream: `receiving-code-review/`

| Upstream item | Where it lives |
|---|---|
| Code Review Reception | review-receive/SKILL.md § Review receive |
| Overview | review-receive/SKILL.md § Review receive |
| Overview — technical evaluation, not emotional performance | review-receive/SKILL.md § Review receive |
| Overview — core principle: verify before implementing, ask before assuming, correctness over comfort | review-receive/SKILL.md § Review receive |
| The Response Pattern | review-receive/SKILL.md § Response pattern |
| The Response Pattern — 1. read the complete feedback without reacting | review-receive/SKILL.md § Response pattern |
| The Response Pattern — 2. understand: restate in own words, or ask | review-receive/SKILL.md § Response pattern |
| The Response Pattern — 3. verify against codebase reality | review-receive/SKILL.md § Response pattern |
| The Response Pattern — 4. evaluate: sound for THIS codebase | review-receive/SKILL.md § Response pattern |
| The Response Pattern — 5. respond: acknowledgment or reasoned pushback | review-receive/SKILL.md § Response pattern |
| The Response Pattern — 6. implement one item at a time, test each | review-receive/SKILL.md § Response pattern |
| Forbidden Responses | review-receive/SKILL.md § Forbidden responses |
| Forbidden Responses — never: "You're absolutely right!" | review-receive/SKILL.md § Forbidden responses |
| Forbidden Responses — never: "Great point!" / "Excellent feedback!" | review-receive/SKILL.md § Forbidden responses |
| Forbidden Responses — never: "Let me implement that now" before verification | review-receive/SKILL.md § Forbidden responses |
| Forbidden Responses — instead: restate the technical requirement | review-receive/SKILL.md § Forbidden responses |
| Forbidden Responses — instead: ask clarifying questions | review-receive/SKILL.md § Forbidden responses |
| Forbidden Responses — instead: push back with technical reasoning if wrong | review-receive/SKILL.md § Forbidden responses |
| Forbidden Responses — instead: just start working | review-receive/SKILL.md § Forbidden responses |
| Handling Unclear Feedback | review-receive/SKILL.md § Unclear feedback |
| Handling Unclear Feedback — any item unclear: stop, implement nothing, ask | review-receive/SKILL.md § Unclear feedback |
| Handling Unclear Feedback — why: items may be related | review-receive/SKILL.md § Unclear feedback |
| Handling Unclear Feedback — example: fix 1-6, unclear on 4 and 5 | review-receive/SKILL.md § Unclear feedback |
| Source-Specific Handling | review-receive/SKILL.md § By source |
| From your human partner | review-receive/SKILL.md § From the user |
| From your human partner — trusted: implement after understanding | review-receive/SKILL.md § From the user |
| From your human partner — still ask if scope is unclear | review-receive/SKILL.md § From the user |
| From your human partner — no performative agreement | review-receive/SKILL.md § From the user |
| From your human partner — skip to action or technical acknowledgment | review-receive/SKILL.md § From the user |
| From External Reviewers | review-receive/SKILL.md § From reviewers |
| From External Reviewers — Dryas reviewers: review-request reviewer, judge, interrogate panels (Dryas) | review-receive/SKILL.md § From reviewers |
| From External Reviewers — check 1: technically correct for THIS codebase | review-receive/SKILL.md § From reviewers |
| From External Reviewers — check 2: breaks existing functionality | review-receive/SKILL.md § From reviewers |
| From External Reviewers — check 3: reason for current implementation | review-receive/SKILL.md § From reviewers |
| From External Reviewers — check 4: works on all platforms and versions | review-receive/SKILL.md § From reviewers |
| From External Reviewers — check 5: reviewer understands full context | review-receive/SKILL.md § From reviewers |
| From External Reviewers — seems wrong: push back with technical reasoning | review-receive/SKILL.md § From reviewers |
| From External Reviewers — can't easily verify: say so and ask | review-receive/SKILL.md § From reviewers |
| From External Reviewers — conflicts with partner's prior decisions: stop and discuss | review-receive/SKILL.md § From reviewers |
| From External Reviewers — partner's rule: be skeptical, but check carefully | review-receive/SKILL.md § From reviewers |
| YAGNI Check for "Professional" Features | review-receive/SKILL.md § YAGNI check |
| YAGNI Check for "Professional" Features — grep for actual usage; unused: propose removal; used: implement properly | review-receive/SKILL.md § YAGNI check |
| YAGNI Check for "Professional" Features — partner's rule: if we don't need it, don't add it | review-receive/SKILL.md § YAGNI check |
| Implementation Order | review-receive/SKILL.md § Order of fixes |
| Implementation Order — 1. clarify anything unclear first | review-receive/SKILL.md § Order of fixes |
| Implementation Order — 2. blocking issues, then simple fixes, then complex fixes | review-receive/SKILL.md § Order of fixes |
| Implementation Order — 3. test each fix individually | review-receive/SKILL.md § Order of fixes |
| Implementation Order — 4. verify no regressions | review-receive/SKILL.md § Order of fixes; verify/SKILL.md § Verify |
| Implementation Order — critical then important before commit; re-review is a new wreview round; log_override (Dryas) | review-receive/SKILL.md § Order of fixes |
| When To Push Back | review-receive/SKILL.md § When to push back |
| When To Push Back — breaks existing functionality | review-receive/SKILL.md § When to push back |
| When To Push Back — reviewer lacks full context | review-receive/SKILL.md § When to push back |
| When To Push Back — violates YAGNI | review-receive/SKILL.md § When to push back |
| When To Push Back — technically incorrect for this stack | review-receive/SKILL.md § When to push back |
| When To Push Back — legacy or compatibility reasons | review-receive/SKILL.md § When to push back |
| When To Push Back — conflicts with partner's architectural decisions | review-receive/SKILL.md § When to push back |
| When To Push Back — how: technical reasoning, specific questions, working tests or code, involve partner if architectural | review-receive/SKILL.md § When to push back |
| When To Push Back — uncomfortable pushing back: name the tension, tell your partner | review-receive/SKILL.md § When to push back |
| Acknowledging Correct Feedback | review-receive/SKILL.md § Acknowledging correct feedback |
| Acknowledging Correct Feedback — good: "Fixed. ...", "Good catch ...", just fix it | review-receive/SKILL.md § Acknowledging correct feedback |
| Acknowledging Correct Feedback — bad: "You're absolutely right!", "Great point!", any thanks or gratitude | review-receive/SKILL.md § Acknowledging correct feedback |
| Acknowledging Correct Feedback — why no thanks: actions speak | review-receive/SKILL.md § Acknowledging correct feedback |
| Acknowledging Correct Feedback — about to write "Thanks": delete it, state the fix | review-receive/SKILL.md § Acknowledging correct feedback |
| Gracefully Correcting Your Pushback | review-receive/SKILL.md § Correcting your pushback |
| Gracefully Correcting Your Pushback — good: "You were right ...", "Verified this ..." | review-receive/SKILL.md § Correcting your pushback |
| Gracefully Correcting Your Pushback — bad: long apology, defending, over-explaining | review-receive/SKILL.md § Correcting your pushback |
| Gracefully Correcting Your Pushback — state the correction factually and move on | review-receive/SKILL.md § Correcting your pushback |
| Common Mistakes | review-receive/SKILL.md § Common mistakes |
| Common Mistakes — performative agreement | review-receive/SKILL.md § Common mistakes |
| Common Mistakes — blind implementation | review-receive/SKILL.md § Common mistakes |
| Common Mistakes — batch without testing | review-receive/SKILL.md § Common mistakes |
| Common Mistakes — assuming reviewer is right | review-receive/SKILL.md § Common mistakes |
| Common Mistakes — avoiding pushback | review-receive/SKILL.md § Common mistakes |
| Common Mistakes — partial implementation | review-receive/SKILL.md § Common mistakes |
| Common Mistakes — can't verify, proceed anyway | review-receive/SKILL.md § Common mistakes |
| Real Examples | review-receive/SKILL.md § Examples |
| Real Examples — performative agreement (bad) | review-receive/SKILL.md § Examples |
| Real Examples — technical verification (good) | review-receive/SKILL.md § Examples |
| Real Examples — YAGNI (good) | review-receive/SKILL.md § Examples |
| Real Examples — unclear item (good) | review-receive/SKILL.md § Examples |
| GitHub Thread Replies | review-receive/SKILL.md § Thread replies |
| GitHub Thread Replies — reply in the comment thread, not top-level | review-receive/SKILL.md § Thread replies |
