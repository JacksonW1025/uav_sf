from __future__ import annotations

from collections import Counter, defaultdict
import os
from pathlib import Path

import yaml

from scripts.probes import p5_runner
from scripts.probes.p5_runner import (
    PHYSICAL_METRICS,
    _metric_row,
    command_for,
    environment_for,
    execution_plan,
    load_matrix,
    select_run_ids,
)
from scripts.probes.p5_campaign_manifest import reconstruct
from scripts.analysis.p5_compare import compare


def test_p5_core_matrix_has_five_matched_pairs_for_t1_through_t9() -> None:
    matrix = load_matrix()
    rows = execution_plan(matrix)
    assert len(rows) == 9 * 5 * 2
    assert {row["transition_class"] for row in rows} == {f"T{i}" for i in range(1, 10)}
    pairs = defaultdict(list)
    for row in rows:
        pairs[row["pair_id"]].append(row)
    assert len(pairs) == 45
    for pair in pairs.values():
        assert {row["mechanism"] for row in pair} == {
            "legacy_offboard",
            "dynamic_external_mode",
        }
        assert len({row["simulation_seed"] for row in pair}) == 1
        assert len({row["context"] for row in pair}) == 1
        assert len({row["fault_offset_s"] for row in pair}) == 1
    assert Counter(row["repeat"] for row in rows) == {i: 18 for i in range(1, 6)}


def test_p5_preflight_disposition_covers_every_preregistered_cell() -> None:
    root = Path(__file__).resolve().parents[1]
    disposition = yaml.safe_load(
        (root / "experiments/probes/p5/preflight_disposition.yaml").read_text(
            encoding="utf-8"
        )
    )
    matched = set(disposition["matched_cells"])
    not_applicable = {item["cell_id"] for item in disposition["not_applicable"]}
    planned = {cell["cell_id"] for cell in load_matrix()["cells"]}
    assert matched.isdisjoint(not_applicable)
    assert matched | not_applicable == planned
    assert all(item["mechanism_basis"] for item in disposition["not_applicable"])


def test_p5_dispatch_preserves_preregistered_fault_and_channel_actions() -> None:
    rows = execution_plan(load_matrix())
    by_class = {}
    for row in rows:
        by_class.setdefault(row["transition_class"], row)
    assert command_for(by_class["T4"])[-2] == "sigterm"
    assert command_for(by_class["T5"])[-2] == "sigkill"
    assert command_for(by_class["T6"])[-2] == "sigstop_sigcont"
    assert command_for(by_class["T7"])[-3:-1] == ["on", "off"]
    assert command_for(by_class["T8"])[-3:-1] == ["off", "on"]
    assert command_for(by_class["T3"]) is None
    assert command_for(by_class["T9"]) is None


def test_p5_uncertainty_model_keeps_physical_units(tmp_path) -> None:
    (tmp_path / "clock_bridge.json").write_text(
        '{"uncertainty_ns": 42000000}\n', encoding="utf-8"
    )
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw/monitor_result.json").write_text(
        '{"failure_detection_latency_ms": 10, "physical_recovery": '
        '{"altitude_loss_m": 0.2, "peak_tilt_rad": 0.03}}\n',
        encoding="utf-8",
    )
    oracle = {
        "transition": {"timestamp_us": 1000},
        "clauses": {
            "installation": {"metrics": {"first_target_consumption_us": 2000, "first_target_writer_us": 2000, "installation_latency_ms": 1}},
            "revocation": {"metrics": {"revocation_latency_ms": 1}},
            "continuity": {"metrics": {"maximum_unowned_window_ms": 1}},
            "exclusivity": {"metrics": {"old_new_epoch_overlap": False}},
        },
    }
    metrics = _metric_row({"transition_class": "T5"}, tmp_path, oracle)
    assert metrics["failure_detection_latency_ms_uncertainty"] == 42.0
    assert metrics["altitude_loss_m_uncertainty"] == 0.01
    assert metrics["peak_tilt_rad_uncertainty"] == 0.001
    assert PHYSICAL_METRICS == {"altitude_loss_m", "peak_tilt_rad", "position_error_m"}


def test_p5_adaptive_repeat_rule_records_both_trigger_types() -> None:
    rows = []
    for repeat, (legacy, dynamic) in enumerate(((10, 11), (10, 13)), start=1):
        for mechanism, value in (("legacy_offboard", legacy), ("dynamic_external_mode", dynamic)):
            rows.append(
                {
                    "validity": "VALID",
                    "pair_id": f"pair-{repeat}",
                    "cell_id": "cell",
                    "mechanism": mechanism,
                    "metric_ms": str(value),
                    "metric_ms_uncertainty": "5",
                }
            )
    config = {
        "metrics": ["metric_ms"],
        "confidence_interval": {"resamples": 100},
        "adaptation": {
            "initial_paired_repeats": 5,
            "maximum_paired_repeats": 10,
            "increase_when_coefficient_of_variation_exceeds": 0.2,
            "increase_when_difference_below_combined_uncertainty": True,
        },
    }
    result = compare(rows, config)
    comparison = result["comparisons"][0]
    assert comparison["adaptive_repeat_trigger"] is True
    assert comparison["difference_below_combined_uncertainty"] is True
    assert comparison["coefficient_of_variation"] > 0.2
    assert result["adaptive_repeat_decision"]["triggered_cells"] == [
        {
            "cell_id": "cell",
            "reasons": [
                "coefficient_of_variation",
                "difference_below_combined_uncertainty",
            ],
        }
    ]


