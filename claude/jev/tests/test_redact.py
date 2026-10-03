import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from redact import redact, redact_obj


class RedactTest(unittest.TestCase):
    def assertGone(self, text, secret):
        out = redact(text)
        self.assertNotIn(secret, out)
        return out

    def test_openrouter_and_sk_keys(self):
        self.assertGone("key sk-or-v1-" + "0123456789abcdef" * 2, "0123456789abcdef0123")

    def test_bearer_and_authorization_header(self):
        self.assertGone('curl -H "Authorization: Bearer abc.def.ghi" x', "abc.def.ghi")
        self.assertGone("token Bearer zzzzzzzzzz", "zzzzzzzzzz")

    def test_env_assignment(self):
        out = self.assertGone("export SUPABASE_SERVICE_ROLE_KEY=" + "eyJhbGciOiJIUzI1NiJ9" + ".payload.sig && ls", "eyJhbGciOiJIUzI1NiJ9")
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY=[REDACTED]", out)
        self.assertGone("DB_PASSWORD='hunter2 x'", "hunter2")

    def test_pem_block(self):
        pem = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----"
        self.assertEqual(redact(pem), "[REDACTED_PEM]")

    def test_url_password(self):
        self.assertGone("psql postgres://user:" + "s3cr3t" + "@db.example.com/x", "s3cr3t")

    def test_token_flags(self):
        self.assertGone("gh auth login --token " + "ghp_" + "abcdefghijklmnopqrstuvwx", "ghp_" + "abcdefghijklmnopqrstuvwx")
        self.assertGone("tool --api-key=abc123", "abc123")

    def test_cloud_key_shapes(self):
        self.assertGone("AKIA" + "ABCDEFGHIJKLMNOP", "AKIA" + "ABCDEFGHIJKLMNOP")
        self.assertGone("AIzaSyA0123456789012345678901234567890", "AIzaSyA0123456789012345678901234567890")

    def test_plain_text_unchanged(self):
        s = "git commit -m 'fix keyboard layout' && pnpm test"
        self.assertEqual(redact(s), s)

    def test_redact_obj_recursive(self):
        o = redact_obj({"a": ["x TOKEN=abc"], "b": {"c": "Bearer qqqqqqqqqq"}, "n": 3})
        self.assertNotIn("abc", o["a"][0])
        self.assertNotIn("qqqqqqqqqq", o["b"]["c"])
        self.assertEqual(o["n"], 3)

    def test_json_yaml_secret_keys_double_quoted(self):
        self.assertGone('"password": "hunter2"', "hunter2")
        self.assertGone('"api_key": "sk-abc123"', "sk-abc123")
        self.assertGone('"client_secret":"secretval"', "secretval")

    def test_json_yaml_secret_keys_single_quoted(self):
        self.assertGone("'api_key': 'mysecret'", "mysecret")
        self.assertGone("'password': 'pass123'", "pass123")

    def test_yaml_secret_keys_unquoted(self):
        self.assertGone("password: mysecretpassword", "mysecretpassword")
        self.assertGone("api_key: " + "abc123" + "def456", "abc123def456")

    def test_curl_user_flag(self):
        self.assertGone("curl -u admin:password123 https://api.example.com", "password123")
        self.assertGone("curl --user user:pass123 https://example.com", "pass123")

    def test_unterminated_pem(self):
        unterminated = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEowIBA\nABCD1234"
        out = redact(unterminated)
        self.assertNotIn("ABCD1234", out)
        self.assertIn("[REDACTED_PEM]", out)

    def test_redact_obj_with_tuples(self):
        o = redact_obj(("TOKEN=abc", "PASS=secret"))
        self.assertIsInstance(o, tuple)
        self.assertNotIn("abc", o[0])
        self.assertNotIn("secret", o[1])

    def test_redaction_timing_guard(self):
        # Ensure no catastrophic backtracking on repeated patterns
        big_text = "KEY" * 1000 + "PASSWORD=x"
        t0 = time.monotonic()
        redact(big_text)
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.5)

    def test_env_var_double_quoted_with_spaces(self):
        out = self.assertGone('X_TOKEN="abc def ghi"', "abc")
        self.assertNotIn("def", out)
        self.assertNotIn("ghi", out)

    def test_env_var_single_quoted_with_spaces(self):
        out = self.assertGone("DB_PASS=" + "'my secret" + " pw'", "my")
        self.assertNotIn("secret", out)
        self.assertNotIn("pw", out)

    def test_yaml_quoted_value_with_spaces(self):
        out = self.assertGone('password: ' + '"my secret' + ' pw"', "my")
        self.assertNotIn("secret", out)
        self.assertNotIn("pw", out)

    def test_json_quoted_value_with_spaces(self):
        out = self.assertGone('{"password": ' + '"my secret' + ' pw"}', "my")
        self.assertNotIn("secret", out)
        self.assertNotIn("pw", out)

    def test_large_redaction_timing_guard(self):
        # Ensure no catastrophic backtracking with large input (≈64k)
        big_text = "KEY" * 21000
        t0 = time.monotonic()
        redact(big_text)
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()


def test_mysql_inline_password():
    assert "s3cretpw" not in redact("mysql -u root -ps3cretpw mydb")
    assert "s3cretpw" not in redact("mysql -u root --password=s3cretpw mydb")


def test_extra_auth_headers():
    for h in ("X-Auth-Token", "X-Access-Token", "Proxy-Authorization"):
        out = redact("curl -H '%s: abcdef123456' https://x" % h)
        assert "abcdef123456" not in out, h


def test_aws_keys():
    out = redact("aws_access_key_id: AKIA" + "ABCDEFGHIJKLMNOP\naws_secret_access_key: " + "wJalrXUtnFEMI/K7MDENG/" + "bPxRfiCYEXAMPLEKEY")
    assert "AKIA" + "ABCDEFGHIJKLMNOP" not in out
    assert "wJalrXUtnFEMI" not in out


def test_mysql_family_variants():
    for tool in ("mysql", "mysqldump", "mysqladmin", "mariadb", "mariadb-dump"):
        assert "s3cretpw" not in redact("%s -u root -ps3cretpw db" % tool), tool
        assert "s3cretpw" not in redact("%s -u root --password=s3cretpw db" % tool), tool
    out = redact("mysql -u root -p'my sec ret' db")
    assert "sec" not in out and "ret'" not in out and "db" in out
    out = redact('mysql -u root -p"my sec ret" db')
    assert "sec" not in out and 'ret"' not in out and "db" in out


def test_mysql_p_only_first_and_not_other_commands():
    out = redact("mysql -u r -pabc && grep -pattern file")
    assert "abc" not in out and "-pattern" in out
    assert "-pfoo" in redact("grep -pfoo file")


def test_mysql_p_only_first_token():
    out = redact("mysql -pabc db -pxyz")
    assert "abc" not in out and "-pxyz" in out


def test_mysql_redaction_is_linear():
    import time
    for payload in ("mysql " * 34000, "mysql " + "x" * 200000, "mysql -p " * 22000,
                    "mysqldump " + "-p " * 70000, "mariadb " * 25000 + "y" * 50000):
        t0 = time.time()
        redact(payload)
        assert time.time() - t0 < 0.5, payload[:20]
