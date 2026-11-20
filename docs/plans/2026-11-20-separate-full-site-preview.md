# Separate Full-Site Preview Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a separate, fully navigable Smart Academic Companion preview deployment that demonstrates the approved restrained multi-colour design in light and dark themes without changing the existing live service or production data.

**Architecture:** Create an isolated Git branch from the approved feature branch, apply the semantic colour system to the existing Flask/Jinja templates, and deploy that branch to a new Render web service. The preview must use a separate Supabase development branch/database so preview actions cannot mutate production academic records; production authentication/database credentials must not be reused.

**Tech Stack:** Python 3.13, Flask 3.1, Jinja templates, Bootstrap 5.3, CSS custom properties, C11 shared library, PostgreSQL/Supabase, Render, GitHub Actions and unittest.

## Global Constraints

- Keep page backgrounds and most content surfaces neutral.
- Use colour as a functional accent, not as decoration.
- Prefer muted, coordinated shades with sufficient contrast over saturated or neon colours.
- Apply the same semantic colour meaning in light and dark themes, adjusting brightness for readability.
- Keep existing component shapes and spacing; do not introduce oversized pill buttons, glowing effects, gradient-heavy backgrounds, or excessive animation.
- Do not add decorative metrics, fake data, or emoji-based iconography.
- Preserve current information architecture, layouts, responsive behaviour, light/dark theme switcher, application workflows, and role/permission rules.
- Do not change business logic, calculations, prediction behaviour, database schema, authentication, roles, or permissions as part of the colour refinement.
- Do not merge into `main`, modify the existing production Render service, or connect the preview to the production database.
- Keep secrets out of Git. Generate a distinct Flask `SECRET_KEY` for preview and use only preview Supabase credentials.
- The existing production Render service is `smart-academic-companion-dr7t` in Singapore, using `bash scripts/build.sh` and `gunicorn -c gunicorn.conf.py wsgi:app`. The preview service must be a separate service in the same Render workspace.
- Existing repository conventions: `wsgi.py` creates the Flask app; `templates/base.html` owns shared theme CSS and navigation; `scripts/build.sh` installs requirements, compiles `c_core/libcore.so`, runs C assertions, and imports the WSGI app; Python tests run with `python -m unittest discover -s tests -v`.

---

### Task 1: Isolate preview source and data services

**Files:**
- Create branch: `preview/balanced-colour-system` (branch name, not a file)
- No application source files modified in this task.
- Preview service configuration is created in Render; Supabase branch is created in Supabase.

**Interfaces:**
- Consumes: approved code and spec on `feat/supabase-auth-render`; current production service configuration.
- Produces: isolated Git branch `preview/balanced-colour-system`; separate Supabase branch project reference and credentials; a new Render web-service identity.

- [ ] **Step 1: Establish the source baseline**

Fetch the latest head SHA of `feat/supabase-auth-render`, confirm it contains the reviewed design spec, and create `preview/balanced-colour-system` from that exact SHA. Do not branch from `main` or overwrite the existing feature branch.

- [ ] **Step 2: Verify the isolation boundary**

Confirm the new branch points to the intended base commit and that the existing PR #4 and production branch remain unchanged.

- [ ] **Step 3: Create an isolated Supabase development branch**

Request the current Supabase branch cost for the existing project before creation. If the tool reports a non-zero charge, show the exact amount and billing interval and obtain explicit cost approval before creating it. The new branch starts with schema migrations but no production user or academic records. Wait until its project status is healthy before reading connection details.

- [ ] **Step 4: Prepare preview-only environment values**

Use the development branch's `DATABASE_URL`, `SUPABASE_URL`, and `SUPABASE_PUBLISHABLE_KEY`; generate a fresh `SECRET_KEY`; set `FLASK_ENV=production`, `FLASK_DEBUG=0`, `COOKIE_SECURE=1`, `PYTHONUNBUFFERED=1`, `WEB_CONCURRENCY=1`, `GUNICORN_THREADS=2`, and `APP_BASE_URL` to the preview URL after it is assigned. If the application requires `SUPABASE_SECRET_KEY` for a server-side operation, use only a key belonging to the preview project. Never copy the production database URL, service-role key, or Flask secret.

- [ ] **Step 5: Verify the isolation configuration**

Confirm the preview Render service configuration points only to the preview Supabase project and the preview Git branch. Confirm the existing production service still points to `feat/supabase-auth-render` and the production database.

**Tests:** Inspect branch source SHA, Render service identity/branch, and preview Supabase project reference. Verify the preview environment contains the required variable names without printing secret values. No production data query or write is part of this task.

---

### Task 2: Implement the balanced semantic colour system

**Files:**
- Modify: `templates/base.html`
- Modify: only the existing module templates that need explicit semantic accent hooks, selected from the observed templates: `templates/attendance.html`, `templates/classrooms.html`, `templates/study_planner.html`, faculty dashboard/manage/classes templates, and student dashboard templates.
- Test: `tests/test_ui_theme.py`

