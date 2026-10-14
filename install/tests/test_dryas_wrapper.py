import os
import subprocess
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[2] / "claude" / "bin"


class WrapperTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX wrapper")
    def test_memory_stats_runs(self):
        db = Path(tempfile.mkdtemp()) / "d.db"
        r = subprocess.run(["sh", str(BIN / "dryas"), "memory", "--db", str(db), "stats"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX wrapper")
    def test_unknown_word_prints_usage(self):
        r = subprocess.run(["sh", str(BIN / "dryas"), "nope"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage:", r.stdout + r.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows wrapper")
    def test_cmd_memory_stats_runs(self):
        db = Path(tempfile.mkdtemp()) / "d.db"
        r = subprocess.run(["cmd", "/c", str(BIN / "dryas.cmd"), "memory", "--db", str(db), "stats"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_both_name_memcli(self):
        for n, needle in (("dryas", "jev/memcli.py"), ("dryas.cmd", "jev\\memcli.py")):
            self.assertIn(needle, (BIN / n).read_text(encoding="utf-8"))

    def test_cmd_python_lookup_order(self):
        t = (BIN / "dryas.cmd").read_text(encoding="utf-8")
        order = [t.index(n) for n in ("DRYAS_PY", "py -3", "python3", "\npython -X")]
        self.assertEqual(order, sorted(order))


if __name__ == "__main__":
    unittest.main()
