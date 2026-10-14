"""Local judge: deterministic answers to the gate's questions (safe, risk), no network, same answer shape as
jev_client.judge. A short DANGER list is judged unsafe (the gate denies); a short DESTRUCTIVE list is judged
destructive (the gate asks); everything else gets no decision and falls through to the harness's permissions.
It never allows: the gate itself never allows. An internal error answers destructive, so the gate asks."""
import re
import shlex
from typing import Any, Dict, List, Optional, Pattern, Tuple

_SEG = re.compile(r"&&|\|\||[;|\n]")
_ROOTS = ("", "~", "$HOME", "${HOME}", "/Users", "/home", "/*", "~/*", "C:", "c:")
_PREFIX = ("sudo", "command", "nohup", "env", "doas")
_HOME_DIR = re.compile(r"^/(?:Users|home)/[^/]+/?$")

DANGER: List[Tuple[str, Pattern[str]]] = [
    ("fork_bomb", re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")),
    ("format_drive", re.compile(r"\bformat\s+[a-z]:", re.I)),
    ("del_drive", re.compile(r"\bdel\s+/s\s+/q\s+[a-z]:\\", re.I)),
    ("mkfs", re.compile(r"(?:^|[\s;&|(])mkfs(?:\.\w+)?\b")),
    ("dd_device", re.compile(r"\bdd\b[^;&|\n]*\bof=/dev/(?:sd|hd|nvme|disk|rdisk)")),
    ("overwrite_device", re.compile(r">\s*/dev/(?:sd|hd|nvme|disk|rdisk)\w*")),
    ("chmod_root", re.compile(r"\bchmod\s+-\w*R\w*\s+(?:0?777|a\+rwx)\s+/(?:\s|$)")),
]
DESTRUCTIVE: List[Tuple[str, Pattern[str]]] = [
    ("git_reset_hard", re.compile(r"\bgit\b[^;&|\n]*\breset\s+(?:\S+\s+)*--hard\b")),
    ("git_clean_force",  # -f without a dry run (-n, --dry-run)
     re.compile(r"\bgit\b[^;&|\n]*\bclean\b(?![^;&|\n]*\s(?:-\w*n\w*|--dry-run)\b)\s+(?:\S+\s+)*-\w*f")),
    ("git_push_force",  # --force, -f, or a +refspec; --force-with-lease is fine
     re.compile(r"\bgit\b[^;&|\n]*\bpush\b[^;&|\n]*(?:\s--force(?!-with-lease)\b|\s-\w*f\w*\b|\s\+\S)")),
    ("git_branch_delete", re.compile(r"\bgit\b[^;&|\n]*\bbranch\s+(?:\S+\s+)*-D\b")),
    ("sql_drop",  # needs an object name, so prose such as `echo "drop table"` does not match
     re.compile(r"\b(?:drop\s+(?:table|database|schema)|truncate\s+table)\s+(?:if\s+exists\s+)?[\"`\[]?\w", re.I)),
    ("pipe_to_shell", re.compile(r"\b(?:curl|wget)\b[^;&\n]*\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b")),
]


def _rm_root(cmd: str) -> bool:
    """A recursive rm whose target is /, ~, $HOME, a home root or one user's home (Ruflo pre-bash parity, plus
    home roots and /Users/<name>, /home/<name>)."""
    for seg in _SEG.split(cmd):
        try:
            words = shlex.split(seg)
        except ValueError:
            words = seg.split()
        while words and ("=" in words[0] or words[0] in _PREFIX):
            words = words[1:]
        if not words or words[0].rsplit("/", 1)[-1] != "rm":
            continue
        args = words[1:]
        flags = "".join(w[1:] for w in args if w.startswith("-") and not w.startswith("--"))
        if not ("r" in flags.lower() or "--recursive" in args):
            continue
        targets = [t for t in args if not t.startswith("-")]
        if any(t.rstrip("/") in _ROOTS or t in ("/", "/*") or _HOME_DIR.match(t) for t in targets):
            return True
    return False


def danger(cmd: str) -> Optional[str]:
    if _rm_root(cmd):
        return "rm_root"
    return next((name for name, rx in DANGER if rx.search(cmd)), None)


def destructive(cmd: str) -> Optional[str]:
    return next((name for name, rx in DESTRUCTIVE if rx.search(cmd)), None)


def _result(p_safe: float, risk: str, risk_conf: float, reasons: List[str]) -> Dict[str, Any]:
    return {"answers": {"safe": {"type": "noul", "value": p_safe, "confidence": max(p_safe, 1.0 - p_safe)},
                        "risk": {"type": "choice", "value": risk, "confidence": risk_conf, "probabilities": {}}},
            "reasons": reasons}


def gate_answers(tool: str, command: str = "", risky: bool = True) -> Dict[str, Any]:
    try:
        if tool == "Bash":
            hit = danger(command)
            if hit:
                return _result(0.02, "destructive", 0.95, ["danger:" + hit])
            hit = destructive(command)
            if hit:
                return _result(0.5, "destructive", 0.8, ["destructive:" + hit])
            if risky:
                return _result(0.8, "worth_a_look", 0.6, ["prescreen:risky"])
            return _result(0.9, "routine", 0.9, [])
        return _result(0.7, "worth_a_look", 0.6, ["file:sensitive_or_outside"])
    except Exception as e:
        return _result(0.5, "destructive", 0.8, ["error:" + type(e).__name__])
