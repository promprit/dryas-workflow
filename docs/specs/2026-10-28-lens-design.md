# Lens review (`dryas:lens`): design

Date: 2026-10-28. Status: design approved in chat 2026-10-28 (approach A, sections 1 and 2 plus the Canopy addendum); written spec approved 2026-10-28. Branch: `spec/lens`.
Contested: yes (changes the numbered design rule in `claude/CLAUDE.md.template` and `docs/workflow.md` §4 step 1, and defines a marker and a text format that FlowObserve's Canopy reads).

## 1. Goal

Every design that needs review goes through the same three lenses, and the result is a page the user can look at, not text in a terminal. New product ideas get their own lens panel (Jobs, Ive, Ng). Both are one Dryas skill, `dryas:lens`, shipped with the plugin on all three editions.

The lenses already exist in one project: FlowObserve's `CLAUDE.md` § Advisory lenses and `design/spec/REVIEW.md`. This lifts them into Dryas so every project gets them, with one wording.

Success:

- A design task in brainstorm (UI, UX, layout, visual style, components, on-screen copy) produces a lens page with the design panel before the design is presented for approval.
- A new feature or product idea in brainstorm produces a lens page with the product panel before approaches are proposed.
- "3 lens", `/lens product` or `/lens design` runs the panel on demand, at any point.
- The page is an Artifact on Claude Code and a local HTML file on Codex and OpenCode. Re-running on the same design updates the same page.
- Every spec and in-chat design that ran a lens carries the fixed `## Lens` block (§6), which Canopy reads with no model call.
- `/orchestrate` never publishes an artifact unless the user asked for it on that run.
- **Not worse than 2.5.0** on prompts per task, speed and cost (§8).

Out of scope: changing FlowObserve or Canopy (they consume the contract in §6; their changes are their own tasks); new Jev log fields or workflow stages; running lenses on non-design, non-product work (bug fixes, internal tooling, refactors).

## 2. Decisions

| # | Decision |
| --- | --- |
| D1 | One skill `dryas:lens` with two panels, design and product (approach A). Not two skills, not rule text only. |
| D2 | Lens names follow Canopy: **focus** (from Jobs), **data** (from Ng), **craft** (from Ive). Each person's name appears only in parentheses as the source of the principle. |
| D3 | Design panel: craft (Ive), `impeccable` critique, `ui-ux-pro-max` check. Product panel: focus (Jobs), craft (Ive), data (Ng: data and AI). |
| D4 | Triggers: design that needs review → design panel; new feature or product idea in brainstorm → product panel; both → one page with both panels; "3 lens" or `/lens [design\|product]` on demand. Not for bug fixes or internal tooling. |
| D5 | Output: one page per design topic, updated in place on re-run. Claude Code: Artifact. Codex, OpenCode: local HTML file. |
| D6 | `/orchestrate` writes `.orchestrate/<branch-slug>-lens.html` (scratch, git-ignored) and names it in the end report; publishes only if the user asked on that run. |
| D7 | Canopy marker: the Artifact publish `label` (`dryas:lens design`, `dryas:lens product`, `dryas:lens design+product`) and the file name `lens/<topic>-lens.html`. No Jev log or reducer change. |
| D8 | Fixed `## Lens` block in the spec or in-chat design (§6). |
| D9 | Lenses advise; the user's approval stays the gate. Lenses never quote or claim endorsement from real people. |
| D10 | If a publish would prompt (consent ask), the Claude edition writes the local file and opens it instead. |
| D11 | Released as 2.6.0, gated against 2.5.0 (§8). |

## 3. The lenses

Our own interpretation of each person's known principles (wording from FlowObserve `CLAUDE.md:5-11`), not quotes.

| Lens | Panel | Question |
| --- | --- | --- |
| Focus (Jobs) | product | What is the one thing this must do or say? Cut whatever does not change what the user does next. Judge the whole experience end to end. |
| Craft (Ive) | both | Reduction and care. Remove until only the essential remains; calm by default, emphasis only for attention; precise type, spacing and motion. |
| Data (Ng) | product | Data first and actionable. What will we measure, does every metric point to a next action, and does any AI part have an eval and a way to find its errors? |
| Impeccable | design | Its critique/audit pass: hierarchy, cognitive load, accessibility, states, anti-patterns. |
| UI/UX Pro Max | design | Style, palette, font pairing, UX guidelines and stack patterns, checked against its data. |

Each lens returns a verdict (`pass` or `change`), its findings, and the change made for each finding. When `impeccable` or `ui-ux-pro-max` is not installed or not callable in the harness (Codex and OpenCode may not have them), the page marks that lens `skipped (not available)` and the run goes on; the craft lens always runs, since it needs no skill.

## 4. The page

Layout, in order:

1. Title (the design topic) and the overall verdict.
2. The design or mockup itself, when there is one (screenshot, comp or embedded markup).
3. One table per lens: Finding | Change made | Lens. Same as FlowObserve `design/spec/REVIEW.md`.
4. "Not done yet": suggestions not accepted, with the lens that made them.

The page follows the `artifact-design` contract on Claude Code (title, tokens, dark mode, phone width). The local-file version on Codex and OpenCode is the same HTML, self-contained, no external scripts.

Locations:

| Where | Path | Published |
| --- | --- | --- |
| Brainstorm, Claude Code | scratchpad `lens/<topic>-lens.html` | yes, Artifact, label per D7 |
| Brainstorm, Codex/OpenCode | `docs/lens/<topic>-lens.html` (committed with the spec) | no, path given |
| `/orchestrate` design review pass | `.orchestrate/<branch-slug>-lens.html` | only if asked on that run |
| On demand (`/lens`) | as brainstorm for the edition | as brainstorm |

`<topic>` is the spec's topic slug. A re-run updates the existing page: the skill reads the link or path from the design's `## Lens` block (`Verdict: … artifact: <link or path>`) and publishes to that `url`, so it works in a later session or after `/handoff`. With no block yet, it creates the page.

## 5. Wiring

New:

- `claude/skills/lens/SKILL.md`: triggers, panels, output and guardrails, with `<!-- claude -->` / `<!-- codex -->` blocks for the Artifact vs local-file step.
- `claude/skills/lens/reference.md`: lens definitions (§3), page layout (§4), the `## Lens` block (§6).
- `claude/commands/lens.md`: `/lens [design|product]`, a thin command that invokes `dryas:lens`; no argument picks from context (D4).
- Generated copies (`codex/skills/lens`, `opencode/skill/dryas-lens`, `opencode/command/lens.md`). The sync tools use hard-coded lists, so these are edits, not free outputs: add `lens` to `COMMANDS` in `tools/sync_codex_plugin.py` (and so `COMMAND_RE`) and to the process-skill rendering there; add `lens` to `FROM_CODEX` in `tools/sync_opencode.py`, so `opencode/command/lens.md` is rendered from `codex/skills/lens/SKILL.md`; update `install/tests/test_inventory.py` for the new skill and command.

Changed:

- `claude/CLAUDE.md.template:7`, the design rule becomes: "Design work (UI/UX, layout, visual style, components, on-screen copy) and new features: run `dryas:lens`." `codex/AGENTS.md.template` has no design rule today: its line 5 becomes "Brainstorm first: before new work, get the user's approval of a design (`$dryas:brainstorm`; design: `$dryas:lens`)." Rule lines are kept short to stay within the template byte budgets (install/tests/test_template_budget.py); the detail lives in the skill and docs/workflow.md.
- `docs/workflow.md` §4 step 1: the Design work paragraph says the same; a new "Product lens" paragraph; the table row at line 285 gains a `dryas:lens` row.
- `claude/skills/brainstorm/SKILL.md:97` and `reference.md` § Presenting the design: design work runs the design panel before the design is presented; a new feature runs the product panel before approaches; the page link and the `## Lens` block go into the in-chat design or the spec.
- `claude/skills/orchestrate/SKILL.md` has no design step today; this adds one. In §8 Finish, before "Review the worktree diff with the `dryas:review-request` skill": when the `## Lens` block in the spec named in the plan header (`**Spec:**` line of the plan the run was started from) has `Panel: design` or `Panel: design+product`, run `dryas:lens` (design panel, in its read-only § Inside /orchestrate mode) on what was built, write `.orchestrate/<branch-slug>-lens.html`, and put its path in the end report; publish it as an Artifact only when the user asked for artifacts when starting this run. No `## Lens` block or `Panel: product` means no lens step. Add `Skill(dryas:lens)` to its `allowed-tools`. Design is recognised by that block, not by guessing from the diff.
- `claude/skills/plan/SKILL.md`: a plan written from a design whose `## Lens` block names the design panel copies the block's `Panel:` line into the plan's Global Constraints, so executors of UI tasks see "design checked by `dryas:lens`; follow the lens page's changes".

## 6. Contract with Canopy (FlowObserve)

Canopy finds artifacts in FlowObserve's spool, where the hook already records each Artifact call's full `tool_input` (checked 2026-10-28). Two things are stable from this release:

1. **Marker.** A lens publish sets `label` to exactly one of `dryas:lens design`, `dryas:lens product`, `dryas:lens design+product`, and its `file_path` ends in `-lens.html`.
2. **`## Lens` block.** In every spec or in-chat design that ran a lens, verbatim shape:

```
## Lens
- Panel: design | product | design+product
- Focus (Jobs): <headline>
  - <insight>
  - <insight>
- Data (Ng): <headline>
  - <insight>
- Craft (Ive): <headline>
- Verdict: pass | change — artifact: <link or path>
```

Each lens has a one-sentence headline and any number of indented insights, with no limit on count or length: a lens writes every insight it has, and a lens with nothing more stays one line. Canopy posts the headline as the advisor's message and the insights as its follow-ups (splitting a long one across messages is Canopy's job, not the lens's). A design-only run writes `- Focus (Jobs): n/a` and `- Data (Ng): n/a` with no insights; the Impeccable and UI/UX Pro Max findings stay on the page, not in the block. A product or design+product run fills all three lenses. No line holds a quote attributed to a real person.

Parsing rules (what Canopy may rely on): the block starts at the `## Lens` heading and ends at the next heading or end of file; its top-level lines start with exactly `- Panel: `, `- Focus (Jobs): `, `- Data (Ng): `, `- Craft (Ive): `, `- Verdict: `, in that order; insights are lines starting with two spaces and `- ` under a lens line. Anything else in the block is ignored.

## 7. Tests

In `install/tests`, following the existing render and sync tests:

- The lens skill renders per edition: the Claude copy names the Artifact publish with the D7 label; the Codex and OpenCode copies name the local file and never the Artifact tool.
- The sync tools produce `dryas-lens` and `lens.md` for OpenCode and `skills/lens` for Codex.
- `claude/CLAUDE.md.template` and `docs/workflow.md` name `dryas:lens`, and their old two-skill rule text is gone; `codex/AGENTS.md.template` has the new design line and `$dryas:lens` in Skills.
- The orchestrate skill's §8 holds the lens step gated on `Panel: design` / `design+product`, with "publish only when the user asked" (D6), and its `allowed-tools` lists `Skill(dryas:lens)`.
- `test_inventory.py` lists the new skill and command.
- `reference.md` holds the `## Lens` block exactly as in §6 (one fixture, shared with the FlowObserve hand-off).

## 8. Release gate (2.6.0 vs 2.5.0)

Per the "no release worse than the last" rule:

- **Prompts per task.** Non-design tasks: unchanged (`tools/compare_v1.py` replay on the real `~/.dryas/jev/logs` tasks, plus `tools/compare_release.py` for the hook path, which this release does not touch). Design tasks: the Artifact publish replaces reading the text design in chat; it must not add a prompt. If a publish raises a consent ask in the test runs, D10 applies and the release ships with the local-file path as the Claude default until publishing is prompt-free.
- **Speed and cost.** One lens run on a design task adds at most one critique pass. Limit: median added time ≤ 90 s and added tokens ≤ 25k per design task. Measured by running the same three design prompts (one design-only, one product-only, one both; fixtures in `tools/fixtures/lens/`) in a headless session on 2.5.0 and on this branch, three runs each side, comparing total tokens and wall time from the session usage. This is a new small script, `tools/compare_lens.py`, and a plan task; `compare_v1.py` only covers prompts. Over either limit fails the release. Report the numbers through `pstack/benchmark-checklist.md`.
- **Noise.** One page per topic, updated in place; no new chat output beyond the link and the `## Lens` block.

Inside `/orchestrate` the lens never publishes unless asked and never edits the spec; the skills it calls are pre-allowed in the orchestrate front matter so the run stays prompt-free.

## 9. Hand-off

After this spec is committed, send the marker and the `## Lens` block (§6) to the FlowObserve session working on Canopy, so it reads exactly this. FlowObserve's own `CLAUDE.md` § Advisory lenses can later point at `dryas:lens`; that is a separate change in that repo.
