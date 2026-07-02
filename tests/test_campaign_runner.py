#!/usr/bin/env python3
from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import campaign_runner  # noqa: E402
import m2_map_elites  # noqa: E402
import theta_genome  # noqa: E402


def base_config(tmp: Path, run_id: str, *, strategy: str = "guided", budget: int = 8) -> campaign_runner.CampaignConfig:
    target = "behavior"
    return campaign_runner.CampaignConfig(
        run_id=run_id,
        run_root=tmp,
        budget=budget,
        bootstrap=2,
        seed=20260627,
        strategy=strategy,
        subspace="steady-wind-physics",
        target_properties=target,
        resolved_target_properties=m2_map_elites.parse_target_properties(target),
        mock_evaluator=True,
        no_confirm=True,
        sim_speed_factor=1.25,
    )


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def genome_trace(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [load_json(result["theta_path"])["theta_genome"]["genome"] for result in state["results"]]


def archive_signature(state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {
            "genome": value["genome"],
            "quality": value["result"]["quality"],
            "feature_bin": value["result"]["feature_bin"],
        }
        for key, value in sorted(state["archive"].items())
    }


class CampaignRunnerTest(unittest.TestCase):
    def assert_steady_combo(self, genome: dict[str, Any]) -> None:
        self.assertEqual(theta_genome.COMBINED_STEADY_DISTURBANCE_TYPE, genome["disturbance_type"])
        self.assertGreater(float(genome["wind_speed_m_s"]), 0.0)
        self.assertGreater(theta_genome.genome_severity(genome)["physics_mismatch"], 0.0)
        theta = theta_genome.theta_from_genome(genome, "unit_combo", 20260627)
        feature = theta["theta_genome"]["map_elites"]
        self.assertEqual(["wind_bucket", "physics_bucket"], feature["feature_dimensions"])

    def test_steady_subspace_candidate_operators_combine_wind_and_physics(self) -> None:
        rng = random.Random(20260627)
        parents = [m2_map_elites.random_candidate_genome("steady-wind-physics", rng) for _ in range(20)]
        mutants = [m2_map_elites.mutate_candidate_genome(parent, "steady-wind-physics", rng) for parent in parents]
        children = [
            m2_map_elites.crossover_candidate_genome(a, b, "steady-wind-physics", rng)
            for a, b in zip(parents, reversed(mutants))
        ]
        for genome in parents + mutants + children:
            self.assert_steady_combo(genome)

    def test_route_a_switching_candidate_operators_use_switch_descriptor(self) -> None:
        rng = random.Random(20260629)
        parents = [m2_map_elites.random_candidate_genome("route-a-switching", rng) for _ in range(20)]
        mutants = [m2_map_elites.mutate_candidate_genome(parent, "route-a-switching", rng) for parent in parents]
        children = [
            m2_map_elites.crossover_candidate_genome(a, b, "route-a-switching", rng)
            for a, b in zip(parents, reversed(mutants))
        ]
        for genome in parents + mutants + children:
            self.assertEqual("switching", genome["disturbance_type"])
            self.assertGreaterEqual(float(genome["switch_roll_pitch_deg"]), m2_map_elites.ROUTE_A_ROLL_PITCH_RANGE[0])
            self.assertLessEqual(float(genome["switch_roll_pitch_deg"]), m2_map_elites.ROUTE_A_ROLL_PITCH_RANGE[1])
            self.assertGreaterEqual(float(genome["switch_rate_rad_s"]), m2_map_elites.ROUTE_A_RATE_RANGE[0])
            self.assertLessEqual(float(genome["switch_rate_rad_s"]), m2_map_elites.ROUTE_A_RATE_RANGE[1])
            self.assertGreaterEqual(float(genome["wind_speed_m_s"]), m2_map_elites.ROUTE_A_WIND_RANGE[0])
            self.assertLessEqual(float(genome["wind_speed_m_s"]), m2_map_elites.ROUTE_A_WIND_RANGE[1])
            theta = theta_genome.theta_from_genome(genome, "unit_route_a", 20260629)
            feature = theta["theta_genome"]["map_elites"]
            self.assertEqual(["switch_roll_pitch_bucket", "wind_bucket"], feature["feature_dimensions"])
            self.assertRegex(feature["wind_bucket"], r"^wind_[0-4]$")

    def test_route_a_grid_has_systematic_switching_cells(self) -> None:
        genomes = campaign_runner.route_a_grid_genomes()
        self.assertEqual(125, len(genomes))
        cells = {
            theta_genome.theta_from_genome(genome, "unit_route_a_grid", 20260629)["theta_genome"]["map_elites"][
                "amplitude_bucket"
            ]
            for genome in genomes
        }
        self.assertGreaterEqual(len(cells), 20)

    def test_resume_matches_uninterrupted_mock_guided_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            full = campaign_runner.run_campaign(base_config(root, "full"), evaluator=m2_map_elites.evaluate_theta)

            first_leg_config = replace(base_config(root, "resumed"), max_evals_this_run=3)
            first_leg = campaign_runner.run_campaign(first_leg_config, evaluator=m2_map_elites.evaluate_theta)
            self.assertEqual(3, first_leg["eval_count"])
            self.assertFalse(first_leg["completed"])

            checkpoint = root / "resumed" / "checkpoint.json"
            resumed_config = replace(base_config(root, "resumed"), max_evals_this_run=0)
            resumed = campaign_runner.run_campaign(
                resumed_config,
                checkpoint=checkpoint,
                evaluator=m2_map_elites.evaluate_theta,
            )

            self.assertEqual(8, full["eval_count"])
            self.assertEqual(8, resumed["eval_count"])
            self.assertTrue(resumed["completed"])
            self.assertEqual(genome_trace(full), genome_trace(resumed))
            self.assertEqual(archive_signature(full), archive_signature(resumed))
            self.assertEqual(full["rng_state"], resumed["rng_state"])

    def test_single_eval_exception_is_recorded_and_campaign_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            def flaky_evaluator(*args: Any, **kwargs: Any) -> m2_map_elites.EvalResult:
                index = int(args[3])
                if index == 1:
                    raise RuntimeError("forced evaluator crash")
                return m2_map_elites.evaluate_theta(*args, **kwargs)

            state = campaign_runner.run_campaign(
                base_config(root, "flaky", budget=4),
                evaluator=flaky_evaluator,
            )
            self.assertEqual(4, state["eval_count"])
            self.assertEqual(4, len(state["results"]))
            self.assertIn("RuntimeError: forced evaluator crash", state["results"][1]["error"])
            self.assertIsNone(state["results"][2]["error"])
            self.assertIn("RuntimeError: forced evaluator crash", state["progress_records"][1]["error"])

    def test_grid_strategy_uses_systematic_baseline_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state = campaign_runner.run_campaign(
                base_config(root, "grid", strategy="grid", budget=6),
                evaluator=m2_map_elites.evaluate_theta,
            )
            self.assertEqual(6, state["eval_count"])
            self.assertTrue(all(item["selection_source"] == "grid_baseline" for item in state["progress_records"]))
            for genome in genome_trace(state):
                self.assert_steady_combo(genome)

    def test_confirmation_properties_are_filtered_to_targets(self) -> None:
        result = {
            "fitness": {
                "target_properties": ["P4", "P6", "P7"],
                "strict_differential_properties": [],
                "clean_differential_properties": [],
                "relative_degradation_differential_properties": ["P2", "P4", "P6"],
            }
        }

        self.assertEqual({"P4", "P6"}, m2_map_elites.robust_properties_from_result(result))
        self.assertEqual(set(), m2_map_elites.strict_properties_from_result(result))
        self.assertEqual({"P4", "P6"}, m2_map_elites.target_relative_degradation_properties(result["fitness"]))
        self.assertEqual(set(), m2_map_elites.target_strict_differential_properties(result["fitness"]))
        self.assertEqual(["P4", "P6"], campaign_runner.property_list(result, "relative_degradation_differential_properties"))

    def test_primary_bug_is_severity_strict_not_property_strict(self) -> None:
        property_only = {
            "fitness": {
                "target_properties": ["P1", "P2"],
                "strict_s0_vs_s3": False,
                "strict_differential_properties": ["P1"],
                "clean_differential_properties": ["P1"],
            }
        }
        severity = {
            "fitness": {
                "target_properties": ["P1", "P2"],
                "strict_s0_vs_s3": True,
                "strict_differential_properties": [],
                "clean_differential_properties": [],
            }
        }

        self.assertFalse(m2_map_elites.severity_primary_from_result(property_only))
        self.assertTrue(m2_map_elites.severity_primary_from_result(severity))
        self.assertEqual(202601, m2_map_elites.confirmation_seed(20260629, 0))


if __name__ == "__main__":
    unittest.main()