def test_dynamic_adapter_replaces_hold_for_matched_internal_fallback() -> None:
    root = Path(__file__).resolve().parents[1]
    header = (
        root / "scripts/adapters/external_mode_adapter/include/route_transition_mode.hpp"
    ).read_text(encoding="utf-8")
    assert ".replaceInternalMode(ModeBase::kModeIDLoiter)" in header


def test_p5_runtime_collects_clock_samples_after_backlog_discard(tmp_path) -> None:
    row = next(
        row
        for row in execution_plan(load_matrix())
        if row["transition_class"] == "T5" and row["mechanism"] == "dynamic_external_mode"
    )
    environment = environment_for(row, tmp_path / "campaign", tmp_path / "attempt")
    assert environment["ROUTE_EXPERIMENT_MIN_CLOCK_SAMPLES"] == "40"
    assert environment["ROUTE_EXPERIMENT_BUILD_PROVENANCE"].endswith(
        "experiments/probes/p5/canonical_control_build_provenance.json"
    )
    assert environment["P0_BUILD_PROVENANCE"].endswith(
        "experiments/probes/p5/canonical_control_build_provenance.json"
    )


def test_p5_exact_run_selector_rejects_unknown_ids() -> None:
    rows = execution_plan(load_matrix())
    selected = select_run_ids(rows, ["p5_t5_hover_pair_r1_dynamic_external_mode"])
    assert [row["run_id"] for row in selected] == [
        "p5_t5_hover_pair_r1_dynamic_external_mode"
    ]
    try:
        select_run_ids(rows, ["not-a-run"])
    except ValueError as exc:
        assert "not-a-run" in str(exc)
    else:
        raise AssertionError("unknown run ID was accepted")


def test_dynamic_adapter_unregisters_after_successful_completion() -> None:
    root = Path(__file__).resolve().parents[1]
    header = (
        root / "scripts/adapters/external_mode_adapter/include/route_transition_mode.hpp"
    ).read_text(encoding="utf-8")
    source = (
        root / "scripts/adapters/external_mode_adapter/src/external_mode.cpp"
    ).read_text(encoding="utf-8")
    assert "bool completionReported() const" in header
    assert "node->getMode().completionReported()" in source
    assert source.index("node.reset();") < source.index("rclcpp::shutdown();")


def test_empty_campaign_reconstruction_has_only_pending_pairs(tmp_path: Path) -> None:
    state = reconstruct(tmp_path)
    assert state["planned_applicable_sides"] == 70
    assert state["planned_applicable_pairs"] == 35
    assert state["completed_cells"] == []
    assert state["partially_completed_cells"] == []
    assert len(state["pending_cells"]) == 35


def test_campaign_batch_caps_environment_attempts_and_new_sides(
    tmp_path: Path, monkeypatch
) -> None:
    rows = [
        row
        for row in execution_plan(load_matrix())
        if row["transition_class"] in {"T5", "T6"}
        and row["mechanism"] == "legacy_offboard"
    ][:2]
    monkeypatch.setattr(p5_runner, "command_for", lambda _row: ["/bin/true"])
    monkeypatch.setattr(p5_runner, "ROOT", tmp_path)
    monkeypatch.setattr(p5_runner, "campaign_identity_snapshot", lambda: {"revision": "test"})
    results = p5_runner.execute_plan(
        rows,
        tmp_path,
        5,
        max_new_sides=1,
        max_environment_attempts=3,
        batch_time_limit_seconds=1200,
    )
    assert len(results) == 1
    assert results[0]["validity"] == "BLOCKED_ENVIRONMENT"
    first_attempts = list((tmp_path / rows[0]["run_id"]).glob("**/attempt_result.json"))
    assert len(first_attempts) == 3
    assert not (tmp_path / rows[1]["run_id"]).exists()


def test_campaign_root_is_canonicalized_before_environment_creation(
    tmp_path: Path, monkeypatch
) -> None:
    row = next(
        row
        for row in execution_plan(load_matrix())
        if row["transition_class"] == "T5" and row["mechanism"] == "legacy_offboard"
    )
    observed: list[Path] = []
    monkeypatch.setattr(p5_runner, "ROOT", tmp_path)
    monkeypatch.setattr(p5_runner, "campaign_identity_snapshot", lambda: {"revision": "test"})
    monkeypatch.setattr(p5_runner, "command_for", lambda _row: ["/bin/true"])

    def environment(_row, campaign_root, _attempt_root):
        observed.append(campaign_root)
        return {}

    monkeypatch.setattr(p5_runner, "environment_for", environment)
    relative = Path(os.path.relpath(tmp_path / "campaign", Path.cwd()))
    p5_runner.execute_plan(
        [row], relative, 1, max_new_sides=1, max_environment_attempts=1
    )
    assert observed == [(tmp_path / "campaign").resolve()]
