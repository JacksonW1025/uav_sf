#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import property_fitness  # noqa: E402


BASE_RHO = {
    "P1": 1.0,
    "P2": 3.0,
    "P3": 0.5,
    "P4": 1.0,
    "P5": 1.0,
    "P6": 1.0,
    "P7": 1.0,
}


def property_result(rho: dict[str, float], severity: int = 0, *, vacuous: set[str] | None = None) -> dict[str, object]:
    vacuous = vacuous or set()
    details = {prop: {"vacuous": prop in vacuous} for prop in BASE_RHO}
    labels = {
        0: "S0_clean_recovery",
        1: "S1_controlled_degraded_survival",
        2: "S2_controlled_safe_failure",
        3: "S3_uncontrolled_tumble_or_spin",
        4: "S4_numeric_or_software_fault",
    }
    return {
        "rho": {**BASE_RHO, **rho},
        "details": details,
        "severity": {"severity": severity, "label": labels[severity], "reasons": []},
    }


class PropertyFitnessTest(unittest.TestCase):
    def test_synthetic_ordering_and_findings(self) -> None:
        boring = property_fitness.differential_property_fitness(
            property_result({}),
            property_result({}),
        )
        too_hard = property_fitness.differential_property_fitness(
            property_result({prop: -0.1 for prop in BASE_RHO}, severity=3),
            property_result({prop: -1.0 for prop in BASE_RHO}, severity=3),
        )
        behavior = property_fitness.differential_property_fitness(
            property_result({}),
            property_result({"P6": -0.5}, severity=1),
        )
        catastrophic = property_fitness.differential_property_fitness(
            property_result({}),
            property_result({"P1": -0.2, "P2": -0.4}, severity=3),
        )

        self.assertEqual(0.0, boring["fitness"])
        self.assertEqual(property_fitness.FITNESS_FLOOR, too_hard["fitness"])
        self.assertGreater(behavior["fitness"], boring["fitness"])
        self.assertIn("P6", behavior["clean_differential_properties"])
        self.assertTrue(behavior["property_finding"])
        self.assertGreater(catastrophic["fitness"], boring["fitness"])
        self.assertEqual(["P1", "P2"], catastrophic["clean_differential_properties"])
        self.assertTrue(catastrophic["strict_s0_vs_s3"])

    def test_driver_targets_do_not_chase_catastrophic_p1_p2(self) -> None:
        result = property_fitness.differential_property_fitness(
            property_result({}),
            property_result({"P1": -0.2, "P2": -0.4}, severity=3),
            target_properties=["P4", "P6", "P7"],
        )
        self.assertEqual(0.0, result["fitness"])
        self.assertEqual("P4", result["best_property"])
        self.assertEqual(["P1", "P2"], result["clean_differential_properties"])
        self.assertFalse(result["per_property"]["P1"]["target"])

    def test_vacuous_p5_is_not_fitness_valid_even_if_rho_is_bad(self) -> None:
        result = property_fitness.differential_property_fitness(
            property_result({"P5": 1.0}, vacuous={"P5"}),
            property_result({"P5": -2.0}, severity=2, vacuous={"P5"}),
            target_properties=["P5"],
        )
        self.assertEqual(property_fitness.FITNESS_FLOOR, result["fitness"])
        self.assertEqual([], result["clean_differential_properties"])
        self.assertEqual("vacuous_property", result["per_property"]["P5"]["excluded_reason"])

    def test_step_theta_adds_p5_to_driver_targets(self) -> None:
        theta = {
            "setpoint": {
                "type": "step",
                "step": {"delta_ned": [0.5, 0.0, 0.0]},
            }
        }
        self.assertEqual(["P4", "P5", "P6", "P7"], property_fitness.driver_target_properties(theta))


if __name__ == "__main__":
    unittest.main()
