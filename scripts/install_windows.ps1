param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host ""
Write-Host "=== StreamingFinder Windows Installer ===" -ForegroundColor Cyan

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot "build_windows.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed. Installation cancelled."
    }
}

$BuiltDir = Join-Path $ProjectRoot "dist\StreamingFinder"
$BuiltExe = Join-Path $BuiltDir "StreamingFinder.exe"
if (-not (Test-Path $BuiltExe)) {
    throw "StreamingFinder.exe was not found. Run scripts\build_windows.ps1 first."
}

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\StreamingFinder"
$DataDir = Join-Path $env:LOCALAPPDATA "StreamingFinder"
$DesktopDir = [Environment]::GetFolderPath("Desktop")
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$DesktopShortcut = Join-Path $DesktopDir "StreamingFinder.lnk"
$StartMenuShortcut = Join-Path $StartMenuDir "StreamingFinder.lnk"

Write-Host "Installing application to $InstallDir" -ForegroundColor DarkCyan
if (Test-Path $InstallDir) {
    Remove-Item $InstallDir -Recurse -Force
}
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item (Join-Path $BuiltDir "*") $InstallDir -Recurse -Force

Write-Host "Preparing persistent app data at $DataDir" -ForegroundColor DarkCyan
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null

$SourceEnv = Join-Path $ProjectRoot ".env"
$InstalledEnv = Join-Path $DataDir ".env"
if ((Test-Path $SourceEnv) -and -not (Test-Path $InstalledEnv)) {
    Copy-Item $SourceEnv $InstalledEnv
    Write-Host "Copied your TMDB configuration into AppData." -ForegroundColor Green
} elseif (-not (Test-Path $InstalledEnv)) {
    Write-Warning "No .env file was found. StreamingFinder will need TMDB_READ_ACCESS_TOKEN configured before online features work."
}

$SourceDatabase = Join-Path $ProjectRoot "data\streaming_finder.db"
$InstalledDatabase = Join-Path $DataDir "streaming_finder.db"
if ((Test-Path $SourceDatabase) -and -not (Test-Path $InstalledDatabase)) {
    Copy-Item $SourceDatabase $InstalledDatabase
    Write-Host "Migrated your existing StreamingFinder library and ratings." -ForegroundColor Green
} elseif (Test-Path $InstalledDatabase) {
    Write-Host "Existing AppData database preserved." -ForegroundColor DarkGreen
}

function New-StreamingFinderShortcut([string]$ShortcutPath) {
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = Join-Path $InstallDir "StreamingFinder.exe"
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.IconLocation = "$(Join-Path $InstallDir 'StreamingFinder.exe'),0"
    $Shortcut.Description = "StreamingFinder"
    $Shortcut.Save()
}

New-StreamingFinderShortcut $DesktopShortcut
New-StreamingFinderShortcut $StartMenuShortcut

Write-Host ""
Write-Host "StreamingFinder is installed." -ForegroundColor Green
Write-Host "Desktop shortcut: $DesktopShortcut"
Write-Host "Start menu shortcut: $StartMenuShortcut"
Write-Host "Persistent data: $DataDir"
Write-Host ""
Write-Host "You can now close VS Code and launch StreamingFinder from the desktop icon." -ForegroundColor Cyan
