from __future__ import annotations

import copy
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from scripts.fuzzer_v0.family_a import attempt_accounting as accounting
from scripts.fuzzer_v0.family_a import capture_environment
from scripts.fuzzer_v0.family_a import compact_evidence
from scripts.fuzzer_v0.family_a import execution_graph
from scripts.fuzzer_v0.family_a import qualification_freshness_collector
from scripts.fuzzer_v0.family_a import state_space_evaluator as evaluator
from scripts.fuzzer_v0.family_a import strategies
from scripts.fuzzer_v0.family_a.authorization import (
    AuthorizationError,
    verify_authorization,
)
from scripts.fuzzer_v0.family_a.safety_supervisor import (
    SafetySupervisor,
    terminate_attempt_process_group,
)


ROOT = Path(__file__).resolve().parents[1]
GRAPH = (
    ROOT
    / "experiments/fuzzer_v0/family_a/full_readiness/slot_execution_graph.yaml"
)
COMPONENTS = (
    ROOT
    / "experiments/fuzzer_v0/family_a/full_readiness/component_manifest.yaml"
)
RUNNER = ROOT / "scripts/fuzzer_v0/family_a/state_space_evaluator.py"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_unique_runner_help_starts_nothing() -> None:
    process = _run()
    assert process.returncode == evaluator.EXIT_SCOPE
    assert "env-build" in process.stderr


