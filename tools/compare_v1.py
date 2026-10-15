#!/usr/bin/env python3
"""Is this branch better than Dryas 1.0 for the user? Release gate for 2.3.x (Task 12 runs it).

  python3 tools/compare_v1.py [--v1 DIR] [--runs N]   exit 0 PASS, 1 FAIL, 2 when DIR/jev/chain.py is missing

Replays the regression corpus (claude/jev/tests/fixtures/scope_shell_corpus.jsonl: real executor shell commands)
as executor PreToolUse events through both hook chains, in a sandbox (temp logs and thresholds, no judge keys, the
local judge), against a fixture worktree with one active task (Scope src/**, tests/**). Sides alternate per run
(v1, new, v1, new, ...) so warmup and drift hit both. Pass when this branch
  - asks 0 times and no more than v1,
  - denies every corpus line marked "deny" and at least as many as v1,
  - denies no line marked "allow",
  - has a median per-event time no higher than v1's beyond the larger of the two run-to-run ranges.
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "claude" / "jev" / "tests" / "fixtures" / "scope_shell_corpus.jsonl"
PLAN = "## Task 1: corpus\nGoal: g\nScope:\n- src/**\n- tests/**\nDone:\n- d\n"


def verdict(v1: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    bad = []
    if new["asks"] > 0 or new["asks"] > v1["asks"]:
        bad.append("asks %d times (v1 %d); target 0" % (new["asks"], v1["asks"]))
    if new["denied_expected"] < new["denied_total_expected"] or new["denied_expected"] < v1["denied_expected"]:
        bad.append("denied %d of %d out-of-scope writes (v1 %d)" % (new["denied_expected"],
                                                                    new["denied_total_expected"], v1["denied_expected"]))
    if new["wrong_denies"]:
        bad.append("denied %d in-scope commands" % new["wrong_denies"])
    noise = max(v1["range_ms"][1] - v1["range_ms"][0], new["range_ms"][1] - new["range_ms"][0])
    if new["p50_ms"] > v1["p50_ms"] + noise:
        bad.append("median %.1f ms vs v1 %.1f ms (noise %.1f ms)" % (new["p50_ms"], v1["p50_ms"], noise))
    return bad


def _sandbox(tmp: Path) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if "KEY" not in k and not k.startswith(("JEV_", "DRYAS_"))}
    env.update(JEV_LOG_DIR=str(tmp / "logs"), JEV_THRESHOLDS=str(tmp / "thresholds.json"), HOME=str(tmp / "home"))
    (tmp / "home").mkdir(exist_ok=True)
    return env


def _one(chain: Path, event: Dict[str, Any], env: Dict[str, str]) -> (str, float):
    """The chain's decision, with a deny counted as "deny" only when the scope lock gave it ("scope lock:" reason);
    a gate deny of a risky command is "gate_deny" (a different rung, not a scope verdict). Asks of any stage count."""
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, "-X", "utf8", str(chain), "pretool"], input=json.dumps(event),
                       capture_output=True, text=True, env=env, timeout=60)
    ms = (time.perf_counter() - t0) * 1000
    try:
        out = json.loads(r.stdout)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        return "allow", ms
    d = out.get("permissionDecision", "allow")
    if d == "deny" and not str(out.get("permissionDecisionReason", "")).startswith("scope lock"):
        d = "gate_deny"
    return d, ms


def run(v1_dir: Path, runs: int) -> Dict[str, Dict[str, Any]]:
    cases = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]
    chains = {"v1": v1_dir / "jev" / "chain.py", "new": REPO / "claude" / "jev" / "chain.py"}
    tmp = Path(tempfile.mkdtemp())
    try:
        wt = tmp / "wt"
        (wt / ".orchestrate").mkdir(parents=True)
        (wt / ".orchestrate" / "PLAN.md").write_text(PLAN, encoding="utf-8")
        (wt / ".orchestrate" / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
        env = _sandbox(tmp)
        decisions: Dict[str, List[str]] = {"v1": [], "new": []}
        times: Dict[str, List[float]] = {"v1": [], "new": []}
        for r in range(runs):
            for side in ("v1", "new") if r % 2 == 0 else ("new", "v1"):
                per = []
                for c in cases:
                    ev = {"tool_name": "Bash", "tool_input": {"command": c["cmd"]}, "agent_id": "a1",
                          "cwd": str(wt / c["cwd"]), "session_id": "compare-v1"}
                    d, ms = _one(chains[side], ev, env)
                    per.append(ms)
                    if r == 0:
                        decisions[side].append(d)
                times[side].append(statistics.median(per))
        out = {}
        for side in ("v1", "new"):
            ds = decisions[side]
            out[side] = {
                "asks": sum(d == "ask" for d in ds),
                "denied_expected": sum(d == "deny" and c["expect"] == "deny" for d, c in zip(ds, cases)),
                "denied_total_expected": sum(c["expect"] == "deny" for c in cases),
                "wrong_denies": sum(d == "deny" and c["expect"] == "allow" for d, c in zip(ds, cases)),
                "p50_ms": statistics.median(times[side]),
                "range_ms": [min(times[side]), max(times[side])],
            }
        return out
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--v1", default=os.path.expanduser("~/.claude/plugins/cache/dryas-workflow/dryas/1.0.0"))
    p.add_argument("--runs", type=int, default=5)
    a = p.parse_args()
    v1_dir = Path(a.v1)
    if not (v1_dir / "jev" / "chain.py").is_file():
        sys.stderr.write("no Dryas 1.0 copy at %s (pass --v1)\n" % v1_dir)
        return 2
    if not CORPUS.is_file():
        sys.stderr.write("no regression corpus at %s\n" % CORPUS)
        return 2
    s = run(v1_dir, max(a.runs, 5))
    print("%-24s %10s %10s" % ("", "Dryas 1.0", "this"))
    for k in ("asks", "denied_expected", "denied_total_expected", "wrong_denies", "p50_ms"):
        print("%-24s %10s %10s" % (k, round(s["v1"][k], 1), round(s["new"][k], 1)))
    print("%-24s %10s %10s" % ("range_ms", s["v1"]["range_ms"], s["new"]["range_ms"]))
    bad = verdict(s["v1"], s["new"])
    print("PASS" if not bad else "FAIL: " + "; ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
