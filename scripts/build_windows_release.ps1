param(
    [switch]$IncludeOptional,
    [switch]$IncludeDocling,
    [switch]$IncludeMinerU,
    [switch]$IncludeUnstructured,
    [switch]$All,
    [switch]$Clean,
    [switch]$SkipTests,
    [switch]$SkipInno,
    [switch]$InstallInno
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$BuildVenv = Join-Path $ProjectRoot ".build_venv"
$BuildPython = Join-Path $BuildVenv "Scripts\python.exe"
$ReleaseRoot = Join-Path $ProjectRoot "release"
$InstallerRoot = Join-Path $ReleaseRoot "LLMIngest-Windows"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    Write-Host "$FilePath $($Arguments -join ' ')" -ForegroundColor DarkGray
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Find-PythonCommand {
    $LocalPython = Join-Path $ProjectRoot "_python313\runtime\python.exe"
    if (Test-Path $LocalPython) {
        return @{ File = $LocalPython; Args = @() }
    }
    $candidates = @(
        @{ File = "py"; Args = @("-3.13") },
        @{ File = "py"; Args = @("-3.12") },
        @{ File = "py"; Args = @("-3.11") },
        @{ File = "python"; Args = @() },
        @{ File = "python3"; Args = @() }
    )
    foreach ($candidate in $candidates) {
        if (Get-Command $candidate.File -ErrorAction SilentlyContinue) {
            & $candidate.File @($candidate.Args + @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)")) 2>$null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        }
    }
    throw "Python 3.11+ was not found. Install Python 3.11, 3.12, or 3.13 before building the release."
}

function Invoke-BasePython {
    param([object]$Python, [string[]]$Arguments)
    Invoke-Checked $Python.File (@($Python.Args) + @($Arguments))
}

function Find-InnoCompiler {
    $command = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Antigravity\resources\app\node_modules\innosetup\bin\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate) {
            try {
                if (Test-Path -LiteralPath $candidate -PathType Leaf -ErrorAction Stop) {
                    return $candidate
                }
            }
            catch {
                Write-Host "Skipping inaccessible Inno Setup candidate: $candidate"
            }
        }
    }
    return $null
}

function Assert-FrozenTkinterPayload {
    param([string]$AppRoot)

    $requiredFiles = @(
        "_internal\_tkinter.pyd",
        "_internal\tcl86t.dll",
        "_internal\tk86t.dll"
    )
    $requiredDirs = @(
        "_internal\tcl",
        "_internal\tk"
    )
    $missing = @()

    foreach ($relativePath in $requiredFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $AppRoot $relativePath) -PathType Leaf)) {
            $missing += $relativePath
        }
    }
    foreach ($relativePath in $requiredDirs) {
        if (-not (Test-Path -LiteralPath (Join-Path $AppRoot $relativePath) -PathType Container)) {
            $missing += $relativePath
        }
    }

    if ($missing.Count -gt 0) {
        throw "Frozen app is missing tkinter runtime files: $($missing -join ', '). Rebuild with a Python runtime that includes tkinter/Tcl/Tk."
    }
}

Set-Location $ProjectRoot

if ($Clean) {
    Write-Step "Cleaning previous build outputs"
    foreach ($path in @($BuildVenv, (Join-Path $ProjectRoot "build"), (Join-Path $ProjectRoot "dist"), $ReleaseRoot)) {
        if (Test-Path $path) {
            Remove-Item -Path $path -Recurse -Force
        }
    }
}

$Python = Find-PythonCommand

Write-Step "Creating build virtual environment"
if (-not (Test-Path $BuildPython)) {
    Invoke-BasePython $Python @("-m", "venv", $BuildVenv)
}

Write-Step "Installing build dependencies"
Invoke-Checked $BuildPython @("-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools")
Invoke-Checked $BuildPython @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements\base.txt"), "pyinstaller")

