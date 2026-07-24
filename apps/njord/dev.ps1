# dev.ps1 — Njord local launcher (stdio equities analysis + recommendation engine).
#
# RECOMMEND-ONLY. No live trading, no broker orders, no real-money path.
# The `live` subcommand always refuses; the LiveAdapter always raises.
#
# Runs standalone: no Willow checkout, no Postgres. Core is stdlib only and the
# default provider (StubProvider) is fully OFFLINE — no network, no extra deps.
#
# Usage:   ./dev.ps1 recommend AAPL MSFT NVDA
#          ./dev.ps1 live AAPL            # REFUSES (non-zero, no order)
# Override venv location:  $env:NJORD_VENV = "C:\some\venv"; ./dev.ps1 ...

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$AppData = if ($env:APP_DATA) { $env:APP_DATA } else { Join-Path $HOME ".willow/apps/njord" }
$VenvDir = if ($env:NJORD_VENV) { $env:NJORD_VENV } else { Join-Path $AppData ".venv" }

$PyExe = if ($IsWindows) { Join-Path $VenvDir "Scripts/python.exe" } else { Join-Path $VenvDir "bin/python3" }

if (-not (Test-Path $PyExe)) {
    Write-Host "Creating venv at $VenvDir"
    python3 -m venv $VenvDir
}

& $PyExe -m pip install -q --upgrade pip
# Editable install; core has no dependencies (real data is the [realdata] extra).
& $PyExe -m pip install -q -e .

$StoreRoot = if ($env:WILLOW_STORE_ROOT) { $env:WILLOW_STORE_ROOT } else { Join-Path $HOME ".willow/store" }
Write-Host "Njord DEV: $(Get-Location)"
Write-Host "  python:  $PyExe"
Write-Host "  store:   $(Join-Path $StoreRoot 'njord')"
Write-Host "  mode:    RECOMMEND-ONLY (live trading disabled)"

& $PyExe -m njord @args
