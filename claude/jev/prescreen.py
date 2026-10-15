"""Local risk-token prescreen for Bash commands.

risky(cmd) returns False only when the whole command text contains no risky
token; such a command may skip the remote judge. It is a denylist, so every
rule errs toward True. Pure function, stdlib only, any exception -> True.
"""
import re

# A command word starts at text start or after whitespace / shell punctuation
# or `/` (so /bin/rm matches) and ends at text end, whitespace or punctuation.
_B = r"(?:^|(?<=[\s;|&()`$={}<>/:]))"
_A = r"(?=$|[\s;|&)`}<>])"
# Start of a simple command: line start, after an operator, keyword or prefix command.
_CMDPOS = (r"(?:^|[;&|()`{\n]|(?<![\w-])(?:then|do|else|elif|if|while|until|!"
           r"|command|builtin|env|nohup|time|nice)\s)\s*")

_WORDS = (
    "rm rmdir mv cp dd ln install unlink truncate shred tee xargs eval exec source "
    "chmod chown chflags sudo su doas kill pkill killall curl wget ssh scp sftp rsync "
    "nc ncat sqlite3 psql mysql redis-cli mongo brew launchctl defaults crontab "
    "osascript open security diskutil mkfs patch docker kubectl dscl sysadminctl tmutil "
    "terraform gh vercel supabase claude make tar unzip zip mkdir touch csrutil "
    # interpreters (python/node/ruby/perl/php: versioned rule below), alt shells
    "bash sh zsh fish npx bunx bun deno ash rbash mksh yash busybox "
    # extras: editors, shells, runners, REPLs, debuggers, file writers, system control
    "pnpx tsx ts-node vi vim nvim nano emacs ed ksh csh tcsh dash pwsh lua expect "
    "tclsh swift Rscript ditto cpio split csplit mkfifo shutdown reboot halt "
    "systemctl gcc clang cc tmux setsid flock "
    "uvx pipx java jshell irb julia scala kotlin groovy erl elixir iex ghci runghc "
    "gdb lldb caffeinate stdbuf chroot openssl nodejs "
    # deploy / database CLIs
    "prisma drizzle-kit dropdb createdb pg_restore pg_dump mongosh firebase wrangler "
    "netlify fly flyctl heroku gcloud az aws simctl turbo nx eas expo fastlane pypy3 "
    "just pulumi helm gradle mvn mvnw rake bundle cmake ninja dotnet mix bazel bazelisk "
    "sbt lein cabal zig meson ant composer "
    # tracers, namespace/priority wrappers, compressors, remote shells, exec-capable tools
    "socat rview vimdiff strace ltrace dtrace nsenter unshare taskset ionice chrt "
    "gzip gunzip bzip2 xz unxz 7z mktemp telnet ftp"
).split()
# Common English words: risky only as the command word (masked copy).
_CMD_WORDS = "at batch watch script timeout gtimeout parallel env nice nohup R stack screen ex view link".split()
_PM_VERBS = ("install add remove uninstall publish update upgrade up i ci link unlink "
             "exec dlx run x rebuild prune dedupe")
# pip/uv/cargo/go/... also run project code on build/test (build.rs, go generate).
_PM_BUILD = "build test bench generate get sync tool"
_NPM_OK = "test lint typecheck list ls outdated why view info --version -v".split()
_GIT_SUBS = (
    "push reset clean checkout switch rebase restore merge cherry-pick revert rm mv "
    "stash am apply pull fetch submodule filter-branch filter-repo update-ref gc prune "
    "config notes replace bisect clone init difftool mergetool send-email credential "
    "lfs maintenance hook sparse-checkout archive format-patch bundle "
    "read-tree checkout-index symbolic-ref update-index"
).split()
# One flag = `-x`/`--long[=v]`; `\w` first keeps the split unambiguous (no
# exponential backtracking on long flag runs).
_FLAG = r"\s+--?\w[\w-]*(?:=\S+)?"
_GIT_PRE = r"(?:\s+-[Cc]\s+\S+|" + _FLAG + ")*"


