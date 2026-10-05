# Dryas Workflow installer for native Windows. Finds Python >= 3.9 and runs install\dryas_install.py.
# Usage: .\install\install.ps1 [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design] [--yes] [--force]
#        [--dry-run] [--uninstall] [--preflight-only] [--harness claude|codex|both]   See docs\install.md.
# DRYAS_PYTHON overrides the interpreter.
$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'install\dryas_install.py'
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
    & $exe @pre $script run --repo $repo @args
    exit $LASTEXITCODE
  }
}
Write-Host 'Missing: Python >= 3.9. Install it and re-run (this installer never installs system packages).'
exit 1
