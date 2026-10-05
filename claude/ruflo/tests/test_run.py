import hashlib, os, re, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
RUN = HERE / "run.py"
SHIM = HERE / "mcp-shim" / "bin" / "cli.js"
NODE = shutil.which("node")
PLUG = Path.home() / ".claude/plugins/cache/ruflo/ruflo-core/0.2.6"
HELPERS = Path.home() / ".claude/ruflo/helpers"
STRIP = ("RUFLO_BIN", "RUFLO_JS", "RUFLO_SSD_ROOT", "DRYAS_DATA_ROOT", "CLAUDE_PROJECT_DIR", "RUFLO_DATA_MODE",
         "RUFLO_NODE_FALLBACK", "RUFLO_NODE_MODULES", "RUFLO_DATA_ROOT", "CLAUDE_FLOW_CWD")
ECHO_JS = ("let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{process.stdout.write('GOT:'+d+'|DIR:'+"
           "process.env.RUFLO_DATA_ROOT+'|NAE:'+process.env.RUFLO_NO_AUTO_ENABLE);process.exit(2)})")
FAKE_RUFLO_JS = ("let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{process.stdout.write('PWD:'+process.cwd()+"
                 "'|CWDENV:'+process.env.CLAUDE_FLOW_CWD+'|ARGS:'+process.argv.slice(2).join(' ')+'|IN:'+d);process.exit(2)})")


def make_exe(d: Path, name: str, pycode: str) -> Path:
    """A runnable fake: a Python script plus a launcher (shebang file on POSIX, .cmd on Windows)."""
    d.mkdir(parents=True, exist_ok=True)
    py = d / (name + "_impl.py")
    py.write_text(pycode, encoding="utf-8")
    if os.name == "nt":
        exe = d / (name + ".cmd")
        exe.write_text('@"%s" "%s" %%*\r\n' % (sys.executable, py), encoding="utf-8")
    else:
        exe = d / name
        exe.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, py), encoding="utf-8")
        exe.chmod(0o755)
    return exe