def test_environment_capture_accepts_gazebo_tools_inventory_exit_255(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = subprocess.CompletedProcess(
        ["gz", "--versions"],
        returncode=255,
        stdout="gz <command> [options]\n",
        stderr="",
    )
    monkeypatch.setattr(
        capture_environment.subprocess,
        "run",
        lambda *args, **kwargs: completed,
    )
    assert capture_environment._gazebo_identity() == "gz <command> [options]"


def test_plan_and_preflight_are_static() -> None:
    plan = evaluator.build_plan()
    assert plan["status"] == "STATIC_PLAN_PASS"
    assert plan["slot_count"] == 6
    assert plan["node_count_per_slot"] == 26
    assert plan["comparison_arms_reachable"] is False
    assert plan["runtime_started"] is False
    preflight = evaluator.preflight(require_clean=False)
    assert preflight["status"] == "STATIC_PREFLIGHT_PASS"
    assert preflight["runtime_started"] is False
    assert preflight["formal_attempt_registered"] is False


@pytest.mark.parametrize("slot_id", [f"V0P-S{number}" for number in range(1, 7)])
def test_each_slot_executes_complete_mock_subprocess_graph(
    tmp_path: Path, slot_id: str
) -> None:
    result = execution_graph.execute_fixture(slot_id=slot_id, root=tmp_path / slot_id)
    assert result["status"] == "PASS"
    assert len(result["records"]) == 26
    for record in result["records"]:
        assert Path(record["output"]).is_file()
        assert record["exit_code"] == 0
    required = {
        record["node_id"]
        for record in result["records"]
        if record["applicability"] == "REQUIRED"
    }
    assert required == set(result["invoked_required_nodes"])


def test_graph_preserves_not_applicable_and_comparison_unreachable(
    tmp_path: Path,
) -> None:
    result = execution_graph.execute_fixture(slot_id="V0P-S1", root=tmp_path)
    assert set(result["not_applicable_nodes"]) == {
        "freshness_collector_start",
        "successor_collector_start",
        "linearization_collector_start",
        "freshness_oracle",
        "successor_oracle",
        "linearization_oracle",
    }
    assert execution_graph.validate_graph()["comparison_reachable"] is False


def test_graph_rejects_missing_and_wrong_order(tmp_path: Path) -> None:
    value = yaml.safe_load(GRAPH.read_text(encoding="utf-8"))
    missing = copy.deepcopy(value)
    missing["pipeline"].pop(4)
    missing_path = tmp_path / "missing.yaml"
    missing_path.write_text(yaml.safe_dump(missing), encoding="utf-8")
    with pytest.raises(execution_graph.GraphError, match="missing or out of order"):
        execution_graph.validate_graph(missing_path, COMPONENTS)

    wrong = copy.deepcopy(value)
    wrong["pipeline"][4], wrong["pipeline"][5] = (
        wrong["pipeline"][5],
        wrong["pipeline"][4],
    )
    wrong_path = tmp_path / "wrong.yaml"
    wrong_path.write_text(yaml.safe_dump(wrong), encoding="utf-8")
    with pytest.raises(execution_graph.GraphError, match="missing or out of order"):
        execution_graph.validate_graph(wrong_path, COMPONENTS)


def test_graph_failed_node_stops_downstream(tmp_path: Path) -> None:
    with pytest.raises(execution_graph.GraphError, match="fixture node failed"):
        execution_graph.execute_fixture(
            slot_id="V0P-S3",
            root=tmp_path,
            fail_node="route_oracle",
        )
    assert not (
        tmp_path / "manifests/graph/18-freshness-oracle.json"
    ).exists()


def test_qualification_freshness_mapping_never_defaults_to_pass(
    tmp_path: Path,
) -> None:
    monitor = tmp_path / "monitor.json"
    events = tmp_path / "events.jsonl"
    trace = tmp_path / "route.jsonl"
    clock = tmp_path / "clock.json"
    output = tmp_path / "freshness.json"
    monitor.write_text(
        json.dumps(
            {
                "status": "PASS",
                "setpoint_enabled": False,
                "heartbeat_or_health_enabled": True,
                "physical_recovery": {"altitude_loss_m": 0.1},
            }
        ),
        encoding="utf-8",
    )
    events.write_text("{}\n", encoding="utf-8")
    trace.write_text("{}\n", encoding="utf-8")
    clock.write_text('{"status":"VALID"}\n', encoding="utf-8")
    value = qualification_freshness_collector.collect(
        run_id="FIXTURE",
        fault_type="SETPOINT_ONLY_STALL",
        monitor_result=monitor,
        monitor_events=events,
        route_trace=trace,
        clock_bridge=clock,
        output=output,
    )
    assert value["producer_stopped"] is True
    assert set(value["windows"].values()) == {"INCOMPLETE"}
    assert value["evidence_quality"]["no_default_pass"] is True


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _normal_supervisor(clock: FakeClock) -> SafetySupervisor:
    supervisor = SafetySupervisor(now=clock)
    supervisor.observe({"event_type": "scenario_started"})
    supervisor.observe({"event_type": "monitor_heartbeat"})
    for collector in ("route", "writer_controller", "clock"):
        supervisor.observe(
            {"event_type": "collector_heartbeat", "collector": collector}
        )
    supervisor.observe({"event_type": "clock_observation", "stalled": False})
    supervisor.observe(
        {
            "event_type": "observation",
            "controller_values": [0.0, 0.1],
            "actuator_values": [0.0],
            "altitude_loss_m": 0.1,
            "horizontal_speed_m_s": 0.2,
            "vertical_speed_m_s": 0.1,
            "attitude_excursion_deg": 5.0,
            "body_rate_rad_s": 0.1,
            "unexpected_ground_contact": False,
            "route_epoch_present": True,
            "writer_lineage_present": True,
            "controller_lineage_present": True,
        }
    )
    supervisor.observe(
        {"event_type": "terminal_state", "landed": True, "disarmed": True}
    )
    return supervisor


def test_supervisor_normal_completion() -> None:
    clock = FakeClock()
    supervisor = _normal_supervisor(clock)
    supervisor.observe({"event_type": "scenario_completed"})
    result = supervisor.result()
    assert result["status"] == "SCENARIO_COMPLETED"
    assert result["stop_reason"] is None


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("altitude_loss_m", 1.1, "height_boundary_exceeded"),
        ("horizontal_speed_m_s", 0.6, "horizontal_speed_boundary_exceeded"),
        ("vertical_speed_m_s", 0.6, "vertical_speed_boundary_exceeded"),
        ("attitude_excursion_deg", 46.0, "attitude_boundary_exceeded"),
        ("body_rate_rad_s", 3.1, "body_rate_boundary_exceeded"),
        ("unexpected_ground_contact", True, "unexpected_ground_contact"),
    ],
)
def test_supervisor_every_physical_stop(
    field: str, value: object, reason: str
) -> None:
    clock = FakeClock()
    supervisor = SafetySupervisor(now=clock)
    supervisor.observe({"event_type": "scenario_started"})
    record: dict[str, object] = {
        "event_type": "observation",
        "controller_values": [0.0],
        "actuator_values": [0.0],
        "altitude_loss_m": 0.0,
        "horizontal_speed_m_s": 0.0,
        "vertical_speed_m_s": 0.0,
        "attitude_excursion_deg": 0.0,
        "body_rate_rad_s": 0.0,
        "unexpected_ground_contact": False,
    }
    record[field] = value
    supervisor.observe(record)
    assert supervisor.result()["stop_reason"] == reason


