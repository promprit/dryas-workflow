"""/tune for keyless users (owned core D): where the deciding judge and its shadow disagree (corpus candidates,
redacted patterns only, never file contents), and gate.allowlist proposals from local asks the user approved.

An ask was approved when its tool_use_id shows up in outcomes.jsonl (logged by gate_outcome.py after the call
ran). Deny decisions are never a source: overriding a deny is logged only by log_override."""
import json
import posixpath
import re
from collections import Counter
from typing import Any, Dict, List, Optional

import gate
import local_judge
import redact
import thresholds

TOP = 10
MAX_PATTERN = 80
_ALLOW = ("none", "skipped")
_PLAIN_WORD = re.compile(r"[A-Za-z0-9._+/-]+")
# The only heads /tune ever proposes: read-only tools with no argument that runs a command or writes a file.
# Left out on purpose: rg (--pre), fd (-x), bat (--pager), less/more (+!), sort (-o), uniq (OUTPUT), tree (-o),
# yq (-i), file (-C), and every multi-purpose tool (git, gh, tar, docker, npm, terraform, ...).
PROPOSABLE_HEADS = frozenset({"jq", "stat", "du", "df", "which", "cut", "tr", "basename", "dirname", "realpath",
                              "readlink", "column", "nl", "diff", "cmp", "comm", "grep", "exa", "eza"})


def pattern(rec: Dict[str, Any]) -> str:
    """A minimal, redacted pattern for a gate record: Bash head, or tool plus file suffix."""
    if rec.get("tool") == "Bash":
        return redact.redact(str(rec.get("head") or ""))[:MAX_PATTERN]
    tool = str(rec.get("tool") or "")
    rel = rec.get("rel")
    if isinstance(rel, list):
        rel = rel[0] if rel else None
    if not isinstance(rel, str) or not rel:
        return tool
    if rel == "<outside>":
        return tool + ":" + rel
    suffix = posixpath.splitext(posixpath.basename(rel))[1]
    return tool + ":" + suffix if suffix else tool


def _norm(decision: Any) -> str:
    return "allow" if decision in _ALLOW or decision is None else str(decision)


def disagreements(gate_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Counter = Counter()
    for r in gate_rows:
        if not isinstance(r, dict) or "shadow_decision" not in r:
            continue
        d, sd = _norm(r.get("decision")), _norm(r.get("shadow_decision"))
        if d != sd:
            counts[(pattern(r), d, sd, str(r.get("provider")), str(r.get("shadow_provider")))] += 1
    return [{"pattern": k[0], "decision": k[1], "shadow_decision": k[2], "provider": k[3], "shadow_provider": k[4],
             "count": n} for k, n in counts.most_common(TOP)]


def approved_asks(gate_rows: List[Dict[str, Any]], outcome_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Pattern -> count of local Bash asks whose tool_use_id ran (the user approved them)."""
    ran = {r["tool_use_id"] for r in outcome_rows if isinstance(r, dict) and isinstance(r.get("tool_use_id"), str)}
    out: Counter = Counter()
    for r in gate_rows:
        if isinstance(r, dict) and r.get("tool") == "Bash" and r.get("provider") == "local" \
                and r.get("decision") == "ask" and isinstance(r.get("tool_use_id"), str) and r["tool_use_id"] in ran:
            out[pattern(r)] += 1
    return dict(out)


def _proposable(c: str, current: List[str]) -> bool:
    words = c.split()
    if not words or not all(_PLAIN_WORD.fullmatch(w) for w in words):
        return False
    head = words[0]
    if head not in PROPOSABLE_HEADS or head in local_judge.ARG_JUDGED_HEADS or gate.allowlisted(c, current):
        return False
    # An allowlist entry bypasses the gate; validate refuses dangerous heads and danger/destructive patterns.
    return thresholds.validate("gate.allowlist", current + [c]) is None


def allowlist_proposal(approved: Dict[str, int], current: List[str], min_approvals: int) -> Optional[Dict[str, Any]]:
    ranked = sorted(approved.items(), key=lambda kv: (-kv[1], kv[0]))
    adds = [c for c, n in ranked if n >= min_approvals and _proposable(c, current)]
    if not adds:
        return None
    return {"key": "gate.allowlist", "old": current, "new": current + adds,
            "why": "You approved these local asks at least %d times each: %s. Review each one: it is allowlisted "
                   "for plain (metachar-free) use only." % (min_approvals, ", ".join(adds))}


def lines(rep: Dict[str, Any]) -> List[str]:
    d, a = rep["disagreements"], rep["approved"]
    return ["- Judge disagreements (deciding vs shadow): %d patterns" % len(d),
            "- Approved local asks: %d (%d patterns)" % (sum(a.values()), len(a)),
            "CORPUS_CANDIDATES_JSON: " + json.dumps(d)]
