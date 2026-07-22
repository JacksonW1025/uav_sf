from __future__ import annotations

import json
import hashlib
from pathlib import Path

import yaml

from scripts.workloads import w1_compact_trace, w1_evaluate_attempt, w1_trace_replay


PHASES = [
    "internal_ground",
    "arm",
    "internal_takeoff",
    "Aerostack2_Offboard",
    "go_to",
    "follow_path",
    "cancel_to_hover",
    "explicit_aircraft_Land",
    "disarm",
]


def _events() -> list[dict]:
    records = [
        {"event_type": "mission_phase", "phase": phase, "monotonic_ns": index + 1}
        for index, phase in enumerate(PHASES)
    ]
    records.extend(
        [
            {"event_type": "service_request", "request_id": "service", "monotonic_ns": 20},
            {"event_type": "service_result", "request_id": "service", "monotonic_ns": 21},
            {"event_type": "action_goal_request", "action": "go_to", "monotonic_ns": 22},
            {
                "event_type": "action_goal_accepted",
                "action": "go_to",
                "goal_id": "01",
                "monotonic_ns": 23,
            },
            {"event_type": "action_feedback", "action": "go_to", "monotonic_ns": 24},
            {
                "event_type": "action_result",
                "action": "go_to",
                "goal_id": "01",
                "monotonic_ns": 25,
            },
            {"event_type": "action_goal_request", "action": "follow_path", "monotonic_ns": 26},
            {
                "event_type": "action_goal_accepted",
                "action": "follow_path",
                "goal_id": "02",
                "monotonic_ns": 27,
            },
            {"event_type": "action_feedback", "action": "follow_path", "monotonic_ns": 28},
            {
                "event_type": "action_cancel_request",
                "goal_id": "02",
                "monotonic_ns": 29,
            },
            {
                "event_type": "action_cancel_ack",
                "goal_id": "02",
                "monotonic_ns": 30,
            },
            {
                "event_type": "action_result",
                "action": "follow_path",
                "goal_id": "02",
                "monotonic_ns": 31,
            },
            {
                "event_type": "motion_reference",
                "values": {"position": [1.0, 0.0, 1.5]},
                "monotonic_ns": 32,
            },
            {"event_type": "mission_finished", "monotonic_ns": 33},
        ]
    )
    return records


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")


