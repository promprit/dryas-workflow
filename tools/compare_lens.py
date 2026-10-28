#!/usr/bin/env python3
"""Is the lens release no worse than the previous release on design tasks? Spec 2026-10-28-lens-design.md §8.

  python3 tools/compare_lens.py --old DIR [--runs N] [--claude PATH]   exit 0 PASS, 1 FAIL, 2 setup error

Runs each prompt in tools/fixtures/lens/ headless (`claude -p ... --output-format json --plugin-dir <side>/claude`)
on the old release checkout (DIR) and on this checkout, sides alternating per run, in a fresh temp folder each time.
PASS when, per prompt, the median added time is at most 90 s, the median added tokens at most 25k, the new side
never has more permission prompts (denials in -p mode) than the old, and every new-side run produced a ## Lens block.
Prompts are counted as permission_denials in -p mode: a tool that would ask interactively shows up only when it is
denied there. Run logs go to a temp JEV_LOG_DIR, never ~/.dryas/jev/logs. Cost is printed for information only.
Run it from a session where the account's own Dryas plugin is not also loaded, or both copies run; the release step
says how.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tools/fixtures/lens"
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens")
LENS_LINE = re.compile(r"^- Verdict: ", re.M)


class RunError(Exception):
    """A headless run failed: a setup error, not a verdict on the release."""


def build_env(tmp: Path) -> dict:
    return {**os.environ, "JEV_LOG_DIR": str(tmp / "logs"), "JEV_THRESHOLDS": str(tmp / "thresholds.json")}


def parse_result(stdout: str) -> Dict[str, object]:
    try:
        d = json.loads(stdout)
    except ValueError as e:
        raise ValueError("not a claude -p json result: %s" % e)
    if not isinstance(d, dict) or "duration_ms" not in d:
        raise ValueError("not a claude -p json result")
    if d.get("is_error"):
        raise ValueError("claude reported an error: %s" % str(d.get("result", ""))[:200])
    usage = d.get("usage") or {}
    return {"ms": int(d["duration_ms"]), "tokens": sum(int(usage.get(k) or 0) for k in TOKEN_KEYS),
            "prompts": len(d.get("permission_denials") or []),
            "lens": LENS_LINE.search(str(d.get("result") or "")) is not None,
            "cost": float(d.get("total_cost_usd") or 0)}


def verdict(old: List[Dict[str, object]], new: List[Dict[str, object]], max_ms: int = 90000,
            max_tokens: int = 25000) -> Tuple[bool, List[str]]:
    med = lambda runs, k: statistics.median(r[k] for r in runs)
    dms, dtok = med(new, "ms") - med(old, "ms"), med(new, "tokens") - med(old, "tokens")
    dcost = med(new, "cost") - med(old, "cost")
    lines, ok = [], True
    if dms > max_ms:
        ok = False
        lines.append("FAIL time: +%d ms median (limit %d)" % (dms, max_ms))
    if dtok > max_tokens:
        ok = False
        lines.append("FAIL tokens: +%d median (limit %d)" % (dtok, max_tokens))
    if max(r["prompts"] for r in new) > max(r["prompts"] for r in old):
        ok = False
        lines.append("FAIL prompts: new side asked more often than the old one")
    if not all(r["lens"] for r in new):
        ok = False
        lines.append("FAIL lens: the new side did not produce a ## Lens block")
    lines.append("time +%d ms, tokens +%d" % (dms, dtok))
    lines.append("cost %s$%.4f" % ("+" if dcost >= 0 else "-", abs(dcost)))
    return ok, lines


def build_cmd(claude: str, side: Path, prompt: str) -> List[str]:
    return [claude, "-p", prompt, "--output-format", "json", "--plugin-dir", str(side / "claude")]


def run_once(claude: str, side: Path, prompt: str, name: str) -> Dict[str, object]:
    where = "side %s, fixture %s" % (side, name)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            p = subprocess.run(build_cmd(claude, side, prompt), cwd=tmp, env=build_env(Path(tmp)),
                               capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            raise RunError("timed out (900 s): %s" % where)
        if p.returncode != 0:
            raise RunError("claude exited %d: %s; stderr: %s" % (p.returncode, where, p.stderr.strip()[:200]))
        try:
            return parse_result(p.stdout)
        except ValueError as e:
            raise RunError("%s: %s" % (where, e))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--old", required=True, type=Path, help="checkout of the previous release (e.g. v2.5.0)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--claude", default="claude")
    a = ap.parse_args(argv)
    if a.runs < 1:
        print("--runs must be at least 1", file=sys.stderr)
        return 2
    a.old = a.old.resolve()
    if not (a.old / "claude").is_dir():
        print("no claude/ in %s" % a.old, file=sys.stderr)
        return 2
    ok = True
    try:
        for f in sorted(FIXTURES.glob("*.md")):
            prompt = f.read_text(encoding="utf-8").strip()
            old, new = [], []
            for i in range(a.runs):
                for side, out in ((a.old, old), (REPO, new)) if i % 2 == 0 else ((REPO, new), (a.old, old)):
                    out.append(run_once(a.claude, side, prompt, f.stem))
            good, lines = verdict(old, new)
            ok = ok and good
            print("%s: %s" % (f.stem, "PASS" if good else "FAIL"))
            for l in lines:
                print("  " + l)
    except RunError as e:
        print("setup error: %s" % e, file=sys.stderr)
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
