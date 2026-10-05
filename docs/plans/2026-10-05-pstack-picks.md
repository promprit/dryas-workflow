# pstack picks Implementation Plan

> **For agentic workers:** run this plan with `/orchestrate` (Dryas Workflow). Each task's header block (Goal, Scope, Done, Failing test first) is its `.orchestrate/PLAN.md` section; the Files, Interfaces and Steps below it are the detail the executor follows. Steps use checkbox (`- [ ]`) syntax. `superpowers:subagent-driven-development` and `executing-plans` are denied in this workflow; do not use them.

**Goal:** Ship an optional `pstack-picks` installer component that vendors interrogate, cleanup (deslop + comment rules), the benchmark checklist and five principles from pstack, and wires them, plus an RCA step before each escalation, into the orchestrate loop.

**Architecture:** Vendored Markdown lives once under `claude/pstack/` and installs to `{{CD}}/pstack/`. Thin entry-point skills exist per harness. Shared files (`executor.md`, both orchestrate skills, both rules templates) carry `<!-- pstack-picks -->` blocks that a new `render.gate_blocks()` keeps or strips by component, so `--no-pstack-picks` installs stay byte-identical to today.

**Tech Stack:** Python 3.9+ stdlib (installer, Jev), Markdown, pytest/unittest.

**Spec:** [docs/specs/2026-10-05-pstack-picks-design.md](../specs/2026-10-05-pstack-picks-design.md). Executors read the spec section their task names.

## Global Constraints

- Upstream: `https://github.com/michael-denyer/pstack-claude` at commit `dc8e617f179cf0bdc68b61e672f33e9eb64c20cf`, MIT. `deslop` is cursor-team-kit, MIT.
- Component name `pstack-picks`, flag `--no-pstack-picks`, on by default. Not added to `install/components.json`.
- Marker lines are exactly `<!-- pstack-picks -->` and `<!-- /pstack-picks -->`, each alone on its line.
- Vendored and entry-point text never contains `poteto`, `pstack:`, `setup-pstack`, `pstack-models`, `effort-`, whole-word `opus|fable|sonnet|haiku`, `just do it`, `never block`, `readonly` (case-insensitive). Exempt: `claude/pstack/LICENSE`, `claude/pstack/LICENSE-cursor-team-kit`, `claude/pstack/NOTICE.md`, `claude/pstack/UPSTREAM.md`. The Claude orchestrate skill already owns model policy and may name models inside its blocks.
- Codex skills never contain `mcp__`, `Agent tool`, `/usr/bin/python3`, `subagent_type`, `Fable` (existing `test_codex_templates` rule).
- Paths in shipped Markdown use `{{CD}}`; the CLAUDE.md template keeps its existing literal `~/.claude/` style.
- Portability: CONTRIBUTING.md rules. Python stdlib only, `encoding="utf-8"`, no shell scripts, no hardcoded interpreter.
- `install/dryas_install.py` stays under 500 lines (481 today).
- Full gate: `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests` and `node claude/ruflo/tests/test_ns.cjs`.

## Review Focus

1. Re-install with `--no-pstack-picks` after a full install: the vendored files stay (no removal by design), so the gated text in `executor.md` must stay too. Owner: Task 3 (`test_reinstall_without_keeps_text`).
2. A marker opened and never closed in a shipped file: the install must abort before writing anything, not install half a block. Owner: Task 3 (`test_unclosed_marker_aborts_before_write`).
3. An HTML comment that is not a component marker (for example `<!-- dryas:start -->`) must pass through untouched. Owner: Task 3 (`test_gate_blocks_ignores_other_comments`).
4. Codex-only install without the component: no `$interrogate` skill, and the AGENTS.md block has no pstack line. Owner: Task 3 (`test_codex_skills_gated`).
5. Interrogate reviewers dispatched while build tasks are still in `active.json` would inherit their globs and could edit. The skills must say reviewers dispatch only after every build task has left `active.json`. Owner: Task 5 (`test_orchestrate_on_content` asserts that sentence).

## Task order

```
Task 1 (vendor text) ─┐
Task 3 (installer) ───┼─> Task 2 (entry skills) ─> Task 5 (loop text)
Task 4 (Jev default) ─┘                         └─> Task 6 (docs)
```

Tasks 1, 3 and 4 have disjoint scopes and can run in parallel. Tasks 5 and 6 can run in parallel.

---

### Task 1: Vendor pstack text

```
## Task 1: Vendor pstack text
Goal: Add the adapted pstack Markdown, licenses, NOTICE and UPSTREAM under claude/pstack/.
Scope:
- claude/pstack/**
- install/tests/test_pstack_content.py
Done:
- python3 -m pytest -q install/tests/test_pstack_content.py passes
- python3 -m pytest -q install/tests/test_portability.py passes
Failing test first: install/tests/test_pstack_content.py :: PstackContentTest.test_layout_complete
```

**Files:**
- Create: `claude/pstack/{LICENSE,LICENSE-cursor-team-kit,NOTICE.md,UPSTREAM.md,cleanup.md,benchmark-checklist.md}`
- Create: `claude/pstack/interrogate/{reviewer-prompt,rubric,code-quality-review,lead-judgment}.md`
- Create: `claude/pstack/principles/{fix-root-causes,prove-it-works,subtract-before-you-add,test-behavior-not-implementation,guard-the-context-window}.md`
- Test: `install/tests/test_pstack_content.py`

**Interfaces:**
- Produces: the paths above. Tasks 2 and 5 link to them as `{{CD}}/pstack/<path>`. Tasks 2 and 5 import `LEAK` from `test_pstack_content`.

- [ ] **Step 1: Write the failing test**

```python
# install/tests/test_pstack_content.py
import re, unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
PSTACK = REPO / "claude" / "pstack"
LAYOUT = ["LICENSE", "LICENSE-cursor-team-kit", "NOTICE.md", "UPSTREAM.md", "cleanup.md", "benchmark-checklist.md",
          "interrogate/reviewer-prompt.md", "interrogate/rubric.md", "interrogate/code-quality-review.md",
          "interrogate/lead-judgment.md", "principles/fix-root-causes.md", "principles/prove-it-works.md",
          "principles/subtract-before-you-add.md", "principles/test-behavior-not-implementation.md",
          "principles/guard-the-context-window.md"]
EXEMPT = {"LICENSE", "LICENSE-cursor-team-kit", "NOTICE.md", "UPSTREAM.md"}
LEAK = re.compile(r"poteto|pstack:|setup-pstack|pstack-models|effort-|\b(opus|fable|sonnet|haiku)\b|just do it|never block|readonly",
                  re.I)
LINK = re.compile(r"\]\(([^)#:]+)(#[^)]*)?\)")


def vendored():
    return [p for p in PSTACK.rglob("*") if p.is_file() and p.relative_to(PSTACK).as_posix() not in EXEMPT]


class PstackContentTest(unittest.TestCase):
    def test_layout_complete(self):
        have = sorted(p.relative_to(PSTACK).as_posix() for p in PSTACK.rglob("*") if p.is_file())
        self.assertEqual(have, sorted(LAYOUT))

    def test_no_leaks(self):
        hits = ["%s:%d" % (p.relative_to(REPO).as_posix(), n)
                for p in vendored() for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                if LEAK.search(line)]
        self.assertEqual(hits, [])

    def test_no_frontmatter_or_home_paths(self):
        for p in vendored():
            t = p.read_text(encoding="utf-8")
            self.assertFalse(t.startswith("---"), p)
            self.assertNotIn("~/", t, p)

    def test_relative_links_resolve(self):
        for p in vendored():
            for m in LINK.finditer(p.read_text(encoding="utf-8")):
                self.assertTrue((p.parent / m.group(1)).resolve().is_file(), (p, m.group(1)))

    def test_licenses_verbatim_holders(self):
        lic = (PSTACK / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Copyright (c) 2026 Lauren Tan", lic)
        self.assertIn("Copyright (c) 2026 Michael Denyer", lic)
        self.assertIn("Cursor", (PSTACK / "LICENSE-cursor-team-kit").read_text(encoding="utf-8"))

    def test_upstream_lists_every_vendored_file(self):
        up = (PSTACK / "UPSTREAM.md").read_text(encoding="utf-8")
        self.assertIn("dc8e617f179cf0bdc68b61e672f33e9eb64c20cf", up)
        for rel in LAYOUT:
            if rel not in EXEMPT:
                self.assertIn("`%s`" % rel, up, rel)

    def test_cleanup_keeps_deslop_and_keep_list(self):
        t = (PSTACK / "cleanup.md").read_text(encoding="utf-8")
        for s in ("Casts to `any` used only to bypass type issues", "Keep behavior unchanged unless fixing a clear bug.",
                  "Legal or license headers.", "Doc comments that define a public API contract."):
            self.assertIn(s, t)
        for s in ("/how", "/why", "/architect", "comment-sicko", "MUST KILL"):
            self.assertNotIn(s, t)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q install/tests/test_pstack_content.py`
