#!/usr/bin/env python3
"""The proposed core action set, as predicates over the semantic state.

Stage 2 selects a minimal representative corpus; this module writes that
selection down in an executable form so it can be checked instead of asserted.
Each core action carries:

* a precondition over the derived semantic state, which is what a closed-loop
  generator would evaluate before choosing the action;
* a marker that recognises the action in retained evidence, so the precondition
  can be replayed against flights that already happened; and
* the cleanup obligation and the contract boundary the action aims at.

Nothing here freezes the corpus.  The selection is signed only after every
action is runtime-selectable and separately qualified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from scripts.state.semantic_state import EXTERNAL_FAMILIES, SemanticState


class CoreActionError(ValueError):
    """A core action declaration is inconsistent with the model."""


MECHANISMS = ("legacy_offboard", "dynamic_external_mode")
AVAILABILITY = ("implemented", "port_required", "not_applicable", "new")
# Markers the in-flight executor can observe today.  An action wired to a live
# backend may only require markers from this set, so its precondition is
# checkable before the action is applied rather than after the fact.
OBSERVABLE_LIVE_MARKERS = (
    "route_active",
    "motion_entered",
    "successor_installed",
    "fallback_installed",
)

Precondition = Callable[[SemanticState], bool]
Marker = Callable[[Mapping[str, Any], SemanticState, SemanticState], bool]


@dataclass(frozen=True)
class LiveActionProfile:
    """How a wired action is applied and what contract it then owes.

    The workload applies the fault mode it was launched with, so selecting an
    action must select the launch parameters and the plan obligations too.
    Otherwise the policy would name one action while the flight performed
    another.
    """

    fault_mode: str
    completion_expected: bool
    fault_expected: bool
    fallback_expected: bool
    workload_phases: tuple[str, ...]
    # How many times the tested route must be entered for this action to be
    # meaningful.  Re-entry needs two entries in one episode.
    repeat_count: int = 1
    # How many times the tested route is entered across the whole episode. A
    # reclaim enters it twice even though each producer session enters once, so
    # this is separate from the repeat count a single producer performs.
    activation_count: int = 1
    # Actions do not share one clock.  A stall is interesting relative to route
    # activation, a re-entry relative to the successor taking over, an adjacent
    # request relative to completion.  Anchoring every action to activation
    # would quietly remove the distinction each one exists to test.
    timing_anchor: str = "route_active"


@dataclass(frozen=True)
class CoreAction:
    """One action proposed for the core corpus."""

    action_id: str
    inventory_action_id: str
    summary: str
    lifecycle_phase: str
    availability: dict[str, str]
    precondition: Precondition
    precondition_text: str
    marker: Marker
    marker_text: str
    cleanup_text: str
    target_boundaries: tuple[str, ...]
    live_markers: tuple[str, ...]
    backend: str | None = None
    live_profile: LiveActionProfile | None = None
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "inventory_action_id": self.inventory_action_id,
            "summary": self.summary,
            "lifecycle_phase": self.lifecycle_phase,
            "availability": dict(sorted(self.availability.items())),
            "precondition": self.precondition_text,
            "marker": self.marker_text,
            "cleanup": self.cleanup_text,
            "target_boundaries": list(self.target_boundaries),
            "live_markers": list(self.live_markers),
            "backend": self.backend,
            "live_profile": (
                {
                    "fault_mode": self.live_profile.fault_mode,
                    "completion_expected": self.live_profile.completion_expected,
                    "fault_expected": self.live_profile.fault_expected,
                    "fallback_expected": self.live_profile.fallback_expected,
                    "workload_phases": list(self.live_profile.workload_phases),
                    "repeat_count": self.live_profile.repeat_count,
                    "activation_count": self.live_profile.activation_count,
                    "timing_anchor": self.live_profile.timing_anchor,
                }
                if self.live_profile is not None
                else None
            ),
            "notes": self.notes,
        }


def _external_authority(state: SemanticState) -> bool:
    return (
        state.route_family in EXTERNAL_FAMILIES
        and state.lineage == "complete"
        and state.phase != "terminal"
    )


def _any_authority(state: SemanticState) -> bool:
    return (
        state.route is not None
        and state.lineage == "complete"
        and state.phase != "terminal"
    )


def _internal_safe_authority(state: SemanticState) -> bool:
    return (
        state.route_family == "internal_safe"
        and state.lineage == "complete"
        and state.phase != "terminal"
    )


CORE_ACTIONS: tuple[CoreAction, ...] = (
    CoreAction(
        action_id="stop_owned_setpoint_stream",
        inventory_action_id="owned_setpoint_stall_healthy",
        summary="Stop the owned setpoint stream while proof-of-life continues.",
        lifecycle_phase="execution",
        availability={
            "legacy_offboard": "implemented",
            "dynamic_external_mode": "implemented",
        },
        precondition=lambda state: _external_authority(state)
        and not state.fault_observed,
        precondition_text=(
            "an external route holds complete authority and no fault has been "
            "observed yet in this episode"
        ),
        marker=lambda event, previous, state: str(event.get("kind")) == "fault_detected"
        and "stall" in str(event.get("reason", "")).lower(),
        marker_text="a fault_detected event whose reason names a stalled stream",
        cleanup_text="release to the preregistered successor and land",
        target_boundaries=("command_stale",),
        live_markers=("route_active", "motion_entered"),
        backend="owned_setpoint_stall_v1",
        live_profile=LiveActionProfile(
            fault_mode="setpoint_stall",
            completion_expected=True,
            fault_expected=True,
            fallback_expected=False,
            workload_phases=(
                "public_takeoff",
                "stable_hover",
                "route_activation",
                "straight_translation",
                "successor_land",
            ),
        ),
    ),
    CoreAction(
        action_id="terminate_owning_producer",
        inventory_action_id="owned_process_exit_fallback",
        summary="Terminate the producer that owns the installed external route.",
        lifecycle_phase="fallback",
        availability={
            "legacy_offboard": "implemented",
            "dynamic_external_mode": "implemented",
        },
        precondition=lambda state: _external_authority(state)
        and not state.fault_observed,
        precondition_text=(
            "an external route holds complete authority and no fault has been "
            "observed yet in this episode"
        ),
        marker=lambda event, previous, state: str(event.get("kind")) == "fault_detected"
        and (
            "exit" in str(event.get("reason", "")).lower()
            or "process" in str(event.get("reason", "")).lower()
        ),
        marker_text="a fault_detected event whose reason names a producer exit",
        cleanup_text="a complete internal safe route must install without operator action",
        target_boundaries=("fallback_installed",),
        live_markers=("route_active", "motion_entered"),
        backend="owned_process_exit_fallback_v1",
        live_profile=LiveActionProfile(
            fault_mode="process_exit",
            completion_expected=False,
            fault_expected=True,
            fallback_expected=True,
            workload_phases=(
                "public_takeoff",
                "stable_hover",
                "route_activation",
                "straight_translation",
                "safe_fallback",
                "successor_land",
            ),
        ),
    ),
    CoreAction(
        action_id="adjacent_land_request",
        inventory_action_id="adjacent_land_request_near_completion",
        summary="Issue a public Land request next to the completion boundary.",
        lifecycle_phase="replacement",
        availability={
            "legacy_offboard": "port_required",
            "dynamic_external_mode": "port_required",
        },
        precondition=_any_authority,
        precondition_text="some route currently holds complete authority",
        marker=lambda event, previous, state: str(event.get("kind")) == "adjacent_request",
        cleanup_text="exactly one successor must win and install completely",
        marker_text="an adjacent_request event",
        target_boundaries=("successor_installed",),
        live_markers=("route_active",),
        notes=(
            "implemented only for the mode executor today; the request itself is a "
            "public Land command, so the port is an anchoring change rather than a "
            "new stimulus"
        ),
    ),
    CoreAction(
        action_id="re_enter_route_after_successor",
        inventory_action_id="route_re_entry_through_hold",
        summary="Request the tested route again while an internal safe route holds authority.",
        lifecycle_phase="re_entry",
        availability={
            "legacy_offboard": "implemented",
            "dynamic_external_mode": "implemented",
        },
        precondition=lambda state: _internal_safe_authority(state)
        and state.completion_observed,
        precondition_text=(
            "a completion has been observed and an internal safe route now holds "
            "complete authority"
        ),
        marker=lambda event, previous, state: str(event.get("kind")) == "transition_requested"
        and int(event.get("cycle") or 0) >= 1,
        marker_text="a transition_requested event the producer recorded as a repeat cycle",
        cleanup_text="the final entry must release to a landing successor",
        target_boundaries=("target_installed", "source_revoked"),
        live_markers=("successor_installed",),
        backend="owned_route_re_entry_v1",
        live_profile=LiveActionProfile(
            fault_mode="normal",
            completion_expected=True,
            fault_expected=False,
            fallback_expected=False,
            workload_phases=(
                "public_takeoff",
                "stable_hover",
                "route_activation",
                "straight_translation",
                "successor_hold",
                "route_re_entry",
                "successor_land",
            ),
            repeat_count=2,
            timing_anchor="successor_installed",
        ),
        notes=(
            "the intermediate safe route is a parameter: the core corpus selects "
            "Hold, while the retained evidence that validates this predicate uses "
            "the RTL variant. The derived re_entry phase is deliberately broader "
            "than this action, because a fixture can enter a route twice without "
            "any tester action; the marker therefore uses the producer's own "
            "recorded cycle rather than the system's observed behaviour. The "
            "dynamic requester has no re-entry loop yet"
        ),
    ),
    CoreAction(
        action_id="withhold_health_reply",
        inventory_action_id="activation_rejection_after_health_loss",
        summary="Withhold the external mode health reply so activation is refused.",
        lifecycle_phase="activation",
        availability={
            "legacy_offboard": "not_applicable",
            "dynamic_external_mode": "implemented",
        },
        precondition=lambda state: state.activation_state == "requested"
        and state.route_family not in EXTERNAL_FAMILIES
        and state.phase != "terminal",
        precondition_text=(
            "activation of the external route has been requested and no external "
            "route holds authority yet"
        ),
        marker=lambda event, previous, state: str(event.get("kind")) == "fault_detected"
        and "reject" in str(event.get("reason", "")).lower(),
        marker_text="a fault_detected event whose reason names a rejection",
        cleanup_text="the vehicle must reach an internal safe route and disarm",
        target_boundaries=("activation_rejected",),
        live_markers=("activation_requested",),
        notes="legacy offboard has no health-reply protocol, so this is not portable",
    ),
    CoreAction(
        action_id="exhaust_registration_capacity",
        inventory_action_id="registration_capacity_rejection",
        summary="Register components until a further registration is refused.",
        lifecycle_phase="registration",
        availability={
            "legacy_offboard": "not_applicable",
            "dynamic_external_mode": "implemented",
        },
        precondition=_any_authority,
        precondition_text="the episode is running and some route holds complete authority",
        marker=lambda event, previous, state: str(event.get("kind")) == "registration"
        and int(event.get("result_code", -1)) == 2,
        marker_text="a registration event whose result code reports a rejection",
        cleanup_text="stop every additional component and keep the primary session consistent",
        target_boundaries=("registration_rejected",),
        live_markers=("route_active",),
        notes="legacy offboard has no registration protocol, so this is not portable",
    ),
    CoreAction(
        action_id="restart_producer_after_loss",
        inventory_action_id="producer_restart_after_exit",
        summary="Restart the producer after a loss and reclaim authority.",
        lifecycle_phase="fallback",
        availability={
            "legacy_offboard": "implemented",
            "dynamic_external_mode": "implemented",
        },
        precondition=lambda state: state.fault_class == "process_exit"
        and _internal_safe_authority(state),
        precondition_text=(
            "a producer loss has been observed and an internal safe route now holds "
            "complete authority"
        ),
        marker=lambda event, previous, state: False,
        marker_text="no retained evidence; the action does not exist yet",
        cleanup_text="either the reclaim installs completely or the safe route is retained",
        target_boundaries=("target_installed",),
        live_markers=("fallback_installed",),
        backend="owned_producer_restart_v1",
        live_profile=LiveActionProfile(
            fault_mode="process_exit",
            completion_expected=True,
            fault_expected=True,
            fallback_expected=True,
            workload_phases=(
                "public_takeoff",
                "stable_hover",
                "route_activation",
                "straight_translation",
                "safe_fallback",
                "route_reclaim",
                "successor_land",
            ),
            repeat_count=1,
            activation_count=2,
            timing_anchor="fallback_installed",
        ),
        notes=(
            "the only proposed action whose legality depends on the outcome of an "
            "earlier action, which is what separates feedback-guided generation "
            "from feedback-free generation. A first attempt found it unreachable "
            "because the runner learned of the producer loss by polling the "
            "process, about eleven seconds after telemetry already showed the "
            "installed safe route, by which time the aircraft had landed. The "
            "loss is now observed from telemetry, which leaves the measured ten "
            "second window; the tested failsafe configuration is unchanged"
        ),
    ),
)


def validate_declarations() -> None:
    """Refuse a declaration that cannot be executed or read back."""

    identifiers: set[str] = set()
    for action in CORE_ACTIONS:
        if action.action_id in identifiers:
            raise CoreActionError(f"duplicate core action: {action.action_id}")
        identifiers.add(action.action_id)
        if set(action.availability) != set(MECHANISMS):
            raise CoreActionError(
                f"{action.action_id}: availability must cover exactly the compared mechanisms"
            )
        for mechanism, status in action.availability.items():
            if status not in AVAILABILITY:
                raise CoreActionError(
                    f"{action.action_id}: unsupported availability {status} for {mechanism}"
                )
        if not action.target_boundaries:
            raise CoreActionError(f"{action.action_id}: a core action must target a boundary")
        if not action.precondition_text.strip() or not action.marker_text.strip():
            raise CoreActionError(f"{action.action_id}: precondition and marker need text")
        # A precondition must be a real restriction: the initial state of an
        # episode may never satisfy it, or the action would be unconditioned.
        if action.precondition(SemanticState()):
            raise CoreActionError(
                f"{action.action_id}: precondition holds in the empty initial state"
            )
        if not action.live_markers:
            raise CoreActionError(f"{action.action_id}: a core action needs a live marker")
        if action.backend is not None and not set(action.live_markers) <= set(
            OBSERVABLE_LIVE_MARKERS
        ):
            raise CoreActionError(
                f"{action.action_id}: a wired action may only require observable markers"
            )
        if (action.backend is None) != (action.live_profile is None):
            raise CoreActionError(
                f"{action.action_id}: a wired action needs a live profile and only a wired action may have one"
            )
        if action.live_profile is not None:
            anchor = action.live_profile.timing_anchor
            if anchor not in action.live_markers:
                raise CoreActionError(
                    f"{action.action_id}: the timing anchor must be one of its live markers"
                )
            if anchor not in OBSERVABLE_LIVE_MARKERS:
                raise CoreActionError(
                    f"{action.action_id}: the timing anchor must be observable in flight"
                )


def core_action(action_id: str) -> CoreAction:
    for action in CORE_ACTIONS:
        if action.action_id == action_id:
            return action
    raise CoreActionError(f"unknown core action: {action_id}")


def wired_actions(mechanism: str) -> tuple[CoreAction, ...]:
    """Core actions that a live backend can apply for this mechanism today."""

    if mechanism not in MECHANISMS:
        raise CoreActionError(f"unsupported mechanism: {mechanism}")
    return tuple(
        action
        for action in CORE_ACTIONS
        if action.backend is not None
        and action.availability[mechanism] == "implemented"
    )


def live_profile(action_id: str) -> LiveActionProfile:
    """How to launch the flight that applies this action."""

    profile = core_action(action_id).live_profile
    if profile is None:
        raise CoreActionError(f"{action_id} has no live backend to apply it")
    return profile


def core_action_records() -> list[dict[str, Any]]:
    validate_declarations()
    return [action.as_dict() for action in CORE_ACTIONS]
