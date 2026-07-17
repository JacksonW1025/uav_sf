from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/px4_ros2_interface/health_reply_gate.patch"
HELPER = ROOT / "scripts/setup/apply_interface_experiment_patch.sh"


def test_health_reply_patch_is_narrow_and_complete() -> None:
    text = PATCH.read_text(encoding="utf-8")
    changed = {line[6:] for line in text.splitlines() if line.startswith("+++ b/")}
    assert changed == {
        "px4_ros2_cpp/include/px4_ros2/components/health_and_arming_checks.hpp",
        "px4_ros2_cpp/include/px4_ros2/components/mode.hpp",
        "px4_ros2_cpp/src/components/health_and_arming_checks.cpp",
    }
    assert "setArmingCheckReplyEnabled" in text
    assert "_reply_enabled" in text
    assert "if (!_reply_enabled)" in text
    assert HELPER.stat().st_mode & 0o111


def test_health_reply_patch_applies_to_locked_interface_checkout() -> None:
    checkout = ROOT / "ros2_ws/src/px4_ros2_interface_lib"
    if not (checkout / ".git").exists():
        pytest.skip("ignored locked interface checkout not present")
    subprocess.run(
        ["git", "-C", str(checkout), "apply", "--check", str(PATCH)], check=True
    )
