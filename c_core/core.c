
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "core.h"

/*
 * Merge two sorted portions of the bookings array.
 *
 * The comparison uses <= so equal start times retain their
 * original relative order. This makes the merge sort stable.
 *
 * Time complexity: O(n) for this merge operation.
 * Space complexity: O(n) for the temporary buffer overall.
 */
static void merge(
    Booking bookings[],
    Booking temp[],
    int left,
    int middle,
    int right
) {
    int i = left;
    int j = middle + 1;
    int k = left;

    while (i <= middle && j <= right) {
        if (bookings[i].start_minute <= bookings[j].start_minute) {
            temp[k++] = bookings[i++];
        } else {
            temp[k++] = bookings[j++];
        }
    }

    while (i <= middle) {
        temp[k++] = bookings[i++];
    }

    while (j <= right) {
        temp[k++] = bookings[j++];
    }

    for (i = left; i <= right; i++) {
        bookings[i] = temp[i];
    }
}

/*
 * Recursively sort bookings by start_minute using merge sort.
 *
 * Time complexity: O(n log n).
 * Space complexity: O(n) for the temporary buffer, plus
 * O(log n) recursion stack space.
 */
static void merge_sort_recursive(
    Booking bookings[],
    Booking temp[],
    int left,
    int right
) {
    if (left >= right) {
        return;
    }

    int middle = left + (right - left) / 2;

    merge_sort_recursive(bookings, temp, left, middle);
    merge_sort_recursive(bookings, temp, middle + 1, right);

    merge(bookings, temp, left, middle, right);
}

/*
 * Sort bookings by start time, earliest first.
 *
 * This is a stable merge sort. Bookings with equal start times
 * keep their original relative order.
 *
 * Time complexity: O(n log n).
 * Space complexity: O(n).
 */
void sort_bookings(Booking bookings[], int count) {
    if (bookings == NULL || count <= 1) {
        return;
    }

    Booking *temp = malloc((size_t)count * sizeof(Booking));

    if (temp == NULL) {
        /* Allocation failed; leave the original array unchanged. */
        return;
    }

    merge_sort_recursive(bookings, temp, 0, count - 1);

    free(temp);
}

/*
 * Return 1 if two bookings overlap in the same room and on the
 * same day. Adjacent half-open intervals do not overlap.
 *
 * Time complexity: O(1).
 * Space complexity: O(1).
 *
 * Validation will be added in Step 2.
 */
int bookings_overlap(const Booking *a, const Booking *b) {
    if (a == NULL || b == NULL) {
        return 0;
    }

    if (strcmp(a->room, b->room) != 0 ||
        a->day_of_week != b->day_of_week) {
        return 0;
    }

    return a->start_minute < b->end_minute &&
           b->start_minute < a->end_minute;
}

/*
 * Return 1 if the requested interval is free in the specified
 * room and day; otherwise return 0.
 *
 * Time complexity: O(n).
 * Space complexity: O(1).
 *
 * Full validation will be added in Step 2.
 */
int is_room_available(
    const Booking bookings[],
    int count,
    const char *room,
    int day,
    int start,
    int end
) {
    if (count < 0 || room == NULL || start < 0 ||
        end > 1440 || start >= end) {
        return 0;
    }

    if (count > 0 && bookings == NULL) {
        return 0;
    }

    for (int i = 0; i < count; i++) {
        if (strcmp(bookings[i].room, room) == 0 &&
            bookings[i].day_of_week == day &&
            start < bookings[i].end_minute &&
            bookings[i].start_minute < end) {
            return 0;
        }
    }

    return 1;
}
