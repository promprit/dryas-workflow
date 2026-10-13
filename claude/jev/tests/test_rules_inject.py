import io
import itertools
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import rules_inject

TEMPLATE = os.path.join(os.path.dirname(HERE), "CLAUDE.md.template")


# outside the repo (installed copy of jev/tests) the plugin manifest is absent; in the repo a missing template must fail
@unittest.skipUnless(os.path.isfile(os.path.join(os.path.dirname(HERE), ".claude-plugin", "plugin.json")),
                     "not running from the repo checkout")
class RulesInjectTest(unittest.TestCase):
    def text(self):
        with open(TEMPLATE, encoding="utf-8") as f:
            return f.read()

    def test_all_on_keeps_pstack_block_without_markers(self):
        out = rules_inject.build(self.text(), [])
        self.assertNotIn("<!-- pstack-picks -->", out)
        self.assertNotIn(rules_inject.SKIP_LINE, out)
        self.assertIn("pstack", out)

    def test_pstack_off_drops_block_and_adds_skip_line(self):
        out = rules_inject.build(self.text(), ["pstack-picks"])
        self.assertNotIn("<!-- pstack-picks -->", out)
        self.assertIn(rules_inject.SKIP_LINE, out)
        self.assertNotIn("benchmark-checklist", out)

    def test_under_cap_for_every_combination(self):
        opt = ["jev", "ruflo", "superpowers", "design", "pstack-picks"]
        for n in range(len(opt) + 1):
            for off in itertools.combinations(opt, n):
                self.assertLess(len(rules_inject.build(self.text(), list(off))), 10000, off)

    def codex_text(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(HERE)), "codex", "AGENTS.md.template"), encoding="utf-8") as f:
            return f.read()

    def test_codex_resolves_root_and_adds_paths_line(self):
        out = rules_inject.build(self.codex_text(), [], "codex", "/p/root", "/usr/bin/python3")
        self.assertNotIn("{{", out)
        self.assertIn("/p/root/pstack/", out)
        self.assertIn(rules_inject.PATHS_LINE % ("/p/root", "/usr/bin/python3"), out)
        self.assertIn("$dryas:orchestrate", out)

    def test_codex_under_8k_for_every_combination(self):
        opt = ["jev", "ruflo", "superpowers", "design", "pstack-picks"]
        for n in range(len(opt) + 1):
            for off in itertools.combinations(opt, n):
                out = rules_inject.build(self.codex_text(), list(off), "codex", "/" + "x" * 200, "/" + "y" * 200)
                self.assertLess(len(out.encode("utf-8")), 8000, off)

    def test_harness_flag(self):
        self.assertEqual(rules_inject.harness(["--harness", "codex"]), "codex")
        self.assertEqual(rules_inject.harness([]), "claude")
        self.assertEqual(rules_inject.harness(["--harness"]), "claude")

    def test_claude_output_has_no_paths_line(self):
        self.assertNotIn("Dryas paths:", rules_inject.build(self.text(), []))

    def test_main_emits_sessionstart_json(self):
        with tempfile.TemporaryDirectory() as d:
            loc = os.path.join(d, "chain.local.json")
            with open(loc, "w") as f:
                json.dump({"off": ["pstack-picks"]}, f)
            with mock.patch.dict(os.environ, {"JEV_CHAIN_LOCAL": loc}), \
                    mock.patch("sys.stdin", io.StringIO('{"source":"startup"}')), \
                    mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                rules_inject.main([])
        hso = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "SessionStart")
        self.assertIn(rules_inject.SKIP_LINE, hso["additionalContext"])

    def test_main_silent_when_template_missing(self):
        with mock.patch.object(rules_inject, "HERE", "/no/such/dir/jev"), \
                mock.patch("sys.stdin", io.StringIO("{}")), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            rules_inject.main([])
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
