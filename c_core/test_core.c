#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "core.h"

static Booking make_booking(
    int id,
    const char *building,
    const char *room,
    int day,
    int start,
    int end)
{
    Booking b = {0};
    b.booking_id = id;
    snprintf(b.building, sizeof(b.building), "%s", building);
    snprintf(b.room, sizeof(b.room), "%s", room);
    b.day_of_week = day;
    b.start_minute = start;
    b.end_minute = end;

    return b;
}

static void test_validation_and_overlap(void)
{
    Booking a = make_booking(1, "CSIT", "CR-1", 1, 540, 600);
    Booking adjacent = make_booking(2, "CSIT", "CR-1", 1, 600, 660);
    Booking overlapping = make_booking(3, "CSIT", "CR-1", 1, 590, 630);
    Booking other_building = make_booking(4, "BTech Block", "CR-1", 1, 550, 580);
    Booking invalid = make_booking(5, "CSIT", "CR-1", 1, 700, 700);

    assert(validate_booking(&a) == 1);
    assert(validate_booking(&invalid) == 0);
    assert(validate_booking(NULL) == 0);

    assert(bookings_overlap(&a, &adjacent) == 0);
    assert(bookings_overlap(&a, &overlapping) == 1);
    assert(bookings_overlap(&a, &other_building) == 0);

    puts("PASS: validation and overlap rules");
}

static void test_sorting(void)
{
    Booking items[] = {
        {0},
        {0},
        {0}};

    items[0] = make_booking(1, "CSIT", "CR-1", 1, 700, 740);
    items[1] = make_booking(2, "CSIT", "CR-1", 1, 540, 580);
    items[2] = make_booking(3, "CSIT", "CR-1", 1, 620, 660);

    sort_bookings(items, 3);

    assert(items[0].start_minute == 540);
    assert(items[1].start_minute == 620);
    assert(items[2].start_minute == 700);

    sort_bookings(NULL, 0);

    puts("PASS: sorting unsorted bookings");
}

static void test_availability(void)
{
    Booking items[] = {
        {0}};

    items[0] = make_booking(1, "CSIT", "CR-1", 1, 540, 600);

    assert(is_room_available(items, 1, "CSIT", "CR-1", 1, 600, 650) == 1);
    assert(is_room_available(items, 1, "CSIT", "CR-1", 1, 590, 620) == 0);
    assert(is_room_available(items, 1, "BTech Block", "CR-1", 1, 550, 580) == 1);
    assert(is_room_free(items, 1, "CSIT", "CR-1", 1, 600, 650) == 1);
    assert(is_room_free(items, 1, "CSIT", "CR-1", 1, 550, 580) == 0);

    puts("PASS: room availability");
}

static void test_free_slots(void)
{
    Booking items[] = {
        {0},
        {0}};
    FreeSlot slots[5];

    items[0] = make_booking(1, "CSIT", "CR-1", 1, 600, 660);
    items[1] = make_booking(2, "CSIT", "CR-1", 1, 540, 600);

    /* Unsorted input; adjacent bookings should form one occupied block. */
    int count = find_free_slots(
        items, 2, "CSIT", "CR-1", 1, 540, 720, slots, 5);

    assert(count == 1);
    assert(slots[0].start_minute == 660);
    assert(slots[0].end_minute == 720);

    /* Empty list: the whole requested window is free. */
    count = find_free_slots(
        NULL, 0, "CSIT", "CR-1", 1, 540, 720, slots, 5);
    assert(count == 1);
    assert(slots[0].start_minute == 540);
    assert(slots[0].end_minute == 720);

    /* Gaps at the start and end of the window. */
    items[0] = make_booking(3, "CSIT", "CR-1", 1, 570, 600);
    items[1] = make_booking(4, "CSIT", "CR-1", 1, 660, 690);

    count = find_free_slots(
        items, 2, "CSIT", "CR-1", 1, 540, 720, slots, 5);

    assert(count == 3);
    assert(slots[0].start_minute == 540 && slots[0].end_minute == 570);
    assert(slots[1].start_minute == 600 && slots[1].end_minute == 660);
    assert(slots[2].start_minute == 690 && slots[2].end_minute == 720);

    puts("PASS: free-slot discovery and boundaries");
}

