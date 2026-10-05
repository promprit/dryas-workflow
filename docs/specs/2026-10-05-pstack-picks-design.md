# pstack picks: design

Date: 2026-10-05. Status: draft for review. Branch: `docs/pstack-picks-plan`.

Source: [michael-denyer/pstack-claude](https://github.com/michael-denyer/pstack-claude) @ `dc8e617` (MIT), a port of Lauren Tan's [cursor/plugins/pstack](https://github.com/cursor/plugins/tree/main/pstack) (MIT). `deslop` comes from Cursor's cursor-team-kit (MIT).

## 1. Goal

Add a few of pstack's best ideas to the Dryas Workflow without weakening the loop. The loop stays in charge: brainstorm -> plan -> judge -> build -> escalate -> review -> ship, the Jev gate, the scope lock, the `executor` agent with the cheap-first ladder, Ruflo memory, ask-before-install/delete/settings, and one agent per worktree.

Success means:

- With `--no-pstack-picks`, the installed files are byte-identical to today's install.
- A default `/orchestrate` run adds one Jev question and one default-model cleanup executor, nothing more. Interrogate reviewers run only when gated (section 5.4). The escalation RCA step adds no agents.
- No vendored text names a model, a pstack agent or pstack configuration, and none of it grants autonomy beyond our ground rules.

## 2. What we take, what we cut

| pstack item | Decision | Reason |
|---|---|---|
| `interrogate` | **Take, adapted** | Multi-model adversarial review with a strong rubric and a lead-judgment filter (at most 5 "Act on", a visible "Dismissed" list). Fills the gap that `/wreview` is one reviewer run by the session that planned the work. Panel cut to two rungs of our ladder (section 6). |
| `why` | **Cut** | It answers "why was this built this way" by fanning out one investigator per MCP category (git, tracker, docs, chat, observability, errors, warehouse) plus a synthesizer, each on the strongest default model. At Escalate the question is "why did this task fail", which is root-cause debugging. Its replacement is an RCA step (section 5.3) built from `superpowers:systematic-debugging` and the fix-root-causes principle. |
| `deslop` | **Take, verbatim** inside `cleanup.md` | Removes AI slop before review: narrating comments, abnormal defensive code, `any` casts, deep nesting. |
| `no-comments` | **Take the rules only** inside `cleanup.md` | The skill needs the `comment-sicko` agent and calls `/how`, `/why` and `/architect`, all out of scope. We keep comment-sicko's keep-list (license headers, foreign constraints, public API docs, issue links, `prettier-ignore`, justified lint suppressions). We drop the persona, the agent and the skill calls; a claimed constraint that cannot be checked is reported open, not encoded. |
| `benchmark-checklist` | **Take, trimmed** | The seven questions and the report rules. Its links to `principle-explain-the-number` and to the Perf issue / Hillclimb playbooks are removed; the one-line reason is inlined. |
| principles: fix-root-causes, prove-it-works, subtract-before-you-add, test-behavior-not-implementation, guard-the-context-window | **Take, verbatim** | Judgment rules the executor lacks today. Linked from `executor.md` and the orchestrate skills (section 5.2). |
| poteto-mode and its SessionStart hook, setup-pstack, arena, swarm, tdd, babysit, shipping playbooks | **Out (agreed)** | They duplicate or fight `/orchestrate`, Jev route, Ruflo and Superpowers. The SessionStart hook injects an `EXTREMELY_IMPORTANT` routing mandate that competes with brainstorm-first. |

Not added either: `how`, `architect`, `reflect`, `unslop`, `technical-writing`, the other 19 principles, `comment-sicko`, `poteto-agent`, effort agents, `models.json`.

## 3. Vendor or depend (spec question 1)

**Recommendation: vendor (copy and adapt).**

| | Vendor | Depend on the plugin, deny the rest |
|---|---|---|
| Unwanted behavior | None ships | SessionStart `poteto-mode` mandate runs on every start/resume/clear/compact. Permissions cannot deny a plugin hook; only `session hook: off` in `pstack-models.md`, a file the plugin owns |
| Deny surface | None | About 40 `Skill(pstack:*)` denies, kept in step with every upstream release |
| Model policy | Rewritten to our roles | `opus`/`fable`/`sonnet` panels and `pstack:poteto-agent` defaults stay in the skill text |
| Upstream updates | Manual diff against a newer commit, recorded in `UPSTREAM.md` | Automatic, including trigger and wording changes we did not review |
| Drift | Ours to control | Upstream's |
| License | Ship LICENSE files and a NOTICE | Nothing to ship |
| Install | Our installer only, no network | Extra marketplace + plugin install and a version pin |

Writing our own from scratch was also rejected: it discards tested prose (the rubric, lead judgment, benchmark questions) for no gain.

Upstream updates are pulled by hand, when we choose: diff each file listed in `UPSTREAM.md` against the new upstream commit, re-apply our edits, update the pinned commit. No sync tooling (YAGNI).

## 4. Adaptation rules (spec question 2)

Every vendored file follows these rules. A test enforces the checkable ones (section 9).

1. Every subagent is the `executor` agent. Interrogate reviewers are `executor` in its existing `reviewer` role.
2. Models are named by role, never by name: "the executor's default model", "the next model on the ladder". The orchestrate skills, which already own model policy, map roles to models.
3. No autonomy wording. Nothing like "Just do it", "never block on the human" or "proceed without asking". Our ground rules (ask before install, move, delete, overwrite, settings) win.
4. No pstack plumbing: no `poteto`, `pstack:`, `setup-pstack`, `pstack-models.md`, effort agents, `readonly` flags, Codex platform-mapping links.
5. Paths use the installer's `{{CD}}` token, never `~` or a literal home path.
6. Edits are recorded per file in `claude/pstack/UPSTREAM.md`.

## 5. Where each pick hooks in (spec question 3)

Step numbers are `docs/workflow.md` §4. "Orchestrate" means both `claude/skills/orchestrate/SKILL.md` and `codex/skills/orchestrate/SKILL.md`; Codex differences are in 5.6.

Every line this section adds to `executor.md`, the orchestrate skills and the rules templates sits inside a `pstack-picks` marker block (section 8), including the RCA step in 5.3, so `--no-pstack-picks` leaves the loop exactly as it is today.

Review and cleanup tasks (5.4, 5.5) skip the TDD gate: their PLAN.md section says `Failing test first: none (review)` or `none (cleanup)`, and the orchestrator does not ask Jev `failing_test_exists` for them. They are dispatched like any task: their id goes into `.orchestrate/active.json` while they run, and comes out when they return.

### 5.1 Step 4, plan: benchmark checklist on perf tasks

When the approved design is performance work, every task that produces or reports a measured number gets one extra `Done:` line: "numbers vetted per `{{CD}}/pstack/benchmark-checklist.md` (verdict, run count, range, limiter)". The PLAN.md format and `planfile.py` do not change.

Outside `/orchestrate`, the `~/.claude/CLAUDE.md` Dryas block gains one line: before reporting a performance number you measured, read the benchmark checklist.

### 5.2 Step 7, dispatch: principles for executors

`executor.md` gains a short Principles block: one line each for fix-root-causes, prove-it-works, test-behavior-not-implementation and subtract-before-you-add, plus the path to the full text under `{{CD}}/pstack/principles/`. One line each, inline, so every dispatch does not pay for four extra reads (the guard-the-context-window rule applied to itself).

Orchestrate gains one line for guard-the-context-window (route bulk output to executors, keep summaries) and points to prove-it-works when judging reports.

### 5.3 Escalate (§3, orchestrate §7): RCA before each climb

Before re-dispatching Sonnet -> Opus, and again before Opus -> Fable, the orchestrator runs `superpowers:systematic-debugging` with the fix-root-causes principle on the failing reports. It reads; it does not edit project files.

- If the root cause is a plan defect (scope too narrow, vague or wrong `Done:`, missing context), fix that task section in `.orchestrate/PLAN.md` and re-dispatch on the **same** model. This does not count as a climb and does not reset the failure counter.
- Otherwise climb as today, with the root cause in the re-dispatch prompt and in the `log_escalation` reason.

Codex runs the same step if Superpowers is installed for Codex; otherwise it applies the fix-root-causes principle directly.

### 5.4 New step between 8 and 9: interrogate (gated)

After every task has returned and passed, and before cleanup:

1. One `jev_judge` call, noul `needs_interrogate`, state `{design_summary, diff_stat, files_touched, contested}`. Instructions: "Does the change described in `design_summary` and `diff_stat` restructure how components fit together, change an interface other modules depend on, or carry `contested: true`?"
2. Run interrogate when Jev says true at confidence >= `interrogate.min_confidence` (default 0.7), or the user asked, or the approved design marked the change contested. Below threshold or Jev unavailable: the orchestrator decides and calls `log_override` when it differs from Jev.
3. Panel: two `executor` reviewers in one message, one on the executor's default model, one on the next model on the ladder. Each gets a review task section with an empty `Scope:`, so the scope lock denies every edit (read-only by structure, not by instruction). Fable is never on the panel.
4. The orchestrator is the lead judge, using `lead-judgment.md`. Each "Act on" finding becomes a new PLAN.md task and goes through the normal TDD gate and dispatch. "Consider" items go to the user in the final report.

### 5.5 Step 9, finish: cleanup task before review

New order: build tasks done -> interrogate if gated (5.4) -> **cleanup task** -> delete `active.json` -> `/wreview` -> `superpowers:verification-before-completion` -> `/commit`.

The cleanup task is one executor on its default model. Its `Scope:` is the files in the diff; its section points to `{{CD}}/pstack/cleanup.md`; `Done:` includes "behavior unchanged" and the project's test command passing. It is skipped when the diff touches only documentation. It runs before review because it changes code.

### 5.6 Codex

`codex/skills/orchestrate/SKILL.md` gets the same steps: RCA before switching to the stronger model, `needs_interrogate`, a two-reviewer panel of Codex sub-agents (cheaper model, then stronger), cleanup before `$wreview`. Without sub-agents, Codex runs one review pass itself with the interrogate prompt and rubric, and states that it did. The review section's empty `Scope:` still applies through Codex's scope-lock hook.

New Codex skills `$interrogate` and `$benchmark-checklist` read the same files under `{{CD}}/pstack/`.

## 6. Cost (spec question 4)

| Event | Added work |
|---|---|
| Every `/orchestrate` run | 1 Jev noul (`needs_interrogate`, about $0.00004), 1 default-model cleanup executor (skipped for docs-only diffs) |
| Gated run (architectural or contested) | 2 read-only reviewers: 1 default model, 1 next rung. Expected on a minority of runs |
| Escalation | RCA by the orchestrator, no new agents. Saves climbs when the cause is a plan defect |
| Perf task | Extra runs the checklist demands (5+ per side), only when numbers are reported |

The cheap-first ladder is untouched: the panel never includes Fable, and nothing starts a build task above its rung.

**Jev decides when interrogate runs**, through the new narrow question in 5.4, with the user and the design able to force it. Its override rate shows up in `/tune` like every other question.

**Success check after rollout:** compare two weeks of `/tune` before and after: Sonnet -> Opus and Opus -> Fable counts and reasons (expect fewer climbs and some "plan fixed, same rung" reasons), and the `needs_interrogate` override rate (high overrides mean the question needs rewording).

## 7. Collisions (spec question 5)

| Pair | Resolution |
|---|---|
| `why` vs `superpowers:systematic-debugging` | `why` is not vendored; systematic-debugging owns the RCA step |
| deslop / cleanup vs `/wreview` | Cleanup is a reference file an executor reads (executors have no Skill tool), not a skill, so it cannot trigger. It edits; `/wreview` only reviews, and runs after it |
| `interrogate` vs `superpowers:requesting-code-review` and other review skills | `disable-model-invocation: true`. It runs only from orchestrate's gated step (which reads the SKILL.md by path) or when the user types `/interrogate` |
| `benchmark-checklist` vs other benchmark skills a user may have | Same `disable-model-invocation: true`; reached by path from PLAN.md `Done:` lines and the CLAUDE.md block |
| Skill names vs our commands and Superpowers | A test asserts no vendored skill name equals `orchestrate`, `wplan`, `wreview`, `commit`, `tune`, `handoff` or any Superpowers skill |
| Users who also install the pstack plugin | Its skills are namespaced `pstack:*`; ours are bare names with model invocation off, so neither fires the other. Documented, not prevented |

## 8. Installer (spec question 6)

- **Component** `pstack-picks`, on by default, added to `OPTIONAL` in `install/run_cmd.py`. `--no-pstack-picks` comes from the existing flag loop. Both wrappers' usage lines list it.
- **Not in `components.json`.** That file lists third-party install commands and plugin version pins, and `thirdparty()` warns when a pinned plugin is missing. pstack-picks fetches nothing; an entry would raise a false warning. Its pin is `claude/pstack/UPSTREAM.md`.
- **File gating.** `_plan_files` replaces its hardcoded `ruflo/` check with a map `{"ruflo": ["ruflo/"], "pstack-picks": ["pstack/", "skills/interrogate/", "skills/benchmark-checklist/"]}`. `codex_target` installs `interrogate` and `benchmark-checklist` only when the component is selected.
- **Text gating.** `executor.md`, both orchestrate skills, `CLAUDE.md.template` and the Codex `AGENTS.md.template` wrap pstack lines in `<!-- pstack-picks -->` ... `<!-- /pstack-picks -->`. `render.rendered()` keeps the inner text and drops the markers when the component is on, and drops the whole block when it is off. That keeps `--no-pstack-picks` installs byte-identical and leaves no dangling paths.
- **Jev threshold.** `thresholds.py` `DEFAULTS` gains `"interrogate": {"min_confidence": 0.7}`. The user-owned `thresholds.json` is never rewritten; the default covers it.
- **Upgrade and uninstall.** No new code: files are recorded and removed as today. As with other components, re-installing with `--no-pstack-picks` does not remove an earlier install; `--uninstall` removes everything. `docs/install.md` says so.
- **Portability (CONTRIBUTING.md).** Markdown only: no scripts, no interpreter paths, `{{CD}}` tokens for paths, UTF-8. The renderer change is Python stdlib. `test_portability.py` already scans `claude/`, `codex/` and `install/`; `test_md_files_use_tokens` is extended to `claude/pstack/**`.

### Layout

```
claude/pstack/                       installed to {{CD}}/pstack/
  LICENSE                            pstack-claude MIT (Lauren Tan, Michael Denyer), verbatim
  LICENSE-cursor-team-kit            cursor-team-kit MIT (Cursor), verbatim, for deslop
  NOTICE.md                          what is vendored, from where, under which license
  UPSTREAM.md                        file -> upstream path @ commit, edits made
  interrogate/reviewer-prompt.md
  interrogate/rubric.md
  interrogate/code-quality-review.md
  interrogate/lead-judgment.md
  cleanup.md                         deslop verbatim + comment keep-list rules
  benchmark-checklist.md
  principles/fix-root-causes.md
  principles/prove-it-works.md
  principles/subtract-before-you-add.md
  principles/test-behavior-not-implementation.md
  principles/guard-the-context-window.md
claude/skills/interrogate/SKILL.md          Claude entry point
claude/skills/benchmark-checklist/SKILL.md  Claude entry point
codex/skills/interrogate/SKILL.md           Codex entry point
codex/skills/benchmark-checklist/SKILL.md   Codex entry point
NOTICE.md                                   repo root: third-party material in this repo
```

## 9. Tests (spec question 7)

New `install/tests/test_pstack_picks.py`:

1. **Ships and installs.** An install with the component writes every file in the layout under the temp Claude dir. An install with `--no-pstack-picks` writes none, and the installed `executor.md`, orchestrate `SKILL.md` and CLAUDE.md block contain no `pstack` text and no markers.
2. **Byte-identical off.** With the component off, installed `executor.md` and orchestrate `SKILL.md` equal the rendered files from before this change (fixture copies).
3. **Codex.** `--harness codex` installs `interrogate` and `benchmark-checklist` under `~/.agents/skills` only with the component on.
4. **References resolve.** Every relative Markdown link and every `{{CD}}/...` path in `claude/pstack/**`, the two skills, `executor.md` and both orchestrate skills points to a file that ships.
5. **No leaks.** Vendored files (except LICENSE, LICENSE-cursor-team-kit, NOTICE.md, UPSTREAM.md) match none of: `poteto`, `pstack:`, `setup-pstack`, `pstack-models`, `effort-`, whole-word `opus|fable|sonnet|haiku` (case-insensitive), `just do it`, `never block`, `readonly`.
6. **No collisions.** Skill `name:` values are not in our command list or the Superpowers skill list, and both skills set `disable-model-invocation: true`.
7. **License travels.** Both LICENSE files and NOTICE.md install next to the vendored text.
8. **Uninstall** removes every pstack-picks file and the CLAUDE.md block lines.

Existing tests updated: `test_run_cmd` component lists, the Jev thresholds test for the new default, `test_md_files_use_tokens` scope. `test_codex_enabled_stages` stays as is (no new hook stages).

Gate before merge: `python -m pytest -q claude/jev/tests install/tests claude/ruflo/tests`, `node claude/ruflo/tests/test_ns.cjs`, `python tools/deny_scan.py claude/pstack` (vendored prose could hit a private deny term), CI green on macOS, Ubuntu and Windows.

## 10. Docs and credits (spec question 8)

- **README.md.** Credits: "[pstack](https://github.com/cursor/plugins/tree/main/pstack) by Lauren Tan, Claude Code port [pstack-claude](https://github.com/michael-denyer/pstack-claude) by Michael Denyer; deslop from Cursor's cursor-team-kit (all MIT)". Replace "Third-party code is not vendored here" with "Third-party code is fetched from upstream, except a few adapted pstack files in `claude/pstack/` (see [NOTICE.md](NOTICE.md))". Recommended-stack table row: pstack picks, `--no-pstack-picks`.
- **NOTICE.md (new, repo root).** Lists vendored material, upstream commits, copyright holders, license files; points to `claude/pstack/NOTICE.md` and `UPSTREAM.md`.
- **docs/workflow.md.** §2 layers table row: "pstack picks (vendored, optional) | review, cleanup and perf references, executor principles | route, pick models, add hooks, or run without a trigger". Edits to §3 (RCA before each climb), §4 steps 4, 7, 8/9 and the new interrogate and cleanup steps, §6 thresholds table (`interrogate`), §9 table (two skills), "Last updated".
- **docs/harnesses.md.** Codex gets `$interrogate`, `$benchmark-checklist` and the shared references; its panel uses Codex sub-agents. Claude Code only: the executor-based read-only panel through the scope lock.
- **docs/install.md.** Components row, flags row, upgrade note.

## 11. Outside this repo (manual, after merge, each asks first)

1. `~/.claude/release/public-manifest.txt` needs `pstack/`, `skills/interrogate/` and `skills/benchmark-checklist/`, or the next `export.sh` run will not carry them and could drop them from the public repo.
2. Re-run the installer to update the live `~/.claude`; refresh `~/.claude/DryasWorkflow.md` and its backup `Dev/docs/DryasWorkflow.md`.
3. FlowObserve: no change. No new loop stage; interrogate and cleanup sit inside Review. `needs_interrogate` appears in Jev MCP logs like any other question.

## 12. Not in scope

- Having the orchestrator rerun each task's `Done:` test command instead of trusting the executor's report (a prove-it-works gap found during this design). Candidate follow-up.
- Sync tooling for upstream pstack.
- Any other pstack skill or principle.