**Interfaces:**
- Consumes: existing `data-bs-theme="light|dark"` theme attributes, Bootstrap 5.3 CSS variables, current shared base layout, and existing page templates.
- Produces: shared semantic CSS tokens for module accents and their subtle surface variants, consumed by template classes.

- [ ] **Step 1: Add focused failing UI assertions**

Extend `tests/test_ui_theme.py` to assert that both theme token sets expose attendance blue, classroom teal, study-planner amber, academic-progress green, and faculty muted-violet tokens; assert that module templates render their intended semantic class hooks. Keep the existing theme persistence, page access, and technical-copy assertions.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_ui_theme -v`

Expected: the new semantic-token and module-hook assertions fail because the current shared stylesheet uses one general accent and does not yet define the full module palette.

- [ ] **Step 3: Implement the minimum presentation changes**

In `templates/base.html`, retain the existing neutral light/dark backgrounds, surfaces, borders, typography, navigation, and theme bootstrap script. Add coordinated light/dark semantic tokens:
  - Attendance: light `#315B83`, dark `#8EAFD0`
  - Classroom Finder: light `#287D78`, dark `#72B9B0`
  - Study Planner: light `#B77932`, dark `#D7A967`
  - Academic Progress: light `#477B61`, dark `#83B69A`
  - Faculty tools: light `#765D9B`, dark `#AE9ACF`

Add subtle surface variants for each accent. Apply them to compact icon containers, section kickers, small labels, chart accents and active contextual indicators. Keep main actions consistent with the existing primary-action treatment. Use narrow module-specific template classes rather than changing whole card or page backgrounds. Do not alter route handlers, data, permissions, forms, or component hierarchy.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_ui_theme -v`

Expected: all theme/UI contract tests pass in both semantic token sets; existing landing, shared-layout and non-technical-copy assertions remain green.

- [ ] **Step 5: Run affected integration checks**

Run: `python -m unittest discover -s tests -v`

Expected: the complete Python test suite passes. Then run the repository build command `bash scripts/build.sh`; expected output includes `All C core tests passed.` and a successful WSGI application import with the C core available.

- [ ] **Step 6: Commit the passing deliverable**

Commit only the shared CSS, the minimal relevant template class changes, and focused UI tests to `preview/balanced-colour-system`.

---

### Task 3: Deploy and verify the separate full-site preview

**Files:**
- Modify: `render.yaml` only if a clearly separate preview blueprint entry is needed and can be represented without altering the existing production service definition; otherwise keep service configuration in Render.
- No production deployment files or service settings are changed.

**Interfaces:**
- Consumes: `preview/balanced-colour-system`, successful build, preview-only Supabase connection and auth configuration.
- Produces: separate Render preview service URL, live health endpoint, and a verified user-facing preview of existing application routes.

- [ ] **Step 1: Create a separate Render web service**

Create a new service in the existing Render workspace, connected to the same repository but branch `preview/balanced-colour-system`, Singapore region, Python runtime, free plan unless Render indicates that plan is unavailable, build command `bash scripts/build.sh`, start command `gunicorn -c gunicorn.conf.py wsgi:app`, and health check path `/healthz`. Do not enable or modify the production service.

- [ ] **Step 2: Configure preview-only environment**

Set the preview-only values prepared in Task 1. Set `APP_BASE_URL` to the new Render URL so auth confirmation and recovery links target the preview host. Configure Supabase Auth redirect allow-list for that preview origin only if the preview auth flow requires it; do not change production redirect settings.

- [ ] **Step 3: Deploy and verify service health**

Wait for Render's initial deploy to finish. Confirm deployment status is live, `/healthz` returns HTTP 200, logs show PostgreSQL backend and C core available, and no required environment setting is missing.

- [ ] **Step 4: Verify the complete website surface**

Check the signed-out landing page and auth pages, then verify student and faculty routes using preview-only test accounts created in the preview Supabase project. Exercise the Attendance Calculator, Classroom Finder, Study Planner and Academic Progress/faculty dashboard. Confirm role restrictions still reject unauthorized access. Inspect light and dark themes at desktop and mobile widths; check contrast, active states, forms, tables and chart accents.

- [ ] **Step 5: Confirm production remains untouched**

Re-read the existing production Render service and confirm its service ID, branch, deployment, URL, and environment configuration have not been changed. Confirm no merge to `main` occurred.

**Tests and expected outcomes:** Full Python and C build checks pass; Render deployment is live; `/healthz` returns 200; preview uses the separate database; representative student/faculty flows and both themes work; production remains on its previous service and branch.

---

## Unresolved externally observable decisions

1. **Supabase branch cost:** The development branch may incur hourly compute charges. Obtain and show the exact quoted cost; do not create the branch if non-zero cost has not been explicitly approved.
2. **Preview account onboarding:** The isolated Supabase branch will not contain production users. Preview testing therefore requires creating separate test accounts through the preview signup flow (or using an approved preview-only test-account setup); production accounts will not work on the preview.
3. **Preview service availability:** Render's free service may sleep when idle. The preview URL remains separate, but first load after inactivity may take longer.
