import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _d in (HERE, ROOT / "tools", ROOT / "claude" / "jev"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
import cloud_check as cc
import cloud_fixtures as fx
import cloud_plan as cp

OPTS = {"prefix": "", "design": False, "own": [], "confirm_own": [], "persist_memory": False}


class CorePlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty = Path(tempfile.mkdtemp())
        cls.plan = cp.build(ROOT, OPTS, cls.empty)
        cp.finish(cls.plan)
        cls.files = cls.plan["files"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls.empty), True)

    def test_core_files(self):
        for rel in (".dryas/jev/gate.py", ".dryas/jev/cloud_hook.py", ".dryas/jev/cloud_check.py", ".dryas/jev/memnotes.py",
                    ".dryas/jev/chain.json", ".dryas/bin/dryas-py", ".dryas/pstack/cleanup.md",
                    ".dryas/docs/dryas-workflow.md", ".dryas/licenses/LICENSE-dryas", ".dryas/licenses/LICENSE-superpowers",
                    ".dryas/NOTICE", ".dryas/VERSION", ".claude/skills/orchestrate/SKILL.md",
                    ".claude/skills/interrogate/SKILL.md", ".claude/commands/tune.md", ".claude/commands/dryas-cloud.md",
                    ".claude/agents/executor.md"):
            self.assertIn(rel, self.files)
        for rel in self.files:
            self.assertFalse("/tests/" in rel or "__pycache__" in rel or rel.startswith(".dryas/ruflo"), rel)
            self.assertFalse("benchmark-checklist/" in rel or rel.endswith("/retro.md"), rel)
        self.assertEqual(self.plan["skipped"], [])
        if os.name != "nt":
            self.assertTrue(self.files[".dryas/bin/dryas-py"]["exec"])

    def test_chain_json_keeps_placeholders_and_drops_extras(self):
        c = json.loads(self.files[".dryas/jev/chain.json"]["data"])
        by = {s["name"]: s for stages in c.values() for s in stages}
        self.assertEqual(by["scope-lock"]["cmd"][-1], "$CD/jev/scope_lock.py")
        self.assertIs(by["ruflo-pre-bash"].get("enabled"), False)
        self.assertIs(by["flowobserve"].get("enabled"), False)
        for name in ("jev-gate", "mem-session-end", "mem-notes"):
            self.assertNotEqual(by[name].get("enabled"), False, name)

    def test_every_planned_file_passes_the_scan(self):
        hits = []
        for rel, e in self.files.items():
            try:
                hits += cc.scan_text(rel, e["data"].decode("utf-8"))
            except UnicodeDecodeError:
                continue
        self.assertEqual(hits, [])

    def test_version_notice_and_records(self):
        v = self.files[".dryas/VERSION"]["data"].decode("utf-8")
        self.assertRegex(v, r"\Aversion: \d+\.\d+\.\d+\S*\ncommit: \S+\nfiles: [0-9a-f]{64}\n\Z")
        notice = self.files[".dryas/NOTICE"]["data"].decode("utf-8").splitlines()
        for rel, e in self.files.items():
            self.assertIn(e["notice"], notice, rel)
            self.assertEqual((e["group"], e["licence"]), ("dryas", "MIT"), rel)
        self.assertEqual(self.files[".claude/skills/plan/SKILL.md"]["source"], "claude/skills/plan/SKILL.md")

    def test_dryas_cloud_command(self):
        text = self.files[".claude/commands/dryas-cloud.md"]["data"].decode("utf-8")
        self.assertIn('Bash(".dryas/bin/dryas-py" ".dryas/jev/cloud_check.py":*)', text)
        self.assertIn('".dryas/bin/dryas-py" ".dryas/jev/cloud_check.py" --repo "$PWD"', text)
        self.assertIn("disable-model-invocation: true", text)

    def test_persist_memory_adds_the_notes_folder(self):
        plan = cp.build(ROOT, dict(OPTS, persist_memory=True), self.empty)
        self.assertEqual(plan["files"][".dryas/memory/notes/.gitkeep"]["data"], b"")
        self.assertNotIn(".dryas/memory/notes/.gitkeep", self.files)


