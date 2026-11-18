-- 0004_demo_data_flag.sql
--
-- Marks students that came from the demonstration seed script so demo data is
-- always separable from real academic records. Nothing is deleted or retyped
-- here; the only index added is a partial unique index on non-NULL emails.
--
-- Removing demo data later (run only after checking the counts):
--
--   SELECT COUNT(*) FROM public.students WHERE is_demo_data;
--   DELETE FROM public.students WHERE is_demo_data;
--
-- seed_data.py refuses to run against a PostgreSQL DATABASE_URL (the deployed
-- project) unless SEED_ALLOW_PRODUCTION=1 is set explicitly.

-- app-migration:
ALTER TABLE students ADD COLUMN IF NOT EXISTS is_demo_data boolean NOT NULL DEFAULT false;

-- app-migration:
COMMENT ON COLUMN students.is_demo_data IS
    'True for rows created by seed_data.py so demonstration data can be identified and removed.';
