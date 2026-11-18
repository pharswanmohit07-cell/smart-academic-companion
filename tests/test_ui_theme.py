"""UI contract tests: theme handling and user-facing (non-technical) copy.

These tests guard the presentation layer only. They never call the risk
model or the C library, so they stay fast and do not need a database.
"""

import unittest

from app import app

PAGES = [
    "/",
    "/attendance",
    "/classrooms",
    "/study-planner",
    "/risk",
    "/faculty/manage",
    "/faculty/classes",
]

# Implementation words that must not reach students or faculty.
TECHNICAL_TERMS = [
    b"min-heap",
    b"max-heap",
    b"greedy",
    b"ctypes",
    b"logistic regression",
    b"StandardScaler",
    b"priority score",
    b"100 \xe2\x88\x92 mastery",  # "100 − mastery"
    b"C interval library",
]


class TestThemeIsCentralised(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_every_page_extends_the_shared_layout(self):
        for path in PAGES:
            with self.subTest(path=path):
                body = self.client.get(path).data
                # One navbar, one theme toggle, one theme script per page.
                self.assertEqual(body.count(b'id="theme-toggle"'), 1, path)
                self.assertEqual(body.count(b"sac-theme"), 2, path)

    def test_light_is_the_default_and_resolved_before_paint(self):
        body = self.client.get("/").data
        # The <html> element starts light and the head script runs first.
        self.assertIn(b'<html lang="en" data-bs-theme="light">', body)
        head = body.split(b"</head>")[0]
        self.assertIn(b'localStorage.getItem(THEME_KEY) === "dark"', head)
        # The stored value is the only input; the OS preference is ignored.
        self.assertNotIn(b"matchMedia", body)
        self.assertNotIn(b"prefers-color-scheme", body)

    def test_theme_toggle_is_accessible(self):
        body = self.client.get("/").data
        self.assertIn(b'aria-label="Switch to dark mode"', body)
        self.assertIn(b'aria-pressed="false"', body)

    def test_light_theme_uses_the_requested_palette(self):
        body = self.client.get("/").data.decode("utf-8")
        for colour in ("#f5f6f8", "#ffffff", "#2563eb", "#1f2937", "#64748b", "#e5e7eb"):
            self.assertIn(colour, body.lower())

    def test_dark_theme_uses_the_requested_palette(self):
        body = self.client.get("/").data.decode("utf-8")
        for colour in ("#111827", "#1f2937", "#273449", "#f3f4f6", "#cbd5e1", "#374151"):
            self.assertIn(colour, body.lower())

    def test_tables_and_forms_follow_the_theme(self):
        css = self.client.get("/").data.decode("utf-8")
        # Overrides must exist for the components the pages actually use.
        for selector in (".table", ".form-control", ".form-select", ".alert", ".btn-primary",
                         ".list-group-item", ".badge"):
            self.assertIn(selector, css)

    def test_toggle_is_present_in_the_mobile_collapse_menu(self):
        body = self.client.get("/").data
        collapse = body.split(b'id="mainNavigation"')[1]
        self.assertIn(b'id="theme-toggle"', collapse)


class TestPagesAreNotTechnical(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_no_implementation_jargon_renders(self):
        for path in PAGES:
            body = self.client.get(path).data.lower()
            for term in TECHNICAL_TERMS:
                with self.subTest(path=path, term=term):
                    self.assertNotIn(term.lower(), body, f"{path} leaks {term!r}")

    def test_study_planner_uses_friendly_labels(self):
        body = self.client.get("/study-planner").data
        self.assertIn(b"Create a study plan based on your topics", body)
        self.assertIn(b"Preparation level", body)
        self.assertIn(b"Generate Study Plan", body)

    def test_dashboard_uses_short_guidance_note(self):
        body = self.client.get("/risk").data
        self.assertIn(b"View student performance, attendance and academic records.", body)

    def test_home_page_describes_what_the_student_can_do(self):
        body = self.client.get("/").data
        self.assertIn(b"AI Study Planner", body)
        self.assertIn(b"how prepared you feel", body)


if __name__ == "__main__":
    unittest.main()
