-- 0006_profile_rls_initplan.sql
--
-- Avoid re-evaluating auth.uid() for every row in the profile policies.
-- This preserves the exact ownership and student-only insert semantics.

-- app-migration:
DROP POLICY IF EXISTS "Users can read own profile" ON public.user_profiles;

-- app-migration:
CREATE POLICY "Users can read own profile"
    ON public.user_profiles
    FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

-- app-migration:
DROP POLICY IF EXISTS "Users can insert own student profile" ON public.user_profiles;

-- app-migration:
CREATE POLICY "Users can insert own student profile"
    ON public.user_profiles
    FOR INSERT
    TO authenticated
    WITH CHECK ((SELECT auth.uid()) = user_id AND role = 'student');
