# Dryas Workflow installer for native Windows. Finds Python >= 3.9 and runs install\dryas_install.py.
# Usage: .\install\install.ps1 [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design] [--no-pstack-picks] [--yes] [--force]
#        [--dry-run] [--uninstall] [--purge] [--preflight-only] [--harness claude|codex|both]
#        [--claude-dir DIR] [--codex-dir DIR] [--flowobserve|--no-flowobserve] [--openrouter-key KEY]   See docs\install.md.
#        .\install\install.ps1 -Repo PATH [--yes] [--force] [--prefix P] [--with-design] [--with-own NAME] [--persist-memory]
#                   sets the repo at PATH up for claude.ai/code cloud sessions (tools\dryas_cloud.py init; docs\cloud-sessions.md)
# Claude Code: run once per config dir (--claude-dir; default $env:CLAUDE_CONFIG_DIR, else ~\.claude).
# Codex: run once per CODEX_HOME (--codex-dir; default $env:CODEX_HOME, else ~\.codex).
# Jev reads $env:OPENROUTER_API_KEY from the shell; --openrouter-key also stores a key as the plugin option.
# DRYAS_PYTHON overrides the interpreter.
$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'install\dryas_install.py'
$cloud = $false  # -Repo PATH (or --repo PATH): set that repo up for cloud sessions instead of installing the plugin
foreach ($arg in $args) { if ($arg -eq '-Repo' -or $arg -eq '--repo' -or "$arg".StartsWith('--repo=')) { $cloud = $true } }
$candidates = @()
if ($env:DRYAS_PYTHON) { $candidates += ,@($env:DRYAS_PYTHON) }
$candidates += ,@('py', '-3')
$candidates += ,@('python')
$candidates += ,@('python3')
foreach ($c in $candidates) {
  $exe = $c[0]
  $pre = @()
  if ($c.Count -gt 1) { $pre = $c[1..($c.Count - 1)] }
  if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
  & $exe @pre -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>$null
  if ($LASTEXITCODE -eq 0) {
    if ($exe -ne 'py') { $env:DRYAS_PYTHON_PATH = (Get-Command $exe).Source }
    if ($cloud) {
      $fwd = @($args | ForEach-Object { if ($_ -eq '-Repo') { '--repo' } else { $_ } })
      & $exe @pre (Join-Path $repo 'tools\dryas_cloud.py') init @fwd
      exit $LASTEXITCODE
    }
    & $exe @pre $script run --repo $repo @args
    exit $LASTEXITCODE
  }
}
Write-Host 'Missing: Python >= 3.9. Install it and re-run (this installer never installs system packages).'
exit 1