def _alt(words):  # longest first, grouped by first char (fast reject per position)
    g = {}
    for w in sorted(words, key=len, reverse=True): g.setdefault(w[0], []).append(re.escape(w[1:]))
    return "|".join(re.escape(c) + "(?:" + "|".join(r) + ")" for c, r in g.items())


def _upto(word, stop):
    """`word` + text without `stop` chars, ending at the next `word` (linear)."""
    return r"\b%s\b(?:(?!\b%s\b)[^%s])*" % (word, word, stop)


_SEG = r";|&\n"  # characters that end a simple command
_PATTERNS = [
    _B + "(?:" + _alt(_WORDS) + ")" + _A,
    # git: mutating subcommands, possibly after -C dir / -c k=v / --flags
    _B + "git" + _GIT_PRE + r"\s+(?:(?:" + _alt(_GIT_SUBS) + ")" + _A
    + r"|worktree\s+(?:add|remove|prune|move)" + _A
    + r"|reflog\s+(?:expire|delete)" + _A
    + r"|remote\s+(?:add|remove|rm|rename|set-url|prune)" + _A
    + "|" + _upto("tag", _SEG) + r"\s(?:-[a-zA-Z]*d|--delete)" + _A
    + "|" + _upto("branch", _SEG)
    + r"\s(?:-[a-zA-Z]*[dDmMfcC]|--delete|--move|--force|--copy)" + _A
    + "|" + _upto("commit", _SEG) + r"\s--amend" + _A
    + "|" + _upto("grep", _SEG) + r"\s(?:-[a-zA-Z]*O|--open-files-in-pager))",
    # any git global -c (core.pager, core.sshCommand ...) or code-loading option
    _B + r"git(?:\s+-C\s+\S+|" + _FLAG + r")*?\s+"
    r"(?:-c(?=\s|=|$)|--(?:exec-path|config-env|git-dir|work-tree))",
    r"--output\b",
    # env-prefix assignments that redirect what programs load or run
    _B + r"(?:GIT_[A-Z_]*|[A-Z_]*PAGER|EDITOR|VISUAL|LD_PRELOAD|LD_LIBRARY_PATH"
    r"|DYLD_[A-Z_]*|PATH|BASH_ENV|ENV|LESSOPEN|PROMPT_COMMAND|NODE_OPTIONS"
    r"|PYTHONSTARTUP|PYTHONPATH|IFS)=",
    # package managers
    _B + r"(?:pip3?|uv|cargo|go|gem|poetry|pnpm|npm|yarn)(?:\s+-\S+)*\s+(?:"
    + _alt(_PM_VERBS.split()) + ")" + _A,
    _B + r"(?:pip3?|uv|cargo|go|gem|poetry)(?:\s+-\S+)*\s+(?:"
    + _alt(_PM_BUILD.split()) + ")" + _A,
    _B + r"(?:pnpm|npm|yarn)\s+(?!(?:" + _alt(_NPM_OK) + ")" + _A + r")\S",
    _B + r"yarn(?=[ \t]*(?:$|[;|&)]))",  # bare yarn = yarn install
    # versioned / alternate interpreters: python3.12, node22, pip3.12, ruby3.3
    _B + r"(?:python|pip|node|ruby|perl|php)[\d.]*" + _A,
    _upto("find", r"\n") + r"\s-(?:delete|exec|execdir|ok|okdir|fprint0?|fls|fprintf)\b",
    _upto("[gmn]?awk", r"\n") + r"(?:system\s*\(|getline|\|\s*\"|\s-f\b)",
    _upto("sort", _SEG) + r"\s-[a-zA-Z]*o",
    # ANSI-C quoting can spell any word
    r"\$'",
    # decoders: hidden payloads are usually piped onward to a shell
    _upto("base64", _SEG) + r"\s(?:-[a-zA-Z]*[dD]|--decode)",
    _upto("xxd", _SEG) + r"\s-[a-zA-Z]*r",
    _upto("rg", _SEG) + r"\s--pre(?=[\s=]|$)",  # rg --pre runs a command per file
]
_SYSBIN = r"(?:/usr|/usr/local|/opt/homebrew)?/s?bin/[^\s/;&|()<>`]+(?=$|[\s;&|()<>`])"
# Command-position rules scan a quote-masked copy (see _mask): quoted text
# holds no real separators, and masking keeps the `$` a quoted word expands.
_RAW_PATTERNS = [
    # `. file` (source) at command position
    _CMDPOS + r"\.\s+\S",
    # wrappers / schedulers that run another command, as the command word
    _CMDPOS + r"(?:[A-Za-z_]\w*=\S*\s+)*(?:\S*/)?(?:" + _alt(_CMD_WORDS) + ")" + _A,
    # command word that is a path (./x.sh, bin/rails, /tmp/x.sh, "/a b/x"),
    # unless it is a system bin dir + basename (the word rules judge those)
    _CMDPOS + r"(?:[A-Za-z_]\w*=\S*\s+)*(?![A-Za-z_]\w*=)(?!" + _SYSBIN
    + r")[^\s;&|()<>/]*/",
    # command word built from a variable, substitution, glob or brace expansion
    # (leading NAME=value assignments are skipped, they are not the command)
    _CMDPOS + r"(?:[A-Za-z_]\w*=(?:'[^']*'|\"[^\"]*\"|[^\s'\"])*\s+)*"
    r"(?![A-Za-z_]\w*=)(?!\[\[?\s|\{\s)[^\s;&|()]*[?*\[{$`]",
]
# sed and its arguments (quoted or bare) up to the end of the simple command.
_SED = re.compile(r"\bsed\b((?:\s+(?:'[^']*'|\"[^\"]*\"|[^\s;|&'\"]+))*)")
_SED_ARG = re.compile(r"'[^']*'|\"[^\"]*\"|[^\s;|&'\"]+")
# in-place edit or script file; w/W (write file) or e (execute) sed commands
_SED_OPT = re.compile(r"-[a-zA-Z]*[if]|--(?:in-place|file)")
_SED_CMD = re.compile(r"(?:^|[/;{}0-9$\s])[gpIiMm0-9]*\s*[wWe](?=\s|$|[;}])")
_RX = [re.compile(p, re.M) for p in _PATTERNS]
_RAW_RX = [re.compile(p, re.M) for p in _RAW_PATTERNS]
_REDIRECT = re.compile(r"(&>>|&>|>>|>\||>&|>)\s*([^\s;|&)<>]*)")
# Line continuations, quotes, backslashes and empty expansions removed:
# r\<newline>m, r''m, \rm, "rm", r${x}m -> rm.
_NORM = re.compile(r"\\\n|['\"\\]|\$\{[^}]*\}|\$\(\)|``|\$[@*]")
_QUOTED = re.compile(r"(?<!\\)(?:'[^']*'|\"(?:\\.|[^\"\\])*\")")