if ($All -or $IncludeOptional) {
    Invoke-Checked $BuildPython @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements\optional.txt"))
}
if ($All -or $IncludeDocling) {
    Invoke-Checked $BuildPython @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements\docling.txt"))
}
if ($All -or $IncludeMinerU) {
    Invoke-Checked $BuildPython @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements\mineru.txt"))
}
if ($All -or $IncludeUnstructured) {
    Invoke-Checked $BuildPython @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements\unstructured.txt"))
}

if (-not $SkipTests) {
    Write-Step "Running tests before packaging"
    Invoke-Checked $BuildPython @("-m", "unittest", "discover", "-s", "tests")
}

Write-Step "Building LLMIngest.exe with PyInstaller"
Invoke-Checked $BuildPython @("-m", "PyInstaller", "--noconfirm", "--clean", (Join-Path $ProjectRoot "packaging\LLMIngest.spec"))

$BuiltApp = Join-Path $ProjectRoot "dist\LLMIngest"
$BuiltExe = Join-Path $BuiltApp "LLMIngest.exe"
if (-not (Test-Path $BuiltExe)) {
    throw "PyInstaller did not produce $BuiltExe"
}
Assert-FrozenTkinterPayload $BuiltApp

Write-Step "Creating self-contained installer folder"
New-Item -ItemType Directory -Path $InstallerRoot -Force | Out-Null
Copy-Item -Path $BuiltApp -Destination $InstallerRoot -Recurse -Force
Copy-Item -Path (Join-Path $ProjectRoot "packaging\windows\Install-LLMIngest.ps1") -Destination $InstallerRoot -Force
Copy-Item -Path (Join-Path $ProjectRoot "packaging\windows\Install-LLMIngest.bat") -Destination $InstallerRoot -Force
Assert-FrozenTkinterPayload (Join-Path $InstallerRoot "LLMIngest")

$Readme = @(
    "# LLM Ingest Windows Installer",
    "",
    "Double-click Install-LLMIngest.bat to install LLM Ingest for the current Windows user.",
    "",
    "The payload is self-contained: the installed app runs from LLMIngest.exe and does not require Python on the target computer.",
    "",
    "Default install location:",
    "",
    "%LOCALAPPDATA%\Programs\LLMIngest"
) -join "`n"
$Readme | Set-Content -Path (Join-Path $InstallerRoot "README_INSTALL.txt") -Encoding UTF8

Write-Step "Creating distributable zip"
$ZipPath = Join-Path $ReleaseRoot "LLMIngest-Windows.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path (Join-Path $InstallerRoot "*") -DestinationPath $ZipPath -Force

$SetupExe = Join-Path $ReleaseRoot "LLMIngestSetup.exe"
if (-not $SkipInno) {
    $InnoCompiler = Find-InnoCompiler
    if ($null -eq $InnoCompiler -and $InstallInno) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($null -eq $winget) {
            throw "Inno Setup was not found, and winget is not available to install it. Install Inno Setup 6 or rerun with -SkipInno."
        }
        Write-Step "Installing Inno Setup with winget"
        Invoke-Checked "winget" @("install", "--id", "JRSoftware.InnoSetup", "-e", "--source", "winget")
        $InnoCompiler = Find-InnoCompiler
    }
    if ($null -ne $InnoCompiler) {
        Write-Step "Building signed-ready Windows setup executable with Inno Setup"
        Invoke-Checked $InnoCompiler @((Join-Path $ProjectRoot "packaging\windows\LLMIngest.iss"))
    } else {
        Write-Warning "Inno Setup was not found. Zip package is ready; install Inno Setup 6 or rerun with -InstallInno to produce LLMIngestSetup.exe."
    }
}

Write-Step "Release build complete"
Write-Host "Executable: $BuiltExe" -ForegroundColor Green
Write-Host "Installer folder: $InstallerRoot" -ForegroundColor Green
Write-Host "Zip package: $ZipPath" -ForegroundColor Green
if (Test-Path $SetupExe) {
    Write-Host "Setup executable: $SetupExe" -ForegroundColor Green
}
