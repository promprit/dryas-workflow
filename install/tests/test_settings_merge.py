import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import settings_merge as sm

FRAG = {
    "model": "opus",
    "env": {"A": "1", "ROOT": "$DRYAS_DATA_ROOT/x", "K": "frag"},
    "permissions": {"allow": ["Bash(x)"], "deny": ["Skill(y)"]},
    "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "/bin/sh \"$HOME/h.sh\"", "timeout": 5}]}]},
}

class RenderTest(unittest.TestCase):
    def test_env_only(self):
        r = sm.render(FRAG, {"DRYAS_DATA_ROOT": "/d", "HOME": "/h"})
        self.assertEqual(r["env"]["ROOT"], "/d/x")
        self.assertEqual(r["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "/bin/sh \"$HOME/h.sh\"")

    def test_unmapped_fails(self):
        with self.assertRaises(ValueError):
            sm.render(FRAG, {"HOME": "/h"})

class MergeTest(unittest.TestCase):
    def setUp(self):
        self.frag = sm.render(FRAG, {"DRYAS_DATA_ROOT": "/d", "HOME": "/h"})

    def test_into_empty(self):
        merged, added, conflicts = sm.merge({}, self.frag)
        self.assertEqual(merged["env"]["A"], "1")
        self.assertEqual(merged["model"], "opus")
        self.assertEqual(added["hooks"], [["PreToolUse", "*", "/bin/sh \"$HOME/h.sh\""]])
        self.assertEqual(conflicts, [])

    def test_conflict_keeps_user_value_not_recorded(self):
        merged, added, conflicts = sm.merge({"env": {"K": "mine"}, "model": "sonnet"}, self.frag)
        self.assertEqual(merged["env"]["K"], "mine")
        self.assertNotIn("K", added["env"])
        self.assertEqual(merged["model"], "sonnet")
        self.assertNotIn("model", added["top"])
        self.assertIn("env.K", conflicts)
        self.assertIn("model", conflicts)

    def test_idempotent(self):
        once, _, _ = sm.merge({}, self.frag)
        twice, added2, _ = sm.merge(once, self.frag)
        self.assertEqual(once, twice)
        self.assertEqual(added2["hooks"], [])
        self.assertEqual(added2["allow"], [])

    def test_unmerge_exact_and_keeps_user_edits(self):
        user = {"env": {"MINE": "x"}, "permissions": {"allow": ["Bash(ls)"]},
                "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "user.sh"}]}]}}
        merged, added, _ = sm.merge(json.loads(json.dumps(user)), self.frag)
        merged["env"]["LATER"] = "y"
        merged["env"]["A"] = "user-changed"
        back = sm.unmerge(merged, added)
        self.assertEqual(back["env"], {"MINE": "x", "LATER": "y", "A": "user-changed"})
        self.assertEqual(back["permissions"]["allow"], ["Bash(ls)"])
        self.assertNotIn("deny", back["permissions"])
        self.assertEqual(back["hooks"], user["hooks"])
        self.assertNotIn("model", back)

class LoadTest(unittest.TestCase):
    def test_malformed_aborts(self):
        p = Path(tempfile.mkdtemp()) / "settings.json"
        p.write_text('{"env": {"A": 1,}}')
        with self.assertRaises(SystemExit) as cm:
            sm.load_settings(p)
        self.assertIn("nothing changed", str(cm.exception))

    def test_missing_is_empty(self):
        self.assertEqual(sm.load_settings(Path(tempfile.mkdtemp()) / "none.json"), {})

if __name__ == "__main__":
    unittest.main()
