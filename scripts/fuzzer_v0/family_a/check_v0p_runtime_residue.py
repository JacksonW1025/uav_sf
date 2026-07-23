#!/usr/bin/env python3
"""Read-only V0-P residual-process and occupied-port audit."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
KNOWN_EXECUTABLE_NAMES = {
    "px4",
    "gz",
    "gz-sim",
    "MicroXRCEAgent",
    "ros2",
}
KNOWN_COMMAND_MARKERS = (
    "scripts/probes/run_p0_scenario.sh",
    "scripts/probes/run_p2_scenario.sh",
    "scripts/probes/run_p3_scenario.sh",
    "scripts/probes/run_c1_concurrency.sh",
    "scripts/probes/run_route_experiment.sh",
    "route_trace_collector.py",
    "clock_bridge_collector.py",
    "actuator_writer_collector.py",
)
FORMAL_PORTS = (8888,)
EXIT_CODES = {
    "CLEAN": 0,
    "RESIDUAL_PROCESS": 10,
    "OCCUPIED_PORT": 11,
    "STALE_STATE": 12,
    "INCOMPLETE_RUN_DIRECTORY": 13,
    "UNKNOWN": 20,
}


def _ancestor_pids(pid: int) -> set[int]:
    ancestors = {pid}
    current = pid
    while current > 1:
        try:
            fields = (Path("/proc") / str(current) / "stat").read_text(
                encoding="utf-8"
            ).split()
            current = int(fields[3])
        except (FileNotFoundError, IndexError, ValueError, PermissionError):
            break
        ancestors.add(current)
    return ancestors


def scan_processes() -> list[dict[str, Any]]:
    excluded = _ancestor_pids(os.getpid())
    records: list[dict[str, Any]] = []
    for proc in sorted(Path("/proc").glob("[0-9]*"), key=lambda item: int(item.name)):
        pid = int(proc.name)
        if pid in excluded:
            continue
        try:
            command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            ).strip()
            executable = os.path.basename(os.readlink(proc / "exe"))
            parent = int((proc / "stat").read_text(encoding="utf-8").split()[3])
        except (FileNotFoundError, IndexError, ValueError, PermissionError, OSError):
            continue
        if executable in KNOWN_EXECUTABLE_NAMES or any(
            marker in command for marker in KNOWN_COMMAND_MARKERS
        ):
            records.append(
                {
                    "pid": pid,
                    "ppid": parent,
                    "executable": executable,
                    "command": command,
                }
            )
    return records


def _port_occupied(port: int, socket_type: int) -> bool:
    family_results: list[bool] = []
    for family, address in (
        (socket.AF_INET, ("0.0.0.0", port)),
        (socket.AF_INET6, ("::", port)),
    ):
        try:
            probe = socket.socket(family, socket_type)
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            probe.bind(address)
        except OSError:
            family_results.append(True)
        else:
            family_results.append(False)
        finally:
            try:
                probe.close()
            except UnboundLocalError:
                pass
    return any(family_results)


def scan_ports(ports: Iterable[int] = FORMAL_PORTS) -> list[dict[str, Any]]:
    occupied: list[dict[str, Any]] = []
    for port in ports:
        for protocol, socket_type in (
            ("UDP", socket.SOCK_DGRAM),
            ("TCP", socket.SOCK_STREAM),
        ):
            if _port_occupied(port, socket_type):
                occupied.append({"port": port, "protocol": protocol})
    return occupied


def scan_stale_state(run_dir: Path | None) -> tuple[list[str], list[str]]:
    if run_dir is None or not run_dir.exists():
        return [], []
    stale: list[str] = []
    incomplete: list[str] = []
    for pattern in ("*.pid", "*.lock"):
        stale.extend(
            str(path.relative_to(run_dir))
            for path in sorted(run_dir.rglob(pattern))
            if path.is_file()
        )
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(run_dir))
        if path.name.endswith((".partial", ".tmp")) or path.stat().st_size == 0:
            incomplete.append(relative)
        if "recorder" in path.name.lower() and path.name.endswith(".open"):
            stale.append(relative)
    return stale, incomplete


def evaluate(
    mode: str,
    *,
    fixture: dict[str, Any] | None = None,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    if mode not in {"preflight", "post-attempt"}:
        raise ValueError("mode must be preflight or post-attempt")
    if fixture is None:
        processes = scan_processes()
        ports = scan_ports()
        stale, incomplete = scan_stale_state(run_dir)
    else:
        processes = list(fixture.get("processes", []))
        ports = list(fixture.get("ports", []))
        stale = list(fixture.get("stale_state", []))
        incomplete = list(fixture.get("incomplete_run_directory", []))
    if processes:
        status = "RESIDUAL_PROCESS"
    elif ports:
        status = "OCCUPIED_PORT"
    elif stale:
        status = "STALE_STATE"
    elif incomplete:
        status = "INCOMPLETE_RUN_DIRECTORY"
    else:
        status = "CLEAN"
    return {
        "schema_version": "1.0",
        "mode": mode,
        "status": status,
        "processes": processes,
        "occupied_ports": ports,
        "stale_state": stale,
        "incomplete_run_directory": incomplete,
        "checked_ports": list(FORMAL_PORTS),
        "terminated_processes": [],
        "read_only": True,
        "exit_code": EXIT_CODES[status],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "post-attempt"))
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fixture = (
        json.loads(args.fixture.read_text(encoding="utf-8"))
        if args.fixture is not None
        else None
    )
    result = evaluate(args.mode, fixture=fixture, run_dir=args.run_dir)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return int(result["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
