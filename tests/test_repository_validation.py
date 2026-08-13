"""Focused tests for repository validation policy."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.validation.validate_repo import ROOT, TERM_SCAN_EXEMPT


class RepositoryValidationTests(unittest.TestCase):
    def test_only_reviewed_narrative_is_exempt_from_scope_term_scan(self) -> None:
        self.assertEqual(TERM_SCAN_EXEMPT, {Path("docs/NEW_NARRATIVE_v7.md")})
        narrative = ROOT / next(iter(TERM_SCAN_EXEMPT))
        self.assertTrue(narrative.is_file())


if __name__ == "__main__":
    unittest.main()
