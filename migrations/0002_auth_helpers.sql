-- 0002_auth_helpers.sql
--
-- Trusted-identity helpers used by the Row Level Security policies.
--
-- * app_current_role()  - the caller's role from public.user_profiles
-- * app_current_teacher() - the caller's teachers.teacher_id, if any
-- * app_teacher_owns_class(class_id) - class-level authorization check
-- * app_can_view_class(class_id)     - admin, class owner, or a student in it
--
-- Design notes
-- ------------
-- The role is ALWAYS read from public.user_profiles, never from the JWT's
-- user_metadata: user_metadata is writable by the signed-in user, so it can
-- never be used for authorization. The project revokes UPDATE on the role
-- column from `authenticated`, and app_current_role() additionally treats
-- every role other than student/faculty/admin as "student".
--
-- All helpers are STABLE, use `SET search_path = ''` (schema-qualified
-- references only) and are SECURITY INVOKER: they read only rows the caller's
-- own RLS policies already permit (a user may always read their own profile),
-- so they cannot be used to read someone else's data. None of them writes,
-- so a caller cannot escalate to admin by calling them.
--
-- admin operations are trusted server-side only: there is deliberately no
-- policy that grants admin from the client. The Flask application performs
-- admin work with the service-role connection after checking the role in
-- Python (app/auth.py). See the notes at the end of 0003_rls_policies.sql.

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_current_role()
RETURNS text
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT COALESCE(
        (SELECT p.role FROM public.user_profiles AS p
          WHERE p.user_id = (SELECT auth.uid())),
        'student'
    );
$$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT public.app_current_role() = 'admin';
$$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_is_faculty()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT public.app_current_role() IN ('faculty', 'admin');
$$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.student_id_for(auth_user_id uuid)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT s.student_id FROM public.students AS s
     WHERE s.auth_user_id = auth_user_id;
$$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_current_student_id()
RETURNS integer
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT public.student_id_for((SELECT auth.uid()));
$$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_current_teacher_id()
RETURNS integer
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT t.teacher_id FROM public.teachers AS t
     WHERE t.auth_user_id = (SELECT auth.uid());
$$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_teacher_owns_class(target_class_id integer)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.faculty_classes AS c
         WHERE c.class_id = target_class_id
           AND c.owner_teacher_id = public.app_current_teacher_id()
    );
$$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_student_in_class(target_class_id integer)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.students AS s
         WHERE s.class_id = target_class_id
           AND s.auth_user_id = (SELECT auth.uid())
    );
$$;

-- app-migration:
CREATE OR REPLACE FUNCTION public.app_can_view_class(target_class_id integer)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT public.app_is_admin()
        OR public.app_teacher_owns_class(target_class_id)
        OR public.app_student_in_class(target_class_id);
$$;

-- Helpers are not client API surface: only the policies call them.
-- app-migration:
REVOKE ALL ON FUNCTION public.app_current_role() FROM PUBLIC;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_is_admin() FROM PUBLIC;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_is_faculty() FROM PUBLIC;

-- app-migration:
REVOKE ALL ON FUNCTION public.student_id_for(uuid) FROM PUBLIC;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_current_student_id() FROM PUBLIC;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_current_teacher_id() FROM PUBLIC;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_teacher_owns_class(integer) FROM PUBLIC;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_student_in_class(integer) FROM PUBLIC;

-- app-migration:
REVOKE ALL ON FUNCTION public.app_can_view_class(integer) FROM PUBLIC;

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
