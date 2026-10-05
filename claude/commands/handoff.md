---
description: Score this session with Jev and save a handoff; then /clear starts fresh with only what matters
---

Run exactly this command with the Bash tool, then show its one-line output to the user:

```
"{{PY}}" -X utf8 "{{CD}}/jev/handoff.py" save --cwd "$PWD"
```

Then tell the user to type `/clear` (Claude cannot run `/clear` itself). Do nothing else.
