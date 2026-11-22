"""UI contract tests: theme handling and user-facing (non-technical) copy.

These tests guard the presentation layer only. They never call the risk
model or the C library directly, so they stay fast.

Ported to the application factory: every page now requires a signed-in user,
and the faculty pages require the faculty role, so the client signs in as a
faculty account that owns one class. The page-level assertions are unchanged.
"""

import unittest

from tests.support import FakeAuthState, TempDatabaseMixin

# Pages every signed-in user can open, plus the faculty-only pages.
# ``/`` itself redirects a signed-in user to their dashboard, so it is tested
# separately as the signed-out landing page.
SHARED_PAGES = ["/attendance", "/classrooms", "/study-planner"]
FACULTY_PAGES = ["/faculty/dashboard", "/faculty/manage", "/faculty/classes"]
PAGES = SHARED_PAGES + FACULTY_PAGES

# Implementation words that must not reach students or faculty.
TECHNICAL_TERMS = [
    b"min-heap",
    b"max-heap",
    b"greedy",
    b"ctypes",
    b"logistic regression",
    b"StandardScaler",
    b"priority score",
    "100 − mastery".encode("utf-8"),
    b"C interval library",
]


class ThemeTestBase(TempDatabaseMixin):
    def stylesheet(self):
        response = self.client.get("/static/css/local-preview.css")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data)
        self.assertEqual(response.mimetype, "text/css")
        data = response.data
        response.close()
        return data
    def setUp(self):
        super().setUp()
        import wsgi

        self.fake = FakeAuthState.current
        self.app = wsgi.create_app()
        self.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = self.app.test_client()

        # Each test signs in itself so a test can inspect the signed-out page.
        user_id = self.fake.add_user("faculty@example.com", "secret-pass-1")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO user_profiles (user_id, email, display_name, role) "
                "VALUES (?, 'faculty@example.com', 'Faculty', 'faculty')",
                (user_id,),
            )
            connection.execute(
                "INSERT INTO teachers (auth_user_id, name, email) "
                "VALUES (?, 'Faculty', 'faculty@example.com')",
                (user_id,),
            )
            connection.commit()
            teacher_id = connection.execute(
                "SELECT teacher_id FROM teachers WHERE auth_user_id = ?", (user_id,)
            ).fetchone()["teacher_id"]
            connection.execute(
                """INSERT INTO faculty_classes
                       (class_name, program, semester, section, description,
                        owner_teacher_id)
                   VALUES ('Theme Class', 'Program', 3, 'A', '', ?)""",
                (teacher_id,),
            )
            connection.commit()

    def sign_in(self):
        token = "ui-theme-token"
        with self.client.session_transaction() as session:
            session["csrf_token"] = token
        response = self.client.post("/auth/login", data={
            "email": "faculty@example.com", "password": "secret-pass-1",
            "csrf_token": token,
        })
        self.assertIn(response.status_code, (301, 302, 303))
        return self.client

    def page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.data

    def landing_page(self):
        """The signed-out home page (``/`` redirects signed-in users)."""
        client = self.app.test_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        return response.data


