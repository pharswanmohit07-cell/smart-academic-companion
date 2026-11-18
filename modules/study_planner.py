"""
AI Study Planner backed by the C heap algorithms in the compiled C core
(``c_core/core.dll`` on Windows, ``c_core/libcore.so`` on Linux).

The C core provides two heap-based algorithms:

* ``rank_topics_by_weakness`` - a min-heap that orders topics from the
  weakest (lowest mastery) to the strongest.
* ``build_study_schedule`` - a greedy scheduler driven by a max-heap that
  fills the available study time with the highest priority topics.

Priority formula (implemented in C, mirrored here for display):

    priority_score = 100 - mastery_pct

A topic with 0% mastery has priority 100 and is studied first; a topic
with 100% mastery has priority 0 and is studied last.

This module is a thin wrapper: every ordering and allocation decision is
made by the C code, not by Python.
"""

import ctypes
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from c_core.cload import load_core  # noqa: E402  (path set up above)

MAX_TOPIC_LEN = 100
MAX_NAME_LEN = 100
MAX_MINUTES = 100000      # one million minutes is far beyond any real plan
MAX_TOPICS = 64           # keeps the form and the result page readable


class StudyTopic(ctypes.Structure):
    """Must match the StudyTopic struct in c_core/core.h exactly."""

    _fields_ = [
        ("topic_id", ctypes.c_int),
        ("topic_name", ctypes.c_char * MAX_TOPIC_LEN),
        ("mastery_pct", ctypes.c_double),
        ("estimated_minutes", ctypes.c_int),
    ]


class StudyPlanItem(ctypes.Structure):
    """Must match the StudyPlanItem struct in c_core/core.h exactly."""

    _fields_ = [
        ("topic_id", ctypes.c_int),
        ("topic_name", ctypes.c_char * MAX_TOPIC_LEN),
        ("mastery_pct", ctypes.c_double),
        ("priority_score", ctypes.c_double),
        ("allocated_minutes", ctypes.c_int),
        ("position", ctypes.c_int),
    ]


# Raises OSError when no platform library is available; callers catch it.
_lib = load_core()

_lib.study_priority_score.argtypes = [ctypes.POINTER(StudyTopic)]
_lib.study_priority_score.restype = ctypes.c_double

_lib.rank_topics_by_weakness.argtypes = [
    ctypes.POINTER(StudyTopic),
    ctypes.c_int,
    ctypes.POINTER(StudyPlanItem),
    ctypes.c_int,
]
_lib.rank_topics_by_weakness.restype = ctypes.c_int

_lib.build_study_schedule.argtypes = [
    ctypes.POINTER(StudyTopic),
    ctypes.c_int,
    ctypes.c_int,                 # available_minutes
    ctypes.POINTER(StudyPlanItem),
    ctypes.c_int,                 # output capacity
    ctypes.POINTER(StudyPlanItem),
    ctypes.c_int,                 # skipped capacity
    ctypes.POINTER(ctypes.c_int),  # scheduled_minutes (out parameter)
    ctypes.POINTER(ctypes.c_int),  # skipped_minutes (out parameter)
]
_lib.build_study_schedule.restype = ctypes.c_int

# Error codes agreed with c_core/core.c.
ERROR_INVALID_ARGUMENT = -1
ERROR_INVALID_TOPIC = -2
ERROR_NO_MEMORY = -3
ERROR_INVALID_TIME = -4


