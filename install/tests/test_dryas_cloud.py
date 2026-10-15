import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cloud_fixtures as fx

SETTINGS = '{\n    "permissions": {"allow": ["Bash(make test)"]},\n    "env": {"FOO": "1"}\n}\n'
MCP = '{"mcpServers": {"docs": {"command": "docs-server"}}}\n'
FILES = {"README.md": "# demo\n", "CLAUDE.md": "# Repo rules\n\nKeep tests green.\n", ".gitignore": "node_modules/\n",
         ".claude/settings.json": SETTINGS, ".mcp.json": MCP}


class CloudCliTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.repo = fx.git_repo(self.base / "repo", FILES)
        self.cfg = self.base / "no-config"  # no design plugins, no own skills

    def cli(self, *args):
        return fx.run_cli(list(args) + ["--repo", str(self.repo), "--claude-dir", str(self.cfg)])

    def init(self, *extra):
        rc, out = self.cli("init", "--yes", *extra)
        self.assertEqual(rc, 0, out)
        fx.commit_all(self.repo)
        return out

    def test_dry_run_changes_nothing(self):
        before = fx.snapshot(self.repo)
        rc, out = self.cli("init")
        self.assertEqual(rc, 0, out)
        self.assertIn("  add     .dryas/jev/gate.py (", out)
        self.assertIn("  change  .claude/settings.json (", out)
        self.assertIn("not copied: update-my-vault (its vault and sources are on the Mac)", out)
        self.assertIn("Dry run: nothing written.", out)
        self.assertEqual(fx.snapshot(self.repo), before)

    def test_init_then_check_passes(self):
        out = self.init()
        self.assertIn("Nothing committed. To commit:", out)
        self.assertRegex(out, r"  git add -A -- .*\.claude/settings\.json .*\.dryas .*CLAUDE\.md")
        self.assertIn('  git commit -m "chore: add Dryas ', out)
        rc, out = self.cli("check")
        self.assertEqual(rc, 0, out)
        self.assertIn("dryas cloud check: 0 problems", out)

    def test_merges_keep_existing_entries(self):
        self.init()
        s = json.loads((self.repo / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertIn("Bash(make test)", s["permissions"]["allow"])
        self.assertEqual(s["env"], {"FOO": "1"})  # no Dryas env in settings.json
        jev = json.loads((self.repo / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["jev"]
        self.assertEqual(jev["env"]["DRYAS_DATA_ROOT"], "${CLAUDE_PROJECT_DIR:-.}/.dryas/state")
        pre = [h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertIn('"${DRYAS_PY:-python3}" -X utf8 "$CLAUDE_PROJECT_DIR/.dryas/jev/cloud_hook.py" chain.py pretool', pre)
        servers = json.loads((self.repo / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
        self.assertEqual(sorted(servers), ["docs", "jev"])
        md = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(md.startswith("# Repo rules\n\nKeep tests green.\n"))
        self.assertIn("<!-- dryas:start -->\nDryas ", md)
        ignore = (self.repo / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(ignore[0], "node_modules/")
        self.assertIn(".dryas/state/", ignore)

    def test_hand_edit_is_drift_and_update_keeps_it(self):
        self.init()
        skill = self.repo / ".claude/skills/plan/SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\nLocal note.\n", encoding="utf-8")
        fx.commit_all(self.repo)
        rc, out = self.cli("check")
        self.assertEqual(rc, 1)
        self.assertIn("drift (hand-edited): .claude/skills/plan/SKILL.md", out)
        rc, out = self.cli("update", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertIn("kept hand-edited .claude/skills/plan/SKILL.md", out)
        self.assertIn("Local note.", skill.read_text(encoding="utf-8"))
        fx.commit_all(self.repo)
        rc, out = self.cli("update", "--yes", "--force")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Local note.", skill.read_text(encoding="utf-8"))
        fx.commit_all(self.repo)
        self.assertEqual(self.cli("check")[0], 0)

    def test_update_twice_changes_nothing(self):
        self.init()
        rc, out = self.cli("update", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertIn("Nothing to change.", out)

    def test_remove_restores_the_repo(self):
        before = fx.snapshot(self.repo)
        self.init()
        rc, out = self.cli("remove", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertEqual(fx.snapshot(self.repo), before)
        self.assertFalse((self.repo / ".dryas").exists())
        self.assertFalse((self.repo / ".claude/skills").exists())

    def test_clash_stops_with_prefix_hint(self):
        own = self.repo / ".claude/skills/plan/SKILL.md"
        own.parent.mkdir(parents=True)
        own.write_text("---\nname: plan\n---\nOur own planning notes.\n", encoding="utf-8")
        fx.commit_all(self.repo)
        before = fx.snapshot(self.repo)
        rc, out = self.cli("init", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn(".claude/skills/plan", out)
        self.assertIn("--prefix", out)
        self.assertEqual(fx.snapshot(self.repo), before)
        self.init("--prefix", "dryas-")
        self.assertIn("\nname: dryas-plan\n", (self.repo / ".claude/skills/dryas-plan/SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(own.read_text(encoding="utf-8"), "---\nname: plan\n---\nOur own planning notes.\n")
        self.assertEqual(self.cli("check")[0], 0)

    def test_malformed_config_stops_the_run(self):
        for rel, bad in ((".claude/settings.json", "{not json\n"), (".mcp.json", "[]\n")):
            (self.repo / rel).write_text(bad, encoding="utf-8")
            fx.commit_all(self.repo)
            before = fx.snapshot(self.repo)
            rc, out = self.cli("init", "--yes")
            self.assertEqual(rc, 1, rel)
            self.assertIn("nothing changed", out)
            self.assertEqual(fx.snapshot(self.repo), before)
            (self.repo / rel).write_text(FILES[rel], encoding="utf-8")
            fx.commit_all(self.repo)

    def test_foreign_jev_server_stops_the_run(self):
        (self.repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"jev": {"command": "my-jev"}}}), encoding="utf-8")
        fx.commit_all(self.repo)
        rc, out = self.cli("init", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("a jev server that Dryas did not write", out)
        self.assertFalse((self.repo / ".dryas").exists())

    def test_mac_path_in_a_copied_file_fails_check(self):
        self.init()
        f = self.repo / ".claude/commands/tune.md"
        f.write_text(f.read_text(encoding="utf-8") + "See /Users/someone/notes.\n", encoding="utf-8")
        rc, out = self.cli("check")
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"\.claude/commands/tune\.md:\d+: absolute Mac path")

    def test_design_copy_carries_licence_and_notice(self):
        self.cfg = fx.design_config(self.base)
        self.init("--with-design")
        self.assertIn("Apache License", (self.repo / ".dryas/licenses/impeccable-LICENSE").read_text(encoding="utf-8"))
        notice = (self.repo / ".dryas/NOTICE").read_text(encoding="utf-8")
        self.assertIn("- impeccable@impeccable 9.9.9 (Apache-2.0): .dryas/licenses/impeccable-LICENSE", notice)
        self.assertTrue((self.repo / ".claude/skills/impeccable/SKILL.md").is_file())
        self.assertEqual(self.cli("check")[0], 0)

    def test_second_init_refuses(self):
        self.init()
        before = fx.snapshot(self.repo)
        rc, out = self.cli("init", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("use update or remove", out)
        self.assertEqual(fx.snapshot(self.repo), before)

    def test_uncommitted_changes_need_force(self):
        (self.repo / "CLAUDE.md").write_text("# changed\n", encoding="utf-8")
        rc, out = self.cli("init")
        self.assertEqual(rc, 1)
        self.assertIn("uncommitted changes in CLAUDE.md", out)
        rc, out = self.cli("init", "--force")
        self.assertEqual(rc, 0, out)
        self.assertIn("Dry run: nothing written.", out)

    def test_init_writes_no_dryas_env_and_remove_keeps_env(self):
        own = '{\n  "env": {"DRYAS_DATA_ROOT": "elsewhere", "FOO": "1"},\n  "permissions": {"allow": ["Bash(make test)"]}\n}\n'
        (self.repo / ".claude/settings.json").write_text(own, encoding="utf-8")
        fx.commit_all(self.repo)
        self.init()
        settings = json.loads((self.repo / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["env"], {"DRYAS_DATA_ROOT": "elsewhere", "FOO": "1"})
        self.assertIn("hooks", settings)
        rc, out = self.cli("remove", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertEqual((self.repo / ".claude/settings.json").read_text(encoding="utf-8"), own)

    def test_not_the_repo_root(self):
        sub = self.repo / "pkg"
        sub.mkdir()
        rc, out = fx.run_cli(["init", "--repo", str(sub)])
        self.assertEqual(rc, 1)
        self.assertIn("is not the repo root", out)
        rc, out = fx.run_cli(["init", "--repo", str(self.base)])
        self.assertEqual(rc, 1)
        self.assertIn("is not a git work tree", out)


class CloudCliGapTest(unittest.TestCase):
    """Gaps a wrong implementation could still pass the plan's tests with."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.repo = fx.git_repo(self.base / "repo", FILES)
        self.cfg = self.base / "no-config"

    def cli(self, *args):
        return fx.run_cli(list(args) + ["--repo", str(self.repo), "--claude-dir", str(self.cfg)])

    def init(self, *extra):
        rc, out = self.cli("init", "--yes", *extra)
        self.assertEqual(rc, 0, out)
        fx.commit_all(self.repo)
        return out

    def test_update_and_remove_without_yes_write_nothing(self):
        # defect: only init honours the dry run
        self.init()
        skill = self.repo / ".claude/skills/plan/SKILL.md"
        skill.write_text("changed\n", encoding="utf-8")
        fx.commit_all(self.repo)
        before = fx.snapshot(self.repo)
        for cmd in (("update", "--force"), ("remove", "--force")):
            rc, out = self.cli(*cmd)
            self.assertEqual(rc, 0, out)
            self.assertIn("Dry run: nothing written.", out)
            self.assertEqual(fx.snapshot(self.repo), before, cmd)

    def test_uncommitted_change_refuses_a_write_too(self):
        # defect: the dirty-tree check only guards the dry run, or --force is ignored
        (self.repo / "CLAUDE.md").write_text("# changed\n", encoding="utf-8")
        before = fx.snapshot(self.repo)
        rc, out = self.cli("init", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("uncommitted changes in CLAUDE.md", out)
        self.assertEqual(fx.snapshot(self.repo), before)
        rc, out = self.cli("init", "--yes", "--force")
        self.assertEqual(rc, 0, out)
        md = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(md.startswith("# changed\n"))
        self.assertIn("<!-- dryas:start -->", md)

    def test_never_commits(self):
        # defect: the run commits (or stages) on the user's behalf
        head = fx.git(self.repo, "rev-parse", "HEAD")
        rc, out = self.cli("init", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertEqual(fx.git(self.repo, "rev-parse", "HEAD"), head)
        self.assertEqual(fx.git(self.repo, "diff", "--cached", "--name-only"), "")
        self.assertIn("?? .dryas/", fx.git_status(self.repo))

    def test_exec_bit_and_chmod_hint(self):
        out = self.init()
        self.assertTrue(os.access(str(self.repo / ".dryas/bin/dryas-py"), os.X_OK))
        self.assertIn("  git add --chmod=+x -- .dryas/bin/dryas-py", out)

    def test_every_file_under_dryas_is_owned_and_the_copy_checks_itself(self):
        # defect: NOTICE, VERSION, licences or docs written but left out of the manifest (unowned in check)
        self.init()
        man = json.loads((self.repo / ".dryas/manifest.json").read_text(encoding="utf-8"))
        on_disk = {r for r in fx.snapshot(self.repo) if r.startswith(".dryas/")} - {".dryas/manifest.json"}
        self.assertTrue(on_disk <= set(man["files"]), sorted(on_disk - set(man["files"])))
        for rel in (".dryas/NOTICE", ".dryas/VERSION", ".dryas/docs/dryas-workflow.md",
                    ".dryas/licenses/LICENSE-dryas", ".dryas/licenses/LICENSE-superpowers"):
            self.assertIn(rel, man["files"])
        p = subprocess.run([sys.executable, "-I", str(self.repo / ".dryas/jev/cloud_check.py"),
                            "--repo", str(self.repo)], capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("dryas cloud check: 0 problems", p.stdout)

    def test_bare_repo_init_then_remove_restores_it(self):
        # defect: files Dryas created (settings.json, .mcp.json, CLAUDE.md, .gitignore) survive remove
        shutil.rmtree(str(self.repo))
        self.repo = fx.git_repo(self.base / "bare", {"README.md": "# demo\n"})
        before = fx.snapshot(self.repo)
        self.init()
        settings = json.loads((self.repo / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("env", settings)
        self.assertEqual(self.cli("check")[0], 0)
        rc, out = self.cli("remove", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertEqual(fx.snapshot(self.repo), before)
        self.assertFalse((self.repo / ".claude").exists())

    def test_remove_drops_state_and_pycache_keeps_memory_notes(self):
        before = fx.snapshot(self.repo)
        self.init("--persist-memory")
        note = self.repo / ".dryas/memory/notes/decision.md"
        note.write_text("We chose X.\n", encoding="utf-8")
        fx.commit_all(self.repo)
        state = self.repo / ".dryas/state/jev"
        state.mkdir(parents=True)
        (state / "log.jsonl").write_text("{}\n", encoding="utf-8")
        for d in (".dryas/jev/__pycache__", ".claude/skills/plan/__pycache__"):
            (self.repo / d).mkdir(parents=True, exist_ok=True)
            (self.repo / d / "x.cpython-39.pyc").write_bytes(b"\0")
        rc, out = self.cli("remove", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertIn("kept .dryas/memory/notes/*.md", out)
        after = fx.snapshot(self.repo)
        self.assertEqual(after.pop(".dryas/memory/notes/decision.md"), b"We chose X.\n")
        self.assertEqual(after, before)
        self.assertFalse((self.repo / ".dryas/state").exists())
        self.assertFalse((self.repo / ".claude/skills").exists())

    def test_malformed_config_stops_update_and_remove(self):
        self.init()
        (self.repo / ".mcp.json").write_text("{broken\n", encoding="utf-8")
        fx.commit_all(self.repo)
        before = fx.snapshot(self.repo)
        for cmd in ("update", "remove"):
            rc, out = self.cli(cmd, "--yes")
            self.assertEqual(rc, 1, cmd)
            self.assertIn("nothing changed", out)
            self.assertEqual(fx.snapshot(self.repo), before, cmd)

    def test_update_keeps_a_hand_edited_file_dryas_drops(self):
        # defect: update deletes a hand-edited file that a narrower option set no longer copies
        self.init("--persist-memory")
        keep = self.repo / ".dryas/memory/notes/.gitkeep"
        keep.write_text("mine\n", encoding="utf-8")
        fx.commit_all(self.repo)
        man = json.loads((self.repo / ".dryas/manifest.json").read_text(encoding="utf-8"))
        man["options"]["persist_memory"] = False
        (self.repo / ".dryas/manifest.json").write_text(json.dumps(man), encoding="utf-8")
        fx.commit_all(self.repo)
        rc, out = self.cli("update", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertIn("kept hand-edited .dryas/memory/notes/.gitkeep", out)
        self.assertEqual(keep.read_text(encoding="utf-8"), "mine\n")


if __name__ == "__main__":
    unittest.main()
