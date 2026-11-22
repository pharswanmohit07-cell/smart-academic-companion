"""Every mutating HTML form must send the session-bound CSRF token."""

import re
import unittest
from pathlib import Path


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates"
FORM_PATTERN = re.compile(r"<form\\b(?P<attributes>[^>]*)>(?P<body>.*?)</form\\s*>", re.I | re.S)
POST_METHOD = re.compile(r"""\\bmethod\\s*=\\s*["']?post["']?\\b""", re.I)
CSRF_FIELD = re.compile(r"""name\\s*=\\s*["']csrf_token["']""", re.I)


class TestCsrfTemplateCoverage(unittest.TestCase):
    def test_every_post_form_includes_session_csrf_token(self):
        missing = []
        checked = 0
        for template in sorted(TEMPLATE_ROOT.rglob("*.html")):
            source = template.read_text(encoding="utf-8")
            for number, match in enumerate(FORM_PATTERN.finditer(source), start=1):
                attributes = match.group("attributes")
                body = match.group("body")
                if not POST_METHOD.search(attributes):
                    continue
                checked += 1
                if not CSRF_FIELD.search(body) or "csrf_token()" not in body:
                    missing.append(f"{template.relative_to(TEMPLATE_ROOT)} form #{number}")

        self.assertGreater(checked, 0, "The template scan must inspect real POST forms.")
        self.assertEqual(
            missing,
            [],
            "Every POST form must submit the session CSRF token. Missing: "
            + ", ".join(missing),
        )


if __name__ == "__main__":
    unittest.main()
