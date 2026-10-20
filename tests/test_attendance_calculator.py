
import unittest

from attendance_calculator import classes_needed, classes_missable


class TestAttendanceCalculator(unittest.TestCase):

    def test_already_at_target(self):
        self.assertEqual(classes_needed(30, 40), 0)

    def test_need_classes_to_reach_75_percent(self):
        self.assertEqual(classes_needed(20, 40), 40)

    def test_attendance_below_target(self):
        self.assertEqual(classes_needed(28, 40), 8)

    def test_no_classes_held(self):
        self.assertEqual(classes_needed(0, 0), 0)

    def test_can_miss_upcoming_classes(self):
        self.assertEqual(classes_missable(30, 40, 12), 3)

    def test_cannot_miss_any_classes(self):
        self.assertEqual(classes_missable(20, 40, 12), -1)

    def test_target_unreachable(self):
        self.assertEqual(classes_missable(10, 40, 5), -1)

    def test_invalid_attendance(self):
        with self.assertRaises(ValueError):
            classes_needed(45, 40)

    def test_invalid_target(self):
        with self.assertRaises(ValueError):
            classes_needed(20, 40, 1.5)

    def test_perfect_attendance_needs_no_classes(self):
        self.assertEqual(classes_needed(40, 40), 0)

    def test_target_of_100_percent(self):
        self.assertEqual(classes_needed(10, 10, 1.0), 0)
        self.assertEqual(classes_needed(9, 10, 1.0), -1)

    def test_negative_upcoming_classes(self):
        with self.assertRaises(ValueError):
            classes_missable(30, 40, -1)

    def test_already_above_target(self):
        self.assertEqual(classes_needed(38, 40), 0)


if __name__ == "__main__":
    unittest.main()
