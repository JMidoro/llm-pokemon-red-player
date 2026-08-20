param(
    [switch]$Portable
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found at $python. Create .venv and install the dev dependencies first."
}

function Invoke-Check {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host "`n== $Name =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

Push-Location $projectRoot
try {
    Invoke-Check "Repository metadata and hygiene" { & $python scripts\validate_repository.py }
    Invoke-Check "Python lint" { & $python -m ruff check . }
    if ($Portable) {
        Invoke-Check "ROM-free Python tests" { & $python -m pytest -q -m "not local_artifacts" }
    } else {
        Invoke-Check "Local artifact audit" { & $python scripts\audit_local_artifacts.py }
        Invoke-Check "Full local Python tests" { & $python -m pytest -q }
    }

    Push-Location (Join-Path $projectRoot "apps\lab-ui")
    try {
        Invoke-Check "Lab UI production build" { npm run build }
        Invoke-Check "Lab UI typecheck" { npm run typecheck }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}

Write-Host "`nAll checks passed."
