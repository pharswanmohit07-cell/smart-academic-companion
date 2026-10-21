
#ifndef CORE_H
#define CORE_H

#include <stddef.h>

#define MAX_NAME_LEN 100
#define MAX_ROOM_LEN 16
#define MAX_BUILDING_LEN 64
#define MAX_TOPIC_LEN 100

/* A student record for academic calculations. */
typedef struct {
    int student_id;
    char name[MAX_NAME_LEN];
    int semester;
    char section;
    double attendance_pct;
    double average_marks;
    double assignment_ratio;
    double marks_trend;
} Student;

/*
 * A room booking represented as a half-open interval [start, end).
 * A room is uniquely identified by both building and room name.
 */
typedef struct {
    int booking_id;
    char building[MAX_BUILDING_LEN];
    char room[MAX_ROOM_LEN];
    char section;
    int day_of_week;       /* 1 = Monday, ..., 5 = Friday */
    int start_minute;      /* Minutes after midnight: 0 to 1440 */
    int end_minute;
} Booking;

/* A free time interval represented as [start, end), in minutes. */
typedef struct {
    int start_minute;
    int end_minute;
} FreeSlot;

/* A topic that can be ranked by weakness in the study planner. */
typedef struct {
    int topic_id;
    char topic_name[MAX_TOPIC_LEN];
    double mastery_pct;    /* 0 to 100 */
    int estimated_minutes;
} StudyTopic;

/*
 * Sort bookings by start time using stable merge sort.
 * Time complexity: O(n log n); space complexity: O(n).
 */
void sort_bookings(Booking bookings[], int count);

/*
 * Returns 1 if the booking is valid, otherwise 0.
 * Time complexity: O(1); space complexity: O(1).
 */
int validate_booking(const Booking *booking);

/*
 * Returns 1 if two valid bookings overlap in the same building,
 * room and day; otherwise returns 0.
 * Time complexity: O(1); space complexity: O(1).
 */
int bookings_overlap(const Booking *a, const Booking *b);

/*
 * Returns 1 if the requested interval is available, 0 otherwise.
 * Invalid input or invalid existing bookings also return 0.
 * Time complexity: O(n); space complexity: O(1).
 */
int is_room_available(
    const Booking bookings[],
    int count,
    const char *building,
    const char *room,
    int day,
    int start,
    int end
);

/*
 * Find free intervals for a building, room and weekday within
 * [day_start, day_end). Returns the number of slots found.
 * Returns a negative value for invalid input or insufficient
 * output capacity.
 *
 * Time complexity: O(n log n).
 * Space complexity: O(n) for the working copy and merge-sort buffer.
 */
int find_free_slots(
    const Booking bookings[],
    int count,
    const char *building,
    const char *room,
    int day,
    int day_start,
    int day_end,
    FreeSlot output[],
    int output_capacity
);

/*
 * Return 1 if the requested interval is free, otherwise 0.
 * Time complexity: O(n); space complexity: O(1).
 */
int is_room_free(
    const Booking bookings[],
    int count,
    const char *building,
    const char *room,
    int day,
    int start,
    int end
);

#endif
