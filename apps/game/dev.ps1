# dev.ps1 — SAFE Game local launcher (Streamlit UI).
#
# Runs standalone: the SAP gate and Willow lattice are optional and degrade
# gracefully when a Willow checkout is absent.
#
# Usage:   ./dev.ps1
# Override venv location:  $env:GAME_VENV = "C:\some\venv"; ./dev.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$AppData = if ($env:APP_DATA) { $env:APP_DATA } else { Join-Path $HOME ".willow/apps/game" }
$VenvDir = if ($env:GAME_VENV) { $env:GAME_VENV } else { Join-Path $AppData ".venv" }

$PyExe = if ($IsWindows) { Join-Path $VenvDir "Scripts/python.exe" } else { Join-Path $VenvDir "bin/python3" }

if (-not (Test-Path $PyExe)) {
    Write-Host "Creating venv at $VenvDir"
    python3 -m venv $VenvDir
}

& $PyExe -m pip install -q --upgrade pip
& $PyExe -m pip install -q -r requirements.txt

Write-Host "SAFE Game DEV: $(Get-Location)"
Write-Host "  python:  $PyExe"

& $PyExe -m streamlit run streamlit_app.py @args