static void test_full_day_and_invalid_input(void)
{
    Booking full_day[] = {
        {0}};
    FreeSlot slots[3];

    full_day[0] = make_booking(1, "CSIT", "CR-1", 1, 0, 1440);

    int count = find_free_slots(
        full_day, 1, "CSIT", "CR-1", 1, 0, 1440, slots, 3);
    assert(count == 0);

    assert(find_free_slots(
               NULL, -1, "CSIT", "CR-1", 1, 0, 1440, slots, 3) == -1);

    assert(find_free_slots(
               NULL, 0, "CSIT", "CR-1", 1, 0, 1440, slots, 0) == -2);

    Booking invalid = make_booking(2, "CSIT", "CR-1", 1, -1, 100);
    assert(validate_booking(&invalid) == 0);

    puts("PASS: full-day booking and invalid inputs");
}

static void test_clash_detection(void)
{
    BookingClash out[10];

    /* Two overlapping bookings in the same room: 1 clash */
    Booking overlap[] = {
        make_booking(1, "Main", "R101", 1, 540, 600),
        make_booking(2, "Main", "R101", 1, 570, 630)};
    assert(detect_booking_clashes(overlap, 2, 1, out, 10) == 1);
    assert(out[0].booking_id_a == 1 && out[0].booking_id_b == 2);

    /* Adjacent bookings: no clash */
    Booking adjacent[] = {
        make_booking(1, "Main", "R101", 1, 540, 600),
        make_booking(2, "Main", "R101", 1, 600, 660)};
    assert(detect_booking_clashes(adjacent, 2, 1, out, 10) == 0);

    /* Same time, different rooms: no clash */
    Booking rooms[] = {
        make_booking(1, "Main", "R101", 1, 540, 600),
        make_booking(2, "Main", "R102", 1, 540, 600)};
    assert(detect_booking_clashes(rooms, 2, 1, out, 10) == 0);

    /* Overlap on a different day than the one queried: no clash */
    Booking other_day[] = {
        make_booking(1, "Main", "R101", 2, 540, 600),
        make_booking(2, "Main", "R101", 2, 570, 630)};
    assert(detect_booking_clashes(other_day, 2, 1, out, 10) == 0);

    /* Three mutually overlapping bookings: 3 clashes */
    Booking triple[] = {
        make_booking(1, "Main", "R101", 1, 540, 660),
        make_booking(2, "Main", "R101", 1, 560, 640),
        make_booking(3, "Main", "R101", 1, 580, 620)};
    assert(detect_booking_clashes(triple, 3, 1, out, 10) == 3);

    /* Output buffer too small: -2 */
    assert(detect_booking_clashes(triple, 3, 1, out, 1) == -2);

    /* Invalid booking (start == end): -1 */
    Booking invalid[] = {make_booking(1, "Main", "R101", 1, 600, 600)};
    assert(detect_booking_clashes(invalid, 1, 1, out, 10) == -1);

    /* Invalid day: -1 */
    assert(detect_booking_clashes(triple, 3, 6, out, 10) == -1);

    /* Empty list: 0 */
    assert(detect_booking_clashes(NULL, 0, 1, out, 10) == 0);

    puts("PASS: sweep-line clash detection");
}

static StudyTopic make_topic(
    int id,
    const char *name,
    double mastery,
    int minutes)
{
    StudyTopic t = {0};
    t.topic_id = id;
    snprintf(t.topic_name, sizeof(t.topic_name), "%s", name);
    t.mastery_pct = mastery;
    t.estimated_minutes = minutes;

    return t;
}

static void test_study_priority_score(void)
{
    StudyTopic weak = make_topic(1, "Recursion", 0.0, 30);
    StudyTopic mid = make_topic(2, "Hashing", 42.5, 30);
    StudyTopic strong = make_topic(3, "Arrays", 100.0, 30);
    StudyTopic invalid = make_topic(4, "Invalid", 120.0, 30);

    assert(study_priority_score(&weak) == 100.0);
    assert(study_priority_score(&mid) == 57.5);
    assert(study_priority_score(&strong) == 0.0);
    assert(study_priority_score(&invalid) == -1.0);
    assert(study_priority_score(NULL) == -1.0);

    puts("PASS: study priority score");
}

