# Metrics Logging and /tune Calibration Fixes Implementation Plan

> **For agentic workers:** this plan is executed by `/orchestrate` (Opus orchestrator, Sonnet executors, scope lock). Each executor receives only its own task section. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make GOV-M4, ESC-M1, REV-M1 and EXE-M3 measurable from logs, and fix `/tune`'s no-op proposals, scattered question names and unfiltered Sonnet→Opus count.

**Architecture:** The scope-lock hook appends a `scope` record on every deny. Three new MCP tools in `jev_mcp.py` (`log_dispatch`, `log_review`, `log_merge`) validate and append records, following `log_escalation`. `tune.py` reads the new logs, adds report lines, groups questions by `canonical()`, and drops no-op proposals. Skill texts in both editions call the new tools.

**Tech Stack:** Python 3 stdlib only, unittest/pytest. Logs: JSON Lines via `claude/jev/jevlog.py`.

**Spec:** `docs/superpowers/specs/2026-10-06-metrics-logging-design.md`

## Global Constraints

- Python stdlib only; no new dependencies.
- All writes go through `jevlog.append(name, record)`; it adds `ts` and never raises.
- The scope lock's allow/deny decision must not change. Logging runs after a deny is decided.
- New MCP tools reject a missing or invalid required field with a tool error (`isError: true`) and write nothing.
- Canonical question names: `executor`, `specific`, `failing_test_exists`, `needs_opus`, `needs_stronger_model`, `done`, `risk`, `safe_to_commit`, `needs_interrogate`.
- Any `/tune` ratio with a zero denominator renders `n/a`.
- Files stay under 500 lines.
- Full suite: `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests`.

## Review Focus

1. Malformed or legacy log lines (string ints, missing fields, non-dict lines) must be skipped by `/tune`, never crash it. Pinned in Task 3.
2. A log directory that cannot be written must not turn a scope-lock deny into an allow. Pinned in Task 1.
3. MCP tools given bools, floats, negative or non-numeric ints must reject, not coerce silently. Pinned in Task 2.
4. A branch reviewed in several rounds, possibly from several sessions, counts its highest round, not the sum. Pinned in Task 3.
5. Records with `attempt` as the string `"1"` (hand-written or older) still count as first dispatches. Pinned in Task 3.

---

### Task 1: Scope-lock deny logging

**Files:**
- Modify: `claude/jev/scope_lock.py`
- Test: `claude/jev/tests/test_scope_lock.py`

**Interfaces:**
- Consumes: `jevlog.append(name: str, record: dict) -> None`
- Produces: log file `scope.jsonl`, records `{"task": [str, ...], "path": str, "decision": "deny"}` (`path` is relative to the worktree root, `/`-separated)

- [ ] **Step 1: Write the failing tests** (append to `ScopeLockTest` in `test_scope_lock.py`; add `self.logs = tempfile.mkdtemp(); os.environ["JEV_LOG_DIR"] = self.logs` at the end of `setUp`)

```python
    def scope_records(self):
        p = os.path.join(self.logs, "scope.jsonl")
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return [json.loads(l) for l in f]

    def test_deny_writes_scope_record(self):
        out = scope_lock.run(self.ev(os.path.join(self.wt, "src/other.ts")))
        self.assertEqual(self.decision(out), "deny")
        recs = self.scope_records()
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0]["task"], recs[0]["path"], recs[0]["decision"]), (["1"], "src/other.ts", "deny"))

    def test_allow_writes_nothing(self):
        self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.wt, "src/feature/a.ts"))))
        self.assertEqual(self.scope_records(), [])

    def test_unwritable_log_dir_still_denies(self):
        blocker = os.path.join(self.logs, "afile")
        open(blocker, "w").close()
        os.environ["JEV_LOG_DIR"] = os.path.join(blocker, "sub")  # parent is a file: makedirs fails
        out = scope_lock.run(self.ev(os.path.join(self.wt, "src/other.ts")))
        self.assertEqual(self.decision(out), "deny")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest -q claude/jev/tests/test_scope_lock.py -k "scope_record or writes_nothing or unwritable"`
