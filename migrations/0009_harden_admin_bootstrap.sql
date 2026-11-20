-- 0009_harden_admin_bootstrap.sql
--
-- The one-time administrator bootstrap code is created lazily by the
-- application on older installations. Create it up front and ensure that the
-- public Supabase Data API cannot read or modify its hash.

-- app-migration:
CREATE TABLE IF NOT EXISTS public.admin_bootstrap (
    id integer PRIMARY KEY CHECK (id = 1),
    code_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at timestamptz,
    claimed_by uuid
);

-- app-migration:
ALTER TABLE public.admin_bootstrap ENABLE ROW LEVEL SECURITY;

-- app-migration:
ALTER TABLE public.admin_bootstrap FORCE ROW LEVEL SECURITY;

-- app-migration:
REVOKE ALL ON TABLE public.admin_bootstrap FROM PUBLIC, anon, authenticated;

-- app-migration:
DROP POLICY IF EXISTS admin_bootstrap_deny_clients ON public.admin_bootstrap;

-- app-migration:
CREATE POLICY admin_bootstrap_deny_clients
    ON public.admin_bootstrap
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);
