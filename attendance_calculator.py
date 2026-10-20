import math


def _validate(attended, total, target):
    if total < 0 or attended < 0 or attended > total:
        raise ValueError("Invalid attendance counts.")
    if not 0 < target <= 1:
        raise ValueError("Target must be greater than 0 and at most 1.")


def classes_needed(attended, total, target=0.75):
    """Extra consecutive classes to attend to reach target. Time O(1), space O(1)."""
    _validate(attended, total, target)
    if total == 0 or attended / total >= target:
        return 0
    return math.ceil((target * total - attended) / (1 - target))


def classes_missable(attended, total, upcoming, target=0.75):
    """Maximum upcoming classes that may be missed; -1 if target is unreachable.
    Assumes all non-missed upcoming classes are attended. Time O(1), space O(1).
    """
    _validate(attended, total, target)
    if upcoming < 0:
        raise ValueError("Upcoming classes cannot be negative.")
    final_total = total + upcoming
    minimum_attended = math.ceil(target * final_total)
    if attended + upcoming < minimum_attended:
        return -1
    return max(0, min(upcoming, attended + upcoming - minimum_attended))


if __name__ == "__main__":
    attended, total, upcoming = 30, 40, 12
    print(f"Current attendance: {attended}/{total} ({attended / total * 100:.2f}%)")
    print("Additional classes needed:", classes_needed(attended, total))
    print("Upcoming classes that can be missed:",
          classes_missable(attended, total, upcoming))
