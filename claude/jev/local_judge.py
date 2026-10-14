"""Local judge: deterministic answers to the gate's questions (safe, risk), no network, same answer shape as
jev_client.judge, plus a direct "decision". A short DANGER list is judged unsafe (decision deny); a short
DESTRUCTIVE list is judged destructive (decision ask); everything else gets no decision and falls through to the
harness's permissions. It never allows: the gate itself never allows. An internal error, or a command longer than
MAX_CHARS (not parsed at all), answers destructive, so the gate asks.

The command is parsed, not regex-scanned: one linear, quote-aware pass splits it into simple commands (on ; & &&
|| | newline ( ) { } $( and backticks), drops keywords, NAME=value assignments and wrappers (sudo, env, nice,
timeout, xargs, ...), and judges the command word and its arguments. `sh -c STRING` and `eval` are judged
recursively (depth 3); so is a heredoc or here-string fed to a shell without -c. A heredoc body is data: it
is skipped up to its delimiter line (the whole rest if unterminated) and never judged as commands. Quoted text is one argument, so `grep "rm -rf /"` or `git commit -m 'reset --hard'` is
not a hit.

Discarding uncommitted work or stashes asks too (git checkout -- <path> / checkout ., git restore <path> without
--staged, git stash clear / drop): those changes have no other copy.

Boundary of the short list: rm -r is denied only for /, a glob in the first component, ~ / $HOME, the home roots
/Users and /home and one user's whole home. Deletes of other system folders (/usr, /etc, /var, ...) are NOT on the
short list; they get no decision here and are left to the harness's permissions."""
import functools
import posixpath
import re
from typing import Any, Dict, List, Optional, Tuple

