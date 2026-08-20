#!/usr/bin/env python3
"""A policy that chooses in flight and can still be re-derived afterwards.

Every earlier decision surface was computed on the host before the flight, so
the container could recompute it from the same inputs and refuse any
difference.  A decision that depends on what the flight observed cannot work
that way: the host does not have the inputs, and the container is the only
thing that ever will.

The invariant is kept by moving what is frozen.  The host freezes a *policy*:
the strategy, the seed, the episode class and its corpus, the timing bins.  The
flight then applies that policy at each decision point and records the inputs it
applied it to — the observed online state and the admissible set it derived from
that state.  Re-derivation replays the policy over those recorded inputs and
refuses any step whose choice differs.

That leaves exactly one thing the flight is trusted for, and it is named rather
than hidden: the observed state itself.  A step's choice cannot be forged,
because it is recomputed; the state it was made from could be, and is checked
separately by replaying the retained in-flight sidecars through
`scripts/state/online_state.py`.  The admissible set is not trusted at all — it
is recomputed from the recorded state rather than read from the record, so a
flight cannot widen its own options.

Selection is over units, as in the single-action corpus decision: an (action,
timing bin) pair.  `STOP` is a unit too.  A loop that ended because the policy
chose to stop and one that ended because nothing was admissible are different
outcomes, and making the choice explicit keeps them distinguishable instead of
both looking like an episode that ran out of time.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from scripts.corpus.core_actions import core_action
from scripts.corpus.episode_classes import (
    EpisodeClassError,
    episode_class,
    validate_declarations,
)
from scripts.evaluator.strategies import (
    ActionCandidate,
    bounded_random_action,
    choose_state_aware,
    official_sequence,
)
from scripts.runtime.live_strategy_backend import LiveStrategyError, OFFSETS_NS
from scripts.state.online_state import OnlineState


POLICY_SCHEMA = "3.0"
SUPPORTED_STRATEGIES = ("official_sequence", "bounded_random_timing", "state_aware")
# The explicit choice to apply nothing further.  It is a unit so that stopping
# is recorded as a decision rather than inferred from an episode that ended.
STOP = "stop"


def policy_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def official_offset_ns(action_id: str) -> int:
    """The official timing for one action: the middle bin of its own window.

    The single-action decision compared every bin against one global offset,
    because all five surrounded one moment.  Here they do not: a termination's
    bins span the active period and a reclaim's span the ten seconds between
    the fallback and touchdown.  Scoring a reclaim against the termination's
    offset would rank its bins by a property they do not have.
    """

    profile = core_action(action_id).live_profile
    if profile is None or not profile.timing_offsets_ns:
        raise LiveStrategyError(f"{action_id} has no timing bins")
    offsets = profile.timing_offsets_ns
    return int(offsets[len(offsets) // 2])


def _derived_seed(seed: int, *parts: Any) -> int:
    """A reproducible sub-seed for one draw.

    The step index is part of the material, so two decision points in one
    episode do not draw the same value from the same seed.
    """

    material = json.dumps(
        {"seed": seed, "parts": [str(part) for part in parts]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def create_policy(
    *,
    strategy: str,
    seed: int | None,
    mechanism: str,
    class_id: str,
    timing_bounds_ns: dict[str, list[int]],
    covered_units: set[str],
) -> dict[str, Any]:
    """Freeze the policy a flight will apply at each of its decision points."""

    validate_declarations()
    if strategy not in SUPPORTED_STRATEGIES:
        raise LiveStrategyError(f"unsupported live strategy: {strategy}")
    if strategy == "official_sequence" and seed is not None:
        raise LiveStrategyError("official sequence must not use a strategy seed")
    if strategy != "official_sequence" and seed is None:
        raise LiveStrategyError(f"{strategy} requires a seed")
    if not all(isinstance(item, str) for item in covered_units):
        raise LiveStrategyError("covered units must be strings")
    try:
        episode = episode_class(class_id)
        episode.obligations(mechanism)
    except EpisodeClassError as exc:
        raise LiveStrategyError(str(exc)) from exc
    for action_id in episode.actions:
        bounds = timing_bounds_ns.get(action_id)
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise LiveStrategyError(f"{action_id} timing bounds are required")
        lower, upper = bounds
        if not all(isinstance(value, int) for value in bounds) or lower < 0 or upper < lower:
            raise LiveStrategyError(f"{action_id} timing bounds are invalid")
    return {
        "schema_version": POLICY_SCHEMA,
        "strategy": strategy,
        "seed": seed,
        "mechanism": mechanism,
        "class_id": class_id,
        "corpus": list(episode.actions),
        "maximum_steps": episode.maximum_steps,
        "timing_bounds_ns": {
            action_id: list(timing_bounds_ns[action_id]) for action_id in episode.actions
        },
        "official_sequence": list(episode.actions),
        "covered_units_before_episode": sorted(covered_units),
    }


def validate_policy(value: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "strategy",
        "seed",
        "mechanism",
        "class_id",
        "corpus",
        "maximum_steps",
        "timing_bounds_ns",
        "official_sequence",
        "covered_units_before_episode",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise LiveStrategyError("closed-loop policy shape differs")
    if value.get("schema_version") != POLICY_SCHEMA:
        raise LiveStrategyError("closed-loop policy schema differs")
    covered = value.get("covered_units_before_episode")
    if not isinstance(covered, list) or not all(isinstance(item, str) for item in covered):
        raise LiveStrategyError("closed-loop coverage feedback is invalid")
    expected = create_policy(
        strategy=str(value.get("strategy")),
        seed=value.get("seed"),
        mechanism=str(value.get("mechanism")),
        class_id=str(value.get("class_id")),
        timing_bounds_ns=value.get("timing_bounds_ns"),
        covered_units=set(covered),
    )
    if value != expected:
        raise LiveStrategyError("closed-loop policy differs from the registered contract")


def admissible_units(
    policy: dict[str, Any], state: OnlineState, applied: list[str]
) -> list[dict[str, Any]]:
    """Every unit the policy may choose from this state, plus stopping.

    Recomputed from the state rather than read from any record, so a flight
    cannot widen its own options.  An action already applied in this episode is
    not offered again: a repeat would be a second instance of the same unit,
    which the coverage feedback already treats as one.
    """

    units: list[dict[str, Any]] = []
    for action_id in policy["corpus"]:
        if action_id in applied:
            continue
        action = core_action(action_id)
        if action.online_gate is None or not action.online_gate(state):
            continue
        lower, upper = policy["timing_bounds_ns"][action_id]
        profile = action.live_profile
        offsets = profile.timing_offsets_ns if profile is not None else ()
        anchor = profile.timing_anchor if profile is not None else None
        for (boundary, _), offset in zip(OFFSETS_NS, offsets):
            if lower <= offset <= upper:
                units.append(
                    {
                        "action": action_id,
                        "backend": action.backend,
                        "boundary": boundary,
                        "offset_ns": offset,
                        "timing_anchor": anchor,
                        "unit": f"{action_id}:{boundary}",
                    }
                )
    if applied:
        # Stopping is only offered once something has been applied.  The class
        # is launched with its fault mode installed and its plan declares
        # `fault_expected`, which is a two-sided obligation: an episode that
        # applied nothing would produce no fault and violate its own plan. The
        # first action is the class's defining stimulus, not a choice; what
        # follows it is the choice.
        units.append(
            {
                "action": STOP,
                "backend": None,
                "boundary": STOP,
                "offset_ns": 0,
                "timing_anchor": None,
                "unit": STOP,
            }
        )
    return units


def select_step(
    *,
    policy: dict[str, Any],
    step_index: int,
    state: OnlineState,
    applied: list[str],
    covered_units: set[str],
) -> dict[str, Any]:
    """One decision point: what the policy applies next, or that it stops.

    A pure function of the policy, the step index, the observed state and the
    coverage carried into this episode, so replaying it over the recorded
    inputs reproduces the choice exactly.
    """

    if step_index < 0 or step_index >= int(policy["maximum_steps"]):
        raise LiveStrategyError("decision step is outside the policy's bounds")
    units = admissible_units(policy, state, applied)
    actionable = [item for item in units if item["action"] != STOP]
    strategy = policy["strategy"]
    seed = policy["seed"]

    if not actionable:
        stop = next((item for item in units if item["unit"] == STOP), None)
        if stop is None:
            # Nothing admissible and nothing applied yet: the class cannot
            # satisfy its own plan from this state, so the loop fails closed
            # rather than flying an episode that is already a violation.
            raise LiveStrategyError(
                "no admissible unit at the first decision point of the episode"
            )
        selected = stop
    elif strategy == "official_sequence":
        # The official sequence applies its actions in the declared order and
        # never chooses to stop early, so it stays the fixed baseline the other
        # strategies are compared against.
        official_sequence(policy["official_sequence"])
        ordered = [
            item
            for action_id in policy["official_sequence"]
            for item in actionable
            if item["action"] == action_id
        ]
        selected = min(
            ordered,
            key=lambda item: (
                policy["official_sequence"].index(item["action"]),
                abs(item["offset_ns"] - official_offset_ns(item["action"])),
                item["offset_ns"],
            ),
        )
    elif strategy == "bounded_random_timing":
        # Stopping is drawn alongside the actions, so the sequence length
        # varies rather than always running to the class's maximum.
        choices = sorted({item["action"] for item in units})
        action = bounded_random_action(choices, seed=_derived_seed(seed, "action", step_index))
        among = [item for item in units if item["action"] == action]
        if len(among) == 1:
            selected = among[0]
        else:
            index = _derived_seed(seed, "timing", step_index, action) % len(among)
            selected = sorted(among, key=lambda item: item["offset_ns"])[index]
    elif strategy == "state_aware":
        # Stopping covers nothing, so it ranks last while any admissible unit
        # is still uncovered and wins once they all are.
        candidate = choose_state_aware(
            [
                ActionCandidate(
                    name=item["unit"],
                    required_state=(),
                    covers=() if item["unit"] == STOP else (item["unit"],),
                    deadline_distance_ns=(
                        0
                        if item["timing_anchor"] is None
                        else item["offset_ns"] - official_offset_ns(item["action"])
                    ),
                )
                for item in units
            ],
            state={},
            covered_contract_boundaries=covered_units,
            seed=_derived_seed(seed, "state_aware", step_index),
        )
        selected = next(item for item in units if item["unit"] == candidate.name)
    else:
        raise LiveStrategyError(f"unsupported live strategy: {strategy}")

    return {
        "step_index": step_index,
        "observed_state": state.as_dict(),
        "observed_state_key": state.key(),
        "applied_before": list(applied),
        "covered_units_before_step": sorted(covered_units),
        "admissible_units": sorted(item["unit"] for item in units),
        "action": selected["action"],
        "backend": selected["backend"],
        "selected_boundary": selected["boundary"],
        "selected_unit": selected["unit"],
        "planned_offset_ns": selected["offset_ns"],
        "timing_anchor": selected["timing_anchor"],
    }


def replay_decision_log(policy: dict[str, Any], log: dict[str, Any]) -> dict[str, Any]:
    """Re-derive every step from its recorded inputs and refuse a difference.

    The recorded observed state is the input; everything else about the step,
    including the admissible set, is recomputed.  A flight that reported a
    different admissible set, or made a choice the policy would not have made
    from the state it recorded, is refused here rather than believed.
    """

    validate_policy(policy)
    if not isinstance(log, dict) or log.get("schema_version") != POLICY_SCHEMA:
        raise LiveStrategyError("closed-loop decision log schema differs")
    if log.get("policy_digest") != policy_digest(policy):
        raise LiveStrategyError("the decision log was not produced by this policy")
    steps = log.get("steps")
    if not isinstance(steps, list) or not steps:
        raise LiveStrategyError("a closed-loop episode records at least one decision")
    if len(steps) > int(policy["maximum_steps"]):
        raise LiveStrategyError("the decision log exceeds the policy's step bound")

    applied: list[str] = []
    covered = set(policy["covered_units_before_episode"])
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or step.get("step_index") != index:
            raise LiveStrategyError(f"decision step {index} is out of order")
        recorded = step.get("observed_state")
        if not isinstance(recorded, dict):
            raise LiveStrategyError(f"decision step {index} records no observed state")
        try:
            state = OnlineState(**recorded)
        except TypeError as exc:
            raise LiveStrategyError(
                f"decision step {index} records an unreadable observed state"
            ) from exc
        expected = select_step(
            policy=policy,
            step_index=index,
            state=state,
            applied=applied,
            covered_units=covered,
        )
        for field in (
            "action",
            "selected_unit",
            "selected_boundary",
            "planned_offset_ns",
            "timing_anchor",
            "admissible_units",
        ):
            if step.get(field) != expected[field]:
                raise LiveStrategyError(
                    f"decision step {index} differs from the policy on {field}"
                )
        if expected["action"] == STOP:
            if index != len(steps) - 1:
                raise LiveStrategyError("a closed-loop episode records nothing after stopping")
            break
        applied.append(expected["action"])
        covered.add(expected["selected_unit"])
    return {
        "policy_digest": log["policy_digest"],
        "steps_replayed": len(steps),
        "applied_actions": list(applied),
        "stopped_by_choice": steps[-1].get("action") == STOP,
        "covered_units_after_episode": sorted(covered),
    }
