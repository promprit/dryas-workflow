# Compound Commands in the Jev Gate Implementation Plan

> **For agentic workers:** this plan is executed by `/orchestrate` (Opus orchestrator, Sonnet executors, scope lock). Each executor receives only its own task section. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Skip the judge for compound Bash commands whose every part is allowlisted and whose parts are joined only by `&&`, `||`, `;`, `|` (plus the redirects `2>&1`, `>/dev/null`, `2>/dev/null`), with a kill switch.

**Architecture:** A quote-aware scanner `split_compound()` in `claude/jev/gate.py` returns parts or `None`. `allowlisted_compound()` requires every part to pass the unchanged `allowlisted()`. `run()` keeps the old single-command check as a floor and only adds the compound check when `gate.compound` is true. A skip record gains `parts`.

**Tech Stack:** Python 3 stdlib only, unittest/pytest.

**Spec:** `docs/superpowers/specs/2026-10-06-compound-gate-design.md` (contested: `/interrogate` is mandatory)

## Global Constraints

- `allowlisted(cmd, allowlist)` is not modified. Nothing is added to `DEFAULTS["gate"]["allowlist"]`.
- New code can only add skips: if the compound path does not skip, the result is exactly today's.
- With `gate.compound` false, gate behavior is exactly as before this change.
- `split_compound` returns `None` (judge) on: any of `; & | < > ( )`, backtick or `$(` inside quotes; any other `&`, `<`, `>`, `(`, `)`, backtick or `$(` outside quotes; a backslash anywhere; newline or carriage return; unclosed quote; an empty part; more than 8 parts.
- Allowed redirects are standalone words only: `2>&1`, `>/dev/null`, `2>/dev/null`, outside quotes, preceded by start-of-part or space/tab and followed by end, space, tab, `;`, `|` or `&`.
- Python stdlib only. Files stay under 500 lines.
- Full suite: `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests`.

## Review Focus

1. A bash comment (`#`) makes bash run less than the parts, never more; the splitter may still judge or skip on the full text. Pinned in Task 1 (`ls # x; pwd` is skipped only because both parts are allowlisted).
2. Redirect lookalikes (`2>&1x`, `>/dev/nullx`, `>& /dev/null`, `'2>&1'`) must be judged. Pinned in Task 1.
3. Commands that the old `allowlisted()` accepted must stay skipped even where `split_compound` returns `None` (for example `ls \foo` with a backslash). Pinned in Task 1 (`test_old_single_skip_is_a_floor`). Known pre-existing quirk, not changed here: the old check accepts `ls\rpwd` because `shlex` treats `\r` as whitespace; bash does not, so the command fails as not found.
4. The default install's allowlist has no `cd` or `grep`; tests must pass their own allowlist rather than relying on a user's `thresholds.json`. Pinned in Task 1.
5. A wrong-typed `gate.compound` is rejected by `thresholds.validate` (used by `/tune apply`). Pinned in Task 1.

---

### Task 1: Splitter, compound check, kill switch and logging

**Files:**
- Modify: `claude/jev/gate.py`
- Modify: `claude/jev/thresholds.py` (`DEFAULTS["gate"]`)
- Create: `claude/jev/tests/test_gate_compound.py`
- Modify: `claude/jev/tests/test_thresholds.py`

**Interfaces:**
- Produces: `gate.split_compound(cmd: str) -> Optional[List[str]]`; `gate.allowlisted_compound(cmd: str, allowlist: List[str]) -> Tuple[bool, int]`; `gate.MAX_PARTS = 8`; threshold `gate.compound: bool = True`; `gate` skip record field `parts: int` when more than one part.

- [ ] **Step 1: Write the failing tests.** Create `claude/jev/tests/test_gate_compound.py`:

```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate

AL = ["ls", "cat", "head", "tail", "wc", "pwd", "git status", "git diff", "git log", "git show",
      "pytest", "python3 -m pytest", "cd", "grep"]

SKIP = {
    "cd /x && git status 2>&1 | tail -3": 3,
    "cd x&&git status": 2,
    "ls; pwd": 2,
    "ls || pwd": 2,
    "git status >/dev/null": 1,
    "git status 2>/dev/null && ls": 2,
    "git status 2>&1": 1,
    "cd 'my dir' && ls": 2,
    "cd \"a'b\" && ls": 2,
    "grep -rn foo . | head -5": 2,
    "cd x\t&&\tls": 2,
    "ls;ls;ls;ls;ls;ls;ls;ls": 8,
    "cd /x && python3 -m pytest -q 2>&1 | tail -1": 3,
    "ls # x; pwd": 2,
}

JUDGE = [
    "ls | sh", "cd /x && git push", "grep -r x . > out.txt", 'git log --format="%h|%s"', "cat a; rm -rf b",
    "ls &", "cat <(ls)", "ls >(cat)", "ls >| f", "ls &> f", "ls |& cat", "ls \\; pwd", "ls\npwd", "ls\rpwd",
    "ls;;pwd", "ls &&", "; ls", "ls;ls;ls;ls;ls;ls;ls;ls;ls", "ls '2>&1'", "ls >/dev/nullx", "ls 2>&1x",
    "ls >& /dev/null", "", "   ", "ls；rm -rf x", "ls $'a;b'", 'ls "$(rm x)"', "ls `rm x`", "ls $(pwd)",
    "cat <<EOF", "ls 'unclosed && pwd", "git status --output=x && ls", "git -c core.pager=sh log && ls",
    "ls 2>&1 &", "FOO=1 ls && pwd",
]

FORBIDDEN = set(";&|<>()`\\\n\r")


