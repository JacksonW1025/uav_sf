#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validity_automation as validity  # noqa: E402


class Dataset:
    def __init__(self, name: str, data: dict[str, list[float] | list[int] | list[bool]]) -> None:
        self.name = name
        self.data = {key: np.asarray(value) for key, value in data.items()}


class FakeULog:
    def __init__(self, datasets: list[Dataset]) -> None:
        self.data_list = datasets


class ValidityAutomationTest(unittest.TestCase):
    def test_infrastructure_failsafe_cuts_control_window(self) -> None:
        ulog = FakeULog(
            [
                Dataset(
                    "vehicle_status",
                    {
                        "timestamp": [0, 9_500_000, 10_000_000, 11_000_000],
                        "failsafe": [False, False, True, True],
                        "nav_state": [14, 14, 14, 5],
                    },
                ),
                Dataset(
                    "failsafe_flags",
                    {
                        "timestamp": [0, 9_500_000, 10_000_000],
                        "offboard_control_signal_lost": [False, True, True],
                        "manual_control_signal_lost": [False, False, False],
                    },
                ),
                Dataset(
                    "vehicle_land_detected",
                    {
                        "timestamp": [0, 12_000_000],
                        "ground_contact": [False, True],
                        "landed": [False, True],
                    },
                ),
                Dataset(
                    "vehicle_local_position",
                    {
                        "timestamp": [0, 1_000_000],
                        "z": [-2.5, -2.5],
                    },
                ),
            ]
        )
        window = validity.decontaminated_control_window(
            ulog,
            0,
            20_000_000,
            controller="classical",
        )
        self.assertTrue(window["valid"])
        self.assertEqual("INFRASTRUCTURE", window["terminal"]["terminal_class"])
        self.assertEqual(10_000_000, window["control_end_us"])
        self.assertTrue(window["cut_at_infrastructure_terminal"])
        self.assertIn("ground_contact_after_infrastructure_terminal", window["terminal"]["terminal_reasons"])

    def test_low_recovery_height_is_fail_loud_invalid(self) -> None:
        ulog = FakeULog(
            [
                Dataset(
                    "vehicle_status",
                    {
                        "timestamp": [0, 1_000_000],
                        "failsafe": [False, False],
                        "nav_state": [23, 23],
                    },
                ),
                Dataset(
                    "vehicle_local_position",
                    {
                        "timestamp": [0, 1_000_000],
                        "z": [-0.25, -0.25],
                    },
                ),
            ]
        )
        window = validity.decontaminated_control_window(ulog, 0, 2_000_000, controller="mcnn")
        gate = validity.decontamination_gate(window)
        self.assertFalse(gate["passed"])
        self.assertEqual(["start_below_min_recovery_height"], gate["reasons"])

    def test_mcnn_identity_gate_passes_and_fails_loud(self) -> None:
        good = {
            "controller": "mcnn",
            "raptor_input_present": False,
            "neural_control_samples": 12_000,
            "neural_control_rate_hz": 228.0,
            "network_output_actuator_exact_equal_count": 11_900,
            "network_output_actuator_exact_match_fraction": 0.99,
            "network_output_actuator_p99_abs_diff": 0.0,
        }
        self.assertTrue(validity.mcnn_identity_gate(good)["passed"])
        bad = dict(good)
        bad["raptor_input_present"] = True
        gate = validity.mcnn_identity_gate(bad)
        self.assertFalse(gate["passed"])
        self.assertIn("raptor_input_present", gate["reasons"])
        with self.assertRaises(validity.ValidityGateError):
            validity.assert_mcnn_identity(bad)

    def test_reproduction_margin_rejects_p7_minus_0p05(self) -> None:
        margins = validity.reproduction_margins()
        self.assertGreater(margins["P7"], 0.05)
        self.assertFalse(validity.robust_property_finding(1.0, -0.05, 0.1, margins["P7"]))
        self.assertTrue(validity.robust_property_finding(1.0, -0.50, 0.1, margins["P7"]))


if __name__ == "__main__":
    unittest.main()
