#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from img_style import COL_SINGLE, OKABE_ITO, save
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "docs/wave2_statecontam_campaign_20260703.md"
FIG_NAME = "fig_wave2_estimation_contam_negative"
ARMS = ["guided", "random"]
GATES = ["valid evals", "delivery/fairness", "identity", "decontamination"]


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator(cells: list[str]) -> bool:
    return all(set(cell) <= {"-", ":"} for cell in cells)


def table_after_marker(path: Path, marker: str) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == marker)
    while start < len(lines) and not lines[start].lstrip().startswith("|"):
        start += 1
    rows: list[list[str]] = []
    while start < len(lines) and lines[start].lstrip().startswith("|"):
        rows.append(split_row(lines[start]))
        start += 1
    header = rows[0]
    return [dict(zip(header, row)) for row in rows[1:] if not is_separator(row)]


def parse_fraction(cell: str) -> tuple[int, int, float]:
    got, total = cell.split("/")
    got_i = int(got)
    total_i = int(total)
    return got_i, total_i, float(got_i) / float(total_i)


def parse_data() -> dict[str, dict[str, object]]:
    main = table_after_marker(SOURCE, "## Main Campaign")
    validity = table_after_marker(SOURCE, "Validity gates over valid evals:")
    out = {arm: {} for arm in ARMS}
    for row in main:
        arm = row["arm"]
        if arm not in out:
            continue
        evals = int(row["evals"])
        valid = int(row["valid"])
        out[arm].update(
            {
                "evals": evals,
                "valid": valid,
                "valid evals": (valid, evals, valid / evals),
                "strict differentials": int(row["strict differentials"]),
                "primary candidates": int(row["primary candidates"]),
                "best diagnostic gap": row["best diagnostic gap"],
            }
        )
    for row in validity:
        arm = row["arm"]
        if arm not in out:
            continue
        out[arm]["delivery/fairness"] = parse_fraction(row["state-shim delivery/fairness"])
        out[arm]["identity"] = parse_fraction(row["identity"])
        out[arm]["decontamination"] = parse_fraction(row["decontamination"])
    return out


def print_provenance(data: dict[str, dict[str, object]]) -> None:
    print(f"SOURCE: {SOURCE.relative_to(REPO_ROOT)}")
    print("TABLES: ## Main Campaign; Validity gates over valid evals")
    for arm in ARMS:
        item = data[arm]
        gate_text = ", ".join(
            f"{gate}={item[gate][0]}/{item[gate][1]} ({item[gate][2]:.3f})" for gate in GATES
        )
        print(
            "VALUE: "
            f"{arm} evals={item['evals']} valid={item['valid']} "
            f"strict_differentials={item['strict differentials']} "
            f"primary_candidates={item['primary candidates']} "
            f"best_diagnostic_gap={item['best diagnostic gap']} gates=[{gate_text}]"
        )
    print("DECISION: Rendered optional Figure E as a compact null-result validity panel.")


def main() -> int:
    data = parse_data()
    print_provenance(data)

    x = np.arange(len(GATES))
    width = 0.34
    fig, axes = plt.subplots(1, 2, figsize=(COL_SINGLE, 2.25), gridspec_kw={"width_ratios": [2.2, 1.0]})
    colors = {"guided": OKABE_ITO[5], "random": OKABE_ITO[1]}
    hatches = {"guided": "", "random": "///"}
    for idx, arm in enumerate(ARMS):
        values = [float(data[arm][gate][2]) for gate in GATES]
        axes[0].bar(
            x + (idx - 0.5) * width,
            values,
            width=width,
            color=colors[arm],
            edgecolor="black",
            linewidth=0.5,
            hatch=hatches[arm],
            label=arm,
        )
    axes[0].set_ylabel("pass fraction")
    axes[0].set_ylim(0.94, 1.005)
    axes[0].set_xticks(x, ["valid", "delivery", "identity", "decontam"], rotation=28, ha="right")
    axes[0].grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.4)
    axes[0].legend(
        loc="lower left",
        bbox_to_anchor=(0.0, 1.02),
        borderaxespad=0.0,
        ncol=2,
        handlelength=1.2,
    )

    strict = [int(data[arm]["strict differentials"]) for arm in ARMS]
    primary = [int(data[arm]["primary candidates"]) for arm in ARMS]
    x2 = np.arange(len(ARMS))
    axes[1].bar(
        x2 - 0.15,
        strict,
        width=0.3,
        color=OKABE_ITO[6],
        edgecolor="black",
        linewidth=0.5,
        hatch="",
        label="strict",
    )
    axes[1].bar(
        x2 + 0.15,
        primary,
        width=0.3,
        color="0.75",
        edgecolor="black",
        linewidth=0.5,
        hatch="...",
        label="primary",
    )
    axes[1].set_ylabel("count")
    axes[1].set_ylim(0, 1)
    axes[1].set_yticks([0, 1])
    axes[1].set_xticks(x2, ARMS, rotation=28, ha="right")
    axes[1].grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.4)
    axes[1].legend(
        loc="lower left",
        bbox_to_anchor=(0.0, 1.02),
        borderaxespad=0.0,
        handlelength=1.2,
    )
    fig.subplots_adjust(wspace=0.42)
    save(fig, FIG_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