class SplitTest(unittest.TestCase):
    def test_skip_cases(self):
        for cmd, n in SKIP.items():
            self.assertEqual(gate.allowlisted_compound(cmd, AL), (True, n), repr(cmd))

    def test_judge_cases(self):
        for cmd in JUDGE:
            self.assertEqual(gate.allowlisted_compound(cmd, AL)[0], False, repr(cmd))

    def test_skipped_parts_are_clean_and_allowlisted(self):
        for cmd in SKIP:
            parts = gate.split_compound(cmd)
            self.assertIsNotNone(parts, repr(cmd))
            for p in parts:
                self.assertTrue(gate.allowlisted(p, AL), (cmd, p))
                self.assertFalse(FORBIDDEN & set(p), (cmd, p))
                self.assertNotIn("$(", p, (cmd, p))

    def test_split_returns_parts(self):
        self.assertEqual(gate.split_compound("cd /x && git status 2>&1 | tail -3"), ["cd /x", "git status", "tail -3"])
        self.assertIsNone(gate.split_compound("ls;" * 9 + "ls"))


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = os.path.join(self.tmp, "logs")
        os.environ["JEV_SSD_ROOT"] = self.tmp
        self.calls = []

    def thresholds(self, **gate_cfg):
        p = os.path.join(self.tmp, "th.json")
        with open(p, "w") as f:
            json.dump({"gate": dict({"allowlist": AL}, **gate_cfg)}, f)
        os.environ["JEV_THRESHOLDS"] = p

    def judge(self, state, questions):
        self.calls.append(state)
        return {"answers": {"safe": {"type": "noul", "value": 0.9, "confidence": 0.9},
                            "risk": {"type": "choice", "value": "routine", "confidence": 0.9, "probabilities": {}}},
                "latency_ms": 1, "input_tokens": 1, "cost": 0.0}

    def bash(self, cmd):
        return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": self.tmp}

    def records(self):
        with open(os.path.join(self.tmp, "logs", "gate.jsonl")) as f:
            return [json.loads(l) for l in f]

    def test_compound_skip_logs_parts(self):
        self.thresholds()
        self.assertIsNone(gate.run(self.bash("cd x && ls | head -1"), judge_fn=self.judge))
        self.assertEqual(self.calls, [])
        rec = self.records()[-1]
        self.assertEqual((rec["decision"], rec["parts"]), ("skipped", 3))

    def test_single_skip_has_no_parts_field(self):
        self.thresholds()
        gate.run(self.bash("ls"), judge_fn=self.judge)
        self.assertNotIn("parts", self.records()[-1])

    def test_kill_switch_judges_compound(self):
        self.thresholds(compound=False)
        gate.run(self.bash("cd x && ls"), judge_fn=self.judge)
        self.assertEqual(len(self.calls), 1)
        gate.run(self.bash("ls"), judge_fn=self.judge)
        self.assertEqual(len(self.calls), 1)  # single allowlisted command still skipped

    def test_old_single_skip_is_a_floor(self):
        self.thresholds()
        gate.run(self.bash("ls \\foo"), judge_fn=self.judge)  # backslash: split_compound gives None, old check skips
        self.assertEqual(self.calls, [])
```

Append to `claude/jev/tests/test_thresholds.py`, inside class `ThresholdsTest` (not `HandoffThresholdsTest`; the file already imports `thresholds`):

```python
    def test_gate_compound_default_and_validation(self):
        self.assertIs(thresholds.DEFAULTS["gate"]["compound"], True)
        self.assertIsNone(thresholds.validate("gate.compound", False))
        self.assertIsNotNone(thresholds.validate("gate.compound", "no"))
        self.assertIsNotNone(thresholds.validate("gate.compound", 0))
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest -q claude/jev/tests/test_gate_compound.py claude/jev/tests/test_thresholds.py`
Expected: FAIL with `AttributeError: module 'gate' has no attribute 'allowlisted_compound'` (and `split_compound`), and `KeyError: 'compound'`.

- [ ] **Step 3: Implement.** In `claude/jev/thresholds.py`, add `"compound": True,` to `DEFAULTS["gate"]` right after `"ask_risk": "destructive",`.

In `claude/jev/gate.py`, make sure the typing import includes `List`, `Optional` and `Tuple`, and add after `allowlisted()`:

```python
MAX_PARTS = 8
_SAFE_REDIRECTS = ("2>/dev/null", "2>&1", ">/dev/null")
_BAD_IN_QUOTES = set(";&|<>()`")
_BAD_OUTSIDE = set("&<>()`")


