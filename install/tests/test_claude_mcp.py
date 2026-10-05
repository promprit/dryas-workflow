import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import claude_mcp

CD = Path("/x/.claude")
PYX = ["/usr/bin/python3", "-X", "utf8"]
PATH = "/x/.claude/jev/jev_mcp.py"
ADD = ["claude", "mcp", "add", "--scope", "user", "jev", "--"] + PYX + [PATH]
REMOVE = ["claude", "mcp", "remove", "--scope", "user", "jev"]


class ClaudeMcpTest(unittest.TestCase):
    def go(self, get, rec=None, dry=False):
        calls = []
        rec = rec if rec is not None else {"mcp": []}
        out = io.StringIO()
        with redirect_stdout(out):
            claude_mcp.ensure_jev(CD, PYX, rec, lambda a, cwd=None: calls.append(a) or 0,
                                  lambda a, *k, **kw: get, dry)
        return calls, rec, out.getvalue()

    def test_fresh_adds(self):
        calls, rec, _ = self.go((1, ""))
        self.assertEqual(calls, [ADD])
        self.assertIn("jev", rec["mcp"])
        self.assertEqual(rec["mcp_specs"]["jev"], PYX + [PATH])

    def test_outdated_ours_is_replaced(self):
        calls, rec, _ = self.go((0, "jev:\n  Command: /usr/bin/python3 /x/.claude/jev/jev_mcp.py\n"))
        self.assertEqual(calls, [REMOVE, ADD])
        self.assertEqual(rec["mcp"].count("jev"), 1)

    def test_up_to_date_does_nothing(self):
        rec = {"mcp": ["jev"], "mcp_specs": {"jev": PYX + [PATH]}}
        calls, _, _ = self.go((0, "jev: /usr/bin/python3 -X utf8 /x/.claude/jev/jev_mcp.py"), rec)
        self.assertEqual(calls, [])

    def test_foreign_is_kept(self):
        calls, _, out = self.go((0, "jev: node /other/server.js"))
        self.assertEqual(calls, [])
        self.assertIn("kept your own jev MCP server (not managed by this installer)", out)

    def test_dry_run_runs_nothing(self):
        calls, _, out = self.go((1, ""), dry=True)
        self.assertEqual(calls, [])
        self.assertIn("would run", out)


if __name__ == "__main__":
    unittest.main()