def test_trace_only_replay_is_deterministic_and_has_no_command_publication(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _write_jsonl(source, _events())
    first, validation = w1_trace_replay.replay(source)
    second, second_validation = w1_trace_replay.replay(source)
    assert validation["valid"] is True
    assert first == second
    assert validation == second_validation
    assert w1_trace_replay.digest(first) == w1_trace_replay.digest(second)
    source_text = Path(w1_trace_replay.__file__).read_text(encoding="utf-8")
    assert "create_publisher" not in source_text
    assert "rclpy" not in source_text


def test_trace_only_replay_rejects_incomplete_cancel_correlation(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    records = [item for item in _events() if item["event_type"] != "action_cancel_ack"]
    _write_jsonl(source, records)
    _, validation = w1_trace_replay.replay(source)
    assert validation["valid"] is False
    assert any("cancel" in error for error in validation["errors"])


def test_compact_trace_keeps_lifecycle_and_samples_continuous_evidence(tmp_path: Path, monkeypatch) -> None:
    mission = tmp_path / "mission.jsonl"
    sidecar = tmp_path / "sidecar.jsonl"
    output = tmp_path / "compact.jsonl"
    summary = tmp_path / "summary.json"
    _write_jsonl(mission, _events())
    _write_jsonl(
        sidecar,
        [
            {"event_type": "setpoint_sample", "monotonic_ns": index + 100, "values": {"x": index}}
            for index in range(5)
        ],
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "w1_compact_trace.py",
            "--mission-events",
            str(mission),
            "--sidecar-events",
            str(sidecar),
            "--output",
            str(output),
            "--summary",
            str(summary),
            "--stride",
            "2",
            "--run-id",
            "test",
        ],
    )
    assert w1_compact_trace.main() == 0
    compact = [json.loads(line) for line in output.read_text().splitlines()]
    assert sum(item["event_type"] == "mission_phase" for item in compact) == len(PHASES)
    assert sum(item["event_type"] == "setpoint_sample" for item in compact) == 3


def test_attempt_evaluator_accepts_complete_synthetic_contract(tmp_path: Path, monkeypatch) -> None:
    raw = tmp_path / "raw"
    processed = raw / "processed"
    (raw / "rosbag").mkdir(parents=True)
    processed.mkdir(exist_ok=True)
    (raw / "flight.ulg").write_bytes(b"ulog")
    (raw / "rosbag" / "metadata.yaml").write_text("rosbag2_bagfile_information: {}\n")
    (raw / "mission_result.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "formal_safety_stop": False,
                "terminal_landed": True,
                "terminal_disarmed": True,
            }
        )
    )
    _write_jsonl(raw / "mission_events.jsonl", _events())
    _write_jsonl(
        raw / "sidecar_events.jsonl",
        [
            {"event_type": "motion_reference", "values": {"position": [1.0, 0.0, 1.5]}},
            {"event_type": "setpoint_sample", "values": {"velocity": [0.5, 0.0, 0.0]}},
            {"event_type": "platform_info"},
            {"event_type": "controller_info"},
        ],
    )
    _write_jsonl(
        processed / "route_trace.jsonl",
        [
            {"event_type": "route_epoch_changed"},
            {"event_type": "px4_setpoint_consumed"},
            {
                "event_type": "allocator_input_published",
                "allocator_input": {"topic": "vehicle_torque_setpoint", "writer": "mc_rate_control"},
                "actuator_writer": "control_allocator",
            },
            {"event_type": "actuator_output_published", "actuator_writer": "control_allocator"},
        ],
    )
    (processed / "clock_bridge.json").write_text(json.dumps({"status": "VALID"}))
    (processed / "raw_artifact_manifest.json").write_text(
        json.dumps({"artifact_set_sha256": "0" * 64})
    )
    cleanup = raw / "cleanup.json"
    cleanup.write_text(json.dumps({"clean": True}))
    output = processed / "result.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "w1_evaluate_attempt.py",
            "--run-id",
            "test",
            "--phase",
            "W1-B",
            "--raw",
            str(raw),
            "--processed",
            str(processed),
            "--output",
            str(output),
            "--cleanup",
            str(cleanup),
        ],
    )
    assert w1_evaluate_attempt.main() == 0
    assert json.loads(output.read_text())["classification"] == "ACCEPTED"


def test_runtime_tooling_matches_w1_source_hash_lock() -> None:
    root = Path(__file__).resolve().parents[1]
    lock = yaml.safe_load(
        (root / "experiments/motivation/w1_workload/source_lock.yaml").read_text()
    )
    tracked = {}
    tracked.update(lock["mission_and_launch_artifacts"])
    tracked.update(lock["repository_artifacts"])
    selected = {
        "config/w1_aerostack2_runtime.yaml": tracked["w1_low_risk_mission_overlay"],
        "config/w1_pid_speed_controller.yaml": tracked["w1_pid_speed_controller_overlay"],
        "config/w1_rosbag_topics.txt": tracked["w1_rosbag_topics"],
    }
    selected.update(
        {
            path: digest
            for path, digest in lock["repository_artifacts"].items()
            if path.startswith("scripts/workloads/w1_")
            or path == "scripts/workloads/run_w1_workload.sh"
            or path.startswith("data/schemas/w1_")
        }
    )
    for relative, expected in selected.items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected


def test_sidecar_does_not_reuse_reserved_rclpy_node_handle() -> None:
    source = Path(w1_trace_replay.__file__).with_name("w1_sidecar_recorder.py").read_text()
    assert "self.handle" not in source
    assert "create_publisher" not in source
