"""Evidence-first Fuzzer v0 validity and SUT outcome classification."""

from __future__ import annotations

from typing import Any


REQUIRED_CHECKS = (
    "armed",
    "source_route_activated",
    "fault_delivered",
    "target_or_fallback_observed",
    "clock_bridge",
    "critical_window",
    "px4_alive",
    "gazebo_alive",
    "ulog_produced",
)


def _failed(checks: dict[str, str], names: set[str]) -> bool:
    return any(checks.get(name) == "FAIL" for name in names)


def classify_pre_oracle(
    checks: dict[str, str], *, input_valid: bool = True, setup_valid: bool = True
) -> tuple[str, str | None]:
    if not input_valid:
        return "INVALID_INPUT", "case schema or transition grammar failed"
    if not setup_valid or _failed(
        checks, {"armed", "source_route_activated", "fault_delivered", "target_or_fallback_observed"}
    ):
        return "INVALID_SETUP", "required initial state or requested event was not established"
    if _failed(checks, {"px4_alive", "gazebo_alive", "ulog_produced"}):
        return "ENVIRONMENT_FAILURE", "SITL process or required source artifact failed"
    if _failed(checks, {"clock_bridge", "critical_window"}) or any(
        checks.get(name) == "UNKNOWN" for name in REQUIRED_CHECKS
    ):
        return "MEASUREMENT_UNKNOWN", "required measurement evidence is incomplete"
    if any(checks.get(name) not in {"PASS", "NOT_APPLICABLE"} for name in REQUIRED_CHECKS):
        return "MEASUREMENT_UNKNOWN", "required validity check is absent"
    return "VALID", None


def classify_with_oracle(
    checks: dict[str, str], oracle: dict[str, Any] | None, *, input_valid: bool = True,
    setup_valid: bool = True,
) -> tuple[str, str | None]:
    classification, reason = classify_pre_oracle(
        checks, input_valid=input_valid, setup_valid=setup_valid
    )
    if classification != "VALID":
        return classification, reason
    if oracle is None or oracle.get("status") == "UNKNOWN":
        return "MEASUREMENT_UNKNOWN", "oracle did not have sufficient evidence"
    clauses = oracle.get("clauses", {})
    if oracle.get("status") == "VIOLATION" or any(
        clause.get("status") == "VIOLATION" for clause in clauses.values()
        if isinstance(clause, dict)
    ):
        return "SUT_VIOLATION", None
    if oracle.get("status") in {"PASS", "NOT_APPLICABLE"}:
        return "SUT_PASS", None
    return "MEASUREMENT_UNKNOWN", f"unsupported oracle status: {oracle.get('status')}"
