#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

from img_style import COL_DOUBLE, OKABE_ITO, save
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "docs/switch_severity_campaign_20260629.md"
FIG_NAME = "fig_rq3_holed_nonmonotonic_boundary"

PANELS = [
    ("### Attitude", "attitude", "attitude (deg)", (47.5, 48.5, "partial recovery")),
    ("### Requested Rate", "requested rate", "requested rate (rad/s)", (1.50, 1.60, "hole")),
    ("### Wind", "wind", "wind (m/s)", (3.5, 6.5, "recovery")),
    ("### Switch Delay", "delay", "delay (s)", (0.055, 0.125, "holes")),
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


def parse_hits(cell: str) -> float:
    got, total = cell.split("/")
    return float(got) / float(total)


def parse_panel(heading: str, x_col: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    rows = table_after_heading(SOURCE, heading)
    values = []
    raw_rows = []
    for row in rows:
        x = parse_number(row[x_col])
        y = parse_hits(row["strict hits"])
        values.append((x, y))
        raw_rows.append(f"{row[x_col]} -> {row['strict hits']} ({y:.3f})")
    arr = np.array(values, dtype=float)
    return arr[:, 0], arr[:, 1], raw_rows


def print_provenance(parsed: dict[str, tuple[np.ndarray, np.ndarray, list[str]]]) -> None:
    print(f"SOURCE: {SOURCE.relative_to(REPO_ROOT)}")
    print("TABLES: ## RQ3: Controlled Dense Sweep; axes Attitude, Requested Rate, Wind, Switch Delay")
    for heading, _, _, _ in PANELS:
        _, _, rows = parsed[heading]
        print(f"TABLE: {heading}")
        for row in rows:
            print(f"VALUE: {row}")
    print("NOTE: Dense sweep reports three seeds per point: 2026062940, 2026062941, 2026062942.")


def main() -> int:
    parsed = {heading: parse_panel(heading, x_col) for heading, x_col, _, _ in PANELS}
    print_provenance(parsed)

    fig, axes = plt.subplots(2, 2, figsize=(COL_DOUBLE, 3.8), sharey=True)
    axes_flat = axes.ravel()
    for ax, (heading, _, xlabel, shade) in zip(axes_flat, PANELS):
        x, y, _ = parsed[heading]
        ax.plot(
            x,
            y,
            color=OKABE_ITO[5],
            marker="o",
            linestyle="-",
            markerfacecolor="white",
            markeredgecolor=OKABE_ITO[5],
        )
        x0, x1, label = shade
        ax.axvspan(x0, x1, color="0.88", alpha=0.65, linewidth=0)
        ax.text((x0 + x1) / 2.0, 0.08, label, ha="center", va="bottom", fontsize=7, color="0.25")
        ax.set_xlabel(xlabel)
        ax.set_ylim(-0.04, 1.04)
        ax.set_yticks([0.0, 0.5, 1.0])
        ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.4)
    axes[0, 0].set_ylabel("strict hit fraction")
    axes[1, 0].set_ylabel("strict hit fraction")
    fig.subplots_adjust(wspace=0.18, hspace=0.38)
    save(fig, FIG_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
