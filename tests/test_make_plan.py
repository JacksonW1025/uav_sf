from __future__ import annotations

import unittest

from scripts.runtime.make_plan import create_plan


class MakePlanTests(unittest.TestCase):
    def test_plan_binds_attested_candidate_identity(self) -> None:
        environment = {
            "environment_id": "thor-qualification",
            "execution_host_id": "agx-thor-local",
            "collector_host_id": "agx-thor-local",
            "target_kind": "sitl",
            "architecture": "aarch64",
            "operating_system": "Ubuntu 24.04 Noble container",
            "px4_binary_digest": "sha256:" + "2" * 64,
            "environment_manifest_digest": "sha256:" + "3" * 64,
        }
        attestation = {
            "attestation_payload": {
                "container": {
                    "candidate": {
                        "repository_revision": "1" * 40,
                        "locks": {"dependencies": "sha256:" + "4" * 64},
                    }
                }
            },
            "execution_environment": environment,
        }
        thresholds = {
            "revocation_deadline_ns": 1,
            "installation_deadline_ns": 1,
            "maximum_effect_gap_ns": 1,
            "maximum_command_age_ns": 1,
            "successor_deadline_ns": 1,
            "fallback_deadline_ns": 1,
        }
        plan = create_plan(
            attestation=attestation,
            run_id="qual-001",
            plan_id="qual-001-plan",
            source_route="internal_hold",
            target_route="legacy_offboard",
            expected_successor="internal_land",
            expected_fallback="internal_land",
            target_activation_expected=True,
            registration_rejection_expected=False,
            activation_rejection_expected=False,
            completion_expected=True,
            fault_expected=False,
            fallback_expected=False,
            thresholds=thresholds,
        )
        self.assertEqual(plan["source_identity"]["repository_commit"], "1" * 40)
        self.assertEqual(plan["execution_environment"], environment)
        self.assertIn("completion", plan["required_event_kinds"])
        self.assertNotIn("fault_detected", plan["required_event_kinds"])

    def test_moving_workload_selects_backward_compatible_schema_revision(self) -> None:
        environment = {
            "environment_id": "thor-a2", "execution_host_id": "host", "collector_host_id": "host",
            "target_kind": "sitl", "architecture": "aarch64", "operating_system": "Ubuntu",
            "px4_binary_digest": "sha256:" + "2" * 64, "environment_manifest_digest": "sha256:" + "3" * 64,
        }
        attestation = {"attestation_payload": {"container": {"candidate": {"repository_revision": "1" * 40, "locks": {"dependencies": "sha256:" + "4" * 64}}}}, "execution_environment": environment}
        workload = {
            "profile_id": "a2", "profile_digest": "sha256:" + "5" * 64,
            "setpoint_semantics": "position_only", "phases": ["takeoff", "move"],
            "injection_phase": "move", "physical_analysis_plan_digest": "sha256:" + "6" * 64,
            "observer_profile": "transition", "observer_config_digest": "sha256:" + "7" * 64,
            "physical_validity": {"minimum_takeoff_height_m": 0.5, "takeoff_dwell_s": 0.5, "minimum_motion_entry_progress_m": 0.75, "minimum_nominal_completion_progress_m": 2.5},
        }
        result = create_plan(
            attestation=attestation, run_id="a2-001", plan_id="a2-001-plan",
            source_route="px4_internal", target_route="legacy_offboard",
            expected_successor="internal_land", expected_fallback="internal_land",
            target_activation_expected=True, registration_rejection_expected=False,
            activation_rejection_expected=False, completion_expected=True,
            fault_expected=False, fallback_expected=False,
            thresholds={name: 1 for name in ("revocation_deadline_ns", "installation_deadline_ns", "maximum_effect_gap_ns", "maximum_command_age_ns", "successor_deadline_ns", "fallback_deadline_ns")},
            workload=workload,
        )
        self.assertEqual(result["schema_version"], "1.3")
        self.assertEqual(result["workload"], workload)
