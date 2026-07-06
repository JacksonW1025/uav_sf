#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from img_style import COL_DOUBLE, OKABE_ITO, save
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "docs/switch_severity_campaign_20260629.md"
FIG_NAME = "fig_rq2_search_efficiency_guided_random_grid"
ARMS = ["guided", "random", "grid"]


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator(cells: list[str]) -> bool:
    return all(set(cell) <= {"-", ":"} for cell in cells)


def first_table_after(path: Path, marker: str) -> list[dict[str, str]]:
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


def parse_rows() -> list[dict[str, object]]:
    rows = first_table_after(SOURCE, "## RQ2: Guided vs Random vs Grid")
    parsed: list[dict[str, object]] = []
    for row in rows:
        arm_label = row["arm"]
        arm = arm_label.split()[0]
        if arm not in ARMS:
            continue
        parsed.append(
            {
                "label": arm_label,
                "arm": arm,
                "evals": int(row["evals"]),
                "valid": int(row["valid"]),
                "first_primary_evals": None
                if row["first primary evals"] == "-"
                else int(row["first primary evals"]),
                "primary_evals": int(row["primary evals"]),
                "qd_score": float(row["QD score"]),
            }
        )
    return parsed


def summarize(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    by_arm: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_arm[str(row["arm"])].append(row)
    summary: dict[str, dict[str, object]] = {}
    for arm in ARMS:
        arm_rows = by_arm.get(arm, [])
        if not arm_rows:
            continue
        primary = np.array([float(r["primary_evals"]) for r in arm_rows])
        qd = np.array([float(r["qd_score"]) for r in arm_rows])
        valid = np.array([float(r["valid"]) for r in arm_rows])
        summary[arm] = {
            "rows": arm_rows,
            "primary_mean": float(np.mean(primary)),
            "qd_mean": float(np.mean(qd)),
            "hit_rate_mean": float(np.mean(primary / valid)),
        }
    return summary


def print_provenance(rows: list[dict[str, object]], summary: dict[str, dict[str, object]]) -> None:
    print(f"SOURCE: {SOURCE.relative_to(REPO_ROOT)}")
    print("TABLE: ## RQ2: Guided vs Random vs Grid, per-arm per-seed discovery table")
    for row in rows:
        print(
            "VALUE: "
            f"{row['label']} evals={row['evals']} valid={row['valid']} "
            f"first_primary_evals={row['first_primary_evals']} "
            f"primary_evals={row['primary_evals']} qd_score={row['qd_score']}"
        )
    for arm in ARMS:
        item = summary[arm]
        print(
            "SUMMARY: "
            f"{arm} primary_mean_per_run={item['primary_mean']:.3f} "
            f"qd_mean={item['qd_mean']:.3f} hit_rate_mean={item['hit_rate_mean']:.4f}"
        )
    ratio = summary["guided"]["primary_mean"] / summary["random"]["primary_mean"]
    print(f"SUMMARY: guided/random primary-eval density ratio={ratio:.3f}")


def add_panel(
    ax,
    summary: dict[str, dict[str, object]],
    metric_key: str,
    row_key: str,
    ylabel: str,
    ylim_pad: float,
) -> None:
    x = np.arange(len(ARMS))
    colors = [OKABE_ITO[5], OKABE_ITO[1], "0.72"]
    hatches = ["", "///", "..."]
    values = [float(summary[arm][metric_key]) for arm in ARMS]
    ax.bar(
        x,
        values,
        width=0.64,
        color=colors,
        edgecolor="black",
        linewidth=0.5,
        hatch=hatches,
        zorder=2,
    )
    markers = {"guided": "o", "random": "s", "grid": "^"}
    offsets = {"guided": [-0.12, 0.0, 0.12], "random": [-0.12, 0.0, 0.12], "grid": [0.0]}
    for idx, arm in enumerate(ARMS):
        rows = list(summary[arm]["rows"])
        for off, row in zip(offsets[arm], rows):
            ax.scatter(
                idx + off,
                float(row[row_key]),
                marker=markers[arm],
                facecolor="white",
                edgecolor="black",
                linewidth=0.7,
                s=20,
                zorder=3,
            )
    ax.set_xticks(x, ARMS)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, max(values) * ylim_pad)
    ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.4, zorder=1)


def main() -> int:
    rows = parse_rows()
    summary = summarize(rows)
    missing = [arm for arm in ARMS if arm not in summary]
    if missing:
        raise RuntimeError(f"missing arms in RQ2 table: {missing}")
    print_provenance(rows, summary)

    fig, axes = plt.subplots(1, 2, figsize=(COL_DOUBLE, 2.45))
    add_panel(
        axes[0],
        summary,
        "primary_mean",
        "primary_evals",
        "primary evals\n(count/run)",
        1.24,
    )
    add_panel(axes[1], summary, "qd_mean", "qd_score", "QD score\n(per run)", 1.18)
    axes[0].set_xlabel("search arm")
    axes[1].set_xlabel("search arm")
    handles = [
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor="white", markeredgecolor="black", label="seed/run"),
    ]
    axes[1].legend(handles=handles, loc="upper right")
    fig.subplots_adjust(wspace=0.33)
    save(fig, FIG_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
