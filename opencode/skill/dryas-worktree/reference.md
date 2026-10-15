# Worktree reference

Read the section the pointer in `SKILL.md` names; nothing here is needed on every turn.

## Quick reference

| Situation | Action |
|---|---|
| Already in a linked worktree | Skip creation (Detect existing isolation) |
| In a submodule | Treat as a normal repo (submodule guard) |
| Native worktree tool available | Use it |
| No native tool | Git fallback |
| `.worktrees/` exists | Use it (check it is ignored) |
| `worktrees/` exists | Use it (check it is ignored) |
| Both exist | Use `.worktrees/` |
| Neither exists | Check the instructions, then default `.worktrees/` |
| Directory not ignored | Add to `.gitignore` and commit |
| Permission error on create | Sandbox fallback: work in place |
| Tests fail at baseline | Report failures and ask |
| No package manifest | Skip dependency install |
| Another session works in this worktree | Create your own worktree and branch |

## Common rationalizations

| Excuse | Reality |
|---|---|
| "I'm obviously not in a worktree, no need to check" | Run the detection. Harness-created isolation and submodules both fool eyeballing; the commands settle it. |
| "`git worktree add` is quicker than looking for a native tool" | A native tool owns placement, branching and cleanup. Bypassing it is the most common mistake: it creates phantom state the harness cannot see or manage. |
| "The worktree directory is surely ignored already" | Run `git check-ignore`. An unignored worktree directory commits the whole tree into the repo. |
| "Any directory name works" | Explicit instructions beat an existing project-local directory, which beats the `.worktrees/` default. |
| "The workspace is fresh, baseline tests can wait" | A dirty baseline makes every later failure ambiguous. Run the tests now; proceeding past failures is your human partner's call. |
| "That worktree is free right now, I'll share it" | One agent per worktree. Make your own. |