def test_supervisor_monitor_stall_collector_failure_timeout_and_abort() -> None:
    clock = FakeClock()
    monitor = SafetySupervisor(now=clock)
    monitor.observe({"event_type": "scenario_started"})
    clock.advance(2.1)
    monitor.check_time()
    assert monitor.result()["stop_reason"] == "monitor_stall"

    collector = SafetySupervisor(now=clock)
    collector.observe({"event_type": "scenario_started"})
    collector.observe({"event_type": "collector_failure", "collector": "route"})
    assert collector.result()["stop_reason"] == "collector_failure:route"

    timeout = SafetySupervisor(now=clock, scenario_timeout_s=1.0)
    timeout.observe({"event_type": "scenario_started"})
    clock.advance(1.1)
    timeout.check_time()
    assert timeout.result()["stop_reason"] == "runner_timeout"

    abort = SafetySupervisor(now=clock)
    abort.observe({"event_type": "scenario_started"})
    abort.observe({"event_type": "px4_abort"})
    assert abort.result()["stop_reason"] == "PX4_abort"


def test_supervisor_kills_only_attempt_process_group() -> None:
    owned = subprocess.Popen(["sleep", "30"], start_new_session=True)
    unrelated = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        assert terminate_attempt_process_group(os.getpgid(owned.pid)) is True
        owned.wait(timeout=5)
        assert owned.returncode == -signal.SIGTERM
        assert unrelated.poll() is None
    finally:
        if owned.poll() is None:
            os.killpg(os.getpgid(owned.pid), signal.SIGKILL)
            owned.wait()
        if unrelated.poll() is None:
            os.killpg(os.getpgid(unrelated.pid), signal.SIGKILL)
            unrelated.wait()


def _append_full_stream(path: Path, attempt_id: str = "V0P-A1") -> None:
    events = (
        "REGISTERED_PRELAUNCH",
        "AUTHORIZATION_VERIFIED",
        "PREFLIGHT_PASSED",
        "LAUNCH_STARTED",
        "SCENARIO_COMPLETED",
        "COLLECTION_CLOSED",
        "ORACLES_COMPLETED",
        "CLEANUP_COMPLETED",
        "CLASSIFIED",
        "CLOSED",
    )
    for sequence, event_type in enumerate(events):
        accounting.append_event(
            path,
            attempt_id=attempt_id,
            slot_id="V0P-S1",
            seed_id="P0_A_OFFBOARD_ADMISSION",
            event_type=event_type,
            repository_commit="a" * 40,
            authorization_commit="b" * 40,
            registration_commit="c" * 40,
            payload={"event": event_type},
            timestamp=f"2026-07-23T00:00:{sequence:02d}.000000Z",
        )


