#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import wave1_windphysics_report as report  # noqa: E402


def fitness(rel_props: list[str], *, p7_gap: float, p7_classical: float, p7_neural: float) -> dict[str, object]:
    margin = 0.4484874426
    per_property = {
        prop: {
            "gap": 0.0,
            "classical_rho": 1.0,
            "neural_rho": 1.0,
            "rho_jitter_reproduction_margin": margin,
            "relative_degradation_differential": prop in rel_props,
        }
        for prop in report.TARGET_PROPERTIES
    }
    per_property["P7"].update(
        {
            "gap": p7_gap,
            "classical_rho": p7_classical,
            "neural_rho": p7_neural,
            "relative_degradation_differential": "P7" in rel_props,
        }
    )
    return {
        "relative_degradation_differential_properties": rel_props,
        "per_property": per_property,
    }


class Wave1ReportTest(unittest.TestCase):
    def test_p7_trigger_confirmation_is_property_specific(self) -> None:
        run = {
            "label": "unit",
            "metadata": {"resolved_target_properties": ["P4", "P6", "P7"]},
            "confirmed": [
                {
                    "passed": True,
                    "candidate": {
                        "result": {
                            "tag": "candidate",
                            "feature_bin": "steady_combo:wind_high:physics_mid",
                            "fitness": fitness(["P4", "P7"], p7_gap=0.9, p7_classical=1.1, p7_neural=0.2),
                        }
                    },
                    "repeats": [
                        {"fitness": fitness(["P4", "P7"], p7_gap=0.5, p7_classical=0.9, p7_neural=0.4)},
                        {"fitness": fitness(["P4"], p7_gap=0.2, p7_classical=0.7, p7_neural=0.5)},
                        {"fitness": fitness(["P4", "P7"], p7_gap=0.6, p7_classical=1.0, p7_neural=0.4)},
                    ],
                }
            ],
        }

        items = report.p7_candidate_items([run])
        self.assertEqual(1, len(items))
        self.assertEqual(2, items[0]["p7_gap_hits"])
        self.assertEqual(2, items[0]["p7_relative_hits"])

        counts = report.trigger_property_confirmation_counts([run])
        self.assertEqual({"triggered": 1, "confirmed_2of3": 1, "confirmed_3of3": 1}, counts["P4"])
        self.assertEqual({"triggered": 1, "confirmed_2of3": 1, "confirmed_3of3": 0}, counts["P7"])


if __name__ == "__main__":
    unittest.main()
