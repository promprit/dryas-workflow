# Cleanup

Run on the files in your Scope after the build tasks pass and before review. Two passes: slop, then comments. Keep behavior unchanged. Run the test command in your Done criteria before you report.

## Pass 1: remove AI code slop

Check the diff against the base branch and remove AI-generated slop introduced in the branch.

### Focus Areas

- Extra comments that are unnecessary or inconsistent with local style
- Defensive checks or try/catch blocks that are abnormal for trusted code paths
- Casts to `any` used only to bypass type issues
- Deeply nested code that should be simplified with early returns
- Other patterns inconsistent with the file and surrounding codebase

### Guardrails

- Keep behavior unchanged unless fixing a clear bug.
- Prefer minimal, focused edits over broad rewrites.
- Keep the final summary concise (1-3 sentences).

## Pass 2: comments

Delete every comment added or changed in the diff against the base branch that is not on this keep-list. Leave older comments alone:

- Legal or license headers.
- Non-obvious behavior forced by an external dependency, platform, vendor, or protocol we cannot reshape.
- `// prettier-ignore`. Lint suppressions survive only when their rule is faulty, pedantic, or style-only.
- Doc comments that define a public API contract.
- Issue or RFC links that explain a constraint code cannot express.

Rules:

- A comment that explains a surprise in our own code is deleted. Name the symbol under UNRESOLVED as a refactor target (rename, extract, type) that would make the behavior obvious. Do not do that refactor here.
- A suppression (`eslint-disable`, `@ts-ignore`, `@ts-expect-error`, `# noqa`, `# type: ignore`) whose rule protects correctness or safety is a finding, not a keep. Leave it and report it under UNRESOLVED.
- A comment that claims a constraint (`IMPORTANT`, `do not remove`, `talk to X before changing`) stays only if nearby code or `git log -S '<text>'` shows the constraint is real and foreign. If you cannot check it, keep the comment and report it under UNRESOLVED. Never invent a reason.
- Touch comments only. Never change application code in this pass.

Report: files touched, comments deleted, comments kept with the keep-list reason, and UNRESOLVED items.