MAX_CHARS = 65536
_DEPTH = 3
# Matched on the capped raw text only; no nested quantifiers. The lookbehind pins NAME to a word start, so a
# long run of name characters is tried from one position only (linear).
_FORK_BOMB = re.compile(r"(?<![^\s;&|(){}])([^\s;&|(){}<>'\"`$\\]+)\s*\(\)\s*\{\s*\1\s*\|\s*\1\s*&\s*\}\s*;\s*\1")
_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
_DRIVE = re.compile(r"[A-Za-z]:[\\/]?\Z")
_DD_DEV = re.compile(r"of=/dev/(?:sd|hd|nvme|disk|rdisk)")
_DEV = re.compile(r"/dev/(?:sd[a-z]|hd[a-z]|nvme[0-9]|disk[0-9]|rdisk[0-9])")
_SQL = re.compile(r"\b(?:drop\s+(?:table|database|schema)|truncate\s+table)\s+(?:if\s+exists\s+)?[\"`\[]?\w", re.I)
_SQL_CLIENTS = {"psql", "mysql", "mariadb", "sqlite3", "sqlcmd", "duckdb", "clickhouse-client", "cockroach"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_POWERSHELL = {"powershell", "pwsh", "powershell.exe", "pwsh.exe"}
_KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "("}
# wrapper -> options that take a separate value
_WRAPPERS: Dict[str, set] = {
    "sudo": {"-u", "-g", "-C", "-h", "-p", "--user", "--group", "--close-from", "--host", "--prompt"},
    "doas": {"-u"}, "env": {"-u", "--unset", "-C", "--chdir"}, "command": set(), "builtin": set(),
    "exec": {"-a"}, "nohup": set(), "nice": {"-n", "--adjustment"}, "time": {"-f", "-o"},
    "timeout": {"-k", "-s", "--kill-after", "--signal"}, "stdbuf": {"-i", "-o", "-e"},
    "ionice": {"-c", "-n", "-p", "-P", "-u"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-s", "-E", "-a"},
}


class _Cmd:
    """One simple command: words (quotes removed), which words held $( or a backtick, redirection targets,
    heredoc and here-string texts fed to its stdin, and the simple command it is piped from."""
    __slots__ = ("words", "dyn", "redirs", "here", "src")

    def __init__(self, src: "Optional[_Cmd]" = None) -> None:
        self.words: List[str] = []
        self.dyn: List[bool] = []
        self.redirs: List[str] = []
        self.here: List[str] = []
        self.src = src


def _scan(s: str) -> List[_Cmd]:
    """Split `s` into simple commands in one pass over its characters (linear in len(s))."""
    out: List[_Cmd] = []
    stack: List[Tuple] = []  # ("(",) group frames and ("$(" | "`", saved outer state) substitution frames
    cmd = _Cmd()
    cur: List[str] = []
    have = dyn = redir = False  # word started (even if empty), word holds $( or `, word is a redirect target
    quote = ""
    hkind = ""  # "<<", "<<-" or "<<<" while the redirect target is a heredoc delimiter or here-string
    pending: List[Tuple[str, bool, _Cmd]] = []  # heredocs whose body starts after the current line
    arith = 0  # open "((" frames: (( )) and $(( )) arithmetic, where << is a shift
    n, i = len(s), 0

    def end_word() -> None:
        nonlocal cur, have, dyn, redir, hkind
        if cur or have:
            word = "".join(cur)
            if redir:
                cmd.redirs.append(word)
                if hkind == "<<<":
                    cmd.here.append(word)
                elif hkind:
                    pending.append((word, hkind == "<<-", cmd))
                redir, hkind = False, ""
            else:
                cmd.words.append(word)
                cmd.dyn.append(dyn)
        cur, have, dyn = [], False, False

    def end_cmd(pipe: bool = False) -> None:
        nonlocal cmd, redir, hkind
        end_word()
        redir, hkind = False, ""
        if cmd.words or cmd.redirs:
            out.append(cmd)
        cmd = _Cmd(cmd if pipe else None)

    def push_sub(kind: str) -> None:
        nonlocal cmd, cur, have, dyn, redir, quote
        stack.append((kind, (cmd, cur, redir, quote)))
        cmd, cur, have, dyn, redir, quote = _Cmd(), [], False, False, False, ""

    def pop_sub() -> None:
        nonlocal cmd, cur, have, dyn, redir, quote
        end_cmd()
        _, (cmd, cur, redir, quote) = stack.pop()
        have = dyn = True

    while i < n:
        c = s[i]
        nxt = s[i + 1] if i + 1 < n else ""
        if quote == "'":
            if c == "'":
                quote = ""
            else:
                cur.append(c)
        elif quote == '"' and c not in '"\\$`':
            cur.append(c)
        elif quote == '"' and c == '"':
            quote = ""
        elif quote == '"' and c == "\\":
            if nxt and nxt in '$`"\\\n':
                cur.append(nxt)
                i += 1
            else:
                cur.append(c)
        elif c == "$" and nxt == "(":
            push_sub("$(")
            i += 1
        elif c == "`":
            if stack and stack[-1][0] == "`":
                pop_sub()
            else:
                push_sub("`")
        elif quote == '"':  # a lone $
            cur.append(c)
        elif c in " \t\r":
            end_word()
        elif c == "\n":
            end_cmd()
            j = i + 1
            for delim, tabs, owner in pending:  # bodies in order, each up to its delimiter line
                body = []
                while j < n:
                    e = s.find("\n", j)
                    e = n if e < 0 else e
                    line = s[j:e]
                    j = e + 1
                    if (line.lstrip("\t") if tabs else line) == delim:
                        break
                    body.append(line)
                owner.here.append("\n".join(body))
            pending.clear()
            i = j - 1
        elif c == "\\":
            if nxt and nxt != "\n":
                cur.append(nxt)
            elif not nxt:
                cur.append(c)
            i += 1
        elif c in "'\"":
            quote, have = c, True
        elif c == "$" and nxt == "'":
            quote, have = "'", True
            i += 1
        elif c == "#" and not cur and not have:
            while i < n and s[i] != "\n":
                i += 1
            continue
        elif c == ";":
            end_cmd()
        elif c == "&" and nxt == ">":
            end_word()
            redir = True
            i += 2 if s[i + 2:i + 3] == ">" else 1
        elif c == "&":
            end_cmd()
            i += nxt == "&"
        elif c == "|":
            end_cmd(pipe=nxt != "|")
            i += nxt in "|&" and nxt != ""
        elif c == "(":
            end_cmd()
            kind = "((" if nxt == "(" or s[i - 1:i] == "(" else "("
            arith += kind == "(("
            stack.append((kind, None))
        elif c == ")":
            if stack and stack[-1][0] == "$(":
                pop_sub()
            else:
                end_cmd()
                if stack and stack[-1][0] in ("(", "(("):
                    arith -= stack.pop()[0] == "(("
        elif c in "{}" and not cur and not have:
            end_cmd()
        elif c in "<>":
            if cur and "".join(cur).isdigit():
                cur, have = [], False
            else:
                end_word()
            if nxt == "(":  # process substitution <(...) / >(...)
                push_sub("$(")
                i += 1
            else:
                redir, start = True, i
                while i + 1 < n and s[i + 1] in "<>&|":
                    i += 1
                op = s[start:i + 1]
                if op == "<<" and s[i + 1:i + 2] == "-":
                    op, i = "<<-", i + 1
                hkind = op if op == "<<<" or (op in ("<<", "<<-") and not arith) else ""
        else:
            cur.append(c)
        i += 1
    end_cmd()
    while stack:
        if stack[-1][0] in ("(", "(("):
            stack.pop()
        else:
            pop_sub()
            end_cmd()
    return out


def _base(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _head(words: List[str]) -> Tuple[int, bool]:
    """Index of the command word after keywords, assignments and wrappers (len(words) if none), and whether
    xargs was among the wrappers."""
    i, n, xargs = 0, len(words), False
    while i < n:
        w = words[i]
        name = _base(w)
        if w in _KEYWORDS or _ASSIGN.match(w):
            i += 1
            continue
        if name not in _WRAPPERS:
            break
        xargs = xargs or name == "xargs"
        takes = _WRAPPERS[name]
        i += 1
        while i < n and words[i].startswith("-") and words[i] != "-":
            opt = words[i]
            i += 1
            if opt == "--":
                break
            if opt.startswith("--"):
                i += opt in takes
                continue
            for k in range(1, len(opt)):  # a bundle; a value-taking letter eats the rest or the next word
                if "-" + opt[k] in takes:
                    i += k == len(opt) - 1
                    break
        if name == "timeout" and i < n:
            i += 1  # the duration
    return i, xargs


def _norm(path: str) -> str:
    p = posixpath.normpath(path)
    return "/" + p.lstrip("/") if p.startswith("/") else p


def _is_root(t: str) -> bool:
    for home in ("~", "$HOME", "${HOME}"):
        if t == home or t.startswith(home + "/"):
            return _norm("/" + t[len(home):]) in ("/", "/*")
    if _DRIVE.match(t):
        return True
    if not t.startswith("/"):
        return False
    parts = _norm(t).strip("/").split("/")
    first = parts[0]
    if first == "" or any(ch in first for ch in "*?["):
        return True
    if first in ("Users", "home"):
        return len(parts) <= 2 or (len(parts) == 3 and parts[2] == "*")
    return False


def _bundles(args: List[str]) -> str:
    """The letters of every single-dash option word."""
    return "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))


def _git(args: List[str]) -> Optional[str]:
    i, n = 0, len(args)
    while i < n and args[i].startswith("-"):
        i += 1 + (args[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"))
    if i >= n:
        return None
    sub, rest = args[i], args[i + 1:]
    flags = _bundles(rest)
    if sub == "reset" and "--hard" in rest:
        return "git_reset_hard"
    if sub == "clean" and ("--force" in rest or "f" in flags) and not ("--dry-run" in rest or "n" in flags):
        return "git_clean_force"
    if sub == "push" and ("--force" in rest or "f" in flags or "d" in flags or "--delete" in rest
                          or "--mirror" in rest or any(len(a) > 1 and a[0] in "+:" for a in rest)):
        return "git_push_force"
    if sub == "branch" and ("D" in flags or (("d" in flags or "--delete" in rest)
                                             and ("f" in flags or "--force" in rest))):
        return "git_branch_delete"
    return _git_discard(sub, rest, flags)


def _operands(args: List[str], takes: Tuple[str, ...] = ()) -> List[str]:
    """Non-option words of a git subcommand; everything after "--" is an operand; an option in `takes`
    consumes the next word as its value."""
    out: List[str] = []
    i, n = 0, len(args)
    while i < n:
        a = args[i]
        if a == "--":
            return out + args[i + 1:]
        if a.startswith("-") and a != "-":
            i += 1 + (a in takes)
            continue
        out.append(a)
        i += 1
    return out


def _git_discard(sub: str, rest: List[str], flags: str) -> Optional[str]:
    """Commands that throw away uncommitted work or stashes (user decision 2026-10-14: always ask)."""
    if sub == "checkout":
        if "--" in rest:
            return "git_checkout_discard" if rest[rest.index("--") + 1:] else None
        return "git_checkout_discard" if "." in _operands(rest, ("-b", "-B", "--orphan")) else None
    if sub == "restore":
        staged = "--staged" in rest or "S" in flags
        worktree = "--worktree" in rest or "W" in flags
        if _operands(rest, ("-s", "--source", "--pathspec-from-file")) and (worktree or not staged):
            return "git_restore_discard"
        return None
    if sub == "stash" and _operands(rest)[:1] in (["clear"], ["drop"]):
        return "git_stash_drop"
    return None


def _shell_string(args: List[str]) -> Optional[str]:
    """STRING of `sh -c STRING` (also -lc, -ec, ...), else None."""
    has_c = False
    for a in args:
        if a.startswith("-") and a != "-" and a != "--":
            has_c = has_c or (not a.startswith("--") and "c" in a)
        elif a != "--":
            return a if has_c else None
    return None


def _judge(cmd: _Cmd, depth: int, hits: List[Optional[str]]) -> None:
    """Record the first danger in hits[0] and the first destructive pattern in hits[1]."""
    def found(slot: int, name: str) -> None:
        if hits[slot] is None:
            hits[slot] = name
    if any(_DEV.match(t) for t in cmd.redirs):
        found(0, "overwrite_device")
    k, xargs = _head(cmd.words)
    if k >= len(cmd.words):
        return
    cw, args, dyn = _base(cmd.words[k]), cmd.words[k + 1:], cmd.dyn[k + 1:]
    if cw in _SHELLS:
        string = _shell_string(args)
        if string is not None:
            if depth < _DEPTH:
                _walk(string, depth + 1, hits)
        elif cmd.here:  # a heredoc or here-string to a shell is a script
            for text in cmd.here if depth < _DEPTH else ():
                _walk(text, depth + 1, hits)
        elif cmd.src is not None and cmd.src.words:
            j, _ = _head(cmd.src.words)
            if j < len(cmd.src.words) and _base(cmd.src.words[j]) in ("curl", "wget"):
                found(1, "pipe_to_shell")
    elif cw == "eval":
        if depth < _DEPTH:
            _walk(" ".join(args), depth + 1, hits)
    elif cw == "rm":
        cut = args.index("--") if "--" in args else len(args)
        opts = args[:cut]
        if "r" in _bundles(opts).lower() or "--recursive" in opts:
            targets = [(a, d) for j, (a, d) in enumerate(zip(args, dyn))
                       if j > cut or (j < cut and not (a.startswith("-") and a != "-"))]
            if any(_is_root(a) for a, _ in targets):
                found(0, "rm_root")
            if any(d for _, d in targets):
                found(1, "rm_dynamic_target")
            if xargs:
                found(1, "xargs_rm_recursive")
    elif cw == "mkfs" or cw.startswith("mkfs."):
        found(0, "mkfs")
    elif cw == "dd":
        if any(_DD_DEV.match(a) for a in args):
            found(0, "dd_device")
    elif cw.lower() == "format":
        if any(_DRIVE.match(a) for a in args):
            found(0, "format_drive")
    elif cw.lower() in ("del", "erase"):
        low = [a.lower() for a in args]
        if "/s" in low and "/q" in low and any(_DRIVE.match(a) for a in args):
            found(0, "del_drive")
    elif cw == "chmod":
        if ("R" in _bundles(args) or "--recursive" in args) and any(a in ("777", "0777", "a+rwx") for a in args) \
                and any(a.startswith("/") and _norm(a) == "/" for a in args):
            found(0, "chmod_root")
    elif cw == "git":
        hit = _git(args)
        if hit:
            found(1, hit)
    elif cw in _SQL_CLIENTS:
        if any(_SQL.search(a) for a in args):
            found(1, "sql_drop")
    elif cw.lower() in _POWERSHELL:
        for a in args:
            r = a.lower()[1:] if a.startswith("-") else ""
            if r == "ec" or (r[:1] == "e" and "encodedcommand".startswith(r)):
                found(1, "powershell_encoded")
                break


def _walk(text: str, depth: int, hits: List[Optional[str]]) -> None:
    for cmd in _scan(text):
        _judge(cmd, depth, hits)


@functools.lru_cache(maxsize=8)
def _analyse(cmd: str) -> Tuple[Optional[str], Optional[str]]:
    """(first danger, first destructive pattern) of a command no longer than MAX_CHARS."""
    hits: List[Optional[str]] = [None, None]
    if _FORK_BOMB.search(cmd):
        hits[0] = "fork_bomb"
    _walk(cmd, 0, hits)
    return hits[0], hits[1]


def danger(cmd: str) -> Optional[str]:
    return _analyse(cmd[:MAX_CHARS])[0]


def destructive(cmd: str) -> Optional[str]:
    return _analyse(cmd[:MAX_CHARS])[1]


def _result(p_safe: float, risk: str, risk_conf: float, reasons: List[str],
            decision: Optional[str] = None) -> Dict[str, Any]:
    return {"answers": {"safe": {"type": "noul", "value": p_safe, "confidence": max(p_safe, 1.0 - p_safe)},
                        "risk": {"type": "choice", "value": risk, "confidence": risk_conf, "probabilities": {}}},
            "reasons": reasons, "decision": decision}


def gate_answers(tool: str, command: str = "", risky: bool = True) -> Dict[str, Any]:
    try:
        if tool == "Bash":
            if len(command) > MAX_CHARS:
                return _result(0.5, "destructive", 0.8, ["too_long"], "ask")
            hit = danger(command)
            if hit:
                return _result(0.02, "destructive", 0.95, ["danger:" + hit], "deny")
            hit = destructive(command)
            if hit:
                return _result(0.5, "destructive", 0.8, ["destructive:" + hit], "ask")
            if risky:
                return _result(0.8, "worth_a_look", 0.6, ["prescreen:risky"])
            return _result(0.9, "routine", 0.9, [])
        return _result(0.7, "worth_a_look", 0.6, ["file:sensitive_or_outside"])
    except Exception as e:
        return _result(0.5, "destructive", 0.8, ["error:" + type(e).__name__], "ask")
