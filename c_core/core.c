
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

/* Return 1 for valid input; otherwise return 0. O(1) time/space. */
int validate_booking(const Booking *booking) {
    if (booking == NULL) {
        return 0;
    }

    if (memchr(booking->building, '\0', MAX_BUILDING_LEN) == NULL ||
        memchr(booking->room, '\0', MAX_ROOM_LEN) == NULL) {
        return 0;
    }

    if (booking->building[0] == '\0' || booking->room[0] == '\0') {
        return 0;
    }

    if (booking->day_of_week < 1 || booking->day_of_week > 5) {
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

/*
 * Find free intervals for one building, room and day.
 *
 * Return:
 *   >= 0 : number of slots written
 *   -1   : invalid input
 *   -2   : insufficient output capacity
 *   -3   : memory allocation failed
 *
 * Time: O(n log n); extra space: O(n).
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
) {
    if (count < 0 || building == NULL || room == NULL ||
        building[0] == '\0' || room[0] == '\0' ||
        day < 1 || day > 5 ||
        day_start < 0 || day_end > 1440 ||
        day_start >= day_end || output_capacity < 0) {
        return -1;
    }

    if (count > 0 && bookings == NULL) {
        return -1;
    }

    if (output_capacity > 0 && output == NULL) {
        return -1;
    }

    /*
     * Validate every input booking before allocating or writing output.
     * This avoids silently accepting malformed booking records.
     */
    for (int i = 0; i < count; i++) {
        if (!validate_booking(&bookings[i])) {
            return -1;
        }
    }

    if (count == 0) {
        if (output_capacity < 1) {
            return -2;
        }

        output[0].start_minute = day_start;
        output[0].end_minute = day_end;
        return 1;
    }

    Booking *selected = malloc((size_t)count * sizeof(Booking));
    Booking *temp = malloc((size_t)count * sizeof(Booking));

    if (selected == NULL || temp == NULL) {
        free(selected);
        free(temp);
        return -3;
    }

    int selected_count = 0;

    for (int i = 0; i < count; i++) {
        if (strcmp(bookings[i].building, building) == 0 &&
            strcmp(bookings[i].room, room) == 0 &&
            bookings[i].day_of_week == day &&
            bookings[i].start_minute < day_end &&
            bookings[i].end_minute > day_start) {
            selected[selected_count++] = bookings[i];
        }
    }

    if (selected_count > 1) {
        merge_sort_recursive(
            selected, temp, 0, selected_count - 1
        );
    }

    int slot_count = 0;
    int cursor = day_start;

    for (int i = 0; i < selected_count; i++) {
        int start = selected[i].start_minute;
        int end = selected[i].end_minute;

        /* Clip bookings to the requested day window. */
        if (start < day_start) {
            start = day_start;
        }
        if (end > day_end) {
            end = day_end;
        }

        if (start > cursor) {
            if (slot_count >= output_capacity) {
                free(selected);
                free(temp);
                return -2;
            }

            output[slot_count].start_minute = cursor;
            output[slot_count].end_minute = start;
            slot_count++;
        }

        /* Merge overlapping bookings by advancing the cursor. */
        if (end > cursor) {
            cursor = end;
        }

        if (cursor >= day_end) {
            break;
        }
    }

    if (cursor < day_end) {
        if (slot_count >= output_capacity) {
            free(selected);
            free(temp);
            return -2;
        }

        output[slot_count].start_minute = cursor;
        output[slot_count].end_minute = day_end;
        slot_count++;
    }

    free(selected);
    free(temp);
    return slot_count;
}

/* Return 1 if the requested interval is free, else 0.
 * O(n) time and O(1) extra space.
 */
int is_room_free(
    const Booking bookings[],
    int count,
    const char *building,
    const char *room,
    int day,
    int start,
    int end
) {
    return is_room_available(
        bookings, count, building, room, day, start, end
    );
}

/* Start/end event used by the sweep-line clash detector. */
typedef struct {
    int minute;
    int is_start;  /* End events are processed before starts at equal times. */
    int booking_index;
} BookingEvent;

/*
 * Stable merge sort for sweep-line events.
 * Sort by time, with end events before start events at equal times.
 * Time: O(n log n); auxiliary space: O(n).
 */
static void merge_events(
    BookingEvent events[],
    BookingEvent temp[],
    int left,
    int middle,
    int right
) {
    int i = left;
    int j = middle + 1;
    int k = left;

    while (i <= middle && j <= right) {
        int take_left =
            events[i].minute < events[j].minute ||
            (events[i].minute == events[j].minute &&
             events[i].is_start <= events[j].is_start);

        if (take_left) {
            temp[k++] = events[i++];
        } else {
            temp[k++] = events[j++];
        }
    }

    while (i <= middle) temp[k++] = events[i++];
    while (j <= right) temp[k++] = events[j++];

    for (i = left; i <= right; i++) {
        events[i] = temp[i];
    }
}

static void merge_sort_events_recursive(
    BookingEvent events[],
    BookingEvent temp[],
    int left,
    int right
) {
    if (left >= right) return;

    int middle = left + (right - left) / 2;

    merge_sort_events_recursive(events, temp, left, middle);
    merge_sort_events_recursive(events, temp, middle + 1, right);
    merge_events(events, temp, left, middle, right);
}

/*
 * Detect every overlapping pair for the requested day.
 * Only bookings in the same building and room can clash.
 *
 * Time: O(n log n + k), where k is the number of same-day
 * candidate pairs considered by the sweep line.
 * Worst-case time: O(n^2) when many bookings overlap.
 * Space: O(n) for events and the active booking list.
 */
int detect_booking_clashes(
    const Booking bookings[],
    int count,
    int day,
    BookingClash output[],
    int output_capacity
) {
    if (count < 0 || day < 1 || day > 5 ||
        output_capacity < 0 ||
        (count > 0 && bookings == NULL) ||
        (output_capacity > 0 && output == NULL)) {
        return -1;
    }

    for (int i = 0; i < count; i++) {
        if (!validate_booking(&bookings[i])) return -1;
    }

    if (count == 0) return 0;

    BookingEvent *events =
        malloc((size_t)count * 2 * sizeof(BookingEvent));
    BookingEvent *temp =
        malloc((size_t)count * 2 * sizeof(BookingEvent));
    int *active = malloc((size_t)count * sizeof(int));

    if (events == NULL || temp == NULL || active == NULL) {
        free(events);
        free(temp);
        free(active);
        return -3;
    }

    int event_count = 0;

    for (int i = 0; i < count; i++) {
        if (bookings[i].day_of_week != day) continue;

        events[event_count++] = (BookingEvent){
            bookings[i].start_minute, 1, i
        };
        events[event_count++] = (BookingEvent){
            bookings[i].end_minute, 0, i
        };
    }

    if (event_count > 1) {
        merge_sort_events_recursive(
            events, temp, 0, event_count - 1
        );
    }

    int active_count = 0;
    int clash_count = 0;

    for (int e = 0; e < event_count; e++) {
        BookingEvent event = events[e];
        int current = event.booking_index;

        if (!event.is_start) {
            for (int a = 0; a < active_count; a++) {
                if (active[a] == current) {
                    active[a] = active[--active_count];
                    break;
                }
            }
            continue;
        }

        for (int a = 0; a < active_count; a++) {
            int other = active[a];

            if (strcmp(bookings[current].building,
                       bookings[other].building) != 0 ||
                strcmp(bookings[current].room,
                       bookings[other].room) != 0) {
                continue;
            }

            if (clash_count >= output_capacity || output == NULL) {
                free(events);
                free(temp);
                free(active);
                return -2;
            }

            output[clash_count].booking_id_a =
                bookings[other].booking_id;
            output[clash_count].booking_id_b =
                bookings[current].booking_id;
            clash_count++;
        }

        active[active_count++] = current;
    }

    free(events);
    free(temp);
    free(active);
    return clash_count;
}

/*
 * Study planner
 * =============
 *
 * Min-heap: orders topics from weakest to strongest so the student can
 * see which topic needs the most attention first. The heap key is
 * mastery_pct (lower first), then priority_score (higher first), then
 * topic_id (lower first) so the result is deterministic.
 *
 * Max-heap: greedy scheduling. At every step the highest priority topic
 * that still fits in the remaining time is selected and its estimated
 * study time is allocated. This is the classic "highest value per unit,
 * take the best that fits" greedy strategy. Its complexity is
 * O(n log n + k log n), where k is the number of rejected candidates.
 *
 * priority_score = 100 - mastery_pct   (rounded to 2 decimals)
 *   0% mastery  -> 100 priority
 *   50% mastery ->  50 priority
 *   100% mastery ->  0 priority
 */

/* ------------------------------------------------------------------ */
/* Heap helpers                                                        */
/* ------------------------------------------------------------------ */

/*
 * -1 when a should be served before b, 1 when b comes first, 0 if equal.
 * O(1) time and space.
 */
static int topic_priority_compare(const StudyTopic *a, const StudyTopic *b) {
    if (a->mastery_pct < b->mastery_pct) return -1;
    if (a->mastery_pct > b->mastery_pct) return 1;

    double score_a = 100.0 - a->mastery_pct;
    double score_b = 100.0 - b->mastery_pct;
    if (score_a > score_b) return -1;
    if (score_a < score_b) return 1;

    if (a->topic_id < b->topic_id) return -1;
    if (a->topic_id > b->topic_id) return 1;
    return 0;
}

/* O(1) time and space. */
static void swap_topics(StudyTopic *a, StudyTopic *b) {
    StudyTopic temp = *a;
    *a = *b;
    *b = temp;
}

/* Restore the min-heap property from index i downwards. O(log n). */
static void min_heap_sift_down(StudyTopic heap[], int size, int index) {
    while (1) {
        int left = 2 * index + 1;
        int right = left + 1;
        int smallest = index;

        if (left < size &&
            topic_priority_compare(&heap[left], &heap[smallest]) < 0) {
            smallest = left;
        }
        if (right < size &&
            topic_priority_compare(&heap[right], &heap[smallest]) < 0) {
            smallest = right;
        }
        if (smallest == index) {
            return;
        }

        swap_topics(&heap[index], &heap[smallest]);
        index = smallest;
    }
}

/* Heapify an arbitrary array into a min-heap. O(n). */
static void min_heap_build(StudyTopic heap[], int size) {
    for (int i = size / 2 - 1; i >= 0; i--) {
        min_heap_sift_down(heap, size, i);
    }
}

/* Remove and return the weakest topic. O(log n). */
static StudyTopic min_heap_pop(StudyTopic heap[], int *size) {
    StudyTopic top = heap[0];
    (*size)--;
    if (*size > 0) {
        heap[0] = heap[*size];
        min_heap_sift_down(heap, *size, 0);
    }
    return top;
}

/* ------------------------------------------------------------------ */
/* Public study planner API                                            */
/* ------------------------------------------------------------------ */

/* Return 1 for a valid topic, 0 otherwise. O(MAX_TOPIC_LEN) time. */
static int validate_study_topic(const StudyTopic *topic) {
    if (topic == NULL) return 0;

    if (memchr(topic->topic_name, '\0', MAX_TOPIC_LEN) == NULL) return 0;
    if (topic->topic_name[0] == '\0') return 0;

    if (!(topic->mastery_pct >= 0.0 && topic->mastery_pct <= 100.0)) {
        return 0;  /* also rejects NaN */
    }

    if (topic->estimated_minutes <= 0) return 0;

    return 1;
}



/* Copy topic data into a plan item. Returns priority score rounded to 2dp. */
static double fill_plan_item(
    StudyPlanItem *item,
    const StudyTopic *topic,
    int allocated_minutes
) {
    double score = 100.0 - topic->mastery_pct;
    double rounded = (double)((long)(score * 100.0 + 0.5)) / 100.0;

    item->topic_id = topic->topic_id;
    memcpy(item->topic_name, topic->topic_name, MAX_TOPIC_LEN);
    item->topic_name[MAX_TOPIC_LEN - 1] = '\0';
    item->mastery_pct = topic->mastery_pct;
    item->priority_score = rounded;
    item->allocated_minutes = allocated_minutes;
    item->position = 0;
    return rounded;
}

double study_priority_score(const StudyTopic *topic) {
    if (!validate_study_topic(topic)) return -1.0;

    double score = 100.0 - topic->mastery_pct;
    return (double)((long)(score * 100.0 + 0.5)) / 100.0;
}

/*
 * Min-heap ordering: lowest mastery first, which is the weakest topic.
 * Time: O(n + n log n); space: O(n).
 */
int rank_topics_by_weakness(
    const StudyTopic topics[],
    int count,
    StudyPlanItem output[],
    int output_capacity
) {
    if (count < 0 || output_capacity < 0) return -1;
    if (count > 0 && topics == NULL) return -1;
    if (output_capacity > 0 && output == NULL) return -1;
    if (count > 0 && output_capacity < count) return -1;
    /* Empty input is not an error: there is simply nothing to rank. */
    if (count == 0) return 0;

    for (int i = 0; i < count; i++) {
        if (!validate_study_topic(&topics[i])) return -2;
    }

    StudyTopic *heap = malloc((size_t)count * sizeof(StudyTopic));
    if (heap == NULL) return -3;

    for (int i = 0; i < count; i++) {
        heap[i] = topics[i];
    }

    min_heap_build(heap, count);

    int size = count;
    for (int i = 0; i < count; i++) {
        StudyTopic weakest = min_heap_pop(heap, &size);
        fill_plan_item(&output[i], &weakest, weakest.estimated_minutes);
        output[i].position = i + 1;
    }

    free(heap);
    return count;
}

/*
 * Max-heap by priority score (equivalently, min mastery).
 * sift_up keeps the strongest candidate at the root.
 */
static void max_heap_sift_up(StudyTopic heap[], int index) {
    while (index > 0) {
        int parent = (index - 1) / 2;
        if (topic_priority_compare(&heap[index], &heap[parent]) >= 0) {
            return;
        }
        swap_topics(&heap[index], &heap[parent]);
        index = parent;
    }
}

static void max_heap_sift_down(StudyTopic heap[], int size, int index) {
    while (1) {
        int left = 2 * index + 1;
        int right = left + 1;
        int best = index;

        if (left < size &&
            topic_priority_compare(&heap[left], &heap[best]) < 0) {
            best = left;
        }
        if (right < size &&
            topic_priority_compare(&heap[right], &heap[best]) < 0) {
            best = right;
        }
        if (best == index) return;

        swap_topics(&heap[index], &heap[best]);
        index = best;
    }
}

static StudyTopic max_heap_pop(StudyTopic heap[], int *size) {
    StudyTopic top = heap[0];
    (*size)--;
    if (*size > 0) {
        heap[0] = heap[*size];
        max_heap_sift_down(heap, *size, 0);
    }
    return top;
}

/*
 * Greedy scheduling with a max-heap.
 *
 * Algorithm:
 *   1. Push every valid topic into a max-heap ordered by priority, so the
 *      weakest topic is always at the root.
 *   2. If the root fits in the remaining time, pop it and allocate its
 *      full estimated time.
 *   3. If it does not fit, stop: a weaker topic may still fit, but the
 *      stronger one has to wait for another session.
 *   4. If the weakest topic itself does not fit, give the leftover minutes
 *      to it as a partial block. It is then reported in output[] (partial
 *      allocation) and in skipped[] (full size), so a caller can show
 *      "only 45 of 60 minutes fitted".
 *   5. Every topic still in the heap is written to skipped[] with its
 *      full estimated time so nothing is silently lost.
 *
 * The sum of allocated minutes never exceeds available_minutes.
 *
 * Time: O(n log n); space: O(n) plus the caller's output buffers.
 */
int build_study_schedule(
    const StudyTopic topics[],
    int count,
    int available_minutes,
    StudyPlanItem output[],
    int output_capacity,
    StudyPlanItem skipped[],
    int skipped_capacity,
    int *scheduled_minutes,
    int *skipped_minutes
) {
    if (count < 0 || output_capacity < 0 || skipped_capacity < 0) return -1;
    if (count > 0 && topics == NULL) return -1;
    if (output_capacity > 0 && output == NULL) return -1;
    if (skipped_capacity > 0 && skipped == NULL) return -1;
    if (count > output_capacity) return -1;
    if (available_minutes <= 0) return -4;
    if (scheduled_minutes != NULL) *scheduled_minutes = 0;
    if (skipped_minutes != NULL) *skipped_minutes = 0;
    if (count == 0) return 0;

    for (int i = 0; i < count; i++) {
        if (!validate_study_topic(&topics[i])) return -2;
    }

    /* The heap holds topic copies; short topics are formatted here. */
    StudyTopic *heap = malloc((size_t)count * sizeof(StudyTopic));
    StudyPlanItem *skipped_copy =
        malloc((size_t)count * sizeof(StudyPlanItem));
    if (heap == NULL || skipped_copy == NULL) {
        free(heap);
        free(skipped_copy);
        return -3;
    }

    int heap_size = 0;
    for (int i = 0; i < count; i++) {
        heap[heap_size] = topics[i];
        max_heap_sift_up(heap, heap_size);
        heap_size++;
    }

    int scheduled_count = 0;
    int skipped_count = 0;
    int used = 0;
    int remaining = available_minutes;

    /* The strongest topic that does not fit as a whole, if any. */
    StudyTopic partial_topic = {0};
    int have_partial = 0;

    /*
     * The max-heap holds every unscheduled topic. In a max-heap the root
     * is always the strongest remaining topic (priority = 100 - mastery,
     * so the lowest mastery). The loop stops once no topic fits.
     */
    while (heap_size > 0) {
        if (heap[0].estimated_minutes > remaining) {
            partial_topic = heap[0];
            have_partial = 1;
            break;
        }

        StudyTopic next = max_heap_pop(heap, &heap_size);
        fill_plan_item(
            &output[scheduled_count], &next, next.estimated_minutes
        );
        output[scheduled_count].position = scheduled_count + 1;
        used += next.estimated_minutes;
        remaining -= next.estimated_minutes;
        scheduled_count++;
    }

    /* Everything left in the heap received no time (or only a part). */
    while (heap_size > 0) {
        StudyTopic leftover = max_heap_pop(heap, &heap_size);
        if (skipped_count < skipped_capacity) {
            fill_plan_item(
                &skipped_copy[skipped_count++], &leftover,
                leftover.estimated_minutes
            );
        }
    }

    /* Give whatever is left to the weakest partially fitting topic. */
    if (have_partial && remaining > 0 && scheduled_count < output_capacity) {
        fill_plan_item(&output[scheduled_count], &partial_topic, remaining);
        output[scheduled_count].position = scheduled_count + 1;
        used += remaining;
        remaining = 0;
        scheduled_count++;
    }

    /* Only now copy out, because skipped_copy is still being written. */
    for (int i = 0; i < skipped_count; i++) {
        skipped[i] = skipped_copy[i];
        skipped[i].position = 0;
    }

    if (scheduled_minutes != NULL) *scheduled_minutes = used;
    if (skipped_minutes != NULL) *skipped_minutes = skipped_count;

    free(heap);
    free(skipped_copy);
    return scheduled_count;
}
