#!/usr/bin/env python3
"""Is the lens release no worse than the previous release on design tasks? Spec 2026-10-28-lens-design.md §8.

  python3 tools/compare_lens.py --old DIR [--runs N] [--claude PATH]   exit 0 PASS, 1 FAIL, 2 setup error

Runs each prompt in tools/fixtures/lens/ headless (`claude -p ... --output-format json --plugin-dir <side>/claude`)
on the old release checkout (DIR) and on this checkout, sides alternating per run, in a fresh temp folder each time.
PASS when, per prompt, the median added time is at most 90 s, the median added tokens at most 25k, and the new side
never has more permission prompts (denials in -p mode) than the old. Run it from a session where the account's own
Dryas plugin is not also loaded, or both copies run; the release step says how.
"""
import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tools/fixtures/lens"
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def parse_result(stdout: str) -> Dict[str, int]:
    try:
        d = json.loads(stdout)
    except ValueError as e:
        raise ValueError("not a claude -p json result: %s" % e)
    if not isinstance(d, dict) or "duration_ms" not in d:
        raise ValueError("not a claude -p json result")
    usage = d.get("usage") or {}
    return {"ms": int(d["duration_ms"]), "tokens": sum(int(usage.get(k) or 0) for k in TOKEN_KEYS),
            "prompts": len(d.get("permission_denials") or [])}


def verdict(old: List[Dict[str, int]], new: List[Dict[str, int]], max_ms: int = 90000,
            max_tokens: int = 25000) -> Tuple[bool, List[str]]:
    med = lambda runs, k: statistics.median(r[k] for r in runs)
    dms, dtok = med(new, "ms") - med(old, "ms"), med(new, "tokens") - med(old, "tokens")
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
    lines.append("time +%d ms, tokens +%d" % (dms, dtok))
    return ok, lines


def build_cmd(claude: str, side: Path, prompt: str) -> List[str]:
    return [claude, "-p", prompt, "--output-format", "json", "--plugin-dir", str(side / "claude")]


def run_once(claude: str, side: Path, prompt: str) -> Dict[str, int]:
    with tempfile.TemporaryDirectory() as cwd:
        p = subprocess.run(build_cmd(claude, side, prompt), cwd=cwd, capture_output=True, text=True, timeout=900)
    return parse_result(p.stdout)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--old", required=True, type=Path, help="checkout of the previous release (e.g. v2.5.0)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--claude", default="claude")
    a = ap.parse_args(argv)
    if not (a.old / "claude").is_dir():
        print("no claude/ in %s" % a.old, file=sys.stderr)
        return 2
    ok = True
    for f in sorted(FIXTURES.glob("*.md")):
        prompt = f.read_text(encoding="utf-8").strip()
        old, new = [], []
        for i in range(a.runs):
            for side, out in ((a.old, old), (REPO, new)) if i % 2 == 0 else ((REPO, new), (a.old, old)):
                out.append(run_once(a.claude, side, prompt))
        good, lines = verdict(old, new)
        ok = ok and good
        print("%s: %s" % (f.stem, "PASS" if good else "FAIL"))
        for l in lines:
            print("  " + l)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
