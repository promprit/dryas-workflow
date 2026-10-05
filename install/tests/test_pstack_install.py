# install/tests/test_pstack_install.py
import io, os, shutil, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import codex_target as ct
import dryas_install as di
import render
import run_cmd
REPO = HERE.parents[1]
BLOCK = "a\n<!-- pstack-picks -->\nPICK {{CD}}/pstack/x.md\n<!-- /pstack-picks -->\nb\n"


class GateBlocksTest(unittest.TestCase):
    def test_on_keeps_body_drops_markers(self):
        self.assertEqual(render.gate_blocks(BLOCK, ["core", "pstack-picks"]), "a\nPICK {{CD}}/pstack/x.md\nb\n")

    def test_off_drops_block(self):
        self.assertEqual(render.gate_blocks(BLOCK, ["core"]), "a\nb\n")

    def test_gate_blocks_ignores_other_comments(self):
        t = "<!-- dryas:start -->\nx\n<!-- dryas:end -->\n"
        self.assertEqual(render.gate_blocks(t, ["core"]), t)

    def test_gate_blocks_unclosed_raises(self):
        with self.assertRaises(ValueError):
            render.gate_blocks("<!-- pstack-picks -->\nx\n", ["core"])
        with self.assertRaises(ValueError):
            render.gate_blocks("x\n<!-- /pstack-picks -->\n", ["core"])


class ComponentTest(unittest.TestCase):
    def test_flag(self):
        self.assertIn("pstack-picks", run_cmd.components(run_cmd.parse([])))
        self.assertNotIn("pstack-picks", run_cmd.components(run_cmd.parse(["--no-pstack-picks"])))


def fixture_repo():
    r = Path(tempfile.mkdtemp())
    files = {"claude/agents/executor.md": "exec\n" + BLOCK,
             "claude/pstack/x.md": "x\n", "claude/skills/interrogate/SKILL.md": "s\n",
             "claude/skills/benchmark-checklist/SKILL.md": "b\n",
             "claude/CLAUDE.md.template": "POLICY\n<!-- pstack-picks -->\nBENCH\n<!-- /pstack-picks -->\n",
             "docs/workflow.md": "# W\n"}
    for rel, t in files.items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(t, encoding="utf-8")
    return r


class _InstallBase(object):
    def setUp(self):
        self.repo = fixture_repo()
        self.home = Path(tempfile.mkdtemp())
        self.cd = self.home / ".claude"
        self.cd.mkdir()
        os.environ.pop("DRYAS_DATA_ROOT", None)
        self.saved = (di.run, di.confirm, di.capture)
        di.run, di.confirm, di.capture = (lambda argv, cwd=None: 0), (lambda p: True), (lambda argv, *a, **k: (1, ""))

    def tearDown(self):
        di.run, di.confirm, di.capture = self.saved

    def install(self, comps):
        with redirect_stdout(io.StringIO()):
            return di.install(self.repo, self.cd, comps, home=self.home, yes=True)


