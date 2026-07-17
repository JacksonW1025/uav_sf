from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "px4" / "route_observability" / "route_observability_topics.patch"
BUILD_SCRIPT = ROOT / "scripts" / "setup" / "build_observability_profile.sh"


def _queue_length() -> int:
    match = re.search(
        r"^\+uint8 ORB_QUEUE_LENGTH\s*=\s*([0-9]+)",
        PATCH.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match
    return int(match.group(1))


def test_selected_queue_is_a_supported_power_of_two() -> None:
    value = _queue_length()
    assert value in {1, 4, 8, 16, 32}
    assert value > 0 and value & (value - 1) == 0


@pytest.mark.parametrize("value", [1, 4, 8, 16, 32])
def test_profile_builder_declares_all_benchmark_queue_sizes(value: int) -> None:
    text = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "1|4|8|16|32" in text
    assert f"{value}" in text
