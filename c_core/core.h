
#ifndef CORE_H
#define CORE_H

#include <stddef.h>

#if defined(_WIN32) && defined(CORE_BUILD_DLL)
    #define CORE_API __declspec(dllexport)
#else
    #define CORE_API
#endif

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

/* A pair of bookings that overlap in the same room and day. */
typedef struct {
    int booking_id_a;
    int booking_id_b;
} BookingClash;

/* A topic that can be ranked by weakness in the study planner. */
typedef struct {
    int topic_id;
    char topic_name[MAX_TOPIC_LEN];
    double mastery_pct;    /* 0 to 100 */
    int estimated_minutes;
} StudyTopic;

/* One scheduled study block produced by the planner. */
typedef struct {
    int topic_id;
    char topic_name[MAX_TOPIC_LEN];
    double mastery_pct;
    double priority_score;  /* 0 to 100; higher means study first */
    int allocated_minutes;  /* Minutes scheduled for this topic */
    int position;           /* 1-based order in the study plan */
} StudyPlanItem;

/*
 * Sort bookings by start time using stable merge sort.
 * Time complexity: O(n log n); space complexity: O(n).
 */
CORE_API void sort_bookings(Booking bookings[], int count);

/*
 * Detect every pair of overlapping bookings on a given weekday.
 * Returns the number of clashes, -1 for invalid input,
 * -2 if the output buffer is too small,
 * or -3 if memory allocation failed.
 *
 * Time complexity: O(n log n + k), where k is the number
 * of candidate pairs checked by the sweep line.
 * Space complexity: O(n) for events and sorting buffers.
 */
CORE_API int detect_booking_clashes(
    const Booking bookings[],
    int count,
    int day,
    BookingClash output[],
    int output_capacity
);

/*
 * Returns 1 if the booking is valid, otherwise 0.
 * Time complexity: O(1); space complexity: O(1).
 */
CORE_API int validate_booking(const Booking *booking);

/*
 * Returns 1 if two valid bookings overlap in the same building,
 * room and day; otherwise returns 0.
 * Time complexity: O(1); space complexity: O(1).
 */
CORE_API int bookings_overlap(const Booking *a, const Booking *b);

/*
 * Returns 1 if the requested interval is available, 0 otherwise.
 * Invalid input or invalid existing bookings also return 0.
 * Time complexity: O(n); space complexity: O(1).
 */
CORE_API int is_room_available(
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
CORE_API int find_free_slots(
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
CORE_API int is_room_free(
    const Booking bookings[],
    int count,
    const char *building,
    const char *room,
    int day,
    int start,
    int end
);

/*
 * Priority score for one study topic: 0 to 100.
 * A topic with 0% mastery scores 100 (study it first) and a topic with
 * 100% mastery scores 0. Returns -1 if the topic is invalid.
 *
 * Time complexity: O(1); space complexity: O(1).
 */
CORE_API double study_priority_score(const StudyTopic *topic);

/*
 * Write the topics ordered from weakest to strongest into output[]
 * using a min-heap keyed on mastery_pct (priority_score descending on
 * ties, topic_id ascending on further ties). output[] may be NULL when
 * output_capacity is 0, which only checks the input.
 *
 * Returns the number of topics written, or:
 *   -1 : invalid argument (NULL topics, negative count, capacity < count,
 *        NULL output while capacity > 0)
 *   -2 : an invalid topic (missing name, mastery outside 0-100,
 *        estimated_minutes <= 0)
 *   -3 : memory allocation failed
 *
 * Time complexity: O(n + n log n); space complexity: O(n).
 */
CORE_API int rank_topics_by_weakness(
    const StudyTopic topics[],
    int count,
    StudyPlanItem output[],
    int output_capacity
);

/*
 * Build a study plan for available_minutes using a max-heap of topics
 * keyed on priority_score. The plan is written in study order into
 * output[], which must hold at least count entries.
 *
 * The schedule never exceeds available_minutes. Leftover time that no
 * topic can use as a whole goes to the weakest unscheduled topic, which
 * is written to output[] as a partial block and also to skipped[].
 *
 * skipped[] receives every topic that needs more time than it received
 * (fully unscheduled topics plus the partially scheduled one), so
 * skipped_capacity should be count + 1. skipped_minutes is optional and
 * receives the number of skipped entries written.
 *
 * Returns the number of scheduled items, or:
 *   -1 : invalid argument
 *   -2 : an invalid topic
 *   -3 : memory allocation failed
 *   -4 : available_minutes is not positive
 *
 * Time complexity: O(n + n log n); space complexity: O(n).
 */
CORE_API int build_study_schedule(
    const StudyTopic topics[],
    int count,
    int available_minutes,
    StudyPlanItem output[],
    int output_capacity,
    StudyPlanItem skipped[],
    int skipped_capacity,
    int *scheduled_minutes,
    int *skipped_minutes
);

#endif
