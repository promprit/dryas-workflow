---
name: commit
description: Conventional commit gated by a secret scan and a Jev "safe to commit?" check. Never pushes. Use for $commit.
---

1. Run `git status --short` and `git diff --cached --stat`. If nothing is staged, stage the named files only; never `git add -A`, never stage `.env*` or other secrets.
2. **Secret scan.** Stop if any staged path (`git diff --cached --name-only`) matches, case-insensitive, `(^|/)\.env($|\.)`, `\.pem$`, `\.key$`, `\.p12$`, `id_rsa`, `id_ed25519`, `credentials`, `\.keychain` or `secrets?\.(json|ya?ml|toml)$`. Then search `git diff --cached -U0` for `sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\.` and stop on any hit (report file and line; never print the secret).
3. Call `jev_judge` (server `jev`) with state `{branch, staged_files, diff_stat, last_test_run_tail, secret_scan: "clean"}` and one noul question `safe_to_commit`: "Is this staged change safe and coherent to commit as one commit?"
4. Commit if the confidence is at least `commit.min_confidence` in `{{CD}}/jev/thresholds.json` and the value is at least 0.5. If Jev is confident it is unsafe, stop and say why. Otherwise you decide; if you commit against Jev's answer, call `log_override`.
5. Message: Conventional Commits (`type(scope): summary`); the body explains why and names the harness (Codex). Never push.
