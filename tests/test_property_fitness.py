#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "analysis"))

import property_fitness  # noqa: E402
import m1_compare  # noqa: E402


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
        self.assertIn("P6", behavior["strict_differential_properties"])
        self.assertEqual(behavior["clean_differential_properties"], behavior["strict_differential_properties"])
        self.assertEqual([], behavior["relative_degradation_differential_properties"])
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

    def test_catastrophic_fitness_requires_decontaminated_classical_s0(self) -> None:
        result = property_fitness.differential_property_fitness(
            property_result({"P1": 0.8, "P2": 3.5}, severity=2),
            property_result({"P1": -0.2, "P2": -0.4}, severity=3),
            target_properties=["P1", "P2"],
        )

        self.assertEqual(property_fitness.FITNESS_FLOOR, result["fitness"])
        self.assertTrue(result["catastrophic_fitness_requires_classical_s0"])
        self.assertFalse(result["per_property"]["P1"]["valid_for_fitness"])
        self.assertEqual(
            "classical_not_decontaminated_s0_for_catastrophic_fitness",
            result["per_property"]["P1"]["excluded_reason"],
        )
        self.assertEqual(
            {
                "P1": "classical_not_decontaminated_s0_for_catastrophic_fitness",
                "P2": "classical_not_decontaminated_s0_for_catastrophic_fitness",
            },
            result["target_exclusion_reasons"],
        )

    def test_absolute_severity_fitness_does_not_require_classical_s0(self) -> None:
        result = property_fitness.absolute_severity_fitness(
            property_result({"P1": 1.0, "P2": 3.0}, severity=3),
            property_result({"P1": -0.2, "P2": -0.4}, severity=3),
            target_properties=["P1", "P2"],
        )

        self.assertEqual("absolute_severity", result["fitness_mode"])
        self.assertEqual(0.4, result["fitness"])
        self.assertEqual("P2", result["best_property"])
        self.assertFalse(result["catastrophic_fitness_requires_classical_s0"])
        self.assertEqual(2, result["valid_property_count"])
        self.assertEqual({}, result["target_exclusion_reasons"])
        self.assertFalse(result["strict_s0_vs_s3"])
        self.assertEqual(property_fitness.FITNESS_FLOOR, result["reference_diff_fitness"]["fitness"])
        self.assertEqual(
            "classical_not_decontaminated_s0_for_catastrophic_fitness",
            result["reference_diff_fitness"]["target_exclusion_reasons"]["P1"],
        )

    def test_vacuous_p5_is_not_fitness_valid_even_if_rho_is_bad(self) -> None:
        result = property_fitness.differential_property_fitness(
            property_result({"P5": 1.0}, vacuous={"P5"}),
            property_result({"P5": -2.0}, severity=2, vacuous={"P5"}),
            target_properties=["P5"],
        )
        self.assertEqual(property_fitness.FITNESS_FLOOR, result["fitness"])
        self.assertEqual([], result["clean_differential_properties"])
        self.assertEqual("vacuous_property", result["per_property"]["P5"]["excluded_reason"])

    def test_borderline_violation_inside_jitter_band_is_not_finding(self) -> None:
        result = property_fitness.differential_property_fitness(
            property_result({}),
            property_result({"P7": -0.05}, severity=1),
            target_properties=["P7"],
        )
        self.assertEqual(["P7"], result["candidate_differential_properties"])
        self.assertEqual([], result["clean_differential_properties"])
        self.assertFalse(result["property_finding"])
        self.assertEqual("candidate", result["per_property"]["P7"]["differential_class"])
        self.assertGreater(result["per_property"]["P7"]["rho_jitter_reproduction_margin"], 0.05)

    def test_relative_degradation_flags_probe_but_not_boring(self) -> None:
        probe = property_fitness.differential_property_fitness(
            property_result({"P7": 0.80}),
            property_result({"P7": 0.30}, severity=1),
            target_properties=["P7"],
        )
        boring = property_fitness.differential_property_fitness(
            property_result({"P7": 0.80}),
            property_result({"P7": 0.60}),
            target_properties=["P7"],
        )

        self.assertEqual(["P7"], probe["relative_degradation_differential_properties"])
        self.assertEqual([], probe["candidate_differential_properties"])
        self.assertEqual([], probe["strict_differential_properties"])
        self.assertTrue(probe["property_finding"])
        self.assertTrue(probe["per_property"]["P7"]["relative_degradation_differential"])
        self.assertFalse(probe["per_property"]["P7"]["strict_differential"])
        self.assertEqual("relative_degradation_differential", probe["per_property"]["P7"]["differential_class"])
        self.assertGreater(
            probe["per_property"]["P7"]["gap"],
            probe["per_property"]["P7"]["rho_jitter_reproduction_margin"],
        )
        self.assertEqual([], boring["relative_degradation_differential_properties"])
        self.assertFalse(boring["property_finding"])

    def test_policy_findings_keep_catastrophic_gate_separate_from_behavior_gate(self) -> None:
        behavior = property_fitness.policy_differential_findings(
            property_result({"P1": -0.2}, severity=1),
            property_result({"P1": -0.4, "P7": -0.50}, severity=3),
        )
        catastrophic = property_fitness.policy_differential_findings(
            property_result({}),
            property_result({"P2": -0.40}, severity=3),
        )

        self.assertEqual(["P7"], behavior["positive_policies"])
        self.assertFalse(behavior["by_policy"]["P2"]["finding"])
        self.assertEqual(
            "catastrophic_requires_classical_s0_and_neural_s3",
            behavior["by_policy"]["P2"]["excluded_reason"],
        )
        self.assertTrue(behavior["by_policy"]["P7"]["finding"])
        self.assertEqual("behavior_margin_violation", behavior["by_policy"]["P7"]["finding_kind"])

        self.assertEqual(["P2"], catastrophic["positive_policies"])
        self.assertTrue(catastrophic["by_policy"]["P2"]["finding"])
        self.assertEqual("catastrophic_severity_sign", catastrophic["by_policy"]["P2"]["finding_kind"])
        self.assertFalse(catastrophic["by_policy"]["P1"]["finding"])
        self.assertEqual("neural_does_not_violate_policy", catastrophic["by_policy"]["P1"]["excluded_reason"])

    def test_policy_findings_reject_vacuous_and_relative_only_behavior(self) -> None:
        result = property_fitness.policy_differential_findings(
            property_result({"P5": 1.0, "P7": 0.80}, vacuous={"P5"}),
            property_result({"P5": -2.0, "P7": 0.30}, severity=2, vacuous={"P5"}),
        )

        self.assertEqual([], result["positive_policies"])
        self.assertEqual("vacuous_property", result["by_policy"]["P5"]["excluded_reason"])
        self.assertEqual("neural_violation_inside_reproduction_margin", result["by_policy"]["P7"]["excluded_reason"])
        self.assertFalse(result["by_policy"]["P7"]["finding"])

    def test_m1_compare_surfaces_relative_degradation_fields(self) -> None:
        result = m1_compare.property_differential(
            property_result({"P7": 0.80}),
            property_result({"P7": 0.30}, severity=1),
        )

        self.assertEqual(["P7"], result["relative_degradation_differential_properties"])
        self.assertEqual([], result["strict_differential_properties"])
        self.assertTrue(result["relative_degradation_finding"])
        self.assertFalse(result["strict_differential_finding"])
        self.assertTrue(result["property_finding"])
        self.assertFalse(result["property_primary_bug"])
        self.assertTrue(result["per_property"]["P7"]["relative_degradation_differential"])

        property_only = m1_compare.property_only_result(
            {"tag": "unit_relative"},
            property_result({"P7": 0.80}),
            property_result({"P7": 0.30}, severity=1),
        )
        self.assertFalse(property_only["primary_bug"])

    def test_m1_compare_surfaces_policy_findings(self) -> None:
        result = m1_compare.property_differential(
            property_result({}),
            property_result({"P2": -0.40, "P7": -0.50}, severity=3),
        )

        self.assertEqual(["P2", "P7"], result["policy_findings"]["positive_policies"])
        self.assertEqual(["P2"], result["policy_findings"]["catastrophic_positive_policies"])
        self.assertEqual(["P7"], result["policy_findings"]["behavior_positive_policies"])

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
