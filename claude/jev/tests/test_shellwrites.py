import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import local_judge
import shellwrites as sw

WT = "/w"
WRITES = ["rm -rf build", "mv a b", "cp -r a b", "tee out.txt", "sed -i 's/a/b/' f", "sed -i '' 's/a/b/' f", "truncate -s 0 f",
          "dd if=/dev/zero of=f", "echo x > f", "cat a >> b", "cmd 2>&1 > log", "git checkout -- f", "git restore .",
          "git reset --hard", "git clean -fd", "git stash pop", "mkdir -p x", "touch f", "tar xf a.tgz", "unzip a.zip",
          "chmod +x f", "npm install x", "pip install y", "cd /p && rm x", "ls; rm x", "/bin/rm x", "r\\m x", "'rm' x"]
NOT_WRITES = ["ls -la", "git status", "git diff --stat", "git log --oneline -5", "grep -rn foo src", "cat f 2>/dev/null",
              "cmd 2>&1", "python3 -m pytest -q", "echo '>' done", "make test", "curl https://x", "git push origin main",
              "npm test", "pnpm lint", "find . -name '*.py'", "wc -l f", "sort f", "docker ps", ""]


def a(cmd, cwd=WT):
    return sw.analyse(cmd, cwd)


class ShellWritesTest(unittest.TestCase):
    def test_old_write_cases(self):
        for c in WRITES:
            self.assertTrue(a(c).writes, c)

    def test_old_read_only_cases(self):
        for c in NOT_WRITES:
            self.assertFalse(a(c).writes, c)

    def test_inline_code_and_local_scripts_are_unknown_writes(self):
        for c in ("python -c \"open('x','w').write('a')\"", "python3 -I -c 'import os'", "node -e 'fs.writeFileSync(1)'",
                  "perl -e 'unlink shift'", "ruby -e 'File.delete(1)'", "php -r 'unlink(1);'", "./build.sh",
                  "cd src && ./gen", "sh gen.sh", "bash -x scripts/x.sh", "../tools/run.sh --fast",
                  "python3 - <<'EOF'\nopen('a', 'w').write('x')\nEOF", "cat x.py | python3"):
            r = a(c)
            self.assertTrue(r.writes and r.unknown, c)
        self.assertEqual(a("python3 - <<'EOF'\nprint(1)\nEOF").rule, "inline_code")
        for c in ("python3 x.py", "python3 -m pytest -q", "node index.js", "npm run build", "make", "go build ./...",
                  "echo ./x", "ls ./", "cat ./README.md"):
            self.assertFalse(a(c).writes, c)

    def test_code_and_prose_are_not_commands(self):
        for c in ('git commit -q -m "fix: split (install) store tests" -- a.ts',
                  "python3 -m pytest -q 2>&1 | tail -3",
                  "cat <<'EOF' | grep x\nconst a = () => { b > c }\nEOF",
                  "pnpm biome check --write src/a.ts 2>&1 | tail -2",
                  "git add src/a.ts && git commit -m 'x'",
                  "grep -n 'a => b' src/a.ts"):
            self.assertFalse(a(c).writes, c)

    def test_readable_targets(self):
        cases = {
            "cd /w/apps/bot && sed -i '' 's/a/b/g' src/x.ts": ["/w/apps/bot/src/x.ts"],
            "sed -i.bak -e 's/a/b/' a.ts b.ts": ["/w/a.ts", "/w/b.ts"],
            "sed -Ei 's/a/b/' a.ts": ["/w/a.ts"],
            "perl -0pi -e 's/x/y/' src/a.ts": ["/w/src/a.ts"],
            "echo x > out/f.txt 2>/dev/null": ["/w/out/f.txt"],
            "cp a.ts /tmp/b.ts": ["/tmp/b.ts"],
            "mv -t dest a b": ["/w/dest"],
            "mkdir -p x/y && touch x/y/z": ["/w/x/y", "/w/x/y/z"],
            "truncate -s 0 f": ["/w/f"],
            "git checkout HEAD~1 -- src/a.ts": ["/w/src/a.ts"],
            "git restore --source HEAD~1 src/a.ts": ["/w/src/a.ts"],
            "tee -a log.txt": ["/w/log.txt"],
            "dd if=/dev/zero of=img bs=1": ["/w/img"],
            "bash -c 'rm a'": ["/w/a"],
            'sed -i "s/a/b/" "my file.ts"': ["/w/my file.ts"],
            "chmod -R 755 dist": ["/w/dist"],
            "rm ../outside.txt": ["/outside.txt"],
        }
        for c, paths in cases.items():
            r = a(c)
            self.assertEqual((r.writes, r.paths, r.unknown), (True, paths, False), c)

    def test_sed_without_in_place_reads_only(self):
        for c in ("sed -n 1,5p f", "sed 's/a/b/' f > /dev/null", "sed -e 's/a/b/' f"):
            self.assertFalse(a(c).writes, c)
        r = a("sed -n 'w out' f")
        self.assertTrue(r.writes and r.unknown)

    def test_unknown_targets(self):
        for c in ("rm $F", "rm *.bak", 'echo > "$(pwd)/x"', "cd $DIR && rm a", "rm ~/x", "git stash",
                  "git -C ../other checkout -- a", "find . -name x | xargs rm", "$PY -c 'x'", "sed -f s.sed f"):
            r = a(c)
            self.assertTrue(r.writes and r.unknown, c)

    def test_relative_target_without_cwd_is_unknown(self):
        r = sw.analyse("rm a", "")
        self.assertTrue(r.writes and r.unknown)
        self.assertEqual(r.paths, [])

    def test_too_long_or_broken_is_unknown_write(self):
        self.assertEqual(a("x" * (local_judge.MAX_CHARS + 1)), sw.Analysis(True, [], True, "error"))

    def test_linear(self):
        for payload in ("rm " * 30000, "echo " + ">" * 50000, "git " * 20000 + "checkout", "a=>b " * 12000):
            t0 = time.monotonic()
            a(payload)
            self.assertLess(time.monotonic() - t0, 0.5, payload[:10])


if __name__ == "__main__":
    unittest.main()
