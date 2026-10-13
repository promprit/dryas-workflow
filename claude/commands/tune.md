---
description: Weekly Jev calibration - override rates, judged share, frontier dispatches, swarm vs plain, spend; propose threshold changes
---
1. Run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/tune.py" report`.
2. (ruflo-cost-tracker is disabled) Note Claude-side usage from `/cost` beside the Jev spend if available.
3. Present the report and each proposal with its reason. Ask the user to approve or reject each one individually.
4. For each approved proposal only: `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/tune.py" apply <key> '<json value>'`. Never apply anything unapproved.
5. Show the final ~/.dryas/jev/thresholds.json.
