import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scope_lock

PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"
SID = "sess-abcdef12"


@unittest.skipIf(os.name == "nt", "Claude's scratchpad is a POSIX path (SCRATCH_BASE is empty on Windows)")
class ScratchpadFilesTest(unittest.TestCase):
    def setUp(self):
        self.wt = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "w") as f:
            f.write(PLAN)
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ["1"]}, f)
        os.environ["JEV_LOG_DIR"] = tempfile.mkdtemp()
        os.environ.pop("DRYAS_HARNESS", None)
        self.base = os.path.realpath(tempfile.mkdtemp())
        self.pad = os.path.join(self.base, "-enc", SID, "scratchpad")
        os.makedirs(self.pad)
        p = mock.patch.object(scope_lock, "SCRATCH_BASE", self.base)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(os.environ.pop, "DRYAS_HARNESS", None)

    def ev(self, path, tool="Write"):
        return {"tool_name": tool, "tool_input": {"file_path": path, "content": "x"}, "cwd": self.wt,
                "agent_id": "a1", "session_id": SID}

    def decision(self, out):
        return out["hookSpecificOutput"]["permissionDecision"] if out else None

    def test_write_into_own_scratchpad_allowed(self):
        self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.pad, "probe.py"))))

    def test_other_session_or_lookalike_denied(self):
        for p in ("-enc/other-session-1234/scratchpad/x", "-enc/%s/scratchpad2/x" % SID):
            out = scope_lock.run(self.ev(os.path.join(self.base, p)))
            self.assertEqual(self.decision(out), "deny", p)

    def test_symlink_out_of_scratchpad_denied(self):
        link = os.path.join(self.pad, "link.ts")
        os.symlink(os.path.join(self.wt, "src", "other.ts"), link)
        self.assertEqual(self.decision(scope_lock.run(self.ev(link))), "deny")

    def test_off_claude_denied(self):
        with mock.patch.dict(os.environ, {"DRYAS_HARNESS": "opencode"}):
            out = scope_lock.run(self.ev(os.path.join(self.pad, "probe.py")))
        self.assertEqual(self.decision(out), "deny")

    def test_edit_and_multiedit_too(self):
        for tool in ("Edit", "MultiEdit"):
            self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.pad, "probe.py"), tool)))


if __name__ == "__main__":
    unittest.main()
