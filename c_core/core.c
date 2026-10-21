
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
 * Validate a booking's building, room, weekday and time interval.
 *
 * Time complexity: O(1).
 * Space complexity: O(1).
 */
int validate_booking(const Booking *booking) {
    if (booking == NULL) {
        return 0;
    }

    if (booking->building[0] == '\0' ||
        booking->room[0] == '\0') {
        return 0;
    }

    /*
     * Ensure both fixed-size character arrays contain a
     * terminating null character before using string functions.
     */
    if (memchr(booking->building, '\0', MAX_BUILDING_LEN) == NULL ||
        memchr(booking->room, '\0', MAX_ROOM_LEN) == NULL) {
        return 0;
    }

    if (booking->day_of_week < 1 ||
        booking->day_of_week > 5) {
        return 0;
    }

    if (booking->start_minute < 0 ||
        booking->end_minute > 1440 ||
        booking->start_minute >= booking->end_minute) {
        return 0;
    }

    return 1;
}

/*
 * Return 1 when two valid bookings overlap in the same building,
 * room and day. Adjacent half-open intervals do not overlap.
 *
 * Time complexity: O(1).
 * Space complexity: O(1).
 */
int bookings_overlap(const Booking *a, const Booking *b) {
    if (!validate_booking(a) || !validate_booking(b)) {
        return 0;
    }

    if (strcmp(a->building, b->building) != 0 ||
        strcmp(a->room, b->room) != 0 ||
        a->day_of_week != b->day_of_week) {
        return 0;
    }

    return a->start_minute < b->end_minute &&
           b->start_minute < a->end_minute;
}

/*
 * Return 1 if a requested interval is free in the specified
 * building, room and day; return 0 otherwise.
 *
 * Invalid arguments or invalid existing bookings return 0.
 *
 * Time complexity: O(n).
 * Space complexity: O(1).
 */
int is_room_available(
    const Booking bookings[],
    int count,
    const char *building,
    const char *room,
    int day,
    int start,
    int end
) {
    if (count < 0 ||
        building == NULL ||
        room == NULL ||
        building[0] == '\0' ||
        room[0] == '\0' ||
        day < 1 ||
        day > 5 ||
        start < 0 ||
        end > 1440 ||
        start >= end) {
        return 0;
    }

    if (count > 0 && bookings == NULL) {
        return 0;
    }

    for (int i = 0; i < count; i++) {
        if (!validate_booking(&bookings[i])) {
            return 0;
        }

        if (strcmp(bookings[i].building, building) == 0 &&
            strcmp(bookings[i].room, room) == 0 &&
            bookings[i].day_of_week == day &&
            start < bookings[i].end_minute &&
            bookings[i].start_minute < end) {
            return 0;
        }
    }

    return 1;
}
