#!/usr/bin/env python3
"""Redraw RQ3 in nominal and delivered coordinates for Round 5."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "docs" / "round5_delivered_state_20260709"


def parse_axis(tag: str) -> tuple[str, float | str]:
    match = re.search(r"switch_severity_dense_sweep_20260630_(.+)_s\d+$", tag)
    point_id = match.group(1) if match else tag
    for axis in ("attitude_deg", "requested_rate_rad_s", "wind_m_s", "switch_delay_s", "approach_phase_rad"):
        prefix = axis + "_"
        if point_id.startswith(prefix):
            raw = point_id[len(prefix) :].replace("p", ".").replace("m", "-")
            try:
                return axis, float(raw)
            except ValueError:
                return axis, raw
    return "unknown", point_id


def main() -> int:
    csv_path = OUT_DIR / "mcnn_dense_delivered_state.csv"
    summary_path = OUT_DIR / "mcnn_dense_summary.json"
    df = pd.read_csv(csv_path)
    parsed = [parse_axis(tag) for tag in df["tag"]]
    df["axis"] = [axis for axis, _ in parsed]
    df["axis_value"] = [value for _, value in parsed]

    rows = []
    for (axis, value), group in df.groupby(["axis", "axis_value"], sort=True):
        rows.append(
            {
                "axis": axis,
                "axis_value": value,
                "n": int(len(group)),
                "s3_count": int((group["outcome_severity"] == 3).sum()),
                "s3_fraction": float((group["outcome_severity"] == 3).mean()),
                "nav23_rp_median_deg": float(group["nav23_est_att_roll_pitch_abs_deg"].median()),
                "nav23_omega_median_rad_s": float(group["nav23_est_rate_omega_norm"].median()),
                "nav23_yaw_median_deg": float(group["nav23_est_att_yaw_deg"].median()),
            }
        )
    with (OUT_DIR / "mcnn_dense_nominal_grid_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    ax = axes[0]
    for axis, marker in [
        ("attitude_deg", "o"),
        ("requested_rate_rad_s", "s"),
        ("wind_m_s", "^"),
        ("switch_delay_s", "D"),
        ("approach_phase_rad", "x"),
    ]:
        subset = [row for row in rows if row["axis"] == axis]
        xs = [float(row["axis_value"]) for row in subset]
        ys = [float(row["s3_fraction"]) for row in subset]
        ax.plot(xs, ys, marker=marker, linewidth=1.2, label=axis)
    ax.set_title("nominal campaign axes")
    ax.set_xlabel("nominal axis value")
    ax.set_ylabel("S3 fraction")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)

    ax = axes[1]
    colors = {0: "#2f9e44", 1: "#fab005", 2: "#fd7e14", 3: "#e03131"}
    for severity in sorted(df["outcome_severity"].dropna().unique()):
        group = df[df["outcome_severity"] == severity]
        ax.scatter(
            group["nav23_est_att_roll_pitch_abs_deg"],
            group["nav23_est_rate_omega_norm"],
            s=24,
            alpha=0.78,
            color=colors.get(int(severity), "#495057"),
            label=f"S{int(severity)}",
        )
    ax.set_title("delivered nav23 state")
    ax.set_xlabel("max(|roll|, |pitch|) deg")
    ax.set_ylabel("||omega|| rad/s")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "mcnn_dense_nominal_vs_actual.png", dpi=180)
    plt.close(fig)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    curve = summary.get("local_consistency", [])
    if curve:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot([row["epsilon_normalized"] for row in curve], [row["consistency"] for row in curve], marker="o")
        ax.set_xlabel("epsilon, normalized by feature std")
        ax.set_ylabel("S3/non-S3 pair consistency")
        ax.set_ylim(0, 1.05)
        ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(OUT_DIR / "mcnn_dense_local_consistency.png", dpi=180)
        plt.close(fig)

    print(
        json.dumps(
            {
                "nominal_csv": str(OUT_DIR / "mcnn_dense_nominal_grid_summary.csv"),
                "nominal_vs_actual_png": str(OUT_DIR / "mcnn_dense_nominal_vs_actual.png"),
                "local_consistency_png": str(OUT_DIR / "mcnn_dense_local_consistency.png"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
