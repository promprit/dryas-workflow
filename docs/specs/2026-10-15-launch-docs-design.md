# Launch docs: design

Date: 2026-10-15. Status: draft for review. Branch: `docs/launch`.
Contested: no (docs, images and GitHub metadata only; no numbered rule, interface or component changes).

## 1. Goal

Rewrite the repo's public face so Dryas markets itself as the product it is. Docs only: no code, flag, hook, template or test behaviour changes, except tests that read doc text (section 8).

Reader: developers and tech leads who already use Claude Code or Codex and have been burned by an agent (it wandered out of scope, claimed tests it never ran, spent big-model money on small questions). Team leads and buyers are the second reader; the operating model serves them one layer down.

Success:

- A stranger understands what Dryas does in 5 seconds (hero), wants it in 30 (problem, asked vs enforced, proof), and has it installed in 2 minutes (install section).
- Every claim on the front page is true today and is followed by the mechanism that backs it.
- The full test suite passes, `tools/inventory.py --check` reports 0 problems, and every README link resolves.

Ruflo and Superpowers code removal is not part of this work: it ships in 2.2 with the OpenCode edition. This pass removes them from the pitch and marks them deprecated in the reference docs.

## 2. Positioning

Approach: enforcement as the spine (A), with the "brilliant agents, no discipline" problem framing (B). Cost is one of the fixes, not the headline.

| Element | Copy |
| --- | --- |
| Name | **Dryas** everywhere public. "The Dryas Workflow Framework" stays only as the formal name in `spec/dryas-spec-v1.md` and one line in "For teams". |
| Headline | **Rules your AI agents can't ignore.** |
| Hook line | **Stop asking your agent to behave. Make it.** |
| Problem headline | **Brilliant agents. No discipline.** |
| GitHub description (128 chars) | Rules your AI agents can't ignore. Design-first, scope-locked, test-proven delivery for Claude Code and Codex, enforced by hooks. |

Voice: Apple-plain. Short declaratives, concrete verbs, no hype words ("revolutionary", "AI-powered", "seamless", "supercharge", "unleash"). Every claim is followed by the mechanism ("Rules are enforced. A hook denies the edit."). House style kept: British spelling.

Honesty rules:

- No "rough edges" or apology copy; a plain status line instead.
- The judge scorecard (including its known gaps) moves to its own page, linked from the front page as "measured on a public corpus, gated in CI". It is not removed or softened.
- The scope lock footnote stays: it covers the file-edit tools, not writes from shell commands.
- Proof numbers are aggregates from the studio's own logs, labelled as such, never a benchmark (section 4).

## 3. README

Target about 150 lines (today 201). Sections in order; the copy below is the approved direction, final wording is settled in the build and reviewed in `/wreview`.

1. **Hero.** `hero` image (section 5), then the hook line, then:
   > Dryas turns Claude Code and Codex into a disciplined delivery team. It agrees the design before it writes code. It edits only the files its task names. It proves the tests pass. It pays for the big model only when the small one fails. Every rule is enforced by a hook, not hoped for in a prompt.

   Status line: `v2 · MIT · Claude Code · Codex · Cloud sessions · macOS, Linux, Windows`. No CI badge here. The line says `v2`, not a patch version, so it does not go stale each release; the build checks no test pins a version string in the README.
2. **The problem.** "Brilliant agents. No discipline." Four bullets: they build before anyone agreed what; they tidy files nobody asked about, and parallel agents overwrite each other; they report tests they never ran; they spend big-model money on small-model questions.
3. **Asked vs enforced.** Five-row table (your agent today / with Dryas): design gate; scope lock (with the shell-write footnote); proof, not claims (executor report block, review and verify gate the merge); model ladder (cheapest first, climb on failure, every step logged); judge and human gates (risky commands judged; install, delete, push, overwrite and settings changes always need you). Then the `scope-lock` image with its caption, and the `ladder` image. Link: "The full comparison" → `docs/why-dryas.md`.
4. **The loop.** `loop` image, then one line per stage (Brainstorm, Plan, Judge, Build, Escalate, Review, Ship). The two human gates (design approval, ship) are named.
5. **Install in 60 seconds.** `git clone`, `install/install.sh` (and `install\install.ps1`), then a first command: `/orchestrate add rate limiting to the login endpoint`. Then: "No API key. No Node. Python 3.9+ and git." One line each linking Windows, Codex, cloud sessions and all flags to `docs/install.md` and `docs/cloud-sessions.md`.
6. **What you get.** Table of the seven commands (`/orchestrate`, `/wreview`, `/interrogate`, `/commit`, `/handoff`, `/tune`, `/retro`), one plain line each. One line on the core: the local judge, Dryas memory and 8 process skills. Link to the glossary.
7. **Proof: we ship with it.** Copy direction:
   > Dryas Studio delivers every project with Dryas, Dryas 2.0 included. Our own logs, 7 to 15 October 2026: **1,154 tasks merged · 1,689 executor dispatches · 160 out-of-scope edits blocked**. Not a benchmark. Just the work.

   Then the `flowobserve` image with its caption and live-demo link, and "About 1,740 tests, CI on macOS, Linux and Windows." Link to `docs/judge-scorecard.md`.
