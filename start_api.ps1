#!/usr/bin/env pwsh
<#
.SYNOPSIS
    One-script launcher. Activates .venv and starts the Mock Order API.
    Keep this terminal open while using the agent.

.EXAMPLE
    .\start_api.ps1
#>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# ── Activate venv ─────────────────────────────────────────────────────────────
$venvActivate = Join-Path $root ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
    Write-Host "✅  Virtual environment activated." -ForegroundColor Green
} else {
    Write-Host "⚠️  No .venv found. Creating it now..." -ForegroundColor Yellow
    python -m venv "$root\.venv"
    & $venvActivate
    pip install -r "$root\requirements.txt"
}

# ── Start API ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "🚀  Starting Mock Order API on http://localhost:8080 ..." -ForegroundColor Cyan
Write-Host "    Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

uvicorn order_api:app --app-dir support_resolution_pack --reload --port 8080
