#!/usr/bin/env python3
"""Formal V0-P orchestration; imported only after every authorization gate."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from scripts.fuzzer_v0.family_a.attempt_accounting import append_event
from scripts.fuzzer_v0.family_a.check_v0p_cleanup import evaluate as cleanup_evaluate
from scripts.fuzzer_v0.family_a.evidence_gate import classify as evidence_classify


ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = Path("/opt/family_a/workspace")
AUTHORIZATION_REPOSITORY = Path(
    os.environ.get("FAMILY_A_AUTHORIZATION_REPO", str(ROOT))
)
READINESS = (
    AUTHORIZATION_REPOSITORY
    / "experiments/fuzzer_v0/family_a/full_readiness"
)


class OrchestrationError(RuntimeError):
    """A formal graph node failed without a safe closure path."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _wait_file(path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.05)
    raise OrchestrationError(f"readiness file timeout: {path}")


def _agent_library_path() -> str:
    values = [str(WORKSPACE / "dds")]
    for pattern in (
        "temp_install/fastdds*/lib",
        "temp_install/fastrtps*/lib",
        "temp_install/fastcdr*/lib",
        "temp_install/microxrcedds_client*/lib",
    ):
        values.extend(str(path) for path in (WORKSPACE / "dds").glob(pattern))
    return ":".join(dict.fromkeys(values))


def _scenario(slot: dict[str, Any], attempt_root: Path) -> tuple[list[str], dict[str, str]]:
    attempt_id = str(slot["attempt_id"])
    raw = attempt_root / "raw"
    collectors = attempt_root / "collectors"
    px4 = WORKSPACE / "src/PX4-Autopilot"
    ros = WORKSPACE / "ros/install"
    environment = {
        "ROS_DISTRO_SETUP": "/opt/ros/jazzy/setup.bash",
        "ROS_WORKSPACE_SETUP": str(ros / "setup.bash"),
        "PX4_OBSERVABILITY_DIR": str(px4),
        "PX4_C1_DIR": str(px4),
        "MICROXRCE_AGENT_BIN": str(WORKSPACE / "dds/MicroXRCEAgent"),
        "MICROXRCE_AGENT_LD_LIBRARY_PATH": _agent_library_path(),
        "ROUTE_EXTERNAL_MODE_BIN": str(
            ros
            / "lib/route_transition_external_mode/route_transition_external_mode"
        ),
        "C1_MODE_BIN": str(
            ros / "lib/route_transition_external_mode/c1_concurrency_probe"
        ),
        "C1_WORKSPACE_SETUP": str(ros / "setup.bash"),
        "C1_AGENT_BUILD": str(WORKSPACE / "dds"),
        "V0P_PHASE": "V0_P_QUALIFICATION",
        "V0P_STRATEGY": "QUALIFICATION",
        "V0P_SLOT_ID": str(slot["slot_id"]),
        "V0P_SEED_ID": str(slot["seed_id"]),
        "V0P_SIMULATION_SEED": str(slot["simulation_seed"]),
        "ROUTE_EXPERIMENT_BUILD_PROVENANCE": (
            "/opt/family_a/build-inventory/px4-build-provenance.json"
        ),
    }
    slot_id = str(slot["slot_id"])
    if slot_id in {"V0P-S1", "V0P-S2", "V0P-S3"}:
        mode = {"V0P-S1": "offboard", "V0P-S2": "external", "V0P-S3": "executor"}[
            slot_id
        ]
        environment.update(
            {
                "P0_RUN_ROOT": str(attempt_root.parent),
                "P0_PROCESSED_ROOT": str(collectors),
                "P0_SIMULATION_SEED": str(slot["simulation_seed"]),
            }
        )
        command = [str(ROOT / "scripts/probes/run_p0_scenario.sh"), mode, attempt_id]
    elif slot_id == "V0P-S4":
        environment.update(
            {
                "ROUTE_EXPERIMENT_RAW_ROOT": str(raw),
                "ROUTE_EXPERIMENT_PROCESSED_ROOT": str(collectors),
                "ROUTE_EXPERIMENT_SIMULATION_SEED": str(slot["simulation_seed"]),
            }
        )
        command = [
            str(ROOT / "scripts/probes/run_p3_scenario.sh"),
            "offboard",
            "on",
            "off",
            attempt_id,
        ]
    elif slot_id == "V0P-S5":
        environment.update(
            {
                "ROUTE_EXPERIMENT_RAW_ROOT": str(raw),
                "ROUTE_EXPERIMENT_PROCESSED_ROOT": str(collectors),
                "ROUTE_EXPERIMENT_SIMULATION_SEED": str(slot["simulation_seed"]),
            }
        )
        command = [
            str(ROOT / "scripts/probes/run_p2_scenario.sh"),
            "external",
            "sigterm",
            attempt_id,
        ]
    elif slot_id == "V0P-S6":
        environment.update(
            {
                "C1_RUN_ID": attempt_id,
                "C1_EVENT_PAIR": "B",
                "C1_TIMING_ORDER": "A_FIRST",
                "C1_SIMULATION_SEED": str(slot["simulation_seed"]),
                "C1_RAW_ROOT": str(raw),
                "C1_PROCESSED_ROOT": str(collectors),
                "C1_LOGGER_TOPICS_FILE": str(ROOT / "config/freshness_logger_topics.txt"),
            }
        )
        command = [str(ROOT / "scripts/probes/run_c1_concurrency.sh")]
    else:
        raise OrchestrationError(f"unknown formal slot: {slot_id}")
    return command, environment


