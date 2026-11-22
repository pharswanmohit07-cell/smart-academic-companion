# Admin Unified Workspace Design

Date: 2026-11-22
Status: Approved direction; awaiting written-spec review

## Goal

Give administrators one practical workspace that reuses the existing Student and Faculty capabilities and adds a clear Users area. Avoid building a second, unrelated administration product. The work must preserve role-based access and improve the consistency of authenticated page layouts.

## User-visible behavior

### Admin navigation and workspace

- An authenticated administrator sees the common academic navigation plus the Faculty tools and an Admin-only **Users** entry.
- The administrator can open the existing student-facing academic modules (attendance, classroom finder/timetable, study planner, and student academic dashboard where applicable) and existing faculty modules (faculty dashboard, records, and class management).
- Existing Student and Faculty accounts continue to see only the navigation and routes permitted by their roles.
- Admin access is additive; it does not weaken or bypass the role checks protecting faculty and admin endpoints.
- Admin's default dashboard should be a useful combined landing view built by reusing existing dashboard data/components where practical, not a new analytics subsystem.

### Users

- The Users page lists registered accounts from the trusted user profile source already used by the application.
- Each row shows the account email, display name when available, and current role.
- Provide text search over email/name and role filtering for Student, Faculty, and Admin.
- Eligible Student accounts can be promoted to Faculty; eligible Faculty accounts can be changed to Student.
- Admin accounts, including the currently signed-in administrator, are protected from role changes in the UI and server endpoint.
- A role change requires an explicit confirmation, submits through the existing CSRF-protected role-management flow, and shows a success or failure message.
- Role changes affect authorization and dashboard routing after the account signs in again. They do not change email credentials or password.
- User listing and role updates must use authenticated server-side data and existing database abstractions; no client-side role authority or hardcoded demo account list.

## Architecture and affected areas

- `templates/base.html`: role-aware navigation and shared authenticated content layout.
- `app/views/faculty_views.py` (or the existing admin/faculty route module): admin landing route and Users route; reuse current role-management service/endpoint where possible.
- `templates/admin/users.html`: searchable/filterable account directory and confirmation UI.
- `templates/risk.html` and the current student dashboard template: reuse existing dashboard modules for Admin without duplicating business logic.
- `static/css/local-preview.css`: consistent centered content width, responsive gutters, and table/form spacing across authenticated panels.
- Tests under `tests/`: route authorization, role change safety, user filtering, admin navigation, shared layout, and dashboard rendering.

These paths are based on the current repository structure and should be rechecked against the merged main branch before implementation.

## Data and permission flow

1. The server loads the authenticated account and its trusted role.
2. Navigation is rendered from that role.
3. Admin-only routes verify the Admin role server-side before loading users or accepting role changes.
4. The Users list reads profile rows from the application's configured database backend.
5. A submitted role change validates the target profile and allowed target role on the server, blocks admin targets, updates the role and any linked faculty record consistently, and commits atomically where supported.
6. On the target user's next sign-in, the existing authentication flow reads the updated role and routes to the corresponding workspace.

## Layout and visual quality

- All authenticated panels share a centered content column with consistent horizontal gutters.
- Avoid nested containers that double the padding or force content to the viewport edges.
- Tables, forms, cards, and headings must remain readable at desktop and mobile widths.
- Preserve the existing visual theme and theme toggle.
- Verify actual rendered pages, not only static CSS strings.

## Failure handling

- If user listing fails, show a clear page-level error and do not render a misleading empty account list.
- If a role update fails, preserve the previous role and show a clear error.
- If a role update succeeds, show the saved role and instruct that the user must sign in again for the new dashboard/permissions to take effect.
- Unauthorized Student/Faculty requests to Admin-only routes must be denied by the server.

## Test and verification plan

- Unit/integration tests for admin-only route protection and allowed role changes.
- Tests that Admin cannot change their own role or another Admin's role.
- Tests that Student/Faculty accounts cannot access Users or admin-only operations.
- Tests that the Users list displays real profile records and that search/filter results match the records.
- Tests for promotion Student -> Faculty and demotion Faculty -> Student, including linked teacher-record consistency and next-login role routing.
- Regression tests for the existing Student and Faculty dashboards and all existing academic modules.
- Python test suite and C core test suite must pass.
- Run the production build/start command in the supported environment where possible.
- After deployment, verify the Render health check and exercise the Admin, Student, and Faculty flows on the live site.

## Out of scope

- A completely separate Admin Control Centre with duplicated versions of every module.
- New account creation, password resets, or email changes from Users.
- Bulk role changes, account deletion, audit-history subsystem, or fabricated activity metrics.
- Changes to Student/Faculty business logic unrelated to making their existing modules available and visually consistent for Admin.

## Open implementation checks

- Confirm the final Admin default route and dashboard composition after PR #15 is merged.
- Confirm the existing database abstraction's transaction behavior for the role update so the profile role and faculty record cannot become inconsistent.
- Confirm which student dashboard endpoint is safe and meaningful for Admin; do not grant access by removing its existing role checks.
