
"""
Classroom timetable utilities backed by the C interval module.

Python wrapper around c_core/core.dll (built from c_core/core.c).
Provides conflict detection and room availability checks.
"""

import ctypes
from pathlib import Path

MAX_ROOM_LEN = 16


class Booking(ctypes.Structure):
    """Mirror of the Booking struct defined in c_core/core.h."""

    _fields_ = [
        ("booking_id", ctypes.c_int),
        ("room", ctypes.c_char * MAX_ROOM_LEN),
        ("section", ctypes.c_char),
        ("day_of_week", ctypes.c_int),
        ("start_minute", ctypes.c_int),
        ("end_minute", ctypes.c_int),
    ]


_DLL_PATH = Path(__file__).resolve().parent.parent / "c_core" / "core.dll"
_lib = ctypes.CDLL(str(_DLL_PATH))

_lib.sort_bookings.argtypes = [ctypes.POINTER(Booking), ctypes.c_int]
_lib.sort_bookings.restype = None

_lib.bookings_overlap.argtypes = [ctypes.POINTER(Booking), ctypes.POINTER(Booking)]
_lib.bookings_overlap.restype = ctypes.c_int

_lib.is_room_available.argtypes = [
    ctypes.POINTER(Booking),
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.c_int,
]
_lib.is_room_available.restype = ctypes.c_int


def _to_ctypes_bookings(rows):
    """Convert an iterable of mappings/tuples to a ctypes Booking array."""
    array = (Booking * len(rows))()

    for i, row in enumerate(rows):
        if isinstance(row, (tuple, list)):
            booking_id, room, section, day, start, end = row
        else:
            booking_id = row["booking_id"]
            room = row["room"]
            section = row["section"]
            day = row["day_of_week"]
            start = row["start_minute"]
            end = row["end_minute"]

        array[i] = Booking(
            booking_id=int(booking_id),
            room=str(room).encode("utf-8")[: MAX_ROOM_LEN - 1],
            section=str(section or "A").encode("utf-8")[:1],
            day_of_week=int(day),
            start_minute=int(start),
            end_minute=int(end),
        )

    return array


def sort_bookings(bookings):
    """Sort bookings by (day, room, start time).

    Accepts a list of mappings with keys booking_id, room, section,
    day_of_week, start_minute, end_minute — or 6-tuples in that order.
    Returns the list sorted.
    """
    array = _to_ctypes_bookings(bookings)
    _lib.sort_bookings(array, len(array))

    result = [
        {
            "booking_id": b.booking_id,
            "room": b.room.decode("utf-8"),
            "section": b.section.decode("utf-8"),
            "day_of_week": b.day_of_week,
            "start_minute": b.start_minute,
            "end_minute": b.end_minute,
        }
        for b in array
    ]
    bookings[:] = result
    return bookings


def bookings_overlap(a, b):
    """Return True if bookings a and b overlap in the same room/day.

    Each of a and b is a mapping or 6-tuple as accepted by sort_bookings.
    Adjacent bookings (a.end == b.start) are NOT considered overlapping.
    """
    array = _to_ctypes_bookings([a, b])
    return bool(_lib.bookings_overlap(
        ctypes.byref(array[0]), ctypes.byref(array[1])
    ))


def is_room_available(bookings, room, day, start, end):
    """Return True if [start, end) is free in `room` on `day`.

    Times are minutes after midnight. Adjacent bookings do not block.
    Returns False for invalid intervals.
    """
    array = _to_ctypes_bookings(bookings)
    return bool(_lib.is_room_available(
        array,
        len(array),
        str(room).encode("utf-8"),
        int(day),
        int(start),
        int(end),
    ))


if __name__ == "__main__":
    sample = [
        {"booking_id": 1, "room": "R101", "section": "A",
         "day_of_week": 2, "start_minute": 600, "end_minute": 660},
        {"booking_id": 2, "room": "R102", "section": "B",
         "day_of_week": 1, "start_minute": 540, "end_minute": 600},
        {"booking_id": 3, "room": "R101", "section": "A",
         "day_of_week": 2, "start_minute": 540, "end_minute": 600},
    ]

    print("Sorted:", sort_bookings(sample))
    print("Overlap 1&3:", bookings_overlap(sample[0], sample[2]))
    print("Room R101 free Tue 10:00-11:00:",
          is_room_available(sample, "R101", 2, 600, 660))
