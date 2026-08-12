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
