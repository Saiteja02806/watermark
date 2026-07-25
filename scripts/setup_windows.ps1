$ErrorActionPreference = "Stop"

$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $workspace

$pythonCandidates = @(
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

if (-not $pythonCandidates) {
    throw "Python 3.11 or 3.12 is required. Install Python, then rerun this script."
}

$python = $pythonCandidates[0]
if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    & $python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install -r apps\api\requirements.txt
cmd /c npm install
cmd /c npm run build

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Start with: .\scripts\start_local.ps1"

