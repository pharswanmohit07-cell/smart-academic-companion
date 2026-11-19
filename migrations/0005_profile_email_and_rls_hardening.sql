-- 0005_profile_email_and_rls_hardening.sql
--
-- Keep the Supabase profile schema aligned with app/accounts.py and tighten
-- direct Data API permissions. Flask performs class-level authorization on
-- its server-side database connection; direct client writes are restricted to
-- the explicitly supported student submission operations.

-- app-migration:
ALTER TABLE public.user_profiles
    ADD COLUMN IF NOT EXISTS email text;

-- app-migration:
CREATE UNIQUE INDEX IF NOT EXISTS user_profiles_email_lower_key
    ON public.user_profiles (lower(email))
    WHERE email IS NOT NULL;

-- Keep profile email in sync with the verified Auth identity at signup.
-- app-migration:
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.user_profiles (user_id, email, display_name, role)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data ->> 'full_name', ''),
        'student'
    )
    ON CONFLICT (user_id) DO UPDATE
       SET email = EXCLUDED.email;
    RETURN NEW;
END;
$$;

-- app-migration:
REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;

-- Avoid recursive RLS: the UPDATE/DELETE policy must inspect the row's
-- owner_teacher_id directly rather than calling a helper that queries the
-- same faculty_classes table.
-- app-migration:
DROP POLICY IF EXISTS faculty_classes_update_owned ON public.faculty_classes;

-- app-migration:
CREATE POLICY faculty_classes_update_owned ON public.faculty_classes
    FOR UPDATE TO authenticated
    USING (
        public.app_is_admin()
        OR owner_teacher_id = public.app_current_teacher_id()
    )
    WITH CHECK (
        public.app_is_admin()
        OR owner_teacher_id = public.app_current_teacher_id()
    );

-- app-migration:
DROP POLICY IF EXISTS faculty_classes_delete_owned ON public.faculty_classes;

-- app-migration:
CREATE POLICY faculty_classes_delete_owned ON public.faculty_classes
    FOR DELETE TO authenticated
    USING (
        public.app_is_admin()
        OR owner_teacher_id = public.app_current_teacher_id()
    );

-- The Flask backend uses its server-side database connection and enforces
-- faculty class ownership before writes. Do not permit broad client-side
-- writes to global reference tables through PostgREST.
-- app-migration:
REVOKE INSERT, UPDATE, DELETE ON TABLE public.subjects FROM authenticated;

-- app-migration:
DROP POLICY IF EXISTS subjects_write_faculty ON public.subjects;

-- app-migration:
REVOKE INSERT, UPDATE, DELETE ON TABLE public.timetable FROM authenticated;

-- app-migration:
DROP POLICY IF EXISTS timetable_write_faculty ON public.timetable;

-- app-migration:
REVOKE INSERT, UPDATE, DELETE ON TABLE public.room_locations FROM authenticated;

-- app-migration:
DROP POLICY IF EXISTS room_locations_write_faculty ON public.room_locations;

-- app-migration:
REVOKE INSERT, UPDATE, DELETE ON TABLE public.exams FROM authenticated;

-- app-migration:
DROP POLICY IF EXISTS exams_write_faculty ON public.exams;

-- app-migration:
REVOKE INSERT, UPDATE, DELETE ON TABLE public.assessment_items FROM authenticated;

-- app-migration:
DROP POLICY IF EXISTS assessment_items_write_faculty ON public.assessment_items;

-- Students may change only the submitted flag, not assignment identity,
-- ownership, title, subject or due date.
-- app-migration:
REVOKE UPDATE ON TABLE public.assignments FROM authenticated;

-- app-migration:
GRANT UPDATE (submitted) ON TABLE public.assignments TO authenticated;

-- app-migration:
REVOKE UPDATE ON TABLE public.assessment_submissions FROM authenticated;

-- app-migration:
GRANT UPDATE (submitted) ON TABLE public.assessment_submissions TO authenticated;
