# dev.ps1 — Private Ledger local launcher (Textual TUI, local SQLite).
#
# Runs standalone: no Willow checkout, no Postgres, no network required.
# Ledger data lives in ~/.willow/private-ledger.db.
#
# Usage:   ./dev.ps1
# Override venv location:  $env:PRIVATE_LEDGER_VENV = "C:\some\venv"; ./dev.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$AppData = if ($env:APP_DATA) { $env:APP_DATA } else { Join-Path $HOME ".willow/apps/private-ledger" }
$VenvDir = if ($env:PRIVATE_LEDGER_VENV) { $env:PRIVATE_LEDGER_VENV } else { Join-Path $AppData ".venv" }

$PyExe = if ($IsWindows) { Join-Path $VenvDir "Scripts/python.exe" } else { Join-Path $VenvDir "bin/python3" }

if (-not (Test-Path $PyExe)) {
    Write-Host "Creating venv at $VenvDir"
    python3 -m venv $VenvDir
}

& $PyExe -m pip install -q --upgrade pip
& $PyExe -m pip install -q -r requirements.txt

Write-Host "Private Ledger DEV: $(Get-Location)"
Write-Host "  python:  $PyExe"

& $PyExe app.py @args
