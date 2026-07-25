$ErrorActionPreference = "Stop"

$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidPath = Join-Path $workspace ".server.pid"
if (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Host "No managed background server PID was found."
    exit 0
}

$serverPid = [int](Get-Content -LiteralPath $pidPath)
$process = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
if ($process -and $process.ProcessName -eq "python") {
    Stop-Process -Id $serverPid
    Write-Host "Stopped the local Frameclean server."
} else {
    Write-Host "The recorded process is no longer running."
}
Remove-Item -LiteralPath $pidPath -Force

