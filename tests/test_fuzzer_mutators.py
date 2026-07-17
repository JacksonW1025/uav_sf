from __future__ import annotations

import json
import random

import pytest

from scripts.fuzzer.case_model import duplicate_fingerprint, validate_case
from scripts.fuzzer.mutators import OPERATORS, mutate
from scripts.fuzzer.scheduler import schedule_guided, schedule_random
from scripts.fuzzer.seed_loader import load_seeds


def parent_case():
    return next(case for case in load_seeds() if case["case_id"] == "p2-dynamic-sigkill")


@pytest.mark.parametrize("operator", sorted(OPERATORS))
def test_each_mutation_operator_is_deterministic_and_schema_valid(operator) -> None:
    left = mutate(parent_case(), rng_seed=911, operator=operator)
    right = mutate(parent_case(), rng_seed=911, operator=operator)
    assert left.operator == operator
    assert left.case == right.case
    validate_case(left.case)
    assert left.case["environment"]["sitl_only"] is True
    assert left.case["environment"]["vehicle"] == "x500"
    assert len(left.case["transition_events"]) <= 12


def test_random_and_guided_schedulers_are_reproducible() -> None:
    seeds = load_seeds()
    random_left = schedule_random(seeds, rng_seed=123)
    random_right = schedule_random(seeds, rng_seed=123)
    assert random_left == random_right
    history = [
        {
            "parent_case_id": seeds[1]["case_id"],
            "fitness": {"validity_tier": 3, "total": 2.0},
            "novelty": {"route_state": 1.0, "transition_sequence": 1.0},
        }
    ]
    guided = schedule_guided(seeds, history, rng_seed=456)
    assert guided.parent_case_id == seeds[1]["case_id"]
    validate_case(guided.mutation.case)


def test_duplicate_fingerprint_is_stable_but_timing_bin_sensitive() -> None:
    first = parent_case()
    same = json.loads(json.dumps(first))
    assert duplicate_fingerprint(first) == duplicate_fingerprint(same)
    same["timing"]["fault_offset_s"] += 1.0
    assert duplicate_fingerprint(first) != duplicate_fingerprint(same)


def test_mutators_never_emit_out_of_envelope_values() -> None:
    case = parent_case()
    for seed in range(100):
        result = mutate(case, rng_seed=seed)
        validate_case(result.case)
        assert all(0 <= event["offset_s"] <= 12 for event in result.case["transition_events"])
        assert result.case["initial_state_constraints"]["maximum_speed_m_s"] <= 2
        assert result.case["environment"]["wind_m_s"] <= 2
