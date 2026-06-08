param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:APP_DATA) {
    $env:APP_DATA = Join-Path $HOME ".willow/apps/ask-jeles"
}

if ($env:ASK_JELES_VENV) {
    $VenvDir = $env:ASK_JELES_VENV
} else {
    $VenvDir = Join-Path $env:APP_DATA ".venv"
}

function Find-Python {
    $candidates = @()
    if ($env:ASK_JELES_PYTHON) {
        $candidates += $env:ASK_JELES_PYTHON
    }
    $candidates += @("py", "python", "python3")
    foreach ($candidate in $candidates) {
        try {
            $cmd = Get-Command $candidate -ErrorAction Stop
            return $cmd.Source
        } catch {
            continue
        }
    }
    throw "Python 3.10+ not found. Install Python from python.org or the Microsoft Store."
}

function Venv-Python {
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        return Join-Path $VenvDir "Scripts/python.exe"
    }
    return Join-Path $VenvDir "bin/python3"
}

$VenvPython = Venv-Python
if (-not (Test-Path $VenvPython)) {
    $Python = Find-Python
    Write-Host "Creating venv at $VenvDir" -ForegroundColor Yellow
    & $Python -m venv $VenvDir
}

if (-not (Test-Path $VenvPython)) {
    throw "Virtualenv python was not created at $VenvPython"
}

& $VenvPython -m pip install -q --upgrade pip
& $VenvPython -m pip install -q -r requirements.txt

if (-not $env:WILLOW_ROOT) {
    $env:WILLOW_ROOT = Join-Path $HOME "github/willow-2.0"
}
if (-not $env:WILLOW_DEV_SAFE_ROOT) {
    $env:WILLOW_DEV_SAFE_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if (-not $env:ASK_JELES_USE_MCP) {
    $env:ASK_JELES_USE_MCP = "1"
}

Write-Host "AskJeles DEV: $PWD"
Write-Host "  python:     $VenvPython"
Write-Host "  willow:     $env:WILLOW_ROOT"
Write-Host "  log:        $(Join-Path $HOME '.willow/jeles.log')"
Write-Host "  keys:       Enter/o open  a synthesize  Ctrl+T quiz  m MCP  Ctrl+L learning  Ctrl+S save  Ctrl+Q quit"

& $VenvPython -m askjeles.crown @AppArgs