static void test_rank_topics_min_heap(void)
{
    StudyPlanItem ranked[6];
    StudyTopic topics[] = {
        make_topic(1, "Arrays", 90.0, 30),
        make_topic(2, "Recursion", 20.0, 45),
        make_topic(3, "Trees", 55.0, 40),
        make_topic(4, "Graphs", 20.0, 60),
    };

    /* Weakest topic (lowest mastery) first. */
    int count = rank_topics_by_weakness(topics, 4, ranked, 6);
    assert(count == 4);
    assert(ranked[0].topic_id == 2 && ranked[0].position == 1);
    assert(ranked[1].topic_id == 4);
    assert(ranked[2].topic_id == 3);
    assert(ranked[3].topic_id == 1);
    assert(strcmp(ranked[0].topic_name, "Recursion") == 0);
    assert(ranked[0].priority_score == 80.0);
    assert(ranked[0].allocated_minutes == 45);

    /* Equal mastery keeps the lower topic_id first. */
    StudyTopic equal[] = {
        make_topic(7, "Loops", 50.0, 20),
        make_topic(5, "Stacks", 50.0, 20),
    };
    count = rank_topics_by_weakness(equal, 2, ranked, 6);
    assert(count == 2);
    assert(ranked[0].topic_id == 5 && ranked[1].topic_id == 7);

    /* One topic. */
    count = rank_topics_by_weakness(topics, 1, ranked, 6);
    assert(count == 1 && ranked[0].topic_id == 1);

    /* Empty list. */
    assert(rank_topics_by_weakness(NULL, 0, ranked, 6) == 0);

    /* Invalid argument and invalid topic data. */
    assert(rank_topics_by_weakness(NULL, 2, ranked, 6) == -1);
    assert(rank_topics_by_weakness(topics, 4, NULL, 6) == -1);
    assert(rank_topics_by_weakness(topics, 4, ranked, 2) == -1);
    assert(rank_topics_by_weakness(topics, -1, ranked, 6) == -1);

    StudyTopic bad_mastery[] = {make_topic(1, "Negative", -1.0, 30)};
    assert(rank_topics_by_weakness(bad_mastery, 1, ranked, 6) == -2);

    StudyTopic bad_minutes[] = {make_topic(1, "Zero", 50.0, 0)};
    assert(rank_topics_by_weakness(bad_minutes, 1, ranked, 6) == -2);

    StudyTopic no_name[] = {make_topic(1, "", 50.0, 30)};
    assert(rank_topics_by_weakness(no_name, 1, ranked, 6) == -2);

    puts("PASS: min-heap ranking of weak topics");
}

