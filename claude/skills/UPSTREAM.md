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
