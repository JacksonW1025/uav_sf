#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import multipolicy_differential as multipolicy  # noqa: E402


def record(
    *,
    tag: str,
    policy: str,
    seed: int,
    candidate_tag: str = "candidate_a",
    cell: str = "switching:rp_4:wind_4",
) -> dict[str, object]:
    return {
        "source_kind": "confirmation",
        "candidate_tag": candidate_tag,
        "tag": tag,
        "seed": seed,
        "cell": cell,
        "valid": True,
        "policy_findings": {
            "positive_policies": [policy],
            "by_policy": {policy: {"finding": True, "neural_violation_margin": 1.0}},
        },
    }


class MultipolicyDifferentialTest(unittest.TestCase):
    def test_workspace_paths_are_mapped_to_repo_root(self) -> None:
        path = multipolicy.repo_path("/workspace/runs/campaigns/example/evals/a.json")

        self.assertEqual(REPO_ROOT / "runs/campaigns/example/evals/a.json", path)

    def test_confirmation_groups_require_same_policy_hits(self) -> None:
        records = [
            record(tag="r1", policy="P6", seed=1),
            record(tag="r2", policy="P6", seed=2),
            record(tag="r3", policy="P7", seed=3),
        ]

        groups = multipolicy.confirmation_groups(records, required_hits_fraction=2.0 / 3.0)
        p6 = groups[("P6", "switching:rp_4:wind_4", "candidate_a")]
        p7 = groups[("P7", "switching:rp_4:wind_4", "candidate_a")]

        self.assertTrue(p6["confirmed"])
        self.assertEqual(2, p6["hits"])
        self.assertEqual([1, 2], p6["hit_seeds"])
        self.assertFalse(p7["confirmed"])
        self.assertEqual(1, p7["hits"])


if __name__ == "__main__":
    unittest.main()
