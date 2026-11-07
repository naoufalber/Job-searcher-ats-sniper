param(
  [ValidateSet('start', 'stop', 'reset', 'status', 'seed')]
  [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$supabaseCommand = (Get-Command supabase -ErrorAction SilentlyContinue).Source
if (-not $supabaseCommand) {
  $supabaseCommand = Join-Path $repoRoot 'apps/web/node_modules/.bin/supabase.cmd'
}
if (-not (Test-Path -LiteralPath $supabaseCommand)) {
  throw 'The project-local Supabase CLI is unavailable. Run npm ci from apps/web first.'
}

if ($env:SUPABASE_DB_URL -or $env:SUPABASE_PROJECT_REF) {
  throw 'Refusing local workflow while hosted Supabase connection variables are present in this shell.'
}

switch ($Action) {
  'start'  { & $supabaseCommand start }
  'stop'   { & $supabaseCommand stop }
  'status' { & $supabaseCommand status }
  'reset'  {
    Write-Host 'Resetting only the local Supabase database and reapplying migrations/seed.sql.' -ForegroundColor Yellow
    & $supabaseCommand db reset
  }
  'seed' {
    Write-Host 'Use reset to apply migrations and the deterministic local seed safely.' -ForegroundColor Yellow
    & $supabaseCommand db reset
  }
}
