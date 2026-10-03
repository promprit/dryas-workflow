import contextlib, io, json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dryas_install as di
import ruflo_helpers as rh
from test_dryas_install import InstallTest as _Base

NAMES = ("auto-memory-hook.mjs", "hook-handler.cjs", "intelligence.cjs", "memory.cjs", "router.cjs", "session.cjs")


def fake(skip_anchor=None, mode=0o644):
    """Fake generator output: each file holds its anchors (old strings) plus filler."""
    out = {}
    for n in NAMES:
        text = "// head\n" + "".join(o + "body\n" for f, o, _ in rh.PATCHES if f == n and o != skip_anchor) + "// tail\n"
        out[n] = (text.encode(), mode)
    return out


def expected(n):
    text = "// head\n" + "".join(o + "body\n" for f, o, _ in rh.PATCHES if f == n) + "// tail\n"
    for f, o, new in rh.PATCHES:
        if f == n:
            text = text.replace(o, new)
    return text


class PatchTableTest(unittest.TestCase):
    def test_table_shape(self):
        self.assertEqual(tuple(rh.HELPERS), NAMES)
        self.assertEqual(len(rh.PATCHES), 5)
        self.assertEqual(sorted({f for f, _, _ in rh.PATCHES}), ["auto-memory-hook.mjs", "hook-handler.cjs", "intelligence.cjs"])

    def test_patch_text_output(self):
        for n in NAMES:
            self.assertEqual(rh.patch_text(n, expected_src(n)), expected(n))

    def test_patch_text_exact_replacement(self):
        out = rh.patch_text("intelligence.cjs", "const SESSION_DIR = path.join(PROJECT_ROOT, '.claude-flow', 'sessions');\n")
        self.assertEqual(out, "const SESSION_DIR = path.join(DATA_ROOT, '.claude-flow', 'sessions');\n")
        out = rh.patch_text("hook-handler.cjs", "function spawnDetachedHookRefresh(subcommand) {\n")
        self.assertTrue(out.startswith("function spawnDetachedHookRefresh(subcommand) {\n  return; // LIFT PATCH:"))

    def test_unpatched_file_passthrough(self):
        self.assertEqual(rh.patch_text("memory.cjs", "abc\n"), "abc\n")

    def test_anchor_zero_or_twice_raises(self):
        with self.assertRaises(rh.HelperError):
            rh.patch_text("hook-handler.cjs", "nothing here\n")
        a = rh.PATCHES[0][1]
        with self.assertRaises(rh.HelperError):
            rh.patch_text("hook-handler.cjs", a + a + rh.PATCHES[1][1])


def expected_src(n):
    return "// head\n" + "".join(o + "body\n" for f, o, _ in rh.PATCHES if f == n) + "// tail\n"


class HelperInstallTest(_Base):
    def setUp(self):
        super().setUp()
        self.hdir = self.cd / "ruflo" / "helpers"

    def test_missing_anchor_aborts(self):
        rh.generate = lambda b: fake(skip_anchor=rh.PATCHES[3][1])
        with self.assertRaises(rh.HelperError) as cm:
            rc = self.install(["core", "ruflo"])
            if rc:
                raise rh.HelperError("rc=%s" % rc)
        self.assertFalse(self.hdir.exists() and any(self.hdir.iterdir()))

    def test_patched_output_written_with_mode_and_recorded(self):
        rh.generate = lambda b: fake(mode=0o755)
        self.assertEqual(self.install(["core", "ruflo"]), 0)
        rec = json.loads((self.cd / ".dryas-installed.json").read_text())
        for n in NAMES:
            self.assertEqual((self.hdir / n).read_text(), expected(n))
            self.assertTrue((self.hdir / n).stat().st_mode & 0o100)
            self.assertIn("ruflo/helpers/" + n, rec["files"])

    def test_generator_called_with_ruflo_bin(self):
        seen = []
        rh.generate = lambda b: seen.append(b) or fake()
        self.install(["core", "ruflo"])
        self.assertEqual(seen, ["/b/ruflo"])

    def test_generator_failure_aborts(self):
        def boom(b):
            raise rh.HelperError("ruflo init failed")
        rh.generate = boom
        with self.assertRaises(rh.HelperError):
            rc = self.install(["core", "ruflo"])
            if rc:
                raise rh.HelperError("rc=%s" % rc)
        self.assertFalse(self.hdir.exists() and any(self.hdir.iterdir()))

    def test_dry_run_runs_nothing(self):
        def boom(b):
            raise AssertionError("generate must not run in dry mode")
        rh.generate = boom
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(self.install(["core", "ruflo"], dry=True), 0)
        self.assertIn("would generate Ruflo helpers with:", buf.getvalue())
        self.assertFalse(self.hdir.exists())

    def test_no_ruflo_no_generation(self):
        rh.generate = lambda b: self.fail("not wanted")
        self.install(["core"])
        self.assertFalse(self.hdir.exists())

    def _verify(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            di.verify(self.cd, ["ruflo"])
        return [l for l in buf.getvalue().splitlines() if "Ruflo helpers patched" in l]

    def test_verify_passes_when_patched(self):
        rh.generate = lambda b: fake()
        self.install(["core", "ruflo"])
        self.assertEqual(rh.check(self.hdir), [])
        lines = self._verify()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("PASS"))

    def test_verify_fails_on_missing_helper(self):
        rh.generate = lambda b: fake()
        self.install(["core", "ruflo"])
        (self.hdir / "router.cjs").unlink()
        self.assertTrue(any("router.cjs" in p for p in rh.check(self.hdir)))
        lines = self._verify()
        self.assertTrue(lines and lines[0].startswith("FAIL") and "router.cjs" in lines[0])

    def test_verify_fails_on_unpatched_helper(self):
        rh.generate = lambda b: fake()
        self.install(["core", "ruflo"])
        (self.hdir / "intelligence.cjs").write_text(expected_src("intelligence.cjs"))
        self.assertTrue(any("intelligence.cjs" in p for p in rh.check(self.hdir)))
        lines = self._verify()
        self.assertTrue(lines and lines[0].startswith("FAIL") and "intelligence.cjs" in lines[0])

    def test_uninstall_removes_helpers(self):
        rh.generate = lambda b: fake()
        self.install(["core", "ruflo"])
        self.assertTrue(self.hdir.exists())
        di.uninstall(self.cd)
        for n in NAMES:
            self.assertFalse((self.hdir / n).exists())


del _Base  # keep only HelperInstallTest's own copy collected
