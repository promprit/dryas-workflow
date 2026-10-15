---
description: "Session retrospective - propose environment improvements by severity; proposes, never applies. Use for /retro."
---
<!-- dryas-managed -->
1. **Input.** The current session, or the session or transcript path the user names.
2. **Read** the transcript for friction, in these categories:
   - **navigation**: files or facts the agent struggled to find;
   - **automated checks**: mistakes a test, lint or hook could have caught;
   - **instruction lines** that changed nothing;
   - **tool cost**: slow or expensive calls and repeated reads;
   - **information access**: missing docs, credentials or tools.
3. **Output** one list ordered by severity. Each item gives: category, evidence (a quote or file:line), proposed change, and kind. Kind is `check` when the rule is mechanical (for example the scope lock, or `tools/inventory.py`) and `prose` only for a judgement call.
4. **The rule:** a mechanical rule becomes a deterministic check, and only judgement calls stay as prose.
5. **Proposes, never applies.** Ask which items the user accepts. Accepted items go into a plan (`/wplan`), not into edits now.
6. **Store** each accepted lesson with `jev_memory_store` on server `jev`, kind "retro", title = the lesson in one line, body = evidence and the agreed change. `jev_memory_search` surfaces it before the next task.
7. **Point to `GLOSSARY.md`** for terms.

Arguments: $ARGUMENTS
