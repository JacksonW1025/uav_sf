#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from img_style import COL_SINGLE, OKABE_ITO, save
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "docs/multipolicy_differential_20260703.md"
FIG_NAME = "fig_multipolicy_severity_convergence"
POLICIES = ["P1", "P2", "P3", "P6", "P7"]
TRANSITIONS = ["S0->S3", "S1->S3", "S0->S1", "S1->S1"]
LABELS = {
    "S0->S3": "S0->S3",
    "S1->S3": "S1->S3",
    "S0->S1": "S0->S1",
    "S1->S1": "S1->S1",
}


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator(cells: list[str]) -> bool:
    return all(set(cell) <= {"-", ":"} for cell in cells)


def table_after_heading(path: Path, heading: str) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    while start < len(lines) and not lines[start].lstrip().startswith("|"):
        start += 1
    rows: list[list[str]] = []
    while start < len(lines) and lines[start].lstrip().startswith("|"):
        rows.append(split_row(lines[start]))
        start += 1
    header = rows[0]
    return [dict(zip(header, row)) for row in rows[1:] if not is_separator(row)]


def parse_data() -> dict[str, dict[str, int]]:
    rows = table_after_heading(SOURCE, "## Severity Split")
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        policy = row["policy"]
        if policy not in POLICIES:
            continue
        raw = row["severity pairs among positive evals"].strip("`")
        pairs = json.loads(raw) if raw else {}
        result[policy] = {key: int(pairs.get(key, 0)) for key in TRANSITIONS}
    missing = [policy for policy in POLICIES if policy not in result]
    if missing:
        raise RuntimeError(f"missing policies in severity split table: {missing}")
    return result


def print_provenance(data: dict[str, dict[str, int]]) -> None:
    print(f"SOURCE: {SOURCE.relative_to(REPO_ROOT)}")
    print("TABLE: ## Severity Split")
    print("ROWS: " + ", ".join(POLICIES))
    for policy in POLICIES:
        print(f"VALUE: {policy} severity_pairs={json.dumps(data[policy], sort_keys=True)}")
    print("NOTE: Honest Conclusion states pure non-S3 confirmed P6/P7 groups = 0.")


def main() -> int:
    data = parse_data()
    print_provenance(data)

    x = np.arange(len(POLICIES))
    bottoms = np.zeros(len(POLICIES), dtype=float)
    colors = {
        "S0->S3": OKABE_ITO[6],
        "S1->S3": OKABE_ITO[1],
        "S0->S1": OKABE_ITO[2],
        "S1->S1": OKABE_ITO[3],
    }
    hatches = {
        "S0->S3": "",
        "S1->S3": "///",
        "S0->S1": "\\\\\\",
        "S1->S1": "...",
    }

    fig, ax = plt.subplots(figsize=(COL_SINGLE, 2.35))
    for transition in TRANSITIONS:
        values = np.array([data[policy][transition] for policy in POLICIES], dtype=float)
        ax.bar(
            x,
            values,
            bottom=bottoms,
            width=0.68,
            color=colors[transition],
            edgecolor="black",
            linewidth=0.4,
            hatch=hatches[transition],
            label=LABELS[transition],
        )
        bottoms += values

    ax.set_ylabel("positive evals (count)")
    ax.set_xlabel("policy")
    ax.set_xticks(x, POLICIES)
    ax.set_ylim(0, max(bottoms) * 1.30)
    ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.4)
    ax.legend(
        ncol=2,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.01),
        borderaxespad=0.0,
        handlelength=1.6,
        columnspacing=0.8,
    )
    ax.annotate(
        "pure non-S3\nconfirmed groups = 0",
        xy=(3.6, bottoms[3] * 0.98),
        xytext=(2.25, max(bottoms) * 1.16),
        arrowprops={"arrowstyle": "-", "linewidth": 0.6, "color": "0.25"},
        ha="left",
        va="center",
        fontsize=7,
    )

    save(fig, FIG_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