Expected: `test_deny_writes_scope_record` FAILS (no `scope.jsonl`); the other two pass already.

- [ ] **Step 3: Implement** in `scope_lock.py`. Add `import jevlog` after `import planfile`. Add above `run()`:

```python
def _active_ids(root: str) -> List[str]:
    try:
        with open(os.path.join(root, ".orchestrate", "active.json"), encoding="utf-8") as f:
            a = json.load(f).get("active", [])
        return [str(x) for x in a] if isinstance(a, list) else []
    except Exception:
        return []


def _log_deny(root: str, path: str) -> None:
    """Record a deny for GOV-M4. Never raises, never changes the decision."""
    try:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        jevlog.append("scope", {"task": _active_ids(root), "path": rel, "decision": "deny"})
    except Exception:
        pass
```

In `run()`, change both deny branches to log first:

```python
            reason = check(os.path.realpath(root), path, has_agent_id)
            if reason:
                _log_deny(os.path.realpath(root), path)
                return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                               "permissionDecisionReason": reason}}
        except Exception as e:
            _log_deny(os.path.realpath(root), path)
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": "scope lock: error checking %s (%s)" % (root, type(e).__name__)}}
```

- [ ] **Step 4: Run the scope-lock tests**

Run: `python3 -m pytest -q claude/jev/tests/test_scope_lock.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add claude/jev/scope_lock.py claude/jev/tests/test_scope_lock.py
git commit -m "feat(scope-lock): log every deny to scope.jsonl for GOV-M4"
```

---

### Task 2: MCP logging tools

**Files:**
- Modify: `claude/jev/jev_mcp.py`
- Test: `claude/jev/tests/test_jev_mcp.py`

**Interfaces:**
- Consumes: `jevlog.append`, existing `_coerce_to_str`, `_coerce_confidence`, `_text`
- Produces: MCP tools and log files:
  - `log_dispatch` → `dispatch.jsonl`: `{"task": str, "tier": str, "role": str, "attempt": int>=1}`
  - `log_review` → `review.jsonl`: `{"task": str, "round": int>=1, "critical": int>=0, "important": int>=0, "minor": int>=0}`
  - `log_merge` → `merge.jsonl`: `{"task": str, "branch": str, "tasks_merged": int>=0, "cost_usd"?: float>=0}`

- [ ] **Step 1: Write the failing tests** (in `McpTest`; replace the existing `test_tools_list`)