class TestThemeIsCentralised(ThemeTestBase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.sign_in()

    def test_every_page_extends_the_shared_layout(self):
        for path in PAGES:
            with self.subTest(path=path):
                body = self.page(path)
                # One navbar, one theme toggle, one theme script per page.
                self.assertEqual(body.count(b'id="theme-toggle"'), 1, path)
                self.assertEqual(body.count(b"sac-theme"), 2, path)

    def test_light_is_the_default_and_resolved_before_paint(self):
        body = self.page("/attendance")
        # The <html> element starts light and the head script runs first.
        self.assertIn(b'<html lang="en" data-bs-theme="light">', body)
        head = body.split(b"</head>")[0]
        self.assertIn(b'localStorage.getItem(THEME_KEY) === "dark"', head)
        # The stored value is the only input; the OS preference is ignored.
        self.assertNotIn(b"matchMedia", body)
        self.assertNotIn(b"prefers-color-scheme", body)

    def test_theme_toggle_is_accessible(self):
        body = self.page("/attendance")
        self.assertIn(b'aria-label="Switch to dark mode"', body)
        self.assertIn(b'aria-pressed="false"', body)

    def test_static_stylesheet_is_served_as_nonempty_css(self):
        with self.app.test_request_context():
            stylesheet_url = self.app.url_for("static", filename="css/local-preview.css")
        self.assertEqual(stylesheet_url, "/static/css/local-preview.css")
        response = self.client.get(stylesheet_url)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 1000)
        self.assertEqual(response.mimetype, "text/css")
        self.assertIn(b"Smart Academic Companion", response.data)
        self.assertIn(b"--app-accent: #F29A52", response.data)

    def test_light_theme_uses_the_requested_palette(self):
        css = self.stylesheet().decode("utf-8")
        for colour in ("#fff1df", "#f8e9d8", "#f29a52", "#34263f", "#66556a", "#ffd1a3"):
            self.assertIn(colour, css.lower())

    def test_apricot_light_and_original_navy_dark_themes_are_separate(self):
        css = self.stylesheet().decode("utf-8").lower()
        base = self.landing_page().lower()
        for token in ("--app-bg: #fff1df", "--app-surface: #f8e9d8",
                      "--app-accent: #f29a52"):
            self.assertIn(token, css)
        for token in ("--app-bg: #0b1220", "--app-surface: #121d30",
                      "--app-accent: #8bb4ff", "--app-cyan: #67d5df",
                      "--app-violet: #c2a7ff"):
            self.assertIn(token, css)
        self.assertIn(b"--app-bg: #0b1220", base)
        self.assertIn(b"--app-bg: #fff1df", base)

    def test_dark_theme_uses_the_original_navy_palette(self):
        css = self.stylesheet().decode("utf-8")
        for colour in ("#0b1220", "#121d30", "#192840", "#30415d",
                       "#f4f7ff", "#c0cadb", "#8bb4ff", "#67d5df", "#c2a7ff"):
            self.assertIn(colour, css.lower())

    def test_text_contrast_and_focus_states_are_explicit(self):
        css = self.stylesheet().decode("utf-8").lower()
        for token in ("--app-text: #34263f", "--app-text-muted: #66556a",
                      "--app-text: #f4f7ff", "--app-text-muted: #c0cadb",
                      ":focus-visible", "outline: 3px solid var(--app-cyan)",
                      "--bs-btn-color: #fff"):
            with self.subTest(token=token):
                self.assertIn(token, css)

    def test_tables_and_forms_follow_the_theme(self):
        css = self.stylesheet().decode("utf-8")
        # Shared stylesheet rules cover the components used across templates.
        for selector in (".table", ".form-control", ".form-select", ".alert", ".btn-primary",
                         ".list-group-item", ".badge"):
            self.assertIn(selector, css)

    def test_toggle_is_present_in_the_mobile_collapse_menu(self):
        body = self.page("/attendance")
        collapse = body.split(b'id="mainNavigation"')[1]
        self.assertIn(b'id="theme-toggle"', collapse)


