import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codex_toml as tt

K1, K2 = "dryas@dryas-workflow:hooks/hooks.json:pre_tool_use:0:0", "dryas@dryas-workflow:hooks/hooks.json:session_start:0:0"


class RemoveTrustTest(unittest.TestCase):
    def test_table_form(self):
        text = ('model = "x"\n\n[hooks.state."%s"]\ntrusted_hash = "sha256:a"\n\n'
                '[hooks.state."other@m:hooks/hooks.json:stop:0:0"]\ntrusted_hash = "sha256:b"\n' % K1)
        new, missing = tt.remove_trust(text, [K1])
        self.assertEqual(missing, [])
        self.assertNotIn(K1, new)
        self.assertIn("other@m", new)
        self.assertIn('model = "x"', new)

    def test_inline_form(self):
        text = '[hooks.state]\n"%s" = { trusted_hash = "sha256:a" }\n"keep" = { trusted_hash = "c" }\n' % K2
        new, missing = tt.remove_trust(text, [K2])
        self.assertEqual((missing, new), ([], '[hooks.state]\n"keep" = { trusted_hash = "c" }\n'))

    def test_missing_reported_text_untouched(self):
        self.assertEqual(tt.remove_trust("a = 1\n", [K1]), ("a = 1\n", [K1]))

    def test_empty_hooks_state_header_dropped(self):
        # the real 0.162.1 CLI writes an empty [hooks.state] header in front of the tables it trusts
        text = ('model = "x"\n\n[hooks.state]\n\n[hooks.state."%s"]\ntrusted_hash = "sha256:a"\n\n'
                '[hooks.state."%s"]\ntrusted_hash = "sha256:b"\n' % (K1, K2))
        new, missing = tt.remove_trust(text, [K1, K2])
        self.assertEqual((new, missing), ('model = "x"\n', []))

    def test_hooks_state_header_kept_while_used(self):
        text = '[hooks.state]\n\n[hooks.state."%s"]\ntrusted_hash = "a"\n\n[hooks.state."o"]\ntrusted_hash = "b"\n' % K1
        new, _ = tt.remove_trust(text, [K1])
        self.assertEqual(new, '[hooks.state]\n\n[hooks.state."o"]\ntrusted_hash = "b"\n')
        text = '[hooks.state]\n"keep" = { trusted_hash = "c" }\n\n[hooks.state."%s"]\ntrusted_hash = "a"\n' % K1
        self.assertEqual(tt.remove_trust(text, [K1])[0], '[hooks.state]\n"keep" = { trusted_hash = "c" }\n')

    def test_header_spelling_variants(self):
        for hdr in ("[hooks.state.'%s']", '[ hooks . state . "%s" ]  # trusted', '["hooks".state."%s"]'):
            text = 'a = 1\n\n' + hdr % K1 + '\ntrusted_hash = "x"\n\n[z]\nb = 2\n'
            new, missing = tt.remove_trust(text, [K1])
            self.assertEqual((new, missing), ('a = 1\n\n[z]\nb = 2\n', []), hdr)

    def test_only_exact_keys(self):
        text = '[hooks.state."%sX"]\ntrusted_hash = "a"\n' % K1
        self.assertEqual(tt.remove_trust(text, [K1]), (text, [K1]))

    def test_multiline_string_is_not_a_header(self):
        text = ('[hooks.state."%s"]\ntrusted_hash = "a"\n\n[notes]\ntext = """\n[hooks.state."%s"]\n"""\n' % (K1, K2))
        new, missing = tt.remove_trust(text, [K1, K2])
        self.assertEqual(missing, [K2])
        self.assertEqual(new, '[notes]\ntext = """\n[hooks.state."%s"]\n"""\n' % K2)

    def test_user_comment_kept(self):
        text = '[hooks.state."%s"]\ntrusted_hash = "a"\n# my note about [z]\n[z]\nb = 2\n' % K1
        self.assertEqual(tt.remove_trust(text, [K1])[0], '# my note about [z]\n[z]\nb = 2\n')


if __name__ == "__main__":
    unittest.main()