```python
    def test_tools_list(self):
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(sorted(t["name"] for t in r["result"]["tools"]),
                         ["jev_judge", "log_dispatch", "log_escalation", "log_merge", "log_override", "log_review"])

    def test_log_dispatch(self):
        r = call("log_dispatch", {"task": "t1", "tier": "sonnet", "role": "coder", "attempt": "1", "extra": "x"})
        self.assertFalse(r["result"]["isError"])
        rec = self.read("dispatch")[0]
        self.assertEqual({k: rec[k] for k in ("task", "tier", "role", "attempt")},
                         {"task": "t1", "tier": "sonnet", "role": "coder", "attempt": 1})
        self.assertNotIn("extra", rec)

    def test_log_review(self):
        call("log_review", {"task": "feat-x", "round": 2, "critical": 0, "important": 3, "minor": 1})
        rec = self.read("review")[0]
        self.assertEqual((rec["round"], rec["important"]), (2, 3))

    def test_log_merge_with_and_without_cost(self):
        call("log_merge", {"task": "feat-x", "branch": "feat-x", "tasks_merged": 5, "cost_usd": 4.2})
        call("log_merge", {"task": "feat-y", "branch": "feat-y", "tasks_merged": 2})
        a, b = self.read("merge")
        self.assertEqual(a["cost_usd"], 4.2)
        self.assertNotIn("cost_usd", b)

    def test_log_tools_reject_bad_input_and_write_nothing(self):
        bad = [("log_dispatch", {"task": "t1", "tier": "sonnet", "role": "coder"}),              # missing attempt
               ("log_dispatch", {"task": "", "tier": "sonnet", "role": "coder", "attempt": 1}),  # empty task
               ("log_dispatch", {"task": "t1", "tier": "sonnet", "role": "coder", "attempt": True}),
               ("log_dispatch", {"task": "t1", "tier": "sonnet", "role": "coder", "attempt": 1.5}),
               ("log_review", {"task": "b", "round": 0, "critical": 0, "important": 0, "minor": 0}),
               ("log_review", {"task": "b", "round": 1, "critical": -1, "important": 0, "minor": 0}),
               ("log_merge", {"task": "b", "branch": "b", "tasks_merged": "many"})]
        for name, args in bad:
            r = call(name, args)
            self.assertTrue(r["result"]["isError"], (name, args))
        for f in ("dispatch", "review", "merge"):
            self.assertFalse(os.path.exists(os.path.join(self.tmp, f + ".jsonl")), f)

    def test_log_merge_ignores_bad_cost(self):
        call("log_merge", {"task": "b", "branch": "b", "tasks_merged": 1, "cost_usd": "nan"})
        call("log_merge", {"task": "c", "branch": "c", "tasks_merged": 1, "cost_usd": -3})
        self.assertTrue(all("cost_usd" not in r for r in self.read("merge")))
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest -q claude/jev/tests/test_jev_mcp.py`
Expected: the new tests and `test_tools_list` FAIL ("unknown tool").

- [ ] **Step 3: Implement** in `jev_mcp.py`. Append to `TOOLS`:

```python
    {
        "name": "log_dispatch",
        "description": "Record one executor dispatch (first or re-dispatch). Feeds /tune: tasks dispatched, GOV-M4, ESC-M1.",
        "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}, "tier": {"type": "string"},
                                                         "role": {"type": "string"}, "attempt": {"type": "integer", "minimum": 1}},
                        "required": ["task", "tier", "role", "attempt"]},
    },
    {
        "name": "log_review",
        "description": "Record one review round of a branch with its finding counts. Feeds /tune: REV-M1, merges without review.",
        "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}, "round": {"type": "integer", "minimum": 1},
                                                         "critical": {"type": "integer", "minimum": 0},
                                                         "important": {"type": "integer", "minimum": 0},
                                                         "minor": {"type": "integer", "minimum": 0}},
                        "required": ["task", "round", "critical", "important", "minor"]},
    },
    {
        "name": "log_merge",
        "description": "Record a local merge of a worktree branch. cost_usd is optional (from /cost). Feeds /tune: EXE-M3.",
        "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}, "branch": {"type": "string"},
                                                         "tasks_merged": {"type": "integer", "minimum": 0},
                                                         "cost_usd": {"type": "number", "minimum": 0}},
                        "required": ["task", "branch", "tasks_merged"]},
    },
```

Add after `_sanitize_log_override`:

```python
def _as_int(v: Any) -> Optional[int]:
    """Strict int: real ints or digit strings; never bools or floats."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    return None


# tool name -> (log file, required string fields, required int fields with minimum)
LOG_TOOLS = {
    "log_dispatch": ("dispatch", ("task", "tier", "role"), {"attempt": 1}),
    "log_review": ("review", ("task",), {"round": 1, "critical": 0, "important": 0, "minor": 0}),
    "log_merge": ("merge", ("task", "branch"), {"tasks_merged": 0}),
}


def _validate_log(args: Dict[str, Any], strs: Any, ints: Dict[str, int]) -> Any:
    """Return (record, bad_fields). A record is written only when bad_fields is empty."""
    rec: Dict[str, Any] = {}
    bad = []
    for k in strs:
        v = args.get(k)
        if v is None or not str(v).strip():
            bad.append(k)
        else:
            rec[k] = _coerce_to_str(v)
    for k, lo in ints.items():
        n = _as_int(args.get(k))
        if n is None or n < lo:
            bad.append(k)
        else:
            rec[k] = n
    return rec, bad
```

