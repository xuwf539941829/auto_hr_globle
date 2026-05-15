<#
.SYNOPSIS
    Full build pipeline: Python backend → Next.js frontend → Electron installer.
.DESCRIPTION
    Produces:
      dist/backend/backend.exe          (PyInstaller)
      dist/desktop/AutoHR Setup *.exe   (NSIS installer)
      dist/desktop/AutoHR-portable-*.exe (portable single-file)
.EXAMPLE
    cd F:\BossAI\auto_hr02\auto_hr
    .\scripts\build-desktop.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

Write-Host "=== Auto HR Desktop Build ===" -ForegroundColor Cyan
Write-Host "Working directory: $Root"

# ── helpers ──────────────────────────────────────────────────────────────────

function Step($msg) { Write-Host "`n--- $msg ---" -ForegroundColor Yellow }
function Ok($msg)   { Write-Host "OK: $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "FAIL: $msg" -ForegroundColor Red; exit 1 }

function Require($cmd) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Fail "'$cmd' not found in PATH. Please install it and re-run."
    }
}

# ── prerequisites ────────────────────────────────────────────────────────────

Step "Checking prerequisites"
Require python
Require node
Require npm
Ok "All tools present"

# ── step 1: PyInstaller backend ──────────────────────────────────────────────

Step "Building Python backend with PyInstaller"

python -m pip show pyinstaller | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller…"
    python -m pip install pyinstaller
}

# Ensure backend deps are installed in the build Python
Write-Host "Installing backend Python dependencies…"
python -m pip install `
    fastapi `
    "uvicorn[standard]" `
    pydantic `
    python-multipart `
    pypdf `
    requests 2>&1 | Select-String -Pattern "(Successfully|already satisfied|ERROR)" | ForEach-Object { Write-Host $_ }

Write-Host "Running PyInstaller…"
python -m PyInstaller backend.spec --distpath dist/backend --workpath build/pyinstaller --noconfirm

if (-not (Test-Path "dist\backend\backend.exe")) {
    Fail "PyInstaller did not produce dist\backend\backend.exe"
}
Ok "dist\backend\backend.exe ready ($('{0:N1}' -f ((Get-Item 'dist\backend\backend.exe').Length / 1MB)) MB)"

# ── step 2: Next.js standalone build ─────────────────────────────────────────

Step "Building Next.js frontend (standalone)"

Set-Location "$Root\frontend"

Write-Host "Running npm ci…"
npm ci --silent

Write-Host "Running next build…"
$env:NEXT_TELEMETRY_DISABLED = "1"
# fix-readlink.js patches fs.readlink to convert EISDIR→ENOENT on virtual/
# network drives that don't implement NTFS reparse-point queries.
# cross-env propagates NODE_OPTIONS to Next.js worker processes.
npm run build

if (-not (Test-Path ".next\standalone\server.js")) {
    Fail ".next\standalone\server.js not found — check next.config.ts has output:'standalone'"
}

# Copy static assets into the standalone directory (required by Next.js docs).
Write-Host "Copying static assets into standalone…"
if (Test-Path ".next\static") {
    Copy-Item -Recurse -Force ".next\static" ".next\standalone\.next\static"
}
if (Test-Path "public") {
    Copy-Item -Recurse -Force "public" ".next\standalone\public"
}

Set-Location $Root
Ok "Next.js standalone build ready"

# ── step 3: Electron package ──────────────────────────────────────────────────

Step "Installing Electron dependencies"

Set-Location "$Root\desktop"
npm ci --silent
Ok "Electron deps installed"

Step "Packaging with electron-builder"
npm run build

Set-Location $Root

$installer = Get-ChildItem "dist\desktop" -Filter "*Setup*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
$portable  = Get-ChildItem "dist\desktop" -Filter "*portable*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1

if ($installer) { Ok "Installer: $($installer.FullName)" }
if ($portable)  { Ok "Portable:  $($portable.FullName)" }

if (-not $installer -and -not $portable) {
    Fail "electron-builder produced no output. Check dist\desktop\ for errors."
}

Write-Host "`n=== Build complete ===" -ForegroundColor Cyan
