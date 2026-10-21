import sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "tools"))
import run_cmd


class ReaSelectTest(unittest.TestCase):
    def sel(self, argv, recorded=None):
        return run_cmd.select(run_cmd.parse(argv), recorded)

    def test_fresh_includes_rea(self):
        self.assertIn("rea", self.sel([]))

    def test_no_rea(self):
        self.assertNotIn("rea", self.sel(["--no-rea"]))

    def test_upgrade_without_record_keeps_it_off(self):
        self.assertNotIn("rea", self.sel([], ["core", "jev", "memory", "design"]))

    def test_with_rea_on_upgrade(self):
        self.assertIn("rea", self.sel(["--with-rea"], ["core", "jev", "memory"]))

    def test_upgrade_keeps_recorded(self):
        self.assertIn("rea", self.sel([], ["core", "jev", "memory", "rea"]))

    def test_with_and_no_contradict(self):
        with self.assertRaises(SystemExit):
            run_cmd.parse(["--with-rea", "--no-rea"])

    def test_constants(self):
        self.assertEqual(run_cmd.WITH, ("ruflo", "superpowers", "design", "rea"))
        self.assertEqual(run_cmd.NO_STAGES, ("rea",))
        self.assertIn("rea", run_cmd.OPTIONAL)

    def test_cloud_never_selects_rea(self):
        src = (HERE.parents[1] / "tools" / "dryas_cloud.py").read_text(encoding="utf-8")
        self.assertNotIn("--with-rea", src)
        self.assertNotIn('"rea"', src)


if __name__ == "__main__":
    unittest.main()
