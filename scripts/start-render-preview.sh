#!/usr/bin/env bash
# Render-only isolated preview bootstrap. Uses SQLite under /tmp; never Supabase.
set -euo pipefail
export DATABASE_URL=""
export DATABASE_FILE="${DATABASE_FILE:-/tmp/sac-render-preview.db}"
export SAC_LOCAL_PREVIEW=1
export FLASK_ENV=development
export FLASK_DEBUG=0
export COOKIE_SECURE=1
: "${PREVIEW_BASIC_AUTH_USER:?Preview access username must be configured}"
: "${PREVIEW_BASIC_AUTH_PASSWORD:?Preview access password must be configured}"
python database.py
python seed_preview_data.py
python demo_data.py
exec gunicorn -c gunicorn.conf.py wsgi:app
