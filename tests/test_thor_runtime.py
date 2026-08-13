from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.collectors.ulog_route import (
    REQUIRED_FIELDS,
    extract_route_observations,
    sequence_gaps,
)
from scripts.runtime.artifacts import create_manifest, verify_manifest
from scripts.runtime.isolation import (
    allocate_isolation,
    cpu_set_members,
    verify_disjoint_cpu_sets,
    verify_unique,
)
from scripts.runtime.run_qualification_batch import (
    QualificationBatchError,
    qualification_gate,
    validate_spec,
)
from scripts.runtime.run_sitl import _read_jsonl_snapshot
from scripts.setup.prepare_sources import SourceError, _verify_patched_tree
from scripts.setup.verify_candidates import _git_identity


class ThorRuntimeTests(unittest.TestCase):
    def test_cpu_sets_are_parsed_and_must_not_overlap(self) -> None:
        self.assertEqual(cpu_set_members("0-2,5"), frozenset({0, 1, 2, 5}))
        verify_disjoint_cpu_sets(["0-2", "3-5", "6-8", "9-13"])
        with self.assertRaisesRegex(ValueError, "overlap"):
            verify_disjoint_cpu_sets(["0-2", "2-4"])

    def test_qualification_batch_requires_one_isolated_slot_per_attempt(self) -> None:
        spec = {
            "schema_version": "1.0",
            "study_id": "qualification-five",
            "concurrency": 2,
            "resources": {
                "cpu_sets": ["0-1", "2-3"],
                "memory_per_attempt": "16g",
            },
            "attempts": [
                {"run_id": "qual-a", "slot": 0},
                {"run_id": "qual-b", "slot": 1},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            validate_spec(spec, run_root=Path(directory))
            spec["attempts"][1]["slot"] = 0
            with self.assertRaises(QualificationBatchError):
                validate_spec(spec, run_root=Path(directory))

    def test_qualification_gate_fails_on_clock_quality(self) -> None:
        spec = {
            "concurrency": 1,
            "qualification_gate": {
                "required_admissible_fraction": 1.0,
                "required_ulog_integrity_fraction": 1.0,
                "maximum_clock_uncertainty_ns": 20_000_000,
                "minimum_central_real_time_factor": 0.97,
                "require_zero_isolation_or_cleanup_failures": True,
            },
        }
        result = qualification_gate(
            spec,
            barrier_passed=True,
            live_errors={},
            process_errors={},
            process_results={
                "attempt": {
                    "outcome": "ACCEPTED",
                    "runtime_outcome": "ACCEPTED",
                    "ulog": {"status": "PASS"},
                    "clock_bridge": {"uncertainty_ns": 20_000_001},
                    "gazebo": {"central_minimum": 0.999},
                }
            },
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failures"], ["clock_uncertainty"])

    def test_jsonl_snapshot_defers_only_an_open_final_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sidecar.jsonl"
            path.write_text('{"kind":"closed"}\n{"kind":', encoding="utf-8")
            self.assertEqual(_read_jsonl_snapshot(path), [{"kind": "closed"}])

            path.write_text('{"kind":}\n', encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                _read_jsonl_snapshot(path)

            path.write_text('{"kind":}\n{"kind":"valid"}', encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                _read_jsonl_snapshot(path)

    def test_parallel_allocations_are_isolated(self) -> None:
        root = Path("/tmp/family-a-tests")
        allocations = [
            allocate_isolation(
                study_id="motivation-v1",
                attempt_id=f"a-{slot}",
                slot=slot,
                run_root=root,
                cpu_sets=["0-2", "3-5", "6-8", "9-11"],
            )
            for slot in range(4)
        ]
        verify_unique(allocations)
        self.assertEqual({item.study_id for item in allocations}, {"motivation-v1"})
        self.assertEqual({item.attempt_id for item in allocations}, {"a-0", "a-1", "a-2", "a-3"})
        self.assertEqual({item.ros_domain_id for item in allocations}, {40, 41, 42, 43})
        self.assertEqual(len({item.xrce_agent_port for item in allocations}), 4)
        self.assertEqual(
            [item.mavlink_udp_local_port for item in allocations],
            [14580, 14581, 14582, 14583],
        )
        self.assertEqual(
            [item.mavlink_udp_port for item in allocations],
            [14540, 14541, 14542, 14543],
        )
        self.assertEqual(
            [item.mavlink_tcp_port for item in allocations],
            [4560, 4561, 4562, 4563],
        )

    def test_patch_tree_keeps_first_porcelain_path_character(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            tracked = root / "msg" / "CMakeLists.txt"
            tracked.parent.mkdir()
            tracked.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Family A Test",
                    "-c",
                    "user.email=family-a@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "fixture",
                ],
                check=True,
            )
            tracked.write_text("after\n", encoding="utf-8")
            _verify_patched_tree(root, {"msg/CMakeLists.txt"}, "fixture")
            with self.assertRaises(SourceError):
                _verify_patched_tree(root, {"sg/CMakeLists.txt"}, "fixture")

            identity = _git_identity(root)
            self.assertEqual(identity["changed_paths"], ["msg/CMakeLists.txt"])

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
            values = {
                field: [0 for _ in timestamps]
                for field in REQUIRED_FIELDS
            }
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

    def test_ulog_extraction_rejects_missing_field(self) -> None:
        values = {field: [0] for field in REQUIRED_FIELDS if field != "event_type"}
        item = SimpleNamespace(name="route_observability", multi_id=0, data=values)
        with self.assertRaisesRegex(ValueError, "lacks fields"):
            extract_route_observations([item])


if __name__ == "__main__":
    unittest.main()
