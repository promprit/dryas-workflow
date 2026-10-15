"""Plan E (Dryas in cloud sessions) starts on plan D as merged. Each check names a D interface E calls. A failure
means D is not merged or renamed something: stop and report it; do not adapt E's tasks."""
import inspect
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for _d in (ROOT / "claude" / "jev", ROOT / "install", ROOT / "tools"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
SHAPE = '"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/jev/'


class DInterfacesTest(unittest.TestCase):
    def test_observe_kinds_and_memory_stages(self):
        import chain
        for kind in ("post", "subagent-stop", "session-start", "session-end", "precompact"):
            self.assertIn(kind, chain.OBSERVE_KINDS)
        self.assertTrue(callable(chain.observe))
        c = json.loads((ROOT / "claude/jev/chain.json").read_text(encoding="utf-8"))
        have = {(kind, s.get("name")) for kind, stages in c.items() for s in stages}
        for want in (("post", "mem-edit"), ("post", "gate-outcome"), ("subagent-stop", "mem-task"),
                     ("session-start", "mem-session-start"), ("session-end", "mem-session-end"),
                     ("precompact", "mem-session-end")):
            self.assertIn(want, have)

    def test_plugin_hooks_keep_one_shape(self):
        h = json.loads((ROOT / "claude/hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
        cmds = [(ev, x["command"]) for ev, groups in h.items() for g in groups for x in g["hooks"]]
        for ev, cmd in cmds:
            self.assertTrue(cmd.startswith(SHAPE), (ev, cmd))
        routed = {(ev, cmd[len(SHAPE):]) for ev, cmd in cmds}
        for want in (("PreToolUse", 'chain.py" pretool'), ("UserPromptSubmit", 'chain.py" prompt'),
                     ("PostToolUse", 'chain.py" post'), ("PostToolUseFailure", 'chain.py" post'),
                     ("SubagentStop", 'chain.py" subagent-stop'), ("SessionStart", 'chain.py" session-start'),
                     ("SessionEnd", 'chain.py" session-end'), ("PreCompact", 'chain.py" precompact')):
            self.assertIn(want, routed)

    def test_memory_hooks_read_the_notes_dir(self):
        import memhooks
        for stage in ("session-start", "session-end"):
            self.assertIn(stage, memhooks.STAGES)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with mock.patch.dict(os.environ, {"DRYAS_NOTES_DIR": d}):
            self.assertEqual(memhooks.notes_dir(d), d)
        self.assertEqual(list(inspect.signature(memhooks.index_notes).parameters), ["conn", "ns", "d"])

    def test_tune_rows_and_log_reader(self):
        import tune
        import tune_tasks
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(tune_tasks.rows([], [], [], []), {})
        self.assertEqual(tune.read("no-such-log", d), [])

    def test_design_component_and_installer_slots(self):
        import run_cmd
        self.assertIn("memory", run_cmd.OPTIONAL)
        comp = json.loads((ROOT / "install/components.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(comp), ["design", "ruflo", "superpowers"])
        installs = [c[3] for c in comp["design"]["commands"] if c[:3] == ["claude", "plugin", "install"]]
        self.assertEqual(sorted(installs), ["impeccable@impeccable", "ui-ux-pro-max@ui-ux-pro-max-skill"])

    def test_dryas_wrapper_and_version(self):
        self.assertIn("memory)", (ROOT / "claude/bin/dryas").read_text(encoding="utf-8"))
        self.assertIn("memory", (ROOT / "claude/bin/dryas.cmd").read_text(encoding="utf-8"))
        v = json.loads((ROOT / "claude/.claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
        self.assertTrue(v.startswith("2."), v)

    def test_shared_helpers_e_reuses(self):
        import claude_md_block
        import render
        import settings_merge
        import sync_codex_plugin
        for f in (claude_md_block.insert_block, claude_md_block.remove_block, render.chain_bytes, render.gate_blocks,
                  settings_merge.merge, settings_merge.unmerge, sync_codex_plugin.harness_blocks):
            self.assertTrue(callable(f))


if __name__ == "__main__":
    unittest.main()
