# claude/jev/tests/test_chain_local.py
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chain

STAGES = [{"name": "scope-lock", "cmd": ["$PY", "$CD/jev/scope_lock.py"], "timeout": 3},
          {"name": "flowobserve", "enabled": False, "cmd": ["$PY", "$HOME/x.py"], "timeout": 1}]


class ApplyLocalTest(unittest.TestCase):
    def test_overrides_only_enabled_and_timeout_by_name(self):
        local = {"stages": {"pretool": {"flowobserve": {"enabled": True, "timeout": 9, "cmd": ["evil"]},
                                        "scope-lock": {"match": ".*"}}}}
        out = chain.apply_local(STAGES, "pretool", local)
        self.assertEqual(out[1]["enabled"], True)
        self.assertEqual(out[1]["timeout"], 9)
        self.assertEqual(out[1]["cmd"], ["$PY", "$HOME/x.py"])
        self.assertNotIn("match", out[0])
        self.assertFalse(STAGES[1]["enabled"])  # inputs untouched

    def test_bad_types_ignored(self):
        local = {"stages": {"pretool": {"flowobserve": {"enabled": "yes", "timeout": -1}}}}
        out = chain.apply_local(STAGES, "pretool", local)
        self.assertEqual((out[1]["enabled"], out[1]["timeout"]), (False, 1))

    def test_other_event_untouched(self):
        local = {"stages": {"prompt": {"flowobserve": {"enabled": True}}}}
        self.assertFalse(chain.apply_local(STAGES, "pretool", local)[1]["enabled"])


class LoadLocalTest(unittest.TestCase):
    def test_missing_is_empty_and_silent(self):
        with mock.patch.dict(os.environ, {"JEV_CHAIN_LOCAL": os.path.join(tempfile.mkdtemp(), "none.json")}), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(chain.load_local(), {})
            self.assertEqual(err.getvalue(), "")

    def test_broken_warns_once_and_falls_back(self):
        p = os.path.join(tempfile.mkdtemp(), "chain.local.json")
        with open(p, "w") as f:
            f.write("{nope")
        with mock.patch.dict(os.environ, {"JEV_CHAIN_LOCAL": p}), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(chain.load_local(), {})
            self.assertEqual(err.getvalue().count("\n"), 1)
            self.assertIn("chain.local.json", err.getvalue())


class PlaceholderTest(unittest.TestCase):
    def test_cd_py_data_root_resolved(self):
        env = {"CLAUDE_PLUGIN_ROOT": "/plug", "DRYAS_PY": "/py", "DRYAS_DATA_ROOT": "/data"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(chain._expand("$CD/jev/x.py"), "/plug/jev/x.py")
            self.assertEqual(chain._expand("${PY}"), "/py")
            self.assertEqual(chain._expand("$DRYAS_DATA_ROOT/ruflo/helpers/h.cjs"), "/data/ruflo/helpers/h.cjs")

    def test_unresolved_is_none(self):
        self.assertIsNone(chain._expand("$NOT_A_VAR_XYZ/x"))

    def test_similar_names_not_matched(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": "/plug", "DRYAS_PY": "/py"}):
            self.assertIsNone(chain._expand("$CDPATH/x"))
            self.assertIsNone(chain._expand("$PYTHONPATH/x"))

    def test_unresolved_stage_skipped_and_logged(self):
        logs = tempfile.mkdtemp()
        st = {"name": "weird", "cmd": ["$NOT_A_VAR_XYZ/x"], "timeout": 1}
        with mock.patch.dict(os.environ, {"JEV_LOG_DIR": logs}):
            self.assertEqual(chain._run(st, "{}"), (None, "", ""))
        with open(os.path.join(logs, "chain.jsonl"), encoding="utf-8") as f:
            rec = json.loads(f.readline())
        self.assertEqual((rec["stage"], rec["skipped"]), ("weird", "unresolved placeholder"))


class LoadStagesMergesLocalTest(unittest.TestCase):
    def test_load_stages_applies_local(self):
        d = tempfile.mkdtemp()
        cfg, loc = os.path.join(d, "chain.json"), os.path.join(d, "chain.local.json")
        with open(cfg, "w") as f:
            json.dump({"pretool": STAGES}, f)
        with open(loc, "w") as f:
            json.dump({"stages": {"pretool": {"flowobserve": {"enabled": True}}}}, f)
        with mock.patch.dict(os.environ, {"JEV_CHAIN_CONFIG": cfg, "JEV_CHAIN_LOCAL": loc}):
            self.assertTrue(chain.load_stages("pretool")[1]["enabled"])


if __name__ == "__main__":
    unittest.main()
