#!/usr/bin/env python3
"""Deterministic, collision-free identities for parallel SITL attempts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class IsolationAllocation:
    study_id: str
    attempt_id: str
    slot: int
    px4_instance: int
    vehicle_identity: str
    gazebo_partition: str
    ros_domain_id: int
    xrce_agent_port: int
    mavlink_udp_local_port: int
    mavlink_udp_port: int
    mavlink_tcp_port: int
    run_directory: str
    temporary_directory: str
    process_group_identity: str
    cpu_set: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def allocate_isolation(
    *,
    study_id: str,
    attempt_id: str,
    slot: int,
    run_root: Path,
    cpu_sets: list[str],
    ros_domain_base: int = 40,
    xrce_port_base: int = 8888,
    mavlink_udp_local_base: int = 14580,
    mavlink_udp_base: int = 14540,
    mavlink_tcp_base: int = 4560,
) -> IsolationAllocation:
    for name, value in (("study_id", study_id), ("attempt_id", attempt_id)):
        if IDENTIFIER.fullmatch(value) is None:
            raise ValueError(f"{name} has an unsafe identity")
    if slot < 0 or slot >= len(cpu_sets):
        raise ValueError("slot has no configured CPU allocation")
    domain = ros_domain_base + slot
    if not 0 <= domain <= 232:
        raise ValueError("ROS domain is outside the portable range")
    for port in (
        xrce_port_base + slot,
        mavlink_udp_local_base + slot,
        mavlink_udp_base + slot,
        mavlink_tcp_base + slot,
    ):
        if not 1024 <= port <= 65535:
            raise ValueError("allocated port is outside the non-privileged range")
    attempt_root = (run_root / study_id / attempt_id).resolve()
    if run_root.resolve() not in attempt_root.parents:
        raise ValueError("attempt directory escapes the configured run root")
    return IsolationAllocation(
        study_id=study_id,
        attempt_id=attempt_id,
        slot=slot,
        px4_instance=slot,
        # PX4's gz_x500 startup rule materializes this exact Gazebo entity.
        vehicle_identity=f"x500_{slot}",
        gazebo_partition=f"family_a_{study_id}_{slot}",
        ros_domain_id=domain,
        xrce_agent_port=xrce_port_base + slot,
        # These offsets deliberately mirror PX4's rcS rules.  An allocation
        # is evidence about the ports actually used by the instance, not a
        # merely collision-free reservation from a different range.
        mavlink_udp_local_port=mavlink_udp_local_base + slot,
        mavlink_udp_port=mavlink_udp_base + slot,
        mavlink_tcp_port=mavlink_tcp_base + slot,
        run_directory=str(attempt_root),
        temporary_directory=str(attempt_root / "tmp"),
        process_group_identity=f"family-a-{attempt_id}",
        cpu_set=cpu_sets[slot],
    )


def verify_unique(allocations: Iterable[IsolationAllocation]) -> None:
    values = list(allocations)
    fields = (
        "attempt_id",
        "px4_instance",
        "vehicle_identity",
        "gazebo_partition",
        "ros_domain_id",
        "xrce_agent_port",
        "mavlink_udp_local_port",
        "mavlink_udp_port",
        "mavlink_tcp_port",
        "run_directory",
        "temporary_directory",
        "process_group_identity",
    )
    for field in fields:
        observed = [getattr(value, field) for value in values]
        if len(observed) != len(set(observed)):
            raise ValueError(f"parallel allocation collides on {field}")
