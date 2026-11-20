-- 0008_fk_indexes_and_ledger_deny_policy.sql
--
-- Cover the remaining foreign-key columns flagged by the Supabase advisor.
-- The app_migrations ledger remains inaccessible to API roles; the explicit
-- false policy documents and enforces that deny-by-default intent.

-- app-migration:
CREATE INDEX IF NOT EXISTS idx_assignments_student ON public.assignments(student_id);

-- app-migration:
CREATE INDEX IF NOT EXISTS idx_assignments_subject ON public.assignments(subject_id);

-- app-migration:
CREATE INDEX IF NOT EXISTS idx_attendance_subject ON public.attendance(subject_id);

-- app-migration:
CREATE INDEX IF NOT EXISTS idx_exams_subject ON public.exams(subject_id);

-- app-migration:
CREATE INDEX IF NOT EXISTS idx_marks_subject ON public.marks(subject_id);

-- app-migration:
CREATE INDEX IF NOT EXISTS idx_timetable_subject ON public.timetable(subject_id);

-- app-migration:
DROP POLICY IF EXISTS app_migrations_deny_clients ON public.app_migrations;

-- app-migration:
CREATE POLICY app_migrations_deny_clients
    ON public.app_migrations
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);
