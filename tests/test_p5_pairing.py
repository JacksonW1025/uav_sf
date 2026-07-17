from __future__ import annotations

from collections import Counter, defaultdict

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
