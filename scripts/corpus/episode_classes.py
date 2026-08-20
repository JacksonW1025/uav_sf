#!/usr/bin/env python3
"""Episode classes: what one launch can admit, and what its plan then owes.

A single-action episode derives everything from the one action it was told to
apply — the runtime fault mode, the workload phases, the plan obligations. An
episode that lets the policy choose in flight cannot: the launch happens before
the choice.

An episode class is the unit that can be launched. It fixes what must be fixed
before the flight and leaves the rest to the policy:

* the runtime fault mode, because `fault_expected` is a two-sided obligation.
  A plan that does not expect a fault is violated by observing one, and a plan
  that expects one is violated by its absence, so whether an episode has a
  fault cannot be left to a decision made in the air.
* the plan obligations, as a baseline plus the branch that replaces it when the
  sequence continues. That is what keeps a multi-sequence episode judgeable
  without switching off the contract boundaries its actions aim at.
* the actions the policy may choose between, all of which must share the class's
  fault mode and be wired for the mechanism.

The four classes follow from the corpus rather than being imposed on it:
grouping the seven core actions by expected fault and fault mode yields exactly
one class per group. Only the process_exit class is declared here, because it is
the only one whose second action depends on the outcome of the first, which is
the distinction a closed loop exists to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.corpus.core_actions import CoreActionError, core_action, wired_actions


class EpisodeClassError(ValueError):
    """An episode class cannot be launched or judged as declared."""


# Which internal safe route the failsafe installs after a producer loss differs
# by mechanism, and the successor a workload requests after a completion is a
# different obligation from the fallback the system installs after a fault.
FALLBACK_BY_MECHANISM = {
    "legacy_offboard": "internal_land",
    "dynamic_external_mode": "internal_rtl",
}


@dataclass(frozen=True)
class EpisodeClass:
    """One launchable episode and the sequences it admits."""

    class_id: str
    summary: str
    fault_mode: str
    # In official order. The policy may choose any admissible subset in flight;
    # the official sequence applies them in this order.
    actions: tuple[str, ...]
    mechanisms: tuple[str, ...]
    # Obligations that hold for the sequence that stops at the first action.
    baseline_obligations: dict[str, Any]
    # The condition that selects the other branch, and what it replaces.
    sequence_condition: str
    branch_obligations: dict[str, Any]
    workload_phases: tuple[str, ...]
    workload_profile: str
    injection_phase: str
    notes: str = ""

    @property
    def maximum_steps(self) -> int:
        """One decision point per action the class can apply."""

        return len(self.actions)

    def obligations(self, mechanism: str) -> dict[str, Any]:
        if mechanism not in self.mechanisms:
            raise EpisodeClassError(f"{self.class_id} is not available for {mechanism}")
        return {
            **self.baseline_obligations,
            "expected_fallback": FALLBACK_BY_MECHANISM[mechanism],
        }

    def sequence_obligations(self) -> dict[str, Any]:
        return {
            "condition": self.sequence_condition,
            "when_observed": dict(self.branch_obligations),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "summary": self.summary,
            "fault_mode": self.fault_mode,
            "actions": list(self.actions),
            "mechanisms": list(self.mechanisms),
            "maximum_steps": self.maximum_steps,
            "baseline_obligations": dict(sorted(self.baseline_obligations.items())),
            "sequence_condition": self.sequence_condition,
            "branch_obligations": dict(sorted(self.branch_obligations.items())),
            "workload_phases": list(self.workload_phases),
            "workload_profile": self.workload_profile,
            "injection_phase": self.injection_phase,
            "notes": self.notes,
        }


EPISODE_CLASSES: tuple[EpisodeClass, ...] = (
    EpisodeClass(
        class_id="process_exit_reclaim",
        summary=(
            "Terminate the producer that owns the tested route, then choose in "
            "flight whether to reclaim it."
        ),
        fault_mode="process_exit",
        actions=("terminate_owning_producer", "restart_producer_after_loss"),
        mechanisms=("legacy_offboard", "dynamic_external_mode"),
        baseline_obligations={
            "expected_successor": "internal_land",
            "target_activation_expected": True,
            # Left at one entry deliberately. A reclaim does enter the tested
            # route twice, but the clause that reads this count judges repeated
            # public requests from the declared source route, and a reclaim
            # requests from the internal navigator the failsafe left the
            # vehicle in. Declaring two would give the reclaim an obligation it
            # does not owe; its boundary is target_installed, which the
            # installation clause judges.
            "target_activation_count": [1, 1],
            "registration_rejection_expected": False,
            "activation_rejection_expected": False,
            "completion_expected": False,
            "fault_expected": True,
            "fallback_expected": True,
        },
        sequence_condition="external_route_reclaimed_after_fault",
        branch_obligations={
            "expected_successor": "internal_hold",
            "completion_expected": True,
            # The reclaim preempts the safe route by design, so requiring a
            # completely installed fallback would be self-contradictory.
            "fallback_expected": False,
        },
        workload_phases=(
            "public_takeoff",
            "stable_hover",
            "route_activation",
            "straight_translation",
            "safe_fallback",
            "route_reclaim",
            "successor_land",
        ),
        workload_profile="straight_line",
        injection_phase="straight_translation",
        notes=(
            "the only class whose second action's legality depends on the "
            "outcome of its first, which is what separates feedback-guided "
            "generation from feedback-free generation"
        ),
    ),
)


def validate_declarations() -> None:
    """Refuse a class that cannot be launched as one episode or judged as one."""

    identifiers: set[str] = set()
    for episode in EPISODE_CLASSES:
        if episode.class_id in identifiers:
            raise EpisodeClassError(f"duplicate episode class: {episode.class_id}")
        identifiers.add(episode.class_id)
        if len(episode.actions) < 2:
            raise EpisodeClassError(
                f"{episode.class_id}: a class that carries a sequence needs at least two actions"
            )
        if len(set(episode.actions)) != len(episode.actions):
            raise EpisodeClassError(f"{episode.class_id}: an action is declared twice")
        if not episode.mechanisms:
            raise EpisodeClassError(f"{episode.class_id}: a class needs a mechanism")
        for mechanism in episode.mechanisms:
            if mechanism not in FALLBACK_BY_MECHANISM:
                raise EpisodeClassError(
                    f"{episode.class_id}: unsupported mechanism {mechanism}"
                )
            wired = {action.action_id for action in wired_actions(mechanism)}
            missing = sorted(set(episode.actions) - wired)
            if missing:
                raise EpisodeClassError(
                    f"{episode.class_id}: {mechanism} cannot apply " + ", ".join(missing)
                )
        for action_id in episode.actions:
            try:
                action = core_action(action_id)
            except CoreActionError as exc:
                raise EpisodeClassError(str(exc)) from exc
            profile = action.live_profile
            if profile is None or profile.application != "runtime":
                raise EpisodeClassError(
                    f"{episode.class_id}: {action_id} is not applied during the flight"
                )
            # One launch installs one fault mode, so every action the policy
            # may choose has to be reachable under it.
            if profile.fault_mode != episode.fault_mode:
                raise EpisodeClassError(
                    f"{episode.class_id}: {action_id} needs fault mode "
                    f"{profile.fault_mode}, not {episode.fault_mode}"
                )
            if action.online_gate is None:
                raise EpisodeClassError(
                    f"{episode.class_id}: {action_id} has no in-flight gate to filter on"
                )
        if not episode.branch_obligations:
            raise EpisodeClassError(
                f"{episode.class_id}: a class that carries a sequence needs a branch"
            )
        if all(
            episode.branch_obligations[field] == episode.baseline_obligations.get(field)
            for field in episode.branch_obligations
        ):
            raise EpisodeClassError(
                f"{episode.class_id}: the branch does not differ from the baseline"
            )


def episode_class(class_id: str) -> EpisodeClass:
    for episode in EPISODE_CLASSES:
        if episode.class_id == class_id:
            return episode
    raise EpisodeClassError(f"unknown episode class: {class_id}")


def episode_class_records() -> list[dict[str, Any]]:
    validate_declarations()
    return [episode.as_dict() for episode in EPISODE_CLASSES]