class TestPagesAreNotTechnical(ThemeTestBase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.sign_in()

    def test_no_implementation_jargon_renders(self):
        for path in PAGES:
            body = self.page(path).lower()
            for term in TECHNICAL_TERMS:
                with self.subTest(path=path, term=term):
                    self.assertNotIn(term.lower(), body, f"{path} leaks {term!r}")

    def test_study_planner_uses_friendly_labels(self):
        body = self.page("/study-planner")
        self.assertIn(b"Create a study plan based on your topics", body)
        self.assertIn(b"Preparation level", body)
        self.assertIn(b"Generate Study Plan", body)

    def test_dashboard_uses_short_guidance_note(self):
        body = self.page("/faculty/dashboard")
        self.assertIn(b"View student performance, attendance and academic records.", body)

    def test_home_page_describes_what_the_student_can_do(self):
        # Visitors who are not signed in get the landing page at ``/``.
        body = self.landing_page()
        self.assertIn(b"AI Study Planner", body)
        self.assertIn(b"how prepared you feel", body)


    def test_landing_brand_and_showcase_use_the_refined_identity(self):
        body = self.landing_page()
        self.assertIn(b'class="brand-name">Smart Academic Companion</span>', body)
        self.assertNotIn(b'class="brand-mark"', body)
        self.assertIn(b'class="workspace-showcase"', body)
        self.assertIn(b'Four tools.', body)
        for label in (b'Attendance', b'Classroom finder', b'Study planner', b'Academic progress'):
            self.assertIn(label, body)

    def test_landing_page_has_a_complete_product_story(self):
        body = self.landing_page()
        for section in (b"landing-hero", b"workspace-showcase", b"workflow-section",
                        b"student-tools-section", b"faculty-tools-section",
                        b"landing-footer"):
            with self.subTest(section=section):
                self.assertIn(section, body)

    def test_auth_pages_do_not_show_internal_faculty_provisioning_copy(self):
        for path in ("/auth/login", "/auth/signup"):
            body = self.client.get(path).data.lower()
            for phrase in (b"faculty accounts are created by an administrator",
                           b"faculty access is provisioned by an administrator"):
                with self.subTest(path=path, phrase=phrase):
                    self.assertNotIn(phrase, body)

    def test_dark_mode_uses_warm_terracotta_surfaces_and_plum_navy_accents(self):
        css = self.stylesheet().decode("utf-8").lower()
        for token in ("--app-bg: #0b1220", "--app-surface: #121d30",
                      "--app-surface-muted: #192840", "--app-accent: #8bb4ff",
                      "--app-accent-soft: #1c3153"):
            with self.subTest(token=token):
                self.assertIn(token, css)

    def test_login_has_no_separate_faculty_entry(self):
        response = self.app.test_client().get("/auth/login")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Faculty access", response.data)
        self.assertIn(b"Forgot your password?", response.data)
        self.assertIn(b"Create an account", response.data)

    def test_auth_forms_keep_student_and_faculty_on_the_same_sign_in(self):
        anonymous = self.app.test_client()
        login = anonymous.get("/auth/login").data
        signup = anonymous.get("/auth/signup").data
        self.assertIn(b"Sign in to continue", login)
        self.assertIn(b"Create your student account", signup)
        self.assertNotIn(b'name="role"', signup)
        self.assertIn(b"auth-workspace-preview", login)
        self.assertIn(b"auth-workspace-preview", signup)

    def test_shared_layout_uses_the_refined_design_system(self):
        body = self.page("/attendance")
        css = self.stylesheet()
        self.assertIn(b"local-preview.css?v=20261122-all-panels-shell-v1", body)
        for selector in (b"--app-accent: #F29A52", b".app-main",
                         b".section-kicker", b".page-heading",
                         b".auth-shell"):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)

    def test_all_signed_in_panels_use_a_shared_centered_content_shell(self):
        for path in PAGES:
            with self.subTest(path=path):
                body = self.page(path)
                self.assertIn(b'class="app-content-shell"', body)
        # The signed-out landing page is intentionally outside the workspace shell.
        self.assertNotIn(b'class="app-content-shell"', self.landing_page())
        css = self.stylesheet().decode("utf-8")
        self.assertIn(".app-content-shell {", css)
        self.assertIn("width: min(100%, 1480px)", css)
        self.assertIn("margin-inline: auto", css)
        self.assertIn("padding-inline: clamp(1rem, 3.2vw, 2.75rem)", css)

    def test_student_dashboard_uses_shared_panel_shell_without_nested_gutters(self):
        source, _, _ = self.app.jinja_env.loader.get_source(
            self.app.jinja_env, "student_dashboard.html"
        )
        self.assertNotIn('<div class="dashboard-shell">', source)
        # This test client is signed in as faculty, so /dashboard correctly
        # redirects to the faculty dashboard. The student template contract
        # is checked above; the shared shell is verified on rendered panels.
        body = self.page("/faculty/dashboard")
        self.assertIn(b'class="app-content-shell"', body)
        css = self.stylesheet().decode("utf-8")
        self.assertIn(".app-content-shell {", css)
        self.assertIn("width: min(100%, 1480px)", css)
        self.assertIn("padding-inline: clamp(1rem, 3.2vw, 2.75rem)", css)
        self.assertIn("@media (max-width: 767.98px)", css)

    def test_theme_script_persists_selected_preference(self):
        body = self.page("/attendance")
        self.assertIn(b'window.localStorage.setItem(THEME_KEY, next)', body)
        self.assertIn(b'button.addEventListener("click"', body)




if __name__ == "__main__":
    unittest.main()