Expected: FAIL in `test_layout_complete` (`claude/pstack` does not exist, so `have == []`).

- [ ] **Step 3: Fetch upstream at the pinned commit (scratch dir, outside the repo) and copy**

```bash
S="$(python3 -c 'import tempfile;print(tempfile.mkdtemp())')"
git clone -q https://github.com/michael-denyer/pstack-claude "$S/pstack"
git -C "$S/pstack" checkout -q dc8e617f179cf0bdc68b61e672f33e9eb64c20cf
U="$S/pstack/plugins/pstack/skills"
mkdir -p claude/pstack/interrogate claude/pstack/principles
cp "$S/pstack/LICENSE" claude/pstack/LICENSE
cp "$S/pstack/LICENSE-cursor-team-kit" claude/pstack/LICENSE-cursor-team-kit
for f in reviewer-prompt rubric code-quality-review lead-judgment; do cp "$U/interrogate/references/$f.md" "claude/pstack/interrogate/$f.md"; done
for f in fix-root-causes prove-it-works subtract-before-you-add test-behavior-not-implementation guard-the-context-window; do
  python3 - "$U/principle-$f/SKILL.md" "claude/pstack/principles/$f.md" <<'EOF'
import sys
t = open(sys.argv[1], encoding="utf-8").read()
body = t.split("---", 2)[2].lstrip("\n")
open(sys.argv[2], "w", encoding="utf-8", newline="\n").write(body)
EOF
done
cp "$U/benchmark-checklist/SKILL.md" claude/pstack/benchmark-checklist.md
```

- [ ] **Step 4: Apply the recorded edits and write the new files**

`claude/pstack/principles/prove-it-works.md`: replace `Commit it only for large or complex work where the trail has to be auditable later, like a big port or migration (the **show-me-your-work** skill).` with `Commit it only for large or complex work where the trail has to be auditable later, like a big port or migration.`

`claude/pstack/benchmark-checklist.md`:
1. Delete the frontmatter (the first `---` block through its closing `---` and the blank line after it).
2. Replace `[Explain the Number](../principle-explain-the-number/SKILL.md) says why.` with `A number you cannot explain may be measuring something other than the work.`
3. Replace `- Keep a PR body to one primary number, per the **Opening a PR** playbook. Put the runs, the range, and the limiter evidence in a linked artifact or a notes file.` with `- Keep a PR body or final report to one primary number. Put the runs, the range, and the limiter evidence in a linked artifact or a notes file.`
4. Delete the section `## How this fits the other perf material` through the end of the file.

The four interrogate references stay verbatim. Run the leak test; if a line hits, reword only that line and add the edit to UPSTREAM.md.

Create `claude/pstack/cleanup.md`:

```markdown
# Cleanup

Run on the files in your Scope after the build tasks pass and before review. Two passes: slop, then comments. Keep behavior unchanged. Run the test command in your Done criteria before you report.

## Pass 1: remove AI code slop

Check the diff against the base branch and remove AI-generated slop introduced in the branch.

### Focus Areas

- Extra comments that are unnecessary or inconsistent with local style
- Defensive checks or try/catch blocks that are abnormal for trusted code paths
- Casts to `any` used only to bypass type issues
- Deeply nested code that should be simplified with early returns
- Other patterns inconsistent with the file and surrounding codebase

### Guardrails

- Keep behavior unchanged unless fixing a clear bug.
- Prefer minimal, focused edits over broad rewrites.
- Keep the final summary concise (1-3 sentences).

## Pass 2: comments

Delete every comment in scope that is not on this keep-list:

- Legal or license headers.
- Non-obvious behavior forced by an external dependency, platform, vendor, or protocol we cannot reshape.
- `// prettier-ignore`. Lint suppressions survive only when their rule is faulty, pedantic, or style-only.
- Doc comments that define a public API contract.
- Issue or RFC links that explain a constraint code cannot express.

Rules:

- A comment that explains a surprise in our own code is deleted. Name the symbol under UNRESOLVED as a refactor target (rename, extract, type) that would make the behavior obvious. Do not do that refactor here.
- A suppression (`eslint-disable`, `@ts-ignore`, `@ts-expect-error`, `# noqa`, `# type: ignore`) whose rule protects correctness or safety is a finding, not a keep. Leave it and report it under UNRESOLVED.
- A comment that claims a constraint (`IMPORTANT`, `do not remove`, `talk to X before changing`) stays only if nearby code or `git log -S '<text>'` shows the constraint is real and foreign. If you cannot check it, keep the comment and report it under UNRESOLVED. Never invent a reason.
- Touch comments only. Never change application code in this pass.

Report: files touched, comments deleted, comments kept with the keep-list reason, and UNRESOLVED items.
```

Create `claude/pstack/NOTICE.md`:

```markdown
# Notice

The files in this folder are adapted from MIT-licensed work. The license texts are next to this file.

