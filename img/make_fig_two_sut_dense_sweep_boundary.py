#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re

from img_style import COL_DOUBLE, OKABE_ITO, save
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
MCNN_SOURCE = REPO_ROOT / "docs/switch_severity_campaign_20260629.md"
RAPTOR_SOURCE = REPO_ROOT / "runs/campaigns/raptor_switch_severity_dense_sweep_20260705/summary.json"
FIG_NAME = "fig_two_sut_dense_sweep_boundary"

PANELS = [
    ("### Attitude", "attitude", "attitude_deg", "attitude (deg)", (47.5, 48.5, "partial recovery")),
    (
        "### Requested Rate",
        "requested rate",
        "requested_rate_rad_s",
        "requested rate (rad/s)",
        (1.50, 1.60, "hole"),
    ),
    ("### Wind", "wind", "wind_m_s", "wind (m/s)", (3.5, 6.5, "recovery")),
    ("### Switch Delay", "delay", "switch_delay_s", "delay (s)", (0.055, 0.125, "holes")),
]


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


def parse_number(cell: str) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", cell)
    if not match:
        raise ValueError(f"cannot parse numeric axis value from {cell!r}")
    return float(match.group(0))


def parse_hits(cell: str) -> tuple[int, int]:
    got, total = cell.split("/")
    return int(got), int(total)


def parse_mcnn_panel(heading: str, x_col: str) -> list[dict[str, float | int]]:
    points: list[dict[str, float | int]] = []
    for row in table_after_heading(MCNN_SOURCE, heading):
        hits, valid = parse_hits(row["strict hits"])
        points.append(
            {
                "value": parse_number(row[x_col]),
                "hits": hits,
                "valid": valid,
                "fraction": hits / valid,
            }
        )
    return points


def load_raptor_axes() -> dict[str, list[dict[str, object]]]:
    with RAPTOR_SOURCE.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)
    axes: dict[str, list[dict[str, object]]] = {}
    for _, _, axis_key, _, _ in PANELS:
        axes[axis_key] = []
        for point in summary["axes"][axis_key]:
            hits = int(point["strict_s0_vs_s3_hits"])
            valid = int(point["valid"])
            axes[axis_key].append(
                {
                    "value": float(point["value"]),
                    "hits": hits,
                    "valid": valid,
                    "fraction": hits / valid,
                    "seeds": list(point["seeds"]),
                    "neural_severity_counts": {
                        int(severity): int(count) for severity, count in point["neural_severity_counts"].items()
                    },
                }
            )
    return axes


def parse_all() -> tuple[dict[str, list[dict[str, float | int]]], dict[str, list[dict[str, object]]]]:
    mcnn = {heading: parse_mcnn_panel(heading, x_col) for heading, x_col, _, _, _ in PANELS}
    raptor = load_raptor_axes()
    for heading, _, axis_key, _, _ in PANELS:
        mcnn_values = np.array([point["value"] for point in mcnn[heading]], dtype=float)
        raptor_values = np.array([point["value"] for point in raptor[axis_key]], dtype=float)
        if len(mcnn_values) != len(raptor_values) or not np.allclose(mcnn_values, raptor_values):
            raise ValueError(f"axis mismatch for {axis_key}: mc_nn={mcnn_values} RAPTOR={raptor_values}")
    return mcnn, raptor


def fmt_value(value: object) -> str:
    return f"{float(value):g}"


def print_provenance(
    mcnn: dict[str, list[dict[str, float | int]]], raptor: dict[str, list[dict[str, object]]]
) -> None:
    print(f"SOURCE: {MCNN_SOURCE.relative_to(REPO_ROOT)}")
    print(f"SOURCE: {RAPTOR_SOURCE.relative_to(REPO_ROOT)}")
    print("TABLES: ## RQ3: Controlled Dense Sweep; axes Attitude, Requested Rate, Wind, Switch Delay")
    all_seeds: set[int] = set()
    max_raptor_severity = 0
    for heading, axis_label, axis_key, _, _ in PANELS:
        print(f"TABLE: {heading}")
        for mcnn_point, raptor_point in zip(mcnn[heading], raptor[axis_key]):
            all_seeds.update(int(seed) for seed in raptor_point["seeds"])
            severity_counts = raptor_point["neural_severity_counts"]
            max_raptor_severity = max(max_raptor_severity, max(severity_counts))
            print(
                "VALUE: "
                f"{axis_label} {fmt_value(mcnn_point['value'])} "
                f"mcnn={mcnn_point['hits']}/{mcnn_point['valid']} "
                f"raptor={raptor_point['hits']}/{raptor_point['valid']}"
            )
    seed_text = "/".join(str(seed) for seed in sorted(all_seeds))
    print(f"NOTE: RAPTOR seeds {seed_text}; max neural_severity=S{max_raptor_severity}.")


def main() -> int:
    mcnn, raptor = parse_all()
    print_provenance(mcnn, raptor)

    fig, axes = plt.subplots(2, 2, figsize=(COL_DOUBLE, 3.8), sharey=True)
    axes_flat = axes.ravel()
    for ax, (heading, _, axis_key, xlabel, shade) in zip(axes_flat, PANELS):
        x0, x1, label = shade
        ax.axvspan(x0, x1, color="0.88", alpha=0.65, linewidth=0, zorder=0)
        ax.text((x0 + x1) / 2.0, 0.08, label, ha="center", va="bottom", fontsize=7, color="0.25")

        mcnn_x = np.array([point["value"] for point in mcnn[heading]], dtype=float)
        mcnn_y = np.array([point["fraction"] for point in mcnn[heading]], dtype=float)
        raptor_x = np.array([point["value"] for point in raptor[axis_key]], dtype=float)
        raptor_y = np.array([point["fraction"] for point in raptor[axis_key]], dtype=float)
        ax.plot(
            mcnn_x,
            mcnn_y,
            color=OKABE_ITO[6],
            marker="o",
            linestyle="-",
            markerfacecolor="white",
            markeredgecolor=OKABE_ITO[6],
            label="mc_nn",
        )
        ax.plot(
            raptor_x,
            raptor_y,
            color=OKABE_ITO[3],
            marker="o",
            linestyle="-",
            markerfacecolor=OKABE_ITO[3],
            markeredgecolor=OKABE_ITO[3],
            label="RAPTOR",
        )
        ax.set_xlabel(xlabel)
        ax.set_ylim(-0.04, 1.04)
        ax.set_yticks([0.0, 0.5, 1.0])
        ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.4)
    axes[0, 0].set_ylabel("strict hit fraction")
    axes[1, 0].set_ylabel("strict hit fraction")
    axes[0, 0].legend(loc="upper left", ncol=2)
    fig.subplots_adjust(wspace=0.18, hspace=0.38)
    save(fig, FIG_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
