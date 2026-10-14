import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import dryas_install as di
import plugin_setup as ps
import run_cmd

P = run_cmd.parse
UP_1X = ["core", "jev", "ruflo", "design"]


class InstallFixTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        p = mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": str(self.root)})
        p.start()
        self.addCleanup(p.stop)

    def test_no_ruflo_upgrade_selects_dryas_memory(self):
        self.assertIn("memory", run_cmd.select(P(["--no-ruflo"]), UP_1X))
        self.assertNotIn("memory", run_cmd.select(P(["--no-ruflo", "--no-memory"]), UP_1X))
        self.assertNotIn("memory", run_cmd.select(P(["--no-ruflo", "--memory", "none"]), UP_1X))

    def test_explicit_judge_beats_key_and_conflicts_error(self):
        a = P(["--judge", "jev"])
        self.assertEqual(run_cmd.providers(a, run_cmd.select(a, None), None)["judge"], "jev")
        for argv in (["--judge", "local", "--openrouter-key", "k"], ["--memory", "ruflo", "--no-ruflo"],
                     ["--memory", "dryas", "--no-memory"], ["--memory", "none", "--with-ruflo"]):
            with self.assertRaises(SystemExit, msg=argv), redirect_stdout(io.StringIO()), \
                    mock.patch("sys.stderr", io.StringIO()):
                P(argv)

    def test_no_judge_flag_records_current_provider(self):
        (self.root / "jev").mkdir()
        (self.root / "jev" / "thresholds.json").write_text(json.dumps({"judge": {"provider": "jev"}}))
        sys.path.insert(0, str(run_cmd.HERE.parent / "claude" / "jev"))
        import thresholds
        want = thresholds.load()["judge"]["provider"]
        self.assertIsNotNone(want)
        pv = run_cmd.providers(P([]), ["core", "jev", "memory"], None)
        self.assertEqual(pv["judge"], want)

    def test_legacy_ruflo_folder_needs_last_account_and_no_other_ruflo_record(self):
        (self.root / "ruflo").mkdir()
        cd = Path(tempfile.mkdtemp())
        other = Path(tempfile.mkdtemp())
        (other / ps.RECORD).write_text(json.dumps({"components": ["core", "ruflo"]}))
        (self.root / "accounts.json").write_text(json.dumps({"claude_dirs": [str(other)]}))
        with mock.patch("shutil.which", lambda n: None):
            self.assertFalse(any(i[2] for i in ps.legacy_items(cd, {}, last_account=False)))
            self.assertFalse(any(i[2] for i in ps.legacy_items(cd, {}, last_account=True)))
            (other / ps.RECORD).write_text(json.dumps({"components": ["core"]}))
            self.assertFalse(any(i[2] for i in ps.legacy_items(cd, {}, last_account=False)))
            (self.root / "accounts.json").write_text(json.dumps({"claude_dirs": []}))
            self.assertTrue(any(i[2] for i in ps.legacy_items(cd, {}, last_account=True)))

    def test_yes_never_removes_folder_and_prints_command(self):
        d = self.root / "ruflo"
        d.mkdir()
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(ps.run_legacy([("remove %s" % d, None, d)], yes=True), 0)
        self.assertTrue(d.exists())
        self.assertIn("rm -rf", out.getvalue())
        self.assertIn(str(d), out.getvalue())

    def test_prompt_names_import_when_never_imported(self):
        d = self.root / "ruflo"
        d.mkdir()
        asked = []
        with mock.patch.object(di, "confirm", lambda q: asked.append(q) or False):
            ps.run_legacy([("remove %s" % d, None, d)], yes=False)
        self.assertIn("dryas memory import-ruflo", asked[0])
        db = sqlite3.connect(str(self.root / "dryas.db"))
        db.execute("CREATE TABLE memory (source TEXT)")
        db.execute("INSERT INTO memory VALUES ('ruflo')")
        db.commit()
        db.close()
        asked.clear()
        with mock.patch.object(di, "confirm", lambda q: asked.append(q) or False):
            ps.run_legacy([("remove %s" % d, None, d)], yes=False)
        self.assertNotIn("import-ruflo", asked[0])

    def test_docs_cut_over(self):
        t = (HERE.parent.parent / "docs" / "install.md").read_text(encoding="utf-8")
        self.assertIn("install.sh --judge jev --memory dryas", t)
        self.assertIn("--keep-extras", t)
        self.assertNotIn("opt-in", t.split("Legacy cleanup")[1].split("\n")[0])
        self.assertNotIn("when setup or uninstall offers it", t)
        self.assertNotIn("keeps its gates off until you pass `--judge local` or `--judge jev`", t)


if __name__ == "__main__":
    unittest.main()