class PrefixTest(unittest.TestCase):
    def test_prefix_renames_the_copies(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(d), True)
        f = cp.build(ROOT, dict(OPTS, prefix="x-"), d)["files"]
        self.assertIn("\nname: x-plan\n", f[".claude/skills/x-plan/SKILL.md"]["data"].decode("utf-8"))
        self.assertIn(".claude/commands/x-wreview.md", f)
        self.assertIn("\nname: x-executor\n", f[".claude/agents/x-executor.md"]["data"].decode("utf-8"))
        self.assertNotIn(".claude/skills/plan/SKILL.md", f)


class DesignTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)

    def test_design_plugins_come_from_components_json(self):
        self.assertEqual(sorted(cp.design_plugins(ROOT)), sorted(cp.DESIGN))

    def test_licensed_design_skills_are_copied_with_their_licence(self):
        plan = cp.build(ROOT, dict(OPTS, design=True), fx.design_config(self.base))
        cp.finish(plan)
        f = plan["files"]
        self.assertEqual(plan["skipped"], [])
        for s in fx.UI_SKILLS + ("impeccable",):
            self.assertEqual(f[".claude/skills/%s/SKILL.md" % s]["group"], "design", s)
        self.assertIn('".claude/skills/ui-ux-pro-max/scripts/search.py"',
                      f[".claude/skills/ui-ux-pro-max/SKILL.md"]["data"].decode("utf-8"))
        self.assertIn("MIT License", f[".dryas/licenses/ui-ux-pro-max-LICENSE"]["data"].decode("utf-8"))
        self.assertIn("Apache License", f[".dryas/licenses/impeccable-LICENSE"]["data"].decode("utf-8"))
        self.assertIn(".dryas/licenses/impeccable-NOTICE.md", f)
        notice = f[".dryas/NOTICE"]["data"].decode("utf-8")
        self.assertIn("- impeccable@impeccable 9.9.9 (Apache-2.0): .dryas/licenses/impeccable-LICENSE", notice)
        self.assertIn("- ui-ux-pro-max@ui-ux-pro-max-skill 9.9.9 (MIT): .dryas/licenses/ui-ux-pro-max-LICENSE", notice)
        if os.name != "nt":
            self.assertTrue(f[".claude/skills/impeccable/scripts/impeccable"]["exec"])

    def test_unconfirmed_licence_is_skipped(self):
        plan = cp.build(ROOT, dict(OPTS, design=True), fx.design_config(self.base, impeccable_licence=False))
        self.assertNotIn(".claude/skills/impeccable/SKILL.md", plan["files"])
        self.assertIn(("impeccable@impeccable", "licence not confirmed (Apache-2.0 text not found)"), plan["skipped"])
        self.assertIn(".claude/skills/design/SKILL.md", plan["files"])

    def test_skill_needing_pip_package_is_skipped(self):
        plan = cp.build(ROOT, dict(OPTS, design=True), fx.design_config(self.base, pip_skill="slides"))
        self.assertNotIn(".claude/skills/slides/SKILL.md", plan["files"])
        self.assertIn(("ui-ux-pro-max@ui-ux-pro-max-skill/slides", "scripts/search.py needs numpy (not stdlib)"),
                      plan["skipped"])
        self.assertIn(".claude/skills/brand/SKILL.md", plan["files"])

    def test_not_installed_is_reported(self):
        plan = cp.build(ROOT, dict(OPTS, design=True), self.base / "nowhere")
        self.assertEqual(sorted(w for w, _ in plan["skipped"]), sorted(cp.DESIGN))


class OwnTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.cd = self.base / "cfg"

    def test_own_skill_is_copied(self):
        fx.own_skill(self.cd, "release-notes", "---\nname: release-notes\ndescription: d\n---\nWrite the notes.\n")
        plan = cp.build(ROOT, dict(OPTS, own=["release-notes"]), self.cd)
        cp.finish(plan)
        e = plan["files"][".claude/skills/release-notes/SKILL.md"]
        self.assertEqual((e["group"], e["licence"], e["licence_file"]), ("own", "own", ""))
        self.assertIn("- own skill release-notes", plan["files"][".dryas/NOTICE"]["data"].decode("utf-8"))

    def test_secret_shaped_text_stops_the_copy_until_confirmed(self):
        fx.own_skill(self.cd, "deploy", "---\nname: deploy\n---\napi_key: example-value-123\n")
        plan = cp.build(ROOT, dict(OPTS, own=["deploy"]), self.cd)
        self.assertNotIn(".claude/skills/deploy/SKILL.md", plan["files"])
        (what, why), = plan["skipped"]
        self.assertEqual(what, "deploy")
        self.assertIn("SKILL.md:4", why)
        self.assertIn("--confirm-own deploy", why)
        self.assertNotIn("example-value-123", why)
        plan = cp.build(ROOT, dict(OPTS, own=["deploy"], confirm_own=["deploy"]), self.cd)
        self.assertIn(".claude/skills/deploy/SKILL.md", plan["files"])

    def test_excluded_and_bad_names_are_refused(self):
        fx.own_skill(self.cd, "update-my-vault", "---\nname: update-my-vault\n---\nx\n")
        plan = cp.build(ROOT, dict(OPTS, own=["update-my-vault", "../escape", "absent"]), self.cd)
        self.assertEqual([w for w, _ in plan["skipped"]], ["update-my-vault", "../escape", "absent"])
        self.assertFalse(any("update-my-vault" in r for r in plan["files"]))


