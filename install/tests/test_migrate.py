import json, os, shutil, sys, tempfile, time, unittest
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import migrate

REPO = HERE.parents[1]


def old_install(cd: Path, log_line: str, tune_value: float, flowobserve_on: bool):
    (cd / "jev" / "logs").mkdir(parents=True)
    (cd / "jev" / "handoff").mkdir()
    (cd / "jev" / "logs" / "calls.jsonl").write_text(log_line + "\n", encoding="utf-8")
    (cd / "jev" / "handoff" / "proj-abc.md").write_text("h\n", encoding="utf-8")
    shipped = json.loads((REPO / "claude" / "jev" / "thresholds.json").read_text(encoding="utf-8"))
    shipped["gate"]["min_confidence"] = tune_value
    (cd / "jev" / "thresholds.json").write_text(json.dumps(shipped), encoding="utf-8")
    chain = json.loads((REPO / "claude" / "jev" / "chain.json").read_text(encoding="utf-8"))
    for st in chain["pretool"] + chain["prompt"]:
        if st["name"] == "flowobserve":
            st["enabled"] = flowobserve_on
    (cd / "jev" / "chain.json").write_text(json.dumps(chain), encoding="utf-8")
    (cd / ".dryas-installed.json").write_text(json.dumps({
        "components": ["core", "jev"], "files": {}, "dirs": [], "claude_md": True, "mcp": [],
        "settings": {"env": {}, "allow": [], "deny": [], "hooks": [["PreToolUse", "*", "x/jev/chain.py pretool"]], "top": {}},
        "settings_backup": None}), encoding="utf-8")


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.t), True)
        self.root = self.t / "dryas"
        self.a, self.b = self.t / "a", self.t / "b"
        self.ran = []
        p = mock.patch.object(migrate.di, "run", lambda argv, cwd=None, env=None: self.ran.append((argv, env)) or 0)
        p.start()
        self.addCleanup(p.stop)
        e = mock.patch.dict(os.environ, {"HOME": str(self.t / "home"), "USERPROFILE": str(self.t / "home"),
                                         "DRYAS_DATA_ROOT": str(self.root)})
        e.start()
        self.addCleanup(e.stop)

    def test_detects_copy_install_only(self):
        self.a.mkdir()
        self.assertFalse(migrate.is_copy_install(self.a))
        old_install(self.a, '{"x":1}', 0.8, True)
        self.assertTrue(migrate.is_copy_install(self.a))
        # a Codex-only copy (no CLAUDE.md block, no chain hook, no jev MCP) is not a Claude install
        rec = json.loads((self.a / ".dryas-installed.json").read_text())
        rec.update(claude_md=False, settings={"env": {}, "allow": [], "deny": [], "hooks": [], "top": {}})
        (self.a / ".dryas-installed.json").write_text(json.dumps(rec))
        self.assertFalse(migrate.is_copy_install(self.a))

    def test_moves_state_and_keeps_only_real_overrides(self):
        old_install(self.a, '{"x":1}', 0.8, True)
        self.assertEqual(migrate.migrate(self.a, self.root), 0)
        self.assertEqual((self.root / "jev" / "logs" / "calls.jsonl").read_text(), '{"x":1}\n')
        self.assertTrue((self.root / "jev" / "handoff" / "proj-abc.md").exists())
        self.assertEqual(json.loads((self.root / "jev" / "thresholds.json").read_text()),
                         {"gate": {"min_confidence": 0.8}})
        self.assertFalse((self.a / ".dryas-installed.json").exists())  # old uninstall ran

    def test_stage_settings_carried(self):
        old_install(self.a, '{"x":1}', 0.8, True)
        migrate.migrate(self.a, self.root)
        loc = json.loads((self.root / "chain.local.json").read_text())
        self.assertTrue(loc["stages"]["pretool"]["flowobserve"]["enabled"])

    def test_second_account_appends_logs_and_keeps_newer_thresholds(self):
        old_install(self.a, '{"a":1}', 0.8, False)
        old_install(self.b, '{"b":2}', 0.9, False)
        migrate.migrate(self.a, self.root)
        os.utime(str(self.b / "jev" / "thresholds.json"), (time.time() + 60,) * 2)
        migrate.migrate(self.b, self.root)
        self.assertEqual((self.root / "jev" / "logs" / "calls.jsonl").read_text(), '{"a":1}\n{"b":2}\n')
        self.assertEqual(json.loads((self.root / "jev" / "thresholds.json").read_text())["gate"]["min_confidence"], 0.9)

    def test_second_run_noop(self):
        old_install(self.a, '{"x":1}', 0.8, True)
        migrate.migrate(self.a, self.root)
        before = (self.root / "jev" / "logs" / "calls.jsonl").read_text()
        self.assertFalse(migrate.is_copy_install(self.a))
        self.assertEqual(migrate.migrate(self.a, self.root), 0)
        self.assertEqual((self.root / "jev" / "logs" / "calls.jsonl").read_text(), before)

    def test_local_doc_copied_never_overwritten(self):
        old_install(self.a, '{"a":1}', 0.8, False)
        old_install(self.b, '{"b":2}', 0.8, False)
        for cd, text in ((self.a, "mine A\n"), (self.b, "mine B\n")):
            (cd / "docs").mkdir()
            (cd / "docs" / "dryas-local.md").write_text(text, encoding="utf-8")
        migrate.migrate(self.a, self.root)
        migrate.migrate(self.b, self.root)
        self.assertEqual((self.root / "docs" / "dryas-local.md").read_text(encoding="utf-8"), "mine A\n")
        self.assertEqual((self.a / "docs" / "dryas-local.md").read_text(encoding="utf-8"), "mine A\n")  # original kept

    def test_old_mcp_removed_from_that_config_dir(self):
        old_install(self.a, '{"a":1}', 0.8, False)
        rec = json.loads((self.a / ".dryas-installed.json").read_text())
        rec["mcp"] = ["jev"]
        (self.a / ".dryas-installed.json").write_text(json.dumps(rec))
        migrate.migrate(self.a, self.root)
        rm = [(argv, env) for argv, env in self.ran if argv[:3] == ["claude", "mcp", "remove"]]
        self.assertEqual(len(rm), 1)
        self.assertEqual(rm[0][1]["CLAUDE_CONFIG_DIR"], str(self.a))

    def test_malformed_settings_stops_before_copying(self):
        old_install(self.a, '{"a":1}', 0.8, True)
        (self.a / "settings.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(migrate.migrate(self.a, self.root), 1)
        self.assertFalse(self.root.exists())
        self.assertTrue((self.a / ".dryas-installed.json").exists())

    def test_failed_uninstall_rerun_does_not_merge_twice(self):
        old_install(self.a, '{"a":1}', 0.8, True)
        with mock.patch.object(migrate.di, "uninstall", lambda cd: 1):
            self.assertEqual(migrate.migrate(self.a, self.root), 1)
        self.assertTrue(migrate.is_copy_install(self.a))
        self.assertEqual(migrate.migrate(self.a, self.root), 0)
        self.assertEqual((self.root / "jev" / "logs" / "calls.jsonl").read_text(), '{"a":1}\n')
        self.assertFalse((self.a / ".dryas-installed.json").exists())

    def test_append_adds_missing_newline(self):
        old_install(self.a, '{"a":1}', 0.8, False)
        (self.root / "jev" / "logs").mkdir(parents=True)
        (self.root / "jev" / "logs" / "calls.jsonl").write_text('{"z":0}', encoding="utf-8")
        migrate.migrate(self.a, self.root)
        self.assertEqual((self.root / "jev" / "logs" / "calls.jsonl").read_text(), '{"z":0}\n{"a":1}\n')


if __name__ == "__main__":
    unittest.main()
