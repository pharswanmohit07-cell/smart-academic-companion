-- 0006_profile_rls_initplan.sql
--
-- Avoid re-evaluating auth.uid() for every row in the profile policies.
-- ALTER POLICY preserves the policies installed during project bootstrap.

-- app-migration:
ALTER POLICY "Users can read own profile"
    ON public.user_profiles
    USING ((SELECT auth.uid()) = user_id);

-- app-migration:
ALTER POLICY "Users can insert own student profile"
    ON public.user_profiles
    WITH CHECK ((SELECT auth.uid()) = user_id AND role = 'student');
