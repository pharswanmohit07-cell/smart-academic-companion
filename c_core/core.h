#ifndef CORE_H
#define CORE_H

#include <stddef.h>

#define MAX_NAME_LEN 100
#define MAX_ROOM_LEN 16
#define MAX_TOPIC_LEN 100

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

typedef struct {
    int booking_id;
    char room[MAX_ROOM_LEN];
    char section;
    int day_of_week;       /* 1 = Monday, ..., 5 = Friday */
    int start_minute;      /* Minutes after midnight */
    int end_minute;
} Booking;

typedef struct {
    int topic_id;
    char topic_name[MAX_TOPIC_LEN];
    double mastery_pct;
    int estimated_minutes;
} StudyTopic;

#endif
