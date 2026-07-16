#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import rq2_archive_reanalysis as reanalysis  # noqa: E402


class Rq2ArchiveReanalysisTest(unittest.TestCase):
    def test_primary_cell_milestones_use_eval_count_not_zero_based_index(self) -> None:
        records = [
            {"index": 0, "primary_bug": False, "feature_bin": "switching:rp_3:wind_0"},
            {"index": 1, "primary_bug": True, "feature_bin": "switching:rp_3:wind_0"},
            {"index": 5, "primary_bug": True, "feature_bin": "switching:rp_3:wind_0"},
            {"index": 7, "primary_bug": True, "feature_bin": "switching:rp_4:wind_1"},
            {"index": 9, "primary_bug": True, "feature_bin": "switching:rp_4:wind_2"},
        ]

        milestones = reanalysis.primary_cell_milestones(records, targets=(1, 2, 3, 4))

        self.assertEqual({1: 2, 2: 8, 3: 10}, milestones)

    def test_dense_axis_summary_counts_valid_strict_hits_and_severities(self) -> None:
        records = [
            {
                "axis": "wind_m_s",
                "value": 4.0,
                "returncode": 0,
                "primary_bug": False,
                "classical_severity": 0,
                "neural_severity": 0,
            },
            {
                "axis": "wind_m_s",
                "value": 4.0,
                "returncode": 1,
                "primary_bug": True,
                "classical_severity": 0,
                "neural_severity": 3,
            },
            {
                "axis": "wind_m_s",
                "value": 4.0,
                "returncode": 0,
                "primary_bug": False,
                "classical_severity": 0,
                "neural_severity": 1,
            },
            {
                "axis": "wind_m_s",
                "value": 3.0,
                "returncode": 0,
                "primary_bug": True,
                "classical_severity": 0,
                "neural_severity": 3,
            },
        ]

        summary = reanalysis.dense_axis_summary(records)

        self.assertEqual(2, summary["wind_m_s"][4.0]["valid"])
        self.assertEqual(1, summary["wind_m_s"][4.0]["invalid"])
        self.assertEqual(0, summary["wind_m_s"][4.0]["strict_hits"])
        self.assertEqual({"0": 2}, summary["wind_m_s"][4.0]["classical_severity_counts"])
        self.assertEqual({"0": 1, "1": 1}, summary["wind_m_s"][4.0]["neural_severity_counts"])
        self.assertEqual(1, summary["wind_m_s"][3.0]["strict_hits"])


if __name__ == "__main__":
    unittest.main()
