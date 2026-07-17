from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import yaml

from scripts.probes.p5_runner import execution_plan, load_matrix


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
