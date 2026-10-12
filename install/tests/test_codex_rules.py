"""The plugin's own copy of rules_inject.py, run the way the Codex SessionStart hook runs it."""
import json, os, re, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
CODEX = ROOT / "codex"


class CodexRulesHookTest(unittest.TestCase):
    def run_hook(self, off):
        t = tempfile.mkdtemp()
        local = Path(t) / "chain.local.json"
        local.write_text(json.dumps({"off": off}), encoding="utf-8")
        env = dict(os.environ, JEV_CHAIN_LOCAL=str(local), PLUGIN_ROOT=str(CODEX), CLAUDE_PLUGIN_ROOT=str(CODEX))
        env.pop("DRYAS_PY", None)
        p = subprocess.run([sys.executable, "-X", "utf8", str(CODEX / "jev" / "rules_inject.py"), "--harness", "codex"],
                           input=json.dumps({"hook_event_name": "SessionStart", "source": "startup"}),
                           capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        return out["additionalContext"]

    def test_codex_rules_with_paths(self):
        ctx = self.run_hook([])
        self.assertIn("# Dryas Workflow (Codex)", ctx)
        self.assertIn("<dryas-root> = " + str(CODEX).replace("\\", "/"), ctx)
        self.assertIn("~/.dryas/docs/dryas-workflow.md", ctx)

    def test_pstack_off(self):
        ctx = self.run_hook(["pstack-picks"])
        self.assertNotIn("$dryas:interrogate", ctx)
        self.assertIn("pstack-picks is not installed", ctx)


class CodexSkillsTest(unittest.TestCase):
    def skills(self):
        return sorted((CODEX / "skills").glob("*/SKILL.md"))

    def test_no_install_tokens(self):
        for s in self.skills():
            t = s.read_text(encoding="utf-8")
            self.assertNotIn("{{", t, s)
            self.assertNotIn("~/.claude", t, s)

    def test_root_paths_exist_in_plugin(self):
        for s in self.skills() + [CODEX / "AGENTS.md.template"]:
            for rel in re.findall(r"(?:<dryas-root>|\{\{CD\}\})/([A-Za-z0-9_./-]+[A-Za-z0-9_])", s.read_text(encoding="utf-8")):
                self.assertTrue((CODEX / rel).exists(), "%s: %s" % (s, rel))

    def test_pstack_skills_check_component(self):
        for n in ("interrogate", "benchmark-checklist"):
            self.assertIn("pstack-picks is not installed", (CODEX / "skills" / n / "SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
