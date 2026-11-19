# Deployment guide — Render + Supabase

This document is the operational checklist for the `feat/supabase-auth-render`
branch. Nothing here has been applied to the live Supabase project or to
Render yet: the steps below are meant to be run once, by you, after reviewing
the branch.

---

## 1. What is deployed

| Piece | Where |
| --- | --- |
| Web app | Render Web Service (Python, Gunicorn) |
| Credentials | Supabase Auth (GoTrue) |
| Data | Supabase PostgreSQL (`DATABASE_URL`) |
| C core | `c_core/libcore.so`, compiled in the Render build step |

The application connects to PostgreSQL as the database owner and performs its
own role/ownership checks; the RLS policies in `migrations/` protect the
Supabase API from the browser side. The service-role key is optional and only
read server-side.

## 2. Render environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `SECRET_KEY` | yes | Flask session key. `render.yaml` generates one. Never reuse the dev key. |
| `DATABASE_URL` | yes | Supabase **Session pooler** URI: `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require`. |
| `SUPABASE_URL` | yes | `https://dofildfkumoboghnrgox.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | yes | Project anon/publishable key (safe for the browser, not used there). |
| `SUPABASE_SECRET_KEY` | no | Service role. Leave empty unless a server task needs it. **Never** commit it. |
| `APP_BASE_URL` | recommended | Public URL, e.g. `https://smart-academic-companion.onrender.com`. Used for email links. (`RENDER_EXTERNAL_URL` is used automatically if unset.) |
| `FLASK_ENV` | yes | `production` |
| `FLASK_DEBUG` | yes | `0` |
| `COOKIE_SECURE` | yes | `1` |
| `ALLOWED_EMAIL_DOMAINS` | optional | e.g. `college.edu.in` to restrict sign-ups. |
| `SESSION_LIFETIME_MINUTES` | optional | Default 480. |

`DATABASE_URL`, `SUPABASE_*` and `APP_BASE_URL` are `sync: false` in
`render.yaml`, so Render asks for them in the dashboard and they never enter
Git.

## 3. Exact build and start commands

```bash
# Build (scripts/build.sh)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
gcc -std=c11 -O2 -Wall -Wextra -shared -fPIC -o c_core/libcore.so c_core/core.c
gcc -std=c11 -O2 -Wall -Wextra -o /tmp/core_tests c_core/core.c c_core/test_core.c -lm
/tmp/core_tests
python -c "import wsgi; print('ok')"

# Start
gunicorn -c gunicorn.conf.py wsgi:app
```

Health check path: `/healthz` (returns 200 with `{"status": "ok"}`; 503 if the
database is unreachable, migrations are pending, or production secrets are
missing).

## 4. First-time Supabase steps

1. **Apply migrations** from your machine (never from the browser):

   ```bash
   export DATABASE_URL='postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require'
   python manage.py migrate --status     # review
   python manage.py migrate              # apply
   python manage.py check-db             # tables, RLS, pending migrations
   ```

   Every statement is idempotent (`IF NOT EXISTS`, `CREATE OR REPLACE`,
   `DROP POLICY IF EXISTS`). Existing tables are not recreated and no column
   is dropped.

2. **Review the `user_profiles` policies** that already existed (the migration
   does not touch them):

   ```sql
   select policyname, cmd, qual, with_check
     from pg_policies where tablename = 'user_profiles';
   select has_column_privilege('authenticated', 'public.user_profiles', 'role', 'UPDATE');
   -- expected: false
   ```

3. **Auth URL configuration** (Dashboard → Authentication → URL Configuration):

   * Site URL: `https://<your-service>.onrender.com`
   * Redirect URLs: `https://<your-service>.onrender.com/auth/confirm`

4. **Email templates** (Authentication → Email Templates). The app handles both
   link styles, but the server-side token_hash form is recommended because it
   does not depend on the browser:

   * Confirm signup and Magic Link:
     `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email`
   * Reset password:
     `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=recovery`
   * Invite user:
     `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=invite`

5. **The first administrator** is created only by an explicit, operator-authorized
   step. Public registration can never grant a role.

   ```bash
   python manage.py issue-bootstrap      # prints a single-use code (once)
   python manage.py bootstrap-status     # shows whether a code is outstanding
   ```

   Then register normally at `/auth/signup` and paste the code into
   *Administrator setup code*. It promotes that one account to `admin`, only
   while `public.user_profiles` is still empty, and cannot be reused or replayed.
   Rerunning `issue-bootstrap` invalidates any unused code. The SHA-256 hash is
   stored in `public.admin_bootstrap`; the plaintext is never stored or logged.

   If you prefer not to use a code, create the account first and then:

   ```bash
   python manage.py provision-admin you@college.edu.in
   ```

6. **Faculty accounts** (there is no faculty sign-up):

   ```bash
   python manage.py provision-faculty faculty@college.edu.in --name "Dr A. Name"
   python manage.py link-student student@college.edu.in --create   # if needed
   ```

   Faculty then create and own their classes; ownership is what grants access
   to those classes' records.

## 5. Deploying on Render

```bash
# in the Render dashboard: New > Blueprint, pick this repository
# branch: feat/supabase-auth-render
```

or, without the blueprint: New Web Service → Runtime **Python**, Build
**`bash scripts/build.sh`**, Start **`gunicorn -c gunicorn.conf.py wsgi:app`**,
Health check **`/healthz`**, then add the variables from section 2.

> Render's default plan runs `chmod +x` on shell scripts only if they are
> committed as executable; if the build fails with "Permission denied", use
> `bash scripts/build.sh` as the build command.

## 6. Verifying after deploy

1. `GET /healthz` → `{"status": "ok", "database": "ok", "c_core": "ok"}`
2. Sign up with a new email → student dashboard.
3. Sign in as a provisioned faculty account → faculty dashboard.
4. Try `/faculty/admin/users` as a student → 403 page.
5. Password reset → email → new password → sign in.
6. Supabase → Advisors → Security / Performance: no new findings from
   `migrations/`.

## 7. Local SQLite data

The existing `academic_companion.db` is untouched. The PostgreSQL migrations
never read or modify it, and `manage.py` refuses to run without
`DATABASE_URL`. To move data over deliberately:

```bash
python manage.py migrate
# export rows from SQLite and import them with a script you review first;
# there is intentionally no automatic importer.
```
