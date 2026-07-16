#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import route_a_anchor_regression as route_a  # noqa: E402


def gate_record(
    group: str,
    seed: int,
    *,
    strict: bool = True,
    classical_s0: bool = True,
    mcnn_s3: bool = True,
) -> dict[str, Any]:
    return {
        "anchor_group": group,
        "label": f"{group}_seed_{seed}",
        "seed": seed,
        "case": f"{group}_case",
        "source": "unit",
        "strict_s0_vs_s3": strict,
        "classical_s0": classical_s0,
        "mcnn_s3": mcnn_s3,
        "rho_sign_summary": {"passes_sign_gate": bool(strict)},
        "judged": {
            "valid_matched_pair": True,
            "classical": {
                "control_level": {
                    "control_level_label": "S0_clean_recovery_decontaminated" if classical_s0 else "S1_controlled"
                }
            },
            "mcnn": {
                "control_level": {
                    "control_level_label": "S3_control_loss_or_tumble" if mcnn_s3 else "S0_clean_recovery_decontaminated"
                }
            },
        },
    }


class RouteAGateAPrimeTest(unittest.TestCase):
    def test_gate_a_prime_passes_deep_strict_and_boundary_six_of_eight(self) -> None:
        records = [
            gate_record("pair1", 20261800),
            gate_record("pair2", 20261901),
        ]
        records.extend(
            gate_record("pair4", seed, strict=idx < 6, mcnn_s3=idx < 6)
            for idx, seed in enumerate(route_a.BOUNDARY_ANCHOR_SEEDS["pair4"])
        )
        records.extend(
            gate_record("pair5", seed)
            for seed in route_a.BOUNDARY_ANCHOR_SEEDS["pair5"]
        )

        result = route_a.evaluate_gate_a_prime(records)

        self.assertTrue(result["gate_passed"])
        self.assertEqual("GATE_A_PRIME_PASS", result["decision"])
        self.assertTrue(result["deep_anchors"]["pair1"]["passed"])
        self.assertTrue(result["deep_anchors"]["pair2"]["passed"])
        self.assertEqual(6, result["boundary_anchors"]["pair4"]["strict_s0_vs_s3_hits"])
        self.assertEqual(8, result["boundary_anchors"]["pair4"]["attempts"])
        self.assertEqual(0.75, result["boundary_anchors"]["pair4"]["hit_rate"])
        self.assertEqual(6, result["boundary_anchors"]["pair4"]["strict_floor"])
        self.assertTrue(result["boundary_anchors"]["pair4"]["passed"])
        self.assertEqual([20262402, 20262502], result["boundary_anchors"]["pair4"]["non_strict_seeds"])

    def test_gate_a_prime_fails_when_deep_anchor_is_not_strict(self) -> None:
        records = [
            gate_record("pair1", 20261800),
            gate_record("pair2", 20261901, strict=False, mcnn_s3=False),
        ]
        records.extend(gate_record("pair4", seed) for seed in route_a.BOUNDARY_ANCHOR_SEEDS["pair4"])
        records.extend(gate_record("pair5", seed) for seed in route_a.BOUNDARY_ANCHOR_SEEDS["pair5"])

        result = route_a.evaluate_gate_a_prime(records)

        self.assertFalse(result["gate_passed"])
        self.assertEqual("GATE_A_PRIME_BLOCKED", result["decision"])
        self.assertFalse(result["deep_anchors"]["pair2"]["passed"])

    def test_gate_a_prime_fails_when_boundary_rate_is_below_six_of_eight(self) -> None:
        records = [
            gate_record("pair1", 20261800),
            gate_record("pair2", 20261901),
        ]
        records.extend(
            gate_record("pair4", seed, strict=idx < 5, mcnn_s3=idx < 5)
            for idx, seed in enumerate(route_a.BOUNDARY_ANCHOR_SEEDS["pair4"])
        )
        records.extend(gate_record("pair5", seed) for seed in route_a.BOUNDARY_ANCHOR_SEEDS["pair5"])

        result = route_a.evaluate_gate_a_prime(records)

        self.assertFalse(result["gate_passed"])
        self.assertEqual("GATE_A_PRIME_BLOCKED", result["decision"])
        self.assertFalse(result["boundary_anchors"]["pair4"]["passed"])
        self.assertEqual(5, result["boundary_anchors"]["pair4"]["strict_s0_vs_s3_hits"])


if __name__ == "__main__":
    unittest.main()
