# Smart Academic Companion — local preview launcher
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Explicitly isolate this review build from any existing local or cloud database.
$previewDir = Join-Path $PSScriptRoot "preview_data"
New-Item -ItemType Directory -Force -Path $previewDir | Out-Null
$env:DATABASE_FILE = Join-Path $previewDir "smart-academic-companion-preview.db"
$env:SAC_LOCAL_PREVIEW = "1"
$env:FLASK_ENV = "development"
$env:FLASK_DEBUG = "0"
$env:COOKIE_SECURE = "0"
$env:SECRET_KEY = "local-preview-only-change-me"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3 -m venv .venv
}
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python -m pip install -r requirements.txt

# Build the existing C features for Windows. GCC/MinGW-w64 must be on PATH.
if (-not (Get-Command gcc -ErrorAction SilentlyContinue)) {
    throw "GCC was not found. Install MinGW-w64/MSYS2 and add gcc to PATH, then rerun this script."
}
gcc -std=c11 -Wall -Wextra -Wpedantic -DCORE_BUILD_DLL -shared c_core/core.c -o c_core/core.dll
if ($LASTEXITCODE -ne 0) { throw "The C core build failed." }

# Initialize and seed ONLY the isolated preview database.
& $python database.py
if ($LASTEXITCODE -ne 0) { throw "Database initialization failed." }
& $python seed_data.py
if ($LASTEXITCODE -ne 0) { throw "Preview sample-data setup failed." }
& $python demo_data.py
if ($LASTEXITCODE -ne 0) { throw "Preview academic demo-data setup failed." }

Write-Host ""
Write-Host "Local preview is ready: http://127.0.0.1:5000" -ForegroundColor Green
Write-Host "Demo login: choose Student or Faculty on the sign-in page."
Write-Host "Database: $env:DATABASE_FILE"
Write-Host "Press Ctrl+C to stop the preview."
& $python wsgi.py
