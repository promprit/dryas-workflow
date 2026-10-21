import json, os, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import dryas_install as di
import rea_setup as rs

PLAN = json.dumps({"status": "planned", "plannedActions": [
    {"kind": "configure_client", "target": "/h/.claude-x/.claude.json"},
    {"kind": "install_skill", "target": "/h/.claude-x/skills/reverse-engineer-anything"}]})
DOCTOR_OK = json.dumps({"identity": {"skill": {"state": "aligned"}, "registrations": []}})
DOCTOR_BAD = json.dumps({"identity": {"skill": {"state": "missing"}}})


class Fake:
    """Stands in for dryas_install: records argv and env, answers from a table keyed by REA subcommand."""
    def __init__(self, setup_rc=0, plan=PLAN, doctor=DOCTOR_OK, answer=True):
        self.calls, self.setup_rc, self.plan, self.doctor, self.answer = [], setup_rc, plan, doctor, answer
        self.asked = []

    def capture(self, argv, input_text=None, env=None, timeout=None):
        self.calls.append((list(argv), env))
        if "--dry-run" in argv:
            return 0, self.plan
        if "doctor" in argv:
            return 0, self.doctor
        return 1, ""

    def run(self, argv, cwd=None, env=None):
        self.calls.append((list(argv), env))
        return self.setup_rc

    def confirm(self, prompt):
        self.asked.append(prompt)
        return self.answer


