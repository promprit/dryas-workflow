import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

JEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JEV)
import paths

PROBE = "import sys; sys.path.insert(0, sys.argv[1]); import paths; print(paths.copy_root()); print(paths.data_root())"


class EnvPathTest(unittest.TestCase):
    def env(self, **kw):
        p = mock.patch.dict(os.environ, kw)
        p.start()
        self.addCleanup(p.stop)

    def test_literal_project_dir_is_expanded(self):
        self.env(DRYAS_DATA_ROOT="$CLAUDE_PROJECT_DIR/.dryas/state", CLAUDE_PLUGIN_ROOT="${CLAUDE_PROJECT_DIR}/.dryas",
                 CLAUDE_PROJECT_DIR="work/repo", JEV_LOG_DIR="")
        self.assertEqual(paths.data_root(), "work/repo/.dryas/state")
        self.assertEqual(paths.plugin_root(), "work/repo/.dryas")
        self.assertEqual(paths.log_dir(), os.path.join("work/repo/.dryas/state", "jev", "logs"))

    def test_mcp_default_form_is_expanded(self):
        self.env(DRYAS_DATA_ROOT="${CLAUDE_PROJECT_DIR:-.}/.dryas/state", CLAUDE_PLUGIN_ROOT="${CLAUDE_PROJECT_DIR:-.}/.dryas",
                 CLAUDE_PROJECT_DIR="work/repo")
        self.assertEqual(paths.data_root(), "work/repo/.dryas/state")
        self.assertEqual(paths.plugin_root(), "work/repo/.dryas")
        self.env(CLAUDE_PROJECT_DIR="")
        self.assertEqual(paths.plugin_root(), os.path.dirname(JEV))  # unset: the code's own folder, never "."

    def test_unset_project_dir_falls_back(self):
        self.env(DRYAS_DATA_ROOT="$CLAUDE_PROJECT_DIR/.dryas/state", CLAUDE_PLUGIN_ROOT="$CLAUDE_PROJECT_DIR/.dryas",
                 CLAUDE_PROJECT_DIR="", JEV_LOG_DIR="")
        self.assertEqual(paths.data_root(), os.path.join(os.path.expanduser("~"), ".dryas"))
        self.assertEqual(paths.plugin_root(), os.path.dirname(JEV))

    def test_other_dollar_values_are_kept(self):
        self.env(DRYAS_DATA_ROOT=os.path.join("C:", "profiles", "a$b", ".dryas"), CLAUDE_PLUGIN_ROOT="")
        self.assertEqual(paths.data_root(), os.path.join("C:", "profiles", "a$b", ".dryas"))
        self.assertEqual(paths.plugin_root(), os.path.dirname(JEV))


