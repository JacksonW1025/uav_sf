#!/usr/bin/env python3
from __future__ import annotations

import math
import random
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import theta_genome  # noqa: E402


class ThetaGenomeTest(unittest.TestCase):
    def test_random_mutation_and_crossover_are_legal(self) -> None:
        rng = random.Random(20260626)
        parents = [theta_genome.random_genome(rng) for _ in range(200)]
        mutants = [theta_genome.mutate_genome(parent, rng) for parent in parents]
        children = [theta_genome.crossover_genome(a, b, rng) for a, b in zip(parents, reversed(mutants))]
        for genome in parents + mutants + children:
            self.assertEqual([], theta_genome.validate_genome(genome))
            theta = theta_genome.theta_from_genome(genome, "unit_theta", 20260626)
            feature = theta["theta_genome"]["map_elites"]
            self.assertIn(feature["disturbance_type"], theta_genome.SHIM_FREE_DISTURBANCE_TYPES)
            self.assertIn(feature["amplitude_bucket"], {"low", "mid", "high"})

    def test_step_theta_has_p5_sized_command_and_settling_window(self) -> None:
        genome = theta_genome.default_genome("step")
        genome["step_magnitude_m"] = 0.5
        genome["step_axis"] = "y"
        genome["step_sign"] = -1
        genome["step_time_s"] = 34.0
        genome["mission_end_s"] = 50.0
        genome = theta_genome.normalize_genome(genome)
        theta = theta_genome.theta_from_genome(genome, "unit_step", 20260626)
        delta = theta["setpoint"]["step"]["delta_ned"]
        self.assertGreaterEqual(math.sqrt(sum(value * value for value in delta)), 0.5)
        self.assertGreaterEqual(theta["timing"]["mission_end_s"] - theta["setpoint"]["step"]["start_s"], 12.0)

    def test_state_contamination_is_deferred_by_default(self) -> None:
        genome = theta_genome.default_genome("state_contam")
        errors = theta_genome.validate_genome(genome)
        self.assertIn("state_contam is DEFERRED pending m2b shim patch drift", errors)
        self.assertTrue(
            all(not spec.enabled for spec in theta_genome.VARIABLE_SPECS if spec.group == "state_contam")
        )


if __name__ == "__main__":
    unittest.main()
