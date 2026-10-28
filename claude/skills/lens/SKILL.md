---
name: lens
description: Use when a design needs review (UI, UX, layout, visual style, components, on-screen copy), when brainstorm meets a new feature or product idea, or when the user says "3 lens" or /lens. Runs the design panel (craft, impeccable, ui-ux-pro-max) or the product panel (focus, craft, data), writes one lens page and a fixed `## Lens` block.
allowed-tools: Agent, Artifact, Skill(artifact-design), Skill(impeccable), Skill(impeccable:impeccable), Skill(ui-ux-pro-max), Skill(ui-ux-pro-max:ui-ux-pro-max), Read, Write, Edit, Glob, Grep
---
<!-- claude -->
Invoke this skill with the Skill tool as `dryas:lens`; `/lens [design|product]` runs it on demand.
<!-- /claude -->
<!-- codex -->
On Codex: invoke this skill as `$dryas:lens`. The lens page is a local HTML file whose path you give the user.
<!-- /codex -->
<!-- opencode -->
On OpenCode: load this skill as `dryas-lens`; `/lens [design|product]` runs it on demand. The lens page is a local HTML file whose path you give the user.
<!-- /opencode -->

# Lens

A lens is advice. The user's approval stays the gate: a lens never approves a design, never blocks one, and never starts implementation.

## Which panel

| Situation | Panel |
| --- | --- |
| A design that needs review (UI, UX, layout, visual style, components, on-screen copy) | design panel |
| A new feature or product idea in brainstorm | product panel |
| Both at once | design+product, one page |
| The user says "3 lens", or `/lens product` | product panel |
| `/lens design` | design panel |
| `/lens` with no argument | pick from the rows above |

Not for bug fixes, internal tooling or refactors, unless the user asks.

## Run the lenses

1. **Subject.** Name what is under review: the in-chat design, the spec, a mockup or screenshot, a running page, or the product idea with its intent note.
2. **Lenses.** Run each lens of the panel in this order; each returns a verdict (`pass` or `change`), its findings, and the change made for each finding. The question each lens asks is in `${CLAUDE_PLUGIN_ROOT}/skills/lens/reference.md` § Lenses.
   - Design panel: craft, then `impeccable` (its critique pass on the subject), then `ui-ux-pro-max` (style, palette, font pairing, UX guidelines, stack patterns).
   - Product panel: focus, then craft, then data.
   - When `impeccable` or `ui-ux-pro-max` is not installed or not callable here, mark that lens `skipped (not available)` and go on; craft always runs, since it needs no skill.
<!-- claude -->
   **Run steps 2-4 in ONE subagent**, so `impeccable` and `ui-ux-pro-max` stay out of this session's context: the Agent tool with `subagent_type: "general-purpose"`, `model: "haiku"`, description `designer: lens review <topic>`. Its prompt carries: the subject (the design text, spec path or mockup path); the panel; the page path to write (`lens/<topic>-lens.html` in your scratchpad, or `.orchestrate/<branch-slug>-lens.html` inside /orchestrate); the instruction to read `${CLAUDE_PLUGIN_ROOT}/skills/lens/reference.md`; to load `impeccable` and `ui-ux-pro-max` with the Skill tool for the design panel (skip a lens it cannot load and mark it `skipped (not available)`); never run Bash; and to reply with ONLY the `## Lens` block exactly as § Lens block, then a list `- <lens>: <finding> → <change>` (reference.md § Subagent reply). You then apply the changes to the design, publish the page or keep the local file (below), and write the block. If the subagent's reply has no `## Lens` block, write the block yourself from its findings; if it reports a lens as skipped, say so to the user.
<!-- /claude -->
<!-- codex -->
   If sub-agents are available, run steps 2-4 in one sub-agent with the same prompt (subject, panel, page path, reference path, reply with ONLY the block and the finding list); otherwise run them here.
