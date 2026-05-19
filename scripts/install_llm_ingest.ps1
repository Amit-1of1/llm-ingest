param(
    [switch]$All,
    [switch]$Optional,
    [switch]$Docling,
    [switch]$MinerU,
    [switch]$Unstructured,
    [switch]$InstallPython,
    [switch]$InstallTesseract,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Logged {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    $commandLine = "$FilePath $($Arguments -join ' ')"
    if ($DryRun) {
        Write-Host "[dry-run] $commandLine" -ForegroundColor Yellow
        return
    }
    Write-Host $commandLine -ForegroundColor DarkGray
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $commandLine"
    }
}

function Find-Python {
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
        $command = Get-Command $candidate.File -ErrorAction SilentlyContinue
        if ($null -eq $command) {
            continue
        }
        try {
            if ($candidate.Args.Count -gt 0) {
                & $candidate.File @($candidate.Args + @("-c", "import sys; print(sys.executable)")) 2>$null
            } else {
                & $candidate.File -c "import sys; print(sys.executable)" 2>$null
            }
            if ($LASTEXITCODE -eq 0) {
                & $candidate.File @($candidate.Args + @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)")) 2>$null
                if ($LASTEXITCODE -eq 0) {
                    return $candidate
                }
            }
        } catch {
            continue
        }
    }
    return $null
}

function Ensure-Python {
    $python = Find-Python
    if ($null -ne $python) {
        return $python
    }
    if (-not $InstallPython) {
        throw "Python 3.11+ was not found. Install Python 3.11+ or rerun with -InstallPython to try installing it with winget."
    }
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($null -eq $winget) {
        throw "Python is missing and winget is not available. Install Python 3.11+ from https://www.python.org/downloads/windows/ and rerun this installer."
    }
    Write-Step "Installing Python with winget"
    Invoke-Logged "winget" @("install", "--id", "Python.Python.3.12", "-e", "--source", "winget")
    $python = Find-Python
    if ($null -eq $python) {
        throw "Python install finished, but Python was still not found on PATH. Open a new terminal and rerun this installer."
    }
    return $python
}

function Invoke-Python {
    param(
        [object]$Python,
        [string[]]$Arguments
    )
    if ($Python -is [string]) {
        Invoke-Logged $Python $Arguments
    } else {
        Invoke-Logged $Python.File (@($Python.Args) + @($Arguments))
    }
}

Set-Location $ProjectRoot
Write-Host "LLM Ingest installer"
Write-Host "Project: $ProjectRoot"

$Python = Ensure-Python

Write-Step "Creating local virtual environment"
if (-not (Test-Path $VenvPython)) {
    Invoke-Python $Python @("-m", "venv", $VenvDir)
} else {
    Write-Host "Using existing virtual environment: $VenvDir"
}

Write-Step "Upgrading pip"
Invoke-Logged $VenvPython @("-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools")

Write-Step "Installing core dependencies"
Invoke-Logged $VenvPython @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements\base.txt"))

if ($All -or $Optional) {
    Write-Step "Installing optional Marker and embedding dependencies"
    Invoke-Logged $VenvPython @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements\optional.txt"))
}

if ($All -or $Docling) {
    Write-Step "Installing Docling dependencies"
    Invoke-Logged $VenvPython @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements\docling.txt"))
}

if ($All -or $MinerU) {
    Write-Step "Installing MinerU dependencies"
    Invoke-Logged $VenvPython @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements\mineru.txt"))
}

if ($All -or $Unstructured) {
    Write-Step "Installing Unstructured dependencies"
    Invoke-Logged $VenvPython @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements\unstructured.txt"))
}

if ($InstallTesseract) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($null -eq $winget) {
        Write-Warning "winget is not available, so Tesseract OCR was not installed."
    } else {
        Write-Step "Installing Tesseract OCR with winget"
        Invoke-Logged "winget" @("install", "--id", "UB-Mannheim.TesseractOCR", "-e", "--source", "winget")
    }
}

Write-Step "Verifying app imports"
Invoke-Logged $VenvPython @("-m", "py_compile", "llm_ingest.py", "llm_ingest_app.pyw", "llm_knowledge_graph.py", "llm_pdf_cleanup.py", "llm_figure_cleanup.py")

Write-Step "Done"
Write-Host "Run the app with:"
Write-Host "  .\launch_llm_ingest_app.bat" -ForegroundColor Green
Write-Host ""
Write-Host "Useful install variants:"
Write-Host "  .\install_llm_ingest.bat"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\install_llm_ingest.ps1 -Optional"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\install_llm_ingest.ps1 -All -InstallTesseract"
