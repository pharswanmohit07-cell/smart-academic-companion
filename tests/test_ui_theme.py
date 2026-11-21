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
        self.assertIn(b"--app-accent: #155eef", response.data)

    def test_light_theme_uses_the_requested_palette(self):
        css = self.stylesheet().decode("utf-8")
        for colour in ("#f3f6fb", "#ffffff", "#155eef", "#172033", "#526176", "#d5deea"):
            self.assertIn(colour, css.lower())

    def test_dark_theme_uses_the_requested_palette(self):
        css = self.stylesheet().decode("utf-8")
        for colour in ("#0b1220", "#121d30", "#192840", "#f4f7ff", "#c0cadb", "#30415d"):
            self.assertIn(colour, css.lower())

    def test_text_contrast_and_focus_states_are_explicit(self):
        css = self.stylesheet().decode("utf-8")
        for token in ("--app-text: #172033", "--app-text-muted: #526176",
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


    def test_landing_background_bleeds_to_both_viewport_edges(self):
        css = self.stylesheet().decode("utf-8")
        landing_rule = css[css.index(".app-main-landing > .landing-page {"):]
        self.assertIn("width: 100vw;", landing_rule)
        self.assertIn("left: 50%;", landing_rule)
        self.assertIn("margin-left: -50vw;", landing_rule)
        self.assertIn("linear-gradient(115deg", landing_rule)

    def test_landing_page_has_a_complete_product_story(self):
        body = self.landing_page()
        for section in (b"landing-hero", b"product-preview", b"workflow-section",
                        b"student-tools-section", b"faculty-tools-section",
                        b"landing-footer"):
            with self.subTest(section=section):
                self.assertIn(section, body)

    def test_shared_layout_uses_the_refined_design_system(self):
        body = self.page("/attendance")
        css = self.stylesheet()
        self.assertIn(b"local-preview.css?v=20261120", body)
        for selector in (b"--app-accent: #155eef", b".app-main",
                         b".section-kicker", b".page-heading",
                         b".auth-shell"):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)

    def test_theme_script_persists_selected_preference(self):
        body = self.page("/attendance")
        self.assertIn(b'window.localStorage.setItem(THEME_KEY, next)', body)
        self.assertIn(b'button.addEventListener("click"', body)




if __name__ == "__main__":
    unittest.main()
