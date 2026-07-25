$ErrorActionPreference = "Stop"

$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $workspace

$python = Join-Path $workspace ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "API environment is missing. Run .\scripts\setup_windows.ps1 first."
}

if (-not (Test-Path -LiteralPath ".\apps\web\dist\index.html")) {
    cmd /c npm run build
}

Write-Host "Frameclean is running at http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop."
& $python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

