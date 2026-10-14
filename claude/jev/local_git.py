"""The git rules of the local judge: which `git` invocations are destructive. Discarding uncommitted work or
stashes asks too: those changes have no other copy. Covered: git checkout with -f/--force, with "--" and a path,
with a path operand after a first operand (<tree-ish> <path...>), or with "." or a <dir>/ operand; git switch with
-f/--force/--discard-changes (also with -C); git restore <path> without --staged; git stash clear / drop. A unique
prefix of a long option (git accepts --forc) counts as the option."""
from typing import List, Optional, Tuple


def bundles(args: List[str]) -> str:
    """The letters of every single-dash option word."""
    return "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))


def git_hit(args: List[str]) -> Optional[str]:
    i, n = 0, len(args)
    while i < n and args[i].startswith("-"):
        i += 1 + (args[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"))
    if i >= n:
        return None
    sub, rest = args[i], args[i + 1:]
    flags = bundles(rest)
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


def _long(rest: List[str], *names: str) -> bool:
    """True when an option word is one of `names` or a prefix git would expand to it (at least "--" + 1 letter)."""
    return any(len(a) > 2 and a.startswith("--") and n.startswith(a) for a in rest for n in names)


def _git_discard(sub: str, rest: List[str], flags: str) -> Optional[str]:
    """Commands that throw away uncommitted work or stashes (user decision 2026-10-14: always ask)."""
    if sub == "checkout":
        if "f" in flags or _long(rest, "--force"):
            return "git_checkout_discard"
        if "--" in rest:
            return "git_checkout_discard" if rest[rest.index("--") + 1:] else None
        ops = _operands(rest, ("-b", "-B", "--orphan"))
        if len(ops) > 1 or any(a == "." or a.endswith("/") for a in ops):
            return "git_checkout_discard"
        return None
    if sub == "switch":
        if "f" in flags or _long(rest, "--force", "--discard-changes"):
            return "git_switch_discard"
        return None
    if sub == "restore":
        staged = "--staged" in rest or "S" in flags
        worktree = "--worktree" in rest or "W" in flags
        if _operands(rest, ("-s", "--source", "--pathspec-from-file")) and (worktree or not staged):
            return "git_restore_discard"
        return None
    if sub == "stash" and _operands(rest)[:1] in (["clear"], ["drop"]):
        return "git_stash_drop"
    return None
