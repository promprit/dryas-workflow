# Upstream

Source: https://github.com/michael-denyer/pstack-claude at `dc8e617f179cf0bdc68b61e672f33e9eb64c20cf`. Paths are relative to `plugins/pstack/` there.

To update: check out the new upstream commit, diff each upstream path below against it, re-apply the listed edits, and change the commit above.

| File here | Upstream path | Edits |
|---|---|---|
| `interrogate/reviewer-prompt.md` | `skills/interrogate/references/reviewer-prompt.md` | none |
| `interrogate/rubric.md` | `skills/interrogate/references/rubric.md` | none |
| `interrogate/code-quality-review.md` | `skills/interrogate/references/code-quality-review.md` | none |
| `interrogate/lead-judgment.md` | `skills/interrogate/references/lead-judgment.md` | none |
| `principles/fix-root-causes.md` | `skills/principle-fix-root-causes/SKILL.md` | frontmatter removed |
| `principles/prove-it-works.md` | `skills/principle-prove-it-works/SKILL.md` | frontmatter removed; show-me-your-work reference removed |
| `principles/subtract-before-you-add.md` | `skills/principle-subtract-before-you-add/SKILL.md` | frontmatter removed |
| `principles/test-behavior-not-implementation.md` | `skills/principle-test-behavior-not-implementation/SKILL.md` | frontmatter removed |
| `principles/guard-the-context-window.md` | `skills/principle-guard-the-context-window/SKILL.md` | frontmatter removed |
| `benchmark-checklist.md` | `skills/benchmark-checklist/SKILL.md` | frontmatter removed; Explain-the-Number link replaced by one sentence; Opening-a-PR playbook reference removed; "How this fits" section removed |
| `cleanup.md` | `skills/deslop/SKILL.md` (Pass 1), `agents/comment-sicko.md` keep-list (Pass 2) | Pass 1 verbatim except "main" became "the base branch"; Pass 2 rewritten: persona, agent, `/how` `/why` `/architect` calls and kill flags removed; unverifiable constraints are kept and reported; Pass 2 limited to comments added or changed in the diff |

Not taken: `poteto-mode` and its hooks, `why`, `how`, `architect`, `arena`, `swarm`, `tdd`, `babysit`, the `no-comments` skill, the `comment-sicko` agent, `setup-pstack`, `models.json`, the other principles.
