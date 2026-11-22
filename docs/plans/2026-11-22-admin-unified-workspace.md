# Admin Unified Workspace Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Admin a dedicated combined workspace and safe searchable user-role management while keeping Student and Faculty permissions intact.

**Architecture:** Extend the existing Flask role-routing model with an Admin-specific dashboard route and role-aware navigation. Keep Admin user operations server-side in the existing Faculty/Admin views and database abstraction, strengthen role transitions so profile and teacher links stay consistent, and reuse the existing academic pages rather than duplicating their business logic. Improve the shared authenticated layout and verify the rendered Admin, Faculty, and Student experiences with the existing SQLite-backed test harness.

**Tech Stack:** Python 3, Flask, Jinja templates, existing database abstraction (SQLite tests and Supabase PostgreSQL production), Bootstrap 5, CSS, unittest, GitHub Actions, Render.

## Global Constraints

- Admin access is additive; it does not weaken or bypass the role checks protecting faculty and admin endpoints.
- Existing Student and Faculty accounts continue to see only the navigation and routes permitted by their roles.
- Admin's default dashboard is a useful combined landing view built by reusing existing dashboard data/components where practical, not a new analytics subsystem.
- The Users page reads registered accounts from the trusted profile source and shows email, display name when available, and role.
- Provide text search over email/name and role filtering for Student, Faculty, and Admin.
- Eligible Student accounts can be promoted to Faculty; eligible Faculty accounts can be changed to Student.
- Admin accounts, including the currently signed-in administrator, are protected from role changes in both UI and server endpoint.
- Role changes require explicit confirmation, use the existing CSRF-protected flow, and show success/failure feedback.
- Role changes affect authorization and dashboard routing after the account signs in again; they do not change email credentials or password.
- Profile role and linked teacher record must remain consistent in one database transaction.
- Never render fabricated users, activity metrics, or demo-account records as if they were real.
- Preserve the existing visual theme and theme toggle; authenticated panels use one centered content shell without nested gutters.
- Keep production Render service and production database untouched until the user reviews and approves the preview.

---

### Task 1: Add Admin-specific dashboard routing and role-aware navigation

**Files:**
- Modify: `app/auth.py`
- Modify: `templates/base.html`
- Modify: `wsgi.py` only if a new blueprint is required (prefer the existing Faculty blueprint for the first implementation)
- Test: `tests/test_admin_workspace.py` (create)

**Interfaces:**
- Existing `dashboard_endpoint(account)` remains the single role-to-dashboard resolver.
- Admin dashboard endpoint: `faculty.admin_dashboard`, protected by `@auth_module.admin_required`.
- Existing `faculty.dashboard`, `faculty.manage`, and `faculty.classes` remain available to Faculty and Admin under their current decorators.

- [ ] **Step 1: Add focused failing tests**

Create Admin, Faculty, and Student accounts using `TempDatabaseMixin` and `FakeAuthState`. Assert:
1. `auth.dashboard_endpoint(admin_account)` returns `faculty.admin_dashboard`.
2. Faculty resolves to `faculty.dashboard`; Student resolves to `student.dashboard`.
3. Signed-in Admin GET `/faculty/admin` returns 200.
4. Signed-in Student and Faculty GET `/faculty/admin` are denied (403).
5. Admin navigation includes Faculty Dashboard, Manage Records, Manage Classes, and Users; Faculty navigation excludes Users; Student navigation excludes all Faculty/Admin links.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_admin_workspace`
Expected: the new routing and navigation assertions fail because the Admin dashboard endpoint and Admin navigation do not yet exist.

- [ ] **Step 3: Implement the minimum behavior**

In `app/auth.py`, check `account.is_admin` before `account.is_faculty` in `dashboard_endpoint` and return `faculty.admin_dashboard`. In `app/views/faculty_views.py`, add GET `/admin` with `@auth_module.admin_required`; render a dedicated `admin/dashboard.html` template with links to the existing academic tools and faculty modules. The dashboard may show only real profile/class counts obtained from the configured database; omit a metric if its query cannot be supported. In `templates/base.html`, show Faculty links to Faculty and Admin, and show Users only to Admin. Keep common academic tools visible to all authenticated users as they are now.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_admin_workspace`
Expected: routing, authorization, and role-specific navbar tests pass.

