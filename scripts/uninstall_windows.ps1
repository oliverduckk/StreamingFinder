param(
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\StreamingFinder"
$DataDir = Join-Path $env:LOCALAPPDATA "StreamingFinder"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "StreamingFinder.lnk"
$StartMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\StreamingFinder.lnk"

foreach ($Path in @($DesktopShortcut, $StartMenuShortcut)) {
    if (Test-Path $Path) {
        Remove-Item $Path -Force
    }
}

if (Test-Path $InstallDir) {
    Remove-Item $InstallDir -Recurse -Force
}

if ($RemoveData -and (Test-Path $DataDir)) {
    Remove-Item $DataDir -Recurse -Force
    Write-Host "StreamingFinder application and personal data removed." -ForegroundColor Green
} else {
    Write-Host "StreamingFinder application removed. Personal data was preserved at:" -ForegroundColor Green
    Write-Host $DataDir
}
