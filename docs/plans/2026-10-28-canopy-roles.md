# Canopy roles and role memory (dryas-workflow part) — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract; Interfaces and Steps follow. Steps use checkbox (`- [ ]`) syntax.

**Goal:** give the three review-request reviewers their own `log_dispatch` role values, load up to three role lessons into each dispatch (logged as a `role-lessons` record in `memory.jsonl`), store at most one lesson per role at the end of a run, and let `memory.role_lessons` switch it all off.
**Architecture:** the memory MCP tools do the deterministic part: a search in a `role-<slug>` namespace caps the result at 3 lessons and 600 body characters, puts this repo's lessons first, and logs `{task, role, lesson_ids}` with `ok: true`; a store in a role namespace tags the lesson with the repo; both do nothing when the switch is off. The orchestrate and review-request skills only say when to call them and which role values to log.
**Tech Stack:** Python 3 stdlib (Jev MCP server, thresholds), Markdown skills, `unittest`/pytest.
**Spec:** `../canopy/docs/specs/2026-10-28-dryas-canopy-design.md` (the sibling `canopy` repo) §5.1 and §9; frozen contract C4 in `../canopy/docs/plans/2026-10-28-canopy-release-index.md` (spec task 2).

## Global Constraints

- New `log_dispatch` role values: exactly `reviewer-spec`, `reviewer-quality`, `reviewer-minimalist` (review-request stages 1, 2, 3). Interrogate reviewers keep `reviewer`; builders keep `coder`, `tester`, `docs`.
- Role namespaces: `role-<slug>`, shared across repos. Dispatch roles map to slugs: `coder`, `tester`, `docs` → `builder`; `reviewer-spec|quality|minimalist` → the same; interrogate `reviewer` → `devils-advocate`. Per-repo namespaces are unchanged.
- At dispatch: one `memory_search` in the role namespace, at most 3 lessons, at most 600 body characters in total, this repo's lessons first. It logs one `memory.jsonl` line: `{"stage": "role-lessons", "ok": true, "task": <task id>, "role": <slug>, "lesson_ids": [<id as string>, ...]}` plus jevlog's `ts`, `session_id`, `cwd`. `ok: true` is required: FlowObserve's memory page counts any memory line without `ok: true` as a failure.
- At the end of a run: at most one lesson per role that took part, stored in its role namespace and tagged `repo:<repo>`.
- Kill switch `memory.role_lessons` in `thresholds.json`, default `true`. Off: role searches return no lessons and log nothing, role stores store nothing. Executors still get no memory tools; the scope lock is unchanged.
- No change to `claude/CLAUDE.md.template` or `codex/AGENTS.md.template` (byte budgets).
- Generated copies (`codex/jev`, `opencode/dryas/jev`, `codex/skills/<process skills>`, `opencode/skill/dryas-*`) only via `python3 tools/sync_codex_plugin.py`; never hand-edit them. The hand-written `codex/skills/orchestrate/SKILL.md` and `opencode/skill/dryas-orchestrate/SKILL.md` are edited directly.
- Files under 500 lines; `python3 tools/deny_scan.py .` clean; full suite `python3 -m pytest -q install/tests claude/jev/tests` passes (`test_codex_appserver.py::RunnerTest::test_close_kills_a_hung_server` may time out under load: rerun it alone).

## Review Focus

1. A role namespace with no lessons yet (the first run ever): the search returns an empty list and still logs a `role-lessons` line with `lesson_ids: []`, so Canopy can show "nothing loaded". Pinned in Task 1 (`test_empty_role_namespace_logs_empty_ids`).
2. A role search without `task` (someone calls it by hand): it returns lessons but logs nothing, since there is no task to attach them to. Pinned in Task 1 (`test_no_task_no_log`).
3. One very long lesson: the 600-character budget cuts it, and a second lesson that no longer fits is dropped rather than returned empty. Pinned in Task 1 (`test_budget_cuts_and_drops`).
4. The switch set to a non-boolean (`"false"` as a string): only a real `false` turns it off, matching how the other switches read. Pinned in Task 1 (`test_switch_off_only_on_false`).
5. A per-repo namespace search (`dryas-workflow`): unchanged behaviour, no cap, no log line. Pinned in Task 1 (`test_project_namespace_unchanged`).

