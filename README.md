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
  - Python unit tests for attendance calculations, classroom wrapper behavior, routes, database initialization, faculty workflows, and risk-model behavior.
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
├── app.py                         # Flask application and routes
├── attendance_calculator.py       # Attendance calculations
├── database.py                    # SQLite connection and initialization
├── schema.sql                     # Database schema
├── seed_data.py                   # Generates sample academic data
├── requirements.txt               # Python dependencies
├── modules/
│   ├── classroom.py               # ctypes wrapper for the C classroom core
│   ├── faculty_dashboard.py       # Faculty dashboard data and summaries
│   └── risk_model.py              # Demonstration academic risk model
├── c_core/
│   ├── core.h                     # C structs and public declarations
│   ├── core.c                     # C implementation
│   └── test_core.c                # C assertion tests
├── templates/
│   ├── base.html                  # Shared page layout
│   ├── attendance.html            # Attendance calculator page
│   ├── classrooms.html             # Classroom finder page
│   ├── faculty_manage.html        # Faculty record management page
│   └── risk.html                  # Faculty dashboard page
└── tests/
    ├── test_app_routes.py
    ├── test_attendance_calculator.py
    ├── test_classroom.py
    ├── test_classroom_free_slots.py
    ├── test_database.py
    ├── test_faculty_dashboard.py
    ├── test_faculty_routes.py
    ├── test_risk_model.py
    └── test_risk_model_database.py
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
.\\.venv\\Scripts\\Activate.ps1
```

If PowerShell blocks activation, you can run the environment's Python directly with `.venv\\Scripts\\python.exe`.

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
.\\c_core\\test_core.exe
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

The current Flask interface includes these pages and workflows:

- **Home page** at `/`.
- **Safe-attendance calculator** at `/attendance`.
- **Empty classroom finder** at `/classrooms`, backed by the C scheduling library and timetable records.
- **Faculty academic dashboard** at `/risk`, showing attendance, Midterm and End Term marks by subject, pending assessments, incomplete records, and rule-based attention flags.
- **Faculty record management** at `/faculty/manage`, including student and subject records, attendance, exam marks, assessment creation, and submission status.

The at-risk labels are demonstration rules based on academic thresholds; they are not validated evidence of real-world prediction accuracy. There is no authentication or role-based access control in the current scope, so do not expose the app publicly or use it for real student records without a security and privacy review.

The provided DLL build command targets Windows. Linux and macOS need a platform-specific shared-library build and corresponding loader path. Seed data is synthetic and should not be treated as real student information.

**Data safety:** `python database.py` initializes the schema and applies compatibility columns without intentionally clearing existing rows. `python seed_data.py` clears existing project-table rows before inserting demo data; use it only with disposable demo data or after making a verified backup.

## Contributing

1. Create a branch for your change.
2. Keep the C header, C implementation, and Python `ctypes` declarations in sync.
3. Add or update tests for behavior changes.
4. Run the Python tests and C assertion tests before submitting a pull request.

## License

No license file is currently documented in this repository. Unless a license is added, reuse and redistribution are not explicitly granted.
