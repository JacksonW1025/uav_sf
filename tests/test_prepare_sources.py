"""Tests for the locked-source checkout helper's network robustness."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.setup.prepare_sources import (
    GIT_ORPHAN_LOCKS,
    _clear_orphan_git_locks,
)


class OrphanLockTests(unittest.TestCase):
    def test_locks_a_killed_git_left_are_cleared(self):
        # A timeout means this script killed the git process, so a lock in that
        # tree belongs to the process it just killed. Leaving it in place made
        # the remaining two attempts fail on "File exists" without issuing a
        # single further request.
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            (tree / ".git").mkdir()
            for name in GIT_ORPHAN_LOCKS:
                (tree / ".git" / name).write_text("", encoding="utf-8")
            removed = _clear_orphan_git_locks(tree)
            self.assertEqual(sorted(removed), sorted(GIT_ORPHAN_LOCKS))
            for name in GIT_ORPHAN_LOCKS:
                self.assertFalse((tree / ".git" / name).exists())

    def test_only_the_named_locks_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            (tree / ".git").mkdir()
            (tree / ".git" / "shallow.lock").write_text("", encoding="utf-8")
            (tree / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            (tree / ".git" / "shallow").write_text("", encoding="utf-8")
            self.assertEqual(_clear_orphan_git_locks(tree), ["shallow.lock"])
            self.assertTrue((tree / ".git" / "HEAD").exists())
            self.assertTrue((tree / ".git" / "shallow").exists())

    def test_a_tree_without_a_git_directory_is_left_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(_clear_orphan_git_locks(Path(directory)), [])

    def test_no_tree_is_not_an_error(self):
        self.assertEqual(_clear_orphan_git_locks(None), [])

    def test_clearing_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            (tree / ".git").mkdir()
            (tree / ".git" / "index.lock").write_text("", encoding="utf-8")
            self.assertEqual(_clear_orphan_git_locks(tree), ["index.lock"])
            self.assertEqual(_clear_orphan_git_locks(tree), [])


if __name__ == "__main__":
    unittest.main()
