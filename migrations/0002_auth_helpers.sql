-- 0002_auth_helpers.sql
--
-- Trusted-identity helpers used by the Row Level Security policies.
--
-- * app_current_role()            - the caller's role from public.user_profiles
-- * app_is_admin() / app_is_faculty()
-- * app_current_student_id()      - students.student_id for the caller's login
-- * app_current_teacher_id()      - teachers.teacher_id for the caller's login
-- * app_teacher_owns_class(class_id) / app_student_in_class(class_id)
-- * app_can_view_class(class_id)  - admin, class owner, or a student in it
--
-- Design notes
-- ------------
-- The role is ALWAYS read from public.user_profiles, never from JWT metadata:
-- user_metadata is writable by the signed-in user, so it can never be used for
-- authorization. The deployed project revokes UPDATE on the role column from
-- `authenticated`, and app_current_role() additionally treats any role other
-- than student/faculty/admin as "student".
--
-- Every helper is STABLE, schema-qualified and SECURITY INVOKER (there is no
-- SECURITY DEFINER anywhere in this project). They only read rows the caller's
-- own policies already permit - a user can always read their own profile and
-- their own teacher row - so they cannot be used to read other people's data,
-- and none of them writes, so a caller cannot escalate by invoking them.
--
-- Recursive policy evaluation: a policy on `students` that calls a helper which
-- queries `students` would recurse. app_current_student_id() is therefore only
-- used in policies on other tables; the student policies compare
-- students.auth_user_id with auth.uid() directly.
--
-- Admin actions are trusted server-side only. No policy grants admin from the
-- client: the Flask application checks the role in Python and performs admin
-- work over its DATABASE_URL connection (app/auth.py, app/views/faculty_views.py).

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_current_role()
RETURNS text
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $fn$
    SELECT COALESCE(
        (SELECT p.role FROM public.user_profiles AS p
          WHERE p.user_id = (SELECT auth.uid())),
        'student'
    );
$fn$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $fn$
    SELECT public.app_current_role() = 'admin';
$fn$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_is_faculty()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $fn$
    SELECT public.app_current_role() IN ('faculty', 'admin');
$fn$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.student_id_for(target_user uuid)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $fn$
    SELECT s.student_id FROM public.students AS s
     WHERE s.auth_user_id = target_user;
$fn$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_current_student_id()
RETURNS integer
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $fn$
    SELECT public.student_id_for((SELECT auth.uid()));
$fn$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_current_teacher_id()
RETURNS integer
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $fn$
    SELECT t.teacher_id FROM public.teachers AS t
     WHERE t.auth_user_id = (SELECT auth.uid());
$fn$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_teacher_owns_class(target_class_id integer)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $fn$
    SELECT EXISTS (
        SELECT 1 FROM public.faculty_classes AS c
         WHERE c.class_id = target_class_id
           AND c.owner_teacher_id = public.app_current_teacher_id()
    );
$fn$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_student_in_class(target_class_id integer)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $fn$
    SELECT EXISTS (
        SELECT 1 FROM public.students AS s
         WHERE s.class_id = target_class_id
           AND s.auth_user_id = (SELECT auth.uid())
    );
$fn$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_can_view_class(target_class_id integer)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $fn$
    SELECT public.app_is_admin()
        OR public.app_teacher_owns_class(target_class_id)
        OR public.app_student_in_class(target_class_id);
$fn$;

-- Helpers are internal: only policies call them, so no client role gets EXECUTE.
-- app-migration:
REVOKE ALL ON FUNCTION public.app_current_role() FROM PUBLIC, anon;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_is_admin() FROM PUBLIC, anon;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_is_faculty() FROM PUBLIC, anon;

-- app-migration:
REVOKE ALL ON FUNCTION public.student_id_for(uuid) FROM PUBLIC, anon;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_current_student_id() FROM PUBLIC, anon;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_current_teacher_id() FROM PUBLIC, anon;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_teacher_owns_class(integer) FROM PUBLIC, anon;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_student_in_class(integer) FROM PUBLIC, anon;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_can_view_class(integer) FROM PUBLIC, anon;

-- app-migration:
GRANT EXECUTE ON FUNCTION public.app_current_role() TO authenticated, service_role;

-- app-migration:
GRANT EXECUTE ON FUNCTION public.app_is_admin() TO authenticated, service_role;

-- app-migration:
GRANT EXECUTE ON FUNCTION public.app_is_faculty() TO authenticated, service_role;

-- app-migration:
GRANT EXECUTE ON FUNCTION public.student_id_for(uuid) TO authenticated, service_role;

-- app-migration:
GRANT EXECUTE ON FUNCTION public.app_current_student_id() TO authenticated, service_role;

-- app-migration:
GRANT EXECUTE ON FUNCTION public.app_current_teacher_id() TO authenticated, service_role;

-- app-migration:
GRANT EXECUTE ON FUNCTION public.app_teacher_owns_class(integer) TO authenticated, service_role;

-- app-migration:
GRANT EXECUTE ON FUNCTION public.app_student_in_class(integer) TO authenticated, service_role;

-- app-migration:
GRANT EXECUTE ON FUNCTION public.app_can_view_class(integer) TO authenticated, service_role;