---

## Task 1: Role lessons in the memory MCP tools, with the kill switch

Goal: role-namespace `memory_search` caps, orders and logs the loaded lessons; role-namespace `memory_store` tags the repo; `memory.role_lessons` turns both off.
Scope:
- claude/jev/memory_mcp.py
- claude/jev/thresholds.py
- claude/jev/thresholds.json
- claude/jev/tests/test_role_memory.py
- install/tests/fixtures/role-lessons.jsonl
- codex/jev/**
- opencode/dryas/jev/**
- reference/inventory-map.json
Done:
- `python3 -m pytest -q claude/jev/tests/test_role_memory.py claude/jev/tests/test_memory_mcp.py claude/jev/tests/test_thresholds.py` passes
- `python3 tools/sync_codex_plugin.py --check` and `python3 tools/sync_opencode.py --check` exit 0; `python3 tools/inventory.py --check` reports 0 problems
- `python3 -m pytest -q install/tests claude/jev/tests` passes
Failing test first: claude/jev/tests/test_role_memory.py :: RoleMemoryTest.test_role_search_caps_and_logs

**Interfaces:**
- Consumes: `memstore.search(conn, ns, query, limit, include_archive, session)` (returns `{"results": [{"id", "title", "body", "tags", ...}], ...}`), `memstore.store`, `projns.project_ns()`, `jevlog.append(name, record)`, `thresholds.load()`.
- Produces: `memory_mcp.ROLE_PREFIX = "role-"`, `ROLE_LESSONS_MAX = 3`, `ROLE_LESSONS_CHARS = 600`; `memory_search` accepts an optional `task` string; `thresholds.DEFAULTS["memory"] = {"role_lessons": True}`; the `memory.jsonl` record in Global Constraints; fixture `install/tests/fixtures/role-lessons.jsonl` (one line, the record shape FlowObserve reads).

- [ ] **Step 1: Write the failing tests.** Create `claude/jev/tests/test_role_memory.py`, using the same harness as `test_memory_mcp.py` (temp `DRYAS_DB`, `JEV_LOG_DIR`, `CLAUDE_PROJECT_DIR` = a temp folder named `proj`, `JEV_SESSION_ID`, and `JEV_THRESHOLDS` = a temp file) and its `call(name, args)` helper. Read `memory.jsonl` from the temp log dir. Tests:
  - `test_role_search_caps_and_logs`: store 5 lessons in `role-builder` (bodies "use Edit not heredocs N"), search `{"namespace": "role-builder", "query": "Edit heredocs", "task": "feat/x:3"}`; at most 3 results; total body length ≤ 600; one `memory.jsonl` line with `stage == "role-lessons"`, `ok is True`, `task == "feat/x:3"`, `role == "builder"`, `lesson_ids` == the returned ids as strings.
  - `test_repo_lessons_first`: store one lesson tagged by a store from another project (patch `CLAUDE_PROJECT_DIR` to a folder named `other` for that store) and one from `proj`; search from `proj`: the `proj` lesson comes first.
  - `test_store_tags_repo`: `memory_store` in `role-reviewer-spec` from `proj`; `memory_list` shows tag `repo:proj`.
  - `test_empty_role_namespace_logs_empty_ids`, `test_no_task_no_log`, `test_budget_cuts_and_drops` (one 590-char body and one 100-char body: the second is cut to 10 chars; with a 600-char first body, only one result), `test_switch_off_only_on_false` (write `{"memory": {"role_lessons": false}}` to `JEV_THRESHOLDS`: search returns `results == []` and `role_lessons == "off"`, no log line, store returns `stored: False`; with `"false"` as a string it stays on), `test_project_namespace_unchanged` (search `dryas`-style namespace `proj` with `limit: 5` returns up to 5 and logs nothing).
  - `test_fixture_matches_record`: the keys of the one line in `install/tests/fixtures/role-lessons.jsonl` equal the keys of a logged record minus `cwd` (`{"stage", "ok", "task", "role", "lesson_ids", "ts", "session_id"}`).
- [ ] **Step 2: Run them to see them fail.** Run: `python3 -m pytest -q claude/jev/tests/test_role_memory.py`. Expected: FAIL (no cap, no log line, no tag).
- [ ] **Step 3: Implement.** In `claude/jev/thresholds.py` `DEFAULTS`, add `"memory": {"role_lessons": True},` before `"history"`; add the same key to `claude/jev/thresholds.json` if that file lists the sections (follow its existing shape; check `claude/jev/tests/test_thresholds.py` for a shipped-vs-defaults test). In `claude/jev/memory_mcp.py`:
  - import `jevlog` and `thresholds` next to the other local imports;
  - add `"task": {"type": "string", "description": "Plan task id (branch:N); in a role-<slug> namespace, logs which lessons were loaded"}` to the `memory_search` input schema;
  - add after `NAMES`:

```python
ROLE_PREFIX = "role-"
ROLE_LESSONS_MAX = 3
ROLE_LESSONS_CHARS = 600


def _role_on() -> bool:
    return thresholds.load().get("memory", {}).get("role_lessons", True) is not False


def _role_search(conn, ns: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if not _role_on():
        return {"results": [], "namespace": ns, "role_lessons": "off"}
    res = memstore.search(conn, ns, str(args.get("query") or ""), limit=10, session=_session())
    repo = "repo:" + projns.project_ns()
    left, out = ROLE_LESSONS_CHARS, []
    for r in sorted(res["results"], key=lambda r: repo not in r["tags"])[:ROLE_LESSONS_MAX]:
        if left <= 0:
            break
        out.append(dict(r, body=r["body"][:left]))
        left -= len(out[-1]["body"])
    task = _opt(args.get("task"))
    if task:
        jevlog.append("memory", {"stage": "role-lessons", "ok": True, "task": task[:200],
                                 "role": ns[len(ROLE_PREFIX):], "lesson_ids": [str(r["id"]) for r in out]})
    return {"results": out, "namespace": ns}
```
  - in `_call`, first line of the `memory_search` branch: `if ns.startswith(ROLE_PREFIX): return _role_search(conn, ns, args), False`;
  - in `_store`, before `memstore.store`: if `ns.startswith(ROLE_PREFIX)`: return `{"stored": False, "reason": "memory.role_lessons is off"}, False` when `not _role_on()`; otherwise append `"repo:" + projns.project_ns()` to the tag list.
  Check that `projns.sanitize("role-builder")` keeps the name (if it rewrites `-`, use the sanitized prefix consistently and say so in the report). Create `install/tests/fixtures/role-lessons.jsonl` with exactly: `{"stage": "role-lessons", "ok": true, "task": "feat/example:2", "role": "builder", "lesson_ids": ["412", "397"], "ts": "2026-10-28T21:00:00+0700", "session_id": "00000000-0000-0000-0000-000000000000"}`.
- [ ] **Step 4: Sync and inventory.** Run `python3 tools/sync_codex_plugin.py` (refreshes `codex/jev` and `opencode/dryas/jev`), then `python3 tools/inventory.py --check`. If it reports new MCP params or log fields as problems, record them in `reference/inventory-map.json` the way earlier additions are recorded (never in the baseline).
- [ ] **Step 5: Run the tests.** The Done commands. Expected: PASS.
- [ ] **Step 6: Commit** (explicit paths, e.g. `feat(memory): role lessons in role-<slug> namespaces with memory.role_lessons switch (task 1)`).

## Task 2: Role values and role-lesson steps in /orchestrate and review-request

Goal: the review-request stages log their own role values, /orchestrate loads role lessons into each dispatch and stores one lesson per role at the end, on all three editions.
Scope:
- claude/skills/orchestrate/SKILL.md
- claude/skills/review-request/SKILL.md
- codex/skills/orchestrate/SKILL.md
- opencode/skill/dryas-orchestrate/SKILL.md
- codex/skills/review-request/**
- opencode/skill/dryas-review-request/**
- docs/workflow.md
- install/tests/test_role_memory_docs.py
- install/tests/test_pstack_loop.py
Done:
- `python3 -m pytest -q install/tests/test_role_memory_docs.py install/tests/test_pstack_loop.py install/tests/test_process_skills.py install/tests/test_opencode_skills.py` passes
- `python3 tools/sync_codex_plugin.py --check` exits 0
- `python3 -m pytest -q install/tests claude/jev/tests` passes
Failing test first: install/tests/test_role_memory_docs.py :: RoleMemoryDocsTest.test_orchestrate_loads_role_lessons

**Interfaces:**
- Consumes: Task 1's `task` argument on `memory_search` and the role-namespace behaviour.
- Produces: the texts `CLAUDE_LESSONS_STEP`, `CLAUDE_LESSONS_STORE`, `REVIEW_ROLES` (defined in the test below) in the skills.

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_role_memory_docs.py`:

```python
"""Canopy spec task 2: reviewer role values and role lessons in /orchestrate and review-request (all editions)."""
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
CLAUDE_LESSONS_STEP = (
    "Role lessons: right before each dispatch, call `mcp__plugin_dryas_jev__memory_search` once with namespace "
    "`role-<slug>`, query = the task title and task = the §5.5 id, where the slug is `builder` for coder, tester and "
    "docs, the review stage's own role for `reviewer-spec`, `reviewer-quality` and `reviewer-minimalist`, and "
    "`devils-advocate` for interrogate reviewers. Add the lessons it returns (at most 3, already cut to 600 "
    "characters) to the dispatch prompt under `Lessons from past <slug> work:`; none returned (or the switch "
    "`memory.role_lessons` is off): add nothing. The tool logs which lessons were loaded.")
CLAUDE_LESSONS_STORE = (
    "Role lessons, once per run after the merge: for each role that took part (`builder` when a build task ran, each "
    "review stage, `devils-advocate` when interrogate ran), store at most one lesson with "
    "`mcp__plugin_dryas_jev__memory_store`, namespace `role-<slug>`, kind outcome, a one-line title and a body under "
    "600 characters on what that role should do or avoid next time, taken from its review findings and escalations. "
    "Skip a role with nothing to learn. The tool tags the lesson with this repo and stores nothing when "
    "`memory.role_lessons` is off.")
REVIEW_ROLES = "role `reviewer-spec`, `reviewer-quality` or `reviewer-minimalist` (stage 1, 2 or 3)"


def read(p):
    return (ROOT / p).read_text(encoding="utf-8")


class RoleMemoryDocsTest(unittest.TestCase):
    def test_orchestrate_loads_role_lessons(self):
        t = read("claude/skills/orchestrate/SKILL.md")
        dispatch = t.split("## 5. Dispatch")[1].split("\n## ")[0]
        self.assertIn(CLAUDE_LESSONS_STEP, dispatch)
        self.assertIn("reviewer-spec, reviewer-quality, reviewer-minimalist", dispatch)
        finish = t.split("## 8. Finish")[1].split("\n## ")[0]
        self.assertIn(CLAUDE_LESSONS_STORE, finish)

    def test_review_request_logs_stage_roles(self):
        self.assertIn(REVIEW_ROLES, read("claude/skills/review-request/SKILL.md"))
        self.assertNotIn("role reviewer, one per stage", read("claude/skills/review-request/SKILL.md"))

    def test_codex_and_opencode(self):
        for p, search in (("codex/skills/orchestrate/SKILL.md", "`memory_search`"),
                          ("opencode/skill/dryas-orchestrate/SKILL.md", "`jev_memory_search`")):
            t = read(p)
            self.assertIn("role-<slug>", t, p)
            self.assertIn(search, t, p)
            self.assertIn("memory.role_lessons", t, p)

    def test_workflow_doc(self):
        t = read("docs/workflow.md")
        for s in ("role-<slug>", "memory.role_lessons", "reviewer-spec"):
            self.assertIn(s, t)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_role_memory_docs.py`. Expected: 4 FAIL.
- [ ] **Step 3: Claude orchestrate.** In `claude/skills/orchestrate/SKILL.md` §5: insert `CLAUDE_LESSONS_STEP` as its own paragraph right after item 3 ("Give each executor ONLY its section…"); in item 6 change `role (coder, tester, reviewer or docs)` to `role (coder, tester, reviewer, reviewer-spec, reviewer-quality, reviewer-minimalist or docs)`. In §8 Finish, insert `CLAUDE_LESSONS_STORE` as its own sentence right after the `log_merge` sentence and before "then remove the worktree" (keep the sentence flow: end the log_merge sentence, add the lessons sentence, then "Then remove the worktree."). `allowed-tools` already lists both memory tools.
- [ ] **Step 4: review-request.** In `claude/skills/review-request/SKILL.md`, the Claude block: replace `role reviewer, one per stage` with `` `REVIEW_ROLES` `` text: `role `reviewer-spec`, `reviewer-quality` or `reviewer-minimalist` (stage 1, 2 or 3), one per stage`. Run `python3 tools/sync_codex_plugin.py` (renders the Codex and OpenCode review-request copies).
- [ ] **Step 5: Codex and OpenCode orchestrate (hand-written).** Add the same two steps in their own words: the Codex copy names `memory_search` / `memory_store`, the OpenCode copy `jev_memory_search` / `jev_memory_store`; both name `role-<slug>`, the slug mapping, the 3-lesson / 600-character cap and `memory.role_lessons`. Then `python3 tools/sync_codex_plugin.py --check` (its shared-name check covers `memory_search`/`memory_store`).
- [ ] **Step 6: Fixture comparison.** `install/tests/test_pstack_loop.py::test_off_is_byte_identical` compares orchestrate to old fixtures through `plugin_form`/`codex_form`: add (old, new) pairs or insertions for every changed sentence, importing the strings from `test_role_memory_docs`. Never edit `install/tests/fixtures/`.
- [ ] **Step 7: Workflow doc.** In `docs/workflow.md`, where the §4 loop describes dispatch (after the "Plan as a file" / dispatch steps), add a short paragraph: "**Role lessons.** Each dispatch loads up to 3 lessons (600 characters) from the role's shared namespace `role-<slug>` (`builder`, `reviewer-spec`, `reviewer-quality`, `reviewer-minimalist`, `devils-advocate`), this repo's first, and logs which ones in `memory.jsonl`; after the merge, at most one new lesson per role is stored. Review-request logs its reviewers as `reviewer-spec`, `reviewer-quality` and `reviewer-minimalist`. Switch off with `memory.role_lessons: false` in `thresholds.json`." Also add `memory.role_lessons` to the thresholds table if the doc has one.
- [ ] **Step 8: Run the tests.** The Done commands. Expected: PASS.
- [ ] **Step 9: Commit** (explicit paths, e.g. `feat(orchestrate): reviewer role values and role lessons (task 2)`).

---

## After merge (main session, not an executor task)

1. Send FlowObserve (Canopy spec task 3) the record shape and `install/tests/fixtures/role-lessons.jsonl`, and the new `log_dispatch` role values.
2. Release gate (C7): `tools/compare_release.py --old <2.5.0>` and `tools/compare_v1.py` (hook path, prompts must stay 0); role memory adds one local MCP call per dispatch (~150 tokens, accepted in the spec). If the cost rise is more than accepted, ship with `memory.role_lessons: false`.
