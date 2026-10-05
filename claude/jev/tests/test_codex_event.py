import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import codex_event as ce

PATCH = ("*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** Add File: src/b.py\n+new\n"
         "*** Delete File: old.txt\n*** Update File: src/c.py\n*** Move to: lib/c.py\n@@\n-1\n+2\n*** End Patch\n")


class PatchTest(unittest.TestCase):
    def test_headers_in_order_with_move(self):
        files = ce.patch_files(PATCH)
        self.assertEqual([f for f, _ in files], ["src/a.py", "src/b.py", "old.txt", "src/c.py", "lib/c.py"])
        self.assertEqual(files[0][1], "*** Update File: src/a.py\n@@\n-x\n+y")

    def test_crlf_and_spaces_in_path(self):
        files = ce.patch_files("*** Begin Patch\r\n*** Add File: docs/my file.md\r\n+x\r\n*** End Patch\r\n")
        self.assertEqual([f for f, _ in files], ["docs/my file.md"])

    def test_indented_header_is_seen(self):
        files = ce.patch_files("*** Begin Patch\n*** Add File: src/ok.ts\n+x\n *** Add File: src/forbidden.ts\n+y\n"
                               "\t*** Update File: src/tab.ts\n+z\n*** End Patch\n")
        self.assertEqual([f for f, _ in files], ["src/ok.ts", "src/forbidden.ts", "src/tab.ts"])

    def test_no_headers_raises(self):
        with self.assertRaises(ce.PatchError):
            ce.patch_files("*** Begin Patch\n+x\n*** End Patch\n")
        with self.assertRaises(ce.PatchError):
            ce.patch_files("")

    def test_patch_text_forms(self):
        self.assertEqual(ce.patch_text({"command": "p"}), "p")
        self.assertEqual(ce.patch_text({"input": "p"}), "p")
        self.assertEqual(ce.patch_text({"command": ["apply_patch", "p"]}), "apply_patch\np")
        for bad in ("p", None, {}, {"command": 3}):
            with self.assertRaises(ce.PatchError):
                ce.patch_text(bad)

    def test_expand_apply_patch(self):
        ev = {"tool_name": "apply_patch", "tool_input": {"command": PATCH}, "cwd": "/w", "session_id": "s"}
        out = ce.expand(ev)
        self.assertEqual(len(out), 5)
        self.assertEqual(out[1], {"tool_name": "Write", "tool_input": {"file_path": "src/b.py",
                                  "content": "*** Add File: src/b.py\n+new"}, "cwd": "/w", "session_id": "s"})

    def test_expand_passthrough_and_bash_list(self):
        ev = {"tool_name": "Read", "tool_input": {"file_path": "x"}}
        self.assertEqual(ce.expand(ev), [ev])
        b = ce.expand({"tool_name": "Bash", "tool_input": {"command": ["bash", "-lc", "ls"]}})
        self.assertEqual(b[0]["tool_input"]["command"], "bash -lc ls")


if __name__ == "__main__":
    unittest.main()