class InstallGatingTest(_InstallBase, unittest.TestCase):
    def test_files_gated(self):
        self.install(["core"])
        self.assertFalse((self.cd / "pstack").exists())
        self.assertFalse((self.cd / "skills" / "interrogate").exists())
        self.assertEqual((self.cd / "agents/executor.md").read_text(encoding="utf-8"), "exec\na\nb\n")
        self.assertNotIn("BENCH", (self.cd / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_files_on(self):
        self.install(["core", "pstack-picks"])
        self.assertTrue((self.cd / "pstack/x.md").is_file())
        self.assertTrue((self.cd / "skills/benchmark-checklist/SKILL.md").is_file())
        ex = (self.cd / "agents/executor.md").read_text(encoding="utf-8")
        self.assertIn("PICK %s/pstack/x.md" % str(self.cd).replace("\\", "/"), ex)
        self.assertNotIn("<!--", ex)
        self.assertIn("BENCH", (self.cd / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_reinstall_without_keeps_text(self):
        self.install(["core", "pstack-picks"])
        self.install(["core"])
        self.assertIn("PICK", (self.cd / "agents/executor.md").read_text(encoding="utf-8"))
        self.assertTrue((self.cd / "pstack/x.md").is_file())

    def test_unclosed_marker_aborts_before_write(self):
        (self.repo / "claude/agents/executor.md").write_text("<!-- pstack-picks -->\nx\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.install(["core"])
        self.assertFalse((self.cd / "agents").exists())

    def test_uninstall_removes_pstack(self):
        self.install(["core", "pstack-picks"])
        with redirect_stdout(io.StringIO()):
            di.uninstall(self.cd)
        self.assertFalse((self.cd / "pstack").exists())
        self.assertFalse((self.cd / "skills" / "interrogate").exists())


class CodexGatingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        shutil.copytree(str(REPO / "codex"), str(self.repo / "codex"))
        for n in ct.PSTACK_SKILLS:
            p = self.repo / "codex" / "skills" / n / "SKILL.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("---\nname: %s\ndescription: d\n---\n" % n, encoding="utf-8")
        t = self.repo / "codex" / "AGENTS.md.template"
        t.write_text(t.read_text(encoding="utf-8") + "<!-- pstack-picks -->\nPSTACKLINE\n<!-- /pstack-picks -->\n",
                     encoding="utf-8")
        self.home = self.tmp / "home"
        self.cdx = self.home / ".codex"
        cd = (self.home / ".claude").as_posix()
        self.mapping = {"PY": "/p", "CD": cd, "PY_SAFE": "/p", "CD_SAFE": cd, "HOME": self.home.as_posix(),
                        "DRYAS_DATA_ROOT": "/d"}

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def install(self, comps):
        with redirect_stdout(io.StringIO()):
            return ct.install_codex(self.repo, self.cdx, self.home, comps, self.mapping, {}, lambda argv: 0)

    def test_codex_skills_gated(self):
        self.assertEqual(self.install(["core"]), 0)
        self.assertFalse((ct.skills_dir(self.home) / "interrogate").exists())
        self.assertNotIn("PSTACKLINE", (self.cdx / "AGENTS.md").read_text(encoding="utf-8"))

    def test_codex_skills_on(self):
        self.assertEqual(self.install(["core", "pstack-picks"]), 0)
        for n in ct.PSTACK_SKILLS:
            self.assertTrue((ct.skills_dir(self.home) / n / "SKILL.md").is_file(), n)
        agents = (self.cdx / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("PSTACKLINE", agents)
        self.assertNotIn("<!-- pstack-picks", agents)

    def test_codex_reinstall_without_keeps_text(self):
        self.install(["core", "pstack-picks"])
        self.install(["core"])
        self.assertIn("PSTACKLINE", (self.cdx / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertTrue((ct.skills_dir(self.home) / "interrogate").exists())


class ChainKeepTest(_InstallBase, unittest.TestCase):
    def test_chain_keeps_user_stage_settings(self):
        import json
        chain = {"pretool": [{"name": "x", "component": "jev", "cmd": ["true"]}]}
        (self.repo / "claude/jev").mkdir(parents=True, exist_ok=True)
        (self.repo / "claude/jev/chain.json").write_text(json.dumps(chain), encoding="utf-8")
        self.install(["core", "jev"])
        p = self.cd / "jev" / "chain.json"
        c = json.loads(p.read_text(encoding="utf-8"))
        c["pretool"][0]["enabled"] = False
        p.write_text(json.dumps(c), encoding="utf-8")
        self.install(["core"])
        c = json.loads(p.read_text(encoding="utf-8"))
        self.assertIs(c["pretool"][0].get("enabled"), False)


class ShippedMarkdownTest(unittest.TestCase):
    def test_markers_balanced(self):
        files = sorted(list((REPO / "claude").rglob("*.md")) + list((REPO / "codex").rglob("*.md")))
        files += [REPO / "claude/CLAUDE.md.template", REPO / "codex/AGENTS.md.template"]
        for f in files:
            t = f.read_text(encoding="utf-8")
            for comps in ([], list(render.GATED)):
                try:
                    render.gate_blocks(t, comps)
                except ValueError as e:
                    self.fail("%s: %s" % (f, e))


class RealRepoInstallTest(_InstallBase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repo = REPO

    def test_layout_licenses_uninstall(self):
        from test_pstack_content import LAYOUT
        self.install(["core", "pstack-picks"])
        for rel in LAYOUT:
            self.assertTrue((self.cd / "pstack" / rel).exists(), rel)
        for n in ("interrogate", "benchmark-checklist"):
            self.assertTrue((self.cd / "skills" / n / "SKILL.md").is_file(), n)
        self.assertIn("benchmark-checklist", (self.cd / "CLAUDE.md").read_text(encoding="utf-8"))
        with redirect_stdout(io.StringIO()):
            di.uninstall(self.cd)
        self.assertFalse((self.cd / "pstack").exists())
        md = self.cd / "CLAUDE.md"
        if md.exists():
            self.assertNotIn("benchmark-checklist", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