class ReaSetupTest(unittest.TestCase):
    def setUp(self):
        self.orig = (di.run, di.capture, di.confirm, rs.node_ok)
        rs.node_ok = lambda *a, **k: None

    def tearDown(self):
        di.run, di.capture, di.confirm, rs.node_ok = self.orig

    def use(self, fake):
        di.run, di.capture, di.confirm = fake.run, fake.capture, fake.confirm
        return fake

    def test_node_versions(self):
        node_ok = self.orig[3]
        which = lambda n: "/bin/" + n
        for v, ok in (("v22.18.0", False), ("v22.19.0", True), ("v23.4.0", False), ("v24.10.9", False),
                      ("v24.11.0", True), ("v25.1.0", False), ("v26.0.0", True), ("v30.2.1", True),
                      ("v20.11.0", False), ("garbage", False)):
            got = node_ok(capture=lambda argv, **k: (0, v + "\n"), which=which)
            self.assertEqual(got is None, ok, v)
        self.assertEqual(node_ok(capture=lambda argv, **k: (0, "v24.14.1"), which=lambda n: ""), rs.NODE_WARNING)
        self.assertEqual(node_ok(capture=lambda argv, **k: (1, ""), which=which), rs.NODE_WARNING)

    def test_argv(self):
        self.assertEqual(rs.setup_argv("claude_code"),
                         ["npx", "-y", "rea-agents@6.7.0", "setup", "--client", "claude_code", "--yes", "--format", "json"])
        self.assertEqual(rs.dry_run_argv("codex"),
                         ["npx", "-y", "rea-agents@6.7.0", "setup", "--client", "codex", "--dry-run", "--format", "json"])
        self.assertEqual(rs.doctor_argv("claude_code"),
                         ["npx", "-y", "rea-agents@6.7.0", "doctor", "--client", "claude_code", "--skill", "--format", "json"])
        self.assertEqual(rs.remove_argv("claude_code"), ["claude", "mcp", "remove", "--scope", "user", "rea"])
        self.assertEqual(rs.remove_argv("codex"), ["codex", "mcp", "remove", "rea"])

    def test_skill_dir_from_plan(self):
        self.assertEqual(rs.skill_dir_from_plan(PLAN), "/h/.claude-x/skills/reverse-engineer-anything")

    def test_skill_dir_missing_action(self):
        self.assertIsNone(rs.skill_dir_from_plan(json.dumps({"status": "planned", "plannedActions": []})))

    def test_skill_dir_garbage(self):
        self.assertIsNone(rs.skill_dir_from_plan("npm notice New minor version\n"))
        self.assertIsNone(rs.skill_dir_from_plan(""))
        self.assertIsNone(rs.skill_dir_from_plan(json.dumps({"plannedActions": [{"kind": "install_skill"}]})))
        self.assertIsNone(rs.skill_dir_from_plan(json.dumps(["x"])))

    def test_skill_dir_after_npm_noise(self):
        self.assertEqual(rs.skill_dir_from_plan("npm warn deprecated x\n" + PLAN),
                         "/h/.claude-x/skills/reverse-engineer-anything")

    def test_skill_state(self):
        self.assertEqual(rs.skill_state(DOCTOR_OK), "aligned")
        self.assertEqual(rs.skill_state(DOCTOR_BAD), "missing")
        self.assertIsNone(rs.skill_state("x"))

    def test_install_yes(self):
        f = self.use(Fake())
        env = {"CLAUDE_CONFIG_DIR": "/h/.claude-x"}
        entry = rs.install("claude_code", env, yes=True, dry_run=False)
        self.assertEqual(entry, {"version": "6.7.0", "client": "claude_code",
                                 "skill_dir": "/h/.claude-x/skills/reverse-engineer-anything"})
        self.assertEqual(f.asked, [])
        argvs = [c[0] for c in f.calls]
        self.assertEqual(argvs, [rs.dry_run_argv("claude_code"), rs.setup_argv("claude_code"), rs.doctor_argv("claude_code")])
        self.assertTrue(all(c[1] is env for c in f.calls))

    def test_install_asks_after_dry_run(self):
        f = self.use(Fake())
        self.assertIsNotNone(rs.install("claude_code", {}, yes=False, dry_run=False))
        self.assertEqual(f.asked, ["Install REA?"])
        self.assertEqual(f.calls[0][0], rs.dry_run_argv("claude_code"))

    def test_install_declined(self):
        f = self.use(Fake(answer=False))
        self.assertIsNone(rs.install("claude_code", {}, yes=False, dry_run=False))
        self.assertEqual([c[0] for c in f.calls], [rs.dry_run_argv("claude_code")])

    def test_install_dry_run_runs_nothing(self):
        f = self.use(Fake())
        self.assertIsNone(rs.install("claude_code", {}, yes=True, dry_run=True))
        self.assertEqual(f.calls, [])

    def test_install_setup_fails(self):
        self.use(Fake(setup_rc=3))
        self.assertIsNone(rs.install("claude_code", {}, yes=True, dry_run=False))

    def test_install_node_missing(self):
        f = self.use(Fake())
        rs.node_ok = lambda *a, **k: rs.NODE_WARNING
        self.assertIsNone(rs.install("claude_code", {}, yes=True, dry_run=False))
        self.assertEqual(f.calls, [])

    def test_install_doctor_not_aligned_still_records(self):
        self.use(Fake(doctor=DOCTOR_BAD))
        entry = rs.install("claude_code", {}, yes=True, dry_run=False)
        self.assertEqual(entry["skill_dir"], "/h/.claude-x/skills/reverse-engineer-anything")

    def test_install_no_skill_in_plan(self):
        self.use(Fake(plan="not json"))
        self.assertEqual(rs.install("claude_code", {}, yes=True, dry_run=False)["skill_dir"], None)

    def test_install_records_when_already_present(self):
        # REA installed by hand earlier: its dry run plans an update, setup is idempotent and succeeds
        plan = json.dumps({"status": "planned", "plannedActions": [
            {"kind": "install_skill", "operation": "update", "target": "/h/.claude/skills/reverse-engineer-anything"}]})
        self.use(Fake(plan=plan))
        self.assertEqual(rs.install("claude_code", {}, yes=True, dry_run=False)["skill_dir"],
                         "/h/.claude/skills/reverse-engineer-anything")

    def test_safe_skill_dir(self):
        with tempfile.TemporaryDirectory() as t:
            good = Path(t) / "skills" / "reverse-engineer-anything"
            good.mkdir(parents=True)
            other = Path(t) / "skills" / "other"
            other.mkdir()
            link = Path(t) / "link" / "reverse-engineer-anything"
            link.parent.mkdir()
            os.symlink(str(good), str(link))
            afile = Path(t) / "f" / "reverse-engineer-anything"
            afile.parent.mkdir()
            afile.write_text("x")
            self.assertTrue(rs.safe_skill_dir(str(good)))
            for p in (str(other), str(link), str(afile), None, "", str(Path(t) / "missing" / "reverse-engineer-anything")):
                self.assertFalse(rs.safe_skill_dir(p), p)

    def test_never_uninstalls_globally(self):
        src = (HERE.parent / "rea_setup.py").read_text(encoding="utf-8")
        self.assertNotIn('"uninstall"', src)


if __name__ == "__main__":
    unittest.main()