static void test_build_study_schedule(void)
{
    StudyPlanItem plan[5];
    StudyPlanItem skipped[5];
    int scheduled = -1;
    int skipped_out = -1;
    StudyTopic topics[] = {
        make_topic(1, "Recursion", 20.0, 60),
        make_topic(2, "Hashing", 50.0, 45),
        make_topic(3, "Arrays", 90.0, 30),
    };

    /* Enough time for everything: weakest first, total used = 135. */
    int count = build_study_schedule(
        topics, 3, 240, plan, 5, skipped, 5, &scheduled, &skipped_out);
    assert(count == 3);
    assert(scheduled == 135);
    assert(plan[0].topic_id == 1 && plan[0].allocated_minutes == 60);
    assert(plan[1].topic_id == 2 && plan[1].allocated_minutes == 45);
    assert(plan[2].topic_id == 3 && plan[2].allocated_minutes == 30);
    assert(plan[0].position == 1 && plan[2].position == 3);
    assert(skipped_out == 0);

    /*
     * Partial allocation: after the 60-minute topic, the 45-minute topic
     * does not fit in the remaining 10 minutes, so the strongest fitting
     * topic gets those 10 minutes. The two rejected topics are reported.
     */
    count = build_study_schedule(
        topics, 3, 70, plan, 5, skipped, 5, &scheduled, &skipped_out);
    assert(count == 2);
    assert(scheduled == 70);
    assert(plan[0].topic_id == 1 && plan[0].allocated_minutes == 60);
    assert(plan[1].topic_id == 2 && plan[1].allocated_minutes == 10);
    assert(plan[0].position == 1 && plan[1].position == 2);
    assert(skipped[0].topic_id == 2 && skipped[0].position == 0);
    assert(skipped[0].allocated_minutes == 45);
    assert(skipped[1].topic_id == 3 && skipped[1].position == 0);
    assert(skipped_out == 2);

    /* 105 minutes: 60 + 45 fit exactly, 5 minutes are left over. */
    count = build_study_schedule(
        topics, 3, 105, plan, 5, skipped, 5, &scheduled, &skipped_out);
    assert(count == 2);
    assert(scheduled == 105);
    assert(plan[0].topic_id == 1 && plan[1].topic_id == 2);
    assert(skipped[0].topic_id == 3 && skipped[0].position == 0);
    assert(skipped[0].allocated_minutes == 30);
    assert(skipped_out == 1);

    /* 45 minutes: exactly one topic fits, no leftover to allocate. */
    count = build_study_schedule(
        topics, 3, 45, plan, 5, skipped, 5, &scheduled, &skipped_out);
    assert(count == 1);
    assert(scheduled == 45);
    assert(plan[0].topic_id == 1 && plan[0].allocated_minutes == 45);
    /* The weakest topic is partial, so all three are reported as short. */
    assert(skipped[0].topic_id == 1 && skipped[0].allocated_minutes == 60);
    assert(skipped[1].topic_id == 2 && skipped[1].allocated_minutes == 45);
    assert(skipped[2].topic_id == 3 && skipped[2].allocated_minutes == 30);
    assert(skipped_out == 3);

    /* 90 minutes: the 60-minute topic plus 30 partial minutes of the next. */
    count = build_study_schedule(
        topics, 3, 90, plan, 5, skipped, 5, &scheduled, &skipped_out);
    assert(count == 2);
    assert(scheduled == 90);
    assert(plan[0].topic_id == 1 && plan[0].allocated_minutes == 60);
    assert(plan[1].topic_id == 2 && plan[1].allocated_minutes == 30);
    assert(plan[0].position == 1 && plan[1].position == 2);
    assert(skipped[0].topic_id == 2 && skipped[0].allocated_minutes == 45);
    assert(skipped_out == 2);

    /* Only 10 minutes: not even the weakest topic fits as a whole. */
    count = build_study_schedule(
        topics, 3, 10, plan, 5, skipped, 5, &scheduled, &skipped_out);
    assert(count == 1);
    assert(scheduled == 10);
    assert(plan[0].topic_id == 1 && plan[0].allocated_minutes == 10);
    assert(plan[0].position == 1);
    /* All three topics still need more time than they received. */
    assert(skipped[0].topic_id == 1 && skipped[0].allocated_minutes == 60);
    assert(skipped[2].topic_id == 3);
    assert(skipped_out == 3);

    /* Never exceeds the available time. */
    for (int available = 1; available <= 200; available++) {
        count = build_study_schedule(
            topics, 3, available, plan, 5, skipped, 5, &scheduled, &skipped_out);
        int total = 0;
        for (int i = 0; i < count; i++) total += plan[i].allocated_minutes;
        assert(count >= 0);
        assert(total == scheduled);
        assert(total <= available);
        assert(count <= 5);
        assert(skipped_out >= 0 && skipped_out <= 4);
        assert(count + skipped_out >= 3);
    }

    /* Empty list is valid and schedules nothing. */
    assert(build_study_schedule(NULL, 0, 60, plan, 5, skipped, 5, &scheduled, &skipped_out) == 0);
    assert(scheduled == 0 && skipped_out == 0);

    /* Invalid arguments. */
    assert(build_study_schedule(topics, 3, 0, plan, 5, skipped, 5, &scheduled, &skipped_out) == -4);
    assert(build_study_schedule(topics, 3, -30, plan, 5, skipped, 5, &scheduled, &skipped_out) == -4);
    assert(build_study_schedule(topics, 3, 60, plan, 2, skipped, 5, &scheduled, &skipped_out) == -1);
    assert(build_study_schedule(topics, 3, 60, plan, 0, skipped, 5, &scheduled, &skipped_out) == -1);
    assert(build_study_schedule(NULL, 3, 60, plan, 5, skipped, 5, &scheduled, &skipped_out) == -1);
    assert(build_study_schedule(topics, 3, 60, NULL, 5, skipped, 5, &scheduled, &skipped_out) == -1);

    StudyTopic bad[] = {make_topic(1, "Bad", 101.0, 30)};
    assert(build_study_schedule(bad, 1, 60, plan, 5, skipped, 5, &scheduled, &skipped_out) == -2);

    /* Zero-duration topics are rejected, never scheduled. */
    StudyTopic bad_minutes[] = {make_topic(1, "Zero", 50.0, 0)};
    assert(build_study_schedule(bad_minutes, 1, 60, plan, 5, skipped, 5, &scheduled, &skipped_out) == -2);

    /* A NULL skipped buffer is rejected while skipped_capacity is positive. */
    assert(build_study_schedule(topics, 3, 60, plan, 5, NULL, 5, &scheduled, &skipped_out) == -1);

    puts("PASS: greedy max-heap study scheduling");
}

int main(void)
{
    test_validation_and_overlap();
    test_sorting();
    test_availability();
    test_free_slots();
    test_full_day_and_invalid_input();
    test_clash_detection();
    test_study_priority_score();
    test_rank_topics_min_heap();
    test_build_study_schedule();

    puts("All C core tests passed.");
    return 0;
}
