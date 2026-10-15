import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cloud_config as cfg

PLUGIN_HOOKS = json.loads((ROOT / "claude/hooks/hooks.json").read_text(encoding="utf-8"))
USER = '{\n    "permissions": {"allow": ["Bash(make test)"]},\n    "env": {"FOO": "1"}\n}\n'


class HooksTest(unittest.TestCase):
    def test_every_plugin_hook_runs_from_the_copy(self):
        h = cfg.hooks(PLUGIN_HOOKS)
        cmds = [x["command"] for groups in h.values() for g in groups for x in g["hooks"]]
        for c in cmds:
            self.assertTrue(c.startswith(cfg.ENTRY), c)
            self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", c)
        self.assertIn(cfg.ENTRY + "chain.py pretool", cmds)
        self.assertFalse(any("rules_inject.py" in c for c in cmds))
        self.assertEqual(h["PreToolUse"][0]["matcher"], PLUGIN_HOOKS["hooks"]["PreToolUse"][0]["matcher"])
        plugin = [x["command"] for groups in PLUGIN_HOOKS["hooks"].values() for g in groups for x in g["hooks"]]
        self.assertEqual(len(cmds), len([c for c in plugin if "rules_inject.py" not in c]))

    def test_fragment_sets_no_env(self):
        f = cfg.fragment(PLUGIN_HOOKS)
        self.assertEqual(sorted(f), ["hooks", "permissions"])
        self.assertEqual(f["permissions"], {"allow": ["mcp__jev"]})
        self.assertEqual(cfg.mcp_entry()["env"], {"CLAUDE_PLUGIN_ROOT": "${CLAUDE_PROJECT_DIR:-.}/.dryas",
                                                  "DRYAS_DATA_ROOT": "${CLAUDE_PROJECT_DIR:-.}/.dryas/state"})


class SettingsTest(unittest.TestCase):
    def test_merge_keeps_the_users_entries_and_undo_restores_bytes(self):
        text, added = cfg.add_settings(USER, cfg.fragment(PLUGIN_HOOKS))
        obj = json.loads(text)
        self.assertEqual(obj["permissions"]["allow"], ["Bash(make test)", "mcp__jev"])
        self.assertEqual(obj["env"]["FOO"], "1")
        self.assertEqual(cfg.remove_settings(text, added, USER), USER)

    def test_created_file_is_removed_again(self):
        text, added = cfg.add_settings(None, cfg.fragment(PLUGIN_HOOKS))
        self.assertIsNone(cfg.remove_settings(text, added, None))
        self.assertIsNone(cfg.remove_settings(None, added, None))

    def test_settings_env_is_never_touched(self):
        user = '{"env": {"DRYAS_DATA_ROOT": "elsewhere", "FOO": "1"}}'
        text, added = cfg.add_settings(user, cfg.fragment(PLUGIN_HOOKS))
        self.assertEqual(json.loads(text)["env"], {"DRYAS_DATA_ROOT": "elsewhere", "FOO": "1"})
        self.assertEqual(added["env"], {})
        self.assertEqual(cfg.remove_settings(text, added, user), user)
        text, added = cfg.add_settings(None, cfg.fragment(PLUGIN_HOOKS))
        self.assertNotIn("env", json.loads(text))

    def test_unparseable_settings_raise(self):
        for bad in ("{not json", "[1, 2]"):
            with self.assertRaises(cfg.CloudError):
                cfg.add_settings(bad, cfg.fragment(PLUGIN_HOOKS))

    def test_later_user_edits_survive_removal(self):
        text, added = cfg.add_settings(USER, cfg.fragment(PLUGIN_HOOKS))
        obj = json.loads(text)
        obj["env"]["BAR"] = "2"
        out = json.loads(cfg.remove_settings(json.dumps(obj), added, USER))
        self.assertEqual(out["env"], {"FOO": "1", "BAR": "2"})
        self.assertNotIn("hooks", out)


class McpTest(unittest.TestCase):
    OTHER = '{"mcpServers": {"docs": {"command": "docs-server"}}}'  # no final newline, on purpose

    def test_add_keeps_other_servers_and_undo_restores_bytes(self):
        text, entry = cfg.add_mcp(self.OTHER, None)
        servers = json.loads(text)["mcpServers"]
        self.assertEqual(sorted(servers), ["docs", "jev"])
        self.assertEqual(servers["jev"]["args"], ["-X", "utf8", "${CLAUDE_PROJECT_DIR:-.}/.dryas/jev/jev_mcp.py"])
        self.assertEqual(cfg.remove_mcp(text, entry, self.OTHER), self.OTHER)

    def test_created_file_is_removed_again(self):
        text, entry = cfg.add_mcp(None, None)
        self.assertIsNone(cfg.remove_mcp(text, entry, None))

    def test_a_foreign_jev_server_stops_the_run(self):
        with self.assertRaises(cfg.CloudError):
            cfg.add_mcp(json.dumps({"mcpServers": {"jev": {"command": "my-jev"}}}), None)
        owned = {"command": "older-dryas"}
        text, _ = cfg.add_mcp(json.dumps({"mcpServers": {"jev": owned}}), owned)  # the one Dryas wrote is replaced
        self.assertEqual(json.loads(text)["mcpServers"]["jev"], cfg.mcp_entry())

    def test_malformed_mcp_raises(self):
        for bad in ("{", '{"mcpServers": []}', "[]"):
            with self.assertRaises(cfg.CloudError):
                cfg.add_mcp(bad, None)


