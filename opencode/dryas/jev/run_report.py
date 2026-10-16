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
