"""The plugin and marketplace manifests, hooks and MCP config are well formed and point at shipped files."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "claude"
BANNED_PREFIX = ("claude-", "anthropic-", "cc-plugin-")
ROOT_REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"'\s]+)")


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


class PluginShapeTest(unittest.TestCase):
    def test_marketplace(self):
        m = load(ROOT / ".claude-plugin" / "marketplace.json")
        self.assertEqual(m["name"], "dryas-workflow")
        self.assertIn("owner", m)
        self.assertEqual([p["name"] for p in m["plugins"]], ["dryas"])
        self.assertEqual(m["plugins"][0]["source"], "./claude")
        self.assertIn("claude-plugins-official", m["allowCrossMarketplaceDependenciesOn"])

    def test_plugin_manifest(self):
        p = load(PLUGIN / ".claude-plugin" / "plugin.json")
        self.assertEqual(p["name"], "dryas")
        self.assertFalse(p["name"].startswith(BANNED_PREFIX))
        self.assertRegex(p["version"], r"^\d+\.\d+\.\d+$")
        dep = [d for d in p["dependencies"] if d["name"] == "superpowers"][0]
        self.assertEqual(dep["marketplace"], "claude-plugins-official")
        # no version range: claude-plugins-official pins superpowers to a commit, and Claude Code then finds
        # "no git tag satisfying" any range, so the install fails; the tested version is checked by setup instead
        self.assertNotIn("version", dep)
        self.assertTrue(p["userConfig"]["openrouter_key"]["sensitive"])

    def test_versions_are_semver_and_in_sync(self):
        # no other release version exists in the repo; the marketplace entry must track plugin.json
        # (bump both whenever shipped plugin content changes)
        p = load(PLUGIN / ".claude-plugin" / "plugin.json")
        m = load(ROOT / ".claude-plugin" / "marketplace.json")
        self.assertRegex(p["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(m["plugins"][0]["version"], p["version"])

    def test_hooks_point_at_shipped_files(self):
        h = load(PLUGIN / "hooks" / "hooks.json")["hooks"]
        cmds = [x["command"] for groups in h.values() for g in groups for x in g["hooks"]]
        self.assertTrue(cmds)
        for c in cmds:
            self.assertTrue(c.startswith('"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/'), c)
            for rel in ROOT_REF.findall(c):
                self.assertTrue((PLUGIN / rel).is_file(), rel)

    def test_hook_events(self):
        h = load(PLUGIN / "hooks" / "hooks.json")["hooks"]
        self.assertEqual(sorted(h), ["PreCompact", "PreToolUse", "SessionStart", "UserPromptSubmit"])
        ss = {g.get("matcher"): [x["command"] for x in g["hooks"]] for g in h["SessionStart"]}
        self.assertTrue(any("rules_inject.py" in c for c in ss["startup|resume|clear|compact"]))
        self.assertTrue(any("compact_restore.py" in c for c in ss["compact"]))
        self.assertTrue(any("handoff_restore.py" in c for c in ss["clear"]))

    def test_pretool_matcher_covers_enabled_chain_stages(self):
        """PreToolUse spawns Python only for the tools an enabled pretool stage matches (flowobserve, shipped
        off, has no match; its own installer adds hooks for the other events and tools)."""
        h = load(PLUGIN / "hooks" / "hooks.json")["hooks"]
        pre = h["PreToolUse"]
        self.assertEqual(len(pre), 1)
        matcher = pre[0]["matcher"]
        self.assertNotEqual(matcher, "*")
        self.assertEqual(matcher, "Bash|Edit|Write|MultiEdit|NotebookEdit")
        tools = set(matcher.split("|"))
        chain = load(PLUGIN / "jev" / "chain.json")["pretool"]
        for st in chain:
            if st.get("enabled") is False:
                continue
            self.assertIn("match", st, st["name"])
            self.assertTrue(set(st["match"].split("|")) <= tools, st["name"])

    def test_mcp(self):
        m = load(PLUGIN / ".mcp.json")["mcpServers"]["jev"]
        self.assertEqual(m["env"]["DRYAS_OPENROUTER_KEY"], "${user_config.openrouter_key}")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/jev/jev_mcp.py", m["args"])
        self.assertEqual(m["command"], "${DRYAS_PY:-python3}")  # DRYAS_PY from settings env; expands in Claude Code
        self.assertTrue((PLUGIN / "jev" / "jev_mcp.py").is_file())

    def test_markdown_has_no_install_tokens(self):
        """[A1] the plugin ships Markdown unrendered: no {{CD}}/{{PY}}, no ~/.claude/jev or ~/.claude/skills."""
        hits = []
        for f in sorted(PLUGIN.rglob("*.md")) + [PLUGIN / "CLAUDE.md.template"]:
            if "tests" in f.parts or f.name in ("NOTICE.md", "UPSTREAM.md"):
                continue
            t = f.read_text(encoding="utf-8")
            for bad in ("{{CD}}", "{{PY}}", "~/.claude/jev", "~/.claude/skills"):
                if bad in t:
                    hits.append("%s: %s" % (f.relative_to(ROOT), bad))
        self.assertEqual(hits, [])

    def test_launcher_is_executable_in_git(self):
        import subprocess
        out = subprocess.run(["git", "ls-files", "-s", "claude/bin/dryas-py"], cwd=str(ROOT),
                             capture_output=True, text=True).stdout
        self.assertTrue(out.startswith("100755"), out)


if __name__ == "__main__":
    unittest.main()