def _mask(text):
    """Quoted text -> "$" if it expands, "/" if it holds a path, else empty."""
    def sub(m):
        q, body = m.group(0)[0], m.group(0)
        if q == '"' and re.search(r"[$`]", body): return '"$"'
        return q + "/" + q if "/" in body else q * 2
    return _QUOTED.sub(sub, text)


def _writes(text):
    return any(m.group(2) != "/dev/null" and not (m.group(1) == ">&" and m.group(2)
               in ("1", "2")) for m in _REDIRECT.finditer(text))


def _sed(text):
    for m in _SED.finditer(text):
        for arg in _SED_ARG.findall(m.group(1)):
            if _SED_OPT.match(arg) or _SED_CMD.search(arg.strip("'\"")):
                return True
    return False


def _scan(text):
    return _writes(text) or _sed(text) or any(rx.search(text) for rx in _RX)


def risky(cmd):
    """True when cmd must go to the judge; False only if no risky token found."""
    try:
        if not cmd.strip():
            return True
        masked = _mask(cmd)
        norm = _NORM.sub("", cmd)  # quoting must not hide a command word
        return (_scan(cmd) or any(rx.search(masked) for rx in _RAW_RX)
                or _scan(norm) or _RAW_RX[1].search(norm) is not None)
    except Exception:
        return True