8. **For teams.** "Dryas is also a target operating model: roles, a RACI, metrics with healthy ranges, maturity levels L0 to L4, and a draft specification any harness can implement." Compact link list: operating model, why Dryas, architecture, layer docs, roles, metrics, adoption guide, spec, reference map, examples, docs index.
9. **Works with.** Claude Code, Codex and cloud sessions (shipping); OpenCode (next, 2.2); Pi, Roo, Cursor (later). Platforms line. Link to `docs/harnesses.md`.
10. **Credits and license.** Superpowers stays credited (the process skills derive from it; NOTICE unchanged). Ruflo: "1.x Ruflo memory imports supported" (`dryas memory import-ruflo`). The other upstreams stay. CI badge here. MIT.

Moves out of the README (content kept, not deleted):

| From README | To |
| --- | --- |
| Reference stack table, every install flag, manual plugin route, uninstall notes | `docs/install.md` |
| Codex and cloud install detail | `docs/install.md`, `docs/cloud-sessions.md` (already there; README keeps one line each) |
| Local judge scorecard and its method | `docs/judge-scorecard.md` (new) |
| "Use it for yourself" fork steps | `docs/adoption-guide.md` |
| "How the reference implementation works" bullets | Folded into sections 3 and 6; detail stays in `docs/workflow.md` |

Ruflo and Superpowers do not appear in the README except in Credits.

## 4. Proof numbers

Source: `~/.dryas/jev/logs` on the studio Mac. Window: timestamps from 2026-10-07 to 2026-10-15 inclusive (local time). Counting method, so the numbers can be reproduced:

| Number | Log | Rule | Value |
| --- | --- | --- | --- |
| Tasks merged | `merge.jsonl` | sum of `tasks_merged` in the window | 1,154 (94 merges) |
| Executor dispatches | `dispatch.jsonl` | records in the window, excluding `phase: "return"` | 1,689 |
| Out-of-scope edits blocked | `scope.jsonl` | `decision: "deny"` in the window | 160 |

