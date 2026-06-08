param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

# dev.ps1 — Story Timeline local launcher (Windows PowerShell)
#
# Usage:
#   .\dev.ps1              # launch TUI
#   .\dev.ps1 --serve      # browser mirror (textual serve)
#
# If PowerShell blocks local scripts:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:APP_DATA) {
    $env:APP_DATA = Join-Path $HOME ".willow/apps/story-timeline"
}

if ($env:STORY_TIMELINE_VENV) {
    $VenvDir = $env:STORY_TIMELINE_VENV
} else {
    $VenvDir = Join-Path $env:APP_DATA ".venv"
}

function Find-Python {
    $candidates = @()
    if ($env:STORY_TIMELINE_PYTHON) {
        $candidates += $env:STORY_TIMELINE_PYTHON
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
if (-not $env:STORY_TIMELINE_DISABLE_MCP) {
    $env:STORY_TIMELINE_DISABLE_MCP = "0"
}

$mcpStatus = "enabled"
$unifiedScript = Join-Path $env:WILLOW_ROOT "sap/unified_mcp.sh"
if ($env:STORY_TIMELINE_DISABLE_MCP -eq "1") {
    $mcpStatus = "disabled"
} elseif (-not (Test-Path $unifiedScript)) {
    $mcpStatus = "offline (WILLOW_ROOT not found)"
}

Write-Host "Story Timeline DEV: $PWD"
Write-Host "  python:     $VenvPython"
Write-Host "  willow:     $env:WILLOW_ROOT"
Write-Host "  mcp:        $mcpStatus"
Write-Host "  db:         $(Join-Path $HOME '.willow/store/story-timeline/timeline.db')"
Write-Host "  keys:       a add  e edit  d delete  l link  p promote  j research  s suggest  i import  q quit"

if ($AppArgs -contains "--serve") {
    & $VenvPython -m textual serve app.py
} else {
    & $VenvPython app.py @AppArgs
}
