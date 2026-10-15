---
description: Run a multi-step task with the strong-tier orchestrator, fast-first executors and Jev gates
argument-hint: <task>
allowed-tools: Read, Edit, Write, Glob, Grep, Agent, ToolSearch, Skill(dryas:brainstorm), Skill(dryas:worktree), Skill(dryas:debug), Skill(dryas:verify), Skill(dryas:review-request), Skill(dryas:review-receive), Bash(git worktree:*), Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git branch:*), Bash(git merge:*), Bash(git merge-base:*), Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/planfile.py" section:*), Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/task_review.py" answer:*), mcp__plugin_dryas_jev__jev_judge, mcp__plugin_dryas_jev__log_override, mcp__plugin_dryas_jev__log_escalation, mcp__plugin_dryas_jev__log_dispatch, mcp__plugin_dryas_jev__log_merge, mcp__plugin_dryas_jev__log_review, mcp__plugin_ruflo-core_ruflo__memory_search, mcp__plugin_ruflo-core_ruflo__memory_store, mcp__plugin_ruflo-core_ruflo__swarm_init, Bash(git add:*), Bash(git commit:*), Bash(grep:*), Read(~/.dryas/jev/thresholds.json)
disable-model-invocation: true
---
Use the orchestrate skill (${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/SKILL.md) for this task: $ARGUMENTS
