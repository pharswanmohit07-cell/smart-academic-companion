# Smart Academic Companion

A student-focused academic support web application built with **Python, Flask, SQLite, and C**. The project brings together attendance planning and classroom timetable utilities, with a small C core exposed to Python through `ctypes`.

## Overview

Students can use the attendance calculator to understand their current attendance, estimate how many consecutive classes they need to attend to reach a target, and calculate how many upcoming classes they may be able to miss while maintaining that target. The project also contains C utilities for sorting classroom bookings, checking interval overlaps and room availability, and finding free time slots.

The repository is a learning project that combines web development, database design, Python testing, C programming, and Python/C interoperability.

## Features

- **Attendance calculator**
  - Calculates current attendance percentage.
  - Estimates additional classes needed to reach a target percentage.
  - Estimates the maximum upcoming classes that can be missed while maintaining a target.
  - Validates attendance counts and target percentages, including the unreachable 100% target edge case after an absence.
- **Classroom scheduling core (C)**
  - Stable merge sort for booking records.
  - Overlap detection using half-open time intervals, so adjacent bookings do not clash.
  - Room availability checks by building, room, and weekday.
  - Free-slot discovery within a requested time window.
- **Python/C bridge**
  - Uses `ctypes` to load the compiled Windows DLL and wrap C booking functions.
- **SQLite data layer**
  - Schema for students, subjects, attendance, marks, assignments, exams, and timetable entries.
  - Foreign-key constraints and indexes for common lookups.
- **Sample academic data**
  - A deterministic seed script creates sample students, subjects, attendance, marks, assignments, exams, and timetable entries.
- **Automated tests**
  - Python unit tests for attendance calculations and classroom wrapper behavior.
  - C assertion-based tests for the core scheduling utilities.

## Tech stack

| Technology | Purpose |
| --- | --- |
| Python | Application logic and tests |
| Flask | Web application and routes |
| SQLite | Local academic database |
| C (C11) | Classroom booking algorithms |
| `ctypes` | Calls the compiled C library from Python |
| pandas, NumPy, scikit-learn | Available data/ML dependencies for project development |
| GCC | Compiles the C core and Windows DLL |

## Project structure

```text
smart-academic-companion/
├── app.py                         # Flask application
├── attendance_calculator.py       # Attendance calculations
├── database.py                    # SQLite connection and initialization
├── schema.sql                     # Database schema
├── seed_data.py                   # Generates sample academic data
├── requirements.txt               # Python dependencies
├── modules/
│   └── classroom.py               # ctypes wrapper for the C classroom core
├── c_core/
│   ├── core.h                     # C structs and public declarations
│   ├── core.c                     # C implementation
│   └── test_core.c                # C assertion tests
└── tests/
    ├── test_attendance_calculator.py
    └── test_classroom.py
```

## Requirements

- Python 3.10 or newer
- GCC with Windows DLL support (for example, MinGW-w64/MSYS2 UCRT64 on Windows)
- Windows for the provided `c_core/core.dll` loading path

## Setup on Windows

Open PowerShell in the repository folder.

### 1. Create and activate a virtual environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can run the environment's Python directly with `.venv\Scripts\python.exe`.

### 2. Install Python dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Compile the C core

Ensure GCC is available in your terminal's PATH, then run:

```powershell
gcc -std=c11 -Wall -Wextra -Wpedantic -DCORE_BUILD -shared c_core/core.c -o c_core/core.dll
```

The DLL must be located at `c_core/core.dll`, because that is the path used by `modules/classroom.py`.

To build and run the standalone C tests:

```powershell
gcc -std=c11 -Wall -Wextra -Wpedantic c_core/core.c c_core/test_core.c -o c_core/test_core.exe
.\c_core\test_core.exe
```

### 4. Initialize the database

```powershell
python database.py
```

This creates `academic_companion.db` using `schema.sql`.

### 5. (Optional) Generate sample data

```powershell
python seed_data.py
```

**Warning:** the seed script clears existing rows in the project tables before inserting its sample dataset. Back up any data you want to keep before running it.

### 6. Start the Flask application

```powershell
python app.py
```

Open the local URL printed by Flask in your browser (usually [http://127.0.0.1:5000](http://127.0.0.1:5000)).

## Running the tests

Run the Python test suite from the repository root:

```powershell
python -m unittest discover -s tests -v
```

Run only the attendance calculator tests:

```powershell
python -m unittest discover -s tests -p "test_attendance_calculator.py" -v
```

Run only the classroom wrapper tests:

```powershell
python -m unittest discover -s tests -p "test_classroom.py" -v
```

The classroom tests require the C DLL to be compiled first.

## Attendance calculation notes

- Attendance is represented as a fraction between `0` and `1` in the Python calculation functions. For example, `0.75` means 75%.
- A booking interval is treated as **half-open**: `[start, end)`. A booking ending at 11:00 does not overlap one starting at 11:00.
- The seed script is intended for local demonstration and testing, not production student records.

## Current scope and limitations

- The Flask interface currently exposes the home page and attendance calculator. Classroom functionality is provided by the C core and its Python wrapper; a dedicated classroom web page may be added separately.
- The provided DLL build command targets Windows. Linux and macOS need a platform-specific shared-library build and corresponding loader path.
- Seed data is synthetic and should not be treated as real student information.
- This project is intended for learning and demonstration; review security, deployment configuration, and data-protection requirements before using it with real academic records.

## Contributing

1. Create a branch for your change.
2. Keep the C header, C implementation, and Python `ctypes` declarations in sync.
3. Add or update tests for behavior changes.
4. Run the Python tests and C assertion tests before submitting a pull request.

## License

No license file is currently documented in this repository. Unless a license is added, reuse and redistribution are not explicitly granted.
