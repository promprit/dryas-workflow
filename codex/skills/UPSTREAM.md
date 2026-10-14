# Upstream

The process skills in this folder (`brainstorm`, `worktree`, `debug`, `verify`, `plan`, `review-request`, `review-receive`, `tdd`) are rewritten from [Superpowers](https://github.com/obra/superpowers) 6.4.1 at `5bf4e78011075bcfc0dc295f0724994cd123ee71` (MIT, (c) 2025 Jesse Vincent; license text: [LICENSE-superpowers](LICENSE-superpowers)). Upstream paths are relative to `skills/` there.

Rewrites may shorten wording, never drop a rule. Each skill's `UPSTREAM.md` maps every heading, step, rule, red flag, rationalization and checklist item of the upstream skill, and every upstream file, to where it lives here. Targets: `<skill>/<file>.md § <heading>`, `template: "<phrase>"`, `executor: "<phrase>"`, `orchestrate: "<phrase>"`, or `extra:superpowers` (Node-based tools, upstream self-tests and authoring history, which stay available by installing Superpowers as an optional extra). Several targets are separated by `; `. `install/tests/test_process_skills.py` checks every target, and that every upstream heading and file has a row, against the committed outline `install/tests/fixtures/superpowers-6.4.1-outline.json` (compared with the live upstream wherever Superpowers 6.4.1 is installed).

To update: diff the upstream skills at the new commit against the one above, carry each change into the Dryas skill and its rows, then change the commit here.

| Dryas skill | Upstream | Used by |
|---|---|---|
| [`brainstorm`](brainstorm/UPSTREAM.md) | `brainstorming/` | orchestrate, always first |
| [`worktree`](worktree/UPSTREAM.md) | `using-git-worktrees/` | orchestrate |
| [`debug`](debug/UPSTREAM.md) | `systematic-debugging/` | orchestrate, executor |
| [`verify`](verify/UPSTREAM.md) | `verification-before-completion/` | orchestrate, commit, merge |
| [`plan`](plan/UPSTREAM.md) | `writing-plans/` | wplan |
| [`review-request`](review-request/UPSTREAM.md) | `requesting-code-review/` | wreview |
| [`review-receive`](review-receive/UPSTREAM.md) | `receiving-code-review/` | wreview |
| [`tdd`](tdd/UPSTREAM.md) | (executor test-first practice), `test-driven-development/` | executor |
