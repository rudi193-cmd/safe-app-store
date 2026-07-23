# dev.ps1 — Oakenscroll's Office local launcher (Textual TUI, local SQLite).
#
# Runs standalone: no Willow checkout, no Postgres, no network required.
# The ledger lives in ~/.willow/store/oakenscrolls-office/office.db.
#
# Usage:   ./dev.ps1
# Override venv location:  $env:OAKENSCROLL_VENV = "C:\some\venv"; ./dev.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$AppData = if ($env:APP_DATA) { $env:APP_DATA } else { Join-Path $HOME ".willow/apps/oakenscrolls-office" }
$VenvDir = if ($env:OAKENSCROLL_VENV) { $env:OAKENSCROLL_VENV } else { Join-Path $AppData ".venv" }

$PyExe = if ($IsWindows) { Join-Path $VenvDir "Scripts/python.exe" } else { Join-Path $VenvDir "bin/python3" }

if (-not (Test-Path $PyExe)) {
    Write-Host "Creating venv at $VenvDir"
    python3 -m venv $VenvDir
}

& $PyExe -m pip install -q --upgrade pip
& $PyExe -m pip install -q -r requirements.txt

Write-Host "Oakenscroll's Office DEV: $(Get-Location)"
Write-Host "  python:  $PyExe"

& $PyExe app.py @args