The logs cover all studio projects (client and in-house), not only this repo; the copy says "every project, Dryas 2.0 included" and never "Dryas built Dryas". Escalation counts are not published: the log mixes in simulated verification runs. Only totals are published: no task, branch, project or path names (the repo's deny-term scan applies). If the build recounts and gets different numbers, it uses the recount and states the window it used. The recount needs the studio Mac's logs, so the build and its verify step run on that Mac.

## 5. Images

Brand source: `projects/dryas/brand-assets` (mark, `README.txt` palette and rules).

Shared system:

- Light: Paper `#EFEEE8` ground, District Green `#1B342C` ink, Driving Mist `#4A5D53` secondary.
- Dark: Shade `#10201B` ground, Paper ink, Moss Pale `#C9CFC4` secondary.
- Earth Brown `#5C4A3F` is the only accent, used only for the human gates and the denial.
- Type: Archivo Medium caps for wordmark and titles (tracking 0.22em wordmark, 0.06em headings); JetBrains Mono for labels and terminal text.
- Brand rules: one stroke weight (3.4 units), round joins, no gradients, glow, bevel or shadow, clearspace around the mark. Product lockup: mark plus **DRYAS**, no subline.
- Each image is one HTML source in `docs/assets/src/` with a light/dark toggle, rendered by the Playwright browser at 2x to PNG in `docs/assets/` (`<name>-light.png`, `<name>-dark.png`). PNG, not SVG, because GitHub does not load web fonts inside an SVG `<img>`. Each file under about 300 KB.
- README markup: `<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/<name>-dark.png"><img src="docs/assets/<name>-light.png" alt="..." width="..."></picture>`.
- Text contrast meets WCAG AA for every palette pair used, in both themes, checked during the build.
- No AI-generated art. No core copy lives only inside an image; the README reads fully without them.

| Image | Size (CSS px) | Content | Alt text |
| --- | --- | --- | --- |
| `hero` | 1600x640 | Mark and DRYAS wordmark top left; headline large in Archivo; hook line in mono below; a thin strip of the seven loop stages along the bottom | "Dryas: rules your AI agents can't ignore." |
| `loop` | 1600x420 | Seven stage nodes on one stroke; Earth Brown "YOU APPROVE" markers at Brainstorm and Ship; a return arc from Escalate to Build labelled "climb a tier, retry" | "The Dryas loop: Brainstorm, Plan, Judge, Build, Escalate, Review, Ship. You approve the design and the ship." |
| `scope-lock` | 1400x560 | Terminal card: an executor on task 2, scoped to `src/auth/**`, tries to edit `src/billing/invoice.ts`; the deny line; the executor continues inside its scope. Caption below the image in the README: "The agent wasn't asked to stay in scope. It couldn't leave." | "A terminal: the scope lock denies an edit to src/billing/invoice.ts because it is outside task 2's scope." |
| `ladder` | 1400x520 | Four rising steps fast, standard, strong, frontier; small mono "e.g. Haiku · Sonnet · Opus · Fable" under them; the arrow climbs only through a failure marker ("failed → logged reason → next tier"); "Stops at the first success" by the top step | "The model ladder: fast, standard, strong, frontier. A task climbs only after a failure, and every climb is logged." |
| `flowobserve` | 1600x1000 | Copied from `projects/flowobserve/docs/screenshot.png` (same owner). Dark only. Caption: "FlowObserve live demo (sample data): every session's stage, and the one that needs you." Links to the live demo | "FlowObserve: four live sessions, each at its stage in the loop; one needs you." |
| `social-preview` | 1280x640 | The hero reversed on District Green with the Paper mark, inside GitHub's safe area. One variant. Uploaded by hand (section 7) | n/a |

The scope-lock deny line is real output, not typed: the build runs `claude/jev/scope_lock.py` on a fixture (an active task 2 with Scope `src/auth/**`, an Edit of `src/billing/invoice.ts`) and pastes the literal reason it returns. Today's format (`scope_lock.py:73`): `scope lock: src/billing/invoice.ts is outside the scope of active task(s) 2`.

After rendering, `impeccable` and `ui-ux-pro-max` critique the images (the design rule) before the README task closes.

## 6. Docs

| File | Change |
| --- | --- |
| `docs/README.md` (new) | Docs landing page with three doors. **Use it:** install, workflow reference, commands, cloud sessions, harnesses, release check. **Understand it:** why Dryas, architecture, the five layer docs, glossary, judge scorecard. **Run it in a team:** operating model, roles, metrics, adoption guide (maturity levels), spec, reference map, examples. Footer **History:** `plans/`, `specs/`, `superpowers/`, CHANGELOG, "how each change was decided". |
| `docs/why-dryas.md` | Tightened as the long-form pitch. Opens with the agreed problem lines. Superpowers and Ruflo leave its framing. The row "third-party parts are hardened on install" is dropped (it exists only for Ruflo's `npx` helpers, which go in 2.2). "What Dryas is not" says OpenCode is next. |
| `docs/judge-scorecard.md` (new) | The scorecard table and method moved from the README, framed as "the number a keyless install gets, gated in CI", with the known gaps stated plainly. If a test or tool reads the scorecard markers from `README.md`, the markers move with the table and the reader is updated in the same task. |
| `docs/workflow.md` §7, §8 and `docs/install.md` (Ruflo and Superpowers parts) | A banner at the top of each part: "Deprecated: removed in 2.2. Dryas memory and the Dryas skills replace them. Bring 1.x Ruflo memory across with `dryas memory import-ruflo`." The reference text below stays accurate: the flags work until 2.2. |
| `docs/install.md` | Gains the content moved out of the README (section 3 table). |
| `docs/adoption-guide.md` | Gains the "Use it for yourself" fork steps. |
| `docs/roadmap.md` | A 2.2 entry: OpenCode edition and removal of the Ruflo and Superpowers extras. Kept small: the OpenCode session also edits this file. |
| `docs/harnesses.md` | OpenCode listed as next (2.2). Kept small, same reason. |
| `CONTRIBUTING.md` | No "rough edges" wording. |
| `CHANGELOG.md` | An `Unreleased` section with a `Docs` entry describing this change. |

Not changed in this pass: `claude/CLAUDE.md.template` (injected into every session, covered by template tests; it changes with the code in 2.2), the `docs/superpowers/` folder name (paths in plans, `tools/sync_codex_plugin.py` and tests; it moves in 2.2), the spec, the layer docs' substance, `NOTICE.md`, `GLOSSARY.md`, Codex copies.

## 7. GitHub metadata

Outward-facing: applied with `gh repo edit` only after Promprit approves this spec's wording; the PR is opened only after asking.

- Description: section 2.
- Topics (20): keep `claude-code`, `codex`, `claude`, `anthropic`, `ai-agents`, `agentic-workflow`, `multi-agent`, `developer-tools`, `code-review`, `ai-governance`, `ai-software-delivery`, `llm-ops`; add `claude-code-plugin`, `coding-agents`, `ai-coding`, `guardrails`, `claude-code-hooks`, `tdd`, `model-routing`, `git-worktrees`; drop `target-operating-model`, `llm-governance`, `developer-workflow`.
- Homepage: `https://dryasstudio.com`.
- Social preview: GitHub's API cannot set it. The handoff gives Promprit the steps: repo Settings → General → Social preview → Edit → upload `docs/assets/social-preview.png`.

## 8. Tests and verification

Tests that read docs: `install/tests/test_public_docs.py`, `test_framework_docs.py`, `test_ladder_docs.py`, `test_tier_docs.py`, `test_pstack_docs.py`, `test_owned_core_docs.py`, the cloud doc tests (`test_cloud_bindings.py`, `test_cloud_session.py`, `test_dryas_cloud.py`, `test_dryas_cloud_more.py`, `cloud_fixtures.py`) and any other test that opens `README.md` or a changed doc. The plan's first task lists every string they require. The rewrite keeps each one or moves it deliberately, updating the test in the same task, never weakening what it protects (for example, a test that the README names the install command keeps checking that).

Done means, with evidence (`dryas:verify`):

1. The full suite passes.
2. `tools/inventory.py --check` reports 0 problems.
3. Every relative link and image path in `README.md` and the changed docs resolves (a link check run in the verify step; not committed as a new tool).
4. The images render in both GitHub themes: Playwright screenshots of the pushed branch's README in light and dark (this needs `docs/launch` pushed to origin, which the standing rule allows).
5. A hype-word scan of the README finds none of the banned words (section 2).
6. The proof numbers match a recount using section 4's method, and the README's test count matches the suite run in step 1 (rounded down to the nearest ten).

## 9. Shipping

- Branch `docs/launch` in this worktree; spec → `/wplan` → `/orchestrate` → `/wreview` and `dryas:verify`.
- No version bump and no tag: docs only. The CHANGELOG `Unreleased` entry ships with 2.2.
- The branch may be pushed (standing rule). `main` is protected: when green, ask before opening the PR; it merges after CI passes on macOS, Ubuntu and Windows.
- The OpenCode session may also edit `docs/roadmap.md` and `docs/harnesses.md`; expect a small merge.

## 10. Out of scope

Code removal of Ruflo and Superpowers (2.2), renaming `docs/superpowers/`, launch posts (the X templates in brand assets), a Show HN or Reddit write-up, a product page on dryasstudio.com, and a terminal GIF of `/orchestrate` (needs a `vhs` install).

## 11. Changes during the build (approved)

- Proof numbers use the closed window 7 to 14 October 2026: 1,036 tasks merged, 1,556 executor dispatches, 150 out-of-scope edits blocked (15 October was still accruing when recounted).
- Test count wording is "over 2,000 tests" (pytest collects 2,042), not a rounded figure.
- After a design critique: the hero is a 1600x400 band (lockup plus the real scope-lock deny line) so the README H1 is the only headline; the scope-lock card is 1400x480 and the ladder 1400x440; labels are at least 24px; ladder failure marks use ink, not the accent; the install block is split per OS; the ladder image sits under Escalate.
- The README command table also lists `/dryas:brainstorm` and `/wplan`, and the install section names `/dryas-cloud`.