def test_accounting_append_only_chain_and_closure(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _append_full_stream(path)
    state = accounting.validate_events(accounting._read(path))
    assert state["closed"] is True
    assert state["formal_budget_consumed"] is True
    with pytest.raises(accounting.AccountingError, match="cannot be reopened"):
        accounting.append_event(
            path,
            attempt_id="V0P-A1",
            slot_id="V0P-S1",
            seed_id="P0_A_OFFBOARD_ADMISSION",
            event_type="CLASSIFIED",
            repository_commit="a" * 40,
            authorization_commit="b" * 40,
            registration_commit="c" * 40,
            payload={},
        )


def test_accounting_tamper_launch_before_register_duplicate_and_incomplete(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    with pytest.raises(accounting.AccountingError, match="invalid transition"):
        accounting.append_event(
            path,
            attempt_id="V0P-A1",
            slot_id="V0P-S1",
            seed_id="seed",
            event_type="LAUNCH_STARTED",
            repository_commit="a" * 40,
            authorization_commit="b" * 40,
            registration_commit="c" * 40,
            payload={},
        )
    _append_full_stream(path)
    records = accounting._read(path)
    records[3]["payload"]["tampered"] = True
    path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(accounting.AccountingError, match="payload hash mismatch"):
        accounting.validate_events(accounting._read(path))

    one = tmp_path / "one.jsonl"
    two = tmp_path / "two.jsonl"
    _append_full_stream(one)
    _append_full_stream(two)
    with pytest.raises(accounting.AccountingError, match="duplicate attempt"):
        accounting.aggregate([one, two])

    partial = tmp_path / "partial.jsonl"
    for event_type in (
        "REGISTERED_PRELAUNCH",
        "AUTHORIZATION_VERIFIED",
        "PREFLIGHT_PASSED",
        "LAUNCH_STARTED",
    ):
        accounting.append_event(
            partial,
            attempt_id="V0P-A2",
            slot_id="V0P-S2",
            seed_id="seed",
            event_type=event_type,
            repository_commit="a" * 40,
            authorization_commit="b" * 40,
            registration_commit="c" * 40,
            payload={},
        )
    assert accounting.aggregate([partial])["incomplete_attempts"] == ["V0P-A2"]


def test_accounting_rejection_retained_without_budget_and_attempt_seven_refused(
    tmp_path: Path,
) -> None:
    rejected = tmp_path / "rejected.jsonl"
    for event_type in ("REGISTERED_PRELAUNCH", "REJECTED_PRELAUNCH"):
        accounting.append_event(
            rejected,
            attempt_id="V0P-A1",
            slot_id="V0P-S1",
            seed_id="seed",
            event_type=event_type,
            repository_commit="a" * 40,
            authorization_commit="b" * 40,
            registration_commit="c" * 40,
            payload={"reason": "fixture"},
        )
    aggregate = accounting.aggregate([rejected])
    assert aggregate["formal_attempts"] == 0
    assert aggregate["rejected_prelaunch_attempts"] == 1
    with pytest.raises(accounting.AccountingError, match="invalid attempt ID"):
        accounting.append_event(
            tmp_path / "seven.jsonl",
            attempt_id="V0P-A7",
            slot_id="V0P-S1",
            seed_id="seed",
            event_type="REGISTERED_PRELAUNCH",
            repository_commit="a" * 40,
            authorization_commit="b" * 40,
            registration_commit="c" * 40,
            payload={},
        )


def _compact_fixture(raw_root: Path) -> dict[str, object]:
    artifact = raw_root / "flight.fixture"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("fixture\n", encoding="utf-8")
    identity = {"path": "fixture", "sha256": "a" * 64}
    return {
        "schema_version": "2.0",
        "attempt": {
            "attempt_id": "FIXTURE-EVIDENCE",
            "slot_id": "V0P-S1",
            "seed_id": "FIXTURE_SEED",
        },
        "authorization": identity,
        "registration": identity,
        "source_and_build_identities": [identity],
        "component_identities": [identity],
        "raw_artifacts": [
            {"path": "flight.fixture", "sha256": _sha(artifact), "flushed": True}
        ],
        "clock_bridge": {"status": "VALID", "sha256": "b" * 64},
        "critical_windows": [
            {"window_id": "target", "status": "COMPLETE", "sha256": "c" * 64}
        ],
        "oracles": [
            {
                "oracle_id": "ROUTE",
                "applicability": "REQUIRED",
                "result": "PASS",
                "sha256": "d" * 64,
            },
            {
                "oracle_id": "FRESHNESS",
                "applicability": "NOT_APPLICABLE",
                "result": "NOT_APPLICABLE",
                "sha256": None,
            },
            {
                "oracle_id": "SUCCESSOR",
                "applicability": "NOT_APPLICABLE",
                "result": "NOT_APPLICABLE",
                "sha256": None,
            },
            {
                "oracle_id": "LINEARIZATION",
                "applicability": "NOT_APPLICABLE",
                "result": "NOT_APPLICABLE",
                "sha256": None,
            },
        ],
        "safety": {"completed": True, "result": "PASS", "sha256": "e" * 64},
        "cleanup": {"completed": True, "result": "CLEAN", "sha256": "f" * 64},
        "classification": "ACCEPTED",
        "closure": {"event_type": "CLOSED", "event_hash": "1" * 64},
    }


def test_compact_evidence_complete_and_outcomes_preserved(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    value = _compact_fixture(raw)
    assert compact_evidence.validate(value, raw_root=raw)["classification"] == "ACCEPTED"
    value["oracles"][0]["result"] = "EXPOSURE"
    value["classification"] = "EXPOSURE"
    assert compact_evidence.validate(value)["classification"] == "EXPOSURE"
    value["oracles"][0]["result"] = "UNKNOWN"
    value["classification"] = "UNKNOWN"
    assert compact_evidence.validate(value)["classification"] == "UNKNOWN"


@pytest.mark.parametrize(
    "mutation",
    [
        "raw_hash",
        "clock",
        "window",
        "oracle",
        "safety",
        "cleanup",
        "closure",
    ],
)
def test_compact_evidence_missing_or_invalid_inputs_refused(
    tmp_path: Path, mutation: str
) -> None:
    raw = tmp_path / "raw"
    value = _compact_fixture(raw)
    if mutation == "raw_hash":
        value["raw_artifacts"][0]["sha256"] = "0" * 64
    elif mutation == "clock":
        value["clock_bridge"]["status"] = "INVALID"
    elif mutation == "window":
        value["critical_windows"][0]["status"] = "INCOMPLETE"
    elif mutation == "oracle":
        value["oracles"][0]["result"] = "NOT_APPLICABLE"
        value["oracles"][0]["sha256"] = None
    elif mutation == "safety":
        value["safety"]["completed"] = False
    elif mutation == "cleanup":
        value["cleanup"]["completed"] = False
    else:
        value["closure"]["event_type"] = "CLASSIFIED"
    with pytest.raises(compact_evidence.EvidenceError):
        compact_evidence.validate(value, raw_root=raw)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _authorization_repo(tmp_path: Path) -> tuple[Path, Path, str, Path, str]:
    bare = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "remote", "add", "origin", str(bare))
    full = repo / "full"
    full.mkdir()
    decision = {
        "decision": "APPROVE_QUALIFICATION_ONLY",
        "status": "QUALIFICATION_AUTHORIZED_NOT_STARTED",
        "authorized_scope": "V0_P_QUALIFICATION_ONLY",
        "qualification_runtime_authorized": True,
        "qualification_execution_requires_separate_task": True,
        "comparison_runtime_authorized": False,
        "official_sequence_authorized": False,
        "bounded_random_timing_authorized": False,
        "state_aware_authorized": False,
        "real_workload_authorized": False,
        "family_b_authorized": False,
        "direct_actuator_authorized": False,
        "hitl_authorized": False,
        "real_flight_authorized": False,
    }
    (full / "decision.json").write_text(json.dumps(decision), encoding="utf-8")
    ledger = {
        "formal_attempts": 0,
        "accepted_attempts": 0,
        "attempts": [],
        "next_attempt_id": "V0P-A1",
    }
    (full / "ledger.yaml").write_text(yaml.safe_dump(ledger), encoding="utf-8")
    (full / "asset").write_text("locked\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    manifest = {
        "schema_version": "1.0",
        "manifest_id": "FAMILY_A_V0P_AUTHORIZATION_IDENTITY",
        "identity_lock_policy": "SUPPLIED_COMMIT_MUST_CONTAIN_THIS_EXACT_MANIFEST_BLOB",
        "branch": "main",
        "qualification_target_accepted": 3,
        "qualification_maximum_formal_attempts": 6,
        "comparison_runtime_authorized": False,
        "decision": {"path": "full/decision.json", "sha256": _sha(full / "decision.json")},
        "initial_ledger": {"path": "full/ledger.yaml", "sha256": _sha(full / "ledger.yaml")},
        "commits": {
            "preregistration": base,
            "implementation": base,
            "environment_identity_lock": base,
            "independent_review": base,
        },
        "locked_assets": {
            f"asset_{number}": {"path": "full/asset", "sha256": _sha(full / "asset")}
            for number in range(6)
        },
    }
    manifest_path = full / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "identity lock")
    auth_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "push", "-u", "origin", "main")
    registration = repo / "registration.json"
    registration.write_text('{"attempt_id":"V0P-A1"}\n', encoding="utf-8")
    _git(repo, "add", "registration.json")
    _git(repo, "commit", "-m", "registration")
    registration_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "push", "origin", "main")
    return repo, manifest_path, auth_commit, registration, registration_commit


