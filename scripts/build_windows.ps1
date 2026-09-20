param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host ""
Write-Host "=== StreamingFinder Windows Build ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

if (-not $SkipInstall) {
    Write-Host "Installing build dependencies..." -ForegroundColor DarkCyan
    python -m pip install -e ".[dev,build]"
}

Write-Host "Running tests..." -ForegroundColor DarkCyan
python -m pytest
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed. Build cancelled."
}

Write-Host "Building StreamingFinder.exe..." -ForegroundColor DarkCyan
python -m PyInstaller --noconfirm --clean streaming_finder.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$ExePath = Join-Path $ProjectRoot "dist\StreamingFinder\StreamingFinder.exe"
if (-not (Test-Path $ExePath)) {
    throw "Build completed but StreamingFinder.exe was not found at $ExePath"
}

Write-Host ""
Write-Host "Build complete:" -ForegroundColor Green
Write-Host $ExePath
