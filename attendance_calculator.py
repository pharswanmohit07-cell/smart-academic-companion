
import math


def classes_needed(attended, total, target=0.75):
    """Calculate extra consecutive classes needed to reach the target.

    Time: O(1)
    Space: O(1)
    """
    if total < 0 or attended < 0 or attended > total:
        raise ValueError("Invalid attendance counts.")
    if not 0 < target <= 1:
        raise ValueError("Target must be greater than 0 and at most 1.")

    if total == 0:
        return 0

    if attended / total >= target:
        return 0

    if target == 1:
        raise ValueError(
            "A 100% attendance target is unreachable after any past absence."
        )

    return math.ceil((target * total - attended) / (1 - target))


def classes_missable(attended, total, upcoming, target=0.75):
    """Calculate the maximum upcoming classes that can be missed.

    Assumes every non-missed upcoming class is attended.
    Returns -1 if the target cannot be maintained even by attending
    every upcoming class.

    Time: O(1)
    Space: O(1)
    """
    if total < 0 or attended < 0 or attended > total:
        raise ValueError("Invalid attendance counts.")
    if upcoming < 0:
        raise ValueError("Upcoming classes cannot be negative.")
    if not 0 < target <= 1:
        raise ValueError("Target must be greater than 0 and at most 1.")

    final_total = total + upcoming
    minimum_attended = math.ceil(target * final_total)

    if attended + upcoming < minimum_attended:
        return -1

    return max(0, min(upcoming, attended + upcoming - minimum_attended))


if __name__ == "__main__":
    attended = 30
    total = 40
    upcoming = 12

    print(f"Current attendance: {attended}/{total} "
          f"({attended / total * 100:.2f}%)")
    print("Additional classes needed:", classes_needed(attended, total))
    print("Upcoming classes that can be missed:",
          classes_missable(attended, total, upcoming))
