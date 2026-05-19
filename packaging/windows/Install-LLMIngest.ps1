param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\LLMIngest",
    [switch]$DesktopShortcut,
    [switch]$NoStartMenuShortcut
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Payload = Join-Path $SourceRoot "LLMIngest"
$Exe = Join-Path $Payload "LLMIngest.exe"

if (-not (Test-Path $Exe)) {
    throw "Installer payload is missing LLMIngest.exe at $Exe"
}

Write-Host "Installing LLM Ingest to $InstallDir"
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item -Path (Join-Path $Payload "*") -Destination $InstallDir -Recurse -Force

$InstalledExe = Join-Path $InstallDir "LLMIngest.exe"
$Shell = New-Object -ComObject WScript.Shell

if (-not $NoStartMenuShortcut) {
    $StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\LLM Ingest"
    New-Item -ItemType Directory -Path $StartMenuDir -Force | Out-Null
    $Shortcut = $Shell.CreateShortcut((Join-Path $StartMenuDir "LLM Ingest.lnk"))
    $Shortcut.TargetPath = $InstalledExe
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Description = "LLM Ingest"
    $Shortcut.Save()
}

if ($DesktopShortcut) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $Shortcut = $Shell.CreateShortcut((Join-Path $Desktop "LLM Ingest.lnk"))
    $Shortcut.TargetPath = $InstalledExe
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Description = "LLM Ingest"
    $Shortcut.Save()
}

Write-Host "Installed LLM Ingest."
Write-Host "Executable: $InstalledExe"
