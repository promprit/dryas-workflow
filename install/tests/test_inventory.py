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


class CheckTest(unittest.TestCase):
    def test_repo_has_no_unmapped_loss(self):
        self.assertEqual(inv.main(["--check"]), 0, "run: python tools/inventory.py --check")

    def test_lost_entry_fails(self):
        self.assertEqual(inv.check(["a:1", "a:2"], ["a:1"], {}, []), ["lost: a:2"])

    def test_mapped_entry_passes_only_when_target_exists(self):
        self.assertEqual(inv.check(["a:2"], ["b:2"], {"a:2": "b:2"}, []), [])
        self.assertEqual(inv.check(["a:2"], [], {"a:2": "b:2"}, []), ["lost: a:2 -> b:2, target missing"])

    def test_extra_mapping_needs_a_listed_component(self):
        self.assertEqual(inv.check(["a:2"], [], {"a:2": "extra:ruflo"}, ["ruflo"]), [])
        self.assertEqual(inv.check(["a:2"], [], {"a:2": "extra:nope"}, ["ruflo"]),
                         ["lost: a:2 -> extra:nope, no such optional component"])

    def test_map_stays_honest(self):
        self.assertEqual(inv.check(["a:1"], ["a:1"], {"a:1": "b:1"}, []), ["stale map: a:1 still exists"])
        self.assertEqual(inv.check([], [], {"z:9": "b:1"}, []), ["unknown map entry: z:9"])

    def test_write_refuses_to_replace_the_baseline(self):
        self.assertEqual(inv.main(["--write"]), 1)

    def test_baseline_is_the_current_1x_surface(self):
        data = json.loads((ROOT / inv.SNAPSHOT).read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "1.0.2")
        self.assertEqual(data["entries"], sorted(data["entries"]))
        self.assertGreater(len(data["entries"]), 150)

    def test_baseline_has_unix_newlines(self):
        self.assertNotIn(b"\r\n", (ROOT / inv.SNAPSHOT).read_bytes())

    def test_collector_error_exits_2(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "claude/jev").mkdir(parents=True)
        (t / "claude/jev/chain.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(inv.main(["--list", "--repo", str(t)]), 2)


class ReviewFixTest(unittest.TestCase):
    def _tmp(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        return t

    def test_kwargs_and_call_fields_are_collected(self):
        t = self._tmp()
        (t / "claude/jev").mkdir(parents=True)
        (t / "claude/jev/x.py").write_text(
            "import jevlog\n"
            "def _head():\n"
            "    if 1:\n"
            "        return {'head': 'x'}\n"
            "    return {}\n"
            "def f(n):\n"
            "    extra = {}\n"
            "    via, extra = 'c', {'parts': 1}\n"
            "    base = dict({'tool': 1}, **_head())\n"
            "    jevlog.append('g', dict(base, decision='d', **extra))\n", encoding="utf-8")
        got = inv._logs(t)
        for f in ("tool", "head", "decision", "parts"):
            self.assertIn("log_field:g:" + f, got)

    def test_real_gate_fields_are_collected(self):
        got = set(inv.collect(ROOT))
        self.assertIn("log_field:gate:parts", got)
        self.assertIn("log_field:gate:head", got)

    def test_tune_subcommands_are_collected(self):
        got = set(inv.collect(ROOT))
        for c in ("report", "apply", "record-compare"):
            self.assertIn("tune_cmd:" + c, got)

    def test_collect_isolates_the_environment_once(self):
        sentinel = str(self._tmp())
        seen = {}

        def spy(repo):
            for k in ("DRYAS_DATA_ROOT", "JEV_LOG_DIR", "JEV_THRESHOLDS", "HOME", "USERPROFILE"):
                seen[k] = os.environ.get(k)
            return set()

        with mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": sentinel, "HOME": sentinel, "USERPROFILE": sentinel}), \
                mock.patch.object(inv, "RUNTIME", (spy,)):
            inv.collect(ROOT)
        for k in ("DRYAS_DATA_ROOT", "HOME", "USERPROFILE"):
            self.assertNotEqual(seen[k], sentinel, k)
            self.assertTrue(seen[k], k)
        self.assertTrue(seen["JEV_LOG_DIR"])
        self.assertTrue(seen["JEV_THRESHOLDS"])

    def test_force_write_refuses_a_non_1x_tree(self):
        t = self._tmp()
        (t / "reference").mkdir()
        snap = t / inv.SNAPSHOT
        snap.write_text("{}", encoding="utf-8")
        with mock.patch.object(inv, "_version", return_value="2.0.0"), \
                mock.patch.object(inv, "collect", return_value=[]):
            rc = inv.main(["--write", "--force", "--repo", str(t)])
        self.assertEqual(rc, 1)
        self.assertEqual(snap.read_text(encoding="utf-8"), "{}")

    def test_flags_do_not_depend_on_parse_returning_the_parser(self):
        import argparse

        class FakeRC:
            OPTIONAL = ["ruflo"]

            @staticmethod
            def parse(argv):
                p = argparse.ArgumentParser()
                p.add_argument("--foo", action="store_true")
                p.parse_args(argv)
                return "not-the-parser"

        with mock.patch.object(inv, "_load", return_value=FakeRC):
            got = inv._flags(ROOT)
        self.assertIn("install_flag:--foo", got)
        self.assertIn("component:optional:ruflo", got)

    def test_load_does_not_write_bytecode_and_restores_the_flag(self):
        t = self._tmp()
        (t / "m.py").write_text("import sys\nSEEN = sys.dont_write_bytecode\n", encoding="utf-8")
        before = sys.dont_write_bytecode
        sys.dont_write_bytecode = False
        try:
            mod = inv._load(t / "m.py", "inventory_probe_m")
            self.assertTrue(mod.SEEN)
            self.assertFalse(sys.dont_write_bytecode)
        finally:
            sys.dont_write_bytecode = before

    def test_every_kind_has_entries(self):
        kinds = {e.split(":", 1)[0] for e in inv.collect(ROOT)}
        want = ("agent allowed_tool chain_stage command component env install_flag log log_field mcp_param "
                "mcp_server mcp_tool permission plugin_config plugin_dep plugin_hook setting settings_hook "
                "skill skill_ref threshold tool_ref tune_cmd tune_line").split()
        self.assertEqual([k for k in want if k not in kinds], [])
