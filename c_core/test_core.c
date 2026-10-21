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
    int end
) {
    Booking b = {0};

    b.booking_id = id;
    snprintf(b.building, sizeof(b.building), "%s", building);
    snprintf(b.room, sizeof(b.room), "%s", room);
    b.day_of_week = day;
    b.start_minute = start;
    b.end_minute = end;

    return b;
}

static void test_validation_and_overlap(void) {
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

static void test_sorting(void) {
    Booking items[] = {
        {0},
        {0},
        {0}
    };

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

static void test_availability(void) {
    Booking items[] = {
        {0}
    };

    items[0] = make_booking(1, "CSIT", "CR-1", 1, 540, 600);

    assert(is_room_available(items, 1, "CSIT", "CR-1", 1, 600, 650) == 1);
    assert(is_room_available(items, 1, "CSIT", "CR-1", 1, 590, 620) == 0);
    assert(is_room_available(items, 1, "BTech Block", "CR-1", 1, 550, 580) == 1);
    assert(is_room_free(items, 1, "CSIT", "CR-1", 1, 600, 650) == 1);
    assert(is_room_free(items, 1, "CSIT", "CR-1", 1, 550, 580) == 0);

    puts("PASS: room availability");
}

static void test_free_slots(void) {
    Booking items[] = {
        {0},
        {0}
    };
    FreeSlot slots[5];

    items[0] = make_booking(1, "CSIT", "CR-1", 1, 600, 660);
    items[1] = make_booking(2, "CSIT", "CR-1", 1, 540, 600);

    /* Unsorted input; adjacent bookings should form one occupied block. */
    int count = find_free_slots(
        items, 2, "CSIT", "CR-1", 1, 540, 720, slots, 5
    );

    assert(count == 1);
    assert(slots[0].start_minute == 660);
    assert(slots[0].end_minute == 720);

    /* Empty list: the whole requested window is free. */
    count = find_free_slots(
        NULL, 0, "CSIT", "CR-1", 1, 540, 720, slots, 5
    );
    assert(count == 1);
    assert(slots[0].start_minute == 540);
    assert(slots[0].end_minute == 720);

    /* Gaps at the start and end of the window. */
    items[0] = make_booking(3, "CSIT", "CR-1", 1, 570, 600);
    items[1] = make_booking(4, "CSIT", "CR-1", 1, 660, 690);

    count = find_free_slots(
        items, 2, "CSIT", "CR-1", 1, 540, 720, slots, 5
    );

    assert(count == 3);
    assert(slots[0].start_minute == 540 && slots[0].end_minute == 570);
    assert(slots[1].start_minute == 600 && slots[1].end_minute == 660);
    assert(slots[2].start_minute == 690 && slots[2].end_minute == 720);

    puts("PASS: free-slot discovery and boundaries");
}

static void test_full_day_and_invalid_input(void) {
    Booking full_day[] = {
        {0}
    };
    FreeSlot slots[3];

    full_day[0] = make_booking(1, "CSIT", "CR-1", 1, 0, 1440);

    int count = find_free_slots(
        full_day, 1, "CSIT", "CR-1", 1, 0, 1440, slots, 3
    );
    assert(count == 0);

    assert(find_free_slots(
        NULL, -1, "CSIT", "CR-1", 1, 0, 1440, slots, 3
    ) == -1);

    assert(find_free_slots(
        NULL, 0, "CSIT", "CR-1", 1, 0, 1440, slots, 0
    ) == -2);

    Booking invalid = make_booking(2, "CSIT", "CR-1", 1, -1, 100);
    assert(validate_booking(&invalid) == 0);

    puts("PASS: full-day booking and invalid inputs");
}

int main(void) {
    test_validation_and_overlap();
    test_sorting();
    test_availability();
    test_free_slots();
    test_full_day_and_invalid_input();

    puts("All C core tests passed.");
    return 0;
}
