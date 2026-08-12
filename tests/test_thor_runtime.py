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
from scripts.runtime.isolation import allocate_isolation, verify_unique
from scripts.setup.prepare_sources import SourceError, _verify_patched_tree
from scripts.setup.verify_candidates import _git_identity


class ThorRuntimeTests(unittest.TestCase):
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
