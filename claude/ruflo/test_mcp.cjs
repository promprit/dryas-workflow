// Realistic MCP check: start the ruflo-core plugin MCP launcher the way Claude Code does (stdio, cwd = project,
// settings env), send initialize + memory_store + memory_search, then exit. Usage: node test_mcp.cjs <repo> <ssdroot>
const { spawn } = require('child_process');
const os = require('os'), path = require('path');
const [repo, ssd] = process.argv.slice(2);
const PLUG = path.join(os.homedir(), '.claude/plugins/cache/ruflo/ruflo-core/0.2.6');
const C = path.join(ssd, '_caches/ruflo');
const env = { ...process.env, CLAUDE_PROJECT_DIR: repo, CLAUDE_PLUGIN_ROOT: PLUG, CLAUDE_FLOW_MCP_TRANSPORT: 'stdio',
  RUFLO_MCP_SKIP_NPX: '1', RUFLO_HOOK_SKIP_NPX: '1', RUFLO_NO_AUTO_ENABLE: '1', RUFLO_SSD_ROOT: ssd,
  ...(process.env.NO_SHIM ? {} : { RUFLO_MCP_CLI_OVERRIDE: path.join(os.homedir(), '.claude/ruflo/mcp-shim/bin/cli.js') }),
  CLAUDE_FLOW_MEMORY_PATH: C + '/memory', CLAUDE_FLOW_DB_PATH: C + '/memory/memory.db',
  CLAUDE_FLOW_SWARM_DIR: C + '/swarm', RUFLO_STATE_DIR: C + '/state', CLAUDE_FLOW_CWD: C + '/mcp' };
const p = spawn('node', [path.join(PLUG, 'scripts/mcp-launch.cjs')], { cwd: repo, env, stdio: ['pipe', 'pipe', 'pipe'] });
let buf = '', err = '';
const got = {};
p.stdout.on('data', d => { buf += d; let i; while ((i = buf.indexOf('\n')) >= 0) { const l = buf.slice(0, i); buf = buf.slice(i + 1); try { const m = JSON.parse(l); if (m.id) got[m.id] = m; } catch {} } });
p.stderr.on('data', d => err += d);
const send = m => p.stdin.write(JSON.stringify(m) + '\n');
send({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'test', version: '1' } } });
setTimeout(() => send({ jsonrpc: '2.0', method: 'notifications/initialized' }), 1500);
setTimeout(() => send({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'memory_store', arguments: { key: 'k1', value: 'v1', namespace: 'testns' } } }), 2000);
setTimeout(() => send({ jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'memory_search', arguments: { query: 'v1', namespace: 'testns' } } }), 6000);
setTimeout(() => { p.kill('SIGTERM');
  const ok = got[1] && got[2];
  console.log(JSON.stringify({ initialize: !!got[1], store: got[2] && JSON.stringify(got[2]).slice(0, 160), search: got[3] && JSON.stringify(got[3]).slice(0, 120), stderr: err.slice(0, 300) }));
  process.exit(ok ? 0 : 3); }, 12000);