def split_compound(cmd: str) -> Optional[List[str]]:
    """Split on &&, ||, ; and | outside quotes; drop safe standalone redirects.

    Returns None (send to the judge) for anything else unusual. Never returns a part that
    contains a shell operator, a backslash or a newline.
    """
    if not cmd or "\\" in cmd or "\n" in cmd or "\r" in cmd:
        return None
    parts: List[str] = []
    cur: List[str] = []
    quote: Optional[str] = None
    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        if quote:
            if c == quote:
                quote = None
            elif c in _BAD_IN_QUOTES:
                return None
            cur.append(c)
            i += 1
            continue
        if c in "'\"":
            quote = c
            cur.append(c)
            i += 1
            continue
        if not cur or cur[-1] in " \t":
            r = next((r for r in _SAFE_REDIRECTS if cmd.startswith(r, i)), None)
            if r and (i + len(r) == n or cmd[i + len(r)] in " \t;|&"):
                i += len(r)
                continue
        if cmd.startswith("|&", i):
            return None
        op = "&&" if cmd.startswith("&&", i) else "||" if cmd.startswith("||", i) else c if c in ";|" else ""
        if op:
            part = "".join(cur).strip()
            if not part:
                return None
            parts.append(part)
            cur = []
            i += len(op)
            continue
        if c in _BAD_OUTSIDE:
            return None
        cur.append(c)
        i += 1
    if quote:
        return None
    part = "".join(cur).strip()
    if not part:
        return None
    parts.append(part)
    return parts if len(parts) <= MAX_PARTS else None


def allowlisted_compound(cmd: str, allowlist: List[str]) -> Tuple[bool, int]:
    parts = split_compound(cmd)
    if not parts or not all(allowlisted(p, allowlist) for p in parts):
        return False, 0
    return True, len(parts)
```

In `run()`, replace

```python
    if tool == "Bash" and allowlisted(str(ti.get("command", "")), t["allowlist"]):
        jevlog.append("gate", dict(base, decision="skipped"))
        return None
```

with

```python
    if tool == "Bash":
        cmd = str(ti.get("command", ""))
        ok, n = allowlisted(cmd, t["allowlist"]), 1
        if not ok and t.get("compound", True):
            ok, n = allowlisted_compound(cmd, t["allowlist"])
        if ok:
            jevlog.append("gate", dict(base, decision="skipped", **({"parts": n} if n > 1 else {})))
            return None
```

This splitter was run against the SKIP and JUDGE tables above before the plan was written; all cases matched.

- [ ] **Step 4: Run the gate and thresholds tests, then the Jev suite**

Run: `python3 -m pytest -q claude/jev/tests/test_gate_compound.py claude/jev/tests/test_gate.py claude/jev/tests/test_thresholds.py`
Expected: all pass.
Run: `python3 -m pytest -q claude/jev/tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add claude/jev/gate.py claude/jev/thresholds.py claude/jev/tests/test_gate_compound.py claude/jev/tests/test_thresholds.py
git commit -m "feat(gate): skip compound commands whose parts are all allowlisted; gate.compound kill switch"
```

---

### Task 2: Docs

**Files:**
- Modify: `docs/governance.md`, `docs/workflow.md`, `docs/metrics.md`
- Modify: `install/tests/test_framework_docs.py`

**Interfaces:**
- Consumes: threshold name `gate.compound` and the joining rules from Task 1.

- [ ] **Step 1: Write the failing test** (append to class `FrameworkDocsTest` in `install/tests/test_framework_docs.py`)

```python
    def test_compound_gate_documented(self):
        self.assertIn("gate.compound", read("docs/governance.md"))
        self.assertIn("compound true", read("docs/workflow.md"))
        self.assertIn("gate.compound", read("docs/metrics.md"))
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest -q install/tests/test_framework_docs.py`
Expected: FAIL on the first assertion.

- [ ] **Step 3: Edit the docs.**

`docs/governance.md`: append to the end of the line that starts `5. **Gates never auto-allow.**` (same line, after its last sentence): ` Allowlisted commands skip the judge; a compound command skips it only when every part is allowlisted and the parts are joined by \`&&\`, \`||\`, \`;\` or \`|\` (plus \`2>&1\`, \`>/dev/null\`, \`2>/dev/null\`). Setting \`gate.compound\` to false turns compound skipping off.`

`docs/workflow.md`: in the thresholds table, change the gate row `| gate | deny_safe_below 0.2, min_confidence 0.7, ask_risk destructive, allowlist |` to `| gate | deny_safe_below 0.2, min_confidence 0.7, ask_risk destructive, allowlist, compound true |`.

`docs/metrics.md`: in the GOV-M1 row's "If out of range" cell (last cell of the row starting `| GOV-M1 |`), append before the closing `|`: ` If a compound-command skip looks wrong, set \`gate.compound\` to false and report the command.`

- [ ] **Step 4: Run the install tests**

Run: `python3 -m pytest -q install/tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add docs/governance.md docs/workflow.md docs/metrics.md install/tests/test_framework_docs.py
git commit -m "docs(gate): document compound skipping and the gate.compound kill switch"
```
