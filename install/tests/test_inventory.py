"""No-loss inventory (owned core, plan 0): every 1.x surface stays or is mapped."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import inventory as inv  # noqa: E402


def _static(repo):
    got = set()
    for c in inv.STATIC:
        got |= c(repo)
    return got


class StaticTest(unittest.TestCase):
    def test_static_surfaces_of_this_repo(self):
        got = _static(ROOT)
        for e in (
            "mcp_server:claude:jev", "mcp_server:codex:jev",
            "plugin_dep:claude:superpowers", "plugin_config:claude:openrouter_key",
            "command:claude:commit", "command:claude:wplan", "command:claude:orchestrate",
            "skill:claude:orchestrate", "skill:codex:wplan", "agent:claude:executor",
            "allowed_tool:claude:skill/orchestrate:mcp__plugin_ruflo-core_ruflo__swarm_init",
            "allowed_tool:claude:skill/orchestrate:Skill(superpowers:brainstorming)",
            "allowed_tool:claude:command/wplan:Skill(superpowers:writing-plans)",
            "skill_ref:claude:superpowers:brainstorming", "tool_ref:codex:memory_search",
            "plugin_hook:claude:PreToolUse:Bash|Edit|Write|MultiEdit|NotebookEdit:chain.py pretool",
            "plugin_hook:codex:PreToolUse:Bash|apply_patch|Edit|Write:chain.py pretool --harness codex",
            "plugin_hook:claude:PreCompact:*:compact_keep.py",
            "chain_stage:pretool:scope-lock:core", "chain_stage:pretool:ruflo-pre-bash:ruflo",
            "chain_stage:prompt:jev-route:jev",
            "settings_hook:ruflo:PostToolUse:Write|Edit|MultiEdit:hook-handler.cjs post-edit",
            "permission:core:deny:Skill(superpowers:executing-plans)",
            "env:ruflo:CLAUDE_FLOW_MEMORY_PATH", "setting:core:model",
            "component:ruflo", "component:superpowers", "component:design",
        ):
            self.assertIn(e, got)

    def test_allowed_tools_keep_parenthesised_commas(self):
        got = _static(ROOT)
        planfile = [e for e in got if e.startswith("allowed_tool:claude:skill/orchestrate:Bash(") and "planfile.py" in e]
        self.assertEqual(len(planfile), 1, planfile)

    def test_generated_codex_copies_are_not_scanned(self):
        self.assertFalse([e for e in _static(ROOT) if ":jev/" in e or ":pstack/" in e])


class MalformedTest(unittest.TestCase):
    def test_bad_json_names_the_file(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "claude/jev").mkdir(parents=True)
        (t / "claude/jev/chain.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(inv.InventoryError) as cm:
            inv._hooks(t)
        self.assertIn("chain.json", str(cm.exception))


class RuntimeTest(unittest.TestCase):
    def test_runtime_surfaces_of_this_repo(self):
        got = set(inv.collect(ROOT))
        for e in (
            "mcp_tool:jev:jev_judge", "mcp_tool:jev:log_dispatch", "mcp_param:jev:log_dispatch.attempt",
            "mcp_param:jev:log_override.jev_confidence",
            "log:gate", "log:route", "log:dispatch", "log:escalations", "log:overrides",
            "log_field:gate:decision", "log_field:gate:via", "log_field:route:route_conf",
            "log_field:dispatch:task", "log_field:review:critical", "log_field:escalations:to_model",
            "log_field:*:ts", "log_field:*:session_id",
            "component:optional:ruflo", "component:optional:superpowers",
            "install_flag:--no-ruflo", "install_flag:--no-superpowers", "install_flag:--no-jev",
            "install_flag:--openrouter-key", "install_flag:--no-flowobserve", "install_flag:--harness=codex",
            "threshold:gate.min_confidence", "threshold:dispatch.haiku_default",
            "threshold:escalation.opus_failures_before_fable",
            "tune_line:Jev calibration", "tune_line:Tool calls", "tune_line:Haiku->Sonnet climb rate (healthy at or under escalation.haiku_climb_max)",
            "tune_line:Swarm vs plain token ratio", "tune_line:Proposals (apply only after approval)",
            "tune_line:PROPOSALS_JSON",
        ):
            self.assertIn(e, got)

    def test_collect_is_sorted_and_stable(self):
        a = inv.collect(ROOT)
        self.assertEqual(a, sorted(a))
        self.assertEqual(a, inv.collect(ROOT))

    def test_user_state_does_not_leak(self):
        before = inv.collect(ROOT)
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "jev/logs").mkdir(parents=True)
        (t / "jev/thresholds.json").write_text(json.dumps({"gate": {"mine_only": 1}}), encoding="utf-8")
        (t / "jev/logs/gate.jsonl").write_text('{"decision":"allow","mine_only":1}\n', encoding="utf-8")
        with mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": str(t), "JEV_LOG_DIR": str(t / "jev/logs")}):
            self.assertEqual(inv.collect(ROOT), before)


class LogFieldTest(unittest.TestCase):
    def test_self_reassigned_record_is_followed_without_recursion(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "claude/jev").mkdir(parents=True)
        (t / "claude/jev/x.py").write_text(
            "import jevlog\n"
            "def f(extra):\n"
            "    rec = {'a': 1}\n"
            "    rec = dict(rec, b=2, **extra)\n"
            "    jevlog.append('x', rec)\n", encoding="utf-8")
        got = inv._logs(t)
        self.assertIn("log:x", got)
        self.assertIn("log_field:x:a", got)
        self.assertIn("log_field:x:b", got)
