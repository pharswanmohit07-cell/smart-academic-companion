# Deployment guide — Render + Supabase

This guide describes the current feat/supabase-auth-render branch and the
connected Supabase project. The live database migrations 0001–0010 have
already been applied and verified. The Render web service has not yet been
created; its Blueprint is prepared but its first plan must be reviewed and
approved.

---

## 1. Current deployment state

| Component | State |
| --- | --- |
| Supabase PostgreSQL schema | Migrations 0001–0009 applied |
| Auth profile and role trigger | Installed; new users default to student |
| RLS | Enabled and forced on all application tables |
| Admin bootstrap storage | RLS enabled, forced, and denied to API roles |
| Security advisor | No security findings at last check |
| Render Blueprint | Created; first sync still needs a successful plan and approval |
| Academic records | Empty; no student/faculty accounts have been created |

The application connects to PostgreSQL through a server-side DATABASE_URL.
Do not put that connection string in GitHub, browser code, screenshots, or chat.
The Supabase publishable key is not a database password; the service-role key
is not required for the normal login flow.

## 2. Render environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| SECRET_KEY | generated | Render generates a Flask session signing key. |
| DATABASE_URL | yes | Supabase Session pooler URI, SSL required. Enter it in Render's secret environment-variable field. |
| SUPABASE_URL | yes | https://dofildfkumoboghnrgox.supabase.co |
| SUPABASE_PUBLISHABLE_KEY | yes | Project publishable key. |
| SUPABASE_SECRET_KEY | no | Not needed for the normal Auth flow. |
| APP_BASE_URL | no | The app falls back to Render's RENDER_EXTERNAL_URL. |
| FLASK_ENV | set by Blueprint | production |
| FLASK_DEBUG | set by Blueprint | 0 |
| COOKIE_SECURE | set by Blueprint | 1 |
| WEB_CONCURRENCY | set by Blueprint | 1 |
| GUNICORN_THREADS | set by Blueprint | 2 |

Only DATABASE_URL is marked sync:false in render.yaml. The Supabase project
URL and publishable key are public configuration values and are preconfigured
in the Blueprint. The database password remains private and is entered only
in Render.

### Getting the database URI without sharing it with an AI agent

In Supabase Dashboard → Project Settings → Database → Connection string,
choose Session pooler and copy the URI. Use the password already set for
this database. Paste it directly into Render's DATABASE_URL field. Do not
paste it into this chat or commit it to .env.example.

Expected URI shape:

~~~
postgresql://postgres.<project-ref>:<database-password>@<session-pooler-host>:5432/postgres?sslmode=require
~~~

Use the Session pooler rather than the direct connection because Render
instances may use IPv4 and the application opens short-lived database
connections per request.

## 3. Build and start commands

The Blueprint uses:

~~~bash
bash scripts/build.sh
gunicorn -c gunicorn.conf.py wsgi:app
~~~

The build script installs Python requirements, compiles
c_core/libcore.so, runs the C tests and imports the Flask application.

Health check path: /healthz. It returns 200 only when required production
configuration, database connectivity, migrations and the C core are ready.

The Blueprint uses Render's Free plan to avoid a paid service. Free
instances can sleep while idle and have a smaller memory budget. The Gunicorn
configuration is deliberately limited to one worker and two threads, with
BLAS thread counts set to one. If the application exceeds the free instance's
memory limit during model use, the correct fix is a measured upgrade or model
memory reduction—not silently creating a paid service.

Academic data is stored in Supabase PostgreSQL, not on Render's ephemeral
filesystem, so a Render restart does not erase student records.

## 4. Supabase migrations and verification

The connected Supabase project already has all ten application migrations.
The application migration ledger records these exact files:

- 0001_initial_schema.sql
- 0002_auth_helpers.sql
- 0003_rls_policies.sql
- 0004_demo_data_flag.sql
- 0005_profile_email_and_rls_hardening.sql
- 0006_profile_rls_initplan.sql
- 0007_private_migration_ledger.sql
- 0008_fk_indexes_and_ledger_deny_policy.sql
- 0009_harden_admin_bootstrap.sql
- 0010_signup_trigger_display_name_safety.sql

After setting DATABASE_URL in Render, the startup health check verifies the
migration ledger. Do not run seed_data.py or demo_data.py against the live
database; those are for isolated demo/test databases only.

For an operator using a local shell with a privately configured
DATABASE_URL, these commands are read/verification first:

~~~bash
python manage.py migrate --status
python manage.py check-db
python scripts/verify_postgres.py --inspect
~~~

The live Supabase database currently has no Auth users and no academic rows.
Do not create demo records in the live database unless explicitly intended.

## 5. Supabase Auth URL configuration

After the Render service exists, copy its exact public URL. In Supabase
Dashboard → Authentication → URL Configuration:

- Set Site URL to the Render service root, e.g.
  https://<service-name>.onrender.com.
- Add redirect URL https://<service-name>.onrender.com/auth/confirm.

In Authentication → Email Templates, use the server-side token-hash flow.
Keep each template's surrounding HTML and replace its confirmation link:

- Confirm signup: {{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email
- Reset password: {{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=recovery
- Invite user (only if inviting faculty): {{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=invite

After saving, check that a real email's button URL starts with the Render
service's /auth/confirm?token_hash= path. If it points to the Supabase
/auth/v1/verify endpoint or ends with #access_token, the template is not
using the flow expected by this server.

## 6. First administrator and faculty accounts

Public signup always creates a student. The role is read from
public.user_profiles; the browser cannot select or update it.

The first administrator must be created by an operator. After the Render
service has its database URL, use the private operator procedure in
manage.py to issue a single-use bootstrap code, then register the first
account and enter that code. Alternatively, an operator can provision an
already registered account with:

~~~bash
python manage.py provision-admin you@college.edu.in
~~~

Faculty accounts are also provisioned by an operator, not through public
signup:

~~~bash
python manage.py provision-faculty faculty@college.edu.in --name "Dr A. Name"
~~~

Faculty can then create classes they own. Class ownership scopes their access
to student records and faculty tools.

## 7. After the first deployment

1. GET /healthz returns 200 with database and C-core status.
2. Register a student account; confirm the email and sign in.
3. Confirm the student dashboard only shows that student's records.
4. Provision a faculty account and sign in using the same login page.
5. Confirm faculty can use student-facing features and their own faculty tools.
6. Confirm a student cannot open faculty-only routes (403).
7. Test password recovery using the configured email template.
8. Re-check Supabase Security and Health advisors.

## 8. Local SQLite data

The existing local academic_companion.db is untouched. The PostgreSQL
migrations do not import it. Any transfer of local student/demo data must be a
separate, reviewed export/import operation; there is intentionally no
automatic importer.
