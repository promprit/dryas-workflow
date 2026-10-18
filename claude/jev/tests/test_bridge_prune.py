import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bridge_fixture as bf  # noqa: E402
import bridge  # noqa: E402

DAY = 86400


@unittest.skipIf(os.name == "nt", "start-time matching uses ps (POSIX)")
class PruneTest(unittest.TestCase):
    def setUp(self):
        self.sb = bf.Sandbox(self)
        self.sb.me()
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "peer-b")
        self.root = os.path.join(self.sb.root, "inbox")
        self.now = time.time()

    def put(self, rel, age_s):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("{}")
        t = self.now - age_s
        os.utime(p, (t, t))
        return p

    def test_removes_old_delivered_and_bad_keeps_recent(self):
        old_d = self.put(os.path.join(bf.SID_B, "delivered", "a.json"), 8 * DAY)
        old_b = self.put(os.path.join(bf.SID_B, "bad", "b.json"), 8 * DAY)
        new_d = self.put(os.path.join(bf.SID_B, "delivered", "c.json"), 1 * DAY)
        bridge.prune(self.now)
        self.assertFalse(os.path.exists(old_d))
        self.assertFalse(os.path.exists(old_b))
        self.assertTrue(os.path.exists(new_d))

    def test_live_session_waiting_kept_however_old(self):
        p = self.put(os.path.join(bf.SID_B, "1-a.json"), 30 * DAY)
        bridge.prune(self.now)
        self.assertTrue(os.path.exists(p))

    def test_ended_session_folder_removed_after_7_days(self):
        self.put(os.path.join(bf.SID_C, "1-a.json"), 8 * DAY)
        bridge.prune(self.now)
        self.assertFalse(os.path.exists(os.path.join(self.root, bf.SID_C)))

    def test_ended_session_folder_with_recent_file_kept(self):
        self.put(os.path.join(bf.SID_C, "1-a.json"), 8 * DAY)
        self.put(os.path.join(bf.SID_C, "2-b.json"), 1 * DAY)
        bridge.prune(self.now)
        self.assertTrue(os.path.isdir(os.path.join(self.root, bf.SID_C)))

    def test_old_tmp_removed(self):
        old = self.put(os.path.join(bf.SID_B, ".tmp-0000aaaa"), 2 * 3600)
        new = self.put(os.path.join(bf.SID_B, ".tmp-0000bbbb"), 60)
        bridge.prune(self.now)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(new))

    def test_rate_files_of_ended_sessions_removed(self):
        ended = self.put(os.path.join(".rate", bf.SID_C + ".json"), 60)
        live = self.put(os.path.join(".rate", bf.SID_B + ".json"), 60)
        bridge.prune(self.now)
        self.assertFalse(os.path.exists(ended))
        self.assertTrue(os.path.exists(live))

    def test_at_most_once_an_hour(self):
        self.put(".last_prune", 600)
        old = self.put(os.path.join(bf.SID_B, "delivered", "a.json"), 8 * DAY)
        bridge.prune(self.now)
        self.assertTrue(os.path.exists(old))
        bridge.prune(self.now + 3600)
        self.assertFalse(os.path.exists(old))


if __name__ == "__main__":
    unittest.main()
