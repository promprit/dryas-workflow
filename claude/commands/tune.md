---
description: Weekly Jev calibration - override rates, judged share, Fable dispatches, swarm vs plain, spend; propose threshold changes
---
1. Run `"{{PY}}" -X utf8 "{{CD}}/jev/tune.py" report`.
2. (ruflo-cost-tracker is disabled) Note Claude-side usage from `/cost` beside the Jev spend if available.
3. Present the report and each proposal with its reason. Ask the user to approve or reject each one individually.
4. For each approved proposal only: `"{{PY}}" -X utf8 "{{CD}}/jev/tune.py" apply <key> '<json value>'`. Never apply anything unapproved.
5. Show the final ~/.claude/jev/thresholds.json.
