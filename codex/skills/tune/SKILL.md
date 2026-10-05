---
name: tune
description: Weekly Jev calibration - override rates, judged share, escalations and spend; propose threshold changes for the user to approve. Use for $tune.
---

1. Run `"{{PY}}" -X utf8 "{{CD}}/jev/tune.py" report` (PowerShell: prefix `& `).
2. Present the report and each proposal with its reason. Ask the user to approve or reject each one separately.
3. For each approved proposal only, run `"{{PY}}" -X utf8 "{{CD}}/jev/tune.py" apply <key> '<json value>'`. Never apply anything unapproved.
4. Show the final `{{CD}}/jev/thresholds.json`.
