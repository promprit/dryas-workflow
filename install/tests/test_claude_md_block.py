import shutil, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import claude_md_block as cmb


class BlockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def test_insert_into_missing_then_remove_deletes_file(self):
        p, rec = self.tmp / "AGENTS.md", {}
        cmb.insert_block(p, "rules →", rec, "agents_md")
        self.assertEqual(p.read_text(encoding="utf-8"), cmb.START + "\nrules →\n" + cmb.END + "\n")
        cmb.remove_block(p, rec, "agents_md")
        self.assertFalse(p.exists())

    def test_existing_content_roundtrip(self):
        p, rec = self.tmp / "AGENTS.md", {}
        p.write_text("MINE\n", encoding="utf-8")
        cmb.insert_block(p, "v1", rec, "agents_md")
        cmb.insert_block(p, "v2", rec, "agents_md")
        t = p.read_text(encoding="utf-8")
        self.assertEqual(t.count(cmb.START), 1)
        self.assertIn("v2", t)
        cmb.remove_block(p, rec, "agents_md")
        self.assertEqual(p.read_text(encoding="utf-8"), "MINE\n")

    def test_custom_markers(self):
        p, rec = self.tmp / "config.toml", {}
        p.write_text('model = "x"\n', encoding="utf-8")
        cmb.insert_block(p, "[mcp_servers.jev]", rec, "toml", "# >>> a >>>", "# <<< a <<<")
        self.assertIn("# >>> a >>>\n[mcp_servers.jev]\n# <<< a <<<\n", p.read_text(encoding="utf-8"))
        cmb.remove_block(p, rec, "toml", "# >>> a >>>", "# <<< a <<<")
        self.assertEqual(p.read_text(encoding="utf-8"), 'model = "x"\n')

    def test_claude_md_wrappers_keep_record_keys(self):
        rec = {}
        cmb.claude_md(self.tmp, "P", rec)
        self.assertTrue(rec["claude_md"])
        self.assertTrue(rec["claude_md_created"])
        cmb.remove_claude_md(self.tmp, rec)
        self.assertFalse((self.tmp / "CLAUDE.md").exists())

    def test_crlf_roundtrip_byte_identical(self):
        p, rec = self.tmp / "AGENTS.md", {}
        raw = b"line one\r\nline two\r\n"
        p.write_bytes(raw)
        cmb.insert_block(p, "rules", rec, "agents_md")
        cmb.remove_block(p, rec, "agents_md")
        self.assertEqual(p.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
