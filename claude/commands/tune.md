---
description: Weekly Jev calibration - override rates, judged share, frontier dispatches, swarm vs plain, spend; propose threshold changes
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/tune.py" report), Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/tune.py" apply:*), Read(~/.dryas/jev/thresholds.json)
disable-model-invocation: true
---
1. Run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/tune.py" report`.
2. Note Claude-side usage from `/cost` beside the Jev spend if available.
3. Present the report and each proposal with its reason. Ask the user to approve or reject each one individually.
4. For each approved proposal only: `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/tune.py" apply <key> '<json value>'`. Never apply anything unapproved.
5. Show the final ~/.dryas/jev/thresholds.json.

**Judge disagreements.** `CORPUS_CANDIDATES_JSON` lists commands where the deciding judge and its shadow disagreed (patterns only, redacted). Show them to the user. For each one the user accepts, add a row to `reference/judge-corpus/commands.jsonl` in the dryas-workflow repo with the verdict the user says is right, and a local-judge rule change in a plan. Never paste file contents.

**Allowlist.** A `gate.allowlist` proposal comes from local asks this user approved at least `gate.allowlist_min_approvals` times. Apply it only after the user approves (`tune.py apply gate.allowlist '<json>'`). Dangerous or destructive entries are refused.
