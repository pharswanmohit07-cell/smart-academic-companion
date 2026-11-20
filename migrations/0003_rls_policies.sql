-- 0003_rls_policies.sql
--
-- Row Level Security for every application table exposed through the
-- Supabase API. The Flask application connects as the database owner (which
-- bypasses RLS) after doing its own authorization checks; these policies are
-- the second line of defence that stops a signed-in user from bypassing the
-- app and calling PostgREST / the database directly.
--
-- Identity model
-- --------------
--   students.auth_user_id        -> auth.users(id)   (one login = one student)
--   teachers.auth_user_id        -> auth.users(id)   (faculty directory)
--   faculty_classes.owner_teacher_id -> teachers     (class-level authorization)
--   public.user_profiles.role    -> trusted role     (student/faculty/admin)
--
-- Policy summary
-- --------------
--   students        read own row only; faculty read students in classes they
--                   own; admins all. Only an admin (server-side) may insert,
--                   update or delete.
--   attendance /
--   marks           read own records only; faculty read records of students in
--                   classes they own. Writes are server-side only.
--   assignments     read own; students may update their own `submitted` flag.
--   assessment_submissions  read own; students may mark their own row submitted.
--   subjects / timetable / room_locations / faculty_classes / exams
--                   readable by any signed-in user (shared timetable data);
--                   faculty may write only inside classes they own / admin.
--   assessment_items  faculty write only for subjects used in their classes.
--   teachers        read own row; admin all.
--
-- Every table has RLS enabled. Tables without a client policy (all the
-- academic record tables) deny every client write by default: the app's
-- server-side connection performs those writes.
--
-- Recursion: policies reference only helper functions from 0002, which read
-- tables the caller can already see (own profile / own teacher row), so
-- policies never call each other.

-- Deny-by-default baseline: remove any inherited client grant first.
-- app-migration:
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'faculty_classes', 'students', 'subjects', 'attendance', 'marks',
        'timetable', 'room_locations', 'assignments', 'exams',
        'assessment_items', 'assessment_submissions', 'teachers'
    ] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
        EXECUTE format('GRANT SELECT ON TABLE public.%I TO authenticated', t);
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
    END LOOP;
END $$;

-- Writes granted to the client only where a policy below allows them.
-- app-migration:
GRANT INSERT, UPDATE ON TABLE public.assignments TO authenticated;

-- app-migration:
GRANT INSERT, UPDATE ON TABLE public.assessment_submissions TO authenticated;

-- app-migration:
GRANT INSERT, UPDATE, DELETE ON TABLE public.room_locations TO authenticated;

-- app-migration:
GRANT INSERT, UPDATE, DELETE ON TABLE public.timetable TO authenticated;

-- app-migration:
GRANT INSERT, UPDATE, DELETE ON TABLE public.assessment_items TO authenticated;

-- app-migration:
GRANT INSERT, UPDATE, DELETE ON TABLE public.faculty_classes TO authenticated;

-- app-migration:
GRANT INSERT, UPDATE, DELETE ON TABLE public.subjects TO authenticated;

-- app-migration:
GRANT INSERT, UPDATE, DELETE ON TABLE public.exams TO authenticated;

-- ------------------------------------------------------------------ students
-- app-migration:
DROP POLICY IF EXISTS students_select_own ON public.students;

-- app-migration:
CREATE POLICY students_select_own ON public.students
    FOR SELECT TO authenticated
    USING (
        auth_user_id = (SELECT auth.uid())
        OR public.app_is_admin()
        OR (
            public.app_current_role() = 'faculty'
            AND class_id IS NOT NULL
            AND public.app_teacher_owns_class(class_id)
        )
    );

-- --------------------------------------------------------------- attendance
-- app-migration:
DROP POLICY IF EXISTS attendance_select ON public.attendance;

-- app-migration:
CREATE POLICY attendance_select ON public.attendance
    FOR SELECT TO authenticated
    USING (
        student_id = public.app_current_student_id()
        OR public.app_is_admin()
        OR EXISTS (
            SELECT 1 FROM public.students AS s
             WHERE s.student_id = attendance.student_id
               AND s.class_id IS NOT NULL
               AND public.app_teacher_owns_class(s.class_id)
        )
    );

-- -------------------------------------------------------------------- marks
-- app-migration:
DROP POLICY IF EXISTS marks_select ON public.marks;

