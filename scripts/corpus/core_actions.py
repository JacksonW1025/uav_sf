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

Precondition = Callable[[SemanticState], bool]
Marker = Callable[[Mapping[str, Any], SemanticState, SemanticState], bool]


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
            "dynamic_external_mode": "port_required",
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
        notes="legacy offboard has no registration protocol, so this is not portable",
    ),
    CoreAction(
        action_id="restart_producer_after_loss",
        inventory_action_id="producer_restart_after_exit",
        summary="Restart the producer after a loss and reclaim authority.",
        lifecycle_phase="fallback",
        availability={
            "legacy_offboard": "new",
            "dynamic_external_mode": "new",
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
        notes=(
            "the only proposed action whose legality depends on the outcome of an "
            "earlier action, which is what separates feedback-guided generation "
            "from feedback-free generation"
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


def core_action_records() -> list[dict[str, Any]]:
    validate_declarations()
    return [action.as_dict() for action in CORE_ACTIONS]
