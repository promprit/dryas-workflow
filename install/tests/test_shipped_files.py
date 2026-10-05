import json, unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
CLAUDE = REPO / "claude"


def hook_commands(frag):
    for comp in frag.values():
        for ev, groups in comp.get("hooks", {}).items():
            for g in groups:
                for h in g["hooks"]:
                    yield ev, h["command"]


class ShippedFilesTest(unittest.TestCase):
    def setUp(self):
        self.frag = json.loads((CLAUDE / "settings.fragment.json").read_text(encoding="utf-8"))
        self.chain = json.loads((CLAUDE / "jev" / "chain.json").read_text(encoding="utf-8"))

    def test_no_posix_shell_in_hooks(self):
        text = (CLAUDE / "settings.fragment.json").read_text(encoding="utf-8")
        self.assertNotIn("/bin/sh", text)
        self.assertNotIn("/usr/bin/python3", text)
        for ev, cmd in hook_commands(self.frag):
            self.assertTrue(cmd.startswith('"$PY" -X utf8 "$CD/'), (ev, cmd))

    def test_chain_stages_use_py(self):
        for kind, stages in self.chain.items():
            for st in stages:
                self.assertEqual(st["cmd"][:3], ["$PY", "-X", "utf8"], st["name"])
                self.assertNotIn("/bin/sh", json.dumps(st))

    def test_codex_enabled_stages(self):
        on = {st["name"] for stages in self.chain.values() for st in stages if "codex" in st.get("harness", [])}
        self.assertEqual(on, {"scope-lock", "jev-gate", "jev-route"})

    def test_only_scope_lock_is_per_file(self):
        per = {st["name"] for stages in self.chain.values() for st in stages if st.get("per_file")}
        self.assertEqual(per, {"scope-lock"})

    def test_ruflo_overrides(self):
        env = self.frag["ruflo"]["env"]
        self.assertEqual(env["RUFLO_HOOK_CLI_OVERRIDE"], "$PY_SAFE -X utf8 $CD_SAFE/ruflo/run.py cli")
        self.assertEqual(env["RUFLO_MCP_CLI_OVERRIDE"], "$CD/ruflo/mcp-shim/bin/cli.js")

    def test_md_files_use_tokens(self):
        for p in list((CLAUDE / "commands").glob("*.md")) + list((CLAUDE / "skills").rglob("*.md")):
            self.assertNotIn("/usr/bin/python3", p.read_text(encoding="utf-8"), p)
        self.assertIn('"{{PY}}" -X utf8 "{{CD}}/jev/handoff.py" save --cwd "$PWD"',
                      (CLAUDE / "commands" / "handoff.md").read_text(encoding="utf-8"))

    def test_shims_gone(self):
        self.assertFalse((CLAUDE / "hooks").exists())
        self.assertFalse((CLAUDE / "jev" / "hooks").exists())


if __name__ == "__main__":
    unittest.main()
