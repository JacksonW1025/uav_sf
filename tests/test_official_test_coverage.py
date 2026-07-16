from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COVERAGE = ROOT / "docs" / "motivation" / "OFFICIAL_TEST_COVERAGE.tsv"
INVENTORY = ROOT / "docs" / "motivation" / "OFFICIAL_EXAMPLE_INVENTORY.tsv"
VALUES = {"YES", "PARTIAL", "NO", "NOT_APPLICABLE", "UNKNOWN"}
CHECKS = (
    "registration", "activation", "basic_execution", "node_loss", "fallback_selection",
    "producer_identity", "freshness", "revocation", "installation", "module_state",
    "writer_identity", "overlap_gap", "reentry_residue", "full_recovery",
)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_official_coverage_values_and_evidence() -> None:
    rows = read_tsv(COVERAGE)
    assert len(rows) >= 15
    for row in rows:
        assert row["test_path"].strip()
        for check in CHECKS:
            assert row[check] in VALUES, (row["test_path"], check, row[check])
        if any(row[check] in {"YES", "PARTIAL"} for check in CHECKS):
            assert row["evidence"].strip()


def test_inventory_is_locked_and_source_specific() -> None:
    rows = read_tsv(INVENTORY)
    assert len(rows) >= 14
    for row in rows:
        assert len(row["commit"]) == 40
        assert row["source_path"].startswith("examples/")
        assert row["build_target"].strip()
        assert row["build_status"] in {"PENDING", "PASS", "FAIL"}
        assert row["run_status"] in {"NOT_RUN", "PASS", "FAIL"}
