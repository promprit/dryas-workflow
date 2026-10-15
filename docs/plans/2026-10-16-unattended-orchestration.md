# Unattended orchestration — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract; Interfaces and Steps follow. Steps use checkbox (`- [ ]`) syntax.

**Goal:** After the user approves the design and the plan, `/orchestrate` runs to the end without asking the user anything: executor shell writes never prompt, risky commands climb plan → judge → orchestrator → user, and every run ends with one plain-language report and stored lessons.

**Architecture:** Shell write detection moves from regexes (`prescreen.writes`) onto local_judge's quote- and heredoc-aware parser in a new `shellwrites.py`, which also reads the files a command writes. The scope lock denies readable out-of-scope targets and allows the rest; a deterministic `scope_audit.py` checks each task's commits and leftovers at task return. The Jev gate turns asks into denies during a run unless the plan's `## Risky actions` or the orchestrator's `.orchestrate/approved.json` covers the command (`runrules.py`). `preflight.py` refuses to start a run in a permission mode that can prompt; `run_report.py` and `/tune` count prompts, denies and violations.

**Tech Stack:** Python 3 stdlib (unittest, subprocess, json), git, the Dryas hook chain (`claude/jev/chain.json`), Markdown skills for Claude Code, Codex and OpenCode.

**Spec:** `docs/specs/2026-10-15-scope-lock-shell-writes-design.md`

## Global Constraints

- Python stdlib only; type hints in the style of the neighbouring module (`typing.List`, `Dict`, `Optional`). Every file stays under 500 lines.
- `claude/` is the source of truth. `codex/jev/`, `opencode/dryas/jev/` and the rendered skills and agents are written only by `python3 tools/sync_codex_plugin.py`, which Task 12 runs. Tasks 1-11 never edit them, except the hand-written files Task 10 names.
- No new `"ask"` decision anywhere. During a run (`.orchestrate/active.json` with a non-empty `active` list) no hook asks the user.
- Log records only gain fields. Keep `decision`, `task`, `tool`, `path` as they are (FlowObserve and `/tune` read them). New fields: `kind`, `rule`, `run`.
- Everything shown to the user is plain language a non-programmer can act on: outcome first, technical details after (spec section G).
- Commit subjects are Conventional Commits ending with `(task N)`; stage explicit paths only.
- Test command (from the worktree root): `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests`.
- Release version: `2.3.1` (a bug-fix release of 2.3).

## Review Focus

