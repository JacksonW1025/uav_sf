#!/usr/bin/env python3
"""Launch one fail-closed SITL attempt in the canonical isolated container."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.runtime.isolation import IDENTIFIER


class ContainerLaunchError(RuntimeError):
    """The host could not establish or close the requested container."""


def _image_identity(image: str) -> dict[str, str]:
    result = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{json .Id}} {{json .Os}} {{json .Architecture}}",
            image,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ContainerLaunchError("image inspection failed: " + result.stderr.strip())
    values = result.stdout.split()
    if len(values) != 3:
        raise ContainerLaunchError("image inspection returned an unexpected identity")
    image_id, operating_system, architecture = (json.loads(value) for value in values)
    if operating_system != "linux" or architecture != "arm64":
        raise ContainerLaunchError("the experiment image is not linux/arm64")
    return {
        "image_id": image_id,
        "operating_system": operating_system,
        "architecture": architecture,
    }


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise ContainerLaunchError(f"refusing to overwrite host driver output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def launch(args: argparse.Namespace) -> dict[str, object]:
    for field in ("study_id", "run_id"):
        if IDENTIFIER.fullmatch(getattr(args, field)) is None:
            raise ContainerLaunchError(f"unsafe {field}")
    run_root = args.run_root.resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    identity = _image_identity(args.image)
    if args.expected_image_id and identity["image_id"] != args.expected_image_id:
        raise ContainerLaunchError("the image ID differs from the frozen environment")
    container_name = f"family-a-{args.study_id}-{args.run_id}"
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--runtime",
        "runc",
        "--network",
        "none",
        "--read-only",
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "--pids-limit",
        str(args.pids_limit),
        "--shm-size",
        args.shm_size,
        "--memory",
        args.memory,
        "--memory-swap",
        args.memory,
        "--cpuset-cpus",
        args.cpu_set,
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=1g",
        "--tmpfs",
        "/var/tmp:rw,nosuid,nodev,size=256m",
        "--env",
        "ROS_LOCALHOST_ONLY=1",
        "--env",
        "GZ_IP=127.0.0.1",
        "--mount",
        # Bind mounts are read-write by default.  The long --mount syntax
        # accepts key=value fields; a bare `rw` is invalid on Docker 27.
        f"type=bind,src={run_root},dst=/runs",
        args.image,
        "python3",
        "-m",
        "scripts.runtime.run_sitl",
        "--run-root",
        "/runs",
        "--study-id",
        args.study_id,
        "--run-id",
        args.run_id,
        "--mechanism",
        args.mechanism,
        "--source-route",
        args.source_route,
        "--setpoint-kind",
        args.setpoint_kind,
        "--fault-mode",
        args.fault_mode,
        "--successor-route",
        args.successor_route,
        "--repeat-count",
        str(args.repeat_count),
        "--slot",
        str(args.slot),
        "--cpu-set",
        args.cpu_set,
        "--active-s",
        str(args.active_s),
        "--simulation-seed",
        str(args.simulation_seed),
        "--readiness-timeout-s",
        str(args.readiness_timeout_s),
        "--attempt-timeout-s",
        str(args.attempt_timeout_s),
        "--safety-limits",
        args.safety_limits,
    ]
    if args.health_loss:
        command.append("--health-loss")
    if args.duplicate_registration:
        command.append("--duplicate-registration")
    if args.manual_land_offset_s is not None:
        command.extend(["--manual-land-offset-s", str(args.manual_land_offset_s)])
    process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=args.outer_timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(
            ["docker", "kill", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        stdout, stderr = process.communicate(timeout=15)
    attempt_root = run_root / args.study_id / args.run_id
    attempt_root.mkdir(parents=True, exist_ok=True)
    _write_new(attempt_root / "container-driver.stdout.log", stdout)
    _write_new(attempt_root / "container-driver.stderr.log", stderr)
    result = {
        "schema_version": "1.0",
        "study_id": args.study_id,
        "run_id": args.run_id,
        "container_name": container_name,
        "container_runtime": "runc",
        "network_mode": "none",
        "image": args.image,
        **identity,
        "returncode": process.returncode,
        "outer_timeout": timed_out,
        "cpu_set": args.cpu_set,
        "memory": args.memory,
    }
    _write_new(
        attempt_root / "container-driver.result.json",
        json.dumps(result, indent=2, sort_keys=True) + "\n",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--expected-image-id")
    parser.add_argument("--run-root", type=Path, default=Path("runs"))
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
    parser.add_argument(
        "--setpoint-kind",
        choices=["trajectory", "attitude", "body_rate"],
        default="trajectory",
    )
    parser.add_argument(
        "--fault-mode",
        choices=["normal", "process_exit", "setpoint_stall"],
        default="normal",
    )
    parser.add_argument("--health-loss", action="store_true")
    parser.add_argument("--duplicate-registration", action="store_true")
    parser.add_argument(
        "--successor-route",
        choices=["internal_hold", "internal_rtl", "internal_land"],
        default="internal_land",
    )
    parser.add_argument("--repeat-count", type=int, default=1)
    parser.add_argument("--manual-land-offset-s", type=float)
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--cpu-set", default="0-11")
    parser.add_argument("--memory", default="24g")
    parser.add_argument("--shm-size", default="1g")
    parser.add_argument("--pids-limit", type=int, default=4096)
    parser.add_argument("--active-s", type=float, default=8.0)
    parser.add_argument("--simulation-seed", type=int, required=True)
    parser.add_argument("--readiness-timeout-s", type=float, default=45.0)
    parser.add_argument("--attempt-timeout-s", type=float, default=60.0)
    parser.add_argument("--outer-timeout-s", type=float, default=130.0)
    parser.add_argument(
        "--safety-limits",
        default="/opt/uav_sf/config/safety_limits.qualification.json",
    )
    args = parser.parse_args()
    try:
        result = launch(args)
    except (OSError, ValueError, ContainerLaunchError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["returncode"] == 0 and not result["outer_timeout"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
