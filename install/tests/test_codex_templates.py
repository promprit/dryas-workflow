import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import settings_merge as sm
CODEX = Path(__file__).resolve().parents[2] / "codex"
SKILLS = ("orchestrate", "wreview", "wplan", "commit", "tune")
M = {"PY": "/p", "CD": "/c", "PY_SAFE": "/ps", "CD_SAFE": "/cs"}


class CodexTemplatesTest(unittest.TestCase):
    def test_skills(self):
        for n in SKILLS:
            t = (CODEX / "skills" / n / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(t.startswith("---\nname: %s\ndescription: " % n), n)
            for banned in ("mcp__", "Agent tool", "/usr/bin/python3", "subagent_type", "Fable"):
                self.assertNotIn(banned, t, (n, banned))
            sm.render_tokens(t, M)  # only known tokens
        self.assertFalse((CODEX / "skills" / "handoff").exists())

    def test_agents_template_small(self):
        t = sm.render_tokens((CODEX / "AGENTS.md.template").read_text(encoding="utf-8"), M)
        self.assertLess(len(t.encode("utf-8")), 8 * 1024)
        self.assertIn("$dryas:orchestrate", t)

    def test_plugin_hooks(self):
        # the copy install's hooks.fragment.json is gone; the plugin ships codex/hooks/hooks.json (frozen form)
        r = json.loads((CODEX / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertFalse((CODEX / "hooks.fragment.json").exists())
        pre = r["hooks"]["PreToolUse"][0]
        self.assertEqual(pre["matcher"], "Bash|apply_patch|Edit|Write")
        self.assertEqual(pre["hooks"][0]["command"],
                         '"${DRYAS_PY:-python3}" -X utf8 "${PLUGIN_ROOT}/jev/chain.py" pretool --harness codex')
        self.assertEqual(pre["hooks"][0]["commandWindows"],
                         'python -X utf8 "%PLUGIN_ROOT%\\jev\\chain.py" pretool --harness codex')
        ups = r["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        self.assertEqual(ups["command"],
                         '"${DRYAS_PY:-python3}" -X utf8 "${PLUGIN_ROOT}/jev/chain.py" prompt --harness codex')
        self.assertEqual(ups["commandWindows"], 'python -X utf8 "%PLUGIN_ROOT%\\jev\\chain.py" prompt --harness codex')

if __name__ == "__main__":
    unittest.main()
