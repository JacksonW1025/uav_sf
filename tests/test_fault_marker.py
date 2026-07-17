from __future__ import annotations

import pytest

from scripts.probes.fault_marker import make_marker


def test_fault_marker_preserves_bounds_and_does_not_claim_exact_signal_time() -> None:
    marker = make_marker(
        "m-1",
        fault_class="sigkill",
        target_session="producer-1",
        host_before_ns=100,
        host_after_ns=140,
        lower_px4_us=10.0,
        upper_px4_us=12.5,
        px4_receipt_us=11.0,
        route_epoch_id=7,
    )
    assert marker["fault_time_uncertainty_us"] == 2.5
    assert marker["px4_receipt_time_us"] == 11.0
    assert "fault_time_px4_us" not in marker


def test_fault_marker_rejects_reversed_bounds_and_marks_missing_map_unknown() -> None:
    with pytest.raises(ValueError):
        make_marker(
            "bad",
            fault_class="pause",
            target_session="p",
            host_before_ns=2,
            host_after_ns=1,
            lower_px4_us=None,
            upper_px4_us=None,
            px4_receipt_us=None,
            route_epoch_id=None,
        )
    unknown = make_marker(
        "unknown",
        fault_class="pause",
        target_session="p",
        host_before_ns=1,
        host_after_ns=2,
        lower_px4_us=None,
        upper_px4_us=None,
        px4_receipt_us=None,
        route_epoch_id=None,
    )
    assert unknown["measurement_status"] == "UNKNOWN_NO_CLOCK_MAP"