In `handle()`'s `tools/call` branch, before the unknown-tool fallthrough:

```python
            if name in LOG_TOOLS:
                file, strs, ints = LOG_TOOLS[name]
                rec, bad = _validate_log(args, strs, ints)
                if bad:
                    return _text(mid, "invalid or missing: %s" % ", ".join(bad), True)
                if name == "log_merge":
                    cost = _coerce_confidence(args.get("cost_usd"))
                    if cost is not None and cost >= 0:
                        rec["cost_usd"] = cost
                jevlog.append(file, rec)
                return _text(mid, "logged")
```

- [ ] **Step 4: Run the MCP tests**

Run: `python3 -m pytest -q claude/jev/tests/test_jev_mcp.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add claude/jev/jev_mcp.py claude/jev/tests/test_jev_mcp.py
git commit -m "feat(jev-mcp): add log_dispatch, log_review and log_merge tools"
```

---

### Task 3: /tune report lines, canonical names and filters

**Files:**
- Modify: `claude/jev/tune.py`
- Test: `claude/jev/tests/test_tune.py`

**Interfaces:**
- Consumes: log files `scope`, `dispatch`, `review`, `merge` (shapes in Tasks 1–2), existing `escalations`, `mcp`, `overrides`
- Produces: `tune.canonical(name: str) -> str`; `tune.CANONICAL: tuple`; `tune.delivery(...) -> dict`; `build()` key `delivery`; `opus_escalations` filtered to `from_model == "sonnet"`; `proposals()` never returns `new == old`

`build()["delivery"]` keys: `tasks_dispatched: int`, `scope_denials: int`, `scope_per_task: float|None`, `climb_rate: float|None`, `review_rounds_median: float|None`, `merges: int`, `merges_without_review: int`, `cost_per_task: float|None`, `merges_without_cost: int`.

- [ ] **Step 1: Write the failing tests** (in `TuneTest`)