def test_authorization_accepts_exact_pushed_identity_and_registration(
    tmp_path: Path,
) -> None:
    repo, manifest, auth_commit, registration, registration_commit = (
        _authorization_repo(tmp_path)
    )
    state = verify_authorization(
        repo=repo,
        manifest_path=manifest,
        authorization_commit=auth_commit,
        require_registration_commit=registration_commit,
        registration_path=registration,
    )
    assert state.next_attempt_id == "V0P-A1"
    assert state.repository_commit == registration_commit


def test_authorization_refuses_dirty_wrong_branch_detached_and_hash_mismatch(
    tmp_path: Path,
) -> None:
    repo, manifest, auth_commit, _, _ = _authorization_repo(tmp_path)
    (repo / "dirty").write_text("x", encoding="utf-8")
    with pytest.raises(AuthorizationError, match="clean worktree"):
        verify_authorization(
            repo=repo, manifest_path=manifest, authorization_commit=auth_commit
        )
    (repo / "dirty").unlink()
    _git(repo, "checkout", "-b", "other")
    with pytest.raises(AuthorizationError, match="branch main"):
        verify_authorization(
            repo=repo, manifest_path=manifest, authorization_commit=auth_commit
        )
    _git(repo, "checkout", "main")
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "--detach", head)
    with pytest.raises(AuthorizationError, match="detached"):
        verify_authorization(
            repo=repo, manifest_path=manifest, authorization_commit=auth_commit
        )
    _git(repo, "checkout", "main")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["decision"]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(value), encoding="utf-8")
    _git(repo, "add", str(manifest.relative_to(repo)))
    _git(repo, "commit", "-m", "bad decision hash fixture")
    bad_identity_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "push", "origin", "main")
    with pytest.raises(AuthorizationError, match="activation decision hash mismatch"):
        verify_authorization(
            repo=repo,
            manifest_path=manifest,
            authorization_commit=bad_identity_commit,
        )


