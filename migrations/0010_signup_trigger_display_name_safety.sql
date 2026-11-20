-- 0010_signup_trigger_display_name_safety.sql
--
-- The auth.users trigger must not use user-editable metadata, even for a
-- display-only field. The Flask signup flow fills display_name from the form
-- after Auth has created the profile. Keep this SECURITY DEFINER trigger
-- narrowly scoped and pinned to an empty search_path.

-- app-migration:
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.user_profiles (user_id, email, display_name, role)
    VALUES (NEW.id, NEW.email, '', 'student')
    ON CONFLICT (user_id) DO UPDATE
       SET email = EXCLUDED.email;
    RETURN NEW;
END;
$$;

-- app-migration:
REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
