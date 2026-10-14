# Upstream coverage: worktree

Rows follow the grammar in [../UPSTREAM.md](../UPSTREAM.md).

## worktree

Upstream: `using-git-worktrees/`

| Upstream item | Where it lives |
|---|---|
| Overview | worktree/SKILL.md § Worktree |
| Overview — isolated workspace; native tools first, git fallback | worktree/SKILL.md § Worktree |
| Overview — core principle: detect, then native, then git; never fight the harness | worktree/SKILL.md § Worktree |
| Overview — announce at start | worktree/SKILL.md § Worktree |
| Overview — one agent per worktree (Dryas) | worktree/SKILL.md § Worktree; template: "One agent per worktree"; orchestrate: "One agent per worktree: this session owns it alone." |
| Step 0: Detect Existing Isolation | worktree/SKILL.md § Detect existing isolation |
| Step 0: Detect Existing Isolation — check before creating anything (git-dir, git-common-dir, branch) | worktree/SKILL.md § Detect existing isolation |
| Step 0: Detect Existing Isolation — submodule guard | worktree/SKILL.md § Detect existing isolation |
| Step 0: Detect Existing Isolation — already in a linked worktree: skip creation | worktree/SKILL.md § Detect existing isolation |
| Step 0: Detect Existing Isolation — report on a branch | worktree/SKILL.md § Detect existing isolation |
| Step 0: Detect Existing Isolation — report on detached HEAD | worktree/SKILL.md § Detect existing isolation |
| Step 0: Detect Existing Isolation — normal checkout: honor a declared preference, else ask consent | worktree/SKILL.md § Detect existing isolation; template: "Every multi-step task runs in its own git worktree" |
| Step 0: Detect Existing Isolation — declined: work in place | worktree/SKILL.md § Detect existing isolation |
| Step 1: Create Isolated Workspace | worktree/SKILL.md § Create the worktree |
| Step 1: Create Isolated Workspace — two mechanisms, in order | worktree/SKILL.md § Create the worktree |
| 1a. Native Worktree Tools (preferred) | worktree/SKILL.md § Create the worktree |
| 1a. Native Worktree Tools (preferred) — use the native tool if present (EnterWorktree on Claude) | worktree/SKILL.md § Create the worktree; worktree/SKILL.md § Worktree |
| 1a. Native Worktree Tools (preferred) — the git fallback beside a native tool creates phantom state | worktree/SKILL.md § Create the worktree |
| 1a. Native Worktree Tools (preferred) — fallback only without a native tool | worktree/SKILL.md § Create the worktree |
| 1b. Git Worktree Fallback | worktree/SKILL.md § Create the worktree |
| 1b. Git Worktree Fallback — Directory Selection: explicit preference beats filesystem state | worktree/SKILL.md § Create the worktree |
| 1b. Git Worktree Fallback — Directory Selection 1. declared directory preference | worktree/SKILL.md § Create the worktree |
| 1b. Git Worktree Fallback — Directory Selection 2. existing .worktrees or worktrees; .worktrees wins | worktree/SKILL.md § Create the worktree |
| 1b. Git Worktree Fallback — Directory Selection 3. default .worktrees/ | worktree/SKILL.md § Create the worktree |
| 1b. Git Worktree Fallback — Safety Verification: a project-local directory must be ignored | worktree/SKILL.md § Create the worktree |
| 1b. Git Worktree Fallback — Safety Verification: not ignored, add to .gitignore and commit | worktree/SKILL.md § Create the worktree |
| 1b. Git Worktree Fallback — Safety Verification: why critical | worktree/SKILL.md § Create the worktree |
| 1b. Git Worktree Fallback — Create the Worktree: add with a new branch, cd into it | worktree/SKILL.md § Create the worktree |
| 1b. Git Worktree Fallback — Sandbox fallback: say so, work in place | worktree/SKILL.md § Create the worktree |
| Step 2: Project Setup | worktree/SKILL.md § Project setup |
| Step 2: Project Setup — Node.js, Rust, Python, Go setup commands | worktree/SKILL.md § Project setup |
| Step 3: Verify Clean Baseline | worktree/SKILL.md § Clean baseline |
| Step 3: Verify Clean Baseline — run the project's tests | worktree/SKILL.md § Clean baseline |
| Step 3: Verify Clean Baseline — tests fail: report and ask | worktree/SKILL.md § Clean baseline |
| Step 3: Verify Clean Baseline — tests pass: report ready | worktree/SKILL.md § Clean baseline |
| Report | worktree/SKILL.md § Report |
| Report — path, test count, ready to implement | worktree/SKILL.md § Report |
| Quick Reference | worktree/SKILL.md § Quick reference |
| Quick Reference — already in linked worktree | worktree/SKILL.md § Quick reference |
| Quick Reference — in a submodule | worktree/SKILL.md § Quick reference |
| Quick Reference — native worktree tool available | worktree/SKILL.md § Quick reference |
| Quick Reference — no native tool | worktree/SKILL.md § Quick reference |
| Quick Reference — .worktrees/ exists | worktree/SKILL.md § Quick reference |
| Quick Reference — worktrees/ exists | worktree/SKILL.md § Quick reference |
| Quick Reference — both exist | worktree/SKILL.md § Quick reference |
| Quick Reference — neither exists | worktree/SKILL.md § Quick reference |
| Quick Reference — directory not ignored | worktree/SKILL.md § Quick reference |
| Quick Reference — permission error on create | worktree/SKILL.md § Quick reference |
| Quick Reference — tests fail during baseline | worktree/SKILL.md § Quick reference |
| Quick Reference — no package.json/Cargo.toml | worktree/SKILL.md § Quick reference |
| Common Rationalizations | worktree/SKILL.md § Common rationalizations |
| Common Rationalizations — "I'm obviously not in a worktree" | worktree/SKILL.md § Common rationalizations |
| Common Rationalizations — "the git fallback is quicker than hunting for a native tool" | worktree/SKILL.md § Common rationalizations |
| Common Rationalizations — "The worktree directory is surely ignored already" | worktree/SKILL.md § Common rationalizations |
| Common Rationalizations — "Any directory name works" | worktree/SKILL.md § Common rationalizations |
| Common Rationalizations — "The workspace is fresh, baseline tests can wait" | worktree/SKILL.md § Common rationalizations |