def test_authorization_refuses_head_origin_mismatch_and_unpushed_registration(
    tmp_path: Path,
) -> None:
    repo, manifest, auth_commit, registration, _ = _authorization_repo(tmp_path)
    (repo / "local").write_text("x", encoding="utf-8")
    _git(repo, "add", "local")
    _git(repo, "commit", "-m", "local only")
    with pytest.raises(AuthorizationError, match="HEAD must equal"):
        verify_authorization(
            repo=repo, manifest_path=manifest, authorization_commit=auth_commit
        )
    second_root = tmp_path / "second"
    second_root.mkdir()
    repo, manifest, auth_commit, registration, _ = _authorization_repo(second_root)
    with pytest.raises(AuthorizationError, match="registration commit"):
        verify_authorization(
            repo=repo,
            manifest_path=manifest,
            authorization_commit=auth_commit,
            require_registration_commit="d" * 40,
            registration_path=registration,
        )


def test_strategy_common_infrastructure_is_frozen_and_separate(tmp_path: Path) -> None:
    pool = strategies.frozen_seed_pool()
    assert len(pool) == 50
    assert strategies.official_sequence(0) == sorted(
        pool, key=lambda item: item.seed_id
    )[0]
    first = strategies.bounded_random_sequence(pool)
    second = strategies.bounded_random_sequence(pool)
    assert first == second
    assert len(first) == 12
    candidates = [
        {"case": "low", "new_route_epoch_transition": False, "realism_level": "R1"},
        {"case": "high", "new_route_epoch_transition": True, "realism_level": "R1"},
    ]
    assert strategies.choose_state_aware(candidates)["case"] == "high"
    state = tmp_path / "coverage.json"
    strategies.write_coverage_state(state, {"accepted_only": True})
    assert json.loads(state.read_text()) == {"accepted_only": True}
    counts = strategies.validate_arm_ledgers(
        {strategy: [] for strategy in strategies.STRATEGIES}
    )
    assert counts == {strategy: 0 for strategy in strategies.STRATEGIES}
    with pytest.raises(strategies.StrategyError, match="budget"):
        strategies.validate_arm_ledgers(
            {
                "OFFICIAL_SEQUENCE": [{}] * 13,
                "BOUNDED_RANDOM_TIMING_COMPARATOR": [],
                "STATE_AWARE_MUTATION": [],
            }
        )
    with pytest.raises(strategies.StrategyError, match="qualification authorization"):
        strategies.require_comparison_authorization(
            {
                "authorized_scope": "V0_P_QUALIFICATION_ONLY",
                "comparison_runtime_authorized": False,
            },
            "OFFICIAL_SEQUENCE",
        )


