# Walkthrough: one feature through the loop

The request: *"Lock accounts after too many failed logins."* The edition is the Claude Code reference implementation. Each step names the layer and the spec rules it satisfies.

## 1. Brainstorm (Governance: WF-2)

The orchestrator asks: per account or per IP? How long? What does the user see? Two approaches are proposed (in-memory counter vs Redis). You pick Redis, per account, 5 tries per 15 minutes, a friendly message on the form. The design is approved. Nothing has been built yet.

## 2. Memory read (Memory: MEM-3)

`memory_search` in the project's namespace returns:

```
Past: rate limiter on /reset-password worked with Redis INCR + EXPIRE
      / failed first time because the key was per request, not per account
```

That line goes into the plan's context.

## 3. Plan (Execution: EXE-1, EXE-2; Governance: GOV-1)

A worktree and branch are created. The orchestrator writes `.orchestrate/PLAN.md` with two tasks, each with its own scope. See [PLAN.md](PLAN.md). Task 2 is UI, so its Done line requires the design pass.

## 4. Judge (Governance: GOV-6)

One `jev_judge` call per task:

| Task | executor | specific | failing_test_exists | needs_opus |
| --- | --- | --- | --- | --- |
| 1 | coder (0.88) | yes (0.81) | no (0.93) | no (0.77) |
| 2 | coder (0.84) | yes (0.79) | no (0.90) | no (0.85) |

No failing tests exist, so testers go first (EXE-4).

## 5. Build (Execution: EXE-3, EXE-7, EXE-8; Governance: GOV-2)

`.orchestrate/active.json` arms the scope lock. Scopes do not overlap, so both tasks run in parallel. Each executor gets only its section.

The Task 2 executor tries to edit `src/ui/theme.ts` to add a warning colour. The scope lock denies it. The executor stops and reports `SCOPE: need src/ui/theme.ts because no warning token exists`. The orchestrator decides the existing error token is fine, and re-dispatches without widening the scope.

## 6. Escalate (Escalation: ESC-2, ESC-4, ESC-5)

Task 1 fails twice on Sonnet: the counter resets on every request. Before climbing, the orchestrator debugs the reports and finds the root cause: the Redis key uses the request id. It is not a plan defect, so the task climbs to Opus with the root cause in its prompt, and the climb is logged ([escalations.jsonl](escalations.jsonl)). Opus fixes it. Fable is never used (ESC-3).

## 7. Review (Review: REV-1 to REV-5)

- Jev's `needs_interrogate` is 0.42 (below 0.7), so no adversarial panel.
- One Sonnet cleanup task removes a leftover debug log.
- `/wreview`: spec compliance passes; code quality flags a magic number, fixed.
- Verification runs both test commands and sees them pass.

## 8. Ship (Review: REV-5; Governance: GOV-5; Memory: MEM-3)

`active.json` is deleted. `/commit` asks Jev "safe to commit?" (0.91 yes) and commits. It does not push: you do. The outcome is stored:

```
Login lockout: Redis per-account key worked. Sonnet failed twice on per-request key
(same mistake as /reset-password) -> consider a shared rate-limit helper.
```

Next time, the memory read will surface that suggestion before planning.
