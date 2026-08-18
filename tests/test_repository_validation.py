"""Focused tests for the V8 tracked-tree boundary."""

from __future__ import annotations

import unittest

from scripts.validation.validate_repo import (
    FORBIDDEN_ACTIVE_PATHS,
    RETAINED_EXPERIMENTS,
    ROOT,
    has_active_files,
)


class RepositoryValidationTests(unittest.TestCase):
    def test_retained_experiment_allowlist_matches_the_checkout(self) -> None:
        observed = {
            path.name
            for path in (ROOT / "experiments").iterdir()
            if path.is_dir() and has_active_files(path)
        }
        self.assertEqual(observed, RETAINED_EXPERIMENTS)

    def test_removed_active_paths_are_absent(self) -> None:
        self.assertTrue(FORBIDDEN_ACTIVE_PATHS)
        self.assertFalse(
            [
                path
                for path in FORBIDDEN_ACTIVE_PATHS
                if has_active_files(ROOT / path)
            ]
        )


if __name__ == "__main__":
    unittest.main()
