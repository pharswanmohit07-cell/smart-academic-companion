#!/usr/bin/env bash
# Render build command.
#
#   1. install Python dependencies
#   2. compile the C11 core into c_core/libcore.so
#   3. run the C test suite (a broken core fails the deploy)
#
# Fails loudly: a deploy without a working libcore.so would silently lose the
# classroom finder and the study planner.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Python dependencies"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "==> Building the C core"
CC="${CC:-gcc}"
if ! command -v "$CC" >/dev/null 2>&1; then
  echo "gcc is required to build c_core/libcore.so" >&2
  exit 1
fi
"$CC" -std=c11 -O2 -Wall -Wextra -shared -fPIC \
  -o c_core/libcore.so c_core/core.c

echo "==> C test suite"
"$CC" -std=c11 -O2 -Wall -Wextra \
  -o /tmp/core_tests c_core/core.c c_core/test_core.c -lm
/tmp/core_tests

echo "==> Python import check"
python -c "import wsgi; print('application imported; C core:', bool(wsgi.app.extensions['sac']['classroom']))"
