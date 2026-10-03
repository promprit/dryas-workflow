import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
import transcript_items as ti
from tx_helpers import assistant, tool_result, tool_use, user, user_blocks, write_jsonl


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tp = os.path.join(self.tmp, "t.jsonl")

    def items(self, records, extra=(), **kw):
        write_jsonl(self.tp, records, extra)
        return ti.extract_items(self.tp, **kw)

    def test_user_assistant_text(self):
        it = self.items([user("hello"), assistant("hi there"), user_blocks("a", "b")])
        self.assertEqual([i["kind"] for i in it], ["user", "assistant", "user"])
        self.assertEqual(it[2]["text"], "a\nb")

    def test_tool_result_only_user_is_not_user_item(self):
        it = self.items([tool_use("t1", "Bash", command="ls"), tool_result("t1", "x")])
        self.assertEqual([i["kind"] for i in it], ["tool"])

    def test_tool_pairing_and_head(self):
        it = self.items([tool_use("t1", "Bash", command="pytest -q"), assistant("mid"),
                         tool_result("t1", [{"type": "text", "text": "3 passed\n\n  in 1s"}])])
        self.assertEqual(it[0]["kind"], "tool")
        self.assertEqual(it[0]["tool"], "Bash")
        self.assertEqual(it[0]["text"], "Bash pytest -q: 3 passed in 1s")
        self.assertFalse(it[0].get("is_error"))
        self.assertEqual(it[1]["kind"], "assistant")

    def test_result_head_300(self):
        it = self.items([tool_use("t1", "Bash", command="x"), tool_result("t1", "y" * 5000)])
        self.assertEqual(it[0]["text"], "Bash x: " + "y" * 300)

    def test_error_flag(self):
        it = self.items([tool_use("t1", "Bash", command="boom"), tool_result("t1", "fail", is_error=True)])
        self.assertTrue(it[0]["is_error"])

    def test_key_args(self):
        recs = [tool_use("a", "Edit", file_path="/p/a.py", old_string="x"), tool_result("a", "ok"),
                tool_use("b", "Grep", pattern="foo.*", path="/p"), tool_result("b", "ok"),
                tool_use("c", "Glob", pattern="**/*.py"), tool_result("c", "ok"),
                tool_use("d", "Agent", description="do thing", prompt="long"), tool_result("d", "ok"),
                tool_use("e", "Read", file_path="/p/r.py"), tool_result("e", "ok"),
                tool_use("f", "Other", blob="x" * 500, label="short"), tool_result("f", "ok")]
        it = self.items(recs)
        self.assertTrue(it[0]["text"].startswith("Edit /p/a.py: "))
        self.assertEqual(it[0]["path"], "/p/a.py")
        self.assertTrue(it[1]["text"].startswith("Grep foo.*: "))
        self.assertTrue(it[2]["text"].startswith("Glob **/*.py: "))
        self.assertTrue(it[3]["text"].startswith("Agent do thing: "))
        self.assertTrue(it[4]["text"].startswith("Read /p/r.py: "))
        self.assertTrue(it[5]["text"].startswith("Other short: "))

    def test_unpaired_tool_use_still_item(self):
        it = self.items([tool_use("t1", "Bash", command='git commit -m "a: b"')])
        self.assertEqual(len(it), 1)
        self.assertTrue(it[0]["text"].startswith('Bash git commit -m "a: b"'))

    def test_injected_text_skipped(self):
        bad = ["<system-reminder>x", "<command-name>/foo", "<local-command-stdout>", "Caveat: foo",
               "<task-notification>done", "[SYSTEM NOTIFICATION x"]
        it = self.items([user(b) for b in bad] + [user("real question about <system-reminder> tags")])
        self.assertEqual(len(it), 1)
        self.assertIn("real question", it[0]["text"])

    def test_meta_and_compact_summary_skipped(self):
        m1 = dict(user("injected skill text"), isMeta=True)
        m2 = dict(user("This session is being continued"), isCompactSummary=True)
        it = self.items([m1, m2, user("Base directory for this skill: /x"), user("Skill /foo:bar was loaded"),
                         user("real")])
        self.assertEqual([i["text"] for i in it], ["real"])

    def test_agent_messages(self):
        recs = [dict(user("Another Claude session sent a message: done " + "x" * 2000), isMeta=True),
                user("<agent-message from=x>hi</agent-message>"), user("real")]
        it = self.items(recs)
        self.assertEqual([i["kind"] for i in it], ["agent", "agent", "user"])
        self.assertEqual(len(it[0]["text"]), 1000)

    def test_leading_tag_blocks_stripped(self):
        recs = [user("<ide_selection>The user selected foo</ide_selection>\nfix this please"),
                user("<ide_opened_file>a.py</ide_opened_file><browser_instruction>x\ny</browser_instruction>"),
                user("<browser_instruction>unterminated")]
        it = self.items(recs)
        self.assertEqual([i["text"] for i in it], ["fix this please"])

    def test_robustness(self):
        big = json.dumps(user("z" * 1100000))
        it = self.items([user("ok")], extra=["not json", "[1,2]", big, json.dumps({"type": "summary"})])
        self.assertEqual(len(it), 1)

    def test_missing_file(self):
        self.assertEqual(ti.extract_items("/nope/x.jsonl"), [])

    def test_max_items_newest(self):
        it = self.items([user("m%d" % i) for i in range(10)], max_items=3)
        self.assertEqual([i["text"] for i in it], ["m7", "m8", "m9"])

    def test_default_extracts_all_items(self):
        it = self.items([user("m%d" % i) for i in range(500)])
        self.assertEqual(len(it), 500)

    def test_uuid_dedupe_keeps_first_and_records_without_uuid(self):
        a = dict(user("yes"), uuid="u1")
        b = dict(user("yes"), uuid="u1")
        c = dict(user("yes"), uuid="u2")
        it = self.items([a, b, c, user("yes"), user("yes")])
        self.assertEqual(len(it), 4)

    def test_more_injected_prefixes(self):
        it = self.items([user("[Request interrupted by user for tool use]"), user("<bash-input>ls</bash-input>"),
                         user("<bash-stdout>x</bash-stdout>"), user("ok")])
        self.assertEqual([i["text"] for i in it], ["ok"])

    def test_pending_tool_has_no_empty_colon(self):
        it = self.items([tool_use("t1", "Bash", command="ls")])
        self.assertEqual(it[0]["text"], "Bash ls: (no result)")

    def test_text_capped_1000(self):
        it = self.items([user("q" * 5000)])
        self.assertEqual(len(it[0]["text"]), 1000)


class AlwaysKeepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tp = os.path.join(self.tmp, "t.jsonl")

    def keep(self, records):
        write_jsonl(self.tp, records)
        return ti.always_keep(ti.extract_items(self.tp))

    def test_last_ten_user_trimmed_500(self):
        lines = self.keep([user("u%d " % i + "q" * 900) for i in range(12)])
        joined = "\n".join(lines)
        self.assertNotIn("u0 ", joined)
        self.assertNotIn("u1 ", joined)
        for k in range(2, 12):
            self.assertIn("u%d " % k, joined)
        self.assertLess(joined.index("u2 "), joined.index("u11 "))
        self.assertTrue(all(len(l) <= 500 + len("user: ") for l in lines))

    def test_agent_not_always_kept(self):
        self.assertEqual(self.keep([user("<agent-message>x</agent-message>")]), [])

    def test_files_touched_order_of_last_touch(self):
        recs = []
        for n, (name, fp) in enumerate([("Edit", "/a"), ("Write", "/b"), ("Edit", "/a"), ("Read", "/r"), ("MultiEdit", "/c")]):
            recs += [tool_use("t%d" % n, name, file_path=fp), tool_result("t%d" % n, "ok")]
        lines = self.keep(recs)
        self.assertIn("Files touched: /b, /a, /c", lines)

    def test_files_touched_max_40(self):
        recs = []
        for n in range(50):
            recs += [tool_use("t%d" % n, "Edit", file_path="/f%d" % n), tool_result("t%d" % n, "ok")]
        line = [l for l in self.keep(recs) if l.startswith("Files touched:")][0]
        self.assertEqual(len(line.split(": ", 1)[1].split(", ")), 40)
        self.assertIn("/f49", line)
        self.assertNotIn("/f0,", line)

    def test_latest_result_per_test_command(self):
        recs = [tool_use("a", "Bash", command="pytest -q"), tool_result("a", "1 failed", is_error=True),
                tool_use("b", "Bash", command="pnpm test"), tool_result("b", "ok 5"),
                tool_use("c", "Bash", command="pytest -q"), tool_result("c", "9 passed"),
                tool_use("d", "Bash", command="ls"), tool_result("d", "files")]
        lines = self.keep(recs)
        joined = "\n".join(lines)
        self.assertIn("9 passed", joined)
        self.assertNotIn("1 failed", joined)
        self.assertIn("ok 5", joined)
        self.assertNotIn("files", joined)

    def test_commits(self):
        recs = [tool_use("a", "Bash", command='git commit -m "feat: x"'), tool_result("a", "[main abc1234] feat: x\n 1 file changed"),
                tool_use("b", "Bash", command='git commit -m "y"'), tool_result("b", "nothing to commit", is_error=True)]
        joined = "\n".join(self.keep(recs))
        self.assertIn("abc1234", joined)
        self.assertNotIn("nothing to commit", joined)

    def test_test_command_must_be_a_command_not_a_mention(self):
        recs = [tool_use("a", "Bash", command='git commit -m "fix jest"'), tool_result("a", "[main abc1234] fix jest"),
                tool_use("b", "Bash", command="pip install pytest"), tool_result("b", "Successfully installed"),
                tool_use("c", "Bash", command="grep -rn pytest ."), tool_result("c", "a.py:1: pytest"),
                tool_use("d", "Bash", command="cd /x && /usr/bin/python3 -m pytest -q"), tool_result("d", "7 passed")]
        joined = "\n".join(self.keep(recs))
        self.assertIn("7 passed", joined)
        self.assertNotIn("Successfully installed", joined)
        self.assertNotIn("a.py:1", joined)

    def test_pending_tests_not_kept(self):
        self.assertEqual(self.keep([tool_use("a", "Bash", command="pytest")]), [])

    def test_indexes_helper_marks_represented(self):
        recs = [user("u"), tool_use("a", "Edit", file_path="/a"), tool_result("a", "ok"), assistant("chat")]
        write_jsonl(self.tp, recs)
        items = ti.extract_items(self.tp)
        _, idx = ti.always_keep_split(items)
        self.assertIn(0, idx)
        self.assertIn(1, idx)
        self.assertNotIn(2, idx)


if __name__ == "__main__":
    unittest.main()