class CopyRootTest(unittest.TestCase):
    def test_a_repo_copy_keeps_state_beside_itself(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        jev = os.path.join(d, ".dryas", "jev")
        os.makedirs(jev)
        shutil.copy(os.path.join(JEV, "paths.py"), jev)
        env = {k: v for k, v in os.environ.items() if k not in ("DRYAS_DATA_ROOT", "CLAUDE_PLUGIN_ROOT")}

        def probe():
            p = subprocess.run([sys.executable, "-c", PROBE, jev], capture_output=True, text=True, env=env, timeout=30)
            return p.stdout.splitlines()

        self.assertEqual(probe()[0], "")  # no manifest: not a copy, the default data root applies
        with open(os.path.join(d, ".dryas", "manifest.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertEqual(probe(), [os.path.join(d, ".dryas"), os.path.join(d, ".dryas", "state")])


class EnvPathEdgeTest(unittest.TestCase):
    """Added: unset vs empty project dir, spaces and backslashes in it, look-alike names, copies reached via ..."""

    def env(self, drop=(), **kw):
        p = mock.patch.dict(os.environ, kw)
        p.start()
        self.addCleanup(p.stop)
        for k in drop:
            os.environ.pop(k, None)

    def test_project_dir_absent_from_env_falls_back(self):
        self.env(drop=("CLAUDE_PROJECT_DIR",), DRYAS_DATA_ROOT="${CLAUDE_PROJECT_DIR:-.}/.dryas/state",
                 CLAUDE_PLUGIN_ROOT="$CLAUDE_PROJECT_DIR/.dryas")
        self.assertEqual(paths._env_path("DRYAS_DATA_ROOT"), "")
        self.assertEqual(paths.data_root(), os.path.join(os.path.expanduser("~"), ".dryas"))
        self.assertEqual(paths.plugin_root(), os.path.dirname(JEV))

    def test_project_dir_with_spaces_and_backslashes_is_inserted_verbatim(self):
        for proj in ("/tmp/my repo", "C:\\Users\\a b\\repo", "x\\1\\g<0>"):
            with self.subTest(proj=proj):
                self.env(DRYAS_DATA_ROOT="$CLAUDE_PROJECT_DIR/.dryas/state", CLAUDE_PROJECT_DIR=proj)
                self.assertEqual(paths.data_root(), proj + "/.dryas/state")

    def test_look_alike_names_are_not_expanded(self):
        for v in ("$CLAUDE_PROJECT_DIRS/state", "${CLAUDE_PROJECT_DIRX}/state", "$CLAUDE_PROJECT/state"):
            with self.subTest(v=v):
                self.env(DRYAS_DATA_ROOT=v, CLAUDE_PROJECT_DIR="work/repo")
                self.assertEqual(paths.data_root(), v)

    def test_every_occurrence_is_expanded(self):
        self.env(DRYAS_DATA_ROOT="$CLAUDE_PROJECT_DIR/a/${CLAUDE_PROJECT_DIR}", CLAUDE_PROJECT_DIR="r")
        self.assertEqual(paths.data_root(), "r/a/r")

    def test_unset_env_var(self):
        self.env(drop=("DRYAS_DATA_ROOT",))
        self.assertEqual(paths._env_path("DRYAS_DATA_ROOT"), "")


class CopyRootEdgeTest(unittest.TestCase):
    """Added: a copy under a path with spaces, reached through "..", and look-alikes that are not copies."""

    def make(self, parent_name=".dryas", manifest="file"):
        d = tempfile.mkdtemp(prefix="dry as ")
        self.addCleanup(shutil.rmtree, d, True)
        jev = os.path.join(d, parent_name, "jev")
        os.makedirs(jev)
        shutil.copy(os.path.join(JEV, "paths.py"), jev)
        m = os.path.join(d, parent_name, "manifest.json")
        if manifest == "file":
            with open(m, "w", encoding="utf-8") as f:
                f.write("{}")
        elif manifest == "dir":
            os.makedirs(m)
        return os.path.realpath(d), jev

    def probe(self, jev, **extra):
        env = {k: v for k, v in os.environ.items() if k not in ("DRYAS_DATA_ROOT", "CLAUDE_PLUGIN_ROOT")}
        env.update(extra)
        p = subprocess.run([sys.executable, "-c", PROBE, jev], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.splitlines()

    def test_copy_under_a_path_with_spaces_reached_through_dotdot(self):
        d, jev = self.make()
        twisted = os.path.join(d, ".dryas", "jev", "..", "jev")
        out = self.probe(twisted)
        self.assertEqual([os.path.realpath(x) for x in out], [os.path.join(d, ".dryas"), os.path.join(d, ".dryas", "state")])
        self.assertNotIn("..", out[0])

    def test_env_data_root_beats_the_copy(self):
        d, jev = self.make()
        out = self.probe(jev, DRYAS_DATA_ROOT="$CLAUDE_PROJECT_DIR/elsewhere", CLAUDE_PROJECT_DIR="proj")
        self.assertEqual(out[1], "proj/elsewhere")

    def test_not_a_copy(self):
        for parent, manifest in ((".dryas", "dir"), ("dryas", "file"), ("x.dryas", "file")):
            with self.subTest(parent=parent, manifest=manifest):
                d, jev = self.make(parent, manifest)
                out = self.probe(jev)
                self.assertEqual(out[0], "")
                self.assertEqual(out[1], os.path.join(os.path.expanduser("~"), ".dryas"))


if __name__ == "__main__":
    unittest.main()
