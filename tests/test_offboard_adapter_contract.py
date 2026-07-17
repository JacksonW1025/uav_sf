from __future__ import annotations

import math

from scripts.adapters.offboard_adapter import OffboardAdapterContract
from scripts.behavior.common_behavior_core import CommonBehaviorCore


def test_proof_of_life_setpoint_and_sequence_are_coupled() -> None:
    contract = OffboardAdapterContract("test.producer", "session-1")
    command = CommonBehaviorCore().command_at(3.5, 1.25)
    first = contract.publication_for(command, 10_000)
    second = contract.publication_for(command, 20_000)
    assert first.publish_sequence == 0
    assert second.publish_sequence == 1
    assert first.proof_of_life["velocity"] is True
    assert first.proof_of_life["position"] is False
    assert first.trajectory_setpoint["timestamp"] == first.producer_timestamp_us
    assert first.trajectory_setpoint["producer_identity"] == "test.producer"
    assert first.trajectory_setpoint["behavior_phase"] == "straight_line"
    assert first.trajectory_setpoint["setpoint_level"] == "velocity"
    assert first.producer_session_id == "session-1"
    assert all(math.isnan(value) for value in first.trajectory_setpoint["position"])


def test_mode_and_release_requests_are_distinct() -> None:
    activate = OffboardAdapterContract.mode_request(1)
    release = OffboardAdapterContract.release_request(2)
    assert activate["event"] == "offboard_mode_requested"
    assert release["event"] == "internal_hold_requested"
    assert activate["param2"] != release["param2"]
