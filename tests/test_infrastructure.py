from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.collectors.ulog_route import REQUIRED_FIELDS, extract_route_observations, sequence_gaps
from scripts.runtime.artifacts import create_manifest, verify_manifest
from scripts.runtime.isolation import (
    allocate_isolation,
    cpu_set_members,
    verify_disjoint_cpu_sets,
    verify_unique,
)
from scripts.runtime.physical_readiness import PhysicalTakeoffGate, physical_takeoff_observed


class InfrastructureTests(unittest.TestCase):
    def test_takeoff_gate_rejects_a_land_detector_pulse(self) -> None:
        gate = PhysicalTakeoffGate(dwell_s=0.5)
        gate.observe_local_position(z_m=-0.08, z_valid=True, now_ns=0)
        gate.observe_land(landed=False, now_ns=0)
        self.assertFalse(gate.evaluate(800_000_000))

    def test_takeoff_replay_requires_sustained_height_and_land_agreement(self) -> None:
        records = [
            {
                "kind": "vehicle_local_position",
                "received_monotonic_ns": 0,
                "z": -0.6,
                "z_valid": True,
            },
            {
                "kind": "vehicle_land_detected",
                "received_monotonic_ns": 10_000_000,
                "landed": False,
            },
            {
                "kind": "vehicle_local_position",
                "received_monotonic_ns": 300_000_000,
                "z": -0.7,
                "z_valid": True,
            },
            {
                "kind": "vehicle_land_detected",
                "received_monotonic_ns": 520_000_000,
                "landed": False,
            },
        ]
        self.assertTrue(physical_takeoff_observed(records))

    def test_cpu_sets_and_allocations_are_disjoint(self) -> None:
        self.assertEqual(cpu_set_members("0-2,5"), frozenset({0, 1, 2, 5}))
        verify_disjoint_cpu_sets(["0-2", "3-5"])
        with self.assertRaisesRegex(ValueError, "overlap"):
            verify_disjoint_cpu_sets(["0-2", "2-4"])
        root = Path("/tmp/family-a-tests")
        allocations = [
            allocate_isolation(
                study_id="qualification",
                attempt_id=f"attempt-{slot}",
                slot=slot,
                run_root=root,
                cpu_sets=["0-2", "3-5"],
            )
            for slot in range(2)
        ]
        verify_unique(allocations)

    def test_raw_manifest_detects_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence.bin").write_bytes(b"original")
            manifest = create_manifest(root)
            verify_manifest(root, manifest)
            (root / "evidence.bin").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_manifest(root, manifest)

    def test_ulog_extraction_orders_instances_and_detects_gaps(self) -> None:
        def dataset(multi_id: int, timestamps: list[int], sequences: list[int]) -> object:
            values = {field: [0 for _ in timestamps] for field in REQUIRED_FIELDS}
            values["timestamp"] = timestamps
            values["subject_timestamp"] = timestamps
            values["sequence"] = sequences
            return SimpleNamespace(
                name="route_observability", multi_id=multi_id, data=values
            )

        records = extract_route_observations(
            [dataset(1, [20, 40], [0, 2]), dataset(0, [10, 30], [0, 1])]
        )
        self.assertEqual([item["timestamp"] for item in records], [10, 20, 30, 40])
        self.assertEqual(
            sequence_gaps(records),
            [{"ulog_multi_id": 1, "previous_sequence": 0, "current_sequence": 2}],
        )


if __name__ == "__main__":
    unittest.main()
