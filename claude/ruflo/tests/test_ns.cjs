// Checks nsFrom() in mcp-shim/bin/cli.js against the shared vectors (ns_cases.json, next to this file). Usage: node test_ns.cjs
'use strict';
const path = require('path');
const { nsFrom } = require(path.join(__dirname, '..', 'mcp-shim', 'bin', 'cli.js'));
const cases = require(path.join(__dirname, 'ns_cases.json'));
let fail = 0;
for (const c of cases) {
  const got = typeof nsFrom === 'function' ? nsFrom(c.start, c.common) : undefined;
  if (got === c.expect) console.log('PASS ' + JSON.stringify(c.start));
  else { console.log('FAIL ' + JSON.stringify(c) + ' got ' + JSON.stringify(got)); fail = 1; }
}
process.exit(fail);
