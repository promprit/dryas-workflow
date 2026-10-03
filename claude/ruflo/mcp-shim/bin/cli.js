#!/usr/bin/env node
// Target of RUFLO_MCP_CLI_OVERRIDE: the ruflo-core plugin launcher runs `node <this> mcp start` with cwd = the
// project. This shim moves the server into $DRYAS_DATA_ROOT/ruflo/<ns> (so `.claude-flow/`,
// `.swarm/`, `ruvector.db` land in the data root, not in the project) and runs the PINNED ruflo CLI (no npx).
// Unlike hooks, MCP must fail loudly: data root or pinned CLI missing -> exit 1 (Claude shows the server disconnected).
// (../dist is a symlink so the launcher's isRunnableCli() check passes.)
'use strict';
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');
function fail(m) { process.stderr.write('[ruflo-mcp-shim] ' + m + '\n'); process.exit(1); }
function dataRoot() {
  const t = process.env.RUFLO_SSD_ROOT;
  if (t) return fs.existsSync(t) ? path.join(t, '_caches') : null;
  const r = process.env.DRYAS_DATA_ROOT || path.join(os.homedir(), '.dryas');
  return fs.existsSync(r) ? r : null;
}
function globalRufloJs() {
  try { return path.join(execFileSync('npm', ['root', '-g'], { encoding: 'utf8' }).trim(), 'ruflo', 'bin', 'ruflo.js'); }
  catch (e) { return ''; }
}
const ROOT = dataRoot();
const RUFLO_JS = process.env.RUFLO_JS || globalRufloJs();
if (!ROOT) fail('data root missing (DRYAS_DATA_ROOT not mounted or not created)');
if (!RUFLO_JS || !fs.existsSync(RUFLO_JS)) fail('ruflo CLI not found: ' + (RUFLO_JS || '(npm root -g failed)'));
let ns;
try {
  ns = execFileSync('/bin/sh', ['-c', '. "$1"; ruflo_ns', 'sh', path.join(__dirname, '..', '..', 'ns.sh')], { encoding: 'utf8' }).trim();
} catch (e) { fail('namespace detection failed: ' + e.message); }
if (!ns) fail('empty namespace');
const dir = path.join(ROOT, 'ruflo', ns);
try { fs.mkdirSync(dir, { recursive: true }); } catch (e) { fail('cannot create ' + dir + ': ' + e.message); }
const child = spawn(process.execPath, [RUFLO_JS, ...process.argv.slice(2)], {
  cwd: dir, stdio: 'inherit',
  env: { ...process.env, CLAUDE_FLOW_CWD: dir, RUFLO_NO_AUTO_ENABLE: '1', RUFLO_DAEMON_AUTOSTART: '0', RUFLO_MCP_SKIP_NPX: '1' },
});
for (const s of ['SIGINT', 'SIGTERM']) process.on(s, () => child.kill(s));
child.on('exit', (code, sig) => { if (sig) process.kill(process.pid, sig); else process.exit(code === null ? 1 : code); });
child.on('error', (e) => fail('spawn failed: ' + e.message));