- A command that `cd`s somewhere and then writes with a relative path (`cd apps/bot && sed -i '' 's/a/b/' src/x.ts`) must be checked against the directory it moved to, and `cd $DIR` must make later targets unknown (allowed, then audited), never wrongly allowed or denied. Pinned in Task 2.
- File names with spaces or quotes (`sed -i 's/a/b/' "my file.ts"`) are one target, not two. Pinned in Task 2.
- A symlink inside the scratchpad that points into the worktree, or a look-alike folder (`scratchpad2`, another session's id), must not pass as the scratchpad. Pinned in Task 3.
- An executor that reports another task's commit, or a sha not on the branch, must fail the audit. Pinned in Task 4.
- A planned prefix (`pnpm db:reset*`) must not cover a compound command that also does something else risky (`pnpm db:reset && git reset --hard`), and must not match a longer word (`pnpm db:resetall`). Pinned in Task 5.

---

## Task 1: Redirect operators in the local judge parser

Goal: `local_judge` records the operator and the dynamic flag of every redirect, and exposes its parser as public `simple_commands`, `head_index`, `base` and `shell_string`, so other modules can read what a command writes.
Scope:
- claude/jev/local_judge.py
- claude/jev/tests/test_local_judge_redirs.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_local_judge_redirs.py claude/jev/tests/test_local_judge.py claude/jev/tests/test_local_judge_cases.py claude/jev/tests/test_local_judge_heredoc.py claude/jev/tests/test_local_judge_discard.py` passes
- `local_judge.danger` / `destructive` results are unchanged (the existing local judge tests pass unmodified)
Failing test first: claude/jev/tests/test_local_judge_redirs.py :: RedirsTest.test_output_operators

**Interfaces:**
- Consumes: nothing new.
- Produces: `local_judge.simple_commands(text: str) -> List[_Cmd]` (raises `ValueError` when `len(text) > MAX_CHARS`); `_Cmd.rops: List[str]` (operator per redirect, same order as `_Cmd.redirs`: `>`, `>>`, `>|`, `>&`, `&>`, `&>>`, `<`, `<<`, `<<-`, `<<<`, `<>`, `<&`); `_Cmd.rdyn: List[bool]` (the redirect target held `$(` or a backtick); `local_judge.head_index = _head`, `local_judge.base = _base`, `local_judge.shell_string = _shell_string`.

- [ ] **Step 1: Write the failing test.** Create `claude/jev/tests/test_local_judge_redirs.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import local_judge as lj


def one(text, first=None):
    cmds = lj.simple_commands(text)
    return [c for c in cmds if not first or c.words[:1] == [first]][0]


class RedirsTest(unittest.TestCase):
    def test_output_operators(self):
        c = one("echo a > f >> g 2>&1 &> h &>> i >| j")
        self.assertEqual(list(zip(c.rops, c.redirs)),
                         [(">", "f"), (">>", "g"), (">&", "1"), ("&>", "h"), ("&>>", "i"), (">|", "j")])

    def test_input_and_heredoc_operators(self):
        c = one("cat < in <<EOF\nbody > x\nEOF")
        self.assertEqual(list(zip(c.rops, c.redirs)), [("<", "in"), ("<<", "EOF")])
        self.assertEqual(c.here, ["body > x"])

    def test_quoted_target_is_one_word(self):
        c = one('echo hi > "my file.txt"')
        self.assertEqual((c.rops, c.redirs, c.rdyn), ([">"], ["my file.txt"], [False]))

    def test_dynamic_target(self):
        c = one('echo x > "$(pwd)/f"', "echo")
        self.assertEqual((c.rops, c.rdyn), ([">"], [True]))

    def test_arrow_in_heredoc_body_is_data(self):
        c = one("python3 - <<'EOF'\nf = lambda: a => {}\nEOF")
        self.assertEqual(c.rops, ["<<"])

    def test_too_long_raises(self):
        with self.assertRaises(ValueError):
            lj.simple_commands("a" * (lj.MAX_CHARS + 1))

    def test_public_helpers(self):
        self.assertEqual(lj.head_index(["sudo", "env", "X=1", "rm", "x"]), (3, False))
        self.assertEqual(lj.base("/bin/rm"), "rm")
        self.assertEqual(lj.shell_string(["-c", "rm x"]), "rm x")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q claude/jev/tests/test_local_judge_redirs.py`. Expected: FAIL with `AttributeError: module 'local_judge' has no attribute 'simple_commands'`.
- [ ] **Step 3: Implement.** In `claude/jev/local_judge.py`:
  1. `_Cmd`: `__slots__ = ("words", "dyn", "redirs", "rops", "rdyn", "here", "src")`; in `__init__` add `self.rops: List[str] = []` and `self.rdyn: List[bool] = []`; extend the docstring: "redirect operators (`rops`) and whether each target held $( or a backtick (`rdyn`)".
  2. `_scan`: add `rop = ""` next to `hkind = ""`. In `end_word`, inside `if redir:` right after `cmd.redirs.append(word)`, add `cmd.rops.append(rop)` and `cmd.rdyn.append(dyn)`.
  3. `push_sub` / `pop_sub`: add `rop` to their `nonlocal` lists and save it with the outer state: `stack.append((kind, (cmd, cur, redir, quote, rop)))`, and `_, (cmd, cur, redir, quote, rop) = stack.pop()`.
  4. The `&>` branch becomes:
     ```python
        elif c == "&" and nxt == ">":
            end_word()
            redir = True
            rop = "&>>" if s[i + 2:i + 3] == ">" else "&>"
            i += 2 if rop == "&>>" else 1
     ```
     (`rop` is assigned in the main loop, so add `nonlocal`-free use: it is a local of `_scan`; `end_word` reads it, which needs no `nonlocal`.)
  5. In the `c in "<>"` branch, after `op` is final (after the `<<-` adjustment), add `rop = op`.
  6. After `_shell_string`, add:
     ```python
     def simple_commands(text: str) -> List[_Cmd]:
         """Public parse of `text` into simple commands (see _scan) for shellwrites. Raises ValueError over MAX_CHARS."""
         if len(text) > MAX_CHARS:
             raise ValueError("command longer than %d characters" % MAX_CHARS)
         return _scan(text)


     head_index = _head
     base = _base
     shell_string = _shell_string
     ```
- [ ] **Step 4: Run the tests.** Run the Done command. Expected: PASS.
- [ ] **Step 5: Commit** `claude/jev/local_judge.py claude/jev/tests/test_local_judge_redirs.py` as `feat(jev): local judge parser records redirect operators (task 1)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 2: shellwrites — what a shell command writes

Goal: New `claude/jev/shellwrites.py` decides whether a Bash command writes files and which absolute paths it writes, from the parsed command (heredoc bodies and quoted text are data); `prescreen.writes` and its regexes are removed.
Scope:
- claude/jev/shellwrites.py
- claude/jev/prescreen.py
- claude/jev/tests/test_shellwrites.py
- claude/jev/tests/test_gate_prescreen.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_shellwrites.py claude/jev/tests/test_gate_prescreen.py` passes
- `grep -n "_WRITE_\|def writes" claude/jev/prescreen.py` prints nothing
Failing test first: claude/jev/tests/test_shellwrites.py :: ShellWritesTest.test_old_write_cases

**Interfaces:**
- Consumes: Task 1's `local_judge.simple_commands`, `head_index`, `base`, `shell_string`, `_Cmd.rops`, `_Cmd.rdyn`; `prescreen._SED_CMD` (kept).
- Produces: `shellwrites.Analysis(writes: bool, paths: List[str], unknown: bool, rule: str)` (a NamedTuple) and `shellwrites.analyse(cmd: str, cwd: str) -> Analysis`. `paths` are absolute and `posixpath.normpath`-ed, not symlink-resolved. `rule` is the first rule that fired, one of `redirect`, `sed`, `perl`, `dd`, `git`, `rm`, `rmdir`, `unlink`, `shred`, `mkdir`, `touch`, `truncate`, `tee`, `chmod`, `chown`, `chflags`, `cp`, `mv`, `ln`, `install`, `inline_code`, `script`, `package`, `sed_script`, `dynamic_command`, `xargs`, `nested`, `error`, or an archive/copy tool name from `_UNREAD`; `""` when nothing writes.

- [ ] **Step 1: Write the failing test.** Move the `WRITES`, `NOT_WRITES` lists and the `TestWrites` class out of `claude/jev/tests/test_gate_prescreen.py` (delete them there, and delete its now-unused imports if any) into the new `claude/jev/tests/test_shellwrites.py`:

```python
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import local_judge
import shellwrites as sw

WT = "/w"
WRITES = ["rm -rf build", "mv a b", "cp -r a b", "tee out.txt", "sed -i 's/a/b/' f", "sed -i '' 's/a/b/' f", "truncate -s 0 f",
          "dd if=/dev/zero of=f", "echo x > f", "cat a >> b", "cmd 2>&1 > log", "git checkout -- f", "git restore .",
          "git reset --hard", "git clean -fd", "git stash pop", "mkdir -p x", "touch f", "tar xf a.tgz", "unzip a.zip",
          "chmod +x f", "npm install x", "pip install y", "cd /p && rm x", "ls; rm x", "/bin/rm x", "r\\m x", "'rm' x"]
NOT_WRITES = ["ls -la", "git status", "git diff --stat", "git log --oneline -5", "grep -rn foo src", "cat f 2>/dev/null",
              "cmd 2>&1", "python3 -m pytest -q", "echo '>' done", "make test", "curl https://x", "git push origin main",
              "npm test", "pnpm lint", "find . -name '*.py'", "wc -l f", "sort f", "docker ps", ""]


def a(cmd, cwd=WT):
    return sw.analyse(cmd, cwd)


class ShellWritesTest(unittest.TestCase):
    def test_old_write_cases(self):
        for c in WRITES:
            self.assertTrue(a(c).writes, c)

    def test_old_read_only_cases(self):
        for c in NOT_WRITES:
            self.assertFalse(a(c).writes, c)

    def test_inline_code_and_local_scripts_are_unknown_writes(self):
        for c in ("python -c \"open('x','w').write('a')\"", "python3 -I -c 'import os'", "node -e 'fs.writeFileSync(1)'",
                  "perl -e 'unlink shift'", "ruby -e 'File.delete(1)'", "php -r 'unlink(1);'", "./build.sh",
                  "cd src && ./gen", "sh gen.sh", "bash -x scripts/x.sh", "../tools/run.sh --fast",
                  "python3 - <<'EOF'\nopen('a', 'w').write('x')\nEOF", "cat x.py | python3"):
            r = a(c)
            self.assertTrue(r.writes and r.unknown, c)
        self.assertEqual(a("python3 - <<'EOF'\nprint(1)\nEOF").rule, "inline_code")
        for c in ("python3 x.py", "python3 -m pytest -q", "node index.js", "npm run build", "make", "go build ./...",
                  "echo ./x", "ls ./", "cat ./README.md"):
            self.assertFalse(a(c).writes, c)

    def test_code_and_prose_are_not_commands(self):
        for c in ('git commit -q -m "fix: split (install) store tests" -- a.ts',
                  "python3 -m pytest -q 2>&1 | tail -3",
                  "cat <<'EOF' | grep x\nconst a = () => { b > c }\nEOF",
                  "pnpm biome check --write src/a.ts 2>&1 | tail -2",
                  "git add src/a.ts && git commit -m 'x'",
                  "grep -n 'a => b' src/a.ts"):
            self.assertFalse(a(c).writes, c)

    def test_readable_targets(self):
        cases = {
            "cd /w/apps/bot && sed -i '' 's/a/b/g' src/x.ts": ["/w/apps/bot/src/x.ts"],
            "sed -i.bak -e 's/a/b/' a.ts b.ts": ["/w/a.ts", "/w/b.ts"],
            "sed -Ei 's/a/b/' a.ts": ["/w/a.ts"],
            "perl -0pi -e 's/x/y/' src/a.ts": ["/w/src/a.ts"],
            "echo x > out/f.txt 2>/dev/null": ["/w/out/f.txt"],
            "cp a.ts /tmp/b.ts": ["/tmp/b.ts"],
            "mv -t dest a b": ["/w/dest"],
            "mkdir -p x/y && touch x/y/z": ["/w/x/y", "/w/x/y/z"],
            "truncate -s 0 f": ["/w/f"],
            "git checkout HEAD~1 -- src/a.ts": ["/w/src/a.ts"],
            "git restore --source HEAD~1 src/a.ts": ["/w/src/a.ts"],
            "tee -a log.txt": ["/w/log.txt"],
            "dd if=/dev/zero of=img bs=1": ["/w/img"],
            "bash -c 'rm a'": ["/w/a"],
            'sed -i "s/a/b/" "my file.ts"': ["/w/my file.ts"],
            "chmod -R 755 dist": ["/w/dist"],
            "rm ../outside.txt": ["/outside.txt"],
        }
        for c, paths in cases.items():
            r = a(c)
            self.assertEqual((r.writes, r.paths, r.unknown), (True, paths, False), c)

    def test_sed_without_in_place_reads_only(self):
        for c in ("sed -n 1,5p f", "sed 's/a/b/' f > /dev/null", "sed -e 's/a/b/' f"):
            self.assertFalse(a(c).writes, c)
        r = a("sed -n 'w out' f")
        self.assertTrue(r.writes and r.unknown)

    def test_unknown_targets(self):
        for c in ("rm $F", "rm *.bak", 'echo > "$(pwd)/x"', "cd $DIR && rm a", "rm ~/x", "git stash",
                  "git -C ../other checkout -- a", "find . -name x | xargs rm", "$PY -c 'x'", "sed -f s.sed f"):
            r = a(c)
            self.assertTrue(r.writes and r.unknown, c)

    def test_relative_target_without_cwd_is_unknown(self):
        r = sw.analyse("rm a", "")
        self.assertTrue(r.writes and r.unknown)
        self.assertEqual(r.paths, [])

    def test_too_long_or_broken_is_unknown_write(self):
        self.assertEqual(a("x" * (local_judge.MAX_CHARS + 1)), sw.Analysis(True, [], True, "error"))

    def test_linear(self):
        for payload in ("rm " * 30000, "echo " + ">" * 50000, "git " * 20000 + "checkout", "a=>b " * 12000):
            t0 = time.monotonic()
            a(payload)
            self.assertLess(time.monotonic() - t0, 0.5, payload[:10])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q claude/jev/tests/test_shellwrites.py`. Expected: FAIL with `ModuleNotFoundError: No module named 'shellwrites'`.
- [ ] **Step 3: Implement.** Create `claude/jev/shellwrites.py`:

```python
#!/usr/bin/env python3
"""What a Bash command writes, for the scope lock (unattended orchestration).

analyse(cmd, cwd) parses the command with local_judge's quote- and heredoc-aware scanner, so heredoc bodies and
quoted text (commit messages, inline code) are data, never commands. It returns an Analysis:
  writes  - something in it writes, moves or deletes files, or runs code that may (inline code, scripts)
  paths   - absolute paths the readable forms write: sed -i, perl -i, output redirects, tee, dd of=, the
            destination of cp/mv/ln/install, the operands of rm/rmdir/unlink/shred/mkdir/touch/truncate and
            chmod/chown/chflags, and git checkout -- / git restore paths. `cd <literal>` is followed.
  unknown - some write could not be read (inline interpreter code, scripts, $VAR, $(...), globs, ~, xargs, a cd to
            an unknown place, archives, package installs, other git writes)
  rule    - the first rule that fired, for the scope log ("" when nothing writes)
Pure, stdlib only, never raises: a parse error or a command over local_judge.MAX_CHARS is Analysis(True, [], True,
"error").
"""
import os
import posixpath
import re
import sys
from typing import List, NamedTuple, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_judge as lj
from prescreen import _SED_CMD

_DEPTH = 3
_OUT_OPS = frozenset({">", ">>", ">|", "&>", "&>>", "<>", ">&"})
_UNSURE = frozenset("$`~*?[")
# options whose value is a separate word (that word is not a target)
_VALUE_OPTS = {
    "truncate": {"-s", "--size", "-r", "--reference"}, "mkdir": {"-m", "--mode"},
    "touch": {"-t", "-d", "-r", "--date", "--reference"}, "shred": {"-n", "-s", "--iterations", "--size"},
    "install": {"-m", "-o", "-g", "-S", "--mode", "--owner", "--group", "--suffix"},
    "cp": {"-S", "--suffix"}, "mv": {"-S", "--suffix"}, "ln": {"-S", "--suffix"},
    "git-restore": {"-s", "--source"},
}
_ALL_OPERANDS = {"rm", "rmdir", "unlink", "shred", "mkdir", "touch", "truncate", "tee"}
_FIRST_IS_MODE = {"chmod", "chown", "chflags"}
_DEST = {"cp", "mv", "ln", "install"}
_UNREAD = {"rsync", "scp", "ditto", "patch", "split", "csplit", "cpio", "tar", "unzip", "zip", "gzip", "gunzip",
           "bzip2", "xz", "unxz", "7z", "mkfifo"}
_GIT_WRITE = {"checkout", "switch", "restore", "reset", "clean", "stash", "rm", "mv", "apply", "am", "rebase", "merge",
              "pull", "cherry-pick", "revert"}
_PM = {"pip", "pip3", "uv", "cargo", "gem", "poetry", "pnpm", "npm", "yarn"}
_PM_WRITE = {"install", "add", "remove", "uninstall", "update", "upgrade", "i", "ci", "link", "unlink"}
_INTERP = re.compile(r"(?:python|pypy|node|nodejs|deno|bun|ruby|perl|php)[\d.]*\Z")
_INLINE = {"-c", "-e", "-E", "-r", "-"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}


class Analysis(NamedTuple):
    writes: bool
    paths: List[str]
    unknown: bool
    rule: str


class _State:
    def __init__(self, cwd: Optional[str]) -> None:
        self.dir = cwd
        self.writes = self.unknown = False
        self.paths: List[str] = []
        self.rule = ""

    def hit(self, rule: str, unknown: bool = False) -> None:
        self.writes = True
        self.unknown = self.unknown or unknown
        self.rule = self.rule or rule

    def target(self, word: str, dyn: bool, rule: str) -> None:
        if dyn or not word or _UNSURE & set(word) or (self.dir is None and not word.startswith("/")):
            return self.hit(rule, unknown=True)
        self.hit(rule)
        self.paths.append(posixpath.normpath(posixpath.join(self.dir or "/", word)))

    def cd(self, args: List[str]) -> None:
        ops = [x for x in args if x != "--"]
        if len(ops) != 1 or ops[0].startswith("-") or _UNSURE & set(ops[0]) or os.environ.get("CDPATH"):
            self.dir = None
        elif ops[0].startswith("/"):
            self.dir = posixpath.normpath(ops[0])
        elif self.dir is not None:
            self.dir = posixpath.normpath(posixpath.join(self.dir, ops[0]))


def analyse(cmd: str, cwd: str) -> Analysis:
    try:
        st = _State(posixpath.normpath(cwd) if cwd else None)
        _walk(cmd, st, 0)
        return Analysis(st.writes, st.paths, st.unknown, st.rule)
    except Exception:
        return Analysis(True, [], True, "error")


def _walk(text: str, st: _State, depth: int) -> None:
    if depth > _DEPTH:
        return st.hit("nested", unknown=True)
    for c in lj.simple_commands(text):
        for op, word, dyn in zip(c.rops, c.redirs, c.rdyn):
            if op in _OUT_OPS and word != "/dev/null" and not (op == ">&" and (word.isdigit() or word == "-")):
                st.target(word, dyn, "redirect")
        h, xargs = lj.head_index(c.words)
        if h >= len(c.words):
            continue
        if xargs:
            st.hit("xargs", unknown=True)
            continue
        if c.dyn[h] or _UNSURE & set(c.words[h]):
            st.hit("dynamic_command", unknown=True)
            continue
        _command(c, c.words[h:], st, depth)


def _command(c, words: List[str], st: _State, depth: int) -> None:
    name, args = lj.base(words[0]), words[1:]
    if name == "cd":
        return st.cd(args)
    if name in ("pushd", "popd"):
        st.dir = None
        return None
    if name in _SHELLS:
        inner = lj.shell_string(args)
        if inner is not None:
            return _walk(inner, st, depth + 1)
        if any(not x.startswith("-") for x in args):
            return st.hit("script", unknown=True)
        for body in c.here:
            _walk(body, st, depth + 1)
        return None
    if name == "eval":
        return _walk(" ".join(args), st, depth + 1)
    if words[0].startswith(("./", "../")):
        return st.hit("script", unknown=True)
    if name == "sed":
        return _sed(args, st)
    if name == "perl" and _perl(args, st):
        return None
    if _INTERP.match(name):
        piped_code = c.src is not None and not [x for x in args if not x.startswith("-")]
        if c.here or piped_code or any(x in _INLINE for x in args):
            st.hit("inline_code", unknown=True)
        return None
    if name == "git":
        return _git(args, st)
    if name in _PM:
        if next((x for x in args if not x.startswith("-")), "") in _PM_WRITE:
            st.hit("package", unknown=True)
        return None
    if name == "dd":
        for x in args:
            if x.startswith("of="):
                st.target(x[3:], False, "dd")
        return None
    if name in _UNREAD:
        return st.hit(name, unknown=True)
    ops = _operands(name, args)
    if name in _ALL_OPERANDS:
        targets = ops
    elif name in _FIRST_IS_MODE:
        targets = ops[1:]
    elif name in _DEST:
        tdir = _target_dir(args)
        targets = [tdir] if tdir else (ops if name == "install" and "-d" in args else ops[-1:])
    else:
        return None
    for t in targets:
        st.target(t, False, name)
    return None


def _operands(name: str, args: List[str]) -> List[str]:
    takes, out, i = _VALUE_OPTS.get(name, set()), [], 0
    while i < len(args):
        x = args[i]
        i += 1
        if x == "--":
            return out + args[i:]
        if x.startswith("-") and x != "-":
            if x in takes or x in ("-t", "--target-directory"):
                i += 1
            continue
        out.append(x)
    return out


def _target_dir(args: List[str]) -> Optional[str]:
    for i, x in enumerate(args):
        if x in ("-t", "--target-directory") and i + 1 < len(args):
            return args[i + 1]
        if x.startswith("--target-directory="):
            return x.split("=", 1)[1]
    return None


def _short(x: str) -> bool:
    return x.startswith("-") and not x.startswith("--") and x != "-"


def _sed(args: List[str], st: _State) -> None:
    inplace, scripts, ops, i = False, [], [], 0
    while i < len(args):
        x = args[i]
        i += 1
        if x == "-i":
            inplace = True
            if i < len(args) and (args[i] == "" or args[i].startswith(".")):
                i += 1  # BSD sed: -i '' or -i .bak
        elif x.startswith("-i") or x.startswith("--in-place"):
            inplace = True
        elif x in ("-f", "--file") or x.startswith("--file=") or (_short(x) and "f" in x[1:]):
            return st.hit("sed_script", unknown=True)
        elif x in ("-e", "--expression"):
            scripts.append(args[i] if i < len(args) else "")
            i += 1
        elif x.startswith("--expression="):
            scripts.append(x.split("=", 1)[1])
        elif _short(x) and "i" in x[1:]:
            inplace = True  # a bundle such as -Ei or -ni
        elif x == "--":
            ops += args[i:]
            break
        elif x.startswith("-") and x != "-":
            continue
        else:
            ops.append(x)
    if not scripts and ops:
        scripts.append(ops.pop(0))
    if any(_SED_CMD.search(s) for s in scripts):
        return st.hit("sed_script", unknown=True)
    if inplace:
        for o in ops:
            st.target(o, False, "sed")
    return None


def _perl(args: List[str], st: _State) -> bool:
    """perl -i[.bak] / -pi / -0pi -e SCRIPT FILES: an in-place edit of FILES. False when it does not edit in place."""
    inplace, saw_e, ops, i = False, False, [], 0
    while i < len(args):
        x = args[i]
        i += 1
        if x == "--":
            ops += args[i:]
            break
        if _short(x):
            letters = x[1:]
            if letters[:1] in ("I", "M", "m"):
                continue  # -Idir, -Mmod: value attached
            if "i" in letters.split(".", 1)[0]:
                inplace = True
            if letters.endswith(("e", "E")):
                saw_e, i = True, i + 1  # the script follows
            continue
        ops.append(x)
    if not inplace:
        return False
    if not saw_e and ops:
        ops.pop(0)  # perl -pi script.pl FILES
    for o in ops:
        st.target(o, False, "perl")
    return True


def _git(args: List[str], st: _State) -> None:
    i, other_dir = 0, False
    while i < len(args) and args[i].startswith("-"):
        x = args[i]
        other_dir = other_dir or x in ("-C", "--git-dir", "--work-tree") or x.startswith(("--git-dir=", "--work-tree="))
        i += 2 if x in ("-C", "-c", "--git-dir", "--work-tree") else 1
    if i >= len(args) or args[i] not in _GIT_WRITE:
        return None
    sub, rest = args[i], args[i + 1:]
    if not other_dir and (sub == "restore" or (sub == "checkout" and "--" in rest)):
        paths = rest[rest.index("--") + 1:] if "--" in rest else _operands("git-restore", rest)
        if paths:
            for p in paths:
                st.target(p, False, "git")
            return None
    return st.hit("git", unknown=True)
```

  Then in `claude/jev/prescreen.py` delete the `# Shell commands that write...` block (`_WRITE_WORDS`, `_WRITE_GIT`, `_WRITE_PM`, `_WRITE_PATTERNS`, `_WRITE_RX`) and `def writes(cmd)`. Keep `_SED_CMD`, `_sed`, `_writes` and `risky` (the gate still uses them).
- [ ] **Step 4: Run the tests.** Run the Done commands. Expected: PASS, and the grep prints nothing. If a `test_readable_targets` case fails, fix `shellwrites.py`, not the test: the cases are the spec's readable forms.
- [ ] **Step 5: Commit** `claude/jev/shellwrites.py claude/jev/prescreen.py claude/jev/tests/test_shellwrites.py claude/jev/tests/test_gate_prescreen.py` as `feat(jev): shellwrites reads what a shell command writes (task 2)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 3: Scope lock never asks about shell writes

Goal: During a run, `scope_lock._bash` denies a shell write whose readable target is outside the active tasks' Scope (and outside this session's scratchpad), allows every other write, and never returns "ask"; every scope record gains `kind`, `rule` and `run`.
Scope:
- claude/jev/scope_lock.py
- claude/jev/tests/test_scope_lock.py
- claude/jev/tests/test_scope_lock_bookkeeping.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_scope_lock.py claude/jev/tests/test_scope_lock_bookkeeping.py claude/jev/tests/test_chain.py` passes
- `grep -n '"ask"' claude/jev/scope_lock.py` prints nothing
Failing test first: claude/jev/tests/test_scope_lock.py :: ScopeLockTest.test_bash_never_asks

**Interfaces:**
- Consumes: Task 2's `shellwrites.analyse(cmd, cwd) -> Analysis(writes, paths, unknown, rule)`.
- Produces: scope.jsonl records `{"task": [ids], "tool": "Bash", "decision": "deny"|"allow", "kind": "deny"|"allow", "rule": <Analysis.rule or "orchestrate">, "run": true}` and, for Edit/Write denies, the existing record plus `"kind": "deny", "rule": "file", "run": true`. `scope_lock.SCRATCH_BASE` (default `"/private/tmp/claude-%d" % os.getuid()`, `""` where `os.getuid` is missing), patchable in tests.

- [ ] **Step 1: Write the failing tests.** In `claude/jev/tests/test_scope_lock.py` replace `test_bash_write_like_asks_never_denies`, `test_bash_codex_main_session_still_asks`, `test_bash_unusable_active_json_asks_not_denies` and `test_bash_broken_prescreen_asks_for_every_command` with the tests below (keep `bash()`, `scope_records()` and every other test; add `import shellwrites` only if a test needs it):

```python
    SID = "0155kfr8-aaaa-bbbb-cccc-0123456789ab"

    def test_bash_never_asks(self):
        for cmd in ("rm x", "echo hi > out.txt", "cat a >> b", "sed -i 's/a/b/' f", "git checkout -- f", "git restore f",
                    "mv a b", "cp a b", "tee f", "truncate -s0 f", "dd if=a of=b", "git stash", "npm install left-pad",
                    "python3 - <<'EOF'\nopen('x', 'w')\nEOF", "rm $F", "./gen.sh"):
            out = scope_lock.run(self.bash(cmd, agent_id="a1"))
            self.assertNotEqual(self.decision(out), "ask", cmd)

    def test_bash_executor_in_scope_targets_allowed(self):
        for cmd in ("sed -i 's/a/b/' src/feature/a.ts", "echo hi > src/feature/out.txt", "cp x src/feature/b.ts",
                    "mkdir -p src/feature/new", "cd src && rm feature/old.ts"):
            self.assertIsNone(scope_lock.run(self.bash(cmd, agent_id="a1")), cmd)
        recs = self.scope_records()
        self.assertTrue(recs and all(r["decision"] == "allow" and r["kind"] == "allow" and r["run"] is True for r in recs))

    def test_bash_executor_out_of_scope_target_denied(self):
        for cmd, path in (("echo hi > out.txt", "out.txt"), ("rm src/other.ts", "src/other.ts"),
                          ("sed -i 's/a/b/' README.md", "README.md"), ("cp a /tmp/elsewhere-x", "/tmp/elsewhere-x")):
            out = scope_lock.run(self.bash(cmd, agent_id="a1"))
            self.assertEqual(self.decision(out), "deny", cmd)
            reason = out["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertIn(path, reason)
            self.assertIn("Edit/Write inside your Scope", reason)
        self.assertTrue(all(r["kind"] == "deny" for r in self.scope_records()))

    def test_bash_unknown_writes_allowed_and_logged(self):
        for cmd in ("python3 - <<'EOF'\nopen('x', 'w')\nEOF", "rm $F", "./gen.sh", "git stash"):
            self.assertIsNone(scope_lock.run(self.bash(cmd, agent_id="a1")), cmd)
        self.assertEqual(self.scope_records()[0]["rule"], "inline_code")

    def test_bash_executor_orchestrate_denied(self):
        out = scope_lock.run(self.bash("echo x > .orchestrate/approved.json", agent_id="a1"))
        self.assertEqual(self.decision(out), "deny")
        self.assertEqual(self.scope_records()[-1]["rule"], "orchestrate")

    def test_bash_codex_main_session_checked(self):
        with mock.patch.dict(os.environ, {"DRYAS_HARNESS": "codex"}):
            self.assertEqual(self.decision(scope_lock.run(self.bash("rm src/other.ts"))), "deny")
            self.assertIsNone(scope_lock.run(self.bash("rm src/feature/a.ts")))
            self.assertIsNone(scope_lock.run(self.bash("python3 -c 'x'")))
            self.assertIsNone(scope_lock.run(self.bash("echo x > .orchestrate/approved.json")))

    def test_bash_scratchpad_of_this_session_only(self):
        base = os.path.realpath(tempfile.mkdtemp())
        pad = os.path.join(base, "-enc-dir", self.SID, "scratchpad")
        os.makedirs(pad)
        os.symlink(os.path.join(self.wt, "src", "other.ts"), os.path.join(pad, "link.ts"))
        with mock.patch.object(scope_lock, "SCRATCH_BASE", base):
            ok = lambda p: scope_lock.run(self.bash("echo x > " + p, agent_id="a1", session_id=self.SID))
            self.assertIsNone(ok(os.path.join(pad, "probe.py")))
            for bad in (os.path.join(base, "-enc-dir", "other-session-id", "scratchpad", "x"),
                        os.path.join(base, "-enc-dir", self.SID, "scratchpad2", "x"),
                        os.path.join(pad, "link.ts")):
                self.assertEqual(self.decision(ok(bad)), "deny", bad)
            with mock.patch.dict(os.environ, {"DRYAS_HARNESS": "opencode"}):
                self.assertEqual(self.decision(ok(os.path.join(pad, "probe.py"))), "deny")

    def test_bash_unusable_active_json_denies_readable_targets(self):
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            f.write("{not json")
        self.assertEqual(self.decision(scope_lock.run(self.bash("rm x", agent_id="a1"))), "deny")
        self.assertIsNone(scope_lock.run(self.bash("ls", agent_id="a1")))
```

  In `claude/jev/tests/test_scope_lock_bookkeeping.py`, change any assertion that expects `"ask"` for a Bash command to the new decision (an `.orchestrate` write by an executor → `deny`; anything else → `None` or `deny` per the table in the Goal); read each test before changing it.
- [ ] **Step 2: Run them to see them fail.** Run: `python3 -m pytest -q claude/jev/tests/test_scope_lock.py`. Expected: FAIL, `test_bash_never_asks` sees `'ask' != 'ask'` style failures (`AssertionError: 'ask' == 'ask' : rm x`).
- [ ] **Step 3: Implement.** In `claude/jev/scope_lock.py`:
  1. Module docstring: replace the last sentence ("Bash is never denied: ...") with: "Bash: during a run an executor's shell write is denied when a target it names is outside the scope (scratch files in this session's Claude scratchpad excepted); other writes are allowed and audited at task return (scope_audit.py). Nothing here asks the user."
  2. Add `import re` and, after `TOOLS`, `SCRATCH_BASE = ("/private/tmp/claude-%d" % os.getuid()) if hasattr(os, "getuid") else ""`.
  3. `_log_deny` adds `"kind": "deny", "rule": "file", "run": True` to its record.
  4. Delete `_shell_writes`. Replace `_bash` with:

```python
def _in_scratchpad(real: str, event: Dict[str, Any]) -> bool:
    """True when `real` (a realpath) lies in this session's Claude Code scratchpad:
    <SCRATCH_BASE>/<one dir>/<session_id>/scratchpad/... Off Claude, without a session id or base: False."""
    sid = event.get("session_id")
    if os.environ.get("DRYAS_HARNESS", "claude") != "claude" or not SCRATCH_BASE or not isinstance(sid, str) \
            or not re.fullmatch(r"[0-9A-Za-z_-]{8,64}", sid):
        return False
    base = os.path.realpath(SCRATCH_BASE)
    if not real.startswith(base + os.sep):
        return False
    parts = os.path.relpath(real, base).split(os.sep)
    return len(parts) >= 4 and parts[1] == sid and parts[2] == "scratchpad"


def _log_bash(ids: List[str], decision: str, rule: str) -> None:
    try:
        jevlog.append("scope", {"task": ids, "tool": "Bash", "decision": decision, "kind": decision, "rule": rule,
                                "run": True})
    except Exception:
        pass


def _bash(event: Dict[str, Any], ti: Dict[str, Any], cwd: str) -> Optional[Dict[str, Any]]:
    """During a run, never ask: deny an executor's shell write when a target it names is outside the union Scope
    (and outside this session's scratchpad), or when the command names .orchestrate; allow the rest, which
    scope_audit.py checks at task return. The main session is not checked on Claude and OpenCode (it edits any
    file with Edit/Write anyway); Codex has no worker identity, so there every session is checked."""
    has_agent_id = "agent_id" in event
    if (not has_agent_id and os.environ.get("DRYAS_HARNESS") != "codex") or not task_active(cwd):
        return None
    cmd = str(ti.get("command", ""))
    root = find_root(cwd)
    real_root = os.path.realpath(root) if root else ""
    ids = _active_ids(real_root) if root else []
    if has_agent_id and ".orchestrate" in cmd.lower():
        _log_bash(ids, "deny", "orchestrate")
        return _deny("scope lock: executors never write .orchestrate/ (orchestrator bookkeeping)")
    import shellwrites  # only Bash needs the parser; most events are file edits
    a = shellwrites.analyse(cmd, cwd)
    if not a.writes:
        return None
    for p in a.paths:
        real = os.path.realpath(p)
        if _in_scratchpad(real, event):
            continue
        reason = check(real_root, real, has_agent_id) if root else "scope lock: %s is outside any worktree" % p
        if reason:
            _log_bash(ids, "deny", a.rule)
            return _deny(reason + ". Use Edit/Write inside your Scope, put scratch files in your scratchpad, or "
                                  "report `SCOPE: need <path> because <reason>`")
    _log_bash(ids, "allow", a.rule)
    return None


def _deny(reason: str) -> Dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}
```

  5. In `run`, call `_bash(event, ti, str(cwd))` instead of `_bash(ti, str(cwd), "agent_id" in event)`.
- [ ] **Step 4: Run the tests.** Run the Done commands. Expected: PASS; the grep prints nothing.
- [ ] **Step 5: Commit** the three Scope files as `fix(scope-lock): never ask about executor shell writes; deny readable out-of-scope targets (task 3)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 4: Scope audit at task return

Goal: New `claude/jev/scope_audit.py` checks, without a model, that a task's own commits and the worktree's uncommitted changes stay inside the allowed Scope, and logs each failure as a scope violation.
Scope:
- claude/jev/scope_audit.py
- claude/jev/tests/test_scope_audit.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_scope_audit.py` passes
Failing test first: claude/jev/tests/test_scope_audit.py :: ScopeAuditTest.test_commit_outside_scope_fails

**Interfaces:**
- Consumes: `planfile.sections`, `planfile.scope`, `planfile.in_scope`; `jevlog.append`.
- Produces: CLI `scope_audit.py PLAN.md N [--base SHA] [SHA...]` printing `{"ok": bool, "outside": [repo-relative paths], "commits": [shas checked], "error": str (only on error)}`, exit 0 (exit 2 on bad usage). Function `audit(plan: str, task: str, shas: List[str], base: Optional[str], cwd: str) -> Dict[str, Any]`. On `ok: false` it appends a scope.jsonl record `{"task": [N], "tool": "audit", "decision": "violation", "kind": "violation", "rule": "audit", "paths": [...], "run": true}`.

- [ ] **Step 1: Write the failing test.** Create `claude/jev/tests/test_scope_audit.py`:

```python
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scope_audit

PLAN = ("## Task 1: a\nGoal: g\nScope:\n- src/a/**\nDone:\n- d\n\n"
        "## Task 2: b\nGoal: g\nScope:\n- src/b/**\nDone:\n- d\n")


class ScopeAuditTest(unittest.TestCase):
    def setUp(self):
        self.wt = os.path.realpath(tempfile.mkdtemp())
        self.logs = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = self.logs
        self.git("init", "-q")
        with open(os.path.join(self.wt, ".git", "info", "exclude"), "a") as f:
            f.write(".orchestrate/\n")
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "w") as f:
            f.write(PLAN)
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ["1", "2"]}, f)
        self.base = self.commit("README.md", "chore: base")

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=self.wt, check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(self, rel, text="x\n"):
        p = os.path.join(self.wt, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a") as f:
            f.write(text)

    def commit(self, rel, msg):
        self.write(rel)
        self.git("add", rel)
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def audit(self, task, shas, base=None):
        return scope_audit.audit(os.path.join(self.wt, ".orchestrate", "PLAN.md"), task, shas, base, self.wt)

    def test_in_scope_commit_ok(self):
        sha = self.commit("src/a/x.ts", "feat: x (task 1)")
        self.assertEqual(self.audit("1", [sha]), {"ok": True, "outside": [], "commits": [sha]})

    def test_commit_outside_scope_fails(self):
        sha = self.commit("src/b/x.ts", "feat: x (task 1)")
        r = self.audit("1", [sha])
        self.assertEqual((r["ok"], r["outside"]), (False, ["src/b/x.ts"]))
        with open(os.path.join(self.logs, "scope.jsonl")) as f:
            rec = json.loads(f.readlines()[-1])
        self.assertEqual((rec["kind"], rec["task"], rec["paths"]), ("violation", ["1"], ["src/b/x.ts"]))

    def test_other_task_commit_not_blamed(self):
        own = self.commit("src/a/x.ts", "feat: x (task 1)")
        self.commit("src/b/y.ts", "feat: y (task 2)")
        self.assertTrue(self.audit("1", [own])["ok"])

    def test_foreign_or_unknown_sha_fails(self):
        r = self.audit("1", ["0" * 40])
        self.assertFalse(r["ok"])
        self.assertIn("error", r)

    def test_uncommitted_checked_against_union(self):
        self.write("src/b/wip.ts")       # task 2 is active: its in-scope work is not task 1's fault
        self.assertTrue(self.audit("1", [])["ok"])
        self.write("docs/z.md")          # untracked, outside every active scope
        r = self.audit("1", [])
        self.assertEqual((r["ok"], r["outside"]), (False, ["docs/z.md"]))

    def test_rename_in_status(self):
        self.commit("src/a/old.ts", "feat: old (task 1)")
        self.git("mv", "src/a/old.ts", "src/a/new.ts")
        self.assertTrue(self.audit("1", [])["ok"])

    def test_fallback_finds_task_commits_by_subject(self):
        self.commit("src/b/x.ts", "feat: x (task 1)")
        r = self.audit("1", [], base=self.base)
        self.assertEqual((r["ok"], r["outside"], len(r["commits"])), (False, ["src/b/x.ts"], 1))

    def test_unknown_task(self):
        r = self.audit("9", [])
        self.assertFalse(r["ok"])
        self.assertIn("no Task 9", r["error"])

    def test_cli_prints_json_and_exits_zero(self):
        sha = self.commit("src/a/x.ts", "feat: x (task 1)")
        p = subprocess.run([sys.executable, scope_audit.__file__, ".orchestrate/PLAN.md", "1", sha], cwd=self.wt,
                           capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)["ok"]), (0, True))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q claude/jev/tests/test_scope_audit.py`. Expected: FAIL with `ModuleNotFoundError: No module named 'scope_audit'`.
- [ ] **Step 3: Implement.** Create `claude/jev/scope_audit.py`:

```python
#!/usr/bin/env python3
"""Scope audit at task return (unattended orchestration): did a task change only files its Scope allows?

  scope_audit.py PLAN.md N [--base SHA] [SHA...]
  prints {"ok": bool, "outside": [paths], "commits": [shas], "error": str (only on error)}; exit 0

Run by the orchestrator in the worktree for every executor report, before jev_judge. It checks
- each reported commit on its own (git diff-tree), against task N's Scope, so other executors' commits in the
  shared worktree never count; a sha that is unknown or not an ancestor of HEAD fails the audit;
- with no shas and --base: the commits since BASE whose message contains "(task N)";
- uncommitted and untracked changes against the union Scope of the tasks in .orchestrate/active.json (another
  running executor's in-scope work is not this task's fault);
- .orchestrate/ is never a valid change.
No model call. A failure is logged to scope.jsonl as a violation. A git error is a failed audit, never a crash.
"""
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import planfile


def _git(args: List[str], cwd: str) -> str:
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=True, timeout=20).stdout


def _active(root: str) -> List[str]:
    try:
        with open(os.path.join(root, ".orchestrate", "active.json"), encoding="utf-8") as f:
            ids = json.load(f).get("active", [])
    except (OSError, ValueError, AttributeError):
        return []
    return [str(t) for t in ids if isinstance(t, (str, int))] if isinstance(ids, list) else []


def _bad(rel: str, globs: List[str]) -> bool:
    return rel.split("/", 1)[0].lower() == ".orchestrate" or not planfile.in_scope(rel, globs)


def _status_paths(root: str) -> List[str]:
    out, entries, i = [], _git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], root).split("\0"), 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        out.append(e[3:])
        if e[0] in "RC":
            i += 1  # the original path of a rename or copy follows
    return out


def audit(plan: str, task: str, shas: List[str], base: Optional[str], cwd: str) -> Dict[str, Any]:
    root = _git(["rev-parse", "--show-toplevel"], cwd).strip()
    with open(plan if os.path.isabs(plan) else os.path.join(cwd, plan), encoding="utf-8") as f:
        secs = planfile.sections(f.read())
    if task not in secs:
        return {"ok": False, "outside": [], "commits": [], "error": "no Task %s in %s" % (task, plan)}
    own = planfile.scope(secs[task])
    if not shas and base:
        shas = _git(["log", "--format=%H", "--fixed-strings", "--grep=(task %s)" % task, "%s..HEAD" % base],
                    root).split()
    outside: List[str] = []
    for sha in shas:
        if subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=root,
                          capture_output=True).returncode != 0:
            return {"ok": False, "outside": [], "commits": shas, "error": "commit %s is not on this branch" % sha}
        files = _git(["diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--root", sha], root).split("\0")
        outside += [p for p in files if p and _bad(p, own)]
    union = own + [g for t in _active(root) for g in planfile.scope(secs.get(t, ""))]
    outside += [p for p in _status_paths(root) if _bad(p, union)]
    outside = sorted(set(outside))
    if outside:
        try:
            jevlog.append("scope", {"task": [task], "tool": "audit", "decision": "violation", "kind": "violation",
                                    "rule": "audit", "paths": outside, "run": True})
        except Exception:
            pass
    return {"ok": not outside, "outside": outside, "commits": shas}


def main(argv: List[str]) -> int:
    args = argv[1:]
    base = None
    if "--base" in args:
        k = args.index("--base")
        base = args[k + 1] if k + 1 < len(args) else None
        args = args[:k] + args[k + 2:]
    if len(args) < 2 or (("--base" in argv) and not base):
        sys.stderr.write("usage: scope_audit.py PLAN.md N [--base SHA] [SHA...]\n")
        return 2
    try:
        out = audit(args[0], args[1], args[2:], base, os.getcwd())
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        out = {"ok": False, "outside": [], "commits": [], "error": "%s: %s" % (type(e).__name__, e)}
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run the tests.** Run the Done command. Expected: PASS.
- [ ] **Step 5: Commit** the two Scope files as `feat(jev): scope audit of a task's commits and leftovers (task 4)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 5: Planned and orchestrator-approved risky actions

Goal: `planfile.risky` reads the plan's `## Risky actions` section and new `claude/jev/runrules.py` says whether a risky command is already decided by the plan or the orchestrator, with a fixed list of actions only the user's plan can allow.
Scope:
- claude/jev/planfile.py
- claude/jev/runrules.py
- claude/jev/tests/test_planfile_risky.py
- claude/jev/tests/test_runrules.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_planfile_risky.py claude/jev/tests/test_runrules.py claude/jev/tests/test_planfile.py` passes
Failing test first: claude/jev/tests/test_runrules.py :: RunRulesTest.test_planned_exact_and_prefix

**Interfaces:**
- Consumes: Task 1's `local_judge.simple_commands`, `head_index`, `base`, `destructive`, `danger`; Task 2's `shellwrites.analyse`.
- Produces: `planfile.risky(text: str) -> List[str]`; `runrules.covered(cmd: str, root: str, cwd: str) -> Optional[str]` returning `"planned"`, `"orchestrator"` or `None`; `runrules.human_only(words: List[str], root: str, cwd: str) -> bool`. File format `.orchestrate/approved.json` = `{"commands": [{"cmd": str, "task": str, "reason": str}]}`.

- [ ] **Step 1: Write the failing tests.** Create `claude/jev/tests/test_planfile_risky.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import planfile

PLAN = """# Plan

## Risky actions
- `rm -rf dist` — deletes the build folder; it is rebuilt automatically, nothing of yours is lost.
- `pnpm db:reset*` — wipes the local test database and refills it with sample data.
- `git push` no sentence, skipped
- rm -rf build — no backticks, skipped

## Task 1: a
Goal: g
Scope:
- src/**
"""


class RiskyTest(unittest.TestCase):
    def test_bullets_with_command_and_sentence(self):
        self.assertEqual(planfile.risky(PLAN), ["rm -rf dist", "pnpm db:reset*"])

    def test_no_section(self):
        self.assertEqual(planfile.risky("## Task 1: a\n"), [])

    def test_sections_ignore_risky(self):
        self.assertEqual(list(planfile.sections(PLAN)), ["1"])


if __name__ == "__main__":
    unittest.main()
```

  Create `claude/jev/tests/test_runrules.py`:

```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import runrules

PLAN = ("## Risky actions\n- `rm -rf dist` — deletes the build folder.\n"
        "- `pnpm db:reset*` — wipes the local test database.\n- `git push origin feat/x` — publishes the branch.\n"
        "- `vercel*` — deploys.\n\n## Task 1: a\nGoal: g\nScope:\n- src/**\n")


class RunRulesTest(unittest.TestCase):
    def setUp(self):
        self.wt = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "w") as f:
            f.write(PLAN)

    def approve(self, *cmds):
        with open(os.path.join(self.wt, ".orchestrate", "approved.json"), "w") as f:
            json.dump({"commands": [{"cmd": c, "task": "1", "reason": "r"} for c in cmds]}, f)

    def cov(self, cmd):
        return runrules.covered(cmd, self.wt, self.wt)

    def test_planned_exact_and_prefix(self):
        self.assertEqual(self.cov("rm -rf dist"), "planned")
        self.assertEqual(self.cov("pnpm db:reset --force"), "planned")
        self.assertIsNone(self.cov("pnpm db:resetall"))
        self.assertIsNone(self.cov("rm -rf distro"))

    def test_compound_needs_every_risky_part_covered(self):
        self.assertEqual(self.cov("pnpm build && rm -rf dist"), "planned")
        self.assertIsNone(self.cov("pnpm db:reset && git reset --hard"))

    def test_nothing_matched_is_not_covered(self):
        self.assertIsNone(self.cov("make build"))

    def test_orchestrator_exact_only(self):
        self.approve("git reset --hard HEAD~1")
        self.assertEqual(self.cov("git reset --hard HEAD~1"), "orchestrator")
        self.assertIsNone(self.cov("git reset --hard HEAD~2"))

    def test_human_only_never_from_orchestrator_or_prefix(self):
        self.approve("git push origin main", "rm -rf /tmp/elsewhere-dir", "terraform apply")
        self.assertIsNone(self.cov("git push origin main"))
        self.assertIsNone(self.cov("rm -rf /tmp/elsewhere-dir"))
        self.assertIsNone(self.cov("terraform apply"))
        self.assertIsNone(self.cov("vercel deploy --prod"))         # plan prefix cannot cover a human-only action
        self.assertEqual(self.cov("git push origin feat/x"), "planned")  # an exact plan entry can

    def test_unreadable_files_cover_nothing(self):
        with open(os.path.join(self.wt, ".orchestrate", "approved.json"), "w") as f:
            f.write("{broken")
        self.assertIsNone(self.cov("git reset --hard HEAD~1"))
        os.remove(os.path.join(self.wt, ".orchestrate", "PLAN.md"))
        self.assertIsNone(self.cov("rm -rf dist"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to see them fail.** Run: `python3 -m pytest -q claude/jev/tests/test_planfile_risky.py claude/jev/tests/test_runrules.py`. Expected: FAIL with `AttributeError: module 'planfile' has no attribute 'risky'` and `ModuleNotFoundError: No module named 'runrules'`.
- [ ] **Step 3: Implement.** In `claude/jev/planfile.py`, after `scope`, add (and extend the module docstring with "and its `## Risky actions` section"):

```python
_RISKY = re.compile(r"^## Risky actions[ \t]*\n(.*?)(?=^## |\Z)", re.M | re.S)
_RISKY_ITEM = re.compile(r"- `([^`\n]+)` +— +\S")


def risky(text: str) -> List[str]:
    """Commands of the plan's `## Risky actions` section, one bullet each: - `<command or prefix*>` — <plain
    sentence>. A bullet without the backticked command or the sentence is skipped (nothing pre-approved)."""
    m = _RISKY.search(text)
    if not m:
        return []
    return [im.group(1).strip() for line in m.group(1).splitlines() for im in [_RISKY_ITEM.match(line.strip())] if im]
```

  Create `claude/jev/runrules.py`:

```python
#!/usr/bin/env python3
"""Run rules for the Jev gate during an unattended run: is a risky command already decided?

covered(cmd, root, cwd) -> "planned" | "orchestrator" | None
  The command is covered when at least one of its simple commands matches an entry and every simple command the
  local judge calls risky (destructive or dangerous) is matched:
  - planned: an entry of `## Risky actions` in <root>/.orchestrate/PLAN.md (the user approved it with the plan),
    exact, or a prefix ending in `*` matched word by word ("pnpm db:reset*" matches "pnpm db:reset --force",
    not "pnpm db:resetall");
  - orchestrator: an exact "cmd" of <root>/.orchestrate/approved.json, {"commands": [{"cmd", "task", "reason"}]},
    which only the orchestrator (main thread) writes.
  Human-only actions (human_only) are matched only by an exact plan entry: never by a plan prefix or approved.json.
Never raises: unreadable files cover nothing.
"""
import json
import os
import shlex
import sys
from typing import Any, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_judge as lj
import planfile
import shellwrites

HUMAN_ONLY_HEADS = {"vercel", "netlify", "fly", "flyctl", "heroku", "firebase", "wrangler", "terraform", "pulumi",
                    "gcloud", "az", "aws", "kubectl", "helm", "eas", "fastlane", "supabase"}
HUMAN_ONLY_SUBS = {"git": {"push"}, "gh": {"release", "repo", "secret", "workflow", "pr"}}


def _read(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _words(entry: str) -> List[str]:
    try:
        return shlex.split(entry)
    except ValueError:
        return []


def human_only(words: List[str], root: str, cwd: str) -> bool:
    """Push, deploy and cloud commands, and deletes or writes whose readable target is outside the worktree."""
    h, _ = lj.head_index(words)
    if h >= len(words):
        return False
    name, rest = lj.base(words[h]), [w for w in words[h + 1:] if not w.startswith("-")]
    if name in HUMAN_ONLY_HEADS or (rest and rest[0] in HUMAN_ONLY_SUBS.get(name, ())):
        return True
    a = shellwrites.analyse(" ".join(shlex.quote(w) for w in words), cwd)
    real_root = os.path.realpath(root)
    return any(not (os.path.realpath(p) + os.sep).startswith(real_root + os.sep) for p in a.paths)


def covered(cmd: str, root: str, cwd: str) -> Optional[str]:
    try:
        entries = planfile.risky(_read(os.path.join(root, ".orchestrate", "PLAN.md")))
        try:
            approved = [str(c.get("cmd", "")) for c in json.loads(_read(os.path.join(root, ".orchestrate",
                                                                                      "approved.json")) or "{}")
                        .get("commands", []) if isinstance(c, dict)]
        except (ValueError, AttributeError):
            approved = []
        exact = [_words(e) for e in entries if not e.endswith("*")]
        prefix = [_words(e[:-1]) for e in entries if e.endswith("*")]
        mine = [_words(c) for c in approved]
        rule, matched = None, False
        for c in lj.simple_commands(cmd):
            w = c.words
            if not w:
                continue
            ho = human_only(w, root, cwd)
            if w in exact:
                hit = "planned"
            elif not ho and any(p and w[:len(p)] == p for p in prefix):
                hit = "planned"
            elif not ho and w in mine:
                hit = "orchestrator"
            else:
                hit = None
            text = " ".join(shlex.quote(x) for x in w)
            if hit:
                matched, rule = True, rule or hit
            elif ho or lj.destructive(text) or lj.danger(text):
                return None
        return rule if matched else None
    except Exception:
        return None
```

- [ ] **Step 4: Run the tests.** Run the Done command. Expected: PASS.
- [ ] **Step 5: Commit** the four Scope files as `feat(jev): planned and orchestrator-approved risky actions (task 5)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 6: The Jev gate never asks during a run

Goal: While a run is active, `gate.run` turns every "ask" (from the Jev model or the local judge) into either an allow, when `runrules.covered` says the plan or the orchestrator already decided it, or a deny the executor can act on; gate records gain `run` and `rule`.
Scope:
- claude/jev/gate.py
- claude/jev/tests/test_gate_run.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_gate_run.py claude/jev/tests/test_gate.py claude/jev/tests/test_gate_decision.py claude/jev/tests/test_gate_outcome.py claude/jev/tests/test_gate_task_review.py` passes
Failing test first: claude/jev/tests/test_gate_run.py :: GateRunTest.test_ask_becomes_deny_during_run

**Interfaces:**
- Consumes: Task 5's `runrules.covered(cmd, root, cwd)`; `taskctx.load(cwd) -> (root, parsed active.json)`.
- Produces: gate.jsonl records gain `"run": bool` on every record and `"rule": "planned"|"orchestrator"|"run_deny"` where the run rule applied. Deny reason text ends with `RUN_DENY` (below).

- [ ] **Step 1: Write the failing test.** Create `claude/jev/tests/test_gate_run.py` (same set-up pattern as `test_gate_decision.py`):

```python
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate

NOKEY = {"OPENROUTER_API_KEY": "", "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}
STRICT = {"prescreen": False, "min_confidence": 0.99, "deny_safe_below": 0.9, "ask_risk": "worth_a_look"}
PLAN = "## Risky actions\n- `git reset --hard` — throws away uncommitted edits in this worktree.\n\n## Task 1: a\nGoal: g\nScope:\n- src/**\n"


class GateRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        env = dict(NOKEY, JEV_LOG_DIR=os.path.join(self.tmp, "logs"), JEV_SSD_ROOT=self.tmp,
                   JEV_THRESHOLDS=os.path.join(self.tmp, "t.json"))
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump({"gate": STRICT}, f)
        self.wt = os.path.realpath(os.path.join(self.tmp, "wt"))
        os.makedirs(os.path.join(self.wt, ".git"))
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "w") as f:
            f.write(PLAN)

    def active(self, ids):
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ids}, f)

    def run_bash(self, cmd):
        out = gate.run({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": self.wt, "agent_id": "a1",
                        "tool_use_id": "toolu_1"})
        return (out["hookSpecificOutput"]["permissionDecision"], out["hookSpecificOutput"]["permissionDecisionReason"]) if out else (None, "")

    def last(self):
        with open(os.path.join(self.tmp, "logs", "gate.jsonl")) as f:
            return json.loads(f.readlines()[-1])

    def test_ask_outside_run_unchanged(self):
        self.assertEqual(self.run_bash("rm -rf build")[0], "ask")
        self.assertIs(self.last()["run"], False)

    def test_ask_becomes_deny_during_run(self):
        self.active(["1"])
        d, reason = self.run_bash("rm -rf build")
        self.assertEqual(d, "deny")
        self.assertIn("NEEDS DECISION", reason)
        self.assertNotIn("please confirm", reason)
        self.assertEqual((self.last()["run"], self.last()["rule"]), (True, "run_deny"))

    def test_planned_action_allowed_during_run(self):
        self.active(["1"])
        self.assertEqual(self.run_bash("git reset --hard")[0], None)
        self.assertEqual(self.last()["rule"], "planned")

    def test_orchestrator_approved_allowed(self):
        self.active(["1"])
        with open(os.path.join(self.wt, ".orchestrate", "approved.json"), "w") as f:
            json.dump({"commands": [{"cmd": "rm -rf build", "task": "1", "reason": "generated"}]}, f)
        self.assertEqual(self.run_bash("rm -rf build")[0], None)
        self.assertEqual(self.last()["rule"], "orchestrator")

    def test_deny_stays_deny(self):
        self.active(["1"])
        self.assertEqual(self.run_bash("rm -rf /")[0], "deny")

    def test_malformed_active_json_counts_as_run(self):
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            f.write("{nope")
        self.assertEqual(self.run_bash("rm -rf build")[0], "deny")

    def test_no_ask_noted_during_run(self):
        self.active(["1"])
        with mock.patch.object(gate.gate_outcome, "note_ask") as note:
            self.run_bash("rm -rf build")
        note.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q claude/jev/tests/test_gate_run.py`. Expected: FAIL (`KeyError: 'run'` and `'ask' != 'deny'`).
- [ ] **Step 3: Implement.** In `claude/jev/gate.py`:
  1. Add `import runrules` to the module imports.
  2. After `decide`/`_local_decision`, add:

```python
RUN_DENY = (". Denied during an unattended run, nobody is asked: find a safer way, or end your report with "
            "`NEEDS DECISION: <exact command> because <reason>` for the orchestrator")


def _run_active(loaded: Tuple[Optional[str], Any]) -> bool:
    """A run is active when active.json exists with a non-empty active list; unreadable counts as active."""
    root, data = loaded
    if root is None:
        return False
    return not isinstance(data, dict) or bool(data.get("active"))


def _unattended(d: Tuple[str, str], tool: str, cmd: str, root: str, cwd: str) -> Tuple[Optional[Tuple[str, str]], str]:
    """During a run nobody is asked: an ask the plan or the orchestrator already decided is allowed
    (runrules.covered), any other becomes a deny the executor can report as NEEDS DECISION."""
    rule = runrules.covered(cmd, root, cwd) if tool == "Bash" else None
    if rule:
        return None, rule
    return ("deny", d[1].replace(" - please confirm", "") + RUN_DENY), "run_deny"
```

  3. In `run`, right after `loaded = taskctx.load(cwd)`, add `active = _run_active(loaded)` and include `run=active` in `base` (`base = dict({"tool": tool, "run": active}, ...)`), so every record, skipped ones included, carries it.
  4. In the `try:` block, after `d = _local_decision(local) if ... else decide(a, t)`, add:

```python
        run_rule = ""
        if d and d[0] == "ask" and active:
            d, run_rule = _unattended(d, tool, cmd, str(loaded[0]), cwd)
```

     and log with the rule: `jevlog.append("gate", _record(dict(base, rule=run_rule) if run_rule else base, d, a, v, t, local, local_ms))` (keep the fallback `except` branch as it is). The existing `if d[0] == "ask" and tool == "Bash" ...: gate_outcome.note_ask(...)` now runs only outside a run, with no change.
- [ ] **Step 4: Run the tests.** Run the Done command. Expected: PASS. If an older gate test asserted the exact `base` keys, add `"run": False` to its expectation rather than removing the field.
- [ ] **Step 5: Commit** the two Scope files as `fix(gate): no prompts during a run; planned and orchestrator-approved actions pass (task 6)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 7: Preflight — refuse to start a run that could prompt

Goal: The chain logs Claude Code's `permission_mode` with every tool call, and new `claude/jev/preflight.py` tells the orchestrator, in plain words, whether this session can run unattended.
Scope:
- claude/jev/chain.py
- claude/jev/preflight.py
- claude/jev/tests/test_preflight.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_preflight.py claude/jev/tests/test_chain.py claude/jev/tests/test_chain_local.py claude/jev/tests/test_chain_observe.py` passes
Failing test first: claude/jev/tests/test_preflight.py :: PreflightTest.test_default_mode_not_ok

**Interfaces:**
- Consumes: `jevlog.log_dir()`, `jevlog.read`-style JSONL lines in `calls.jsonl` with `ts`, `cwd`, `tool`, and the new `permission_mode`.
- Produces: calls.jsonl records `{"tool": ..., "permission_mode": <str, only when the hook input had one>}`; CLI `preflight.py` printing `{"ok": bool, "mode": str, "now": "<ISO time>", "say": "<plain text>"}`, exit 0; function `check(cwd: str, now: Optional[float] = None) -> Dict[str, Any]`.

- [ ] **Step 1: Write the failing test.** Create `claude/jev/tests/test_preflight.py`:

```python
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preflight


def ts(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t))


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.logs = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = self.logs
        self.cwd = os.path.realpath(tempfile.mkdtemp())
        self.now = time.time()

    def calls(self, *recs):
        with open(os.path.join(self.logs, "calls.jsonl"), "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

    def rec(self, mode, age=5, cwd=None):
        r = {"tool": "Bash", "ts": ts(self.now - age), "cwd": cwd or self.cwd}
        if mode:
            r["permission_mode"] = mode
        return r

    def test_auto_ok(self):
        self.calls(self.rec("auto"))
        r = preflight.check(self.cwd, self.now)
        self.assertEqual((r["ok"], r["mode"]), (True, "auto"))

    def test_bypass_ok(self):
        self.calls(self.rec("bypassPermissions"))
        self.assertTrue(preflight.check(self.cwd, self.now)["ok"])

    def test_default_mode_not_ok(self):
        self.calls(self.rec("default"))
        r = preflight.check(self.cwd, self.now)
        self.assertFalse(r["ok"])
        self.assertIn("Shift+Tab", r["say"])
        self.assertIn("auto mode", r["say"])

    def test_accept_edits_not_ok(self):
        self.calls(self.rec("acceptEdits"))
        self.assertFalse(preflight.check(self.cwd, self.now)["ok"])

    def test_newest_matching_record_wins(self):
        self.calls(self.rec("default", age=50), self.rec("auto", age=3), self.rec("default", age=1, cwd="/elsewhere"))
        self.assertEqual(preflight.check(self.cwd, self.now)["mode"], "auto")

    def test_no_mode_is_unknown_and_starts_with_warning(self):
        self.calls(self.rec(None))
        r = preflight.check(self.cwd, self.now)
        self.assertEqual((r["ok"], r["mode"]), (True, "unknown"))
        self.assertTrue(r["say"])

    def test_stale_or_missing_log_is_unknown(self):
        self.calls(self.rec("default", age=600))
        self.assertEqual(preflight.check(self.cwd, self.now)["mode"], "unknown")
        os.remove(os.path.join(self.logs, "calls.jsonl"))
        self.assertEqual(preflight.check(self.cwd, self.now)["mode"], "unknown")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q claude/jev/tests/test_preflight.py`. Expected: FAIL with `ModuleNotFoundError: No module named 'preflight'`.
- [ ] **Step 3: Implement.**
  1. In `claude/jev/chain.py` `main`, replace `jevlog.append("calls", {"tool": str(event.get("tool_name", ""))})` with:

```python
        rec = {"tool": str(event.get("tool_name", ""))}
        mode = event.get("permission_mode")  # Claude Code: default, acceptEdits, plan, auto, bypassPermissions
        if isinstance(mode, str) and mode:
            rec["permission_mode"] = mode[:32]
        jevlog.append("calls", rec)
```

  2. Create `claude/jev/preflight.py`:

```python
#!/usr/bin/env python3
"""Preflight for an unattended run (/orchestrate §1b): can this session run the plan without asking the user?

  preflight.py   prints {"ok": bool, "mode": str, "now": ISO time, "say": plain-language text}; exit 0

Reads the newest calls.jsonl record for this working directory from the last 120 s (the chain logs one per tool
call, with Claude Code's permission_mode, just before this script runs). ok when the mode is auto or
bypassPermissions: in any other mode executor shell commands can prompt, and they cannot be known in advance.
No record with a mode (Codex, OpenCode, or no log): mode "unknown", ok, and "say" is a one-line warning.
"""
import json
import os
import sys
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog

WINDOW_S = 120
OK_MODES = {"auto", "bypassPermissions"}
SAY_NOT_OK = ("This session can stop to ask you for permission while it works, so it would not finish on its own. "
              "Press Shift+Tab until the bottom line says auto mode (or restart Claude in auto mode), then run "
              "/orchestrate again.")
SAY_UNKNOWN = ("I could not check whether this session can ask you for permission while it works; if it does, "
               "the run will wait for you.")


def _epoch(ts: str) -> Optional[float]:
    try:
        return time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return None


def check(cwd: str, now: Optional[float] = None) -> Dict[str, Any]:
    now = time.time() if now is None else now
    here = os.path.realpath(cwd)
    mode = "unknown"
    try:
        with open(os.path.join(jevlog.log_dir(), "calls.jsonl"), encoding="utf-8") as f:
            lines = f.readlines()[-500:]
    except OSError:
        lines = []
    for line in reversed(lines):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        t = _epoch(str(r.get("ts", ""))) if isinstance(r, dict) else None
        if t is None or now - t > WINDOW_S or os.path.realpath(str(r.get("cwd", ""))) != here:
            continue
        mode = str(r.get("permission_mode") or "unknown")
        break
    ok = mode in OK_MODES or mode == "unknown"
    say = "" if mode in OK_MODES else (SAY_UNKNOWN if mode == "unknown" else SAY_NOT_OK)
    return {"ok": ok, "mode": mode, "now": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)), "say": say}


if __name__ == "__main__":
    sys.stdout.write(json.dumps(check(os.getcwd())) + "\n")
    sys.exit(0)
```

- [ ] **Step 4: Run the tests.** Run the Done command. Expected: PASS.
- [ ] **Step 5: Commit** the three Scope files as `feat(jev): preflight refuses a run that could prompt; log permission mode (task 7)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 8: Counting prompts — /tune split and the run report

Goal: `/tune` counts scope asks, denies and violations separately and reports prompts during runs (target 0), and new `claude/jev/run_report.py` gives the numbers for one run's end report.
Scope:
- claude/jev/tune.py
- claude/jev/run_report.py
- claude/jev/tests/test_tune_scope_split.py
- claude/jev/tests/test_run_report.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_tune_scope_split.py claude/jev/tests/test_run_report.py claude/jev/tests/test_tune.py claude/jev/tests/test_tune_tasks.py` passes
Failing test first: claude/jev/tests/test_tune_scope_split.py :: ScopeSplitTest.test_split_counts

**Interfaces:**
- Consumes: scope.jsonl records of Tasks 3 and 4 (`decision` deny|allow|ask|violation, `kind`, `rule`, `run`) and gate.jsonl records of Task 6 (`decision`, `run`, `rule`); `tune.read(name, log_dir)`.
- Produces: `tune.delivery(...)` keys `scope_denials` (records with decision `deny` only), `scope_asks`, `scope_violations`, `run_prompts` (scope and gate records with `run: true` and decision `ask`); `delivery` gains a `gate: List[Any]` keyword argument with default `()`. CLI `run_report.py <worktree root> <start ISO time>` printing `{"prompts", "scope_denies", "violations", "run_denies", "planned", "orchestrator", "inline_code"}`; function `report(root: str, since: str, log_dir: Optional[str] = None) -> Dict[str, int]`.

- [ ] **Step 1: Write the failing tests.** Create `claude/jev/tests/test_tune_scope_split.py`:

```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tune


def write(d, name, recs):
    with open(os.path.join(d, name + ".jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


class ScopeSplitTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = self.d
        os.environ["JEV_THRESHOLDS"] = os.path.join(self.d, "thresholds.json")

    def test_split_counts(self):
        write(self.d, "scope", [{"task": ["1"], "path": "a", "decision": "deny"}] * 2
              + [{"task": ["1"], "tool": "Bash", "decision": "ask"}] * 3
              + [{"task": ["1"], "tool": "Bash", "decision": "allow", "kind": "allow", "rule": "inline_code", "run": True}] * 4
              + [{"task": ["1"], "tool": "audit", "decision": "violation", "kind": "violation", "run": True}])
        write(self.d, "gate", [{"tool": "Bash", "decision": "ask", "run": True}, {"tool": "Bash", "decision": "ask", "run": False}])
        d = tune.build()["delivery"]
        self.assertEqual((d["scope_denials"], d["scope_asks"], d["scope_violations"], d["run_prompts"]), (2, 3, 1, 1))

    def test_render_names_run_prompts(self):
        write(self.d, "gate", [{"tool": "Bash", "decision": "ask", "run": True}])
        self.assertIn("Prompts during runs (target 0): 1", tune.render(tune.build(), []))


if __name__ == "__main__":
    unittest.main()
```

  Create `claude/jev/tests/test_run_report.py`:

```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import run_report


class RunReportTest(unittest.TestCase):
    def test_counts_this_worktree_since_start(self):
        d = tempfile.mkdtemp()
        wt = "/w/wt"
        def rec(**k):
            return dict({"ts": "2026-10-16T10:00:00+0700", "cwd": wt, "run": True}, **k)
        with open(os.path.join(d, "scope.jsonl"), "w") as f:
            for r in [rec(decision="deny", kind="deny", rule="sed"), rec(decision="allow", kind="allow", rule="inline_code"),
                      rec(decision="allow", kind="allow", rule="inline_code"), rec(decision="violation", kind="violation"),
                      rec(decision="ask"), rec(decision="deny", cwd="/other"), rec(decision="deny", ts="2026-10-16T08:00:00+0700")]:
                f.write(json.dumps(r) + "\n")
        with open(os.path.join(d, "gate.jsonl"), "w") as f:
            for r in [rec(decision="deny", rule="run_deny"), rec(decision="none", rule="planned"),
                      rec(decision="none", rule="orchestrator"), rec(decision="ask")]:
                f.write(json.dumps(r) + "\n")
        r = run_report.report(wt, "2026-10-16T09:00:00+0700", d)
        self.assertEqual(r, {"prompts": 2, "scope_denies": 1, "violations": 1, "run_denies": 1, "planned": 1,
                             "orchestrator": 1, "inline_code": 2})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to see them fail.** Run: `python3 -m pytest -q claude/jev/tests/test_tune_scope_split.py claude/jev/tests/test_run_report.py`. Expected: FAIL (`KeyError: 'scope_asks'`, `ModuleNotFoundError: No module named 'run_report'`).
- [ ] **Step 3: Implement.**
  1. `claude/jev/tune.py` `delivery`: add the keyword argument `gate: Any = ()`; replace `denials = sum(1 for r in scope if isinstance(r, dict))` with:

```python
    scope = [r for r in scope if isinstance(r, dict)]
    denials = sum(1 for r in scope if r.get("decision") == "deny")
    asks = sum(1 for r in scope if r.get("decision") == "ask")
    violations = sum(1 for r in scope if r.get("kind") == "violation")
    run_prompts = sum(1 for r in list(scope) + [g for g in gate if isinstance(g, dict)]
                      if r.get("run") is True and r.get("decision") == "ask")
```

     and add `"scope_asks": asks, "scope_violations": violations, "run_prompts": run_prompts,` to the returned dict next to `"scope_denials"`. In `build`, pass the gate records it already reads: `delivery(dispatch, scope, esc, review, merge, gate=<the gate list build already loads>)` (read `build` first and use its existing variable). In `render`, after the scope-lock line, add `"- Prompts during runs (target 0): %d (scope asks %d, violations %d)" % (d["run_prompts"], d["scope_asks"], d["scope_violations"]),`.
  2. Create `claude/jev/run_report.py`:

```python
#!/usr/bin/env python3
"""Numbers for one unattended run's end report (/orchestrate §8).

  run_report.py <worktree root> <start ISO time>   prints the counts as JSON; exit 0

Counts scope.jsonl and gate.jsonl records written by sessions working in <worktree root> (their cwd is the root
or below it) at or after <start>: prompts (any "ask" while a run was active; target 0), scope denies, scope
violations (audit), gate run denies, risky actions allowed by the plan or by the orchestrator, and inline-code
shell writes (the executor habit the lessons watch).
"""
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tune


def _epoch(ts: Any) -> float:
    try:
        return time.mktime(time.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return 0.0


def report(root: str, since: str, log_dir: Optional[str] = None) -> Dict[str, int]:
    start, base = _epoch(since), os.path.normpath(root)

    def mine(name: str) -> List[Dict[str, Any]]:
        out = []
        for r in tune.read(name, log_dir):
            cwd = os.path.normpath(str(r.get("cwd", "")))
            if (cwd == base or cwd.startswith(base + os.sep)) and _epoch(r.get("ts")) >= start:
                out.append(r)
        return out

    scope, gate = mine("scope"), mine("gate")
    return {
        "prompts": sum(1 for r in scope + gate if r.get("run") is True and r.get("decision") == "ask"),
        "scope_denies": sum(1 for r in scope if r.get("decision") == "deny"),
        "violations": sum(1 for r in scope if r.get("kind") == "violation"),
        "run_denies": sum(1 for r in gate if r.get("rule") == "run_deny"),
        "planned": sum(1 for r in gate if r.get("rule") == "planned"),
        "orchestrator": sum(1 for r in gate if r.get("rule") == "orchestrator"),
        "inline_code": sum(1 for r in scope if r.get("rule") == "inline_code"),
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.stderr.write("usage: run_report.py <worktree root> <start ISO time>\n")
        sys.exit(2)
    sys.stdout.write(json.dumps(report(sys.argv[1], sys.argv[2])) + "\n")
    sys.exit(0)
```

- [ ] **Step 4: Run the tests.** Run the Done command. Expected: PASS. If `test_tune.py` or `test_tune_tasks.py` breaks on `scope_denials`, check which records it writes: records with `decision: "deny"` must still count; do not change those tests' numbers.
- [ ] **Step 5: Commit** the four Scope files as `feat(tune): count prompts during runs; run report numbers (task 8)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 9: Claude orchestrate, executor and plan instructions

Goal: The Claude edition's `/orchestrate` skill and command, the executor agent, the plan skill, `/wplan` and the interrogate skill describe and permit the unattended run: preflight, Risky actions, base shas, scope audit, NEEDS DECISION / NEEDS USER, one plain-language report, lessons and a notification.
Scope:
- claude/skills/orchestrate/SKILL.md
- claude/commands/orchestrate.md
- claude/agents/executor.md
- claude/skills/plan/SKILL.md
- claude/commands/wplan.md
- claude/skills/interrogate/SKILL.md
- install/tests/test_unattended_docs.py
Done:
- `python3 -m pytest -q install/tests/test_unattended_docs.py install/tests/test_pstack_docs.py install/tests/test_process_skills.py install/tests/test_framework_docs.py install/tests/test_ladder_docs.py install/tests/test_owned_core_docs.py` passes
Failing test first: install/tests/test_unattended_docs.py :: UnattendedDocsTest.test_orchestrate_runs_unattended

**Interfaces:**
- Consumes: CLIs from Tasks 4, 7, 8 (`scope_audit.py PLAN.md N --base SHA [SHA...]`, `preflight.py`, `run_report.py <root> <start>`), Task 5's `## Risky actions` format and `.orchestrate/approved.json` format, Task 6's `NEEDS DECISION` wording.
- Produces: the executor report lines `COMMITS: <sha> [<sha>...]` / `COMMITS: none` and `NEEDS DECISION: <exact command> because <reason>`; the orchestrator's `NEEDS USER` items; `active.json` field `"base": {"<N>": "<sha>"}`.

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_unattended_docs.py`:

```python
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class UnattendedDocsTest(unittest.TestCase):
    def test_orchestrate_runs_unattended(self):
        s = read("claude/skills/orchestrate/SKILL.md")
        for needle in ("jev/preflight.py", "## Risky actions", "jev/scope_audit.py", "--base", "NEEDS DECISION",
                       ".orchestrate/approved.json", "NEEDS USER", "jev/run_report.py", "PushNotification",
                       '"base"', "nobody is asked"):
            self.assertIn(needle, s, needle)

    def test_orchestrate_tools_allow_the_new_scripts(self):
        for rel in ("claude/skills/orchestrate/SKILL.md", "claude/commands/orchestrate.md"):
            head = read(rel).split("\n---", 1)[0]
            for needle in ("jev/scope_audit.py", "jev/preflight.py", "jev/run_report.py", "git rev-parse",
                           "PushNotification"):
                self.assertIn(needle, head, "%s: %s" % (rel, needle))

    def test_executor_reports_commits_and_decisions(self):
        s = read("claude/agents/executor.md")
        for needle in ("COMMITS:", "(task N)", "NEEDS DECISION:", "checked when you report back"):
            self.assertIn(needle, s, needle)
        self.assertNotIn("a shell write makes the user confirm it", s)

    def test_plan_proposes_risky_actions_in_plain_words(self):
        for rel in ("claude/skills/plan/SKILL.md", "claude/commands/wplan.md"):
            s = read(rel)
            self.assertIn("## Risky actions", s, rel)
            self.assertIn("plain", s, rel)

    def test_interrogate_never_asks_during_a_run(self):
        self.assertIn("during /orchestrate", read("claude/skills/interrogate/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_unattended_docs.py`. Expected: FAIL (`AssertionError: 'jev/preflight.py' not found`).
- [ ] **Step 3: Implement.** Make these edits; keep every other line as it is.
  1. `claude/skills/orchestrate/SKILL.md` frontmatter `allowed-tools` and `claude/commands/orchestrate.md` `allowed-tools`: append `Bash(git rev-parse:*)`, `Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/scope_audit.py":*)`, `Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/preflight.py":*)`, `Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/run_report.py":*)`, `PushNotification`.
  2. SKILL, after the `## 0.` section's second paragraph, add: "**The user decides in brainstorm and plan; from step 1b on, nobody is asked.** Hooks never prompt during a run: they allow, or deny with a reason the executor can act on. You decide what an executor reports as `NEEDS DECISION`; only what you must not decide alone becomes a `NEEDS USER` item in the end report."
  3. SKILL, new section after `## 1.`:
     ```
     ## 1b. Preflight: the run must not need the user
     Run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/preflight.py"` once, before the first `active.json`. It prints `{"ok", "mode", "now", "say"}`. Not ok: do not start; tell the user `say` word for word (it is written for someone who does not code) and stop. Ok: keep `now` as the run start for §8; if `say` is not empty, pass it on in one line; then tell the user in one plain line that the run has started and they can leave.
     ```
  4. SKILL §2.2: after the PLAN.md block add: "If the plan has a `## Risky actions` section, copy it verbatim to the top of `.orchestrate/PLAN.md`, above the first task. The gate reads it there: during the run those commands are allowed without asking anyone (an exact entry, or a prefix ending in `*`)."
  5. SKILL §5.2: the file becomes `{"active": [<ids>], "base": {"<N>": "<sha>"}}`, where the sha is `git rev-parse HEAD` taken just before that task's first dispatch (kept for re-dispatches; §5.6 `git diff --numstat <base>..HEAD` and §6 read it from here).
  6. SKILL §5.3: replace "The dispatch prompt allows the executor to commit its own task: explicit paths, conventional message;" with "The dispatch prompt allows the executor to commit its own task: explicit paths, a conventional message whose subject ends with `(task <N>)`, and the report ends with `COMMITS: <sha>...` or `COMMITS: none`;".
  7. SKILL §6, first paragraph becomes: "For each report, first run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/scope_audit.py" .orchestrate/PLAN.md <N> --base <base of N> <COMMITS shas>` in the worktree. `ok: false` means the task is not done: re-dispatch it on the same model with "revert these files: <outside> (`git checkout -- <path>` if tracked, delete if new), then make the change with Edit/Write inside your Scope". That re-run is not a climb; a second audit failure on the task counts as a failure (§7). Then one `jev_judge` call with state `{task_section, executor_report}`:" (the two question bullets stay).
  8. SKILL §6, add a paragraph after the `SCOPE: need` sentence:
     ```
     `NEEDS DECISION: <command> because <reason>` means the gate denied a risky command during the run, and nobody is asked: you decide. Approve only when the command is needed for the task, stays inside the worktree, and can be undone or only touches generated or test data. To approve, add `{"cmd": "<exact command>", "task": "<N>", "reason": "<one line>"}` to `.orchestrate/approved.json` (`{"commands": [...]}`; create it if missing), call `mcp__plugin_dryas_jev__log_override` (question "run_ask", Jev "ask", yours "allow", the reason), and re-dispatch. Otherwise re-dispatch with a safer way, or make it a `NEEDS USER` item: the task stays not done, its id leaves `active.json`, and the run carries on with the other tasks. Your own risky commands follow the same rule. The gate never lets approved.json cover a push, a deploy or cloud command, or a delete outside the worktree: only an exact entry in the plan's Risky actions can.
     ```
  9. SKILL `## 8. Finish`: insert at the start: "If every task left is `NEEDS USER` or blocked, skip review and merge: go straight to the report below." Insert before "Then remove the worktree" ... at the end of §8, add:
     ```
     **Report, once.** Run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/run_report.py" <worktree> <run start from §1b>`. Write the report in plain words first, for someone who does not code: how many parts are done; each part not done and why; each `NEEDS USER` item as a question with your recommended answer. Then a `Details` heading: the counts (`prompts` should be 0), commits, branch, files. Store one `memory_store` lesson (kind outcome) per recurring cause you saw, for example "executors edited files through inline code N times" (the `inline_code` count) or "the plan missed the risky action X"; put proposals (a Risky actions default, a new detector case) in the report, never apply them. Then send one PushNotification (load it with ToolSearch `select:PushNotification`) with one plain sentence: done, or stopped and why.
     ```
  10. `claude/agents/executor.md` rule 1: replace the sentence "Write files with Edit or Write, not shell redirects, heredocs or `cp`/`mv`: the hook checks those tools silently, while a shell write makes the user confirm it." with "Edit files with Edit or Write. A shell write to a file outside your Scope is denied, and every change you made is checked when you report back: anything outside your Scope sends the task back to you to revert. Put scratch files in your scratchpad." Add rule 6: "6. If the gate denies a risky command, find a safer way or end your report with `NEEDS DECISION: <exact command> because <reason>`. Never ask the user anything." Rule 5: append "Each commit subject ends with `(task N)` (your task number), and your report's last block line is `COMMITS: <sha> [<sha>...]` or `COMMITS: none`." Add the line `COMMITS: <shas or none>` to the final report block after `UNRESOLVED:`.
  11. `claude/skills/plan/SKILL.md`: after `## Review focus` add:
      ```
      ## Risky actions
      If a task must run a command the gate would judge risky (deleting generated folders, resetting a test database, a force push the design calls for), list it in a `## Risky actions` section after Review Focus, one bullet each: - `<exact command, or a prefix ending in *>` — <one plain sentence: what it does, what could be lost, why the plan needs it>. Write the sentence for someone who does not code. Approving the plan approves these, so the run never stops to ask. No such command: leave the section out.
      ```
      and in `## Self-review` add item 5: "**Risky actions:** every risky command a task's steps run is listed, each with its plain sentence."
  12. `claude/commands/wplan.md`: add one line: "Ask the user's critical questions now, in plain words; the run that follows asks nothing. The plan's `## Risky actions` (see the plan skill) is part of what they approve."
  13. `claude/skills/interrogate/SKILL.md` line "If you are unsure of the intent, ask the user before going on." becomes "If you are unsure of the intent, ask the user before going on; during /orchestrate, take the intent from the approved spec and plan instead, because nobody is asked during a run."
- [ ] **Step 4: Run the tests.** Run the Done command. Expected: PASS. If an older doc test pins a sentence you replaced (for example the executor's rule 1 text in a pstack or ladder test), update that test's expected text to the new sentence; do not keep the old sentence.
- [ ] **Step 5: Commit** the Scope files as `docs(orchestrate): unattended run instructions for Claude (task 9)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 10: Codex and OpenCode orchestrate instructions, GOV-2

Goal: The hand-written Codex and OpenCode orchestrate skills and the OpenCode `/orchestrate` command carry the same unattended-run steps as Task 9, and the GOV-2 row describes the new enforcement.
Scope:
- codex/skills/orchestrate/SKILL.md
- opencode/skill/dryas-orchestrate/SKILL.md
- opencode/command/orchestrate.md
- reference/README.md
- install/tests/test_unattended_docs_editions.py
Done:
- `python3 -m pytest -q install/tests/test_unattended_docs_editions.py install/tests/test_opencode_docs.py install/tests/test_opencode_skills.py install/tests/test_codex_skill_render.py` passes
Failing test first: install/tests/test_unattended_docs_editions.py :: EditionsDocsTest.test_codex_and_opencode_orchestrate

**Interfaces:**
- Consumes: the same CLIs and formats as Task 9 (`scope_audit.py`, `preflight.py`, `run_report.py`, `## Risky actions`, `.orchestrate/approved.json`, `NEEDS DECISION`, `COMMITS:`).
- Produces: nothing other tasks read.

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_unattended_docs_editions.py`:

```python
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class EditionsDocsTest(unittest.TestCase):
    def test_codex_and_opencode_orchestrate(self):
        for rel in ("codex/skills/orchestrate/SKILL.md", "opencode/skill/dryas-orchestrate/SKILL.md"):
            s = read(rel)
            for needle in ("jev/preflight.py", "## Risky actions", "jev/scope_audit.py", "NEEDS DECISION",
                           ".orchestrate/approved.json", "NEEDS USER", "jev/run_report.py", "nobody is asked"):
                self.assertIn(needle, s, "%s: %s" % (rel, needle))

    def test_opencode_command_mentions_unattended(self):
        self.assertIn("nobody is asked", read("opencode/command/orchestrate.md"))

    def test_gov2_row(self):
        row = [l for l in read("reference/README.md").splitlines() if l.startswith("| GOV-2 |")][0]
        self.assertIn("audited against its scope", row)
        self.assertIn("partial", row)
        self.assertNotIn("shell-command edits are a known limit", row)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_unattended_docs_editions.py`. Expected: FAIL (`AssertionError: 'jev/preflight.py' not found`).
- [ ] **Step 3: Implement.** Read `claude/skills/orchestrate/SKILL.md` as Task 9 left it (if Task 9 has not merged yet, use the text of Task 9 Step 3 items 2-9 in this plan) and carry the same steps into `codex/skills/orchestrate/SKILL.md` and `opencode/skill/dryas-orchestrate/SKILL.md`, in each file's own words for its harness: keep each file's script-path convention (read how it already calls `planfile.py` and call `preflight.py`, `scope_audit.py`, `run_report.py` the same way), its own notification wording (Codex and OpenCode have no PushNotification: say "end with the report; the harness shows it"), and its existing section numbers. In `opencode/command/orchestrate.md` add one line: "The user decides in brainstorm and plan; during the run nobody is asked." In `reference/README.md` replace the GOV-2 row with:
  `| GOV-2 | partial | partial | partial | Hook denies Edit/Write outside scope (and Codex \`apply_patch\`; OpenCode edit, write and patch tools). Shell writes with readable targets are denied outside scope; every task's changes are audited against its scope at task return and sent back if outside. Writes outside the worktree by inline code are a known limit |`
- [ ] **Step 4: Run the tests.** Run the Done command. Expected: PASS.
- [ ] **Step 5: Commit** the Scope files as `docs(orchestrate): unattended run for Codex and OpenCode; GOV-2 row (task 10)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 11: Regression corpus of real executor commands

Goal: A fixture of about 200 real executor shell commands from 2026-10-13..15 pins that the scope lock asks about none of them, allows every in-scope one and denies every out-of-scope readable target.
Scope:
- claude/jev/tests/fixtures/scope_shell_corpus.jsonl
- claude/jev/tests/test_scope_shell_corpus.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_scope_shell_corpus.py` passes
- the fixture has at least 150 `allow` and 20 `deny` lines, and `python3 claude/jev/redact.py` (or the redaction function it exposes; read it first) finds nothing left to redact in it
Failing test first: claude/jev/tests/test_scope_shell_corpus.py :: CorpusTest.test_corpus

**Interfaces:**
- Consumes: Task 3's `scope_lock.run` decisions and scope records.
- Produces: fixture lines `{"cmd": str, "cwd": "<relative dir in the fixture worktree, '' for its root>", "expect": "allow"|"deny", "why": "<category>"}`.

- [ ] **Step 1: Write the failing test.** Create `claude/jev/tests/test_scope_shell_corpus.py`:

```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scope_lock

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = "## Task 1: corpus\nGoal: g\nScope:\n- src/**\n- tests/**\nDone:\n- d\n"


class CorpusTest(unittest.TestCase):
    def test_corpus(self):
        wt = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(wt, ".orchestrate"))
        with open(os.path.join(wt, ".orchestrate", "PLAN.md"), "w") as f:
            f.write(PLAN)
        with open(os.path.join(wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ["1"]}, f)
        os.environ["JEV_LOG_DIR"] = tempfile.mkdtemp()
        with open(os.path.join(HERE, "fixtures", "scope_shell_corpus.jsonl"), encoding="utf-8") as f:
            cases = [json.loads(l) for l in f if l.strip()]
        self.assertGreaterEqual(sum(c["expect"] == "allow" for c in cases), 150)
        self.assertGreaterEqual(sum(c["expect"] == "deny" for c in cases), 20)
        wrong = []
        for c in cases:
            out = scope_lock.run({"tool_name": "Bash", "tool_input": {"command": c["cmd"]}, "agent_id": "a1",
                                  "cwd": os.path.join(wt, c["cwd"])})
            got = out["hookSpecificOutput"]["permissionDecision"] if out else "allow"
            if got != c["expect"]:
                wrong.append((c["why"], c["expect"], got, c["cmd"][:120]))
        self.assertEqual(wrong, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q claude/jev/tests/test_scope_shell_corpus.py`. Expected: FAIL with `FileNotFoundError` (no fixture yet).
- [ ] **Step 3: Build the fixture.** In your scratchpad (not in the repo), write a short script that reads the Bash `tool_use` commands of subagent transcripts (`~/.claude/projects/**/*.jsonl` and `~/.claude-team/projects/**/*.jsonl`, files modified 2026-10-13..15, entries with `isSidechain: true` or under a `subagents/` folder). Pick about 200 commands that the old detector flagged as writes, covering every category: heredoc/arrow false positives, commit messages, `sed -i`, `perl -pi`, redirects, `cp`/`mv`/`mkdir`/`touch`/`rm`, inline `python3 - <<EOF`/`-c`/`node -e`, scripts, `git checkout --`, scratchpad writes. Rewrite each one so it runs against the fixture worktree: absolute worktree paths become relative paths under `src/` or `tests/` (in scope, `expect: allow`) or under `docs/`, `README.md`, `/tmp/elsewhere-*` (out of scope, `expect: deny`); scratchpad paths become `/tmp/elsewhere-*` with `expect: deny` (the fixture has no session id). Trim code bodies and commit messages to what the parser needs (keep heredoc delimiters, keep `=>` and `>` inside them). Remove any secret, token, e-mail, user name or customer text; run the repo's `redact.py` over each `cmd` and check by eye. Write one JSON object per line with `cmd`, `cwd`, `expect`, `why`. Expected outcomes follow the Task 3 table: readable targets in `src/**` or `tests/**` → allow; a readable target outside → deny; unreadable writes → allow.
- [ ] **Step 4: Run the tests.** Run the Done command. Expected: PASS. A wrong case is a real finding: if the parser is wrong, report it (`UNRESOLVED:`) with the command; do not change the expectation to match.
- [ ] **Step 5: Commit** the two Scope files as `test(scope-lock): regression corpus of real executor commands (task 11)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 12: Sync editions and release 2.3.1

Goal: Codex and OpenCode copies are re-rendered from `claude/`, the version is 2.3.1 everywhere it is pinned, the CHANGELOG says in plain words what the release fixes, and every release check passes.
Scope:
- codex/**
- opencode/**
- .claude-plugin/marketplace.json
- claude/.claude-plugin/plugin.json
- claude/jev/jev_mcp.py
- CHANGELOG.md
- docs/specs/2026-10-15-scope-lock-shell-writes-design.md
Done:
- `python3 tools/sync_codex_plugin.py --check` exits 0
- `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests` passes
- `python3 tools/inventory.py --check` reports 0 problems
- `python3 tools/release_check.py` reports no FAIL
- `grep -rn '"2.3.0"' .claude-plugin claude/.claude-plugin codex/.codex-plugin claude/jev/jev_mcp.py codex/jev/jev_mcp.py opencode/dryas/jev/jev_mcp.py` prints nothing
Failing test first: none (review)

**Interfaces:**
- Consumes: all earlier tasks.
- Produces: the release.

- [ ] **Step 1: Sync.** Run `python3 tools/sync_codex_plugin.py`, then `python3 tools/sync_codex_plugin.py --check`. Expected: exit 0. Read `git status --short codex opencode`: only files this plan changed (jev modules, executor agents, plan skill) may appear.
- [ ] **Step 2: Version.** Change `2.3.0` to `2.3.1` in `.claude-plugin/marketplace.json`, `claude/.claude-plugin/plugin.json`, `codex/.codex-plugin/plugin.json`, and the `serverInfo` version in `claude/jev/jev_mcp.py` (then re-run the sync so `codex/jev/jev_mcp.py` and `opencode/dryas/jev/jev_mcp.py` follow).
- [ ] **Step 3: CHANGELOG.** Add a `## 2.3.1` entry above `## 2.3.0`, plain words first: "Approve the plan, walk away: `/orchestrate` no longer stops to ask you about routine file changes or risky commands during a run. Shell edits outside a task's files are blocked or sent back; risky commands are decided by the plan, the judge or the orchestrator, and only what cannot be undone outside the project waits for you in the end report. Before starting, `/orchestrate` checks that the session cannot stop to ask, and it ends with one report and one notification." Then a short technical list (shellwrites, scope audit, runrules, preflight, run report, /tune prompt counts, GOV-2 wording).
- [ ] **Step 4: Spec rollout.** In `docs/specs/2026-10-15-scope-lock-shell-writes-design.md` section 11, change "Minor release." to "Bug-fix release 2.3.1." and add to section 6 that Bash scope records also log allowed writes (`kind: "allow"`, with the rule), which is what feeds the `inline_code` lesson.
- [ ] **Step 5: Verify.** Run every Done command. Expected: all pass. If `install/tests/test_launch_pitch_docs.py` pins the newest CHANGELOG heading, read it and make it accept `## 2.3.1` above `## 2.3.0` without weakening what it checks.
- [ ] **Step 6: Commit** the changed files as `chore(release): Dryas 2.3.1 — unattended orchestration fixes (task 12)` when the dispatch prompt allows it; otherwise report and the orchestrator commits.
