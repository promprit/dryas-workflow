import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cloud_plan  # noqa: E402


class WindowsExecBitTest(unittest.TestCase):
    """Windows has no exec bit on disk: the copy takes it from the mode git records."""

    def test_windows_reads_the_exec_bit_from_git(self):
        with mock.patch.object(cloud_plan.os, "name", "nt"):
            self.assertTrue(cloud_plan._exec(ROOT / "claude/bin/dryas-py"))
            self.assertFalse(cloud_plan._exec(ROOT / "claude/jev/gate.py"))  # a shebang alone is not exec

    def test_outside_git_is_not_exec(self):
        with mock.patch.object(cloud_plan.os, "name", "nt"), \
                mock.patch.object(cloud_plan, "_git_execs", return_value=frozenset()):
            self.assertFalse(cloud_plan._exec(ROOT / "claude/bin/dryas-py"))


if __name__ == "__main__":
    unittest.main()