def test_environment_locks_have_no_floating_final_base() -> None:
    dockerfile = (
        ROOT / "containers/family_a_fuzzer_v0/Dockerfile"
    ).read_text(encoding="utf-8")
    source_lock = yaml.safe_load(
        (
            ROOT / "containers/family_a_fuzzer_v0/source-commits.lock.yaml"
        ).read_text(encoding="utf-8")
    )
    assert (
        source_lock["base_image"]["oci_index_digest"]
        == "sha256:31daab66eef9139933379fb67159449944f4e2dcf2e22c2d12cc715f29873e0f"
    )
    assert (
        source_lock["base_image"]["linux_arm64_platform_digest"]
        == "sha256:b82a5ba3869a81196414cf34e4fc25c7935aab78b1f5187570ca9362c478cdbd"
    )
    assert "FROM ${BASE_IMAGE}" in dockerfile
    assert "jazzy-ros-base:" not in dockerfile
    assert "linux/arm64" in (
        ROOT / "containers/family_a_fuzzer_v0/docker-bake.hcl"
    ).read_text(encoding="utf-8")


def test_comparison_fixture_refusal_and_formal_execute_boundary() -> None:
    comparison = _run("fixture-execute-refusal")
    assert comparison.returncode == 0
    assert json.loads(comparison.stdout)["status"] == "EXECUTE_REFUSED"
    execute = _run(
        "execute",
        "--attempt-id",
        "V0P-A1",
        "--slot-id",
        "V0P-S1",
        "--seed-id",
        "P0_A_OFFBOARD_ADMISSION",
        "--authorization-commit",
        "a" * 40,
        "--registration-commit",
        "b" * 40,
    )
    assert execute.returncode == evaluator.EXIT_AUTHORIZATION
    assert json.loads(execute.stdout)["runtime_started"] is False
