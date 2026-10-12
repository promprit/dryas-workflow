"""The Codex plugin: marketplace, manifest, frozen hook command lines, MCP config, no symlinks."""
import json, os, re, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
CODEX = ROOT / "codex"
PRE = '"${DRYAS_PY:-python3}" -X utf8 "${PLUGIN_ROOT}/jev/'
HOOK_LINES = {  # frozen: part of each hook's trust hash; changing one makes users re-trust
    "SessionStart": [PRE + 'rules_inject.py" --harness codex'],
    "UserPromptSubmit": [PRE + 'chain.py" prompt --harness codex'],
    "PreToolUse": [PRE + 'chain.py" pretool --harness codex'],
}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


class CodexPluginShapeTest(unittest.TestCase):
    def test_marketplace_points_codex_at_codex_edition(self):
        m = load(ROOT / ".agents" / "plugins" / "marketplace.json")
        self.assertEqual(m["name"], "dryas-workflow")
        self.assertEqual([(p["name"], p["source"]) for p in m["plugins"]], [("dryas", "./codex")])
        self.assertEqual(load(ROOT / ".claude-plugin" / "marketplace.json")["name"], "dryas-workflow")

    def test_manifest(self):
        m = load(CODEX / ".codex-plugin" / "plugin.json")
        self.assertEqual(m["name"], "dryas")
        self.assertEqual(m["version"], load(ROOT / "claude" / ".claude-plugin" / "plugin.json")["version"])
        for k in ("userConfig", "dependencies", "commands", "agents"):
            self.assertNotIn(k, m)
        self.assertLessEqual(len(m.get("interface", {}).get("defaultPrompt", [])), 3)

    def test_hook_lines_frozen(self):
        h = load(CODEX / "hooks" / "hooks.json")
        self.assertLessEqual(set(h), {"description", "hooks"})
        got = {ev: [x["command"] for g in groups for x in g["hooks"]] for ev, groups in h["hooks"].items()}
        self.assertEqual(got, HOOK_LINES)
        self.assertEqual(h["hooks"]["PreToolUse"][0]["matcher"], "Bash|apply_patch|Edit|Write")
        self.assertEqual(h["hooks"]["SessionStart"][0]["matcher"], "startup|resume|clear|compact")

    def test_hook_paths_exist(self):
        text = (CODEX / "hooks" / "hooks.json").read_text(encoding="utf-8")
        for rel in re.findall(r"\$\{PLUGIN_ROOT\}/([^\"\\]+)", text):
            self.assertTrue((CODEX / rel).is_file(), rel)

    def test_mcp_relative_no_expansion(self):
        m = load(CODEX / ".mcp.json")["mcpServers"]
        self.assertEqual(set(m), {"jev"})
        jev = m["jev"]
        self.assertEqual((jev["command"], jev["cwd"]), ("python3", "."))
        self.assertTrue((CODEX / jev["args"][-1]).is_file())
        self.assertIn("OPENROUTER_API_KEY", jev["env_vars"])
        self.assertNotIn("${", json.dumps(m))
        self.assertNotIn("env", jev)  # secrets only via env_vars

    def test_no_symlinks(self):
        for d, dirs, files in os.walk(str(CODEX)):
            for n in dirs + files:
                self.assertFalse(os.path.islink(os.path.join(d, n)), os.path.join(d, n))


if __name__ == "__main__":
    unittest.main()
