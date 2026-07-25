$ErrorActionPreference = "Stop"

$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $workspace

$samEnvironment = Join-Path $workspace ".sam2-venv"
$samConfig = Join-Path $samEnvironment "pyvenv.cfg"
if (-not (Test-Path -LiteralPath $samConfig)) {
    throw "Install and verify SAM 2.1 before installing ProPainter."
}

$pythonHomeLine = Get-Content -LiteralPath $samConfig |
    Where-Object { $_ -match "^home\s*=" } |
    Select-Object -First 1
if (-not $pythonHomeLine) {
    throw "Could not locate the Python 3.10 runtime used by SAM 2.1."
}
$pythonHome = ($pythonHomeLine -split "=", 2)[1].Trim()
$basePython = Join-Path $pythonHome "python.exe"
if (-not (Test-Path -LiteralPath $basePython)) {
    throw "The shared Python 3.10 executable is missing: $basePython"
}

$repository = Join-Path $workspace "vendor\ProPainter"
if (-not (Test-Path -LiteralPath (Join-Path $repository "inference_propainter.py"))) {
    git clone --depth 1 https://github.com/sczhou/ProPainter.git $repository
}

$environment = Join-Path $workspace ".propainter-venv"
$environmentPython = Join-Path $environment "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $environmentPython)) {
    & $basePython -m venv $environment
}
& $environmentPython -m ensurepip --upgrade --default-pip

$overlay = Join-Path $environment "Lib\site-packages\sam2_cuda_runtime.pth"
$samPackages = (Resolve-Path (Join-Path $samEnvironment "Lib\site-packages")).Path
Set-Content -LiteralPath $overlay -Value $samPackages

& $environmentPython -m pip install `
    av addict einops future scipy matplotlib scikit-image `
    imageio-ffmpeg requests timm yapf imageio

$weights = Join-Path $repository "weights"
New-Item -ItemType Directory -Path $weights -Force | Out-Null
$release = "https://github.com/sczhou/ProPainter/releases/download/v0.1.0"
foreach ($filename in @(
    "raft-things.pth",
    "recurrent_flow_completion.pth",
    "ProPainter.pth"
)) {
    $target = Join-Path $weights $filename
    if (-not (Test-Path -LiteralPath $target)) {
        & curl.exe -L --fail --retry 3 "$release/$filename" -o $target
        if ($LASTEXITCODE -ne 0) {
            throw "Could not download $filename"
        }
    }
}

& $environmentPython -c `
    "import torch, av, scipy, skimage, imageio; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"

Write-Host "ProPainter is installed for non-commercial local use." -ForegroundColor Green
Write-Host "Restart Frameclean so /api/health reports propainter: true."
