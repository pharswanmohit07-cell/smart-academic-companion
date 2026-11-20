# Smart Academic Companion — local preview launcher
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Explicitly isolate this review build from any existing local or cloud database.
$previewDir = Join-Path $PSScriptRoot "preview_data"
New-Item -ItemType Directory -Force -Path $previewDir | Out-Null
$env:DATABASE_FILE = Join-Path $previewDir "smart-academic-companion-preview.db"
$env:DATABASE_URL = ""
$env:SUPABASE_URL = ""
$env:SUPABASE_PUBLISHABLE_KEY = ""
$env:SUPABASE_ANON_KEY = ""
$env:SUPABASE_SECRET_KEY = ""
$env:SUPABASE_SERVICE_ROLE_KEY = ""
$env:SAC_LOCAL_PREVIEW = "1"
$env:FLASK_ENV = "development"
$env:FLASK_DEBUG = "0"
$env:COOKIE_SECURE = "0"
$env:SECRET_KEY = "local-preview-only-change-me"

# NumPy/pandas wheels do not support the free-threaded 3.13t interpreter
# used by the Python install marked with "*" on this machine.
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$rebuildVenv = -not (Test-Path $venvPython)
if (-not $rebuildVenv) {
    $gilDisabled = & $venvPython -c "import sysconfig; print(int(sysconfig.get_config_var('Py_GIL_DISABLED') or 0))"
    if ($LASTEXITCODE -ne 0 -or $gilDisabled.Trim() -eq "1") {
        $rebuildVenv = $true
    }
}
if ($rebuildVenv) {
    if (Test-Path ".venv") {
        Remove-Item -Recurse -Force ".venv"
    }
    # Select the regular 64-bit Python 3.13 install, not Python 3.13t.
    py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the preview environment with standard Python 3.13. Install the regular 64-bit Python 3.13 build (not the free-threaded 3.13t build) and rerun."
    }
}
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$gilDisabled = & $python -c "import sysconfig; print(int(sysconfig.get_config_var('Py_GIL_DISABLED') or 0))"
if ($LASTEXITCODE -ne 0 -or $gilDisabled.Trim() -eq "1") {
    throw "The preview requires standard 64-bit Python 3.13, not the free-threaded 3.13t build."
}
& $python -m pip install --disable-pip-version-check --only-binary=:all: -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    $pythonVersion = & $python --version
    throw "Python dependency installation failed for $pythonVersion. No source builds were attempted. Check that a supported 64-bit Python version is installed, then rerun the launcher. The preview setup stopped before database seeding or app startup."
}

# Build the existing C features for Windows. GCC/MinGW-w64 must be on PATH.
if (-not (Get-Command gcc -ErrorAction SilentlyContinue)) {
    throw "GCC was not found. Install MinGW-w64/MSYS2 and add gcc to PATH, then rerun this script."
}
gcc -std=c11 -Wall -Wextra -Wpedantic -DCORE_BUILD_DLL -shared c_core/core.c -o c_core/core.dll
if ($LASTEXITCODE -ne 0) { throw "The C core build failed." }

# Initialize and seed ONLY the isolated preview database.
& $python database.py
if ($LASTEXITCODE -ne 0) { throw "Database initialization failed." }
& $python seed_preview_data.py
if ($LASTEXITCODE -ne 0) { throw "Preview sample-data setup failed." }
& $python demo_data.py
if ($LASTEXITCODE -ne 0) { throw "Preview academic demo-data setup failed." }

Write-Host ""
Write-Host "Local preview is ready: http://127.0.0.1:5000" -ForegroundColor Green
Write-Host "Demo login: choose Student or Faculty on the sign-in page."
Write-Host "Database: $env:DATABASE_FILE"
Write-Host "Press Ctrl+C to stop the preview."
& $python wsgi.py
