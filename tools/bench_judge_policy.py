#!/usr/bin/env python3
"""Time judge_policy.project_local at a VOID-like depth: cold (fresh cache) and cached. Spec 2026-10-19 §7.
  python3 tools/bench_judge_policy.py [--n 2000]"""
import argparse
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude" / "jev"))
import judge_policy  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=2000)
    n = p.parse_args().n
    tmp = tempfile.mkdtemp()
    try:
        start = os.path.join(tmp, "VOID", "Pilot", ".claude", "worktrees", "x", "src")
        os.makedirs(start)
        Path(tmp, "VOID", ".dryas-judge").write_text("local\n", encoding="utf-8")
        cold, warm = [], []
        for _ in range(n):
            judge_policy.clear_cache()
            t0 = time.perf_counter()
            judge_policy.project_local(start)
            cold.append((time.perf_counter() - t0) * 1e6)
            t0 = time.perf_counter()
            judge_policy.project_local(start)
            warm.append((time.perf_counter() - t0) * 1e6)
        c, w = statistics.median(cold), statistics.median(warm)
        print("cold p50 %.1f us, cached p50 %.2f us (n=%d)" % (c, w, n))
        # Unmarked folder: negatives are not cached, so every call walks the cwd, process folder and env chains.
        outside = os.path.join(tmp, "outside", "a", "b", "c", "d", "src")
        os.makedirs(outside)
        here, env = os.getcwd(), os.environ.pop("CLAUDE_PROJECT_DIR", None)
        os.chdir(outside)
        try:
            unmarked = []
            for _ in range(n):
                t0 = time.perf_counter()
                judge_policy.project_local(outside)
                unmarked.append((time.perf_counter() - t0) * 1e6)
        finally:
            os.chdir(here)
            if env is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = env
        print("unmarked uncached p50 %.1f us (n=%d)" % (statistics.median(unmarked), n))
        ok = c < 1000 and w < 10
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