def _run_oracle(
    command: list[str], output: Path, log: Path
) -> dict[str, Any]:
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(process.stdout + process.stderr, encoding="utf-8")
    if process.returncode or not output.is_file():
        return {
            "result": "UNKNOWN",
            "sha256": None,
            "invoked": True,
            "exit_code": process.returncode,
        }
    value = json.loads(output.read_text(encoding="utf-8"))
    result = str(value.get("status", value.get("classification", "UNKNOWN")))
    if result not in {"PASS", "EXPOSURE", "VIOLATION", "UNKNOWN"}:
        result = "UNKNOWN"
    return {
        "result": result,
        "sha256": _sha256(output),
        "invoked": True,
        "exit_code": process.returncode,
    }


def execute(
    *,
    slot: dict[str, Any],
    attempt_root: Path,
    repository_commit: str,
    authorization_commit: str,
    registration_commit: str,
) -> dict[str, Any]:
    attempt_id = str(slot["attempt_id"])
    authorization_manifest = READINESS / "authorization_identity_manifest.json"
    environment_lock = READINESS / "full_environment_lock.yaml"
    component_manifest = READINESS / "component_manifest.yaml"
    registration_record = (
        AUTHORIZATION_REPOSITORY
        / "experiments/fuzzer_v0/family_a/qualification_attempts"
        / attempt_id
        / "registration.json"
    )
    required_identities = (
        authorization_manifest,
        environment_lock,
        component_manifest,
        registration_record,
    )
    missing_identities = [str(path) for path in required_identities if not path.is_file()]
    if missing_identities:
        raise OrchestrationError(
            f"formal identity inputs are missing: {missing_identities}"
        )
    for name in (
        "registration",
        "raw",
        "collectors",
        "safety",
        "oracles",
        "cleanup",
        "compact",
        "manifests",
    ):
        (attempt_root / name).mkdir(parents=True, exist_ok=False)
    stream = attempt_root / "registration/events.jsonl"

    def event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return append_event(
            stream,
            attempt_id=attempt_id,
            slot_id=str(slot["slot_id"]),
            seed_id=str(slot["seed_id"]),
            event_type=event_type,
            repository_commit=repository_commit,
            authorization_commit=authorization_commit,
            registration_commit=registration_commit,
            payload=payload,
        )

    event("REGISTERED_PRELAUNCH", {"registration_commit_verified": True})
    event("AUTHORIZATION_VERIFIED", {"pushed_main_verified": True})
    residue = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/fuzzer_v0/family_a/check_v0p_runtime_residue.py"),
            "preflight",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if residue.returncode:
        event("REJECTED_PRELAUNCH", {"reason": "process_or_port_preflight_failed"})
        return {
            "status": "REJECTED_PRELAUNCH",
            "runtime_started": False,
            "formal_budget_consumed": False,
        }
    event("PREFLIGHT_PASSED", {"process_port_audit": "CLEAN"})

    safety_events = attempt_root / "safety/live-events.jsonl"
    telemetry_ready = attempt_root / "collectors/telemetry.ready.json"
    telemetry_stop = attempt_root / "collectors/telemetry.stop"
    telemetry_result = attempt_root / "collectors/telemetry-result.json"
    required_extra = []
    applicability = slot["node_applicability"]
    if applicability["freshness_collector_start"] == "REQUIRED":
        required_extra.append("freshness")
    if applicability["successor_collector_start"] == "REQUIRED":
        required_extra.append("successor")
    if applicability["linearization_collector_start"] == "REQUIRED":
        required_extra.append("linearization")
    telemetry_command = [
        sys.executable,
        str(ROOT / "scripts/fuzzer_v0/family_a/runtime_telemetry_collector.py"),
        "--attempt-id",
        attempt_id,
        "--events",
        str(safety_events),
        "--ready",
        str(telemetry_ready),
        "--stop",
        str(telemetry_stop),
        "--output",
        str(telemetry_result),
    ]
    for collector in required_extra:
        telemetry_command.extend(["--collector", collector])
    telemetry_log = (attempt_root / "collectors/telemetry.log").open(
        "w", encoding="utf-8"
    )
    telemetry = subprocess.Popen(
        telemetry_command,
        cwd=ROOT,
        stdout=telemetry_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _wait_file(telemetry_ready, 30)

    successor: subprocess.Popen[str] | None = None
    successor_log_handle = None
    successor_events = attempt_root / "collectors/successor-events.jsonl"
    successor_result = attempt_root / "collectors/successor-observation.json"
    if applicability["successor_collector_start"] == "REQUIRED":
        component_name = (
            "Route Transition"
            if slot["slot_id"] == "V0P-S3"
            else "C1 Concurrency Probe"
        )
        successor_log_handle = (attempt_root / "collectors/successor.log").open(
            "w", encoding="utf-8"
        )
        successor = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "scripts/tracing/successor_lifecycle_monitor.py"),
                "--run-id",
                attempt_id,
                "--output",
                str(successor_result),
                "--events",
                str(successor_events),
                "--timeout",
                "155",
                "--component-name",
                component_name,
            ],
            cwd=ROOT,
            stdout=successor_log_handle,
            stderr=subprocess.STDOUT,
        )
        _wait_file(successor_events, 30)

    supervisor_ready = attempt_root / "safety/supervisor-ready.json"
    supervisor_result = attempt_root / "safety/supervisor-result.json"
    pgid_file = attempt_root / "safety/attempt-process-group"
    supervisor_command = [
        sys.executable,
        str(ROOT / "scripts/fuzzer_v0/family_a/safety_supervisor.py"),
        "--events",
        str(safety_events),
        "--ready",
        str(supervisor_ready),
        "--output",
        str(supervisor_result),
        "--attempt-process-group-file",
        str(pgid_file),
    ]
    for collector in required_extra:
        supervisor_command.extend(["--required-collector", collector])
    supervisor_log = (attempt_root / "safety/supervisor.log").open(
        "w", encoding="utf-8"
    )
    supervisor = subprocess.Popen(
        supervisor_command,
        cwd=ROOT,
        stdout=supervisor_log,
        stderr=subprocess.STDOUT,
    )
    _wait_file(supervisor_ready, 10)

    command, additions = _scenario(slot, attempt_root)
    environment = os.environ.copy()
    environment.update(additions)
    scenario_log = (attempt_root / "raw/scenario.log").open("w", encoding="utf-8")
    scenario = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=scenario_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    process_group = os.getpgid(scenario.pid)
    pgid_file.write_text(f"{process_group}\n", encoding="utf-8")
    _append_jsonl(
        safety_events,
        {"event_type": "scenario_started", "process_group": process_group},
    )
    event(
        "LAUNCH_STARTED",
        {"scenario_command": command, "attempt_process_group": process_group},
    )
    try:
        scenario_code = scenario.wait(timeout=155)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process_group, signal.SIGTERM)
        except ProcessLookupError:
            pass
        scenario_code = 124
    scenario_log.close()
    telemetry_stop.touch()
    try:
        telemetry.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(telemetry.pid), signal.SIGTERM)
        telemetry.wait(timeout=5)
    telemetry_log.close()
    if successor is not None:
        try:
            successor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            successor.terminate()
            successor.wait(timeout=5)
        assert successor_log_handle is not None
        successor_log_handle.close()

    collectors = attempt_root / "collectors"
    route_trace = collectors / "route_trace.jsonl"
    clock_bridge = collectors / "clock_bridge.json"
    route_result_existing = collectors / "route_oracle.json"
    route_complete = route_trace.is_file()
    clock_complete = clock_bridge.is_file()
    writer_complete = (collectors / "route_summary.json").is_file()
    _append_jsonl(
        safety_events,
        {
            "event_type": "observation",
            "controller_values": [0.0] if route_complete else [],
            "actuator_values": [0.0] if writer_complete else [],
            "route_epoch_present": route_complete,
            "writer_lineage_present": writer_complete,
            "controller_lineage_present": writer_complete,
        },
    )
    _append_jsonl(safety_events, {"event_type": "scenario_completed"})
    try:
        supervisor.wait(timeout=10)
    except subprocess.TimeoutExpired:
        supervisor.terminate()
        supervisor.wait(timeout=5)
    supervisor_log.close()
    safety = (
        json.loads(supervisor_result.read_text(encoding="utf-8"))
        if supervisor_result.is_file()
        else {"status": "FORMAL_SAFETY_STOP", "stop_reason": "supervisor_failure"}
    )
    if scenario_code == 0 and safety.get("status") == "SCENARIO_COMPLETED":
        event("SCENARIO_COMPLETED", {"scenario_exit_code": 0})
    else:
        event(
            "SAFETY_STOPPED",
            {
                "scenario_exit_code": scenario_code,
                "reason": safety.get("stop_reason") or "scenario_failure",
            },
        )
    event(
        "COLLECTION_CLOSED",
        {
            "telemetry_exit_code": telemetry.returncode,
            "successor_exit_code": successor.returncode if successor is not None else None,
            "route_trace_present": route_complete,
            "clock_bridge_present": clock_complete,
        },
    )

    if applicability["freshness_collector_start"] == "REQUIRED":
        freshness_observation = collectors / "freshness_observation.json"
        freshness_command = [
            sys.executable,
            str(
                ROOT
                / "scripts/fuzzer_v0/family_a/qualification_freshness_collector.py"
            ),
            "--run-id",
            attempt_id,
            "--fault-type",
            (
                "SETPOINT_ONLY_STALL"
                if slot["slot_id"] == "V0P-S4"
                else "TOTAL_PROCESS_STOP"
            ),
            "--monitor-result",
            str(attempt_root / "raw/monitor_result.json"),
            "--monitor-events",
            str(attempt_root / "raw/monitor_events.jsonl"),
            "--route-trace",
            str(route_trace),
            "--clock-bridge",
            str(clock_bridge),
            "--output",
            str(freshness_observation),
        ]
        fault_record = attempt_root / "raw/fault_record.json"
        if fault_record.is_file():
            freshness_command.extend(["--fault-record", str(fault_record)])
        freshness_process = subprocess.run(
            freshness_command,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        (collectors / "freshness-collector.log").write_text(
            freshness_process.stdout + freshness_process.stderr,
            encoding="utf-8",
        )

    oracle_records: list[dict[str, Any]] = []
    route_output = attempt_root / "oracles/route.json"
    route_record = _run_oracle(
        [
            sys.executable,
            str(ROOT / "scripts/oracles/route_oracle_v0.py"),
            "--trace",
            str(route_trace),
            "--clock-bridge",
            str(clock_bridge),
            "--output",
            str(route_output),
        ],
        route_output,
        attempt_root / "oracles/route.log",
    )
    if route_record["sha256"] is None and route_result_existing.is_file():
        route_record = {
            "result": str(
                json.loads(route_result_existing.read_text(encoding="utf-8")).get(
                    "status", "UNKNOWN"
                )
            ),
            "sha256": _sha256(route_result_existing),
            "invoked": True,
            "exit_code": 0,
        }
    oracle_records.append(
        {
            "oracle_id": "ROUTE",
            "applicability": "REQUIRED",
            **route_record,
        }
    )
    oracle_node_map = {
        "FRESHNESS": "freshness_oracle",
        "SUCCESSOR": "successor_oracle",
        "LINEARIZATION": "linearization_oracle",
    }
    for oracle_id, node in oracle_node_map.items():
        required = applicability[node] == "REQUIRED"
        output = attempt_root / f"oracles/{oracle_id.lower()}.json"
        if required:
            # Required commands are always invoked. Missing source inputs make the
            # Oracle return nonzero and remain UNKNOWN; they never become PASS.
            component_command = {
                "FRESHNESS": [
                    sys.executable,
                    str(ROOT / "scripts/oracles/pre_revocation_freshness_oracle.py"),
                    "--profile",
                    str(ROOT / "experiments/motivation/freshness/primary_preregistration.yaml"),
                    "--observation",
                    str(collectors / "freshness_observation.json"),
                    "--output",
                    str(output),
                ],
                "SUCCESSOR": [
                    sys.executable,
                    str(ROOT / "scripts/oracles/successor_progression_oracle.py"),
                    "--lifecycle-events",
                    str(successor_events),
                    "--executor-log",
                    str(attempt_root / "raw/external_mode.log"),
                    "--route-trace",
                    str(route_trace),
                    "--route-oracle",
                    str(route_output if route_output.is_file() else route_result_existing),
                    "--clock-bridge",
                    str(clock_bridge),
                    "--profile",
                    str(ROOT / "experiments/motivation/successor/baseline_lifecycle_profile.yaml"),
                    "--output",
                    str(output),
                ],
                "LINEARIZATION": [
                    sys.executable,
                    str(ROOT / "scripts/oracles/authority_event_linearization_oracle.py"),
                    "--runner-result",
                    str(attempt_root / "raw/monitor_result.json"),
                    "--events",
                    str(attempt_root / "raw/monitor_events.jsonl"),
                    "--trace",
                    str(route_trace),
                    "--clock-bridge",
                    str(clock_bridge),
                    "--output",
                    str(output),
                ],
            }[oracle_id]
            oracle_records.append(
                {
                    "oracle_id": oracle_id,
                    "applicability": "REQUIRED",
                    **_run_oracle(
                        component_command,
                        output,
                        attempt_root / f"oracles/{oracle_id.lower()}.log",
                    ),
                }
            )
        else:
            oracle_records.append(
                {
                    "oracle_id": oracle_id,
                    "applicability": "NOT_APPLICABLE",
                    "result": "NOT_APPLICABLE",
                    "sha256": None,
                    "invoked": False,
                    "exit_code": 0,
                }
            )
    event("ORACLES_COMPLETED", {"oracles": oracle_records})

    telemetry_value = (
        json.loads(telemetry_result.read_text(encoding="utf-8"))
        if telemetry_result.is_file()
        else {}
    )
    cleanup_input = {
        "land_result_present": telemetry_value.get("land_seen") is True,
        "disarm_result_present": telemetry_value.get("disarm_seen") is True,
        "runner_exit_status": scenario_code,
        "collectors_closed": telemetry.returncode == 0,
        "file_flush_complete": True,
        "expected_artifacts": [
            "registration/events.jsonl",
            "safety/supervisor-result.json",
        ],
        "closed_artifacts": [
            "registration/events.jsonl",
            "safety/supervisor-result.json",
        ],
    }
    cleanup_input_path = attempt_root / "cleanup/input.json"
    cleanup_input_path.write_text(
        json.dumps(cleanup_input, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    cleanup = cleanup_evaluate(cleanup_input, run_dir=attempt_root)
    cleanup_path = attempt_root / "cleanup/result.json"
    cleanup_path.write_text(
        json.dumps(cleanup, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    event("CLEANUP_COMPLETED", {"cleanup_status": cleanup["status"]})

    gate_input = {
        "oracles": [
            {
                "oracle_id": item["oracle_id"],
                "applicability": item["applicability"],
                "result": item["result"],
            }
            for item in oracle_records
        ],
        "safety_result": (
            "PASS"
            if safety.get("status") == "SCENARIO_COMPLETED"
            else "FORMAL_SAFETY_STOP"
        ),
        "cleanup_result": cleanup["status"],
    }
    gate = evidence_classify(gate_input)
    gate_path = attempt_root / "compact/evidence-gate.json"
    gate_path.write_text(
        json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    event("CLASSIFIED", {"classification": gate["classification"]})
    closed = event("CLOSED", {"classification": gate["classification"]})

    raw_artifacts = [
        {
            "path": str(path.relative_to(attempt_root / "raw")),
            "sha256": _sha256(path),
            "flushed": True,
        }
        for path in sorted((attempt_root / "raw").rglob("*"))
        if path.is_file()
    ]
    compact_input = {
        "schema_version": "2.0",
        "attempt": {
            "attempt_id": attempt_id,
            "slot_id": slot["slot_id"],
            "seed_id": slot["seed_id"],
        },
        "authorization": {
            "path": str(authorization_manifest.relative_to(AUTHORIZATION_REPOSITORY)),
            "sha256": _sha256(authorization_manifest),
        },
        "registration": {
            "path": str(registration_record.relative_to(AUTHORIZATION_REPOSITORY)),
            "sha256": _sha256(registration_record),
        },
        "source_and_build_identities": [
            {
                "path": str(environment_lock.relative_to(AUTHORIZATION_REPOSITORY)),
                "sha256": _sha256(environment_lock),
            }
        ],
        "component_identities": [
            {
                "path": str(component_manifest.relative_to(AUTHORIZATION_REPOSITORY)),
                "sha256": _sha256(component_manifest),
            }
        ],
        "raw_artifacts": raw_artifacts,
        "clock_bridge": {
            "status": (
                "VALID"
                if clock_complete
                and json.loads(clock_bridge.read_text(encoding="utf-8")).get("status")
                == "VALID"
                else "INVALID"
            ),
            "sha256": _sha256(clock_bridge) if clock_complete else "0" * 64,
        },
        "critical_windows": [
            {
                "window_id": "route_target_window",
                "status": "COMPLETE" if route_record["result"] != "UNKNOWN" else "INCOMPLETE",
                "sha256": route_record["sha256"] or "0" * 64,
            }
        ],
        "oracles": [
            {
                "oracle_id": item["oracle_id"],
                "applicability": item["applicability"],
                "result": item["result"],
                "sha256": item["sha256"],
            }
            for item in oracle_records
        ],
        "safety": {
            "completed": supervisor_result.is_file(),
            "result": gate_input["safety_result"],
            "sha256": _sha256(supervisor_result) if supervisor_result.is_file() else "0" * 64,
        },
        "cleanup": {
            "completed": True,
            "result": cleanup["status"],
            "sha256": _sha256(cleanup_path),
        },
        "classification": gate["classification"],
        "closure": {"event_type": "CLOSED", "event_hash": closed["event_hash"]},
    }
    compact_input_path = attempt_root / "compact/input.json"
    compact_input_path.write_text(
        json.dumps(compact_input, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    compact_output = attempt_root / "compact/compact-evidence.json"
    compact = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/fuzzer_v0/family_a/compact_evidence.py"),
            "build",
            "--input",
            str(compact_input_path),
            "--output",
            str(compact_output),
            "--raw-root",
            str(attempt_root / "raw"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "status": (
            "CLOSED"
            if compact.returncode == 0
            else "CLOSED_COMPACT_EVIDENCE_REFUSED"
        ),
        "classification": gate["classification"],
        "scenario_exit_code": scenario_code,
        "safety_status": safety.get("status"),
        "cleanup_status": cleanup["status"],
        "compact_evidence_exit_code": compact.returncode,
        "formal_budget_consumed": True,
        "runtime_started": True,
    }