| Files | Upstream | Copyright | License |
|---|---|---|---|
| `interrogate/*`, `principles/*`, `benchmark-checklist.md`, `cleanup.md` (Pass 2 rules) | [pstack-claude](https://github.com/michael-denyer/pstack-claude) @ `dc8e617`, a port of [cursor/plugins/pstack](https://github.com/cursor/plugins/tree/main/pstack) | (c) 2026 Lauren Tan; port (c) 2026 Michael Denyer | MIT, [LICENSE](LICENSE) |
| `cleanup.md` (Pass 1, deslop) | [cursor/plugins/cursor-team-kit](https://github.com/cursor/plugins/tree/main/cursor-team-kit) via pstack-claude @ `dc8e617` | (c) 2026 Cursor | MIT, [LICENSE-cursor-team-kit](LICENSE-cursor-team-kit) |

Changes made for the Dryas Workflow are listed per file in [UPSTREAM.md](UPSTREAM.md).
```

Create `claude/pstack/UPSTREAM.md`:

```markdown
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
| `cleanup.md` | `skills/deslop/SKILL.md` (Pass 1), `agents/comment-sicko.md` keep-list (Pass 2) | Pass 1 verbatim except "main" became "the base branch"; Pass 2 rewritten: persona, agent, `/how` `/why` `/architect` calls and kill flags removed; unverifiable constraints are kept and reported |

Not taken: `poteto-mode` and its hooks, `why`, `how`, `architect`, `arena`, `swarm`, `tdd`, `babysit`, the `no-comments` skill, the `comment-sicko` agent, `setup-pstack`, `models.json`, the other principles.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest -q install/tests/test_pstack_content.py install/tests/test_portability.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add claude/pstack install/tests/test_pstack_content.py
git commit -m "feat(pstack): vendor adapted pstack references under claude/pstack"
```

---

### Task 2: Entry-point skills (Claude Code and Codex)

```
## Task 2: Entry-point skills
Goal: Add interrogate and benchmark-checklist skills for Claude Code and Codex that read the shared claude/pstack files.
Scope:
- claude/skills/interrogate/**
- claude/skills/benchmark-checklist/**
- codex/skills/interrogate/**
- codex/skills/benchmark-checklist/**
- install/tests/test_pstack_skills.py
Done:
- python3 -m pytest -q install/tests/test_pstack_skills.py install/tests/test_codex_templates.py install/tests/test_shipped_files.py passes
Failing test first: install/tests/test_pstack_skills.py :: PstackSkillsTest.test_skills_exist
```

Depends on Task 1 (link targets, `LEAK`) and Task 3 (`ct.PSTACK_SKILLS`).

**Files:**
- Create: `claude/skills/interrogate/SKILL.md`, `claude/skills/benchmark-checklist/SKILL.md`
- Create: `codex/skills/interrogate/SKILL.md`, `codex/skills/benchmark-checklist/SKILL.md`
- Test: `install/tests/test_pstack_skills.py`

**Interfaces:**
- Consumes: `claude/pstack/**` and `test_pstack_content.LEAK` (Task 1); `codex_target.PSTACK_SKILLS == ("interrogate", "benchmark-checklist")` (Task 3).
- Produces: skill names `interrogate`, `benchmark-checklist`; `test_pstack_skills.CD_PATH` regex (used by Task 5). Task 5 refers to `{{CD}}/skills/interrogate/SKILL.md`.

- [ ] **Step 1: Write the failing test**

```python
# install/tests/test_pstack_skills.py
import re, sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import codex_target as ct
from test_pstack_content import LEAK
REPO = HERE.parents[1]
NAMES = ("interrogate", "benchmark-checklist")
OURS = {"orchestrate", "wplan", "wreview", "commit", "tune", "handoff"}
SUPERPOWERS = {"brainstorming", "using-git-worktrees", "test-driven-development", "requesting-code-review",
               "receiving-code-review", "verification-before-completion", "writing-plans", "systematic-debugging",
               "subagent-driven-development", "executing-plans", "dispatching-parallel-agents",
               "finishing-a-development-branch", "diagnosing-superpowers", "writing-skills", "using-superpowers"}
CD_PATH = re.compile(r"\{\{CD\}\}/([A-Za-z0-9_./-]+)")


def skill(h, n):
    return (REPO / h / "skills" / n / "SKILL.md").read_text(encoding="utf-8")


class PstackSkillsTest(unittest.TestCase):
    def test_skills_exist(self):
        for h in ("claude", "codex"):
            for n in NAMES:
                self.assertTrue(skill(h, n).startswith("---\nname: %s\ndescription: " % n), (h, n))
        self.assertEqual(tuple(ct.PSTACK_SKILLS), NAMES)

    def test_claude_skills_not_model_invoked(self):
        for n in NAMES:
            head = skill("claude", n).split("---", 2)[1]
            self.assertIn("\ndisable-model-invocation: true\n", head, n)

    def test_no_name_collisions(self):
        for n in NAMES:
            self.assertNotIn(n, OURS | SUPERPOWERS)

    def test_no_leaks(self):
        for h in ("claude", "codex"):
            for n in NAMES:
                for i, line in enumerate(skill(h, n).splitlines(), 1):
                    self.assertIsNone(LEAK.search(line), (h, n, i, line))

    def test_cd_paths_resolve(self):
        for h in ("claude", "codex"):
            for n in NAMES:
                for rel in CD_PATH.findall(skill(h, n)):
                    self.assertTrue((REPO / "claude" / rel.rstrip(".")).exists(), (h, n, rel))

    def test_interrogate_read_only_panel(self):
        t = skill("claude", "interrogate")
        self.assertIn("Scope:\n(none: read-only review)", t)
        self.assertIn("never the top rung", t)
        self.assertIn("after every build task has left `.orchestrate/active.json`", t)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q install/tests/test_pstack_skills.py`
Expected: FAIL with `FileNotFoundError` for `claude/skills/interrogate/SKILL.md`.

- [ ] **Step 3: Write the four skills**

`claude/skills/interrogate/SKILL.md`:

````markdown
---
name: interrogate
description: Adversarial review of a finished change by two reviewers on different models, then a lead verdict. Runs from the orchestrate skill's gated interrogate step or when the user types /interrogate. Not for routine review; /wreview covers that.
disable-model-invocation: true
---

# Interrogate

Two reviewers on different models challenge one change. The signal comes from model diversity, not personas. The deliverable is a verdict. Change nothing yourself.

## 1. Scope

Default: the diff from the merge-base with the default branch to HEAD, plus uncommitted changes in the worktree. Use the files or diff the user names instead, if any. Note the context files a reviewer needs to understand the change.

## 2. Intent

Write one paragraph stating the intent, from the approved design or spec, the PLAN.md goals and the commit messages. If you are unsure of the intent, ask the user before going on.

## 3. Reviewers

Read `{{CD}}/pstack/interrogate/reviewer-prompt.md` and fill it with the intent, the diff (or the exact command that prints it), `{{CD}}/pstack/interrogate/rubric.md` and `{{CD}}/pstack/interrogate/code-quality-review.md`. Both reviewers get the same filled prompt.

Inside `/orchestrate`, dispatch only after every build task has left `.orchestrate/active.json`. Add one section per reviewer to `.orchestrate/PLAN.md`:

```
## Task <N>: interrogate reviewer <A|B>
Goal: Adversarial review of the change; report findings only.
Scope:
(none: read-only review)
Done:
- Findings returned in the reviewer-prompt output format
Failing test first: none (review)
```

Put both ids in `.orchestrate/active.json`. The empty Scope makes the scope lock deny every edit. Dispatch both in one message with `subagent_type: executor`: reviewer A on the executor's default model, reviewer B on the next model on the ladder (the orchestrate skill names it), never the top rung. Remove both ids when they return.

Outside `/orchestrate`, dispatch the same two reviewers with "Do not edit any file" at the top of the prompt.

## 4. Synthesize

1. Parse all findings.
2. Consensus: a finding both reviewers raised independently is the highest signal.
3. Lone findings: still read them, weight them lower.
4. Deduplicate: merge findings that describe the same issue; note who raised it.
5. Disagreements: when one reviewer flags something the other explicitly clears, record both.

## 5. Lead judgment

You are the lead reviewer. Read `{{CD}}/pstack/interrogate/lead-judgment.md` and put every finding in one bucket: **Act on**, **Consider**, **Noted** or **Dismissed**, each with the reviewer(s) who raised it and a one-line rationale.

## Output

### Intent
> the paragraph from step 2

### Reviewers
- Reviewer A: default model, N findings
- Reviewer B: next model on the ladder, N findings

### Act On
### Consider
### Noted
### Dismissed
### Agreement Map

## After the verdict (inside `/orchestrate`)

Each Act On finding becomes a new PLAN.md task and goes through the TDD gate and dispatch like any task. Consider items go to the user in the final report.
````

`claude/skills/benchmark-checklist/SKILL.md`:

```markdown
---
name: benchmark-checklist
description: Vet a performance number you measured (limiter, tuning, limits, errors, repeatability, relevance, whether the work ran) before you report or act on it. Runs from a PLAN.md Done line, the CLAUDE.md rule, or /benchmark-checklist.
disable-model-invocation: true
---

# Benchmark checklist

Read `{{CD}}/pstack/benchmark-checklist.md` in full. Answer each of its questions with evidence from a run, not a guess about the code. Report in its Report format: verdict first, then the number with unit, run count, range and limiter. Call the result inconclusive when its rules say so.
```

`codex/skills/interrogate/SKILL.md`:

```markdown
---
name: interrogate
description: Adversarial review of a finished change by two reviewers on different models, then a lead verdict. Use for $interrogate or the gated interrogate step of $orchestrate; not for routine review ($wreview covers that).
---

# Interrogate (Codex)

1. **Scope.** The diff from the merge-base with the default branch to HEAD plus uncommitted changes, or what the user names.
2. **Intent.** One paragraph from the approved design, the plan goals and the commit messages. Unsure: ask the user.
3. **Reviewers.** Fill `{{CD}}/pstack/interrogate/reviewer-prompt.md` with the intent, the diff, `{{CD}}/pstack/interrogate/rubric.md` and `{{CD}}/pstack/interrogate/code-quality-review.md`. Inside `$orchestrate`, start only after every build task has left `.orchestrate/active.json`. Run two Codex sub-agents with the same prompt: one on a cheaper model, one on a stronger model. They never edit files. Without sub-agents, run one review pass yourself with that prompt and say so in the verdict.
4. **Synthesize.** Consensus findings first, lone findings weighted lower, duplicates merged, disagreements recorded.
5. **Lead judgment.** Follow `{{CD}}/pstack/interrogate/lead-judgment.md`. Buckets: Act On, Consider, Noted, Dismissed, each with who raised it and a one-line reason. End with an Agreement Map.
6. Change nothing. Inside `$orchestrate`, each Act On item becomes a new plan task.
```

`codex/skills/benchmark-checklist/SKILL.md`:

```markdown
---
name: benchmark-checklist
description: Vet a performance number you measured before you report or act on it. Use for $benchmark-checklist or when a plan task's Done line asks for it.
---

Read `{{CD}}/pstack/benchmark-checklist.md` in full. Answer each question with evidence from a run. Report in its Report format: verdict first, then the number with unit, run count, range and limiter.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest -q install/tests/test_pstack_skills.py install/tests/test_codex_templates.py install/tests/test_shipped_files.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/interrogate claude/skills/benchmark-checklist codex/skills/interrogate codex/skills/benchmark-checklist install/tests/test_pstack_skills.py
git commit -m "feat(pstack): interrogate and benchmark-checklist skills for Claude Code and Codex"
```

---

### Task 3: Installer component and text gating

```
## Task 3: Installer component pstack-picks
Goal: Add the pstack-picks component, --no-pstack-picks, file gating and <!-- pstack-picks --> text gating for Claude and Codex installs.
Scope:
- install/run_cmd.py
- install/render.py
- install/dryas_install.py
- install/codex_target.py
- install/install.sh
- install/install.ps1
- install/tests/test_pstack_install.py
- install/tests/test_run_cmd.py
Done:
- python3 -m pytest -q install/tests passes
- wc -l install/dryas_install.py is under 500
Failing test first: install/tests/test_pstack_install.py :: GateBlocksTest.test_on_keeps_body_drops_markers
```

**Files:**
- Modify: `install/run_cmd.py` (`OPTIONAL`, `components()`, usage docstring)
- Modify: `install/render.py` (new `GATED`, `gate_blocks()`; `rendered()` calls it)
- Modify: `install/dryas_install.py` (`COMPONENT_DIRS` in `_plan_files`, `copy_files` text components, `_prevalidate`, `claude_md` call)
- Modify: `install/codex_target.py` (`PSTACK_SKILLS`, `skills_for()`, gate AGENTS.md and skill text)
- Modify: `install/install.sh:3`, `install/install.ps1:2` (usage comment lines)
- Modify: `install/tests/test_run_cmd.py:19-20`
- Test: `install/tests/test_pstack_install.py`

**Interfaces:**
- Produces: `render.GATED: Tuple[str, ...] = ("pstack-picks",)`; `render.gate_blocks(text: str, comps: Iterable[str]) -> str` (raises `ValueError` on an unclosed or unopened marker); `dryas_install.COMPONENT_DIRS: Dict[str, Tuple[str, ...]]`; `codex_target.PSTACK_SKILLS = ("interrogate", "benchmark-checklist")`; `codex_target.skills_for(comps: List[str]) -> Tuple[str, ...]`.
- Consumes: nothing from other tasks (tests use fixture repos).

- [ ] **Step 1: Write the failing test**

```python
# install/tests/test_pstack_install.py
import io, os, shutil, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import codex_target as ct
import dryas_install as di
import render
import run_cmd
REPO = HERE.parents[1]
BLOCK = "a\n<!-- pstack-picks -->\nPICK {{CD}}/pstack/x.md\n<!-- /pstack-picks -->\nb\n"


class GateBlocksTest(unittest.TestCase):
    def test_on_keeps_body_drops_markers(self):
        self.assertEqual(render.gate_blocks(BLOCK, ["core", "pstack-picks"]), "a\nPICK {{CD}}/pstack/x.md\nb\n")

    def test_off_drops_block(self):
        self.assertEqual(render.gate_blocks(BLOCK, ["core"]), "a\nb\n")

    def test_gate_blocks_ignores_other_comments(self):
        t = "<!-- dryas:start -->\nx\n<!-- dryas:end -->\n"
        self.assertEqual(render.gate_blocks(t, ["core"]), t)

    def test_gate_blocks_unclosed_raises(self):
        with self.assertRaises(ValueError):
            render.gate_blocks("<!-- pstack-picks -->\nx\n", ["core"])
        with self.assertRaises(ValueError):
            render.gate_blocks("x\n<!-- /pstack-picks -->\n", ["core"])


class ComponentTest(unittest.TestCase):
    def test_flag(self):
        self.assertIn("pstack-picks", run_cmd.components(run_cmd.parse([])))
        self.assertNotIn("pstack-picks", run_cmd.components(run_cmd.parse(["--no-pstack-picks"])))


def fixture_repo():
    r = Path(tempfile.mkdtemp())
    files = {"claude/agents/executor.md": "exec\n" + BLOCK,
             "claude/pstack/x.md": "x\n", "claude/skills/interrogate/SKILL.md": "s\n",
             "claude/skills/benchmark-checklist/SKILL.md": "b\n",
             "claude/CLAUDE.md.template": "POLICY\n<!-- pstack-picks -->\nBENCH\n<!-- /pstack-picks -->\n",
             "docs/workflow.md": "# W\n"}
    for rel, t in files.items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(t, encoding="utf-8")
    return r


class InstallGatingTest(unittest.TestCase):
    def setUp(self):
        self.repo = fixture_repo()
        self.home = Path(tempfile.mkdtemp())
        self.cd = self.home / ".claude"
        self.cd.mkdir()
        os.environ.pop("DRYAS_DATA_ROOT", None)
        self.saved = (di.run, di.confirm, di.capture)
        di.run, di.confirm, di.capture = (lambda argv, cwd=None: 0), (lambda p: True), (lambda argv, *a, **k: (1, ""))

    def tearDown(self):
        di.run, di.confirm, di.capture = self.saved

    def install(self, comps):
        with redirect_stdout(io.StringIO()):
            return di.install(self.repo, self.cd, comps, home=self.home, yes=True)

    def test_files_gated(self):
        self.install(["core"])
        self.assertFalse((self.cd / "pstack").exists())
        self.assertFalse((self.cd / "skills" / "interrogate").exists())
        self.assertEqual((self.cd / "agents/executor.md").read_text(encoding="utf-8"), "exec\na\nb\n")
        self.assertNotIn("BENCH", (self.cd / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_files_on(self):
        self.install(["core", "pstack-picks"])
        self.assertTrue((self.cd / "pstack/x.md").is_file())
        self.assertTrue((self.cd / "skills/benchmark-checklist/SKILL.md").is_file())
        ex = (self.cd / "agents/executor.md").read_text(encoding="utf-8")
        self.assertIn("PICK %s/pstack/x.md" % str(self.cd).replace("\\", "/"), ex)
        self.assertNotIn("<!--", ex)
        self.assertIn("BENCH", (self.cd / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_reinstall_without_keeps_text(self):
        self.install(["core", "pstack-picks"])
        self.install(["core"])
        self.assertIn("PICK", (self.cd / "agents/executor.md").read_text(encoding="utf-8"))
        self.assertTrue((self.cd / "pstack/x.md").is_file())

    def test_unclosed_marker_aborts_before_write(self):
        (self.repo / "claude/agents/executor.md").write_text("<!-- pstack-picks -->\nx\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.install(["core"])
        self.assertFalse((self.cd / "agents").exists())

    def test_uninstall_removes_pstack(self):
        self.install(["core", "pstack-picks"])
        with redirect_stdout(io.StringIO()):
            di.uninstall(self.cd)
        self.assertFalse((self.cd / "pstack").exists())
        self.assertFalse((self.cd / "skills" / "interrogate").exists())


class CodexGatingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        shutil.copytree(str(REPO / "codex"), str(self.repo / "codex"))
        for n in ct.PSTACK_SKILLS:
            p = self.repo / "codex" / "skills" / n / "SKILL.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("---\nname: %s\ndescription: d\n---\n" % n, encoding="utf-8")
        t = self.repo / "codex" / "AGENTS.md.template"
        t.write_text(t.read_text(encoding="utf-8") + "<!-- pstack-picks -->\nPSTACKLINE\n<!-- /pstack-picks -->\n",
                     encoding="utf-8")
        self.home = self.tmp / "home"
        self.cdx = self.home / ".codex"
        cd = (self.home / ".claude").as_posix()
        self.mapping = {"PY": "/p", "CD": cd, "PY_SAFE": "/p", "CD_SAFE": cd, "HOME": self.home.as_posix(),
                        "DRYAS_DATA_ROOT": "/d"}

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def install(self, comps):
        with redirect_stdout(io.StringIO()):
            return ct.install_codex(self.repo, self.cdx, self.home, comps, self.mapping, {}, lambda argv: 0)

    def test_codex_skills_gated(self):
        self.assertEqual(self.install(["core"]), 0)
        self.assertFalse((ct.skills_dir(self.home) / "interrogate").exists())
        self.assertNotIn("PSTACKLINE", (self.cdx / "AGENTS.md").read_text(encoding="utf-8"))

    def test_codex_skills_on(self):
        self.assertEqual(self.install(["core", "pstack-picks"]), 0)
        for n in ct.PSTACK_SKILLS:
            self.assertTrue((ct.skills_dir(self.home) / n / "SKILL.md").is_file(), n)
        agents = (self.cdx / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("PSTACKLINE", agents)
        self.assertNotIn("<!-- pstack-picks", agents)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q install/tests/test_pstack_install.py`
Expected: FAIL with `AttributeError: module 'render' has no attribute 'gate_blocks'` (collection also fails on `ct.PSTACK_SKILLS`).

- [ ] **Step 3: Implement `gate_blocks` in `install/render.py`**

Add after the imports (`re`, `Iterable`, `Tuple` join the existing imports):

```python
GATED: Tuple[str, ...] = ("pstack-picks",)
_MARK = re.compile(r"^<!-- (/?)(%s) -->\n?" % "|".join(re.escape(g) for g in GATED), re.M)


def gate_blocks(text: str, comps: Iterable[str]) -> str:
    """Keep the body of each <!-- NAME --> ... <!-- /NAME --> block when NAME is selected, else drop it."""
    on, out, pos, open_name = set(comps), [], 0, None
    for m in _MARK.finditer(text):
        closing, name = m.group(1) == "/", m.group(2)
        if closing != (open_name is not None) or (closing and name != open_name):
            raise ValueError("unbalanced <!-- %s%s --> marker" % (m.group(1), name))
        if not closing:
            out.append(text[pos:m.start()])
            open_name = name
        else:
            if open_name in on:
                out.append(text[pos:m.start()])
            open_name = None
        pos = m.end()
    if open_name is not None:
        raise ValueError("unclosed <!-- %s --> marker" % open_name)
    out.append(text[pos:])
    return "".join(out)
```

Change the `.md` branch of `rendered()`:

```python
    if rel.endswith(".md"):
        return sm.render_tokens(gate_blocks(f.read_text(encoding="utf-8"), comps), mapping).encode("utf-8")
```

- [ ] **Step 4: Gate files and text in `install/dryas_install.py`**

Next to `SKIP`:

```python
COMPONENT_DIRS = {"ruflo": ("ruflo/",), "pstack-picks": ("pstack/", "skills/interrogate/", "skills/benchmark-checklist/")}
```

In `_plan_files`, replace the ruflo condition:

```python
        if rel in SKIP or any(rel.startswith(d) and c not in comps for c, ds in COMPONENT_DIRS.items() for d in ds):
            continue
```

In `copy_files`, render text with the recorded components as well, so a re-install without the flag keeps text that matches the files left on disk:

```python
    text_comps = sorted(set(rec.get("components", [])) | set(comps))
    for rel, f in _plan_files(repo, comps):
        if f.is_symlink():
            _put(cd, rel, rec, force, ts, rep, dry, link=os.readlink(str(f)))
        else:
            _put(cd, rel, rec, force, ts, rep, dry, data=_rendered(rel, f, text_comps, mapping, cd), mode_src=f)
```

In `_prevalidate`, add at the end so a bad marker in the template aborts before any write:

```python
    tpl = repo / "claude" / "CLAUDE.md.template"
    if tpl.exists():
        gate_blocks(tpl.read_text(encoding="utf-8"), comps)
```

In `install()`:

```python
        elif claude and tpl.exists():
            claude_md(cd, gate_blocks(tpl.read_text(encoding="utf-8"), comps_all), rec)
```

Import: `from render import chain_bytes, gate_blocks, rendered as _rendered  # noqa: E402`.

- [ ] **Step 5: Component flag in `install/run_cmd.py`**

```python
OPTIONAL = ("jev", "ruflo", "superpowers", "design", "pstack-picks")
```

```python
def components(a: argparse.Namespace) -> List[str]:
    return ["core"] + [c for c in OPTIONAL if not getattr(a, "no_" + c.replace("-", "_"))]
```

Add `[--no-pstack-picks]` after `[--no-design]` in the module docstring, in `install/install.sh` line 3 and in `install/install.ps1` line 2. Update `install/tests/test_run_cmd.py` lines 19-20:

```python
        self.assertEqual(run_cmd.components(run_cmd.parse(["--no-ruflo"])), ["core", "jev", "superpowers", "design", "pstack-picks"])
        self.assertEqual(run_cmd.components(run_cmd.parse([])), ["core", "jev", "ruflo", "superpowers", "design", "pstack-picks"])
```

- [ ] **Step 6: Codex gating in `install/codex_target.py`**

```python
PSTACK_SKILLS = ("interrogate", "benchmark-checklist")


def skills_for(comps: List[str]) -> Tuple[str, ...]:
    return SKILLS + (PSTACK_SKILLS if "pstack-picks" in comps else ())
```

In `install_codex`, use `skills_for(comps)` in the dry-run message and in the skill loop, import `from render import gate_blocks`, and gate both texts:

```python
    insert_block(cdx / "AGENTS.md", sm.render_tokens(gate_blocks(tpl, comps), mapping), rec, "agents_md")
```

```python
        (dest / "SKILL.md").write_text(sm.render_tokens(gate_blocks(text, comps), mapping), encoding="utf-8")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python3 -m pytest -q install/tests && wc -l install/dryas_install.py`
Expected: all PASS; line count under 500.

- [ ] **Step 8: Commit**

```bash
git add install/run_cmd.py install/render.py install/dryas_install.py install/codex_target.py install/install.sh install/install.ps1 install/tests/test_pstack_install.py install/tests/test_run_cmd.py
git commit -m "feat(install): pstack-picks component with file and text gating"
```

---

### Task 4: Jev default for the interrogate threshold

```
## Task 4: Jev interrogate threshold default
Goal: Add interrogate.min_confidence = 0.7 to the Jev threshold defaults.
Scope:
- claude/jev/thresholds.py
- claude/jev/tests/test_thresholds.py
Done:
- python3 -m pytest -q claude/jev/tests passes
Failing test first: claude/jev/tests/test_thresholds.py :: ThresholdsTest.test_interrogate_default
```

**Files:**
- Modify: `claude/jev/thresholds.py:10-30` (`DEFAULTS`)
- Test: `claude/jev/tests/test_thresholds.py`

**Interfaces:**
- Produces: `thresholds.load()["interrogate"]["min_confidence"] == 0.7`. Task 5's orchestrate text refers to it as `interrogate.min_confidence`.

- [ ] **Step 1: Write the failing test** (append to `ThresholdsTest`)

```python
    def test_interrogate_default(self):
        self.assertEqual(thresholds.load()["interrogate"]["min_confidence"], 0.7)
        self.assertIsNone(thresholds.validate("interrogate.min_confidence", 0.8))
        self.assertIsNotNone(thresholds.validate("interrogate.min_confidence", 1.5))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q claude/jev/tests/test_thresholds.py -k interrogate`
Expected: FAIL with `KeyError: 'interrogate'`.

- [ ] **Step 3: Add the default** (after the `"commit"` line in `DEFAULTS`)

```python
    "interrogate": {"min_confidence": 0.7},
```

The shipped `claude/jev/thresholds.json` is not touched; it is user-owned after install and the default covers it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest -q claude/jev/tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add claude/jev/thresholds.py claude/jev/tests/test_thresholds.py
git commit -m "feat(jev): interrogate.min_confidence threshold default"
```

---

### Task 5: Loop text (executor, orchestrate, rules templates)

```
## Task 5: Loop text for pstack picks
Goal: Add gated pstack-picks blocks to executor.md, both orchestrate skills and both rules templates, leaving the off render byte-identical to before.
Scope:
- claude/agents/executor.md
- claude/skills/orchestrate/SKILL.md
- codex/skills/orchestrate/SKILL.md
- claude/CLAUDE.md.template
- codex/AGENTS.md.template
- install/tests/test_pstack_loop.py
- install/tests/fixtures/pre_pstack/**
Done:
- python3 -m pytest -q install/tests passes
Failing test first: install/tests/test_pstack_loop.py :: PstackLoopTest.test_orchestrate_on_content
```

Depends on Tasks 1-4.

**Files:**
- Modify: the five files in Scope
- Create: `install/tests/fixtures/pre_pstack/{executor.md,orchestrate-claude.md,orchestrate-codex.md,CLAUDE.md.template,AGENTS.md.template}` (copies from commit `373dbf3`)
- Test: `install/tests/test_pstack_loop.py`

**Interfaces:**
- Consumes: `render.gate_blocks` (Task 3), `test_pstack_content.LEAK` (Task 1), `test_pstack_skills.CD_PATH` (Task 2), `interrogate.min_confidence` (Task 4), `{{CD}}/skills/interrogate/SKILL.md` (Task 2).

- [ ] **Step 1: Save the pre-change fixtures**

```bash
mkdir -p install/tests/fixtures/pre_pstack
git show 373dbf3:claude/agents/executor.md > install/tests/fixtures/pre_pstack/executor.md
git show 373dbf3:claude/skills/orchestrate/SKILL.md > install/tests/fixtures/pre_pstack/orchestrate-claude.md
git show 373dbf3:codex/skills/orchestrate/SKILL.md > install/tests/fixtures/pre_pstack/orchestrate-codex.md
git show 373dbf3:claude/CLAUDE.md.template > install/tests/fixtures/pre_pstack/CLAUDE.md.template
git show 373dbf3:codex/AGENTS.md.template > install/tests/fixtures/pre_pstack/AGENTS.md.template
```

`install/tests/` is outside the portability scan, and `.gitattributes` keeps text line endings stable on Windows.

- [ ] **Step 2: Write the failing test**

```python
# install/tests/test_pstack_loop.py
import sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import render
from test_pstack_content import LEAK
from test_pstack_skills import CD_PATH
REPO = HERE.parents[1]
FIX = HERE / "fixtures" / "pre_pstack"
FILES = {"executor.md": "claude/agents/executor.md", "orchestrate-claude.md": "claude/skills/orchestrate/SKILL.md",
         "orchestrate-codex.md": "codex/skills/orchestrate/SKILL.md", "CLAUDE.md.template": "claude/CLAUDE.md.template",
         "AGENTS.md.template": "codex/AGENTS.md.template"}
MODEL_POLICY_OWNERS = {"claude/skills/orchestrate/SKILL.md"}


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def block_lines(text):
    off = set(render.gate_blocks(text, []).splitlines())
    return [l for l in render.gate_blocks(text, ["pstack-picks"]).splitlines() if l not in off]


class PstackLoopTest(unittest.TestCase):
    def test_off_is_byte_identical(self):
        for fix, rel in FILES.items():
            self.assertEqual(render.gate_blocks(read(rel), []), (FIX / fix).read_text(encoding="utf-8"), rel)

    def test_orchestrate_on_content(self):
        on = render.gate_blocks(read("claude/skills/orchestrate/SKILL.md"), ["pstack-picks"])
        for s in ('"needs_interrogate"', "interrogate.min_confidence", "{{CD}}/skills/interrogate/SKILL.md",
                  "{{CD}}/pstack/cleanup.md", "superpowers:systematic-debugging", "same model",
                  "after every build task has left `.orchestrate/active.json`", "none (review)", "none (cleanup)",
                  "{{CD}}/pstack/benchmark-checklist.md", "Never put the top rung on the panel"):
            self.assertIn(s, on, s)

    def test_codex_orchestrate_on_content(self):
        on = render.gate_blocks(read("codex/skills/orchestrate/SKILL.md"), ["pstack-picks"])
        for s in ("needs_interrogate", "$interrogate", "{{CD}}/pstack/cleanup.md", "root cause",
                  "after every build task has left `.orchestrate/active.json`"):
            self.assertIn(s, on, s)
        self.assertNotIn("Fable", on)

    def test_executor_principles(self):
        on = render.gate_blocks(read("claude/agents/executor.md"), ["pstack-picks"])
        for n in ("fix-root-causes", "prove-it-works", "test-behavior-not-implementation", "subtract-before-you-add"):
            self.assertIn("{{CD}}/pstack/principles/%s.md" % n, on)

    def test_block_text_has_no_leaks_and_paths_resolve(self):
        for rel in FILES.values():
            lines = block_lines(read(rel))
            self.assertTrue(lines, rel)
            for line in lines:
                if rel not in MODEL_POLICY_OWNERS:
                    self.assertIsNone(LEAK.search(line), (rel, line))
                for p in CD_PATH.findall(line):
                    self.assertTrue((REPO / "claude" / p.rstrip(".`")).exists(), (rel, p))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest -q install/tests/test_pstack_loop.py`
Expected: `test_off_is_byte_identical` PASSES (no blocks yet); `test_orchestrate_on_content` FAILS on `'"needs_interrogate"'`.

- [ ] **Step 4: Add the blocks**

Every block is whole lines inserted between existing lines; no existing line changes.

`claude/agents/executor.md`, after rule 5 and its blank line (before "End with exactly this block:"):

```markdown
<!-- pstack-picks -->
Principles (full text in `{{CD}}/pstack/principles/`). They apply inside your Scope and goal only:
- Fix root causes: reproduce first, ask why until you reach the cause, never add a guard that only silences a symptom (`{{CD}}/pstack/principles/fix-root-causes.md`).
- Prove it works: check the real artifact (run it, read the value), never a proxy or "it compiles" (`{{CD}}/pstack/principles/prove-it-works.md`).
- Test behavior: name the defect a test must catch and assert the required result through the public interface (`{{CD}}/pstack/principles/test-behavior-not-implementation.md`).
- Subtract before you add: remove dead code in your scope first; no speculative guards or options (`{{CD}}/pstack/principles/subtract-before-you-add.md`).

If your section names `{{CD}}/pstack/cleanup.md` or `{{CD}}/pstack/benchmark-checklist.md`, read it in full and follow it.

<!-- /pstack-picks -->
```

`claude/skills/orchestrate/SKILL.md`, five blocks.

(a) After the paragraph that starts "You (Opus) plan, dispatch, judge and integrate." and its blank line:

```markdown
<!-- pstack-picks -->
Keep bulk output in executors and only summaries here (`{{CD}}/pstack/principles/guard-the-context-window.md`). Judge each report against the real artifact, not the self-report (`{{CD}}/pstack/principles/prove-it-works.md`).

<!-- /pstack-picks -->
```

(b) In §2, directly after the line `   Scopes of tasks that may run in parallel must not overlap.`:

```markdown
<!-- pstack-picks -->
   When the approved design is performance work, every task that produces or reports a measured number gets the Done line: `numbers vetted per {{CD}}/pstack/benchmark-checklist.md (verdict, run count, range, limiter)`.
<!-- /pstack-picks -->
```

(c) In §4, directly after the TDD gate paragraph line:

```markdown
<!-- pstack-picks -->
Review and cleanup tasks (`Failing test first: none (review)` or `none (cleanup)`) skip this gate and the §3 Jev call; their executor role is fixed (reviewer or coder).
<!-- /pstack-picks -->
```

(d) In §7, directly after the line `First Sonnet failure: re-dispatch once more on Sonnet with the failure details; the second Sonnet failure escalates to Opus.`:

```markdown
<!-- pstack-picks -->
Before each climb (Sonnet → Opus, Opus → Fable), run superpowers:systematic-debugging with `{{CD}}/pstack/principles/fix-root-causes.md` on the failing reports. Read only; do not edit project files. If the root cause is a plan defect (scope too narrow, Done vague or wrong, missing context), fix that task section in `.orchestrate/PLAN.md` and re-dispatch on the same model: that is not a climb and the failure count stays. Otherwise climb, and put the root cause in the re-dispatch prompt and in the `log_escalation` reason.
<!-- /pstack-picks -->
```

(e) Directly before the line `## 8. Finish`:

````markdown
<!-- pstack-picks -->
## 7b. Interrogate (gated), then cleanup
Start only after every build task has left `.orchestrate/active.json`.

1. One `mcp__jev__jev_judge` call:
```json
{"state": {"design_summary": "...", "diff_stat": "...", "files_touched": [], "contested": false},
 "questions": {
  "needs_interrogate": {"type": "noul", "instructions": "Does the change described in `design_summary` and `diff_stat` restructure how components fit together, change an interface other modules depend on, or carry `contested: true`?",
                        "criteria": {"true": "Architectural or contested change", "false": "Contained change with no shared-interface impact"}}}}
```
2. Run `{{CD}}/skills/interrogate/SKILL.md` (read it and follow it) when Jev says true at confidence ≥ `interrogate.min_confidence`, when the user asked, or when the approved design marked the change contested. Below threshold, escalated or Jev unavailable: you decide; call `mcp__jev__log_override` when you differ. Reviewer A runs on the executor's default (Sonnet), reviewer B with `model: opus`. Never put the top rung on the panel. Act On findings become new tasks (§3-§6).
3. Cleanup: unless the diff touches documentation only, add one task with Scope = the files in the diff, `Failing test first: none (cleanup)`, and Done = `follow {{CD}}/pstack/cleanup.md; behavior unchanged; <project test command> passes`. Dispatch it like any task (Sonnet, `active.json`).

<!-- /pstack-picks -->
````

`codex/skills/orchestrate/SKILL.md`, directly after item 6 ("On return"):

```markdown
<!-- pstack-picks -->
6b. **Root cause, review, cleanup.** Before moving a failed task to the stronger model, find the root cause (Superpowers' systematic-debugging if installed, else `{{CD}}/pstack/principles/fix-root-causes.md`); a plan defect is fixed in the plan and retried on the same model. Start the next part only after every build task has left `.orchestrate/active.json`. Ask Jev `needs_interrogate` (noul: "Does the change described in `design_summary` and `diff_stat` restructure how components fit together, change an interface other modules depend on, or carry `contested: true`?"); if true at ≥ `interrogate.min_confidence`, or the user asked, run `$interrogate`. Then, unless the diff is documentation only, run one cleanup task on the diff's files following `{{CD}}/pstack/cleanup.md`, tests rerun, before `$wreview`. Workers follow the principles in `{{CD}}/pstack/principles/`.
<!-- /pstack-picks -->
```

`claude/CLAUDE.md.template`, directly after the last bullet of "# Model policy (super workflow)":

```markdown
<!-- pstack-picks -->
- Before reporting a performance number you measured, read `~/.claude/pstack/benchmark-checklist.md` and answer its questions. `/interrogate` (two-model adversarial review) runs only from `/orchestrate`'s gated step or when the user asks.
<!-- /pstack-picks -->
```

`codex/AGENTS.md.template`, directly after the `$orchestrate` ... `$tune` line under `## Skills`:

```markdown
<!-- pstack-picks -->
`$interrogate` (gated two-model review), `$benchmark-checklist` (vet a measured performance number). Shared references: `{{CD}}/pstack/`.
<!-- /pstack-picks -->
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest -q install/tests`
Expected: PASS, including `test_codex_templates` (AGENTS under 8 KiB, no `Fable` in Codex skills) and `test_shipped_files`.

- [ ] **Step 6: Commit**

```bash
git add claude/agents/executor.md claude/skills/orchestrate/SKILL.md codex/skills/orchestrate/SKILL.md claude/CLAUDE.md.template codex/AGENTS.md.template install/tests/test_pstack_loop.py install/tests/fixtures/pre_pstack
git commit -m "feat(orchestrate): gated interrogate, cleanup, RCA and principles (pstack picks)"
```

---

### Task 6: Docs and credits

```
## Task 6: Docs and credits for pstack picks
Goal: Document pstack picks in README, a new root NOTICE.md, workflow.md, harnesses.md and install.md.
Scope:
- README.md
- NOTICE.md
- docs/workflow.md
- docs/harnesses.md
- docs/install.md
- install/tests/test_pstack_docs.py
Done:
- python3 -m pytest -q install/tests/test_pstack_docs.py passes
Failing test first: install/tests/test_pstack_docs.py :: PstackDocsTest.test_readme
```

Runs after Task 2, in parallel with Task 5 (disjoint scope).

**Files:**
- Create: `NOTICE.md`, `install/tests/test_pstack_docs.py`
- Modify: `README.md`, `docs/workflow.md`, `docs/harnesses.md`, `docs/install.md`

- [ ] **Step 1: Write the failing test**

```python
# install/tests/test_pstack_docs.py
import unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


class PstackDocsTest(unittest.TestCase):
    def test_readme(self):
        t = read("README.md")
        for s in ("pstack", "Lauren Tan", "Michael Denyer", "cursor-team-kit", "`--no-pstack-picks`", "NOTICE.md"):
            self.assertIn(s, t, s)
        self.assertNotIn("Third-party code is not vendored here.", t)

    def test_notice(self):
        t = read("NOTICE.md")
        for s in ("claude/pstack/NOTICE.md", "claude/pstack/UPSTREAM.md", "dc8e617", "MIT"):
            self.assertIn(s, t, s)

    def test_workflow(self):
        t = read("docs/workflow.md")
        for s in ("pstack picks", "needs_interrogate", "| interrogate | min_confidence 0.7 |", "`/interrogate`",
                  "`/benchmark-checklist`", "Root cause before each climb", "cleanup"):
            self.assertIn(s, t, s)
        self.assertNotIn("Last updated: 2026-10-03.", t)

    def test_harnesses_and_install(self):
        self.assertIn("$interrogate", read("docs/harnesses.md"))
        i = read("docs/install.md")
        for s in ("`--no-pstack-picks`", "pstack picks", "does not remove that component"):
            self.assertIn(s, i, s)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q install/tests/test_pstack_docs.py`
Expected: FAIL in `test_readme` (`pstack` not found) and `FileNotFoundError` for `NOTICE.md`.

- [ ] **Step 3: Write the docs**

`NOTICE.md` (new):

```markdown
# Notice

This repository is MIT-licensed (see [LICENSE](LICENSE)). Third-party tools are fetched from upstream by the installer, with one exception.

## Vendored material

`claude/pstack/` holds adapted files from [pstack-claude](https://github.com/michael-denyer/pstack-claude) at commit `dc8e617` (MIT, (c) 2026 Lauren Tan and (c) 2026 Michael Denyer), a port of [cursor/plugins/pstack](https://github.com/cursor/plugins/tree/main/pstack), plus `deslop` from Cursor's cursor-team-kit (MIT, (c) 2026 Cursor). License texts, provenance and every edit: [claude/pstack/NOTICE.md](claude/pstack/NOTICE.md) and [claude/pstack/UPSTREAM.md](claude/pstack/UPSTREAM.md).
```

`README.md`:
- Recommended stack table, new last row: ``| [pstack](https://github.com/michael-denyer/pstack-claude) picks | Interrogate review, cleanup, benchmark checklist, executor principles (vendored, adapted) | `--no-pstack-picks` |``
- Credits, new bullet: `- [pstack](https://github.com/cursor/plugins/tree/main/pstack) by Lauren Tan, Claude Code port [pstack-claude](https://github.com/michael-denyer/pstack-claude) by Michael Denyer, and deslop from Cursor's cursor-team-kit (all MIT)`
- Replace `Third-party code is not vendored here. The installer fetches it from upstream.` with ``Third-party code is fetched from upstream by the installer, except a few adapted pstack files in `claude/pstack/` (see [NOTICE.md](NOTICE.md)).``

`docs/workflow.md`:
- `Last updated: 2026-10-05.`
- §2 table, new row after Superpowers: ``| **pstack picks** (vendored from pstack, optional, `--no-pstack-picks`) | Review, cleanup and perf references, executor principles | Route, pick models, add hooks, or run without a trigger |``
- §3, new bullet after item 4: `- **Root cause before each climb** (pstack picks). Before Sonnet → Opus and Opus → Fable, the orchestrator runs systematic-debugging on the failing reports. A plan defect is fixed in PLAN.md and re-run on the same model; otherwise the climb carries the root cause in its prompt and its log_escalation reason.`
- §4 step 4, new bullet: `- Perf work: tasks that report a measured number get a Done line pointing to the benchmark checklist.`
- §4 step 7, new bullet: `- Executors follow four principles (fix root causes, prove it works, test behavior, subtract before you add), full text in ~/.claude/pstack/principles/.`
- §4, new step between 8 and 9: `8b. **Interrogate and cleanup** (pstack picks). Jev noul needs_interrogate (architectural or contested change?); at ≥ 0.7, or when you ask, two read-only executor reviewers (Sonnet and Opus, never Fable) run /interrogate and Opus judges; Act On items become tasks. Then one Sonnet cleanup task removes slop and stale comments from the diff's files, tests rerun. Docs-only diffs skip cleanup.`
- §6 thresholds table, new row: `| interrogate | min_confidence 0.7 |`
- §9 table, new rows: ``| `/interrogate` | Two-model adversarial review with a lead verdict; gated step of /orchestrate or on request |`` and ``| `/benchmark-checklist` | Vet a measured perf number before reporting it |``

`docs/harnesses.md`: in the Codex skills list add `$interrogate` and `$benchmark-checklist`, and append to that paragraph: `With pstack picks, Codex runs the same root-cause, interrogate and cleanup steps; its interrogate panel is two Codex sub-agents (cheaper, then stronger).` In the Claude Code only list add `the read-only executor review panel (scope lock with an empty Scope)`.

`docs/install.md`:
- Components table row: ``| pstack picks | Interrogate review, cleanup, benchmark checklist and principles, adapted from [pstack-claude](https://github.com/michael-denyer/pstack-claude) (see NOTICE.md) | `--no-pstack-picks` skips |``
- Flags table row: ``| `--no-pstack-picks` | Do not install the pstack picks |``
- Upgrade section, new sentence: `Re-running with --no-pstack-picks (or any --no- flag) after a full install does not remove that component; use --uninstall.`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest -q install/tests/test_pstack_docs.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md NOTICE.md docs/workflow.md docs/harnesses.md docs/install.md install/tests/test_pstack_docs.py
git commit -m "docs: pstack picks credits, NOTICE and workflow updates"
```

---

## Finish (orchestrator, not a task)

1. Full gate: `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests`, `node claude/ruflo/tests/test_ns.cjs`, `python3 tools/deny_scan.py claude/pstack claude/skills/interrogate claude/skills/benchmark-checklist` (needs the private term list; if it is absent, say so).
2. Dry runs: `./install/install.sh --dry-run` lists `pstack/...` files; `./install/install.sh --dry-run --no-pstack-picks` lists none.
3. `/wreview`, `superpowers:verification-before-completion`, `/commit`. CI green on macOS, Ubuntu and Windows before merge.
4. After merge, ask the user before each: add `pstack/`, `skills/interrogate/`, `skills/benchmark-checklist/` to `~/.claude/release/public-manifest.txt`; re-run the installer; refresh `~/.claude/DryasWorkflow.md` and `Dev/docs/DryasWorkflow.md`.
5. Two weeks after rollout: run `/tune` and compare escalation counts and the `needs_interrogate` override rate with the two weeks before (spec section 6).