- [ ] **Step 5: Run the affected integration check**

Run: `python -m unittest tests.test_auth_flow tests.test_ui_theme tests.test_admin_workspace`
Expected: existing sign-in routing and shared theme tests pass alongside the new Admin tests. If the actual existing auth test module uses a different filename, run the repository's matching discovered test module instead and record the exact command.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add app/auth.py app/views/faculty_views.py templates/base.html templates/admin/dashboard.html tests/test_admin_workspace.py
git commit -m "feat: add dedicated admin workspace"
```

---

### Task 2: Make the Admin Users directory searchable and safe to update

**Files:**
- Modify: `app/views/faculty_views.py`
- Modify: `templates/admin/users.html`
- Test: `tests/test_admin_workspace.py`

**Interfaces:**
- GET `/faculty/admin/users` remains the Users directory route and remains protected by `@auth_module.admin_required`.
- POST `/faculty/admin/set-role` remains the role update endpoint and remains protected by `@auth_module.admin_required` and global CSRF validation.
- Query parameters: `q` for email/name search and `role` for one of `all|student|faculty|admin`.

- [ ] **Step 1: Add focused failing tests**

Assert:
1. Admin sees only profile rows matching case-insensitive substring search in email or display name.
2. Role filter returns only the selected role; invalid role filter safely falls back to all roles.
3. Student and Faculty receive 403 for both GET Users and POST role update.
4. Admin cannot change their own role, another Admin's role, or submit an unsupported role.
5. Student -> Faculty creates/links exactly one teacher row for the target auth user; Faculty -> Student clears that row's `auth_user_id` without deleting the teacher record or changing credentials.
6. A failed database operation leaves the profile role and teacher link unchanged.
7. A valid change displays a success message and explains that the target account must sign in again.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_admin_workspace`
Expected: search/filter tests fail because the route currently returns every profile; transition failure tests expose any inconsistent or insufficiently guarded role-update behavior.

- [ ] **Step 3: Implement the minimum behavior**

Add parameterized SQL conditions to the profile query using the existing database placeholder abstraction. Normalize and validate `q` and `role`; never concatenate user input into SQL. Include `user_id` and current role in the target lookup. Reject self-targeting by user ID and reject every target whose current role is Admin. Permit only Student <-> Faculty transitions. Keep profile update and teacher insert/link or unlink on the same connection and commit only after both succeed; explicitly roll back on a caught database failure. Retain the existing CSRF protection. Add a browser confirmation prompt to each eligible role-change form and preserve the selected search/filter query after POST redirects. The page-level error must be distinct from an empty result set.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_admin_workspace`
Expected: search, filtering, access control, confirmation markup, allowed transitions, protected Admin records, and failure rollback tests pass.

- [ ] **Step 5: Run the affected integration check**

Run: `python -m unittest discover -s tests`
Expected: the full Python suite passes, including auth, Faculty ownership, Student isolation, and role update regression tests.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add app/views/faculty_views.py templates/admin/users.html tests/test_admin_workspace.py
git commit -m "feat: add searchable admin user management"
```

---

### Task 3: Improve Admin dashboard composition and consistent panel layout

**Files:**
- Create: `templates/admin/dashboard.html`
- Modify: `templates/admin/users.html`
- Modify: `templates/risk.html` only if rendered evidence shows the existing faculty dashboard needs a targeted spacing correction
- Modify: `templates/student_dashboard.html` only if rendered evidence shows the existing student dashboard needs a targeted spacing correction
- Modify: `static/css/local-preview.css`
- Test: `tests/test_admin_workspace.py`
- Test: `tests/test_ui_theme.py`

**Interfaces:**
- `admin/dashboard.html` receives only server-derived profile/class counts and named route URLs.
- The shared authenticated content shell remains `.app-content-shell` from PR #15.
- No duplicate student/faculty business logic or fabricated dashboard values.

- [ ] **Step 1: Add focused failing tests**

