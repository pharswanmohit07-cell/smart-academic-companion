# Smart Academic Companion UI Redesign Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing restrained presentation with a balanced, high-contrast, vibrant academic SaaS interface across all existing pages.

**Architecture:** Retain Flask/Jinja and Bootstrap, centralise design tokens and reusable styling in the existing shared layout, then update page-specific templates without changing route or form contracts. Keep the current theme persistence mechanism and extend UI tests to guard contrast-oriented tokens and shared component states.

**Tech Stack:** Python, Flask, Jinja2, Bootstrap 5.3, CSS, unittest, GitHub, Render.

## Global Constraints

- Light Mode remains the first-visit default; retain the `sac-theme` preference key.
- Dark Mode must remain readable and respect the saved preference.
- Preserve all routes, form names/actions, CSRF fields, Supabase authentication, roles, permissions, data operations, calculations, and C integrations.
- Do not change database schema or remove functionality.
- Use blue/cyan/violet/coral accents sparingly; never sacrifice text contrast.
- No fake metrics, emoji icons, excessive neon, gradient-heavy backgrounds, oversized pill buttons, or unnecessary animation.
- Keep responsive layouts, visible keyboard focus, and reduced-motion support.
- Work only on `feat/academic-platform-visual-redesign`; do not merge or deploy production without approval.

---

### Task 1: Shared design system and landing page preview

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/home.html` (only if page-specific style adjustments are needed)
- Modify: `tests/test_ui_theme.py`

**Interfaces:**
- Consumes: existing `data-bs-theme`, `sac-theme`, Bootstrap 5.3 classes, shared Jinja `base.html` blocks.
- Produces: shared CSS tokens and accessible styling for navigation, cards, forms, buttons, tables, alerts, badges, focus, and responsive layouts.

- [ ] Add assertions for the new light/dark token values, text contrast tokens, focus-visible styling, and retained theme toggle.
- [ ] Run `python -m unittest tests.test_ui_theme -v`; expected initial failure for the new tokens.
- [ ] Append a final override layer to the existing shared stylesheet. Use dark slate text on light surfaces and near-white text on dark surfaces; use blue for primary buttons with white text in both themes; define cyan/violet/coral as accent-only tokens.
- [ ] Preserve `sac-theme` storage and existing theme toggle JavaScript.
- [ ] Run `python -m unittest tests.test_ui_theme -v`; expected all theme contract tests pass.
- [ ] Run `python -m unittest discover -s tests -v`; expected page rendering and auth/route contracts remain green.
- [ ] Commit the independently passing shared layer.

### Task 2: Landing and authentication pages

**Files:**
- Modify: `templates/home.html`
- Modify: `templates/auth/_layout.html`
- Modify: `templates/auth/login.html`
- Modify: `templates/auth/signup.html`
- Modify: `templates/auth/forgot_password.html`
- Modify: `templates/auth/reset_password.html`
- Modify: `templates/auth/no_account.html`

**Interfaces:**
- Consumes: existing named Jinja blocks, route URLs, form fields, CSRF tokens, flash messages.
- Produces: consistent branded landing and authentication presentation with unchanged submission behaviour.

- [ ] Add/adjust page assertions for landing sections and auth form field names.
- [ ] Run focused route/auth tests and confirm assertions cover existing form contracts.
- [ ] Refine page structure and shared styles without renaming inputs, changing form methods/actions, or removing security fields.
- [ ] Run `python -m unittest tests.test_app_routes tests.test_auth_authorization -v`; expected auth and landing routes pass.
- [ ] Run the full Python suite; expected no route/auth regression.
- [ ] Commit the passing page group.

### Task 3: Student workspace pages

**Files:**
- Modify: `templates/student_dashboard.html`
- Modify: `templates/attendance.html`
- Modify: `templates/classrooms.html`
- Modify: `templates/study_planner.html`

**Interfaces:**
- Consumes: existing template context variables, form names, POST actions, route URLs, and C-backed module results.
- Produces: readable academic overview, calculator results, classroom availability, and study-plan presentation.

- [ ] Add focused render assertions for core headings, inputs, result regions, and mobile table wrappers.
- [ ] Run the existing route, attendance, classroom, and study-planner tests to establish current behaviour.
- [ ] Improve visual hierarchy, result emphasis, form grouping, status labels, and responsive table presentation while preserving every input name and output variable.
- [ ] Run `python -m unittest tests.test_attendance_calculator tests.test_classroom tests.test_study_planner -v` plus the relevant route tests; expected calculations and C wrappers remain unchanged.
- [ ] Run the full Python suite and C core assertion tests; expected all existing behaviour remains intact.
- [ ] Commit the passing student page group.

### Task 4: Faculty, admin, and error pages

**Files:**
- Modify: `templates/risk.html`
- Modify: `templates/faculty_manage.html`
- Modify: `templates/faculty_classes.html`
- Modify: `templates/admin/users.html`
- Modify: `templates/errors/400.html`
- Modify: `templates/errors/403.html`
- Modify: `templates/errors/404.html`
- Modify: `templates/errors/500.html`

**Interfaces:**
- Consumes: existing faculty/admin context variables, table data, form fields, route URLs, and role checks.
- Produces: consistent management surfaces, legible analytics and statuses, and branded error states.

- [ ] Add focused page render assertions for key management forms, tables, and error headings.
- [ ] Run faculty, class-management, authorization, and route tests to establish existing behaviour.
- [ ] Restyle faculty/admin tables, filters, student pickers, status badges, forms, and error states without altering server-side contracts.
- [ ] Run `python -m unittest discover -s tests -v`; expected all tests pass.
- [ ] Run C core tests where toolchain is available; expected assertion executable reports all tests passed.
- [ ] Commit the passing faculty/supporting page group.

## Unresolved product decisions

None block implementation. Keep page copy and information architecture unless a visual change can be made without altering the underlying workflow.
