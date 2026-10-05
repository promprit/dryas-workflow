#!/usr/bin/env node
// Target of RUFLO_MCP_CLI_OVERRIDE: the ruflo-core plugin launcher runs `node <this> mcp start` with cwd = the
// project. This shim moves the server into $DRYAS_DATA_ROOT/ruflo/<ns> (so `.claude-flow/`,
// `.swarm/`, `ruvector.db` land in the data root, not in the project) and runs the PINNED ruflo CLI (no npx).
// Unlike hooks, MCP must fail loudly: data root or pinned CLI missing -> exit 1 (Claude shows the server disconnected).
// (../dist is a symlink or a Windows junction so the launcher's isRunnableCli() check passes.)
// Namespace rules match ../../ns.py; shared vectors: ../../tests/ns_cases.json.
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
  try {
    const win = process.platform === 'win32';
    // npm is npm.cmd on Windows and Node refuses to spawn .cmd files without a shell (fixed arguments, no user input).
    const root = execFileSync(win ? 'npm.cmd' : 'npm', ['root', '-g'], { encoding: 'utf8', shell: win }).trim();
    return path.join(root, 'ruflo', 'bin', 'ruflo.js');
  } catch (e) { return ''; }
}
function parts(p) { return p.replace(/\\/g, '/').replace(/\/+$/, '').split('/'); }
function nsFrom(start, common) {
  let name = null;
  if (common) {
    const c = parts(common);
    if (c.length >= 2 && c[c.length - 1] === '.git' && c[c.length - 2]) name = c[c.length - 2];
  }
  if (name === null) { const s = parts(start); name = s[s.length - 1]; }
  name = name.replace(/[^A-Za-z0-9._-]/g, '_');
  return (name === '' || name === '.' || name === '..') ? '_unknown' : name;
}
function rufloNs() {
  const start = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  let common = null;
  try {
    common = execFileSync('git', ['-C', start, 'rev-parse', '--path-format=absolute', '--git-common-dir'],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim() || null;
  } catch (e) { common = null; }
  return nsFrom(start, common);
}
function main() {
  const ROOT = dataRoot();
  const RUFLO_JS = process.env.RUFLO_JS || globalRufloJs();
  if (!ROOT) fail('data root missing (DRYAS_DATA_ROOT not mounted or not created)');
  if (!RUFLO_JS || !fs.existsSync(RUFLO_JS)) fail('ruflo CLI not found: ' + (RUFLO_JS || '(npm root -g failed)'));
  const ns = rufloNs();
  const dir = path.join(ROOT, 'ruflo', ns);
  try { fs.mkdirSync(dir, { recursive: true }); } catch (e) { fail('cannot create ' + dir + ': ' + e.message); }
  const child = spawn(process.execPath, [RUFLO_JS, ...process.argv.slice(2)], {
    cwd: dir, stdio: 'inherit',
    env: { ...process.env, CLAUDE_FLOW_CWD: dir, RUFLO_NO_AUTO_ENABLE: '1', RUFLO_DAEMON_AUTOSTART: '0', RUFLO_MCP_SKIP_NPX: '1' },
  });
  for (const s of ['SIGINT', 'SIGTERM']) process.on(s, () => child.kill(s));
  child.on('exit', (code, sig) => { if (sig) process.kill(process.pid, sig); else process.exit(code === null ? 1 : code); });
  child.on('error', (e) => fail('spawn failed: ' + e.message));
}
module.exports = { nsFrom };
if (require.main === module) main();
