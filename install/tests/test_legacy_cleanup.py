import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dryas_install as di
import plugin_setup as ps


class LegacyTest(unittest.TestCase):
    def setUp(self):
        self.cd = Path(tempfile.mkdtemp())
        (self.cd / "plugins").mkdir()
        (self.cd / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"plugins": {"ruflo-core@ruflo": [{}], "ruflo-swarm@ruflo": [{}], "impeccable@impeccable": [{}]}}),
            encoding="utf-8")
        self.root = Path(tempfile.mkdtemp())
        (self.root / "ruflo").mkdir()
        p = mock.patch.object(ps, "data_root", lambda: self.root)
        p.start()
        self.addCleanup(p.stop)

    def test_each_item_listed_and_confirmed(self):
        with mock.patch("shutil.which", lambda n: "/usr/bin/" + n):
            items = ps.legacy_items(self.cd, {}, last_account=True)
        labels = [i[0] for i in items]
        self.assertTrue(any("ruflo-core@ruflo" in l for l in labels))
        self.assertTrue(any("ruflo-swarm@ruflo" in l for l in labels))
        self.assertFalse(any("impeccable" in l for l in labels))
        self.assertTrue(any("npm uninstall -g ruflo" in l for l in labels))
        self.assertTrue(any(str(self.root / "ruflo") in l for l in labels))
        asked = []
        with mock.patch.object(di, "confirm", lambda q: asked.append(q) or False), \
                mock.patch.object(di, "run", side_effect=AssertionError("ran unasked")):
            self.assertEqual(ps.run_legacy(items, yes=False), 0)
        self.assertEqual(len(asked), len(items))
        self.assertTrue((self.root / "ruflo").exists())  # never removed by default

    def test_not_last_account_keeps_npm_package(self):
        with mock.patch("shutil.which", lambda n: "/usr/bin/" + n):
            labels = [i[0] for i in ps.legacy_items(self.cd, {}, last_account=False)]
        self.assertFalse(any("npm" in l for l in labels))

    def test_yes_never_removes_dir(self):
        items = [("remove %s" % (self.root / "ruflo"), None, self.root / "ruflo")]
        self.assertEqual(ps.run_legacy(items, yes=True), 0)
        self.assertTrue((self.root / "ruflo").exists())

    def test_confirmed_removes_dir(self):
        items = [("remove %s" % (self.root / "ruflo"), None, self.root / "ruflo")]
        with mock.patch.object(di, "confirm", lambda q: True):
            self.assertEqual(ps.run_legacy(items, yes=False), 0)
        self.assertFalse((self.root / "ruflo").exists())

    def test_plugin_already_offered_by_extras_is_not_repeated(self):
        rec = {"thirdparty": [["claude", "plugin", "install", "ruflo-core@ruflo"]]}
        with mock.patch("shutil.which", lambda n: None):
            labels = [i[0] for i in ps.legacy_items(self.cd, rec, last_account=True)]
        self.assertFalse(any("ruflo-core@ruflo" in l for l in labels))
        self.assertTrue(any("ruflo-swarm@ruflo" in l for l in labels))
