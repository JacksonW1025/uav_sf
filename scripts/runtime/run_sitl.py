#!/usr/bin/env python3
"""Run one isolated Thor SITL attempt inside the attested container."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from scripts.runtime.isolation import allocate_isolation
from scripts.corpus.core_actions import live_profile
from scripts.runtime.live_strategy_backend import CORPUS_SCHEMA, validate_live_decision
from scripts.runtime.physical_readiness import physical_takeoff_observed
from scripts.runtime.preflight import self_check


class RuntimeFailure(RuntimeError):
    """An attempt could not close its process and evidence set."""


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeFailure(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


class Lifecycle:
    def __init__(self, path: Path, run_id: str) -> None:
        if path.exists():
            raise RuntimeFailure(f"refusing to overwrite: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._run_id = run_id
        self._sequence = 0

    def append(self, kind: str, **payload: Any) -> None:
        record = {
            "schema_version": "1.0",
            "sequence": self._sequence,
            "run_id": self._run_id,
            "kind": kind,
            "received_monotonic_ns": time.monotonic_ns(),
            **payload,
        }
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._sequence += 1


class ManagedProcess:
    def __init__(
        self,
        *,
        name: str,
        command: list[str],
        cwd: Path,
        environment: dict[str, str],
        output_directory: Path,
        cpu_set: str,
    ) -> None:
        self.name = name
        # Retained so a lost producer can be restarted with the same contract
        # and only the session-specific parameters replaced.
        self.command = list(command)
        self.stdout_path = output_directory / f"{name}.stdout.log"
        self.stderr_path = output_directory / f"{name}.stderr.log"
        self._stdout = self.stdout_path.open("xb")
        self._stderr = self.stderr_path.open("xb")
        self.process = subprocess.Popen(
            ["taskset", "--cpu-list", cpu_set, *command],
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=self._stdout,
            stderr=self._stderr,
            start_new_session=True,
        )

    def terminate(self, grace_s: float = 5.0) -> None:
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=grace_s)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self._stdout.close()
        self._stderr.close()


def _wait_for_telemetry(path: Path, processes: list[ManagedProcess], timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        failed = [item for item in processes if item.process.poll() is not None]
        if failed:
            raise RuntimeFailure(
                "process exited before telemetry: "
                + ", ".join(f"{item.name}={item.process.returncode}" for item in failed)
            )
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            if '"kind":"vehicle_status"' in text and '"kind":"timesync_sample"' in text:
                return
        time.sleep(0.2)
    raise RuntimeFailure("ROS/PX4 telemetry readiness timed out")


def _read_jsonl_snapshot(path: Path) -> list[dict[str, Any]]:
    """Read one file snapshot without accepting a damaged closed record.

    Sidecars append a complete JSON record followed by a newline, but a reader
    may take its snapshot between those writes.  Only an invalid final fragment
    from a snapshot that does not end in a newline is deferred to the next read.
    A malformed closed or interior record remains a hard runtime failure.
    """

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1 and not text.endswith("\n"):
                break
            raise
        if not isinstance(record, dict):
            raise ValueError(f"JSONL record {index + 1} is not an object: {path}")
        records.append(record)
    return records


def _wait_for_armed(path: Path, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            for record in reversed(_read_jsonl_snapshot(path)):
                if record.get("kind") == "vehicle_status":
                    if int(record.get("arming_state", -1)) == 2:
                        return
                    break
        time.sleep(0.1)
    raise RuntimeFailure("duplicate-registration fixture did not observe armed state")


def _wait_for_lifecycle_kind(path: Path, kind: str, timeout_s: float) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            for record in _read_jsonl_snapshot(path):
                if record.get("kind") == kind:
                    return int(record["received_monotonic_ns"])
        time.sleep(0.05)
    raise RuntimeFailure(f"workload did not publish {kind} before its deadline")


def _latest_ulog(root: Path) -> Path:
    candidates = sorted(root.rglob("*.ulg"), key=lambda path: path.stat().st_mtime_ns)
    if not candidates:
        raise RuntimeFailure("PX4 produced no ULog")
    return candidates[-1]


def _semantic_success(
    path: Path, mechanism: str, *, expected_rejection: bool = False
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    records = _read_jsonl_snapshot(path)
    statuses = [item for item in records if item.get("kind") == "vehicle_status"]
    land = [item for item in records if item.get("kind") == "vehicle_land_detected"]
    armed = any(int(item.get("arming_state", -1)) == 2 for item in statuses)
    airborne = physical_takeoff_observed(records)
    if expected_rejection:
        if any(23 <= int(item.get("nav_state", -1)) <= 30 for item in statuses):
            reasons.append("external target activated despite the expected rejection")
    elif not armed:
        reasons.append("vehicle never reached ARMING_STATE_ARMED")
    if not expected_rejection and not airborne:
        reasons.append("vehicle never became airborne")
    if not expected_rejection and mechanism == "legacy_offboard" and not any(
        int(item.get("nav_state", -1)) == 14 for item in statuses
    ):
        reasons.append("vehicle never reached legacy Offboard nav state")
    if not expected_rejection and mechanism in {"dynamic_external_mode", "mode_executor"} and not any(
        23 <= int(item.get("nav_state", -1)) <= 30 for item in statuses
    ):
        reasons.append("vehicle never reached an allocated external nav state")
    terminal_status = statuses[-1] if statuses else {}
    terminal_land = land[-1] if land else {}
    if int(terminal_status.get("arming_state", -1)) != 1:
        reasons.append("terminal vehicle state is not disarmed")
    if not bool(terminal_land.get("landed", False)):
        reasons.append("terminal vehicle state is not landed")
    return not reasons, reasons


def capacity_command(index: int) -> list[str]:
    """One additional external mode component competing for a navigation slot."""

    return [
        "ros2",
        "run",
        "family_a_modes",
        "external_mode",
        "--ros-args",
        "-r",
        f"__node:=family_a_capacity_{index + 1}",
        "-p",
        "active_duration_s:=8.0",
    ]


def _adjacent_bucket(decision: dict[str, Any] | None) -> str:
    """Record the request against the completion boundary it was aimed at.

    The manual requester keeps the vocabulary the Stage A1 timing cells used,
    so the two earliest bins are before the scheduled completion, the middle
    one is on it, and the two latest are after.
    """

    boundary = str((decision or {}).get("selected_boundary", "boundary"))
    return {
        "early": "before",
        "pre_boundary": "before",
        "boundary": "near",
        "post_boundary": "after",
        "late": "after",
    }.get(boundary, "near")


def _latest_safe_route(path: Path) -> str | None:
    records = _read_jsonl_snapshot(path)
    statuses = [item for item in records if item.get("kind") == "vehicle_status"]
    if not statuses:
        return None
    return {
        4: "internal_hold",
        5: "internal_rtl",
        18: "internal_land",
    }.get(int(statuses[-1].get("nav_state", -1)))


def _terminal_safe(path: Path) -> bool:
    records = _read_jsonl_snapshot(path)
    statuses = [item for item in records if item.get("kind") == "vehicle_status"]
    land = [item for item in records if item.get("kind") == "vehicle_land_detected"]
    return bool(
        statuses
        and land
        and int(statuses[-1].get("arming_state", -1)) == 1
        and bool(land[-1].get("landed", False))
    )


def _mission_started(path: Path, mechanism: str) -> bool:
    records = _read_jsonl_snapshot(path)
    statuses = [item for item in records if item.get("kind") == "vehicle_status"]
    armed = any(int(item.get("arming_state", -1)) == 2 for item in statuses)
    airborne = physical_takeoff_observed(records)
    if mechanism == "legacy_offboard":
        target_active = any(int(item.get("nav_state", -1)) == 14 for item in statuses)
    else:
        target_active = any(
            23 <= int(item.get("nav_state", -1)) <= 30 for item in statuses
        )
    return armed and airborne and target_active


def run(args: argparse.Namespace) -> dict[str, Any]:
    strategy_decision = None
    if args.strategy_decision_path is not None:
        try:
            strategy_decision = json.loads(
                args.strategy_decision_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise RuntimeFailure("live strategy decision is not valid JSON") from exc
        if not isinstance(strategy_decision, dict):
            raise RuntimeFailure("live strategy decision is not an object")
        validate_live_decision(strategy_decision)
        # The flight must perform the action that was decided.  A corpus
        # decision names a core action, whose live profile fixes the runtime
        # fault mode; the earlier single-action decision names that mode
        # directly.
        if strategy_decision.get("schema_version") == CORPUS_SCHEMA:
            expected_fault_mode = live_profile(str(strategy_decision["action"])).fault_mode
        else:
            expected_fault_mode = strategy_decision["action"]
        if expected_fault_mode != args.fault_mode:
            raise RuntimeFailure("live strategy action differs from the runtime fault mode")
        if args.workload_profile != "straight_line":
            raise RuntimeFailure("the live strategy backend requires the moving workload")
        if args.mechanism not in {"legacy_offboard", "dynamic_external_mode"}:
            raise RuntimeFailure("the live strategy backend does not support this mechanism")
    preflight = self_check()
    if preflight["status"] != "PASS":
        raise RuntimeFailure("formal container preflight failed: " + ", ".join(preflight["failures"]))
    allocation = allocate_isolation(
        study_id=args.study_id,
        attempt_id=args.run_id,
        slot=args.slot,
        run_root=args.run_root,
        cpu_sets=[args.cpu_set for _ in range(args.slot + 1)],
    )
    run_directory = Path(allocation.run_directory)
    if run_directory.exists():
        raise RuntimeFailure(f"run directory already exists: {run_directory}")
    raw = run_directory / "raw"
    tmp = run_directory / "tmp"
    raw.mkdir(parents=True)
    tmp.mkdir()
    lifecycle = Lifecycle(raw / "runner.lifecycle.jsonl", args.run_id)
    _write_new(run_directory / "allocation.json", allocation.as_dict())
    _write_new(run_directory / "preflight.json", preflight)
    lifecycle.append("attempt_started", mechanism=args.mechanism)

    repository = Path("/opt/uav_sf")
    px4_source = repository / "external/px4_autopilot"
    px4_binary = px4_source / "build/px4_sitl_default/bin/px4"
    px4_data = px4_source / "build/px4_sitl_default/etc"
    gz_models = px4_source / "Tools/simulation/gz/models"
    gz_worlds = px4_source / "Tools/simulation/gz/worlds"
    gz_plugins = (
        px4_source
        / "build/px4_sitl_default/src/modules/simulation/gz_plugins"
    )
    gz_server_config = (
        px4_source / "src/modules/simulation/gz_bridge/server.config"
    )
    px4_work = tmp / "px4-rootfs"
    px4_work.mkdir()
    telemetry = raw / "telemetry.sidecar.jsonl"
    decision = raw / "safety.decision.json"
    action_request = raw / "strategy-action.request.json"
    environment = dict(os.environ)
    environment.update(
        {
            "HOME": str(tmp / "home"),
            "TMPDIR": str(tmp),
            "XDG_DATA_HOME": str(tmp / "xdg"),
            "ROS_DOMAIN_ID": str(allocation.ros_domain_id),
            "GZ_PARTITION": allocation.gazebo_partition,
            "PX4_SYS_AUTOSTART": "4001",
            "PX4_SIM_MODEL": "gz_x500",
            "PX4_GZ_WORLD": "default",
            "PX4_GZ_STANDALONE": "1",
            # Calling the built PX4 binary directly bypasses the Make target
            # that normally sources build/.../rootfs/gz_env.sh.  Bind every
            # Gazebo search path to an immutable path inside this image.
            "PX4_GZ_MODELS": str(gz_models),
            "PX4_GZ_WORLDS": str(gz_worlds),
            "PX4_GZ_PLUGINS": str(gz_plugins),
            "PX4_GZ_SERVER_CONFIG": str(gz_server_config),
            "GZ_SIM_RESOURCE_PATH": f"{gz_models}:{gz_worlds}",
            "GZ_SIM_SYSTEM_PLUGIN_PATH": str(gz_plugins),
            "GZ_SIM_SERVER_CONFIG_PATH": str(gz_server_config),
            "PX4_UXRCE_DDS_PORT": str(allocation.xrce_agent_port),
            # ROS domains already isolate attempts. Clear PX4's implicit
            # nonzero-instance namespace so every isolated container uses the
            # same project command/topic contract.
            "PX4_UXRCE_DDS_NS": "",
            # The x500 airframe assumes a physical power module and GCS.
            # Neither exists in this network-isolated SITL topology. These
            # documented PX4 parameters disable only those absent interfaces;
            # all estimator, control and experiment safety checks stay active.
            "PX4_PARAM_CBRK_SUPPLY_CHK": "894281",
            "PX4_PARAM_NAV_DLL_ACT": "0",
            # Formal fault cells require a deterministic, contract-level
            # response to loss of the Legacy Offboard proof-of-life.
            "PX4_PARAM_COM_OF_LOSS_T": "1.0",
            "PX4_PARAM_COM_OBL_RC_ACT": "4",
            # One boot-to-shutdown ULog is required so registration, route,
            # fault and terminal evidence remain in one closed source window.
            "PX4_PARAM_SDLOG_MODE": "2",
            "HEADLESS": "1",
        }
    )
    Path(environment["HOME"]).mkdir()
    processes: list[ManagedProcess] = []

    def start(name: str, command: list[str], cwd: Path = repository) -> ManagedProcess:
        process = ManagedProcess(
            name=name,
            command=command,
            cwd=cwd,
            environment=environment,
            output_directory=raw,
            cpu_set=args.cpu_set,
        )
        processes.append(process)
        lifecycle.append("process_started", process=name, pid=process.process.pid)
        return process

    outcome = "ENVIRONMENT_FAILURE"
    failure_reason: str | None = None
    workload: ManagedProcess | None = None
    reclaim_process: ManagedProcess | None = None
    adjacent_process: ManagedProcess | None = None
    capacity_started = False
    reclaim_command: list[str] = []
    reclaim_session = f"reclaim-{args.run_id}"
    safety: ManagedProcess | None = None
    expected_fault_observed = False
    observed_fallback_route: str | None = None
    try:
        start(
            "xrce_agent",
            ["/opt/microxrce/bin/MicroXRCEAgent", "udp4", "-p", str(allocation.xrce_agent_port)],
        )
        start(
            "gazebo",
            [
                "gz",
                "sim",
                "-r",
                "-s",
                "--seed",
                str(args.simulation_seed),
                str(gz_worlds / "default.sdf"),
            ],
        )
        time.sleep(1.0)
        start(
            "px4",
            [
                str(px4_binary),
                "-d",
                "-i",
                str(allocation.px4_instance),
                "-w",
                str(px4_work),
                str(px4_data),
            ],
            px4_source,
        )
        time.sleep(2.0)
        # Gazebo publishes simulation statistics in the same isolated
        # partition.  The retained stream is used only to assess evidence
        # quality and stable throughput when selecting formal concurrency.
        start(
            "gazebo_stats",
            ["gz", "topic", "-e", "-t", "/world/default/stats"],
        )
        start(
            "gazebo_clock_sidecar",
            [
                "/opt/family_a_ws/install/lib/family_a_modes/gazebo_clock_sidecar",
                str(raw / "gazebo.clock.jsonl"),
            ],
        )
        start(
            "telemetry_sidecar",
            [
                "ros2",
                "run",
                "family_a_runtime",
                "telemetry_sidecar",
                "--ros-args",
                "-p",
                f"run_id:={args.run_id}",
                "-p",
                f"output_path:={telemetry}",
            ],
        )
        _wait_for_telemetry(telemetry, processes, args.readiness_timeout_s)
        safety = start(
            "safety_supervisor",
            [
                "ros2",
                "run",
                "family_a_runtime",
                "safety_supervisor",
                "--ros-args",
                "-p",
                f"run_id:={args.run_id}",
                "-p",
                f"sidecar_path:={telemetry}",
                "-p",
                f"decision_path:={decision}",
                "-p",
                f"limits_path:={args.safety_limits}",
                "-p",
                f"target_system:={allocation.px4_instance + 1}",
            ],
        )
        if args.mechanism == "legacy_offboard":
            workload = start(
                "workload",
                [
                    "ros2",
                    "run",
                    "family_a_runtime",
                    "offboard_controller",
                    "--ros-args",
                    "-p",
                    f"run_id:={args.run_id}",
                    "-p",
                    f"lifecycle_path:={raw / 'workload.lifecycle.jsonl'}",
                    "-p",
                    f"setpoint_kind:={args.setpoint_kind}",
                    "-p",
                    f"fault_mode:={args.fault_mode}",
                    "-p",
                    f"active_s:={args.active_s}",
                    "-p",
                    f"stall_after_s:={args.stall_after_s}",
                    "-p",
                    f"source_route:={args.source_route}",
                    "-p",
                    f"successor_route:={args.successor_route}",
                    "-p",
                    f"repeat_count:={args.repeat_count}",
                    "-p",
                    f"target_system:={allocation.px4_instance + 1}",
                    "-p",
                    f"workload_profile:={args.workload_profile}",
                    "-p",
                    f"motion_settle_s:={args.motion_settle_s}",
                    "-p",
                    f"motion_speed_m_s:={args.motion_speed_m_s}",
                    "-p",
                    f"motion_distance_m:={args.motion_distance_m}",
                    "-p",
                    f"motion_entry_progress_m:={args.motion_entry_progress_m}",
                    "-p",
                    f"motion_completion_progress_m:={args.motion_completion_progress_m}",
                    *(
                        ["-p", f"action_request_path:={action_request}"]
                        if strategy_decision
                        else []
                    ),
                    *(
                        ["-p", f"scheduled_action:={args.scheduled_action}"]
                        if args.scheduled_action
                        else []
                    ),
                ],
            )
        elif args.mechanism == "dynamic_external_mode":
            registration_handoff = raw / "external-mode.registration.json"
            workload = start(
                "external_mode_requester",
                [
                    "ros2",
                    "run",
                    "family_a_runtime",
                    "external_mode_requester",
                    "--ros-args",
                    "-p",
                    f"run_id:={args.run_id}",
                    "-p",
                    f"lifecycle_path:={raw / 'workload.lifecycle.jsonl'}",
                    "-p",
                    f"active_s:={args.active_s}",
                    "-p",
                    f"source_route:={args.source_route}",
                    "-p",
                    f"successor_route:={args.successor_route}",
                    "-p",
                    f"fault_mode:={'health_loss' if args.health_loss else args.fault_mode}",
                    "-p",
                    f"target_system:={allocation.px4_instance + 1}",
                    "-p",
                    f"registration_handoff_path:={registration_handoff}",
                    "-p",
                    f"workload_profile:={args.workload_profile}",
                    "-p",
                    f"stall_after_s:={args.stall_after_s}",
                    "-p",
                    f"motion_entry_progress_m:={args.motion_entry_progress_m}",
                    "-p",
                    f"motion_completion_progress_m:={args.motion_completion_progress_m}",
                    *(
                        ["-p", f"action_request_path:={action_request}"]
                        if strategy_decision
                        else []
                    ),
                    *(
                        ["-p", f"scheduled_action:={args.scheduled_action}"]
                        if args.scheduled_action
                        else []
                    ),
                    "-p",
                    f"repeat_count:={args.repeat_count}",
                ],
            )
            time.sleep(0.5)
            start(
                "external_mode",
                [
                    "ros2",
                    "run",
                    "family_a_modes",
                    "external_mode",
                    "--ros-args",
                    "-p",
                    f"active_duration_s:={args.active_s}",
                    "-p",
                    f"fault_mode:={'normal' if args.health_loss else args.fault_mode}",
                    "-p",
                    f"health_reply_enabled:={'false' if args.health_loss else 'true'}",
                    "-p",
                    f"run_id:={args.run_id}",
                    "-p",
                    f"registration_handoff_path:={registration_handoff}",
                    "-p",
                    f"workload_profile:={args.workload_profile}",
                    "-p",
                    f"stall_after_s:={args.stall_after_s}",
                    "-p",
                    f"motion_settle_s:={args.motion_settle_s}",
                    "-p",
                    f"motion_speed_m_s:={args.motion_speed_m_s}",
                    "-p",
                    f"motion_distance_m:={args.motion_distance_m}",
                    *(
                        ["-p", f"action_request_path:={action_request}"]
                        if strategy_decision
                        else []
                    ),
                ],
            )
            if args.duplicate_registration and args.scheduled_action != "exhaust_registration_capacity":
                # Exercise the public registration-capacity boundary. PX4
                # exposes eight external nav-state slots (23..30); the
                # primary component holds one, seven further registrations
                # remain legal, and the eighth additional request must be
                # rejected without modifying commander internals.
                _wait_for_armed(telemetry, 20.0)
                for duplicate_index in range(8):
                    start(
                        f"external_mode_capacity_{duplicate_index + 1}",
                        capacity_command(duplicate_index),
                    )
                    time.sleep(0.2)
        elif args.mechanism == "mode_executor":
            workload = start(
                "mode_executor",
                [
                    "ros2",
                    "run",
                    "family_a_modes",
                    "mode_executor",
                    "--ros-args",
                    "-p",
                    f"run_id:={args.run_id}",
                    "-p",
                    f"lifecycle_path:={raw / 'workload.lifecycle.jsonl'}",
                    "-p",
                    f"mode_duration_s:={args.active_s}",
                ],
            )
            if args.manual_land_offset_s is not None:
                transition_anchor_ns = _wait_for_lifecycle_kind(
                    raw / "workload.lifecycle.jsonl", "transition_requested", 30.0
                )
                bucket = (
                    "before"
                    if args.manual_land_offset_s < 0
                    else ("after" if args.manual_land_offset_s > 0 else "near")
                )
                start(
                    "manual_requester",
                    [
                        "ros2",
                        "run",
                        "family_a_runtime",
                        "manual_requester",
                        "--ros-args",
                        "-p",
                        f"run_id:={args.run_id}",
                        "-p",
                        f"output_path:={raw / 'adjacent.lifecycle.jsonl'}",
                        "-p",
                        f"request_delay_s:={max(0.0, args.active_s + args.manual_land_offset_s)}",
                        "-p",
                        f"anchor_monotonic_ns:={transition_anchor_ns}",
                        "-p",
                        f"timing_bucket:={bucket}",
                        "-p",
                        f"target_system:={allocation.px4_instance + 1}",
                    ],
                )
        else:
            raise RuntimeFailure(f"attempt mechanism is not implemented: {args.mechanism}")
        if args.scheduled_action == "restart_producer_after_loss" and workload is not None:
            reclaim_command = [
                *workload.command,
                "-p",
                f"lifecycle_path:={raw / 'workload.reclaim.lifecycle.jsonl'}",
                "-p",
                "fault_mode:=normal",
                "-p",
                "source_route:=px4_internal",
                "-p",
                f"producer_session_label:={reclaim_session}",
            ]
        if args.scheduled_action == "adjacent_land_request":
            # Started with the workload, not on demand, so it is already
            # running when the decided moment arrives.
            adjacent_process = start(
                "manual_requester",
                [
                    "ros2",
                    "run",
                    "family_a_runtime",
                    "manual_requester",
                    "--ros-args",
                    "-p",
                    f"run_id:={args.run_id}",
                    "-p",
                    f"output_path:={raw / 'adjacent.lifecycle.jsonl'}",
                    "-p",
                    f"trigger_path:={action_request}",
                    "-p",
                    f"timing_bucket:={_adjacent_bucket(strategy_decision)}",
                    "-p",
                    f"target_system:={allocation.px4_instance + 1}",
                ],
            )
        if args.strategy_decision_path is not None:
            start(
                "strategy_action_executor",
                [
                    "python3",
                    "-m",
                    "scripts.runtime.strategy_action_executor",
                    "--run-id",
                    args.run_id,
                    "--decision",
                    str(args.strategy_decision_path),
                    "--lifecycle",
                    str(raw / "workload.lifecycle.jsonl"),
                    "--runner-lifecycle",
                    str(raw / "runner.lifecycle.jsonl"),
                    "--telemetry",
                    str(telemetry),
                    "--request",
                    str(action_request),
                    "--output",
                    str(raw / "strategy.lifecycle.jsonl"),
                ],
            )
        deadline = time.monotonic() + args.attempt_timeout_s
        while time.monotonic() < deadline:
            if (
                args.scheduled_action == "exhaust_registration_capacity"
                and not capacity_started
                and action_request.is_file()
            ):
                # Exhaust the navigation slots while the tested route holds
                # authority, which is the variant a policy can time.
                capacity_started = True
                for duplicate_index in range(8):
                    start(
                        f"external_mode_capacity_{duplicate_index + 1}",
                        capacity_command(duplicate_index),
                    )
            if (
                args.scheduled_action == "restart_producer_after_loss"
                and reclaim_process is None
                and action_request.is_file()
            ):
                # The lost producer cannot restart itself.  This is checked
                # before the producer's exit is noticed, because that notice was
                # measured about eleven seconds late and the aircraft lands
                # first.
                reclaim_process = start("workload_reclaim", reclaim_command)
                lifecycle.append(
                    "producer_restarted", producer_session=reclaim_session
                )
            if decision.exists():
                lifecycle.append("fault_detected", reason="active_safety_stop")
                outcome = "FORMAL_SAFETY_STOP"
                break
            if safety.process.poll() is not None:
                outcome = "ENVIRONMENT_FAILURE"
                break
            if (
                args.manual_land_offset_s is not None
                and _mission_started(telemetry, args.mechanism)
                and _terminal_safe(telemetry)
            ):
                success, reasons = _semantic_success(telemetry, args.mechanism)
                outcome = "ACCEPTED" if success else "INCONCLUSIVE"
                if reasons:
                    lifecycle.append("semantic_rejection", reasons=reasons)
                break
            if workload.process.poll() is not None:
                if args.fault_mode == "process_exit":
                    if not expected_fault_observed:
                        lifecycle.append("fault_detected", reason="source_process_exit")
                        expected_fault_observed = True
                    if observed_fallback_route is None:
                        observed_fallback_route = _latest_safe_route(telemetry)
                        if observed_fallback_route is not None:
                            lifecycle.append(
                                "fallback_triggered", route=observed_fallback_route
                            )
                    if reclaim_process is not None and reclaim_process.process.poll() is None:
                        time.sleep(0.2)
                        continue
                    if _terminal_safe(telemetry):
                        success, reasons = _semantic_success(telemetry, args.mechanism)
                        outcome = "ACCEPTED" if success else "INCONCLUSIVE"
                        if reasons:
                            lifecycle.append("semantic_rejection", reasons=reasons)
                        break
                    # The producer exit is the planned fault stimulus.  Keep
                    # PX4, telemetry, and the independent safety supervisor
                    # alive until the public failsafe reaches a terminal
                    # state or the preregistered attempt timeout expires.
                    time.sleep(0.2)
                    continue
                elif workload.process.returncode == 0:
                    success, reasons = _semantic_success(
                        telemetry,
                        args.mechanism,
                        expected_rejection=args.health_loss,
                    )
                    outcome = "ACCEPTED" if success else "INCONCLUSIVE"
                    if reasons:
                        lifecycle.append("semantic_rejection", reasons=reasons)
                else:
                    outcome = "INCONCLUSIVE"
                break
            unexpected_exits = []
            for item in processes:
                if item in {workload, safety} or item.process.poll() is None:
                    continue
                expected_external_exit = (
                    args.mechanism == "dynamic_external_mode"
                    and args.fault_mode == "process_exit"
                    and item.name == "external_mode"
                    and item.process.returncode == 74
                )
                expected_health_fixture_exit = (
                    args.mechanism == "dynamic_external_mode"
                    and args.health_loss
                    and item.name == "external_mode"
                    and item.process.returncode != 0
                )
                expected_duplicate_rejection = (
                    args.duplicate_registration
                    and item.name.startswith("external_mode_capacity_")
                    and item.process.returncode != 0
                )
                if expected_external_exit:
                    if not expected_fault_observed:
                        lifecycle.append("fault_detected", reason="external_component_exit")
                        expected_fault_observed = True
                    if _terminal_safe(telemetry):
                        success, reasons = _semantic_success(telemetry, args.mechanism)
                        outcome = "ACCEPTED" if success else "INCONCLUSIVE"
                        if reasons:
                            lifecycle.append("semantic_rejection", reasons=reasons)
                        break
                elif expected_health_fixture_exit:
                    pass
                elif expected_duplicate_rejection:
                    pass
                else:
                    unexpected_exits.append(item)
            if outcome in {"ACCEPTED", "INCONCLUSIVE"}:
                break
            if unexpected_exits:
                outcome = "ENVIRONMENT_FAILURE"
                break
            time.sleep(0.2)
        else:
            outcome = "TIMEOUT"

        # Ask PX4 to flush the logger before process-group cleanup.
        subprocess.run(
            [str(px4_source / "build/px4_sitl_default/bin/px4-shutdown"), "--instance", str(allocation.px4_instance)],
            cwd=px4_source,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        time.sleep(1.0)
    except (OSError, RuntimeFailure, subprocess.SubprocessError, ValueError) as exc:
        failure_reason = str(exc)
        outcome = "ENVIRONMENT_FAILURE"
        lifecycle.append("runtime_failure", reason=failure_reason)
    finally:
        for process in reversed(processes):
            process.terminate()
            lifecycle.append(
                "process_stopped", process=process.name, returncode=process.process.returncode
            )

    retained_ulog: str | None = None
    try:
        ulog = _latest_ulog(px4_work)
        shutil.copy2(ulog, raw / "px4.ulg")
        retained_ulog = str(raw / "px4.ulg")
    except (OSError, RuntimeFailure) as exc:
        if failure_reason is None:
            failure_reason = str(exc)
        outcome = "ENVIRONMENT_FAILURE"
        lifecycle.append("evidence_retention_failure", reason=str(exc))
    lifecycle.append("cleanup_completed", outcome=outcome)
    result = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "outcome": outcome,
        "allocation": allocation.as_dict(),
        "ulog": retained_ulog,
    }
    if failure_reason is not None:
        result["failure_reason"] = failure_reason
    _write_new(run_directory / "runtime_result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=Path("/runs"))
    parser.add_argument("--study-id", default="thor-qualification")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--mechanism",
        choices=["legacy_offboard", "dynamic_external_mode", "mode_executor"],
        default="legacy_offboard",
    )
    parser.add_argument(
        "--source-route",
        choices=["px4_internal", "internal_hold", "internal_rtl"],
        default="internal_hold",
    )
    parser.add_argument("--setpoint-kind", choices=["trajectory", "attitude", "body_rate"], default="trajectory")
    parser.add_argument("--fault-mode", choices=["normal", "process_exit", "setpoint_stall"], default="normal")
    parser.add_argument("--health-loss", action="store_true")
    parser.add_argument("--duplicate-registration", action="store_true")
    parser.add_argument(
        "--successor-route",
        choices=["internal_hold", "internal_rtl", "internal_land"],
        default="internal_land",
    )
    parser.add_argument("--repeat-count", type=int, default=1)
    parser.add_argument("--scheduled-action", default="")
    parser.add_argument("--manual-land-offset-s", type=float)
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--cpu-set", default="0-11")
    parser.add_argument("--active-s", type=float, default=8.0)
    parser.add_argument("--stall-after-s", type=float, default=3.0)
    parser.add_argument("--workload-profile", choices=["hover", "straight_line"], default="hover")
    parser.add_argument("--motion-settle-s", type=float, default=1.0)
    parser.add_argument("--motion-speed-m-s", type=float, default=0.75)
    parser.add_argument("--motion-distance-m", type=float, default=3.5)
    parser.add_argument("--motion-entry-progress-m", type=float, default=0.75)
    parser.add_argument("--motion-completion-progress-m", type=float, default=2.5)
    parser.add_argument("--strategy-decision-path", type=Path)
    parser.add_argument("--simulation-seed", type=int, required=True)
    parser.add_argument("--readiness-timeout-s", type=float, default=45.0)
    parser.add_argument("--attempt-timeout-s", type=float, default=60.0)
    parser.add_argument(
        "--safety-limits",
        type=Path,
        default=Path("/opt/uav_sf/config/safety_limits.qualification.json"),
    )
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, RuntimeFailure, subprocess.SubprocessError, ValueError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["outcome"] == "ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
