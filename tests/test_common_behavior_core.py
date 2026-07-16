from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.behavior.common_behavior_core import BehaviorPhase, CommonBehaviorCore


ROOT = Path(__file__).resolve().parents[1]


def test_behavior_sequence_and_markers() -> None:
    core = CommonBehaviorCore()
    assert core.takeoff_marker(1.0).behavior_phase == BehaviorPhase.TAKEOFF_MARKER.value
    assert core.command_at(0.0, 2.0).behavior_phase == BehaviorPhase.HOVER.value
    assert core.command_at(3.0, 3.0).behavior_phase == BehaviorPhase.STRAIGHT_LINE.value
    assert core.command_at(8.0, 4.0).behavior_phase == BehaviorPhase.LOW_SPEED_TURN.value
    completed = core.command_at(core.duration_seconds, 5.0)
    assert completed.termination_event == "mission_complete"
    assert core.cancel(6.0).termination_event == "cancel"


def test_commands_are_finite_and_low_speed() -> None:
    core = CommonBehaviorCore()
    for elapsed in (0.0, 3.0, 8.0, 10.0):
        command = core.command_at(elapsed, 100.0 + elapsed)
        assert command.velocity is not None
        assert max(abs(value) for value in command.velocity) <= 0.5
    with pytest.raises(ValueError):
        core.command_at(-1.0, 0.0)


def test_common_core_has_no_interface_imports() -> None:
    path = ROOT / "scripts" / "behavior" / "common_behavior_core.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden = ("rclpy", "px4_msgs", "px4_ros2", "raptor", "mc_nn")
    assert not any(any(token in name.lower() for token in forbidden) for name in imported)
