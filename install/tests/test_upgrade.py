import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import upgrade

REC = {"env": {"A": "1", "OLD": "x"}, "allow": ["Bash(old)", "keep"], "deny": [], "top": {"model": "opus"},
       "hooks": [["PreToolUse", "*", "/bin/sh old"], ["Stop", None, "same"]]}
FRAG = {"model": "opus", "env": {"A": "1"}, "permissions": {"allow": ["keep"]},
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "same"}]}]}}


class UpgradeTest(unittest.TestCase):
    def test_stale_settings(self):
        self.assertEqual(upgrade.stale_settings(REC, FRAG),
                         {"env": {"OLD": "x"}, "allow": ["Bash(old)"], "deny": [], "top": {},
                          "hooks": [["PreToolUse", "*", "/bin/sh old"]]})

    def test_changed_env_value_is_stale(self):
        self.assertEqual(upgrade.stale_settings({"env": {"A": "old"}}, {"env": {"A": "new"}})["env"], {"A": "old"})

    def test_subtract(self):
        st = upgrade.stale_settings(REC, FRAG)
        self.assertEqual(upgrade.subtract(REC, st),
                         {"env": {"A": "1"}, "allow": ["keep"], "deny": [], "top": {"model": "opus"},
                          "hooks": [["Stop", None, "same"]]})

    def test_has_any(self):
        self.assertFalse(upgrade.has_any(upgrade.stale_settings({}, {})))
        self.assertTrue(upgrade.has_any(upgrade.stale_settings(REC, FRAG)))

    def test_stale_files(self):
        self.assertEqual(upgrade.stale_files(["a", "b", "c"], {"a", "c"}), ["b"])


if __name__ == "__main__":
    unittest.main()