class ClaudeMdTest(unittest.TestCase):
    def test_block_round_trip_keeps_the_repos_text(self):
        for orig in (None, "# Repo rules\n\nKeep tests green.\n", "# Repo\r\nCRLF lines\r\nno final newline"):
            rec = {}
            new = cfg.claude_md(orig, "Dryas rules here", rec)
            self.assertIn("<!-- dryas:start -->\nDryas rules here\n<!-- dryas:end -->\n", new)
            if orig:
                self.assertTrue(new.startswith(orig))
            self.assertEqual(cfg.undo_claude_md(new, rec), orig)

    def test_second_insert_replaces_the_block(self):
        rec = {}
        twice = cfg.claude_md(cfg.claude_md("# Repo\n", "v1", rec), "v2", rec)
        self.assertEqual(twice.count("<!-- dryas:start -->"), 1)
        self.assertIn("v2", twice)
        self.assertEqual(cfg.undo_claude_md(twice, rec), "# Repo\n")


class GitignoreTest(unittest.TestCase):
    def test_lines_added_once_and_removed_exactly(self):
        for orig in (None, "node_modules/\n", "node_modules/", ".orchestrate/\nbuild/\n"):
            text, rec = cfg.add_gitignore(orig)
            for line in cfg.GITIGNORE:
                self.assertEqual(text.splitlines().count(line), 1, (orig, line))
            self.assertEqual(cfg.remove_gitignore(text, rec), orig)


class EdgeCaseTest(unittest.TestCase):
    """Added by the executor: real-file shapes the plan's round trips do not cover."""
    FRAG = cfg.fragment(PLUGIN_HOOKS)

    def test_settings_odd_shapes_come_back_byte_exact(self):
        shapes = (
            '{"z": 1,\r\n  "permissions": {"deny": ["Bash(rm:*)"]},\r\n  "a": [3, 2]}\r\n',  # CRLF, odd order
            '{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine"}]}]}}',
            '{"permissions": {"allow": ["mcp__jev"]}}',  # the user already allows jev: not ours to remove
            "{}",
        )
        for user in shapes:
            text, added = cfg.add_settings(user, self.FRAG)
            self.assertEqual(cfg.remove_settings(text, added, user), user, user)
        text, _ = cfg.add_settings(shapes[1], self.FRAG)
        self.assertEqual(len(json.loads(text)["hooks"]["PreToolUse"]), 2)

    def test_settings_second_add_changes_nothing(self):
        text, added = cfg.add_settings(USER, self.FRAG)
        again, added2 = cfg.add_settings(text, self.FRAG)
        self.assertEqual(json.loads(again), json.loads(text))
        self.assertEqual((added2["hooks"], added2["allow"]), ([], []))

    def test_users_own_allow_survives_removal(self):
        user = '{"permissions": {"allow": ["mcp__jev"]}}'
        text, added = cfg.add_settings(user, self.FRAG)
        self.assertEqual(json.loads(cfg.remove_settings(text, added, None))["permissions"]["allow"], ["mcp__jev"])

    def test_mcp_odd_shapes_come_back_byte_exact(self):
        for user in ('{"b": 1, "mcpServers": {}, "a": 2}\r\n', '{"other": true}', '{"mcpServers": {"x": {}}}\n'):
            text, entry = cfg.add_mcp(user, None)
            self.assertEqual(cfg.remove_mcp(text, entry, user), user, user)

    def test_mcp_removal_leaves_a_changed_jev_alone(self):
        text, entry = cfg.add_mcp(None, None)
        obj = json.loads(text)
        obj["mcpServers"]["jev"]["command"] = "edited"
        out = json.loads(cfg.remove_mcp(json.dumps(obj), entry, None))
        self.assertEqual(out["mcpServers"]["jev"]["command"], "edited")

    def test_mcp_rerun_is_stable(self):
        text, entry = cfg.add_mcp('{"mcpServers": {"docs": {}}}', None)
        again, entry2 = cfg.add_mcp(text, entry)
        self.assertEqual((again, entry2), (text, entry))

    def test_claude_md_with_the_block_already_there_and_a_trailing_blank_line(self):
        for orig in ("# R\n\n", "# R", "\n"):
            rec = {}
            new = cfg.claude_md(orig, "x", rec)
            self.assertEqual(new.count("<!-- dryas:start -->"), 1)
            self.assertEqual(cfg.undo_claude_md(new, rec), orig, repr(orig))

    def test_gitignore_with_lines_already_present(self):
        have = ".dryas/state/\n.orchestrate/\n"
        for orig in (have, have + ".dryas/**/__pycache__/\n", ".orchestrate/\r\nbuild/\r\n", "  .orchestrate/  \n"):
            text, rec = cfg.add_gitignore(orig)
            for line in cfg.GITIGNORE:
                self.assertEqual([x.strip() for x in text.splitlines()].count(line), 1, (orig, line))
            self.assertEqual(cfg.remove_gitignore(text, rec), orig, repr(orig))
        full = have + ".dryas/**/__pycache__/\n.claude/skills/**/__pycache__/\n"
        text, rec = cfg.add_gitignore(full)
        self.assertEqual((text, rec["added"]), (full, []))

    def test_gitignore_removal_keeps_lines_the_user_added_after(self):
        text, rec = cfg.add_gitignore("a\n")
        out = cfg.remove_gitignore(text + "later/\n", rec)
        self.assertEqual(out, "a\nlater/\n")


