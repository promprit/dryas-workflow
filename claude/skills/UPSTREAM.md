# Upstream

The process skills in this folder (`brainstorm`, `worktree`, `debug`, `verify`, `plan`, `review-request`, `review-receive`, `tdd`) are rewritten from [Superpowers](https://github.com/obra/superpowers) 6.4.1 at `5bf4e78011075bcfc0dc295f0724994cd123ee71` (MIT, (c) 2025 Jesse Vincent; license text: [LICENSE-superpowers](LICENSE-superpowers)). Upstream paths are relative to `skills/` there.

Rewrites may shorten wording, never drop a rule. Each section below maps every heading, step, rule, red flag, rationalization and checklist item of the upstream skill, and every upstream file, to where it lives here. Targets: `<skill>/<file>.md § <heading>`, `template: "<phrase>"`, `executor: "<phrase>"`, `orchestrate: "<phrase>"`, or `extra:superpowers` (Node-based tools, upstream self-tests and authoring history, which stay available by installing Superpowers as an optional extra). Several targets are separated by `; `. `install/tests/test_process_skills.py` checks every target, and, where Superpowers 6.4.1 is installed, that every upstream heading and file has a row.

To update: diff the upstream skills at the new commit against the one above, carry each change into the Dryas skill and its rows, then change the commit here.

| Dryas skill | Upstream | Used by |
|---|---|---|
| `brainstorm` | `brainstorming/` | orchestrate, always first |
| `worktree` | `using-git-worktrees/` | orchestrate |
| `debug` | `systematic-debugging/` | orchestrate, executor |
| `verify` | `verification-before-completion/` | orchestrate, commit, merge |
| `plan` | `writing-plans/` | wplan |
| `review-request` | `requesting-code-review/` | wreview |
| `review-receive` | `receiving-code-review/` | wreview |
| `tdd` | (executor test-first practice), `test-driven-development/` | executor |

## brainstorm

Upstream: `brainstorming/`

| Upstream item | Where it lives |
|---|---|
| Brainstorming Ideas Into Designs — turn ideas into designs through dialogue | brainstorm/SKILL.md § Brainstorm |
| Brainstorming Ideas Into Designs — classify first, then context, refine, design, approval | brainstorm/SKILL.md § Brainstorm |
| Establish Shared Understanding | brainstorm/SKILL.md § Shared understanding |
| Establish Shared Understanding — outcome the partner can recognize and correct | brainstorm/SKILL.md § Shared understanding |
| Establish Shared Understanding — 1. Discover intent | brainstorm/SKILL.md § Shared understanding |
| Establish Shared Understanding — 1. one focused question about purpose when missing | brainstorm/SKILL.md § Shared understanding |
| Establish Shared Understanding — 1. app genre is not intent; gathering requirements is not re-authorization | brainstorm/SKILL.md § Shared understanding |
| Establish Shared Understanding — 2. Write back your understanding | brainstorm/SKILL.md § Shared understanding |
| Establish Shared Understanding — 2. separate what they said from assumptions; invite correction | brainstorm/SKILL.md § Shared understanding |
| Establish Shared Understanding — 3. Carry intent into the design | brainstorm/SKILL.md § Shared understanding |
| Establish Shared Understanding — reflect a supplied purpose instead of re-asking; keep the note concise | brainstorm/SKILL.md § Shared understanding |
| HARD-GATE — no implementation action before the path's prerequisites | brainstorm/SKILL.md § Hard gate; template: "Brainstorm first, always" |
| HARD-GATE — Spike: partner approves question and probe | brainstorm/SKILL.md § Hard gate |
| HARD-GATE — Bounded: partner approves the short in-chat design | brainstorm/SKILL.md § Hard gate |
| HARD-GATE — Architectural: approve the spec, review the plan, select its execution method | brainstorm/SKILL.md § Hard gate; plan/SKILL.md § Hand-off |
| HARD-GATE — design approval only permits the spec; spec approval only permits writing-plans | brainstorm/SKILL.md § Hard gate |
| HARD-GATE — a reply approves only the stage presented | brainstorm/SKILL.md § Hard gate |
| HARD-GATE — resume at the earliest incomplete stage; no skipping | brainstorm/SKILL.md § Hard gate |
| HARD-GATE — read-only exploration allowed | brainstorm/SKILL.md § Hard gate |
| Three Paths | brainstorm/SKILL.md § Three paths |
| Three Paths — classify and say it out loud before the first question | brainstorm/SKILL.md § Three paths |
| Three Paths — Spike | brainstorm/SKILL.md § Three paths |
| Three Paths — Spike: no design doc, no spec; findings as a recommendation; code stays throwaway | brainstorm/SKILL.md § Three paths |
| Three Paths — Bounded | brainstorm/SKILL.md § Three paths |
| Three Paths — Bounded: the flow must already exist in the repo | brainstorm/SKILL.md § Three paths |
| Three Paths — Bounded: design in chat, STOP, approval as hard a gate; no spec, no plan doc | brainstorm/SKILL.md § Three paths |
| Three Paths — Architectural | brainstorm/SKILL.md § Three paths |
| Three Paths — in doubt take the heavier path; one-way ratchet, nothing downgrades | brainstorm/SKILL.md § Three paths |
| Anti-Pattern: "Too Simple To Need Approval" | brainstorm/SKILL.md § Too simple to need approval |
| Anti-Pattern: "Too Simple To Need Approval" — scale the artifact to the path; complete its reviews | brainstorm/SKILL.md § Too simple to need approval |
| Red Flags | brainstorm/SKILL.md § Red flags |
| Red Flags — "This is too simple to need a design" | brainstorm/SKILL.md § Red flags |
| Red Flags — "I'll call it bounded and skip the spec" | brainstorm/SKILL.md § Red flags |
| Red Flags — "It's bounded and the design is obvious" | brainstorm/SKILL.md § Red flags |
| Red Flags — "I understand this kind of app, so it's bounded" | brainstorm/SKILL.md § Red flags |
| Red Flags — "The spike works, so I'll keep the code" | brainstorm/SKILL.md § Red flags |
| Red Flags — "It grew, but I'm almost done" | brainstorm/SKILL.md § Red flags |
| Red Flags — "They approved the spike, so the follow-up change is approved too" | brainstorm/SKILL.md § Red flags |
| Checklist | brainstorm/SKILL.md § Checklist |
| Checklist — classify, announce, one task per item, in order | brainstorm/SKILL.md § Checklist |
| Checklist — Spike 1. Explore project context | brainstorm/SKILL.md § Checklist |
| Checklist — Spike 2. Present question + probe plan | brainstorm/SKILL.md § Checklist |
| Checklist — Spike 3. Get approval | brainstorm/SKILL.md § Checklist |
| Checklist — Spike 4. Investigate | brainstorm/SKILL.md § Checklist |
| Checklist — Spike 5. Report findings | brainstorm/SKILL.md § Checklist |
| Checklist — Bounded 1. Explore project context | brainstorm/SKILL.md § Checklist |
| Checklist — Bounded 2. Ask clarifying questions | brainstorm/SKILL.md § Checklist |
| Checklist — Bounded 3. Present short design in chat | brainstorm/SKILL.md § Checklist |
| Checklist — Bounded 4. Get approval | brainstorm/SKILL.md § Checklist |
| Checklist — Bounded 5. Implement | brainstorm/SKILL.md § Checklist |
| Checklist — Architectural 1. Explore project context | brainstorm/SKILL.md § Checklist |
| Checklist — Architectural 2. Offer the visual companion just-in-time | extra:superpowers |
| Checklist — Architectural 3. Ask clarifying questions | brainstorm/SKILL.md § Checklist |
| Checklist — Architectural 4. Propose 2-3 approaches | brainstorm/SKILL.md § Checklist |
| Checklist — Architectural 5. Present design | brainstorm/SKILL.md § Checklist |
| Checklist — Architectural 6. Write design doc | brainstorm/SKILL.md § Checklist; brainstorm/SKILL.md § After the design |
| Checklist — Architectural 7. Spec self-review | brainstorm/SKILL.md § Checklist |
| Checklist — Architectural 8. User reviews written spec | brainstorm/SKILL.md § Checklist |
| Checklist — Architectural 9. Transition to implementation | brainstorm/SKILL.md § Checklist |
| Process Flow | brainstorm/SKILL.md § Process flow |
| Process Flow — digraph | brainstorm/SKILL.md § Process flow |
| Process Flow — terminal states are path-bound; only writing-plans after architectural | brainstorm/SKILL.md § Process flow |
| The Process | brainstorm/SKILL.md § The process |
| The Process — spike stops at the probe; bounded is context, questions, short design | brainstorm/SKILL.md § The process |
| The Process — Understanding the idea: check project state first | brainstorm/SKILL.md § The process |
| The Process — Understanding the idea: flag multiple independent subsystems at once | brainstorm/SKILL.md § The process |
| The Process — Understanding the idea: decompose into sub-projects, each its own cycle | brainstorm/SKILL.md § The process |
| The Process — Understanding the idea: one question at a time | brainstorm/SKILL.md § The process |
| The Process — Understanding the idea: prefer multiple choice | brainstorm/SKILL.md § The process |
| The Process — Understanding the idea: one question per message | brainstorm/SKILL.md § The process |
| The Process — Understanding the idea: purpose, constraints, success criteria | brainstorm/SKILL.md § The process |
| The Process — Exploring approaches: 2-3 approaches with trade-offs | brainstorm/SKILL.md § The process |
| The Process — Exploring approaches: conversational, with recommendation | brainstorm/SKILL.md § The process |
| The Process — Exploring approaches: lead with the recommended option | brainstorm/SKILL.md § The process |
| The Process — Exploring approaches: YAGNI ruthlessly | brainstorm/SKILL.md § The process |
| The Process — Presenting the design: present once understood | brainstorm/SKILL.md § The process |
| The Process — Presenting the design: scale sections, up to 200-300 words | brainstorm/SKILL.md § The process |
| The Process — Presenting the design: ask after each section | brainstorm/SKILL.md § The process |
| The Process — Presenting the design: cover architecture, components, data flow, errors, testing | brainstorm/SKILL.md § The process |
| The Process — Presenting the design: go back and clarify | brainstorm/SKILL.md § The process |
| The Process — Design for isolation and clarity: small units, clear interfaces | brainstorm/SKILL.md § The process |
| The Process — Design for isolation and clarity: what it does, how used, what it depends on | brainstorm/SKILL.md § The process |
| The Process — Design for isolation and clarity: understandable without internals | brainstorm/SKILL.md § The process |
| The Process — Design for isolation and clarity: focused files; large file signals too much | brainstorm/SKILL.md § The process |
| The Process — Working in existing codebases: explore first, follow patterns | brainstorm/SKILL.md § The process |
| The Process — Working in existing codebases: targeted improvements that affect the work | brainstorm/SKILL.md § The process |
| The Process — Working in existing codebases: no unrelated refactoring | brainstorm/SKILL.md § The process |
| After the Design (architectural path) | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — Documentation: spec path | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — Documentation: user preferences override the location | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — Documentation: writing-clearly-and-concisely skill if available | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — Documentation: commit the design document | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — Spec Self-Review 1. Placeholder scan | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — Spec Self-Review 2. Internal consistency | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — Spec Self-Review 3. Scope check | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — Spec Self-Review 4. Ambiguity check | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — Spec Self-Review: fix inline, no re-review | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — User Review Gate: ask, wait, re-review on changes, proceed on approval | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — Implementation: invoke writing-plans | brainstorm/SKILL.md § After the design |
| After the Design (architectural path) — Implementation: do not invoke any other skill | brainstorm/SKILL.md § After the design |
| Visual Companion | extra:superpowers |
| Visual Companion — offering just-in-time, offer as its own message | extra:superpowers |
| Visual Companion — per-question browser or terminal decision | extra:superpowers |
| Visual Companion — read visual-companion.md on acceptance | extra:superpowers |
| spec-document-reviewer-prompt.md | brainstorm/spec-reviewer-prompt.md § Spec reviewer |
| spec-document-reviewer-prompt.md — what to check, calibration, output format | brainstorm/spec-reviewer-prompt.md § Spec reviewer |
| visual-companion.md | extra:superpowers |
| scripts/ | extra:superpowers |

## plan

Upstream: `writing-plans/`

| Upstream item | Where it lives |
|---|---|
| Writing Plans | plan/SKILL.md § Plan |
| Overview | plan/SKILL.md § Overview |
| Overview — zero context, document everything, bite-sized tasks | plan/SKILL.md § Overview |
| Overview — DRY, YAGNI, TDD, frequent commits | plan/SKILL.md § Overview |
| Overview — skilled developer, new to the toolset and domain, weak on test design | plan/SKILL.md § Overview |
| Overview — Announce at start | plan/SKILL.md § Overview |
| Overview — Context: worktree created at execution time | plan/SKILL.md § Overview; orchestrate: "Create a worktree" |
| Overview — Save plans to | plan/SKILL.md § Hand-off |
| Overview — user preferences override the plan location | plan/SKILL.md § Overview |
| Scope Check | plan/SKILL.md § Scope check |
| Scope Check — one plan per independent subsystem, each working and testable | plan/SKILL.md § Scope check |
| File Structure | plan/SKILL.md § File structure |
| File Structure — map files and responsibilities before tasks | plan/SKILL.md § File structure |
| File Structure — clear boundaries, one responsibility per file | plan/SKILL.md § File structure |
| File Structure — prefer smaller, focused files | plan/SKILL.md § File structure |
| File Structure — files that change together live together | plan/SKILL.md § File structure |
| File Structure — follow established patterns; split an unwieldy file you modify | plan/SKILL.md § File structure |
| File Structure — structure informs decomposition; self-contained tasks | plan/SKILL.md § File structure |
| Task Right-Sizing | plan/SKILL.md § Task right-sizing |
| Task Right-Sizing — fold setup into the task that needs it; split where a reviewer could reject one | plan/SKILL.md § Task right-sizing |
| Task Right-Sizing — each task ends with an independently testable deliverable | plan/SKILL.md § Task right-sizing |
| Bite-Sized Task Granularity | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — one action per step, 2-5 minutes | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — write the failing test | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — run it to make sure it fails | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — implement the minimal code | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — run the tests, make sure they pass | plan/SKILL.md § Bite-sized steps |
| Bite-Sized Task Granularity — commit | plan/SKILL.md § Bite-sized steps |
| Plan Document Header | plan/SKILL.md § Plan header |
| Plan Document Header — every plan MUST start with the header | plan/SKILL.md § Plan header |
| Plan Document Header — For agentic workers line | plan/SKILL.md § Plan header |
| Plan Document Header — Goal, Architecture, Tech Stack | plan/SKILL.md § Plan header |
| Plan Document Header — Spec path; the spec travels with the plan | plan/SKILL.md § Plan header |
| Plan Document Header — Global Constraints section | plan/SKILL.md § Global constraints |
| Plan Document Header — Review Focus section | plan/SKILL.md § Review focus |
| Plan Document Header — Review Focus: silence in the spec is not permission to break | plan/SKILL.md § Review focus |
| Plan Document Header — Review Focus: pin each line with a test in the owning task | plan/SKILL.md § Review focus |
| Task Structure | plan/SKILL.md § Task format |
| Task Structure — Files: create, modify with line ranges, test | plan/SKILL.md § Task format |
| Task Structure — Interfaces: Consumes and Produces | plan/SKILL.md § Task format |
| Task Structure — Step 1 write the failing test (code) | plan/SKILL.md § Task format |
| Task Structure — Step 2 run test to verify it fails | plan/SKILL.md § Task format |
| Task Structure — Step 3 write minimal implementation | plan/SKILL.md § Task format |
| Task Structure — Step 4 run test to verify it passes | plan/SKILL.md § Task format |
| Task Structure — Step 5 commit | plan/SKILL.md § Task format |
| No Placeholders | plan/SKILL.md § No placeholders |
| No Placeholders — "TBD", "TODO", "implement later", "fill in details" | plan/SKILL.md § No placeholders |
| No Placeholders — "Add appropriate error handling" / validation / edge cases | plan/SKILL.md § No placeholders |
| No Placeholders — "Write tests for the above" | plan/SKILL.md § No placeholders |
| No Placeholders — "Similar to Task N" | plan/SKILL.md § No placeholders |
| No Placeholders — steps without how; code blocks required | plan/SKILL.md § No placeholders |
| No Placeholders — references to undefined types or functions | plan/SKILL.md § No placeholders |
| Self-Review | plan/SKILL.md § Self-review |
| Self-Review — a checklist you run yourself | plan/SKILL.md § Self-review |
| Self-Review — 1. Spec coverage | plan/SKILL.md § Self-review |
| Self-Review — 2. Placeholder scan | plan/SKILL.md § Self-review |
| Self-Review — 3. Type consistency | plan/SKILL.md § Self-review |
| Self-Review — 4. Review Focus | plan/SKILL.md § Self-review |
| Self-Review — fix inline; a requirement with no task gets a task | plan/SKILL.md § Self-review |
| Execution Handoff | plan/SKILL.md § Hand-off |
| Execution Handoff — link the plan, ask for review, wait before implementation | plan/SKILL.md § Hand-off |
| Execution Handoff — execution method already supplied: preserve it | plan/SKILL.md § Hand-off |
| Execution Handoff — no method supplied: offer Subagent-driven or Native | plan/SKILL.md § Hand-off |
| Execution Handoff — Subagent-driven: fresh executor and reviewer per task | plan/SKILL.md § Hand-off; orchestrate: "Give each executor ONLY its section" |
| Execution Handoff — Native: in-session execution | plan/SKILL.md § Hand-off |
| plan-document-reviewer-prompt.md | plan/plan-reviewer-prompt.md § Plan reviewer |
| plan-document-reviewer-prompt.md — what to check, calibration, output format | plan/plan-reviewer-prompt.md § Plan reviewer |

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

## verify

Upstream: `verification-before-completion/`

| Upstream item | Where it lives |
|---|---|
| Overview | verify/SKILL.md § Verify |
| Overview — core principle: evidence before claims, always | verify/SKILL.md § Verify |
| Overview — violating the letter is violating the spirit | verify/SKILL.md § Verify |
| The Iron Law | verify/SKILL.md § Iron law |
| The Iron Law — no completion claims without fresh verification evidence | verify/SKILL.md § Iron law |
| The Iron Law — not run in this message, cannot claim it passes | verify/SKILL.md § Iron law |
| The Gate Function | verify/SKILL.md § Gate function |
| The Gate Function — 1. IDENTIFY | verify/SKILL.md § Gate function |
| The Gate Function — 2. RUN | verify/SKILL.md § Gate function |
| The Gate Function — 3. READ | verify/SKILL.md § Gate function |
| The Gate Function — 4. VERIFY: no, state actual status; yes, claim with evidence | verify/SKILL.md § Gate function |
| The Gate Function — 5. ONLY THEN | verify/SKILL.md § Gate function |
| The Gate Function — skip any step = lying, not verifying | verify/SKILL.md § Gate function |
| Common Failures | verify/SKILL.md § Common failures |
| Common Failures — tests pass | verify/SKILL.md § Common failures |
| Common Failures — linter clean | verify/SKILL.md § Common failures |
| Common Failures — build succeeds | verify/SKILL.md § Common failures |
| Common Failures — bug fixed | verify/SKILL.md § Common failures |
| Common Failures — regression test works | verify/SKILL.md § Common failures |
| Common Failures — agent completed | verify/SKILL.md § Common failures |
| Common Failures — requirements met | verify/SKILL.md § Common failures |
| Red Flags - STOP | verify/SKILL.md § Red flags |
| Red Flags - STOP — "should", "probably", "seems to" | verify/SKILL.md § Red flags |
| Red Flags - STOP — satisfaction before verification | verify/SKILL.md § Red flags |
| Red Flags - STOP — about to commit, push or PR without verification | verify/SKILL.md § Red flags |
| Red Flags - STOP — trusting agent success reports | verify/SKILL.md § Red flags |
| Red Flags - STOP — relying on partial verification | verify/SKILL.md § Red flags |
| Red Flags - STOP — "just this once" | verify/SKILL.md § Red flags |
| Red Flags - STOP — tired and wanting work over | verify/SKILL.md § Red flags |
| Red Flags - STOP — any wording implying success without verification | verify/SKILL.md § Red flags |
| Rationalization Prevention | verify/SKILL.md § Rationalizations |
| Rationalization Prevention — "Should work now" | verify/SKILL.md § Rationalizations |
| Rationalization Prevention — "I'm confident" | verify/SKILL.md § Rationalizations |
| Rationalization Prevention — "Just this once" | verify/SKILL.md § Rationalizations |
| Rationalization Prevention — "Linter passed" | verify/SKILL.md § Rationalizations |
| Rationalization Prevention — "Agent said success" | verify/SKILL.md § Rationalizations |
| Rationalization Prevention — "I'm tired" | verify/SKILL.md § Rationalizations |
| Rationalization Prevention — "Partial check is enough" | verify/SKILL.md § Rationalizations |
| Rationalization Prevention — "Different words so rule doesn't apply" | verify/SKILL.md § Rationalizations |
| Key Patterns | verify/SKILL.md § Key patterns |
| Key Patterns — tests | verify/SKILL.md § Key patterns |
| Key Patterns — regression tests (red-green) | verify/SKILL.md § Key patterns |
| Key Patterns — build | verify/SKILL.md § Key patterns |
| Key Patterns — requirements | verify/SKILL.md § Key patterns |
| Key Patterns — agent delegation | verify/SKILL.md § Key patterns |
| When To Apply | verify/SKILL.md § When to apply |
| When To Apply — ALWAYS before: any success or completion claim | verify/SKILL.md § When to apply |
| When To Apply — ALWAYS before: any expression of satisfaction | verify/SKILL.md § When to apply |
| When To Apply — ALWAYS before: any positive statement about work state | verify/SKILL.md § When to apply |
| When To Apply — ALWAYS before: committing, PR creation, task completion | verify/SKILL.md § When to apply; orchestrate: "Merge only after review and verification pass" |
| When To Apply — ALWAYS before: moving to the next task | verify/SKILL.md § When to apply |
| When To Apply — ALWAYS before: delegating to agents | verify/SKILL.md § When to apply |
| When To Apply — applies to exact phrases, paraphrases, implications, any suggestion of completion | verify/SKILL.md § When to apply |

## debug

Upstream: `systematic-debugging/`

| Upstream item | Where it lives |
|---|---|
| Overview | debug/SKILL.md § Debug |
| Overview — core principle: root cause before fixes; symptom fixes are failure | debug/SKILL.md § Debug; executor: "Fix root causes" |
| Overview — violating the letter is violating the spirit | debug/SKILL.md § Debug |
| The Iron Law | debug/SKILL.md § Iron law |
| The Iron Law — no fixes without root cause investigation first | debug/SKILL.md § Iron law |
| The Iron Law — Phase 1 incomplete: no fix proposals | debug/SKILL.md § Iron law |
| When to Use | debug/SKILL.md § When to use |
| When to Use — any technical issue (test failures, production bugs, unexpected behavior, performance, build, integration) | debug/SKILL.md § When to use |
| When to Use — ESPECIALLY: under time pressure | debug/SKILL.md § When to use |
| When to Use — ESPECIALLY: one quick fix seems obvious | debug/SKILL.md § When to use |
| When to Use — ESPECIALLY: already tried multiple fixes | debug/SKILL.md § When to use |
| When to Use — ESPECIALLY: previous fix didn't work | debug/SKILL.md § When to use |
| When to Use — ESPECIALLY: don't fully understand the issue | debug/SKILL.md § When to use |
| When to Use — don't skip: issue seems simple | debug/SKILL.md § When to use |
| When to Use — don't skip: in a hurry | debug/SKILL.md § When to use |
| When to Use — don't skip: manager wants it fixed NOW | debug/SKILL.md § When to use |
| When to Use — before an escalation climb; plan defects fixed in PLAN.md (Dryas) | debug/SKILL.md § When to use; orchestrate: "Before each climb" |
| The Four Phases | debug/SKILL.md § Iron law |
| The Four Phases — complete each phase before the next | debug/SKILL.md § Iron law |
| Phase 1: Root Cause Investigation | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 1. Read error messages carefully | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 2. Reproduce consistently; not reproducible, gather data | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 3. Check recent changes | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 4. Gather evidence in multi-component systems | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 4. instrument each boundary, run once, analyze, investigate | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 4. multi-layer example | debug/SKILL.md § Phase 1: Root cause |
| Phase 1: Root Cause Investigation — 5. Trace data flow | debug/SKILL.md § Phase 1: Root cause; debug/root-cause-tracing.md § The tracing process |
| Phase 1: Root Cause Investigation — 5. quick version: origin, caller, trace up, fix at source | debug/SKILL.md § Phase 1: Root cause |
| Phase 2: Pattern Analysis | debug/SKILL.md § Phase 2: Pattern analysis |
| Phase 2: Pattern Analysis — 1. Find working examples | debug/SKILL.md § Phase 2: Pattern analysis |
| Phase 2: Pattern Analysis — 2. Compare against references, read completely | debug/SKILL.md § Phase 2: Pattern analysis |
| Phase 2: Pattern Analysis — 3. Identify differences, however small | debug/SKILL.md § Phase 2: Pattern analysis |
| Phase 2: Pattern Analysis — 4. Understand dependencies | debug/SKILL.md § Phase 2: Pattern analysis |
| Phase 3: Hypothesis and Testing | debug/SKILL.md § Phase 3: Hypothesis and test |
| Phase 3: Hypothesis and Testing — 1. Form a single hypothesis | debug/SKILL.md § Phase 3: Hypothesis and test |
| Phase 3: Hypothesis and Testing — 2. Test minimally, one variable at a time | debug/SKILL.md § Phase 3: Hypothesis and test |
| Phase 3: Hypothesis and Testing — 3. Verify before continuing; no fixes on top | debug/SKILL.md § Phase 3: Hypothesis and test |
| Phase 3: Hypothesis and Testing — 4. When you don't know | debug/SKILL.md § Phase 3: Hypothesis and test |
| Phase 4: Implementation | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 1. Create a failing test case (test-driven-development/ skill) | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 2. Implement a single fix; no while-I'm-here, no bundled refactoring | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 3. Verify the fix (verification-before-completion/ skill) | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 4. Fix doesn't work: count; under 3 back to Phase 1; 3+ stop | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 5. 3+ fixes failed: question the architecture | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 5. signs of an architectural problem | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 5. question fundamentals; discuss with your human partner | debug/SKILL.md § Phase 4: Fix |
| Phase 4: Implementation — 5. not a failed hypothesis, a wrong architecture | debug/SKILL.md § Phase 4: Fix |
| Red Flags - STOP and Follow Process | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Quick fix for now, investigate later" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Just try changing X and see if it works" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Add multiple changes, run tests" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Skip the test, I'll manually verify" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "It's probably X, let me fix that" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "I don't fully understand but this might work" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Pattern says X but I'll adapt it differently" | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "Here are the main problems" without investigation | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — proposing solutions before tracing data flow | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — "One more fix attempt" after 2+ | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — each fix reveals a new problem elsewhere | debug/SKILL.md § Red flags |
| Red Flags - STOP and Follow Process — all mean return to Phase 1; 3+ failed, question the architecture | debug/SKILL.md § Red flags |
| your human partner's Signals You're Doing It Wrong | debug/SKILL.md § Signals from the user |
| your human partner's Signals You're Doing It Wrong — "Is that not happening?" | debug/SKILL.md § Signals from the user |
| your human partner's Signals You're Doing It Wrong — "Will it show us...?" | debug/SKILL.md § Signals from the user |
| your human partner's Signals You're Doing It Wrong — "Stop guessing" | debug/SKILL.md § Signals from the user |
| your human partner's Signals You're Doing It Wrong — "Ultra-think this" | debug/SKILL.md § Signals from the user |
| your human partner's Signals You're Doing It Wrong — "We're stuck?" | debug/SKILL.md § Signals from the user |
| your human partner's Signals You're Doing It Wrong — stop, return to Phase 1 | debug/SKILL.md § Signals from the user |
| Common Rationalizations | debug/SKILL.md § Rationalizations |
| Common Rationalizations — "Issue is simple, don't need process" | debug/SKILL.md § Rationalizations |
| Common Rationalizations — "Emergency, no time for process" | debug/SKILL.md § Rationalizations |
| Common Rationalizations — "Just try this first, then investigate" | debug/SKILL.md § Rationalizations |
| Common Rationalizations — "I'll write test after confirming fix works" | debug/SKILL.md § Rationalizations |
| Common Rationalizations — "Multiple fixes at once saves time" | debug/SKILL.md § Rationalizations |
| Common Rationalizations — "Reference too long, I'll adapt the pattern" | debug/SKILL.md § Rationalizations |
| Common Rationalizations — "I see the problem, let me fix it" | debug/SKILL.md § Rationalizations |
| Common Rationalizations — "One more fix attempt" (after 2+ failures) | debug/SKILL.md § Rationalizations |
| Quick Reference | debug/SKILL.md § Quick reference |
| Quick Reference — four phases: key activities and success criteria | debug/SKILL.md § Quick reference |
| When Process Reveals "No Root Cause" | debug/SKILL.md § No root cause found |
| When Process Reveals "No Root Cause" — 1. you've completed the process | debug/SKILL.md § No root cause found |
| When Process Reveals "No Root Cause" — 2. document what you investigated | debug/SKILL.md § No root cause found |
| When Process Reveals "No Root Cause" — 3. appropriate handling (retry, timeout, error message) | debug/SKILL.md § No root cause found |
| When Process Reveals "No Root Cause" — 4. monitoring or logging | debug/SKILL.md § No root cause found |
| When Process Reveals "No Root Cause" — 95% are incomplete investigation | debug/SKILL.md § No root cause found |
| Supporting Techniques | debug/SKILL.md § Supporting techniques |
| Supporting Techniques — root-cause-tracing, defense-in-depth, condition-based-waiting | debug/SKILL.md § Supporting techniques |
| Supporting Techniques — fix-root-causes principle (Dryas) | debug/SKILL.md § Supporting techniques |
| root-cause-tracing.md | debug/root-cause-tracing.md § Root cause tracing |
| root-cause-tracing.md — Overview, core principle | debug/root-cause-tracing.md § Overview |
| root-cause-tracing.md — When to Use (flowchart, use when) | debug/root-cause-tracing.md § When to use |
| root-cause-tracing.md — The Tracing Process 1-5 | debug/root-cause-tracing.md § The tracing process |
| root-cause-tracing.md — Adding Stack Traces (instrument, stderr in tests, run and capture, analyze) | debug/root-cause-tracing.md § Adding stack traces |
| root-cause-tracing.md — Finding Which Test Causes Pollution | debug/root-cause-tracing.md § Find the polluter |
| root-cause-tracing.md — Real Example: Empty projectDir | debug/root-cause-tracing.md § Real example: empty projectDir |
| root-cause-tracing.md — Key Principle (flowchart, never fix just the symptom) | debug/root-cause-tracing.md § Key principle |
| root-cause-tracing.md — Stack Trace Tips | debug/root-cause-tracing.md § Stack trace tips |
| root-cause-tracing.md — Real-World Impact | debug/root-cause-tracing.md § Real-world impact |
| defense-in-depth.md | debug/defense-in-depth.md § Defense-in-depth validation |
| defense-in-depth.md — Overview, core principle | debug/defense-in-depth.md § Overview |
| defense-in-depth.md — Why Multiple Layers | debug/defense-in-depth.md § Why multiple layers |
| defense-in-depth.md — Layer 1: Entry Point Validation | debug/defense-in-depth.md § Layer 1: Entry point validation |
| defense-in-depth.md — Layer 2: Business Logic Validation | debug/defense-in-depth.md § Layer 2: Business logic validation |
| defense-in-depth.md — Layer 3: Environment Guards | debug/defense-in-depth.md § Layer 3: Environment guards |
| defense-in-depth.md — Layer 4: Debug Instrumentation | debug/defense-in-depth.md § Layer 4: Debug instrumentation |
| defense-in-depth.md — Applying the Pattern 1-4 | debug/defense-in-depth.md § Applying the pattern |
| defense-in-depth.md — Example from Session | debug/defense-in-depth.md § Example from a session |
| defense-in-depth.md — Key Insight | debug/defense-in-depth.md § Key insight |
| condition-based-waiting.md | debug/condition-based-waiting.md § Condition-based waiting |
| condition-based-waiting.md — Overview, core principle | debug/condition-based-waiting.md § Overview |
| condition-based-waiting.md — When to Use (flowchart, use when, don't use when) | debug/condition-based-waiting.md § When to use |
| condition-based-waiting.md — Core Pattern | debug/condition-based-waiting.md § Core pattern |
| condition-based-waiting.md — Quick Patterns | debug/condition-based-waiting.md § Quick patterns |
| condition-based-waiting.md — Implementation (waitFor) | debug/condition-based-waiting.md § Implementation |
| condition-based-waiting.md — Implementation: domain helpers in the example file | debug/condition-based-waiting.md § Implementation |
| condition-based-waiting.md — Common Mistakes (too fast, no timeout, stale data) | debug/condition-based-waiting.md § Common mistakes |
| condition-based-waiting.md — When Arbitrary Timeout IS Correct | debug/condition-based-waiting.md § When an arbitrary timeout IS correct |
| condition-based-waiting.md — Real-World Impact | debug/condition-based-waiting.md § Real-world impact |
| condition-based-waiting-example.ts | extra:superpowers |
| find-polluter.sh | debug/root-cause-tracing.md § Find the polluter |
| CREATION-LOG.md | extra:superpowers |
| test-academic.md | extra:superpowers |
| test-pressure-1.md | extra:superpowers |
| test-pressure-2.md | extra:superpowers |
| test-pressure-3.md | extra:superpowers |