def _validate_topic(topic):
    """Return (name, mastery, minutes) or raise ValueError."""
    try:
        name = str(topic["name"]).strip()
        mastery = float(topic["mastery_pct"])
        minutes = int(topic["estimated_minutes"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Each topic needs a name, a mastery percentage and estimated minutes."
        ) from exc

    if not name:
        raise ValueError("Every topic needs a name.")
    if len(name.encode("utf-8")) >= MAX_TOPIC_LEN:
        raise ValueError(f"Topic names must be shorter than {MAX_TOPIC_LEN} characters.")
    if not 0 <= mastery <= 100:
        raise ValueError(
            f'Mastery for "{name}" must be between 0% and 100%.'
        )
    if not 1 <= minutes <= MAX_MINUTES:
        raise ValueError(
            f'Estimated study minutes for "{name}" must be a whole number '
            "between 1 and 100000."
        )
    return name, mastery, minutes


def _to_ctypes_topics(topics):
    """Convert a list of dicts into a ctypes StudyTopic array."""
    if not isinstance(topics, (list, tuple)):
        raise ValueError("Topics must be provided as a list.")

    if len(topics) > MAX_TOPICS:
        raise ValueError(f"Add at most {MAX_TOPICS} topics per plan.")

    array = (StudyTopic * len(topics))()
    for index, topic in enumerate(topics):
        name, mastery, minutes = _validate_topic(topic)
        array[index] = StudyTopic(
            topic_id=index + 1,
            topic_name=name.encode("utf-8"),
            mastery_pct=mastery,
            estimated_minutes=minutes,
        )
    return array


def _plan_item_to_dict(item, estimated_minutes=None):
    data = {
        "topic_id": item.topic_id,
        "name": item.topic_name.decode("utf-8", errors="replace"),
        "mastery_pct": item.mastery_pct,
        "priority_score": item.priority_score,
        "allocated_minutes": item.allocated_minutes,
        "position": item.position,
    }
    if estimated_minutes is not None:
        data["estimated_minutes"] = estimated_minutes
    return data


def priority_score(mastery_pct):
    """Return the C priority score (100 - mastery) for one mastery value."""
    topic = StudyTopic(
        topic_id=1,
        topic_name=b"topic",
        mastery_pct=float(mastery_pct),
        estimated_minutes=1,
    )
    return _lib.study_priority_score(ctypes.byref(topic))


def rank_topics(topics):
    """Order topics from weakest to strongest using the C min-heap.

    Returns a list of dicts: name, mastery_pct, priority_score,
    estimated_minutes and position (1-based).
    """
    array = _to_ctypes_topics(topics)
    count = len(array)

    if count == 0:
        return []

    output = (StudyPlanItem * count)()
    written = _lib.rank_topics_by_weakness(array, count, output, count)
    if written < 0:
        raise ValueError(f"The C ranking routine failed with error code {written}.")

    # The C struct keeps topic_id and estimated minutes, so the caller gets
    # the ranking as it exists inside the C heap, not a Python rebuild of it.
    by_id = {topic.topic_id: topic.estimated_minutes for topic in array}
    return [
        _plan_item_to_dict(item, by_id.get(item.topic_id))
        for item in output[:written]
    ]


def build_plan(topics, available_minutes):
    """Build a study plan using the C max-heap scheduler.

    Returns a dict with:
      * topics         - topics ordered weakest first (min-heap)
      * schedule       - allocated study blocks in recommended order
      * skipped        - topics that received no time, with a reason
      * available_minutes / scheduled_minutes / remaining_minutes
      * complete       - True when every topic was fully scheduled

    Raises ValueError for invalid input or invalid minutes.
    """
    try:
        available = int(available_minutes)
    except (TypeError, ValueError) as exc:
        raise ValueError("Available study time must be a whole number of minutes.") from exc

    if not 1 <= available <= MAX_MINUTES:
        raise ValueError(
            "Available study time must be between 1 and 100000 minutes."
        )

    array = _to_ctypes_topics(topics)
    count = len(array)

    # The min-heap ranking is the presentation order of the plan.
    ranked = rank_topics(topics) if count else []

    if count == 0:
        return {
            "topics": [],
            "schedule": [],
            "skipped": [],
            "available_minutes": available,
            "scheduled_minutes": 0,
            "remaining_minutes": available,
            "complete": False,
        }

    output = (StudyPlanItem * count)()
    # count topics plus at most one partial shortfall entry can be reported.
    skipped_capacity = count + 1
    skipped_output = (StudyPlanItem * skipped_capacity)()
    scheduled_minutes = ctypes.c_int(0)
    skipped_minutes = ctypes.c_int(0)

    scheduled_count = _lib.build_study_schedule(
        array,
        count,
        available,
        output,
        count,
        skipped_output,
        skipped_capacity,
        ctypes.byref(scheduled_minutes),
        ctypes.byref(skipped_minutes),
    )
    if scheduled_count < 0:
        if scheduled_count == ERROR_INVALID_TIME:
            raise ValueError("Available study time must be greater than zero.")
        raise ValueError(
            f"The C scheduling routine failed with error code {scheduled_count}."
        )

    schedule = [_plan_item_to_dict(item) for item in output[:scheduled_count]]

    # rank_topics() reads estimated minutes straight from the C struct.
    estimated = {topic["name"]: topic["estimated_minutes"] for topic in ranked}
    scheduled_names = sorted({item["name"] for item in schedule})

    # The C core lists every topic that needs more time than it received.
    skipped = [
        _plan_item_to_dict(item)
        for item in skipped_output[: skipped_minutes.value]
    ]

    # A topic can be scheduled partially: fewer minutes than it estimated.
    partial_names = set()
    for item in schedule:
        needed = estimated.get(item["name"], item["allocated_minutes"])
        if item["allocated_minutes"] < needed:
            item["partial"] = True
            item["needed_minutes"] = needed
            partial_names.add(item["name"])
        else:
            item["partial"] = False

    for item in skipped:
        needed = estimated.get(item["name"], item["allocated_minutes"])
        item["needed_minutes"] = needed
        if item["name"] in partial_names:
            granted = next(
                entry["allocated_minutes"] for entry in schedule
                if entry["name"] == item["name"]
            )
            item["reason"] = (
                f"Only {granted} of {needed} minutes fitted; "
                "the rest needs another study session."
            )
        else:
            item["reason"] = (
                f"{needed} minutes needed, but no time was left. "
                "Study it in another session."
            )

    # Weakest-first order for display, matching the ranking above.
    order = {topic["name"]: topic["position"] for topic in ranked}
    skipped.sort(key=lambda entry: order.get(entry["name"], 0))

    total_used = int(scheduled_minutes.value)
    return {
        "topics": ranked,
        "schedule": schedule,
        "skipped": skipped,
        "available_minutes": available,
        "scheduled_minutes": total_used,
        "remaining_minutes": max(0, available - total_used),
        "complete": not skipped and len(schedule) == count,
        "scheduled_names": scheduled_names,
    }


if __name__ == "__main__":
    demo = [
        {"name": "Recursion", "mastery_pct": 25, "estimated_minutes": 60},
        {"name": "Normalisation", "mastery_pct": 55, "estimated_minutes": 45},
        {"name": "Graphs", "mastery_pct": 10, "estimated_minutes": 90},
        {"name": "Arrays", "mastery_pct": 90, "estimated_minutes": 30},
    ]
    print("Weakest first:", [t["name"] for t in rank_topics(demo)])
    result = build_plan(demo, 120)
    for item in result["schedule"]:
        print(f"{item['position']}. {item['name']} - {item['allocated_minutes']} min")
    print("Scheduled:", result["scheduled_minutes"], "of", result["available_minutes"])
    print("Not scheduled:", [item["name"] for item in result["skipped"]])
