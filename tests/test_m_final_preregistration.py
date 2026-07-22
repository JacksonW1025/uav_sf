import csv
import hashlib
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
M_FINAL = ROOT / "experiments/motivation/m_final"
CUTOFF = "3665337673e7e0a62ea204ac64f5644b8e428c25"


def load_yaml(name: str):
    return yaml.safe_load((M_FINAL / name).read_text(encoding="utf-8"))


def test_preregistration_freezes_scope_and_authorization():
    prereg = load_yaml("preregistration.yaml")
    assert prereg["study_boundary"]["evidence_cutoff_commit"] == CUTOFF
    assert prereg["study_boundary"]["no_new_runtime_attempts"] is True
    assert prereg["study_boundary"]["no_closed_campaign_reopened"] is True
    assert prereg["oracle_result_rules"] == {
        "unknown_is_pass": False,
        "not_applicable_is_pass": False,
        "exposure_is_violation": False,
        "rejected_attempt_enters_sut_denominator": False,
        "reduced_instrumentation_is_new_independent_defect": False,
    }
    boundary = prereg["authorization_boundary"]
    assert boundary["m_final_may_authorize_next_phase_preregistration_only"] is True
    assert boundary["m_final_executes_next_phase"] is False
    for key in (
        "authorizes_aerostack2_native_adapter",
        "authorizes_family_b_runtime",
        "authorizes_direct_actuator",
        "authorizes_hitl",
        "authorizes_real_flight",
        "authorizes_unprovenanced_random_events",
        "authorizes_large_campaign",
    ):
        assert boundary[key] is False


def test_source_lock_hashes_and_commits_are_present():
    lock = load_yaml("source_lock.yaml")
    assert lock["evidence_cutoff_commit"] == CUTOFF
    assert lock["tracked_raw_files"] == 0
    for artifact in lock["protected_artifacts"]:
        path = ROOT / artifact["path"]
        assert path.exists(), artifact["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
    for commit in lock["source_commits"].values():
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "origin/main"],
            cwd=ROOT,
            check=True,
        )
    assert lock["preregistration_commit"] == "2f20fb0cf140a27ebdb379a08a176c0a929c6125"


def test_gate_matrix_and_ledger_scope_are_complete():
    matrix = load_yaml("gate_matrix.yaml")
    assert list(matrix["clauses"]) == [f"MG{i}" for i in range(1, 11)]
    with (M_FINAL / "evidence_ledger.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 23
    ids = {row["evidence_id"] for row in rows}
    assert len(ids) == len(rows)
    referenced = {
        evidence_id
        for clause in matrix["clauses"].values()
        for evidence_id in clause["primary_evidence"]
    }
    assert referenced <= ids
    for row in rows:
        assert len(row) == 31
        for field in ("report_path", "gate_path", "ledger_path", "summary_path"):
            if row[field] != "NA":
                assert (ROOT / row[field]).exists(), (row["evidence_id"], field)
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", row["final_commit"], "origin/main"],
            cwd=ROOT,
            check=True,
        )
    assert matrix["preregistration_commit"] == "2f20fb0cf140a27ebdb379a08a176c0a929c6125"
