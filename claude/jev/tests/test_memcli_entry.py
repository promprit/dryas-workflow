import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MEMCLI = ROOT / "claude/jev/memcli.py"
CLOUD = ROOT / "tools/dryas_cloud.py"


def run(script, *args, **env):
    e = dict(os.environ, **env)
    return subprocess.run([sys.executable, "-X", "utf8", str(script)] + list(args), capture_output=True, text=True,
                          env=e, timeout=120)


class LeadingTokenTest(unittest.TestCase):
    """dryas.cmd forwards its whole line, so the entries drop one leading `memory` / `cloud` token."""

    def test_memcli_ignores_a_leading_memory(self):
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "m.db")
            a = run(MEMCLI, "--db", db, "stats")
            b = run(MEMCLI, "memory", "--db", db, "stats")
            self.assertEqual((a.returncode, b.returncode), (0, 0), a.stderr + b.stderr)
            self.assertEqual(a.stdout, b.stdout)

    def test_cloud_ignores_a_leading_cloud(self):
        with tempfile.TemporaryDirectory() as d:
            a = run(CLOUD, "check", "--repo", d)
            b = run(CLOUD, "cloud", "check", "--repo", d)
            self.assertEqual(a.returncode, b.returncode, a.stderr + b.stderr)
            self.assertEqual(a.stdout, b.stdout)
            self.assertNotIn("invalid choice", b.stderr)

    def test_only_one_token_is_dropped(self):
        p = run(CLOUD, "cloud", "cloud", "check")
        self.assertEqual(p.returncode, 2)
        self.assertIn("invalid choice", p.stderr)


if __name__ == "__main__":
    unittest.main()
