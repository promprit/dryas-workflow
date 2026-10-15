import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cloud_config as cfg
import cloud_plan as cp
import inventory as inv

TABLE = json.loads((ROOT / "reference/cloud-bindings.json").read_text(encoding="utf-8"))


def copied(kind):
    return sorted(k.split(":")[2] for k, v in TABLE["entries"].items() if k.startswith(kind) and v.startswith("copy:"))


class CloudBindingsTest(unittest.TestCase):
    def test_table_covers_every_core_component(self):
        self.assertEqual(inv.cloud_check(inv.collect(ROOT), TABLE), [])

    def test_copied_skills_commands_and_agents_match_the_plan(self):
        self.assertEqual(copied("skill:claude:"), sorted(cp.CORE_SKILLS))
        self.assertEqual(copied("command:claude:"), sorted(cp.CORE_COMMANDS))
        self.assertEqual(copied("agent:claude:"), sorted(cp.CORE_AGENTS))

    def test_copied_plugin_hooks_match_the_settings_hooks(self):
        made = cfg.hooks(json.loads((ROOT / "claude/hooks/hooks.json").read_text(encoding="utf-8")))
        got = {(ev, g.get("matcher") or "*", h["command"][len(cfg.ENTRY):])
               for ev, groups in made.items() for g in groups for h in g["hooks"]}
        want = set()
        for k, v in TABLE["entries"].items():
            if k.startswith("plugin_hook:claude:") and v.startswith("copy:"):
                ev, matcher, key = k[len("plugin_hook:claude:"):].split(":", 2)
                want.add((ev, matcher, key))
        self.assertEqual(got, want)

    def test_not_copied_names_match_the_plan(self):
        self.assertEqual(TABLE["not_copied"], dict(cp.NOT_COPIED))

    def test_cloud_check_reports_gaps(self):
        cur = ["command:claude:a", "command:claude:b", "install_flag:--x"]
        table = {"entries": {"command:claude:a": "copy: .claude/commands/a.md", "command:claude:gone": "exclude: retired",
                             "command:claude:b": "maybe"}}
        self.assertEqual(inv.cloud_check(cur, table), [
            "cloud table: command:claude:gone is not in the inventory",
            "cloud table: command:claude:b needs copy:, opt-in: or exclude: and a reason"])
        self.assertEqual(inv.cloud_check(cur, {"entries": {}})[0],
                         "cloud table: command:claude:a is neither copied nor excluded")
        self.assertEqual(inv.cloud_check(cur, []), ['cloud table: reference/cloud-bindings.json has no "entries" object'])

    def test_docs_name_the_opt_ins(self):
        doc = (ROOT / "docs/cloud-sessions.md").read_text(encoding="utf-8")
        for want in ("dryas cloud init", "--yes", "DRYAS_JUDGE=jev", "OPENROUTER_API_KEY", "openrouter.ai",
                     "--persist-memory", ".dryas/jev/cloud_check.py", "DRYAS_CLOUD_HOOKS"):
            self.assertIn(want, doc)
        self.assertIn("cloud-bindings.json", (ROOT / "reference/README.md").read_text(encoding="utf-8"))
        self.assertRegex((ROOT / "GLOSSARY.md").read_text(encoding="utf-8"), r"(?m)^- \*\*repo copy\*\*: \S")


class CloudBindingsExtraTest(unittest.TestCase):
    """Gaps the plan's tests leave: an empty reason, a wrong value type, and docs that name things the code lacks."""

    def test_blank_reason_and_non_string_value_are_reported(self):
        cur = ["command:claude:a", "command:claude:b"]
        table = {"entries": {"command:claude:a": "exclude:   ", "command:claude:b": 3}}
        self.assertEqual(inv.cloud_check(cur, table), [
            "cloud table: command:claude:a needs copy:, opt-in: or exclude: and a reason",
            "cloud table: command:claude:b needs copy:, opt-in: or exclude: and a reason"])

    def test_every_entry_has_a_reason(self):
        for k, v in TABLE["entries"].items():
            self.assertTrue(v.startswith(inv.CLOUD_VALUES) and v.split(":", 1)[1].strip(), k)
        for k, v in TABLE["not_copied"].items():
            self.assertTrue(v.strip(), k)

    def test_no_component_is_both_copied_and_excluded(self):
        for k in TABLE["entries"]:
            self.assertNotIn(k, TABLE["not_copied"])
        self.assertEqual(len(TABLE["entries"]), len(set(TABLE["entries"])))

    def test_check_runs_the_cloud_table(self):
        import contextlib
        import io
        from unittest import mock
        out = io.StringIO()
        with mock.patch.object(inv, "cloud_check", return_value=["cloud table: planted"]), \
                contextlib.redirect_stdout(out):
            code = inv.main(["--check"])
        self.assertEqual(code, 1)
        self.assertIn("cloud table: planted", out.getvalue())

    def test_docs_commands_and_flags_exist_in_the_code(self):
        doc = (ROOT / "docs/cloud-sessions.md").read_text(encoding="utf-8")
        code = (ROOT / "tools/dryas_cloud.py").read_text(encoding="utf-8")
        for flag in ("--yes", "--force", "--prefix", "--with-design", "--with-own", "--confirm-own",
                     "--persist-memory", "--repo"):
            self.assertIn(flag, doc)
            self.assertIn(flag, code, flag)
        for sub in ("init", "update", "remove", "check"):
            self.assertIn("dryas cloud " + sub, doc)
            self.assertIn('"%s"' % sub, code, sub)

    def test_docs_describe_the_current_behaviour(self):
        doc = (ROOT / "docs/cloud-sessions.md").read_text(encoding="utf-8")
        for want in ("--no-design", "--without-own", "--no-persist-memory", ".claude/skills/**/__pycache__/",
                     "Stop, PreCompact and SessionEnd", "memnotes.py export", "before the final commit",
                     "custom data root", "plugin registry", "disabled but still installed",
                     "keeps what it cannot rebuild", "only dropping its option removes",
                     "live `.claude/settings.json`", "memory note", "no-op without a notes folder",
                     "codex_event.py", "ruflo_import.py", "chain.py", "memcli.py"):
            self.assertIn(want, doc)

    def test_docs_paths_exist(self):
        doc = (ROOT / "docs/cloud-sessions.md").read_text(encoding="utf-8")
        for rel in ("tools/dryas_cloud.py", "claude/jev/cloud_check.py", "claude/jev/cloud_hook.py",
                    "reference/cloud-bindings.json", "install/install.sh", "install/install.ps1",
                    "claude/bin/dryas", "claude/commands/dryas-cloud.md"):
            self.assertTrue((ROOT / rel).exists(), rel)
        for rel in ("reference/cloud-bindings.json",):
            self.assertIn(rel, doc)

    def test_docs_env_names_are_read_by_the_code(self):
        hook = (ROOT / "claude/jev/cloud_hook.py").read_text(encoding="utf-8")
        self.assertIn("DRYAS_CLOUD_HOOKS", hook)
        corpus = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "claude/jev").glob("*.py"))
        self.assertIn("DRYAS_JUDGE", corpus)
        self.assertIn("OPENROUTER_API_KEY", corpus)

    def test_docs_have_no_mac_paths(self):
        doc = (ROOT / "docs/cloud-sessions.md").read_text(encoding="utf-8")
        self.assertNotIn("/Users/", doc)
        self.assertNotIn("/Volumes/", doc)


if __name__ == "__main__":
    unittest.main()