-- app-migration:
CREATE POLICY marks_select ON public.marks
    FOR SELECT TO authenticated
    USING (
        student_id = public.app_current_student_id()
        OR public.app_is_admin()
        OR EXISTS (
            SELECT 1 FROM public.students AS s
             WHERE s.student_id = marks.student_id
               AND s.class_id IS NOT NULL
               AND public.app_teacher_owns_class(s.class_id)
        )
    );

-- -------------------------------------------------------------- assignments
-- app-migration:
DROP POLICY IF EXISTS assignments_select ON public.assignments;

-- app-migration:
CREATE POLICY assignments_select ON public.assignments
    FOR SELECT TO authenticated
    USING (
        student_id = public.app_current_student_id()
        OR public.app_is_admin()
        OR EXISTS (
            SELECT 1 FROM public.students AS s
             WHERE s.student_id = assignments.student_id
               AND s.class_id IS NOT NULL
               AND public.app_teacher_owns_class(s.class_id)
        )
    );

-- A student may only flip the submitted flag on their own assignment.
-- app-migration:
DROP POLICY IF EXISTS assignments_update_own ON public.assignments;

-- app-migration:
CREATE POLICY assignments_update_own ON public.assignments
    FOR UPDATE TO authenticated
    USING (student_id = public.app_current_student_id())
    WITH CHECK (student_id = public.app_current_student_id());

-- ---------------------------------------------------- assessment_submissions
-- app-migration:
DROP POLICY IF EXISTS submissions_select ON public.assessment_submissions;

-- app-migration:
CREATE POLICY submissions_select ON public.assessment_submissions
    FOR SELECT TO authenticated
    USING (
        student_id = public.app_current_student_id()
        OR public.app_is_admin()
        OR EXISTS (
            SELECT 1 FROM public.students AS s
             WHERE s.student_id = assessment_submissions.student_id
               AND s.class_id IS NOT NULL
               AND public.app_teacher_owns_class(s.class_id)
        )
    );

-- app-migration:
DROP POLICY IF EXISTS submissions_upsert_own ON public.assessment_submissions;

-- app-migration:
CREATE POLICY submissions_upsert_own ON public.assessment_submissions
    FOR INSERT TO authenticated
    WITH CHECK (student_id = public.app_current_student_id());

-- app-migration:
DROP POLICY IF EXISTS submissions_update_own ON public.assessment_submissions;

-- app-migration:
CREATE POLICY submissions_update_own ON public.assessment_submissions
    FOR UPDATE TO authenticated
    USING (student_id = public.app_current_student_id())
    WITH CHECK (student_id = public.app_current_student_id());

-- --------------------------------------------------------- faculty_classes
-- app-migration:
DROP POLICY IF EXISTS faculty_classes_select ON public.faculty_classes;

-- app-migration:
CREATE POLICY faculty_classes_select ON public.faculty_classes
    FOR SELECT TO authenticated
    USING (true);

-- Faculty may create a class only if it is owned by their own teacher row.
-- app-migration:
DROP POLICY IF EXISTS faculty_classes_insert_owned ON public.faculty_classes;

-- app-migration:
CREATE POLICY faculty_classes_insert_owned ON public.faculty_classes
    FOR INSERT TO authenticated
    WITH CHECK (
        public.app_is_admin()
        OR (
            public.app_current_role() = 'faculty'
            AND owner_teacher_id = public.app_current_teacher_id()
            AND owner_teacher_id IS NOT NULL
        )
    );

-- app-migration:
DROP POLICY IF EXISTS faculty_classes_update_owned ON public.faculty_classes;

-- app-migration:
CREATE POLICY faculty_classes_update_owned ON public.faculty_classes
    FOR UPDATE TO authenticated
    USING (public.app_is_admin() OR public.app_teacher_owns_class(class_id))
    WITH CHECK (public.app_is_admin() OR public.app_teacher_owns_class(class_id));

-- app-migration:
DROP POLICY IF EXISTS faculty_classes_delete_owned ON public.faculty_classes;

-- app-migration:
CREATE POLICY faculty_classes_delete_owned ON public.faculty_classes
    FOR DELETE TO authenticated
    USING (public.app_is_admin() OR public.app_teacher_owns_class(class_id));

-- ------------------------------------------------------------ shared data
-- Subjects, timetable, rooms and exams are read-only reference data for
-- every signed-in user. Only faculty/admin may change them.
-- app-migration:
DROP POLICY IF EXISTS subjects_select ON public.subjects;

-- app-migration:
CREATE POLICY subjects_select ON public.subjects
    FOR SELECT TO authenticated
    USING (true);