Assert Admin dashboard contains a clear welcome/overview, real account/class counts, and links to Attendance, Classrooms, Study Planner, Faculty Dashboard, Manage Records, Manage Classes, and Users. Assert Admin Users search/filter controls have labels and retain selected values. Assert all Admin pages have one shared content shell and no nested dashboard shell. Add responsive CSS contract checks for directory controls and table wrapping.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_admin_workspace tests.test_ui_theme`
Expected: dashboard/template assertions fail until the Admin landing page and controls are implemented.

- [ ] **Step 3: Implement the minimum behavior**

Build the Admin dashboard from real profile and faculty-class counts plus clear links to existing modules. Keep the Admin page compact and action-oriented; do not add a new chart or duplicate the Faculty risk dashboard. Add a labeled search input and role select to the Users page, an explicit confirmation step, and responsive table controls. Use the current design tokens and spacing conventions in `static/css/local-preview.css`; avoid one-off nested max-width wrappers because PR #15 supplies the common shell. Only adjust Faculty/Student templates where actual rendered page inspection shows a concrete alignment or spacing defect.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_admin_workspace tests.test_ui_theme`
Expected: Admin page, shared-shell, theme, navigation, and responsive contract tests pass.

- [ ] **Step 5: Run the affected integration check**

Run: `python -m unittest discover -s tests`
Expected: all Python tests pass. Also run `bash scripts/build.sh` in a Linux-compatible environment to verify Python imports and the C shared library build/tests.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add templates/admin/dashboard.html templates/admin/users.html templates/risk.html templates/student_dashboard.html static/css/local-preview.css tests/test_admin_workspace.py tests/test_ui_theme.py
git commit -m "style: refine admin and academic panel layouts"
```

---

### Task 4: Build and publish an isolated preview for user review

**Files:**
- Modify: `docs/specs/2026-11-22-admin-unified-workspace-design.md` only if implementation reveals a necessary approved clarification.
- Create: `docs/plans/2026-11-22-admin-unified-workspace.md` (this plan)
- No production service or production database changes.

**Interfaces:**
- Preview is a separate Render web service on the free plan, pointed at the feature branch.
- Production Render service `srv-dbvinhff3r2c73cc2830` remains on `main`.
- Preview must use a separate non-production data source and must not receive production database credentials.

- [ ] **Step 1: Add preview configuration only after feature tests pass**

Inspect the existing preview service and environment configuration. Reuse a pre-existing isolated preview service only if it can be safely assigned to this feature branch without affecting another active preview. Otherwise create a separate free Render web service with the repository, branch, build command `bash scripts/build.sh`, and start command `gunicorn -c gunicorn.conf.py wsgi:app`. Do not copy production secrets or connect the preview to production Supabase/Postgres.

- [ ] **Step 2: Verify the preview data boundary**

Expected: preview environment has no production `DATABASE_URL`, Supabase auth keys, or production `SECRET_KEY`. If a safe isolated login/demo data setup cannot be configured without secrets or exposing seeded credentials, stop and report the blocker rather than publishing an insecure preview.

- [ ] **Step 3: Verify the deployed preview**

Check Render deploy status, `/healthz`, sign-in, Admin dashboard, Users search/filter, role-change flow with disposable preview accounts, Faculty dashboard, Student dashboard, Attendance, Classrooms, and Study Planner. Verify that role updates in preview do not affect production.

- [ ] **Step 4: Commit the review handoff**

```bash
git add docs/plans/2026-11-22-admin-unified-workspace.md
git commit -m "docs: add admin workspace implementation plan"
```

---

### Task 5: Production handoff after explicit preview approval

**Files:**
- Merge the reviewed feature pull request into `main` only after the user explicitly approves the preview.
- No production credentials or production database schema changes are included in this feature.

- [ ] **Step 1: Verify final branch checks**

Run: `python -m unittest discover -s tests` and `bash scripts/build.sh`; verify GitHub Actions Python and C checks pass.

- [ ] **Step 2: Merge only after approval**

Keep the preview branch available until the user approves it. After approval, merge the feature PR and confirm Render deploys `main`.

- [ ] **Step 3: Verify production**

Check the production Render deployment and `https://smart-academic-companion-dr7t.onrender.com/healthz`; verify Admin, Faculty, Student, and academic tool access. Confirm no preview-only credentials or configuration reached production.
