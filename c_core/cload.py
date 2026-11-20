"""
Platform-aware loader for the compiled C core.

The C algorithms in ``c_core/core.c`` are compiled into a shared library:

* Windows: ``c_core/core.dll``  (``gcc -shared -DCORE_BUILD_DLL ...``)
* Linux / macOS: ``c_core/libcore.so`` (``gcc -shared -fPIC ...``)

``modules/classroom.py`` and ``modules/study_planner.py`` both call
:func:`load_core`, so the library name and the search path live in one place.

If the library cannot be loaded an ``OSError`` is raised with a build hint.
The application reports that error instead of silently falling back to a
Python implementation: the C algorithms are the implementation.
"""

import ctypes
import os
import sys
from pathlib import Path

C_CORE_DIR = Path(__file__).resolve().parent

if sys.platform == "win32":
    # Keep the historical Windows name so existing local builds keep working.
    LIBRARY_NAMES = ("core.dll",)
    BUILD_HINT = (
        "gcc -std=c11 -shared -DCORE_BUILD_DLL -o c_core/core.dll c_core/core.c"
    )
elif sys.platform == "darwin":
    LIBRARY_NAMES = ("libcore.dylib", "core.dylib")
    BUILD_HINT = "gcc -std=c11 -dynamiclib -o c_core/libcore.dylib c_core/core.c"
else:
    LIBRARY_NAMES = ("libcore.so", "core.so")
    BUILD_HINT = "gcc -std=c11 -shared -fPIC -o c_core/libcore.so c_core/core.c"


def candidate_paths():
    """Return the library paths that are searched, in priority order."""
    override = os.environ.get("CORE_LIBRARY_PATH")
    paths = []
    if override:
        paths.append(Path(override))
    paths.extend(C_CORE_DIR / name for name in LIBRARY_NAMES)
    return paths


def find_library():
    """Return the first existing library path, or None."""
    for path in candidate_paths():
        if path.is_file():
            return path
    return None


def load_core():
    """Load and return the C core as a ``ctypes.CDLL``.

    Raises ``OSError`` when no shared library can be loaded.
    """
    last_error = None
    for path in candidate_paths():
        if not path.is_file():
            continue
        try:
            return ctypes.CDLL(str(path))
        except OSError as exc:  # wrong architecture, missing runtime, ...
            last_error = exc

    searched = ", ".join(str(path) for path in candidate_paths())
    message = (
        f"The C library could not be loaded (searched: {searched}). "
        f"Build it with: {BUILD_HINT}"
    )
    raise OSError(message) from last_error
