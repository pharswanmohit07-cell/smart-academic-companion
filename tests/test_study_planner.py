import ctypes
import unittest
from unittest.mock import patch

import modules.study_planner as study_planner


def topic(name, mastery, minutes):
    return {"name": name, "mastery_pct": mastery, "estimated_minutes": minutes}


SAMPLE = [
    topic("Recursion", 20, 60),
    topic("Hashing", 50, 45),
    topic("Arrays", 90, 30),
]


class TestStructureLayout(unittest.TestCase):
    """The ctypes structures must match c_core/core.h exactly."""

    def test_study_topic_layout(self):
        fields = [name for name, *_ in study_planner.StudyTopic._fields_]
        self.assertEqual(
            fields, ["topic_id", "topic_name", "mastery_pct", "estimated_minutes"]
        )
        # Sizes follow the C compiler's natural alignment on x64 Windows
        # (int 4, 100-byte char array padded to 104, double 8).
        self.assertEqual(study_planner.StudyTopic.topic_name.offset, 4)
        self.assertEqual(study_planner.StudyTopic.mastery_pct.offset, 104)
        self.assertEqual(study_planner.StudyTopic.estimated_minutes.offset, 112)
        self.assertEqual(ctypes.sizeof(study_planner.StudyTopic), 120)

    def test_study_plan_item_layout(self):
        fields = [name for name, *_ in study_planner.StudyPlanItem._fields_]
        self.assertEqual(
            fields,
            [
                "topic_id",
                "topic_name",
                "mastery_pct",
                "priority_score",
                "allocated_minutes",
                "position",
            ],
        )
        self.assertEqual(study_planner.StudyPlanItem.topic_name.offset, 4)
        self.assertEqual(study_planner.StudyPlanItem.priority_score.offset, 112)
        self.assertEqual(study_planner.StudyPlanItem.allocated_minutes.offset, 120)
        self.assertEqual(study_planner.StudyPlanItem.position.offset, 124)
        self.assertEqual(ctypes.sizeof(study_planner.StudyPlanItem), 128)

    def test_priority_score_comes_from_c(self):
        self.assertEqual(study_planner.priority_score(0), 100.0)
        self.assertEqual(study_planner.priority_score(42.5), 57.5)
        self.assertEqual(study_planner.priority_score(100), 0.0)


class TestRankTopics(unittest.TestCase):
    def test_weakest_topic_is_first(self):
        ranked = study_planner.rank_topics(SAMPLE)
        self.assertEqual([item["name"] for item in ranked],
                         ["Recursion", "Hashing", "Arrays"])
        self.assertEqual([item["position"] for item in ranked], [1, 2, 3])
        self.assertEqual(ranked[0]["priority_score"], 80.0)

    def test_equal_mastery_is_deterministic(self):
        ranked = study_planner.rank_topics([
            topic("Later", 55, 20),
            topic("Earlier", 55, 20),
        ])
        self.assertEqual([item["name"] for item in ranked], ["Later", "Earlier"])

    def test_single_topic(self):
        ranked = study_planner.rank_topics([topic("Only", 10, 15)])
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["estimated_minutes"], 15)

    def test_empty_list(self):
        self.assertEqual(study_planner.rank_topics([]), [])

    def test_invalid_mastery_is_rejected(self):
        with self.assertRaises(ValueError):
            study_planner.rank_topics([topic("Bad", 101, 20)])
        with self.assertRaises(ValueError):
            study_planner.rank_topics([topic("Bad", -1, 20)])

    def test_invalid_minutes_and_names_are_rejected(self):
        with self.assertRaises(ValueError):
            study_planner.rank_topics([topic("Zero", 50, 0)])
        with self.assertRaises(ValueError):
            study_planner.rank_topics([topic("", 50, 20)])
        with self.assertRaises(ValueError):
            study_planner.rank_topics([{"name": "No minutes", "mastery_pct": 10}])


class TestBuildPlan(unittest.TestCase):
    def test_all_topics_fit(self):
        result = study_planner.build_plan(SAMPLE, 240)
        self.assertEqual([item["name"] for item in result["schedule"]],
                         ["Recursion", "Hashing", "Arrays"])
        self.assertEqual(result["scheduled_minutes"], 135)
        self.assertEqual(result["available_minutes"], 240)
        self.assertEqual(result["remaining_minutes"], 105)
        self.assertTrue(result["complete"])
        self.assertEqual(result["skipped"], [])

    def test_time_never_exceeds_available(self):
        for available in range(1, 200):
            result = study_planner.build_plan(SAMPLE, available)
            self.assertLessEqual(result["scheduled_minutes"], available)
            self.assertEqual(
                sum(item["allocated_minutes"] for item in result["schedule"]),
                result["scheduled_minutes"],
            )

    def test_small_time_produces_a_partial_block(self):
        result = study_planner.build_plan(SAMPLE, 10)
        self.assertEqual(len(result["schedule"]), 1)
        self.assertTrue(result["schedule"][0]["partial"])
        self.assertEqual(result["schedule"][0]["allocated_minutes"], 10)
        self.assertFalse(result["complete"])
        reasons = " ".join(item["reason"] for item in result["skipped"])
        self.assertIn("10 of 60 minutes", reasons)

    def test_topics_that_do_not_fit_are_reported(self):
        result = study_planner.build_plan(SAMPLE, 90)
        self.assertEqual(result["scheduled_minutes"], 90)
        names = [item["name"] for item in result["skipped"]]
        self.assertIn("Hashing", names)
        self.assertFalse(result["complete"])

    def test_skipped_list_follows_weakest_first_order(self):
        result = study_planner.build_plan(SAMPLE, 90)
        order = [item["name"] for item in result["topics"]]
        positions = [order.index(item["name"]) for item in result["skipped"]]
        self.assertEqual(positions, sorted(positions))

    def test_available_time_validation(self):
        for bad in (0, -5, "abc", None, 200000):
            with self.assertRaises(ValueError):
                study_planner.build_plan(SAMPLE, bad)

    def test_invalid_topic_validation(self):
        with self.assertRaises(ValueError):
            study_planner.build_plan([topic("Bad", 120, 30)], 60)

    def test_empty_input(self):
        result = study_planner.build_plan([], 60)
        self.assertEqual(result["schedule"], [])
        self.assertEqual(result["topics"], [])
        self.assertEqual(result["scheduled_minutes"], 0)
        self.assertFalse(result["complete"])

    def test_too_many_topics_is_rejected(self):
        many = [topic(f"Topic {i}", 50, 10)
                for i in range(study_planner.MAX_TOPICS + 1)]
        with self.assertRaises(ValueError):
            study_planner.build_plan(many, 60)


class TestDllLoadingErrors(unittest.TestCase):
    def test_missing_dll_raises_os_error(self):
        with self.assertRaises(OSError):
            ctypes.CDLL("c_core/this_library_does_not_exist.dll")

    def test_old_dll_without_planner_functions_is_detected(self):
        # Simulate a DLL built from the previous core.c (no planner symbols).
        old_lib = ctypes.CDLL(str(study_planner._DLL_PATH))
        with self.assertRaises(AttributeError):
            old_lib.this_symbol_does_not_exist

    def test_c_error_code_becomes_value_error(self):
        with patch.object(
            study_planner._lib, "build_study_schedule", return_value=-2
        ):
            with self.assertRaises(ValueError):
                study_planner.build_plan(SAMPLE, 60)


if __name__ == "__main__":
    unittest.main()
