"""tools/compare_lens.py: parse headless results and judge the lens release gate (spec §8)."""
import json
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import compare_lens as cl  # noqa: E402


def run(ms, tokens, prompts=0):
    return {"ms": ms, "tokens": tokens, "prompts": prompts}


class CompareLensTest(unittest.TestCase):
    def test_parse_result(self):
        out = json.dumps({"type": "result", "duration_ms": 41000, "permission_denials": [{"tool_name": "Artifact"}],
                          "usage": {"input_tokens": 10, "output_tokens": 2000, "cache_creation_input_tokens": 300,
                                    "cache_read_input_tokens": 9000}})
        self.assertEqual(cl.parse_result(out), {"ms": 41000, "tokens": 11310, "prompts": 1})

    def test_parse_result_rejects_non_result(self):
        with self.assertRaises(ValueError):
            cl.parse_result("not json")

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

    def test_verdict_uses_median(self):
        old = [run(60000, 50000)] * 3
        ok, _ = cl.verdict(old, [run(60000, 50000), run(60000, 50000), run(900000, 900000)])
        self.assertTrue(ok)

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
