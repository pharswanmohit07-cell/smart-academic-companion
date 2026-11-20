-- 0007_private_migration_ledger.sql
--
-- The application migration ledger is operational metadata used only by the
-- server-side DATABASE_URL connection. It must not be exposed through the
-- Supabase Data API.

-- app-migration:
CREATE TABLE IF NOT EXISTS public.app_migrations (
    filename text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- app-migration:
REVOKE ALL ON TABLE public.app_migrations FROM PUBLIC, anon, authenticated;

-- app-migration:
ALTER TABLE public.app_migrations ENABLE ROW LEVEL SECURITY;

-- app-migration:
ALTER TABLE public.app_migrations FORCE ROW LEVEL SECURITY;
