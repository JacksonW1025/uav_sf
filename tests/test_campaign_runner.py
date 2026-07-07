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

    def test_state_contam_subspace_candidate_operators_use_bias_descriptor(self) -> None:
        rng = random.Random(20260703)
        parents = [m2_map_elites.random_candidate_genome("state-contam", rng) for _ in range(20)]
        mutants = [m2_map_elites.mutate_candidate_genome(parent, "state-contam", rng) for parent in parents]
        children = [
            m2_map_elites.crossover_candidate_genome(a, b, "state-contam", rng)
            for a, b in zip(parents, reversed(mutants))
        ]
        for genome in parents + mutants + children:
            self.assertEqual("state_contam", genome["disturbance_type"])
            self.assertEqual(0.0, genome["wind_speed_m_s"])
            self.assertEqual(1.0, genome["mass_scale"])
            theta = theta_genome.theta_from_genome(genome, "unit_state_contam_route", 20260703)
            feature = theta["theta_genome"]["map_elites"]
            self.assertEqual(["velocity_bias_bucket", "angular_rate_bias_bucket"], feature["feature_dimensions"])
            self.assertTrue(theta["environment"]["uses_state_shim"])
            self.assertEqual(1, theta["px4_params"]["M2B_EN"])

    def test_state_contam_theta_requires_state_shim_delivery_gate(self) -> None:
        rng = random.Random(20260703)
        state_genome = m2_map_elites.random_candidate_genome("state-contam", rng)
        state_theta = theta_genome.theta_from_genome(state_genome, "unit_state_contam_delivery", 20260703)
        self.assertTrue(m2_map_elites.requires_state_shim_delivery(state_theta))

        steady_genome = m2_map_elites.random_candidate_genome("steady-wind-physics", rng)
        steady_theta = theta_genome.theta_from_genome(steady_genome, "unit_steady_delivery", 20260703)
        self.assertFalse(m2_map_elites.requires_state_shim_delivery(steady_theta))

    def test_raptor_sut_config_uses_isolated_board_with_groundtruth_installer(self) -> None:
        config = m2_map_elites.sut_config("raptor")

        self.assertEqual("raptor", config.controller)
        self.assertEqual("scripts/build_px4_raptor_sih.sh", str(config.build_script.relative_to(REPO_ROOT)))
        installer_paths = {str(path.relative_to(REPO_ROOT)) for path in config.skip_build_installers}
        self.assertIn("scripts/install_raptor_sih_board.sh", installer_paths)
        self.assertIn("scripts/install_fuzz1b_dds_groundtruth.sh", installer_paths)
        self.assertIn("scripts/install_m2b_state_shim.sh", installer_paths)
        board = (REPO_ROOT / "boards/px4/sitl/raptor_sih.px4board").read_text(encoding="utf-8")
        self.assertIn("CONFIG_MODULES_MC_RAPTOR=y", board)
        self.assertNotIn("CONFIG_MODULES_MC_NN_CONTROL=y", board)
        build_script = (REPO_ROOT / "scripts/build_px4_raptor_sih.sh").read_text(encoding="utf-8")
        self.assertIn("install_fuzz1b_dds_groundtruth.sh", build_script)

    def test_ros_environment_skips_incompatible_repo_overlay_when_ros_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            install = root / "ros2_ws/install"
            (install / "px4_msgs/lib/python9.9").mkdir(parents=True)
            (install / "setup.bash").write_text("# incompatible test overlay\n", encoding="utf-8")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            ros2 = bin_dir / "ros2"
            ros2.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            ros2.chmod(0o755)
            original_root = m2_map_elites.REPO_ROOT
            try:
                m2_map_elites.REPO_ROOT = root
                setup_files = m2_map_elites.ros_setup_files_for_environment({"PATH": str(bin_dir)})
            finally:
                m2_map_elites.REPO_ROOT = original_root

        self.assertEqual([], setup_files)

    def test_ros_overlay_python_compatibility_accepts_current_python_px4_msgs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            install = Path(tmpdir)
            py_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
            (install / "px4_msgs/local/lib" / py_version / "dist-packages").mkdir(parents=True)
            self.assertTrue(m2_map_elites.ros_overlay_supports_current_python(install))

    def test_state_shim_fairness_command_uses_campaign_outputs_and_delivery_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = Path(tmpdir)
            theta_path = docs_dir / "theta.json"
            evidence = {
                "ulog_paths": {
                    "classical": str(docs_dir / "classical.ulg"),
                    "mcnn": str(docs_dir / "mcnn.ulg"),
                },
                "task_paths": {
                    "classical": str(docs_dir / "classical_task.json"),
                    "mcnn": str(docs_dir / "mcnn_task.json"),
                },
            }

            cmd, output, log = m2_map_elites.state_shim_fairness_command(
                theta_path,
                docs_dir,
                "unit_tag",
                evidence,
            )

        self.assertEqual(docs_dir / "state_shim_fairness_unit_tag.json", output)
        self.assertEqual(docs_dir / "state_shim_fairness_unit_tag.log", log)
        self.assertIn("--require-state-shim-delivery", cmd)
        self.assertEqual(str(theta_path), cmd[cmd.index("--theta") + 1])
        self.assertEqual(str(docs_dir / "classical.ulg"), cmd[cmd.index("--classical-ulog") + 1])
        self.assertEqual(str(docs_dir / "mcnn.ulg"), cmd[cmd.index("--raptor-ulog") + 1])
        self.assertEqual(str(docs_dir / "classical_task.json"), cmd[cmd.index("--classical-task-json") + 1])
        self.assertEqual(str(docs_dir / "mcnn_task.json"), cmd[cmd.index("--raptor-task-json") + 1])

    def test_state_shim_fairness_command_uses_selected_neural_controller_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = Path(tmpdir)
            theta_path = docs_dir / "theta.json"
            evidence = {
                "neural_controller": "raptor",
                "ulog_paths": {
                    "classical": str(docs_dir / "classical.ulg"),
                    "raptor": str(docs_dir / "raptor.ulg"),
                },
                "task_paths": {
                    "classical": str(docs_dir / "classical_task.json"),
                    "raptor": str(docs_dir / "raptor_task.json"),
                },
            }

            cmd, _, _ = m2_map_elites.state_shim_fairness_command(theta_path, docs_dir, "unit_tag", evidence)

        self.assertEqual(str(docs_dir / "raptor.ulg"), cmd[cmd.index("--raptor-ulog") + 1])
        self.assertEqual(str(docs_dir / "raptor_task.json"), cmd[cmd.index("--raptor-task-json") + 1])

    def test_evaluate_theta_mock_raptor_uses_raptor_identity_and_property_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            genome = m2_map_elites.random_candidate_genome("route-a-switching", random.Random(20260705))
            theta = theta_genome.theta_from_genome(genome, "unit_raptor_selector", 20260705)
            result = m2_map_elites.evaluate_theta(
                theta,
                root / "theta.json",
                root / "eval",
                0,
                10,
                {},
                m2_map_elites.load_thresholds(None),
                mock_evaluator=True,
                target_properties=m2_map_elites.parse_target_properties("route-a-catastrophic"),
                sut="raptor",
            )
            comparison = load_json(result.compare_path)

        self.assertEqual(0, result.returncode)
        self.assertEqual("raptor", result.sut)
        self.assertEqual("raptor", result.neural_controller)
        self.assertTrue(result.neural_confirmed)
        self.assertEqual("raptor", comparison["property_oracle"]["neural"]["controller"])
        self.assertIn("raptor", result.evidence["property_paths"])
        self.assertIn("raptor_identity", result.evidence["validity"])
        self.assertNotIn("mcnn_identity", result.evidence["validity"])

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

    def test_fitness_mode_reaches_evaluator_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = "route-a-catastrophic"
            config = campaign_runner.CampaignConfig(
                run_id="absolute_mode",
                run_root=root,
                budget=1,
                bootstrap=1,
                seed=20260629,
                strategy="guided",
                subspace="route-a-switching",
                target_properties=target,
                resolved_target_properties=m2_map_elites.parse_target_properties(target),
                mock_evaluator=True,
                no_confirm=True,
                sim_speed_factor=1.25,
                fitness_mode="absolute_severity",
            )
            seen: list[str] = []

            def capture_evaluator(*args: Any, **kwargs: Any) -> m2_map_elites.EvalResult:
                seen.append(str(kwargs.get("fitness_mode")))
                return m2_map_elites.evaluate_theta(*args, **kwargs)

            state = campaign_runner.run_campaign(config, evaluator=capture_evaluator)

        self.assertEqual(["absolute_severity"], seen)
        self.assertEqual("absolute_severity", state["metadata"]["fitness_mode"])
        self.assertEqual("absolute_severity", state["results"][0]["fitness"]["fitness_mode"])

    def test_sut_reaches_evaluator_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = campaign_runner.CampaignConfig(
                run_id="raptor_mode",
                run_root=root,
                budget=1,
                bootstrap=1,
                seed=20260705,
                strategy="guided",
                subspace="route-a-switching",
                target_properties="route-a-catastrophic",
                resolved_target_properties=m2_map_elites.parse_target_properties("route-a-catastrophic"),
                mock_evaluator=True,
                no_confirm=True,
                sim_speed_factor=1.25,
                sut="raptor",
            )
            seen: list[str] = []

            def capture_evaluator(*args: Any, **kwargs: Any) -> m2_map_elites.EvalResult:
                seen.append(str(kwargs.get("sut")))
                return m2_map_elites.evaluate_theta(*args, **kwargs)

            state = campaign_runner.run_campaign(config, evaluator=capture_evaluator)

        self.assertEqual(["raptor"], seen)
        self.assertEqual("raptor", state["metadata"]["sut"])
        self.assertEqual("RAPTOR mc_raptor mode 23 (original clipped inputs)", state["metadata"]["neural_controller"])
        self.assertEqual("raptor", state["results"][0]["sut"])
        self.assertEqual("raptor", state["results"][0]["neural_controller"])

    def test_guided_abs_strategy_alias_sets_absolute_fitness_mode(self) -> None:
        parser = campaign_runner.build_parser()
        args = parser.parse_args(["--run-id", "alias", "--strategy", "guided_abs"])
        config = campaign_runner.resolve_new_config(args)

        self.assertEqual("guided", config.strategy)
        self.assertEqual("absolute_severity", config.fitness_mode)

    def test_cli_accepts_raptor_sut_selector(self) -> None:
        parser = campaign_runner.build_parser()
        args = parser.parse_args(["--run-id", "sut", "--sut", "raptor"])
        config = campaign_runner.resolve_new_config(args)

        self.assertEqual("raptor", config.sut)

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

    def test_relative_degradation_results_are_queued_for_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = base_config(Path(tmpdir), "reportable_queue")
            state = campaign_runner.new_state(config, random.Random(config.seed))
            result = m2_map_elites.EvalResult(
                index=0,
                tag="relative_e0000",
                theta_path=str(Path(tmpdir) / "theta.json"),
                docs_dir=str(Path(tmpdir) / "evals"),
                returncode=0,
                elapsed_wall_s=1.0,
                compare_path=None,
                quadrant="relative_degradation_differential",
                primary_bug=False,
                classical_usable=True,
                classical_safe=True,
                raptor_safe=True,
                infrastructure_limited=False,
                quality=2.0,
                fitness={
                    "fitness": 2.0,
                    "target_properties": ["P2", "P4"],
                    "strict_s0_vs_s3": False,
                    "strict_differential_properties": [],
                    "relative_degradation_differential_properties": ["P2", "P4"],
                    "per_property": {},
                },
                feature_bin="state_contam:vel_2:gyro_4",
                severity=0.5,
                seed=20260703,
                evidence={},
            )

            campaign_runner.update_state_after_eval(config, state, result, {"disturbance_type": "state_contam"}, "random")

        self.assertEqual(0, len(state["primary_candidates"]))
        self.assertEqual(1, len(state["reportable_candidates"]))
        self.assertEqual("relative_e0000", state["reportable_candidates"][0]["result"]["tag"])

    def test_run_confirmations_uses_reportable_candidates_without_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(base_config(Path(tmpdir), "confirm_reportable"), no_confirm=False)
            state = campaign_runner.new_state(config, random.Random(config.seed))
            state["completed"] = True
            state["primary_candidates"] = []
            state["reportable_candidates"] = [{"result": {"tag": "relative_e0000", "quality": 2.0}}]
            called: dict[str, Any] = {}
            original = m2_map_elites.confirm_candidates

            def fake_confirm(run_dir: Path, candidates: list[dict[str, Any]], args: Any) -> list[dict[str, Any]]:
                called["run_dir"] = run_dir
                called["candidates"] = candidates
                return [{"passed": True}]

            try:
                m2_map_elites.confirm_candidates = fake_confirm
                campaign_runner.run_confirmations(config, state, random.Random(config.seed))
            finally:
                m2_map_elites.confirm_candidates = original

        self.assertEqual(["relative_e0000"], [item["result"]["tag"] for item in called["candidates"]])
        self.assertEqual([{"passed": True}], state["confirmed"])


if __name__ == "__main__":
    unittest.main()
