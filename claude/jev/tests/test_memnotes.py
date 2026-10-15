import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

JEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JEV)
import jevlog
import memdb
import memhooks
import memnotes
import memstore


class MemNotesTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.notes = os.path.join(self.d, "notes")
        os.makedirs(self.notes)
        self.cwd = os.path.join(self.d, "demo")
        os.makedirs(self.cwd)
        p = mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": self.d, "DRYAS_DB": os.path.join(self.d, "d.db"),
                                         "JEV_LOG_DIR": os.path.join(self.d, "logs"), "DRYAS_NOTES_DIR": self.notes,
                                         "JEV_SESSION_ID": "", "JEV_CWD": ""})
        p.start()
        self.addCleanup(p.stop)
        self.conn = memdb.connect()
        self.addCleanup(self.conn.close)
        self.ns = "demo"

    def start(self, sid="s1", ago=60.0):
        with memdb.tx(self.conn):
            self.conn.execute("INSERT INTO sessions (id, ns, started) VALUES (?, ?, ?)", (sid, self.ns, time.time() - ago))

    def export(self, sid="s1"):
        return memnotes.export(self.conn, {"session_id": sid, "cwd": self.cwd})

    def test_export_writes_a_redacted_note(self):
        self.start()
        memstore.store(self.conn, self.ns, "Retry flaky calls", "Use the retry helper. password = hunter2hunter2",
                       check_content=False)
        with memdb.tx(self.conn):
            self.conn.execute("INSERT INTO tasks (task_id, ns, title, tier_start, tier_end, outcome, started, ended) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              ("feat:1", self.ns, "Add the parser", "haiku", "sonnet", "merged", time.time() - 30,
                               time.time()))
        jevlog.append("dispatch", dict(task="feat:1", role="coder", tier="haiku", attempt=1, tokens=1200))
        path = self.export()
        self.assertEqual(os.path.dirname(path), self.notes)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("---\nname: Dryas session "))
        for want in ("## Lessons and decisions", "Retry flaky calls", "## Tasks",
                     "feat:1 Add the parser: merged (haiku -> sonnet)", "## Task numbers (/tune)", "start_tier=haiku",
                     "tokens=1200.0"):
            self.assertIn(want, text)
        self.assertNotIn("hunter2hunter2", text)

    def test_nothing_to_keep_writes_nothing(self):
        self.start()
        self.assertIsNone(self.export())
        self.assertEqual(os.listdir(self.notes), [])

    def test_earlier_sessions_are_left_out(self):
        memstore.store(self.conn, self.ns, "Old lesson", "From an earlier session.", created=time.time() - 3600)
        self.start()
        memstore.store(self.conn, self.ns, "New lesson", "From this session.")
        with open(self.export(), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("New lesson", text)
        self.assertNotIn("Old lesson", text)

    def test_session_id_cannot_escape_the_notes_dir(self):
        self.start("../../x y")
        memstore.store(self.conn, self.ns, "Lesson", "Body.")
        path = self.export("../../x y")
        self.assertEqual(os.path.dirname(path), self.notes)
        self.assertTrue(os.path.basename(path).endswith("-xy.md"), path)

    def test_note_is_indexed_by_the_next_session_start(self):
        self.start()
        memstore.store(self.conn, self.ns, "Retry flaky calls", "Use the retry helper.")
        self.export()
        self.assertEqual(memhooks.index_notes(self.conn, self.ns, self.notes)["indexed"], 1)
        row = self.conn.execute("SELECT title, body FROM memory WHERE kind = 'note'").fetchone()
        self.assertTrue(row["title"].startswith("Dryas session "))
        self.assertIn("Retry flaky calls", row["body"])

    def test_main_without_notes_dir_does_nothing(self):
        env = dict(os.environ, DRYAS_NOTES_DIR=os.path.join(self.d, "absent"), DRYAS_DB=os.path.join(self.d, "o.db"))
        p = subprocess.run([sys.executable, os.path.join(JEV, "memnotes.py"), "export"], input='{"session_id": "s1"}',
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertFalse(os.path.exists(os.path.join(self.d, "o.db")))


    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_secrets_in_every_free_text_field_are_redacted(self):
        self.start()
        tok = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2"
        with memdb.tx(self.conn):
            self.conn.execute("UPDATE sessions SET summary = ? WHERE id = 's1'", ("Used API_KEY=sk-live-9988776655 today",))
            self.conn.execute("INSERT INTO tasks (task_id, ns, title, tier_start, tier_end, outcome, started, ended) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              ("feat:2", self.ns, "Rotate " + tok, "haiku", "sonnet", "merged", time.time() - 5, time.time()))
        memstore.store(self.conn, self.ns, "Title " + tok, "Body\nBearer abcdef123456789\nsecret: zz9yy8xx7ww6",
                       check_content=False)
        text = self.read(self.export())
        for leak in (tok, "sk-live-9988776655", "abcdef123456789", "zz9yy8xx7ww6"):
            self.assertNotIn(leak, text)
        self.assertIn("[REDACTED", text)

    def test_tokens_number_is_not_redacted(self):
        self.start()
        jevlog.append("dispatch", dict(task="feat:3", role="coder", tier="haiku", attempt=1, tokens=98765))
        text = self.read(self.export())
        self.assertIn("tokens=98765.0", text)
        self.assertNotIn("REDACTED", text)

    def test_missing_notes_dir_is_not_created(self):
        self.start()
        memstore.store(self.conn, self.ns, "Lesson", "Body.")
        gone = os.path.join(self.d, "nope")
        with mock.patch.dict(os.environ, {"DRYAS_NOTES_DIR": gone}):
            self.assertIsNone(self.export())
        self.assertFalse(os.path.exists(gone))

    def test_repeated_export_overwrites_one_note(self):
        self.start()
        memstore.store(self.conn, self.ns, "Lesson", "Body.")
        a = self.export()
        b = self.export()
        self.assertEqual(a, b)
        self.assertEqual(len(os.listdir(self.notes)), 1)
        self.assertEqual(self.read(a).count("## Lessons and decisions"), 1)

    def test_long_session_is_bounded_and_valid_utf8(self):
        self.start()
        for i in range(60):
            memstore.store(self.conn, self.ns, "L%d " % i + "\u0e44\u0e17\u0e22" * 40, "\u4e2d\u6587" * 200 + str(i),
                           check_content=False)
        path = self.export()
        raw = open(path, "rb").read()
        self.assertLessEqual(len(raw), memnotes.MAX_BYTES)
        raw.decode("utf-8")
        self.assertTrue(raw.startswith(b"---\nname: Dryas session "))
        self.assertLessEqual(raw.count(b"- outcome:"), memnotes.MAX_ITEMS)

    def test_non_utf8_stdin_still_exports(self):
        self.start()
        memstore.store(self.conn, self.ns, "Lesson", "Body.")
        env = dict(os.environ, DRYAS_CWD="")
        ev = b'{"session_id": "s1", "cwd": "' + self.cwd.encode() + b'", "x": "\xff\xfe"}'
        p = subprocess.run([sys.executable, os.path.join(JEV, "memnotes.py"), "export"], input=ev,
                           capture_output=True, env=env, timeout=30)
        self.assertEqual((p.returncode, p.stdout), (0, b""))
        self.assertEqual(len(os.listdir(self.notes)), 1)

    def test_main_bad_input_exits_zero_silently(self):
        p = subprocess.run([sys.executable, os.path.join(JEV, "memnotes.py"), "export"], input="not json",
                           capture_output=True, text=True, env=dict(os.environ), timeout=30)
        self.assertEqual((p.returncode, p.stdout), (0, ""))


class ChainStageTest(unittest.TestCase):
    def test_mem_notes_stage_follows_the_session_summary(self):
        with open(os.path.join(JEV, "chain.json"), encoding="utf-8") as f:
            stages = json.load(f)["session-end"]
        names = [s["name"] for s in stages]
        self.assertGreater(names.index("mem-notes"), names.index("mem-session-end"))
        st = stages[names.index("mem-notes")]
        self.assertEqual(st["cmd"], ["$PY", "-X", "utf8", "$CD/jev/memnotes.py", "export"])
        self.assertEqual(st["requires_path"], "$CD/memory/notes")
        self.assertEqual((st["component"], st["observe"], st["timeout"]), ("core", True, 2))


class TimingTest(unittest.TestCase):
    """The note must exist before the agent's final commit: SessionEnd comes after it, so Stop and PreCompact refresh it."""

    def stages(self, kind):
        with open(os.path.join(JEV, "chain.json"), encoding="utf-8") as f:
            return json.load(f).get(kind, [])

    def test_note_refreshed_on_stop(self):
        names = [s["name"] for s in self.stages("stop")]
        self.assertIn("mem-notes", names)
        st = self.stages("stop")[names.index("mem-notes")]
        self.assertEqual(st["cmd"], ["$PY", "-X", "utf8", "$CD/jev/memnotes.py", "export"])
        self.assertEqual(st["requires_path"], "$CD/memory/notes")
        self.assertEqual((st["component"], st["observe"], st["timeout"]), ("core", True, 2))

    def test_note_refreshed_on_precompact(self):
        names = [s["name"] for s in self.stages("precompact")]
        self.assertIn("mem-notes", names)
        self.assertGreater(names.index("mem-notes"), names.index("mem-session-end"))
        st = self.stages("precompact")[names.index("mem-notes")]
        self.assertEqual((st["component"], st["observe"], st["timeout"], st["requires_path"]),
                         ("core", True, 2, "$CD/memory/notes"))


if __name__ == "__main__":
    unittest.main()
