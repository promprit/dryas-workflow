---
name: tune
description: Weekly Jev calibration - override rates, judged share, escalations and spend; propose threshold changes for the user to approve. Use for $dryas:tune.
---

`<dryas-root>` and `<dryas-py>` are given in the Dryas rules ("Dryas paths:"). If they are missing, the Dryas hooks are not trusted: tell the user to run /hooks in Codex and stop.

1. Run `"<dryas-py>" -X utf8 "<dryas-root>/jev/tune.py" report` (PowerShell: prefix `& `).
2. Present the report and each proposal with its reason. Ask the user to approve or reject each one separately.
3. For each approved proposal only, run `"<dryas-py>" -X utf8 "<dryas-root>/jev/tune.py" apply <key> '<json value>'`. Never apply anything unapproved.
4. Show the final `~/.dryas/jev/thresholds.json`.

**Judge disagreements.** `CORPUS_CANDIDATES_JSON` lists commands where the deciding judge and its shadow disagreed (patterns only, redacted). Show them to the user. For each one the user accepts, add a row to `reference/judge-corpus/commands.jsonl` in the dryas-workflow repo with the verdict the user says is right, and a local-judge rule change in a plan. Never paste file contents.

**Allowlist.** A `gate.allowlist` proposal in `$dryas:tune` comes from local asks this user approved at least `gate.allowlist_min_approvals` times. Proposals come only from approved local Bash asks, never from denies or edits, by design. Apply it only after the user approves (`tune.py apply gate.allowlist '<json>'`). Dangerous or destructive entries are refused.
