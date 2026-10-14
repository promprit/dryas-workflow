# Review receive reference

Read the section the pointer in `SKILL.md` names; nothing here is needed on every turn.

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
