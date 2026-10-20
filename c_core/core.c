
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "core.h"

/*
 * Sort bookings by day, then room, then start time.
 * Algorithm: Insertion sort.
 * Time complexity: O(n^2)
 * Space complexity: O(1)
 */
void sort_bookings(Booking bookings[], int count) {
    for (int i = 1; i < count; i++) {
        Booking current = bookings[i];
        int j = i - 1;

        while (j >= 0 &&
               (bookings[j].day_of_week > current.day_of_week ||
                (bookings[j].day_of_week == current.day_of_week &&
                 strcmp(bookings[j].room, current.room) > 0) ||
                (bookings[j].day_of_week == current.day_of_week &&
                 strcmp(bookings[j].room, current.room) == 0 &&
                 bookings[j].start_minute > current.start_minute))) {
            bookings[j + 1] = bookings[j];
            j--;
        }

        bookings[j + 1] = current;
    }
}

/*
 * Return 1 if two bookings overlap in the same room and on the same day.
 * Adjacent bookings, such as 09:00-10:00 and 10:00-11:00,
 * are allowed.
 * Time complexity: O(1)
 * Space complexity: O(1)
 */
int bookings_overlap(const Booking *a, const Booking *b) {
    if (strcmp(a->room, b->room) != 0 ||
        a->day_of_week != b->day_of_week) {
        return 0;
    }

    return a->start_minute < b->end_minute &&
           b->start_minute < a->end_minute;
}

/*
 * Return 1 if a requested interval is free in the specified room/day.
 * Time complexity: O(n)
 * Space complexity: O(1)
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