<!-- /codex -->
<!-- opencode -->
   Run steps 2-4 with the task tool on `dryas-executor-fast` when it can load skills, with the same prompt (subject, panel, page path, reference path, reply with ONLY the block and the finding list); otherwise run them here.
<!-- /opencode -->
3. **Apply.** In brainstorm, apply each change to the design before you present it, so the user approves the changed design. Inside `/orchestrate`, the `change` findings go to review next to the reviewers' findings.
4. **Page.** Write the lens page as `${CLAUDE_PLUGIN_ROOT}/skills/lens/reference.md` § Page describes. `<topic>` is the spec's topic slug (or a short slug of the design's name).
5. **Save or publish** (below).
6. **Block.** Write the `## Lens` block into the in-chat design or the spec, exactly as `${CLAUDE_PLUGIN_ROOT}/skills/lens/reference.md` § Lens block shows.
7. **Tell the user** the page link or path, the verdict, and one line per lens that changed something.

## Save or publish

<!-- claude -->
Load the `artifact-design` skill before writing the page. Write it to your scratchpad as `lens/<topic>-lens.html` and publish it with the Artifact tool, `label` exactly `dryas:lens design`, `dryas:lens product` or `dryas:lens design+product` (the panel that ran). FlowObserve's Canopy reads that label and the `-lens.html` file name; keep both exact. If the publish is denied or fails, write the same page to `docs/lens/<topic>-lens.html` and put the path in the block and in your message.

Inside `/orchestrate`: write `.orchestrate/<branch-slug>-lens.html` and name its path in the end report; publish it, with the same label, only when the user asked for artifacts when starting the run.
<!-- /claude -->
<!-- codex -->
Write the page to `docs/lens/<topic>-lens.html` (self-contained HTML, no external scripts) and give the user its path; it is committed with the spec. Inside `$dryas:orchestrate`: write `.orchestrate/<branch-slug>-lens.html` and name its path in the end report. Never publish it anywhere: only when the user asked for artifacts when starting the run may you tell them the path to share.
<!-- /codex -->
<!-- opencode -->
Write the page to `docs/lens/<topic>-lens.html` (self-contained HTML, no external scripts) and give the user its path; it is committed with the spec. Inside `/orchestrate`: write `.orchestrate/<branch-slug>-lens.html` and name its path in the end report. Never publish it anywhere: only when the user asked for artifacts when starting the run may you tell them the path to share.
<!-- /opencode -->

## Re-run

A second run on the same design updates the same page. Read the design's `## Lens` block first; its `Verdict:` line ends in `artifact: <link or path>`.
<!-- claude -->
- A claude.ai link: publish to that `url`.
- A local path: publish a new page, then replace the path in the block with its link.
<!-- /claude -->
<!-- codex -->
- A local path: overwrite that file.
- A link: write a new local page and replace the link in the block with its path.
<!-- /codex -->
<!-- opencode -->
- A local path: overwrite that file.
- A link: write a new local page and replace the link in the block with its path.
<!-- /opencode -->
- No block yet: create the page and the block.

## Inside /orchestrate

Run from `/orchestrate`, the lens is read-only on the design: skip § Re-run and step 6 (never write or change the spec's `## Lens` block), never publish unless the user asked for artifacts when starting the run, and write the page only to `.orchestrate/<branch-slug>-lens.html`, where `<branch-slug>` is the branch name with `/` replaced by `-`. Each `change` finding goes to the review as a line `lens: <finding> — <change>`, so the orchestrator handles it with the reviewers' findings; the page is for the user.

## Guardrails

- The lenses are our own interpretation of each person's known principles. Never quote them, never write words as said by them, never claim their endorsement. Their names appear only in the parentheses of the lens names.
- One page per topic; no chat output beyond the link or path, the verdict and the one-line-per-lens summary.
- Do not run a lens the situation does not call for: no lens on bug fixes, internal tooling or refactors unless asked.