```python
    def test_canonical_names(self):
        cases = {"needs_opus.t3": "needs_opus", "t2_needs_opus": "needs_opus", "needs_opus_t10": "needs_opus",
                 "needs_opus_any": "needs_opus", "specific_12": "specific", "specific_all": "specific",
                 "executor1": "executor", "executor_kind": "executor", "done_t5": "done", "t6_done": "done",
                 "failing_tests_exist": "failing_test_exists", "failing_test_t1": "failing_test_exists",
                 "failing_test_exists_2": "failing_test_exists", "risk_t5": "risk",
                 "needs_stronger_model.t1": "needs_stronger_model",
                 "opus4": "opus4", "t1_opus": "t1_opus", "other_needs_opus": "other_needs_opus", "failing1": "failing1"}
        for raw, want in cases.items():
            self.assertEqual(tune.canonical(raw), want, raw)

    def test_questions_grouped_by_canonical_name(self):
        write(self.d, "mcp", [{"answers": {"needs_opus.t1": {"confidence": 0.9}, "t2_needs_opus": {"confidence": 0.9}}}])
        write(self.d, "overrides", [{"question": "needs_opus_t3"}])
        q = tune.build()["questions"]
        self.assertEqual((q["needs_opus"]["calls"], q["needs_opus"]["overrides"]), (2, 1))

    def test_sonnet_opus_count_requires_from_sonnet(self):
        write(self.d, "escalations", [{"reason": "a", "from_model": "sonnet", "to_model": "opus"},
                                      {"reason": "b", "from_model": "opus", "to_model": "opus"},
                                      {"reason": "c", "to_model": "opus"}])
        self.assertEqual(tune.build()["opus_escalations"]["count"], 1)

    def test_delivery_metrics(self):
        write(self.d, "dispatch", [{"task": "t1", "tier": "sonnet", "role": "coder", "attempt": 1},
                                   {"task": "t1", "tier": "sonnet", "role": "coder", "attempt": 2},
                                   {"task": "t2", "tier": "sonnet", "role": "tester", "attempt": "1"},
                                   {"task": "t3", "tier": "opus", "role": "coder", "attempt": 1},
                                   {"task": "t4", "tier": "sonnet", "role": "coder", "attempt": 1},
                                   "not a dict", {"tier": "sonnet"}])
        write(self.d, "scope", [{"task": ["1"], "path": "a", "decision": "deny"}] * 2)
        write(self.d, "escalations", [{"reason": "x", "from_model": "sonnet", "to_model": "opus"}])
        write(self.d, "review", [{"task": "b1", "round": 1}, {"task": "b1", "round": 2}, {"task": "b1", "round": 1},
                                 {"task": "b2", "round": 1}, {"task": "b3", "round": "x"}])
        write(self.d, "merge", [{"task": "b1", "branch": "b1", "tasks_merged": 4, "cost_usd": 8.0},
                                {"task": "b2", "branch": "b2", "tasks_merged": 2},
                                {"task": "b9", "branch": "b9", "tasks_merged": 1, "cost_usd": 2.0}])
        d = tune.build()["delivery"]
        self.assertEqual(d["tasks_dispatched"], 4)
        self.assertEqual(d["scope_denials"], 2)
        self.assertAlmostEqual(d["scope_per_task"], 0.5)
        self.assertAlmostEqual(d["climb_rate"], 0.25)
        self.assertAlmostEqual(d["review_rounds_median"], 1.5)   # b1 max 2, b2 max 1, b3 has no valid round
        self.assertEqual((d["merges"], d["merges_without_review"]), (3, 1))  # b9
        self.assertAlmostEqual(d["cost_per_task"], 2.0)          # (8+2)/(4+1)
        self.assertEqual(d["merges_without_cost"], 1)

    def test_delivery_empty_logs_render_na(self):
        r = tune.build()
        d = r["delivery"]
        self.assertEqual((d["tasks_dispatched"], d["scope_per_task"], d["climb_rate"], d["review_rounds_median"], d["cost_per_task"]),
                         (0, None, None, None, None))
        text = tune.render(r, [])
        self.assertIn("Scope-lock denials per task (healthy 0-1): n/a", text)
        self.assertIn("Cost per merged task: n/a", text)

    def test_noop_proposal_dropped(self):
        th = thresholds.load()
        allow = th["gate"]["allowlist"]
        rep = {"questions": {}, "tool_calls": 500, "judged_share": 0.6, "top_judged_heads": [allow[0]],
               "swarm_vs_plain": None, "compare_count": 0}
        self.assertEqual(tune.proposals(rep, th), [])
```

Note: `write()` in this test file JSON-encodes each element, so `"not a dict"` becomes a JSON string line; `read()` must skip it (non-dict). If `read()` currently returns it, the `isinstance(r, dict)` filters in `delivery()` handle it.

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest -q claude/jev/tests/test_tune.py`
Expected: the six new tests FAIL (`canonical` missing, no `delivery` key, unfiltered count, no-op proposal returned).

- [ ] **Step 3: Implement** in `tune.py`. Add `import statistics` with the other imports. Add after `_steps`:

```python
CANONICAL = ("executor", "specific", "failing_test_exists", "needs_opus", "needs_stronger_model",
             "done", "risk", "safe_to_commit", "needs_interrogate")
_ALIASES = {"failing_tests_exist": "failing_test_exists", "failing_test": "failing_test_exists"}


