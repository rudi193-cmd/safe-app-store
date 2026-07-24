# dev.ps1 — Private Ledger local launcher (Textual TUI, local SQLite).
#
# Runs standalone: no Willow checkout, no Postgres, no network required.
# Ledger data lives under $WILLOW_STORE_ROOT/private-ledger/private-ledger.db
# (default ~/.willow/store/private-ledger/private-ledger.db).
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
# Editable install of the packaged app (pulls textual/httpx from pyproject and
# exposes the `private_ledger` package + `private-ledger` console script).
& $PyExe -m pip install -q -e .

$StoreRoot = if ($env:WILLOW_STORE_ROOT) { $env:WILLOW_STORE_ROOT } else { Join-Path $HOME ".willow/store" }
Write-Host "Private Ledger DEV: $(Get-Location)"
Write-Host "  python:  $PyExe"
Write-Host "  db:      $(Join-Path $StoreRoot 'private-ledger/private-ledger.db')"

& $PyExe -m private_ledger @args
