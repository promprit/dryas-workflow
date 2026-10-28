"""tools/compare_lens.py: parse headless results and judge the lens release gate (spec §8)."""
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import compare_lens as cl  # noqa: E402


def run(ms, tokens, prompts=0, lens=True, cost=0.0):
    return {"ms": ms, "tokens": tokens, "prompts": prompts, "lens": lens, "cost": cost}


def result_json(**extra):
    d = {"type": "result", "duration_ms": 41000, "permission_denials": [{"tool_name": "Artifact"}],
         "usage": {"input_tokens": 10, "output_tokens": 2000, "cache_creation_input_tokens": 300,
                   "cache_read_input_tokens": 9000}}
    d.update(extra)
    return json.dumps(d)


class CompareLensTest(unittest.TestCase):
    def test_parse_result(self):
        out = result_json()
        self.assertEqual(cl.parse_result(out), {"ms": 41000, "tokens": 2310, "prompts": 1, "lens": False,
                                                "cost": 0.0})

    def test_parse_result_rejects_non_result(self):
        with self.assertRaises(ValueError):
            cl.parse_result("not json")

    def test_parse_result_is_error(self):
        with self.assertRaises(ValueError):
            cl.parse_result(result_json(is_error=True))

    def test_parse_result_detects_lens_block(self):
        text = "## Lens\n- Panel: design\n- Verdict: ship it\n"
        self.assertTrue(cl.parse_result(result_json(result=text))["lens"])
        self.assertFalse(cl.parse_result(result_json(result="- Verdict:ship"))["lens"])

    def test_parse_result_reads_cost(self):
        self.assertEqual(cl.parse_result(result_json(total_cost_usd=0.0123))["cost"], 0.0123)

    def test_verdict_limits(self):
        old = [run(60000, 50000)] * 3
        ok, lines = cl.verdict(old, [run(140000, 70000)] * 3)
        self.assertTrue(ok, lines)
        ok, lines = cl.verdict(old, [run(160000, 70000)] * 3)
        self.assertFalse(ok)
        self.assertTrue(any("time" in l for l in lines))
        ok, lines = cl.verdict(old, [run(60000, 80000)] * 3)
        self.assertFalse(ok)
        self.assertTrue(any("tokens" in l for l in lines))

    def test_verdict_prompts(self):
        ok, lines = cl.verdict([run(1, 1, 0)] * 3, [run(1, 1, 1)] * 3)
        self.assertFalse(ok)
        self.assertTrue(any("prompts" in l for l in lines))

    def test_verdict_requires_lens(self):
        old = [run(60000, 50000)] * 3
        ok, lines = cl.verdict(old, [run(60000, 50000, lens=True), run(60000, 50000, lens=False),
                                     run(60000, 50000)])
        self.assertFalse(ok)
        self.assertIn("FAIL lens: the new side did not produce a ## Lens block", lines)

    def test_verdict_reports_cost(self):
        ok, lines = cl.verdict([run(1, 1, cost=0.0)] * 3, [run(1, 1, cost=0.001)] * 3)
        self.assertTrue(ok, lines)
        self.assertIn("cost +$0.0010", lines)

    def test_verdict_uses_median(self):
        old = [run(60000, 50000)] * 3
        ok, _ = cl.verdict(old, [run(60000, 50000), run(60000, 50000), run(900000, 900000)])
        self.assertTrue(ok)

    def test_env_isolates_logs(self):
        env = cl.build_env(Path("/t"))
        self.assertEqual(env["JEV_LOG_DIR"], "/t/logs")
        self.assertEqual(env["JEV_THRESHOLDS"], "/t/thresholds.json")

    def test_run_once_uses_isolated_env_and_cwd(self):
        seen = {}

        def fake_run(cmd, **kw):
            seen.update(kw)
            return types.SimpleNamespace(returncode=0, stdout=result_json(), stderr="")

        with mock.patch.object(cl.subprocess, "run", side_effect=fake_run):
            cl.run_once("claude", Path("/old"), "hello", "design")
        self.assertEqual(seen["env"]["JEV_LOG_DIR"], str(Path(seen["cwd"]) / "logs"))

    def test_run_once_nonzero_exit_is_run_error(self):
        fake = types.SimpleNamespace(returncode=1, stdout="", stderr="boom")
        with mock.patch.object(cl.subprocess, "run", return_value=fake):
            with self.assertRaises(cl.RunError) as ctx:
                cl.run_once("claude", Path("/old"), "hello", "design")
        self.assertIn("/old", str(ctx.exception))
        self.assertIn("design", str(ctx.exception))

    def test_run_once_timeout_is_run_error(self):
        with mock.patch.object(cl.subprocess, "run", side_effect=subprocess.TimeoutExpired("claude", 900)):
            with self.assertRaises(cl.RunError):
                cl.run_once("claude", Path("/old"), "hello", "design")

    def test_failed_run_is_setup_error(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cl, "run_once", side_effect=cl.RunError("x")):
            (Path(tmp) / "claude").mkdir()
            self.assertEqual(cl.main(["--old", tmp, "--runs", "1"]), 2)

    def test_fixtures(self):
        names = sorted(p.name for p in (ROOT / "tools/fixtures/lens").glob("*.md"))
        self.assertEqual(names, ["both.md", "design.md", "product.md"])

    def test_build_cmd(self):
        cmd = cl.build_cmd("claude", Path("/old"), "hello")
        self.assertEqual(cmd[:3], ["claude", "-p", "hello"])
        self.assertIn("--output-format", cmd)
        self.assertEqual(cmd[cmd.index("--plugin-dir") + 1], "/old/claude")


if __name__ == "__main__":
    unittest.main()
