---
name: tune
description: Weekly Jev calibration - override rates, judged share, escalations and spend; propose threshold changes for the user to approve. Use for $dryas:tune.
---

`<dryas-root>` and `<dryas-py>` are given in the Dryas rules ("Dryas paths:"). If they are missing, the Dryas hooks are not trusted: tell the user to run /hooks in Codex and stop.

1. Run `"<dryas-py>" -X utf8 "<dryas-root>/jev/tune.py" report` (PowerShell: prefix `& `).
2. Present the report and each proposal with its reason. Ask the user to approve or reject each one separately.
3. For each approved proposal only, run `"<dryas-py>" -X utf8 "<dryas-root>/jev/tune.py" apply <key> '<json value>'`. Never apply anything unapproved.
4. Show the final `~/.dryas/jev/thresholds.json`.