class RoundTripTest(unittest.TestCase):
    """init/update/remove leave the user's own config content and bytes as they were (interrogate B1, A5, B9, B12)."""
    FRAG = cfg.fragment(PLUGIN_HOOKS)
    EMPTY = ('{"hooks": {}}', '{"env": {}}', '{"permissions": {"allow": []}}', '{"permissions": {}}',
             '{"hooks": {"Stop": []}}', '{"hooks": {"PreToolUse": []}}',
             '{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}}',
             '{\n    "hooks": {},\n    "permissions": {\n        "allow": []\n    }\n}')  # 4 spaces, no final newline

    @staticmethod
    def _update(text, added, orig):
        """What dryas_cloud update does: take the earlier entries out, then add them again."""
        return cfg.add_settings(cfg.remove_settings(text, added, orig), RoundTripTest.FRAG)

    def test_empty_user_keys_survive_remove(self):
        for user in self.EMPTY:
            text, added = cfg.add_settings(user, self.FRAG)
            self.assertEqual(cfg.remove_settings(text, added, user), user, user)
            edited = json.loads(text)
            edited["later"] = 1  # a user edit after init: removal cannot fall back to the original bytes
            want = dict(json.loads(user), later=1)
            self.assertEqual(json.loads(cfg.remove_settings(json.dumps(edited), added, user)), want, user)

    def test_no_drift_after_three_updates(self):
        for user in self.EMPTY + (USER, None):
            text, added = cfg.add_settings(user, self.FRAG)
            first = text
            for _ in range(3):
                text, added = self._update(text, added, user)
                self.assertEqual(text, first, user)
            self.assertEqual(cfg.remove_settings(text, added, user), user, user)

    def test_removal_after_a_user_edit_keeps_the_files_format(self):
        user = '{\n    "a": "caf\u00e9"\n}'  # 4 spaces, no final newline, non-ASCII
        text, added = cfg.add_settings(user, self.FRAG)
        obj = json.loads(text)
        obj["b"] = 2
        out = cfg.remove_settings(cfg.dump(obj, text), added, user)
        self.assertEqual(out, '{\n    "a": "caf\u00e9",\n    "b": 2\n}')

    def test_dump_keeps_indent_and_readable_text(self):
        for user, unit in (('{\n    "a": "\u00e9t\u00e9"\n}\n', "    "), ('{\n\t"a": "\u00e9t\u00e9"\n}\n', "\t"),
                           ('{"a": "\u00e9t\u00e9"}', "  ")):
            for text in (cfg.add_settings(user, self.FRAG)[0], cfg.add_mcp(user, None)[0]):
                self.assertIn('"\u00e9t\u00e9"', text)
                self.assertNotIn("\\u00e9", text)
                self.assertTrue(text.startswith("{\n" + unit + '"'), (user, text[:20]))
                self.assertEqual(text.endswith("\n"), user.endswith("\n"), user)
        text, _ = cfg.add_settings(None, self.FRAG)
        self.assertTrue(text.startswith('{\n  "') and text.endswith("}\n"))

    def test_gitignore_covers_skill_bytecode(self):
        self.assertIn(".claude/skills/**/__pycache__/", cfg.GITIGNORE)
        text, rec = cfg.add_gitignore(None)
        self.assertIn(".claude/skills/**/__pycache__/\n", text)
        self.assertIsNone(cfg.remove_gitignore(text, rec))


if __name__ == "__main__":
    unittest.main()
