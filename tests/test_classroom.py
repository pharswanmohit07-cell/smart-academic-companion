
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.classroom import bookings_overlap, is_room_available, sort_bookings


def booking(bid, room, day, start, end, section="A"):
    return {"booking_id": bid, "room": room, "section": section,
            "day_of_week": day, "start_minute": start, "end_minute": end}


class TestClassroom(unittest.TestCase):

    def test_sort_by_day_room_start(self):
        rows = [
            booking(1, "R101", 2, 600, 660),
            booking(2, "R102", 1, 540, 600),
            booking(3, "R101", 2, 540, 600),
        ]
        sorted_rows = sort_bookings(rows)
        self.assertEqual([r["booking_id"] for r in sorted_rows], [2, 3, 1])

    def test_overlap_same_room(self):
        a = booking(1, "R101", 2, 540, 600)
        b = booking(2, "R101", 2, 570, 630)
        self.assertTrue(bookings_overlap(a, b))

    def test_no_overlap_adjacent(self):
        a = booking(1, "R101", 2, 540, 600)
        b = booking(2, "R101", 2, 600, 660)
        self.assertFalse(bookings_overlap(a, b))

    def test_no_overlap_different_room_or_day(self):
        a = booking(1, "R101", 2, 540, 600)
        b = booking(2, "R102", 2, 540, 600)
        c = booking(3, "R101", 3, 540, 600)
        self.assertFalse(bookings_overlap(a, b))
        self.assertFalse(bookings_overlap(a, c))

    def test_room_available_when_free(self):
        rows = [booking(1, "R101", 2, 540, 600)]
        self.assertTrue(is_room_available(rows, "R101", 2, 600, 660))

    def test_room_unavailable_when_booked(self):
        rows = [booking(1, "R101", 2, 540, 600)]
        self.assertFalse(is_room_available(rows, "R101", 2, 590, 660))

    def test_invalid_interval(self):
        rows = []
        self.assertFalse(is_room_available(rows, "R101", 2, 660, 600))
        self.assertFalse(is_room_available(rows, "R101", 2, 600, 1500))


if __name__ == "__main__":
    unittest.main()
