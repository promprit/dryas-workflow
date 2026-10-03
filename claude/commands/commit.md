---
description: Conventional commit, gated by a Jev "safe to commit?" check
argument-hint: [message hint]
---
1. Run `git status --short` and `git diff --cached --stat` (stage named files only if nothing is staged; never `git add -A`, never stage .env* or other secrets).
2. Secret scan. First run `git diff --cached --name-only` and STOP if any staged path matches (case-insensitive) `(^|/)\.env($|\.)`, `\.pem$`, `\.key$`, `\.p12$`, `id_rsa`, `id_ed25519`, `credentials`, `\.keychain`, `secrets?\.(json|ya?ml|toml)$`. Then grep the staged diff (`git diff --cached -U0`) for `sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\.` and STOP on any hit (report file + line, never print the secret). Only then set `secret_scan: "clean"` in Jev's state.
3. Call `mcp__jev__jev_judge` with state `{branch, staged_files, diff_stat, last_test_run_tail, secret_scan: "clean"}` and question `safe_to_commit` noul: "Is this staged change safe and coherent to commit as one commit?"
4. If confidence ≥ `commit.min_confidence` (thresholds.json) and Jev's `value` ≥ 0.5: commit. If confidently unsafe: stop and say why. Otherwise you (Opus) decide; if you commit against Jev's answer, call `mcp__jev__log_override`.
5. Message: Conventional Commits (`type(scope): summary`), body explains why. "$ARGUMENTS" is a hint. Never push.