def canonical(name: str) -> str:
    """Fold '<question>.<task>' and legacy task-affixed names onto CANONICAL; unknown names pass through."""
    base = str(name).split(".", 1)[0]
    if base in CANONICAL:
        return base
    s = re.sub(r"^t\d+_", "", base)
    s = re.sub(r"(_t\d+|_\d+|\d+|_any|_all|_kind)$", "", s)
    s = _ALIASES.get(s, s)
    return s if s in CANONICAL else str(name)


def _int(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if v == v and v >= 0 else None


def delivery(dispatch: List[Any], scope: List[Any], esc: List[Dict[str, Any]],
             review: List[Any], merge: List[Any]) -> Dict[str, Any]:
    dispatch = [r for r in dispatch if isinstance(r, dict)]
    review = [r for r in review if isinstance(r, dict)]
    merge = [r for r in merge if isinstance(r, dict) and r.get("task") is not None]
    tasks = {str(r["task"]) for r in dispatch if r.get("task") is not None and _int(r.get("attempt")) == 1}
    n = len(tasks)
    denials = sum(1 for r in scope if isinstance(r, dict))
    climbs = _steps(esc, "opus", "sonnet")["count"]
    rounds: Dict[str, int] = {}
    for r in review:
        k, v = r.get("task"), _int(r.get("round"))
        if k is not None and v is not None:
            rounds[str(k)] = max(rounds.get(str(k), 0), v)
    reviewed = {str(r.get("task")) for r in review if r.get("task") is not None}
    costed = [(c, _int(r.get("tasks_merged")) or 0) for r in merge for c in [_num(r.get("cost_usd"))] if c is not None]
    merged_tasks = sum(t for _, t in costed)
    return {
        "tasks_dispatched": n,
        "scope_denials": denials,
        "scope_per_task": round(denials / n, 4) if n else None,
        "climb_rate": round(climbs / n, 4) if n else None,
        "review_rounds_median": float(statistics.median(rounds.values())) if rounds else None,
        "merges": len(merge),
        "merges_without_review": sum(1 for r in merge if str(r["task"]) not in reviewed),
        "cost_per_task": round(sum(c for c, _ in costed) / merged_tasks, 4) if merged_tasks else None,
        "merges_without_cost": len(merge) - len(costed),
    }
```

Note on `test_delivery_metrics`: `b3` has a review record (invalid round), so it counts as reviewed but adds no round; `b9` has no review record. Expected `merges_without_review == 1`.

In `build()`:
- read the new logs: `dispatch, scope, review, merge = read("dispatch", log_dir), read("scope", log_dir), read("review", log_dir), read("merge", log_dir)`
- in the `mcp` loop, compute `cq = canonical(q)` and count into `q_calls[cq]` and `q_below[cq]` instead of `q`
- `q_over = Counter(canonical(str(r.get("question"))) for r in over)`
- change `"opus_escalations": _steps(esc, "opus"),` to `"opus_escalations": _steps(esc, "opus", "sonnet"),`
- add `"delivery": delivery(dispatch, scope, esc, review, merge),` to the returned dict

At the end of `proposals()`, replace `return out` with:

```python
    return [p for p in out if p["new"] != p["old"]]
```

In `render()`, define before `lines`:

```python
    d = rep["delivery"]

    def na(v: Any, fmt: str = "%.2f") -> str:
        return "n/a" if v is None else fmt % v

    delivery_lines = [
        "- Tasks dispatched: %d" % d["tasks_dispatched"],
        "- Scope-lock denials per task (healthy 0-1): %s (%d denials)" % (na(d["scope_per_task"]), d["scope_denials"]),
        "- Sonnet->Opus climb rate (healthy under 20%%): %s" % ("n/a" if d["climb_rate"] is None else "%.0f%%" % (d["climb_rate"] * 100)),
        "- Median review rounds per branch (healthy <= 1): %s" % na(d["review_rounds_median"], "%.1f"),
        "- Merges without a review (should be 0): %d of %d" % (d["merges_without_review"], d["merges"]),
        "- Cost per merged task: %s (%d of %d merges had no cost)" % (na(d["cost_per_task"], "$%.2f"), d["merges_without_cost"], d["merges"]),
    ]
```

Then split the existing `lines = [...]` literal right after the `"- Fable without a prior Opus step (should be 0): ..."` entry: the first part ends with that entry, then `lines += delivery_lines`, then `lines += [...]` with the remaining entries (swarm ratio, Jev spend, blank line, table header and separator) unchanged.

- [ ] **Step 4: Run the tune tests and the whole Jev suite**

Run: `python3 -m pytest -q claude/jev/tests`
Expected: all pass (existing `test_report_numbers` still passes: its escalations come from Sonnet).

- [ ] **Step 5: Commit**

```bash
git add claude/jev/tune.py claude/jev/tests/test_tune.py
git commit -m "feat(tune): delivery KPIs, canonical question names, sonnet filter, drop no-op proposals"
```

---

### Task 4: Skill and command text, both editions

**Files:**
- Modify: `claude/skills/orchestrate/SKILL.md`, `claude/commands/wreview.md`, `codex/skills/orchestrate/SKILL.md`, `codex/skills/wreview/SKILL.md`
- Create: `install/tests/test_metrics_logging_text.py`

**Interfaces:**
- Consumes: tool names `log_dispatch`, `log_review`, `log_merge` (Task 2); naming rule `<question>.<task>` (Task 3)
- Produces: skill instructions that call the tools

- [ ] **Step 1: Write the failing test** `install/tests/test_metrics_logging_text.py`

```python
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def test_orchestrate_texts_log_dispatch_and_merge():
    for rel in ("claude/skills/orchestrate/SKILL.md", "codex/skills/orchestrate/SKILL.md"):
        t = read(rel)
        for s in ("log_dispatch", "log_merge", "<question>.<task>"):
            assert s in t, (rel, s)


def test_wreview_texts_log_review():
    for rel in ("claude/commands/wreview.md", "codex/skills/wreview/SKILL.md"):
        assert "log_review" in read(rel), rel
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest -q install/tests/test_metrics_logging_text.py`
Expected: both FAIL.

- [ ] **Step 3: Edit the texts.**

`claude/skills/orchestrate/SKILL.md`:
- In `## 5. Dispatch`, after item 5 add:
  `6. Right after every dispatch (first or re-dispatch, any tier) call \`mcp__jev__log_dispatch\` with task (the PLAN.md task id), tier (sonnet, opus or fable), role (coder, tester, reviewer or docs) and attempt (1 for the first dispatch of that task, then +1 per re-dispatch).`
- In `## 7. Escalation`, after the line starting `First Sonnet failure:` add: `Each re-dispatch is logged with \`mcp__jev__log_dispatch\` (§5.6).`
- In `## 8. Finish`, replace `never push; then remove the worktree.` with: `never push; then call \`mcp__jev__log_merge\` with task and branch (the worktree branch name), tasks_merged (the number of task sections in .orchestrate/PLAN.md) and cost_usd when you have the session cost from /cost or a cost notice; then remove the worktree.`
- In `## Question rules (typesafe skill)`, append: ` When one call covers several tasks, name each question \`<question>.<task>\` (for example \`needs_opus.t3\`); /tune groups calls by the part before the dot.`

`claude/commands/wreview.md`: append to the body line: ` After each review round, call \`mcp__jev__log_review\` with task (the branch name), round (1 for the first review of this branch, +1 for each re-review) and the counts of critical, important and minor findings.`

`codex/skills/orchestrate/SKILL.md`:
- Item 3: append ` When one call covers several tasks, name each question \`<question>.<task>\` (for example \`needs_stronger_model.t3\`); $tune groups calls by the part before the dot.`
- Item 5: append ` After every dispatch, including retries and doing a task yourself, call \`log_dispatch\` (task, tier as the model name, role, attempt starting at 1).`
- Item 7: replace `never push; remove the worktree.` with `never push; call \`log_merge\` (task and branch = the worktree branch, tasks_merged = task sections in the plan, cost_usd if known); remove the worktree.`

`codex/skills/wreview/SKILL.md`: append a paragraph: `After each review round, call \`log_review\` (server \`jev\`) with task (the branch name), round (1 for the first review of this branch, +1 for each re-review) and the counts of critical, important and minor findings.`

- [ ] **Step 4: Run the install tests**

Run: `python3 -m pytest -q install/tests`
Expected: all pass, including shipped-file, template and portability tests.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/orchestrate/SKILL.md claude/commands/wreview.md codex/skills/orchestrate/SKILL.md codex/skills/wreview/SKILL.md install/tests/test_metrics_logging_text.py
git commit -m "feat(skills): log dispatch, review and merge; name batched questions <question>.<task>"
```

---

### Task 5: Docs

**Files:**
- Modify: `docs/metrics.md`, `docs/adoption-guide.md`, `docs/roadmap.md`, `install/tests/test_framework_docs.py`

**Interfaces:**
- Consumes: report line names from Task 3; record shapes from Tasks 1–2
- Produces: docs that state live status honestly

- [ ] **Step 1: Write the failing test** (append to class `FrameworkDocsTest` in `install/tests/test_framework_docs.py`)

```python
    def test_metrics_status_matches_logging(self):
        t = read("docs/metrics.md")
        self.assertNotIn("| planned |", t)              # no KPI row left as planned
        self.assertIn("## Logging records", t)
        self.assertNotIn("by hand until", read("docs/adoption-guide.md"))
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest -q install/tests/test_framework_docs.py`
Expected: FAIL.

- [ ] **Step 3: Edit the docs.**

`docs/metrics.md`:
- GOV-M4 row: Source `` `scope` ``, Status `live`.
- ESC-M1 row: Source `` `escalations`, `dispatch` ``, Status `live: only climbs from Sonnet count`.
- EXE-M3 row: Source `` `merge` ``, Status `partial: cost_usd is entered by hand; /tune reports how many merges lack it`.
- REV-M1 row: Source `` `review` ``, Status `live`.
- Replace the `## Planned logging` heading and its intro line with `## Logging records` and the line: `Each record is written once, at the point shown. Records written by the orchestrator or /wreview are only as complete as those calls; the scope record is written by the hook itself.` Update the table rows: `scope` | task, path, decision | scope-lock hook, on every deny | GOV-M4; `dispatch` | task, tier, role, attempt | orchestrator via `log_dispatch`, every dispatch | GOV-M4, ESC-M1; `review` | task, round, critical, important, minor | `/wreview` via `log_review`, every round | REV-M1; `merge` | task, branch, tasks_merged, cost_usd (optional) | orchestrator via `log_merge`, at merge | EXE-M3.
- In "How to read this", in the Status bullet, replace the clause `; [Planned logging](#planned-logging) lists each one` with `. [Logging records](#logging-records) lists what writes each log`.

`docs/adoption-guide.md` maturity table:
- L1 exit: `Every merged change had an approved design (checked by hand) and a review (/tune: merges without a review = 0), and REV-M1 ≤ 1.`
- L2 exit: `GOV-M4 ≤ 1 denial per task.`
- L3 turn-on: `Cheap executors and the escalation ladder, with every climb logged.` L3 exit: `ESC-M1 under 20% and ESC-M2 = 0.`

`docs/roadmap.md`:
- Replace the unticked "Log the planned metrics" item with: `- [x] Log the planned metrics: scope, dispatch, review and merge records, reported by /tune ([metrics.md](metrics.md#logging-records))`
- Metrics status row: `Covered (EXE-M3 cost is entered by hand)`

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add docs/metrics.md docs/adoption-guide.md docs/roadmap.md install/tests/test_framework_docs.py
git commit -m "docs(metrics): mark logged KPIs live; logging records; maturity exits"
```
