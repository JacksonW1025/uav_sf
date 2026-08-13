"""Strict matched-block validation and differential analysis tests."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

from scripts.analysis.matched_differential import (
    analyze_block,
    analyze_blocks,
    block_id_for,
    motivation_unpaired_descriptive,
)


_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64


def _match() -> dict[str, object]:
    return {
        "abstract_task": "hold_position_then_land",
        "setpoint_level": "trajectory",
        "fault_semantics": "process_exit",
        "successor_semantics": "safe_land",
        "fallback_semantics": "health_loss_then_safe_land",
        "simulation_seed": 101,
        "fault_seed": 202,
        "schedule_seed": 303,
        "planned_action_offset_ns": 2_000_000_000,
        "cpu_set": "8-11",
        "load_profile": "nominal",
        "observer_config_digest": _DIGEST_A,
        "environment_digest": _DIGEST_B,
        "common_software_digest": _DIGEST_C,
    }


def _arm(mechanism: str, *, age_ns: int, offset_ns: int) -> dict[str, object]:
    realized = _match()
    realized.pop("planned_action_offset_ns")
    realized["actual_action_offset_ns"] = offset_ns
    return {
        "arm_id": f"arm-{mechanism}",
        "mechanism": mechanism,
        "attempt_id": f"attempt-{mechanism}",
        "treatment_description": {
            "fixture": f"fixture-{mechanism}",
            "adapter": f"adapter-{mechanism}",
            "code_path": f"path-{mechanism}",
        },
        "realized_match": realized,
        "evidence_gate": "ADMISSIBLE",
        "correctness": {
            "top_level": "PASS",
            "semantic_vector": ["PASS"],
        },
        "observations": {
            "route_installed": True,
            "route_installation_latency_ns": 120_000_000,
            "route_revoked": True,
            "revocation_latency_ns": 20_000_000,
            "maximum_command_age_ns": age_ns,
            "lineage_complete": True,
            "owner_matches_expected": True,
            "observed_owner": mechanism,
            "successor_installed": True,
            "successor_installation_latency_ns": 130_000_000,
            "fallback_installed": True,
            "fallback_installation_latency_ns": 1_100_000_000,
            "physical_outcome": "LANDED",
            "observation_completeness": 1.0,
            "direct_observation_fields": [
                "route_installed",
                "maximum_command_age_ns",
                "owner_matches_expected",
            ],
        },
    }


def block() -> dict[str, object]:
    declared = _match()
    value: dict[str, object] = {
        "schema_version": "1.0",
        "profile": "PROCESS_LOSS_FALLBACK",
        "declared_match": declared,
        "arms": [
            _arm(
                "legacy_offboard", age_ns=180_000_000, offset_ns=2_000_000_000
            ),
            _arm(
                "dynamic_external_mode",
                age_ns=240_000_000,
                offset_ns=2_010_000_000,
            ),
        ],
    }
    value["block_id"] = block_id_for(value["profile"], declared)
    return value


class MatchedDifferentialTests(unittest.TestCase):
    def test_fully_matched_block_produces_signal_without_mutating_correctness(self) -> None:
        result = analyze_block(block())
        self.assertEqual(result["match_status"], "FULLY_MATCHED")
        self.assertTrue(result["paired_estimate_eligible"])
        pair = result["pairs"][0]
        self.assertEqual(pair["semantic_disposition"], "DIFFERENTIAL_DIVERGENCE")
        self.assertEqual(
            pair["paired_latency_differences_ns"]["maximum_command_age_ns"],
            -60_000_000,
        )
        self.assertEqual(
            set(pair["paired_verdict_vector"].values()),
            {"PASS"},
        )
        self.assertTrue(pair["correctness_verdicts_unchanged"])

    def test_timing_outside_tolerance_is_partial_and_excluded(self) -> None:
        value = block()
        value["arms"][1]["realized_match"]["actual_action_offset_ns"] = 2_030_000_001
        result = analyze_block(value)
        self.assertEqual(result["match_status"], "PARTIALLY_MATCHED")
        self.assertFalse(result["paired_estimate_eligible"])
        self.assertIn(
            "ACTION_TIMING_MISMATCH",
            {reason["code"] for reason in result["mismatch_reasons"]},
        )

    def test_semantic_mismatch_is_unmatched(self) -> None:
        value = block()
        value["arms"][1]["realized_match"]["abstract_task"] = "different_task"
        result = analyze_block(value)
        self.assertEqual(result["match_status"], "UNMATCHED")
        self.assertFalse(result["paired_estimate_eligible"])
        self.assertEqual(result["pairs"], [])

    def test_inadmissible_arm_keeps_match_status_but_excludes_estimate(self) -> None:
        value = block()
        value["arms"][1]["evidence_gate"] = "INADMISSIBLE"
        result = analyze_block(value)
        self.assertEqual(result["match_status"], "FULLY_MATCHED")
        self.assertFalse(result["paired_estimate_eligible"])
        self.assertEqual(result["pairs"], [])
        self.assertIn(
            "INADMISSIBLE_ARM",
            {reason["code"] for reason in result["estimate_exclusion_reasons"]},
        )

    def test_duplicate_mechanism_is_never_treated_as_a_pair(self) -> None:
        value = block()
        value["arms"][1]["mechanism"] = "legacy_offboard"
        result = analyze_block(value)
        self.assertEqual(result["match_status"], "UNMATCHED")
        self.assertEqual(result["pairs"], [])

    def test_effect_size_uses_only_eligible_complete_pairs(self) -> None:
        first = block()
        second = copy.deepcopy(first)
        second["declared_match"]["simulation_seed"] = 102
        second["arms"][0]["realized_match"]["simulation_seed"] = 102
        second["arms"][1]["realized_match"]["simulation_seed"] = 102
        second["block_id"] = block_id_for(second["profile"], second["declared_match"])
        second["arms"][1]["observations"]["maximum_command_age_ns"] = 280_000_000
        summary = analyze_blocks([first, second])
        effect = next(
            item
            for item in summary["paired_effects"]
            if item["metric"] == "maximum_command_age_ns"
        )
        self.assertEqual(effect["complete_pair_count"], 2)
        self.assertEqual(effect["mean_difference_ns"], -80_000_000)
        self.assertIsNotNone(effect["standardized_effect_dz"])

    def test_motivation_corpus_is_only_unpaired_descriptive_input(self) -> None:
        records = motivation_unpaired_descriptive(Path("."))
        self.assertEqual(len(records), 151)
        self.assertEqual({item["pairing_status"] for item in records}, {"UNMATCHED"})
        self.assertEqual(
            {item["reason_code"] for item in records},
            {"NO_PREREGISTERED_MATCHED_BLOCK"},
        )


if __name__ == "__main__":
    unittest.main()
