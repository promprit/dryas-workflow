# Plan reference

Read the section the pointer in `SKILL.md` names; nothing here is needed on every turn.

## File structure guidance

- Design units with clear boundaries and well-defined interfaces. Each file has one clear responsibility.
- You reason best about code you can hold in context, and edits are more reliable in focused files. Prefer smaller, focused files over large ones that do too much.
- Files that change together live together. Split by responsibility, not by technical layer.
- In existing codebases, follow established patterns. If the codebase uses large files, do not restructure unilaterally; but if a file you are modifying has grown unwieldy, a split in the plan is reasonable.

## Placeholder patterns

These are plan failures; replace each with the actual content:
- "TBD", "TODO", "implement later", "fill in details".
- "Add appropriate error handling" / "add validation" / "handle edge cases".
- "Write tests for the above" (without the test code).
- "Similar to Task N" (repeat the code: the engineer may read tasks out of order, and an executor sees only its own).
- Steps that say what to do without showing how (code blocks are required for code steps).
- References to types, functions or methods not defined in any task.

## Task fields

- Scope lists the exact files to create, modify and test (globs only where a folder is new); steps name exact paths, with line ranges for modified code.
- Interfaces: an executor sees only its own task, so this block is how it learns the names, parameter and return types its neighbors use.
- Step 1 shows the real test code; Step 2 names the exact command and the expected failure; Step 3 shows the minimal implementation; Step 4 expects PASS; Step 5 commits explicit paths with a conventional message.
- Tasks that may run in parallel have non-overlapping Scope globs; say the order at the end of the file map.
