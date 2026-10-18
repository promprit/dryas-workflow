#!/usr/bin/env python3
"""Is this branch no worse than the previous release on the hooks every prompt and edit pays for? REL-1 for the
cross-account bridge (docs/specs/2026-10-18-cross-account-bridge-design.md §9.3).

  python3 tools/compare_release.py [--old DIR] [--runs N]   exit 0 PASS, 1 FAIL, 2 when DIR/jev/chain.py is missing

Replays synthetic UserPromptSubmit and PostToolUse events (made up here, no user data) through the old release's
hook chain and this checkout's, in a sandbox (temp logs, thresholds, data root and home, no judge keys, so the
local judge), with an empty bridge inbox. Sides alternate per run (old, new, new, old, ...) so warmup and drift hit
both. PASS when this branch asks 0 times and blocks 0 times and its median per-event time is no higher than the old
one's beyond the larger of the two run-to-run ranges. A second pass with one waiting message before each event
reports the delivery cost (informational: the old release cannot deliver).
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
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_v1

REPO = Path(__file__).resolve().parents[1]
SID = "00000000-0000-4000-8000-000000000001"
PROMPTS = ("fix the failing test in src/app.py", "explain how the hook chain orders its stages",
           "rename the helper and update its callers", "what does /tune report", "add a --dry-run flag",
           "review the diff before I merge", "why is the build slow", "write a test for the parser",
           "summarise the last commit", "continue")
POSTS = (("Bash", {"command": "ls"}), ("Bash", {"command": "git status"}), ("Bash", {"command": "pytest -q"}),
         ("Edit", {"file_path": "src/app.py"}), ("Write", {"file_path": "src/new.py"}))


def events(cwd: str) -> List[Dict[str, Any]]:
    base = {"session_id": SID, "cwd": cwd, "transcript_path": os.path.join(cwd, "t.jsonl")}
    out = [dict(base, hook_event_name="UserPromptSubmit", prompt=p, _kind="prompt") for p in PROMPTS]
    out += [dict(base, hook_event_name="PostToolUse", tool_name=t, tool_input=ti, tool_response={}, _kind="post")
            for t, ti in POSTS]
    out.append(dict(base, hook_event_name="PostToolUseFailure", tool_name="Bash",
                    tool_input={"command": "false"}, tool_response={}, _kind="post"))
    return out


def verdict(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    bad = []
    if new["asks"] or new["blocks"]:
        bad.append("asks %d, blocks %d; target 0" % (new["asks"], new["blocks"]))
    noise = max(old["range_ms"][1] - old["range_ms"][0], new["range_ms"][1] - new["range_ms"][0])
    if new["p50_ms"] > old["p50_ms"] + noise:
        bad.append("median %.1f ms vs old %.1f ms (noise %.1f ms)" % (new["p50_ms"], old["p50_ms"], noise))
    return bad


def _one(chain: Path, ev: Dict[str, Any], env: Dict[str, str]) -> Tuple[str, float]:
    payload = {k: v for k, v in ev.items() if k != "_kind"}
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, "-X", "utf8", str(chain), ev["_kind"]], input=json.dumps(payload),
                       capture_output=True, text=True, env=env, timeout=60)
    ms = (time.perf_counter() - t0) * 1000
    try:
        out = json.loads(r.stdout) if r.stdout.strip() else {}
    except ValueError:
        out = {}
    if out.get("decision") == "block":
        return "block", ms
    if (out.get("hookSpecificOutput") or {}).get("permissionDecision") == "ask":
        return "ask", ms
    return "ok", ms


def _seed(data: Path, n: int) -> None:
    box = data / "inbox" / SID
    box.mkdir(parents=True, exist_ok=True)
    msg = {"v": 1, "id": "m-%012x" % n, "ts": "2026-10-18T00:00:00Z",
           "from": {"sessionId": "00000000-0000-4000-8000-000000000002", "name": "peer", "account": ".claude-other",
                    "cwd": "/work"}, "to": SID, "reply_to": None, "text": "status update %d" % n}
    (box / ("%013d-%08x.json" % (n, n))).write_text(json.dumps(msg), encoding="utf-8")


def run(old_dir: Path, runs: int, seeded: bool = False) -> Dict[str, Dict[str, Any]]:
    chains = {"old": old_dir / "jev" / "chain.py", "new": REPO / "claude" / "jev" / "chain.py"}
    tmp = Path(tempfile.mkdtemp())
    try:
        env = compare_v1._sandbox(tmp)
        data = tmp / "data"
        data.mkdir()
        env.update(DRYAS_DATA_ROOT=str(data), JEV_CHAIN_LOCAL=str(tmp / "none.json"))
        evs = events(str(tmp))
        res = {s: {"asks": 0, "blocks": 0, "times": []} for s in chains}
        n = 0
        for r in range(runs):
            for side in ("old", "new") if r % 2 == 0 else ("new", "old"):
                per = []
                for ev in evs:
                    if seeded:
                        n += 1
                        _seed(data, n)
                    d, ms = _one(chains[side], ev, env)
                    per.append(ms)
                    res[side]["asks"] += d == "ask"
                    res[side]["blocks"] += d == "block"
                res[side]["times"].append(statistics.median(per))
        return {s: {"asks": v["asks"], "blocks": v["blocks"], "p50_ms": statistics.median(v["times"]),
                    "range_ms": [min(v["times"]), max(v["times"])]} for s, v in res.items()}
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


def main() -> int:
    cd = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    p = argparse.ArgumentParser()
    p.add_argument("--old", default=str(cd / "plugins" / "cache" / "dryas-workflow" / "dryas" / "2.3.2"))
    p.add_argument("--runs", type=int, default=6)
    a = p.parse_args()
    old = Path(a.old)
    if not (old / "jev" / "chain.py").is_file():
        sys.stderr.write("no old Dryas copy at %s (pass --old)\n" % old)
        return 2
    s = run(old, max(a.runs, 4))
    print("%-12s %12s %12s" % ("", old.name, "this"))
    for k in ("asks", "blocks", "p50_ms"):
        print("%-12s %12s %12s" % (k, round(s["old"][k], 1), round(s["new"][k], 1)))
    print("%-12s %12s %12s" % ("range_ms", [round(x, 1) for x in s["old"]["range_ms"]],
                               [round(x, 1) for x in s["new"]["range_ms"]]))
    d = run(old, 2, seeded=True)["new"]
    print("delivery (1 waiting message per event, informational): p50 %.1f ms" % d["p50_ms"])
    bad = verdict(s["old"], s["new"])
    print("PASS" if not bad else "FAIL: " + "; ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