class RunTest(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.ssd = self.t / "ssd"
        self.ssd.mkdir()
        (self.t / "echo.js").write_text(ECHO_JS, encoding="utf-8")
        (self.t / "fakeruflo.js").write_text(FAKE_RUFLO_JS, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(str(self.t), ignore_errors=True)

    def run_py(self, args, stdin="payload", path=None, **env):
        e = {k: v for k, v in os.environ.items() if k not in STRIP}
        e.update(env)
        if path is not None:
            e["PATH"] = path
        p = subprocess.run([sys.executable, str(RUN)] + args, input=stdin, capture_output=True, text=True, env=e,
                           timeout=120)
        return p.returncode, p.stdout + p.stderr

    def cache(self, ns):
        return os.path.join(str(self.ssd), "_caches", "ruflo", ns)

    def test_data_root_missing_is_silent(self):
        rc, out = self.run_py(["helper", "node", str(self.t / "echo.js")], RUFLO_SSD_ROOT=str(self.t / "none"))
        self.assertEqual((rc, out), (0, ""))

    def test_helper_missing_is_silent(self):
        rc, out = self.run_py(["helper", "node", str(self.t / "nope.js")], RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual((rc, out), (0, ""))

    def test_command_missing_is_silent(self):
        rc, out = self.run_py(["helper", "no-such-cmd-xyz", str(self.t / "echo.js")], RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual((rc, out), (0, ""))

    def test_unknown_subcommand_is_silent(self):
        self.assertEqual(self.run_py(["bogus"]), (0, ""))

    @unittest.skipUnless(NODE, "node not installed")
    def test_helper_runs_in_cache_dir_and_never_exits_2(self):
        proj = str(self.t / "x" / "myproj")
        rc, out = self.run_py(["helper", "node", str(self.t / "echo.js")], stdin="hello-stdin",
                              CLAUDE_PROJECT_DIR=proj, RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "GOT:hello-stdin|DIR:%s|NAE:1" % self.cache("myproj"))
        self.assertTrue(os.path.isdir(self.cache("myproj")))

    @unittest.skipUnless(NODE, "node not installed")
    def test_env_mode_leaves_data_root_unset(self):
        rc, out = self.run_py(["helper", "node", str(self.t / "echo.js")], stdin="e", RUFLO_DATA_MODE="env",
                              RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual(out, "GOT:e|DIR:undefined|NAE:1")

    def test_node_fallback_when_node_not_on_path(self):
        fake = make_exe(self.t / "fb", "fakenode", "import sys\nprint('FALLBACK:' + sys.argv[1])\n")
        (self.t / "h.js").write_text("x", encoding="utf-8")
        empty = self.t / "emptybin"
        empty.mkdir()
        rc, out = self.run_py(["helper", "node", str(self.t / "h.js")], path=str(empty),
                              RUFLO_NODE_FALLBACK=str(fake), RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual(out.strip(), "FALLBACK:%s" % (self.t / "h.js"))
        rc, out = self.run_py(["helper", "node", str(self.t / "h.js")], path=str(empty),
                              RUFLO_NODE_FALLBACK=str(self.t / "none"), RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual((rc, out), (0, ""))

    def test_cli_noop_without_root_or_binary(self):
        self.assertEqual(self.run_py(["cli", "hooks", "x"], RUFLO_SSD_ROOT=str(self.t / "none"),
                                     RUFLO_BIN=str(self.t / "none")), (0, ""))
        self.assertEqual(self.run_py(["cli", "hooks", "x"], RUFLO_SSD_ROOT=str(self.ssd),
                                     RUFLO_BIN=str(self.t / "nobin")), (0, ""))

    @unittest.skipUnless(NODE, "node not installed")
    def test_cli_runs_ruflo_js_in_cache_dir(self):
        rc, out = self.run_py(["cli", "hooks", "post-command", "-c", "ls"], stdin="stdin-data",
                              CLAUDE_PROJECT_DIR=str(self.t / "x" / "projcli"), RUFLO_SSD_ROOT=str(self.ssd),
                              RUFLO_JS=str(self.t / "fakeruflo.js"))
        d = self.cache("projcli")
        self.assertEqual(rc, 0)
        m = re.fullmatch(r"PWD:(.*)\|CWDENV:(.*)\|ARGS:(.*)\|IN:(.*)", out, re.S)
        self.assertIsNotNone(m, out)
        self.assertTrue(os.path.samefile(m.group(1), d))
        self.assertEqual(m.group(2), d)
        self.assertEqual(m.group(3), "hooks post-command -c ls")
        self.assertEqual(m.group(4), "stdin-data")

    @unittest.skipIf(os.name == "nt", "RUFLO_BIN fake launcher is POSIX-only")
    def test_cli_uses_ruflo_bin_when_no_js(self):
        fake = make_exe(self.t / "rb", "ruflo", "import sys\nprint('BIN:' + ' '.join(sys.argv[1:]))\n")
        rc, out = self.run_py(["cli", "a", "b"], RUFLO_SSD_ROOT=str(self.ssd), RUFLO_BIN=str(fake))
        self.assertEqual(out.strip(), "BIN:a b")

    @unittest.skipUnless(NODE, "node not installed")
    def test_worktree_uses_main_repo_namespace(self):
        repo = self.t / "x" / "myrepo"
        repo.mkdir(parents=True)
        g = ["git", "-c", "user.email=a@b", "-c", "user.name=t"]
        subprocess.run(g + ["init", "-q"], cwd=str(repo), check=True)
        subprocess.run(g + ["commit", "-q", "--allow-empty", "-m", "i"], cwd=str(repo), check=True)
        subprocess.run(g + ["worktree", "add", "-q", ".worktrees/main", "-b", "wt"], cwd=str(repo), check=True)
        wt = str(repo / ".worktrees" / "main")
        rc, out = self.run_py(["cli", "hooks", "y"], stdin="i", CLAUDE_PROJECT_DIR=wt, RUFLO_SSD_ROOT=str(self.ssd),
                              RUFLO_JS=str(self.t / "fakeruflo.js"))
        self.assertIn("CWDENV:%s|" % self.cache("myrepo"), out)
        rc, out = self.run_py(["helper", "node", str(self.t / "echo.js")], stdin="i", CLAUDE_PROJECT_DIR=wt,
                              RUFLO_SSD_ROOT=str(self.ssd))
        self.assertIn("DIR:%s|" % self.cache("myrepo"), out)

    @unittest.skipUnless(NODE, "node not installed")
    def test_mcp_shim_fails_loudly_without_data_root(self):
        e = {k: v for k, v in os.environ.items() if k not in STRIP}
        e["RUFLO_SSD_ROOT"] = str(self.t / "nossd")
        p = subprocess.run([NODE, str(SHIM), "mcp", "start"], stdin=subprocess.DEVNULL, capture_output=True, env=e,
                           timeout=30)
        self.assertEqual(p.returncode, 1)

    # ---- end-to-end against the locally installed ruflo plugin and helpers (skipped elsewhere, e.g. CI)

    def plugin_env(self, proj, ssd):
        e = {k: v for k, v in os.environ.items() if k not in STRIP}
        e.update(CLAUDE_PROJECT_DIR=str(proj), CLAUDE_PLUGIN_ROOT=str(PLUG), RUFLO_SSD_ROOT=str(ssd),
                 RUFLO_HOOK_CLI_OVERRIDE="%s -X utf8 %s cli" % (sys.executable, RUN), RUFLO_HOOK_SKIP_NPX="1")
        return e

    @unittest.skipUnless(PLUG.is_dir() and NODE and shutil.which("ruflo"), "ruflo plugin not installed")
    def test_e2e_post_command_keeps_project_clean(self):
        g = self.t / "gitrepo"
        g.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(g), check=True)
        ev = '{"tool_name":"Bash","tool_input":{"command":"echo e2e"},"tool_response":{"exit_code":0}}'
        js = ("process.argv=[process.argv[0],'x','post-command'];"
              "require(require('path').join(process.env.CLAUDE_PLUGIN_ROOT,'scripts','ruflo-hook.cjs'))")
        subprocess.run([NODE, "-e", js], cwd=str(g), input=ev, text=True, capture_output=True,
                       env=self.plugin_env(g, self.ssd), timeout=120)
        self.assertFalse((g / ".claude-flow").exists())
        self.assertFalse((g / ".swarm").exists())
        self.assertTrue(os.path.isdir(self.cache("gitrepo")))

    @unittest.skipUnless((HELPERS / "hook-handler.cjs").is_file() and NODE, "installed ruflo helpers absent")
    def test_session_restore_never_spawns_npx(self):
        fb = self.t / "fakebin"
        marker = self.t / "npx-marker"
        make_exe(fb, "npx", "open(%r, 'w').close()\n" % str(marker))
        proj = self.t / "proj6"
        proj.mkdir()
        self.run_py(["helper", "node", str(HELPERS / "hook-handler.cjs"), "session-restore"], stdin="{}",
                    path=str(fb) + os.pathsep + os.environ["PATH"], CLAUDE_PROJECT_DIR=str(proj),
                    RUFLO_SSD_ROOT=str(self.ssd))
        time.sleep(1)
        self.assertFalse(marker.exists())

    @unittest.skipUnless((HELPERS / "auto-memory-hook.mjs").is_file() and NODE, "installed ruflo helpers absent")
    def test_auto_memory_import_is_read_only(self):
        proj = self.t / "proj7"
        proj.mkdir()
        key = re.sub(r"[/_:]", "-", str(proj))
        md = self.t / "home" / ".claude" / "projects" / key / "memory"
        md.mkdir(parents=True)
        (md / "MEMORY.md").write_text("# Memory\n\n## Fact one\nSome remembered fact for the test.\n", encoding="utf-8")

        def snap():
            return sorted((str(p.relative_to(md)), hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "")
                          for p in md.rglob("*"))
        before = snap()
        rc, out = self.run_py(["helper", "node", str(HELPERS / "auto-memory-hook.mjs"), "import"], stdin="{}",
                              HOME=str(self.t / "home"), USERPROFILE=str(self.t / "home"),
                              CLAUDE_PROJECT_DIR=str(proj), RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual(snap(), before)
        self.assertRegex(out, r"Imported [1-9]")

    @unittest.skipUnless(PLUG.is_dir() and NODE, "ruflo plugin not installed")
    def test_e2e_mcp_store_lands_in_cache(self):
        r2 = self.t / "e2erepo"
        r2.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(r2), check=True)
        ssd2 = self.t / "ssd2"
        ssd2.mkdir()
        p = subprocess.run([NODE, str(HERE / "test_mcp.cjs"), str(r2), str(ssd2)], capture_output=True, text=True,
                           timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual([n for n in os.listdir(str(r2)) if n != ".git"], [])
        self.assertTrue((ssd2 / "_caches" / "ruflo" / "e2erepo" / "ruvector.db").is_file())


if __name__ == "__main__":
    unittest.main()
