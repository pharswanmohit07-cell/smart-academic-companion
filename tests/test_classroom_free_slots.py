import unittest

from modules.classroom import find_free_slots, detect_clashes


def booking(booking_id, room, day, start, end):
    return {
        "booking_id": booking_id, "building": "Main", "room": room,
        "section": "A", "day_of_week": day,
        "start_minute": start, "end_minute": end,
    }


class TestFreeSlotsAndClashes(unittest.TestCase):
    def test_free_after_back_to_back_bookings(self):
        rows = [booking(1, "R101", 2, 540, 600), booking(2, "R101", 2, 600, 660)]
        self.assertEqual(
            find_free_slots(rows, "R101", 2, 540, 1080),
            [{"start_minute": 660, "end_minute": 1080}],
        )

    def test_empty_room_is_free_all_day(self):
        self.assertEqual(
            find_free_slots([], "R101", 2, 540, 1080),
            [{"start_minute": 540, "end_minute": 1080}],
        )

    def test_fully_booked_room_has_no_slots(self):
        rows = [booking(1, "R101", 2, 540, 1080)]
        self.assertEqual(find_free_slots(rows, "R101", 2, 540, 1080), [])

    def test_gap_in_the_middle(self):
        rows = [booking(1, "R101", 2, 540, 600), booking(2, "R101", 2, 720, 780)]
        self.assertEqual(
            find_free_slots(rows, "R101", 2, 540, 840),
            [
                {"start_minute": 600, "end_minute": 720},
                {"start_minute": 780, "end_minute": 840},
            ],
        )

    def test_clash_detected(self):
        rows = [booking(1, "R101", 1, 540, 600), booking(2, "R101", 1, 570, 630)]
        self.assertEqual(
            detect_clashes(rows, 1),
            [{"booking_id_a": 1, "booking_id_b": 2}],
        )

    def test_adjacent_bookings_do_not_clash(self):
        rows = [booking(1, "R101", 1, 540, 600), booking(2, "R101", 1, 600, 660)]
        self.assertEqual(detect_clashes(rows, 1), [])

    def test_invalid_day_raises(self):
        with self.assertRaises(ValueError):
            detect_clashes([booking(1, "R101", 1, 540, 600)], 9)


if __name__ == "__main__":
    unittest.main()