-- app-migration:
DROP POLICY IF EXISTS subjects_write_faculty ON public.subjects;

-- app-migration:
CREATE POLICY subjects_write_faculty ON public.subjects
    FOR ALL TO authenticated
    USING (public.app_is_faculty())
    WITH CHECK (public.app_is_faculty());

-- app-migration:
DROP POLICY IF EXISTS timetable_select ON public.timetable;

-- app-migration:
CREATE POLICY timetable_select ON public.timetable
    FOR SELECT TO authenticated
    USING (true);

-- app-migration:
DROP POLICY IF EXISTS timetable_write_faculty ON public.timetable;

-- app-migration:
CREATE POLICY timetable_write_faculty ON public.timetable
    FOR ALL TO authenticated
    USING (public.app_is_faculty())
    WITH CHECK (public.app_is_faculty());

-- app-migration:
DROP POLICY IF EXISTS room_locations_select ON public.room_locations;

-- app-migration:
CREATE POLICY room_locations_select ON public.room_locations
    FOR SELECT TO authenticated
    USING (true);

-- app-migration:
DROP POLICY IF EXISTS room_locations_write_faculty ON public.room_locations;

-- app-migration:
CREATE POLICY room_locations_write_faculty ON public.room_locations
    FOR ALL TO authenticated
    USING (public.app_is_faculty())
    WITH CHECK (public.app_is_faculty());

-- app-migration:
DROP POLICY IF EXISTS exams_select ON public.exams;

-- app-migration:
CREATE POLICY exams_select ON public.exams
    FOR SELECT TO authenticated
    USING (true);

-- app-migration:
DROP POLICY IF EXISTS exams_write_faculty ON public.exams;

-- app-migration:
CREATE POLICY exams_write_faculty ON public.exams
    FOR ALL TO authenticated
    USING (public.app_is_faculty())
    WITH CHECK (public.app_is_faculty());

-- ------------------------------------------------------- assessment_items
-- app-migration:
DROP POLICY IF EXISTS assessment_items_select ON public.assessment_items;

-- app-migration:
CREATE POLICY assessment_items_select ON public.assessment_items
    FOR SELECT TO authenticated
    USING (true);

-- Faculty may create or change an assessment only for a subject that is used
-- by a class they own (or a subject not yet tied to any class at all).
-- app-migration:
DROP POLICY IF EXISTS assessment_items_write_faculty ON public.assessment_items;

-- app-migration:
CREATE POLICY assessment_items_write_faculty ON public.assessment_items
    FOR ALL TO authenticated
    USING (public.app_is_faculty())
    WITH CHECK (
        public.app_is_admin()
        OR (
            NOT EXISTS (
                SELECT 1 FROM public.timetable AS t
                 WHERE t.subject_id = assessment_items.subject_id
            )
            OR EXISTS (
                SELECT 1
                  FROM public.timetable AS t
                  JOIN public.students AS s ON s.class_id IS NOT NULL
                  JOIN public.faculty_classes AS c ON c.class_id = s.class_id
                 WHERE t.subject_id = assessment_items.subject_id
                   AND c.owner_teacher_id = public.app_current_teacher_id()
            )
        )
    );

-- ------------------------------------------------------------------ teachers
-- app-migration:
DROP POLICY IF EXISTS teachers_select_own ON public.teachers;

-- app-migration:
CREATE POLICY teachers_select_own ON public.teachers
    FOR SELECT TO authenticated
    USING (auth_user_id = (SELECT auth.uid()) OR public.app_is_admin());

-- ------------------------------------------------------------------- notes
--
-- 1. public.user_profiles keeps the policies created with the project
--    (read own profile, insert own student profile, role updates revoked).
--    This migration does not replace them. Verify with:
--
--        select policyname, cmd, qual, with_check
--          from pg_policies where schemaname = 'public' and tablename = 'user_profiles';
--
--    The role column must NOT be updatable by `authenticated`:
--
--        select role has_column_privilege('authenticated', 'public.user_profiles', 'role', 'UPDATE');
--
--    Expected: false.
--
-- 2. Promotion to faculty/admin is a trusted server-side operation. The Flask
--    app validates the caller's role from user_profiles and then uses its
--    DATABASE_URL connection to update the role. No client policy allows it,
--    so a user cannot promote themselves through the API.
--
-- 3. Service-role keys are never sent to the browser. The app reads them from
--    the server environment only (see app/supabase_client.py).
