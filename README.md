# Smart Academic Companion

A student-focused academic support web application built with **Python, Flask, SQLite, and C**. The project brings together attendance planning, classroom timetable utilities, a C-based study planner, and a faculty academic dashboard, with a small C core exposed to Python through `ctypes`.

## Overview

Students can use the attendance calculator to understand their current attendance, estimate how many consecutive classes they need to attend to reach a target, and calculate how many upcoming classes they may be able to miss while maintaining that target. The project also contains C utilities for sorting classroom bookings, checking interval overlaps and room availability, finding free time slots, and building a study plan from two heap algorithms (a min-heap that ranks weak topics and a greedy max-heap scheduler that fits topics into the available study time).

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
- **AI Study Planner (C heaps)**
  - `rank_topics_by_weakness` uses a min-heap to order topics from lowest to highest mastery.
  - `build_study_schedule` uses a greedy max-heap to allocate the available study time.
  - Priority is explained simply: `priority = 100 - mastery`, so weak topics come first.
  - Runs fully offline in C; no external AI API and no API keys.
- **Python/C bridge**
  - Uses `ctypes` to load the compiled Windows DLL and wrap the C booking and study-planner functions.
- **SQLite data layer**
  - Schema for students, subjects, attendance, marks, assignments, exams, timetable entries, faculty classes, assessments, and assessment submissions.
  - Foreign-key constraints and indexes for common lookups.
- **Faculty academic dashboard**
  - Student overview with attendance, Midterm and End Term marks, pending assessments and incomplete records.
  - Class filter, plus a demonstration logistic-regression risk score with its strongest contributing factor.
- **Custom class management**
  - Create classes, add students, move students between classes, and group legacy students into default classes.
- **Sample academic data**
  - A deterministic seed script creates sample students, subjects, attendance, marks, assignments, exams, and timetable entries.
- **Automated tests**
  - Python unit tests for attendance calculations, classroom wrapper behavior, the study-planner wrapper, routes, database initialization, faculty and class workflows, and risk-model behavior.
  - C assertion-based tests for the scheduling utilities and both study-planner heaps.

## Tech stack

| Technology | Purpose |
| --- | --- |
| Python | Application logic and tests |
| Flask | Web application and routes |
| SQLite | Local academic database |
| C (C11) | Classroom booking algorithms and study-planner heaps |
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
│   ├── study_planner.py           # ctypes wrapper for the C study-planner heaps
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
│   ├── faculty_classes.html       # Custom class management page
│   ├── study_planner.html         # AI Study Planner page
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
    ├── test_risk_model_database.py
    ├── test_risk_dashboard_integration.py
    ├── test_study_planner.py
    └── test_study_planner_routes.py
```

## Requirements

- Python 3.10 or newer
- GCC with Windows DLL support (for example, MinGW-w64/MSYS2 UCRT64 on Windows)
- Windows for the provided `c_core/core.dll` loading path

## Setup on Windows

Open PowerShell in the repository folder.

### 1. Create and activate a virtual environment

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
```

This project's commands use a virtual environment named `venv`. If you prefer `.venv`, substitute that name everywhere. If PowerShell blocks activation, run the environment's Python directly instead: `.\venv\Scripts\python.exe -m unittest discover -s tests -v`.

### 2. Install Python dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Compile the C core

Ensure GCC is available in your terminal's PATH, then run:

```powershell
gcc -std=c11 -Wall -Wextra -Wpedantic -DCORE_BUILD_DLL -shared c_core/core.c -o c_core/core.dll
```

The `-DCORE_BUILD_DLL` flag is required: it makes the C functions visible to Python. Without it the DLL builds but has no exported symbols.

The DLL must be located at `c_core/core.dll`, because that is the path used by `modules/classroom.py` and `modules/study_planner.py`. Rebuild it after changing `core.c`; an older DLL does not contain the study-planner functions and the planner page will show a build reminder.

To build and run the standalone C tests:

```powershell
gcc -std=c11 -Wall -Wextra -Wpedantic c_core/core.c c_core/test_core.c -o c_core/test_core.exe
.\c_core\test_core.exe
```

The C test program runs 11 assertion groups and prints `All C core tests passed.` on success.

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

## Study planner algorithm notes

