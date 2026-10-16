#!/usr/bin/env python3
"""What a Bash command writes, for the scope lock (unattended orchestration).

analyse(cmd, cwd) parses the command with local_judge's quote- and heredoc-aware scanner, so heredoc bodies and
quoted text (commit messages, inline code) are data, never commands. It returns an Analysis:
  writes  - something in it writes, moves or deletes files, or runs code that may (inline code, scripts)
  paths   - absolute paths the readable forms write: sed -i, perl -i, output redirects, tee, dd of=, the
            destination of cp/mv/ln/install, the operands of rm/rmdir/unlink/shred/mkdir/touch/truncate and
            chmod/chown/chflags, git checkout -- / git restore paths, find -fprint/-fprint0/-fprintf/-fls FILE,
            curl -o/--output, wget -O/--output-document, sort -o and git diff|log|format-patch --output FILE.
            `cd <literal>` is followed.
  unknown - some write could not be read (inline interpreter code, scripts, a shell fed by a pipe, $VAR, $(...),
            globs, ~, xargs, a cd to an unknown place, archives, package installs, find -delete/-exec/-execdir/
            -ok/-okdir, curl -O, awk with > in its program, git config that sets a value, other git writes)
  rule    - the first rule that fired, for the scope log ("" when nothing writes)
Pure, stdlib only, never raises: a parse error or a command over local_judge.MAX_CHARS is Analysis(True, [], True,
"error").
Known limit (GOV-2, same as Dryas 1.0): code that runs a script or interpreter file (`python x.py`, `make`,
`node x.js`) can write anywhere and is not flagged here; such writes inside the worktree are caught by the
task-return audit (scope_audit.py), writes outside it are not.
"""
import os
import posixpath
import re
import sys
from typing import List, NamedTuple, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_judge as lj

# Same pattern as prescreen._SED_CMD (a test keeps them equal); importing prescreen here costs ~5 ms per process.
_SED_CMD = re.compile(r"(?:^|[/;{}0-9$\s])[gpIiMm0-9]*\s*[wWe](?=\s|$|[;}])")

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
_FIND_RUN = {"-delete", "-exec", "-execdir", "-ok", "-okdir"}
_FIND_OUT = {"-fprint", "-fprint0", "-fprintf", "-fls"}
# command -> (short letter, long option naming the output file, options that write a file named by the URL,
# short letters whose value follows them, so a bundle stops there)
_OUT_OPT = {"curl": ("o", "--output", {"-O", "--remote-name", "--remote-name-all"}, "AbcCdDeEFHKmrTuUwxXyYzQPt"),
            "wget": ("O", "--output-document", set(), "aABDeiIlnoPQRtTUwXY"),
            "sort": ("o", "--output", set(), "kStT"), "git": ("", "--output", set(), "")}
_GIT_OUT = {"diff", "log", "format-patch"}  # git diff|log|format-patch --output FILE
_AWK = {"awk", "gawk", "mawk", "nawk"}


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
        if c.src is not None:
            return st.hit("script", unknown=True)  # echo ... | sh: the script comes from the pipe
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
    if name == "find":
        return _find(args, st)
    if name in ("curl", "wget", "sort"):
        return _out_opt(name, args, st)
    if name in _AWK:
        return _awk(args, st)
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


def _out_target(word: str, st: _State, rule: str) -> None:
    if word != "-":  # "-" is stdout
        st.target(word, False, rule)


def _find(args: List[str], st: _State) -> None:
    for i, x in enumerate(args):
        if x in _FIND_RUN:
            return st.hit("find", unknown=True)
        if x in _FIND_OUT:
            _out_target(args[i + 1] if i + 1 < len(args) else "", st, "find")
    return None


def _out_opt(name: str, args: List[str], st: _State) -> None:
    """curl -o FILE, wget -O FILE, sort -o FILE and their long forms (also bundled: curl -sSLo FILE)."""
    letter, long, remote, valued = _OUT_OPT[name]
    i = 0
    while i < len(args):
        x = args[i]
        i += 1
        if x == "--":
            break
        if x in remote:
            return st.hit(name, unknown=True)
        if x == long:
            _out_target(args[i] if i < len(args) else "", st, name)
            i += 1
        elif x.startswith(long + "="):
            _out_target(x.split("=", 1)[1], st, name)
        elif _short(x):
            for k, ch in enumerate(x[1:], 1):
                if "-" + ch in remote:
                    return st.hit(name, unknown=True)
                if ch == letter or ch in valued:
                    value = x[k + 1:]
                    if not value:
                        value, i = (args[i] if i < len(args) else ""), i + 1
                    if ch == letter:
                        _out_target(value, st, name)
                    break
    return None


def _awk(args: List[str], st: _State) -> None:
    """awk 'PROGRAM' FILES: a > or >> in PROGRAM writes a file the program names."""
    i = 0
    while i < len(args):
        x = args[i]
        i += 1
        if x in ("-f", "--file"):
            return None  # program file: not read here
        if x in ("-F", "-v"):
            i += 1
        elif x == "--" or not x.startswith("-") or x == "-":
            prog = args[i] if x == "--" and i < len(args) else x
            if ">" in prog:
                st.hit("awk", unknown=True)
            return None
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
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if sub in _GIT_OUT:
        return _out_opt("git", rest, st)
    if sub == "config":
        reads = [x for x in rest if x.startswith("--get") or x in ("--list", "-l")]
        if not reads and rest[:1] not in (["get"], ["list"]):
            st.hit("git", unknown=True)
        return None
    if sub not in _GIT_WRITE:
        return None
    if not other_dir and (sub == "restore" or (sub == "checkout" and "--" in rest)):
        paths = rest[rest.index("--") + 1:] if "--" in rest else _operands("git-restore", rest)
        if paths:
            for p in paths:
                st.target(p, False, "git")
            return None
    return st.hit("git", unknown=True)