class AddedGapsTest(unittest.TestCase):
    """Gaps in the plan's tests: a wrong plan that copies without a licence, loses exec bits or lists too little."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.cd = self.base / "cfg"

    def test_every_licence_file_and_dryas_path_is_in_the_plan(self):
        plan = cp.build(ROOT, dict(OPTS, design=True, persist_memory=True), fx.design_config(self.base))
        cp.finish(plan)
        for rel, e in plan["files"].items():
            if e["licence_file"]:
                self.assertIn(e["licence_file"], plan["files"], rel)
        for rel in plan["files"]:
            self.assertTrue(rel.startswith((".dryas/", ".claude/")), rel)

    def test_apache_skill_without_its_own_licence_field_is_skipped(self):
        cd = fx.design_config(self.base)
        md = next(cd.glob("plugins/cache/impeccable/**/skills/impeccable/SKILL.md"))
        md.write_text("---\nname: impeccable\ndescription: d\n---\nx\n", encoding="utf-8")
        plan = cp.build(ROOT, dict(OPTS, design=True), cd)
        self.assertNotIn(".claude/skills/impeccable/SKILL.md", plan["files"])
        self.assertFalse(any(r.startswith(".dryas/licenses/impeccable") for r in plan["files"]))

    def test_design_licence_text_must_match_the_claimed_licence(self):
        cd = fx.design_config(self.base)
        (cd / "plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/9.9.9/LICENSE").write_text("All rights reserved.\n")
        plan = cp.build(ROOT, dict(OPTS, design=True), cd)
        self.assertNotIn(".claude/skills/design/SKILL.md", plan["files"])
        self.assertIn(("ui-ux-pro-max@ui-ux-pro-max-skill", "licence not confirmed (MIT text not found)"),
                      plan["skipped"])

    def test_other_excluded_names_are_refused(self):
        for n in ("fo-iterm", "claude-hud"):
            fx.own_skill(self.cd, n, "---\nname: %s\n---\nx\n" % n)
        plan = cp.build(ROOT, dict(OPTS, own=["fo-iterm", "claude-hud"], confirm_own=["fo-iterm", "claude-hud"]),
                        self.cd)
        self.assertEqual(sorted(w for w, _ in plan["skipped"]), ["claude-hud", "fo-iterm"])
        self.assertFalse(any("fo-iterm" in r or "claude-hud" in r for r in plan["files"]))

    def test_skill_with_a_licence_file_is_not_own(self):
        p = fx.own_skill(self.cd, "thirdparty", "---\nname: thirdparty\n---\nx\n")
        (p.parent / "LICENSE").write_text("MIT License\n")
        plan = cp.build(ROOT, dict(OPTS, own=["thirdparty"]), self.cd)
        self.assertFalse(any("thirdparty" in r for r in plan["files"]))
        self.assertEqual([w for w, _ in plan["skipped"]], ["thirdparty"])

    def test_own_skill_with_pip_helper_is_skipped(self):
        p = fx.own_skill(self.cd, "tool", "---\nname: tool\n---\nx\n")
        (p.parent / "run.py").write_text("import requests\n")
        plan = cp.build(ROOT, dict(OPTS, own=["tool"]), self.cd)
        self.assertFalse(any("/tool/" in r for r in plan["files"]))
        (what, why), = plan["skipped"]
        self.assertIn("requests", why)

    def test_own_skill_with_a_mac_path_is_skipped_and_stdlib_helper_kept_executable(self):
        p = fx.own_skill(self.cd, "ok", "---\nname: ok\n---\nx\n")
        h = p.parent / "scripts/run.py"
        h.parent.mkdir()
        h.write_text("import json\n")
        h.chmod(0o755)
        fx.own_skill(self.cd, "bad", "---\nname: bad\n---\nsee /Users/someone/x\n")
        plan = cp.build(ROOT, dict(OPTS, own=["ok", "bad"]), self.cd)
        self.assertEqual([w for w, _ in plan["skipped"]], ["bad"])
        if os.name != "nt":
            self.assertTrue(plan["files"][".claude/skills/ok/scripts/run.py"]["exec"])
            self.assertFalse(plan["files"][".claude/skills/ok/SKILL.md"]["exec"])

    def test_own_skill_gets_the_prefix(self):
        fx.own_skill(self.cd, "notes", "---\nname: notes\ndescription: d\n---\nx\n")
        plan = cp.build(ROOT, dict(OPTS, prefix="x-", own=["notes"]), self.cd)
        self.assertIn("\nname: x-notes\n", plan["files"][".claude/skills/x-notes/SKILL.md"]["data"].decode("utf-8"))


if __name__ == "__main__":
    unittest.main()


class HardeningTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.cd = self.base / "cfg"

    def _build(self, name, confirm=False):
        return cp.build(ROOT, dict(OPTS, own=[name], confirm_own=[name] if confirm else []), self.cd)

    def test_symlink_in_own_skill_is_skipped(self):
        p = fx.own_skill(self.cd, "linky", "---\nname: linky\n---\nx\n")
        secret = self.base / "secret.txt"
        secret.write_text("outside the skill\n")
        try:
            os.symlink(str(secret), str(p.parent / "leak.txt"))
        except (OSError, NotImplementedError):
            self.skipTest("no symlinks here")
        plan = self._build("linky")
        self.assertFalse(any("leak.txt" in r for r in plan["files"]))
        self.assertIn(".claude/skills/linky/SKILL.md", plan["files"])
        self.assertFalse(any(b"outside the skill" in e["data"] for e in plan["files"].values()))

    def test_excluded_names_match_case_insensitively(self):
        fx.own_skill(self.cd, "Update-My-Vault", "---\nname: Update-My-Vault\n---\nx\n")
        plan = self._build("Update-My-Vault")
        self.assertFalse(any("ault" in r for r in plan["files"]))
        self.assertEqual([w for w, _ in plan["skipped"]], ["Update-My-Vault"])

    def test_binary_file_in_own_skill_needs_confirmation(self):
        p = fx.own_skill(self.cd, "bin", "---\nname: bin\n---\nx\n")
        (p.parent / "blob.dat").write_bytes(b"\xff\xfe\x00\x80binary")
        plan = self._build("bin")
        self.assertFalse(any(r.startswith(".claude/skills/bin/") for r in plan["files"]))
        (what, why), = plan["skipped"]
        self.assertEqual(what, "bin")
        self.assertIn("blob.dat", why)
        self.assertIn("--confirm-own bin", why)
        plan = self._build("bin", confirm=True)
        self.assertIn(".claude/skills/bin/blob.dat", plan["files"])

    def test_core_ships_no_unused_scripts(self):
        files = cp.build(ROOT, OPTS, self.cd)["files"]
        self.assertNotIn(".dryas/jev/rules_inject.py", files)

    def test_cloud_text_shares_the_home_state_pattern(self):
        import cloud_text as ct
        self.assertIs(ct.HOME_STATE, cc.HOME_STATE)