Both algorithms live in `c_core/core.c` and are called from Python through `ctypes` in `modules/study_planner.py`.

- **Priority** is `100 - mastery_pct`, rounded to two decimals. A topic at 0% mastery has priority 100; a topic at 100% mastery has priority 0.
- **Min-heap ranking** (`rank_topics_by_weakness`): every topic is pushed into a min-heap keyed on mastery, then popped one by one. Lowest mastery comes out first, with `priority_score` and `topic_id` as tie-breakers so the order is deterministic. Build is `O(n)`, all pops together are `O(n log n)`.
- **Greedy max-heap scheduling** (`build_study_schedule`): topics are pushed into a max-heap keyed on priority, so the weakest topic is always at the root. The root is scheduled if it fits in the remaining time; otherwise the leftover minutes are given to that same weakest topic as a partial block. Topics still in the heap are reported as not scheduled. The total never exceeds the available time.
  - **The scheduler is greedy, not optimal.** It always prefers the weakest topic, so it does not search for the best possible packing of topics into the available time. This is deliberate: the plan always starts with the topic that most needs attention and the behaviour is easy to explain.
- **Errors** are returned as negative codes (`-1` invalid argument, `-2` invalid topic data, `-3` allocation failure, `-4` non-positive available time) and are turned into readable messages by the Python wrapper.
- **Validation**: mastery must be 0-100, estimated minutes must be positive, names must be non-empty and fit the fixed-size C buffer. Empty input is valid and simply produces no plan.

## Attendance calculation notes

- Attendance is represented as a fraction between `0` and `1` in the Python calculation functions. For example, `0.75` means 75%.
- A booking interval is treated as **half-open**: `[start, end)`. A booking ending at 11:00 does not overlap one starting at 11:00.
- The seed script is intended for local demonstration and testing, not production student records.

## Current scope and limitations

The current Flask interface includes these pages and workflows:

- **Home page** at `/`.
- **Safe-attendance calculator** at `/attendance`.
- **Empty classroom finder** at `/classrooms`, backed by the C scheduling library and timetable records.
- **AI Study Planner** at `/study-planner`. Enter topic names, mastery percentages and estimated study minutes plus the available study time. The page lists topics weakest first, the recommended study order, allocated minutes per topic, total available time, total scheduled time, and any topics that could not fit.
- **Faculty academic dashboard** at `/risk`, showing attendance, Midterm and End Term marks by subject, pending assessments, incomplete records, rule-based attention flags, and the demonstration risk score.
- **Faculty record management** at `/faculty/manage`, including student and subject records, attendance, exam marks, assessment creation, and submission status.
- **Class management** at `/faculty/classes`, for custom classes, student assignment and moving students between classes.

The at-risk labels are demonstration rules based on academic thresholds; they are not validated evidence of real-world prediction accuracy. The dashboard now shows an individual logistic-regression risk score next to each student, trained on those rule-based labels and broken down by strongest contributing factor. It is a teaching demonstration: it is not a validated dropout predictor and must not be used to decide anything about a student. Students without complete attendance, marks and assignment data are shown as "No prediction". If the model cannot be trained (for example, fewer than 10 students with complete data), the dashboard shows a notice and keeps working. There is no authentication or role-based access control in the current scope, so do not expose the app publicly or use it for real student records without a security and privacy review.

No deployment configuration is included. The application is a Windows-targeted Flask app that loads a locally compiled `c_core/core.dll`, keeps its data in a local SQLite file and has no authentication, so it is intended to run locally for the demonstration. Hosting it would need a Linux build of the C core, a persistent writable database and an authentication layer first.

The provided DLL build command targets Windows. Linux and macOS need a platform-specific shared-library build and corresponding loader path. Seed data is synthetic and should not be treated as real student information.

**Data safety:** `python database.py` initializes the schema and applies compatibility columns without intentionally clearing existing rows. `python seed_data.py` clears existing project-table rows before inserting demo data; use it only with disposable demo data or after making a verified backup.

## Contributing

1. Create a branch for your change.
2. Keep the C header, C implementation, and Python `ctypes` declarations in sync.
3. Add or update tests for behavior changes.
4. Run the Python tests and C assertion tests before submitting a pull request.

## License

No license file is currently documented in this repository. Unless a license is added, reuse and redistribution are not explicitly granted.
