#!/usr/bin/env python3
"""Reanalyze switch-severity guided archives against the RQ3 dense sweep.

This is intentionally read-only with respect to campaign artifacts. It consumes
existing JSON/JSONL files under runs/campaigns and writes a compact markdown
report plus a structured summary JSON.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GUIDED_RUNS = [
    REPO_ROOT / "runs/campaigns/switch_severity_guided_0_20260629",
    REPO_ROOT / "runs/campaigns/switch_severity_guided_1_20260630",
    REPO_ROOT / "runs/campaigns/switch_severity_guided_2_20260630",
]
DEFAULT_DENSE_SWEEP = REPO_ROOT / "runs/campaigns/switch_severity_dense_sweep_20260630/sweep_results.jsonl"
DEFAULT_REPORT = REPO_ROOT / "docs/rq2_archive_reanalysis_20260705.md"
DEFAULT_SUMMARY = REPO_ROOT / "docs/rq2_archive_reanalysis_20260705.json"
FITNESS_FLOOR = -1.0e9


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def local_artifact_path(value: str | None) -> Path | None:
    if not value:
        return None
    if value.startswith("/workspace/"):
        return REPO_ROOT / value.removeprefix("/workspace/")
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def load_result_genome(result: dict[str, Any]) -> dict[str, Any]:
    theta_path = local_artifact_path(str(result.get("theta_path", "")))
    if theta_path is None or not theta_path.exists():
        raise FileNotFoundError(f"missing theta for result {result.get('tag')}: {theta_path}")
    theta = read_json(theta_path)
    genome = theta.get("theta_genome", {}).get("genome")
    if not isinstance(genome, dict):
        raise ValueError(f"theta missing theta_genome.genome: {theta_path}")
    return genome


def load_run_records(run_dir: Path) -> list[dict[str, Any]]:
    records = read_jsonl(run_dir / "evals.jsonl")
    for record in records:
        record["run_id"] = run_dir.name
        record["genome"] = load_result_genome(record)
    return records


def archive_rows(run_dir: Path) -> list[dict[str, Any]]:
    archive = read_json(run_dir / "archive.json")
    rows: list[dict[str, Any]] = []
    for cell, elite in sorted(archive.items()):
        result = elite["result"]
        genome = elite["genome"]
        fitness = result.get("fitness", {}) if isinstance(result.get("fitness"), dict) else {}
        rows.append(
            {
                "run_id": run_dir.name,
                "cell": cell,
                "eval_index": int(result["index"]),
                "evals_used": int(result["index"]) + 1,
                "quality": float(result.get("quality", FITNESS_FLOOR)),
                "primary_bug": bool(result.get("primary_bug")),
                "classical_severity": fitness.get("classical_severity"),
                "neural_severity": fitness.get("neural_severity"),
                "switch_roll_pitch_deg": float(genome["switch_roll_pitch_deg"]),
                "wind_speed_m_s": float(genome["wind_speed_m_s"]),
                "switch_rate_rad_s": float(genome["switch_rate_rad_s"]),
                "switch_delay_s": float(genome["switch_delay_s"]),
            }
        )
    return rows


def primary_cell_milestones(records: list[dict[str, Any]], targets: Iterable[int] = (1, 3, 5, 8, 10)) -> dict[int, int]:
    wanted = set(targets)
    out: dict[int, int] = {}
    cells: set[str] = set()
    for record in sorted(records, key=lambda item: int(item["index"])):
        if bool(record.get("primary_bug")):
            cells.add(str(record.get("feature_bin")))
        covered = len(cells)
        for target in sorted(wanted):
            if covered >= target and target not in out:
                out[target] = int(record["index"]) + 1
    return out


def is_valid_eval(record: dict[str, Any]) -> bool:
    return int(record.get("returncode", 1)) == 0 and record.get("error") in (None, "")


def dense_axis_summary(records: list[dict[str, Any]]) -> dict[str, dict[float, dict[str, Any]]]:
    grouped: dict[str, dict[float, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        grouped[str(record["axis"])][float(record["value"])].append(record)

    summary: dict[str, dict[float, dict[str, Any]]] = {}
    for axis, by_value in grouped.items():
        summary[axis] = {}
        for value, items in sorted(by_value.items()):
            valid = [item for item in items if int(item.get("returncode", 1)) == 0]
            hits = [item for item in valid if bool(item.get("primary_bug"))]
            summary[axis][value] = {
                "evals": len(items),
                "valid": len(valid),
                "invalid": len(items) - len(valid),
                "strict_hits": len(hits),
                "hit_rate_valid": (len(hits) / len(valid)) if valid else None,
                "classical_severity_counts": dict(Counter(str(item.get("classical_severity")) for item in valid)),
                "neural_severity_counts": dict(Counter(str(item.get("neural_severity")) for item in valid)),
            }
    return summary


def attitude_band(value: float) -> str:
    if value < 36.0:
        return "<36"
    if value < 40.0:
        return "36-<40"
    if value < 42.0:
        return "40-<42"
    if value <= 45.0:
        return "42-45"
    if value < 48.0:
        return "45-<48"
    return ">=48"


def wind_band(value: float) -> str:
    if value < 1.0:
        return "0-<1"
    if value < 2.0:
        return "1-<2"
    if value < 3.0:
        return "2-<3"
    if value < 4.0:
        return "3-<4"
    if value < 5.0:
        return "4-<5"
    return "5-6"


def rate_band(value: float) -> str:
    if value < 1.45:
        return "<1.45"
    if value < 1.65:
        return "1.45-<1.65"
    if value < 1.85:
        return "1.65-<1.85"
    return ">=1.85"


def delay_band(value: float) -> str:
    if value < 0.03:
        return "<0.03"
    if value < 0.06:
        return "0.03-<0.06"
    if value < 0.09:
        return "0.06-<0.09"
    if value < 0.12:
        return "0.09-<0.12"
    if value < 0.15:
        return "0.12-<0.15"
    return "0.15-0.18"


def grouped_eval_counts(records: list[dict[str, Any]], key: str, bucket_fn: Any) -> dict[str, dict[str, int | float | None]]:
    counts: dict[str, dict[str, int | float | None]] = {}
    buckets = sorted({bucket_fn(float(record["genome"][key])) for record in records})
    for bucket in buckets:
        items = [record for record in records if bucket_fn(float(record["genome"][key])) == bucket]
        valid = [record for record in items if is_valid_eval(record)]
        primary = [record for record in valid if bool(record.get("primary_bug"))]
        counts[bucket] = {
            "evals": len(items),
            "valid": len(valid),
            "primary": len(primary),
            "primary_rate": (len(primary) / len(valid)) if valid else None,
        }
    return counts


def numeric_summary(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [float(row[key]) for row in rows]
    return {
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def dense_hits(summary: dict[str, dict[float, dict[str, Any]]], axis: str, values: Iterable[float]) -> str:
    parts = []
    for value in values:
        item = summary.get(axis, {}).get(float(value), {})
        parts.append(f"{value:g}:{item.get('strict_hits', '?')}/{item.get('valid', '?')}")
    return ", ".join(parts)


def primary_rate_for(counts: dict[str, dict[str, int | float | None]], bucket: str) -> str:
    item = counts.get(bucket, {})
    rate = item.get("primary_rate")
    if not isinstance(rate, (int, float)) or not math.isfinite(float(rate)):
        return "n/a"
    return f"{item.get('primary')}/{item.get('valid')} ({100.0 * float(rate):.1f}%)"


def assess_boundary_features(
    archive: list[dict[str, Any]],
    eval_counts: dict[str, dict[str, dict[str, int | float | None]]],
    dense: dict[str, dict[float, dict[str, Any]]],
) -> list[dict[str, Any]]:
    archive_attitudes = [row["switch_roll_pitch_deg"] for row in archive]
    archive_rates = [row["switch_rate_rad_s"] for row in archive]
    high_rate_elites = sum(1 for value in archive_rates if value >= 1.45)
    high_wind_primary = sum(1 for row in archive if row["wind_speed_m_s"] >= 4.0 and row["primary_bug"])
    delay_hole_elites = sum(1 for row in archive if 0.06 <= row["switch_delay_s"] < 0.09 or 0.12 <= row["switch_delay_s"] < 0.15)

    assessments = [
        {
            "feature": "attitude onset near 40 deg",
            "status": "partial",
            "score": 0.5,
            "core": True,
            "archive_evidence": (
                f"final elite min attitude {min(archive_attitudes):.2f} deg; "
                f"36-<40 eval bucket {primary_rate_for(eval_counts['attitude'], '36-<40')}; "
                "the search archive does not supply a controlled lower-safe side"
            ),
            "dense_evidence": dense_hits(dense, "attitude_deg", [38.0, 40.0, 42.0]),
        },
        {
            "feature": "42-45 deg stable strict band",
            "status": "strong",
            "score": 1.0,
            "core": True,
            "archive_evidence": (
                f"{sum(1 for row in archive if 42.0 <= row['switch_roll_pitch_deg'] <= 45.0)}/"
                f"{len(archive)} final elites are in 42-45 deg; eval bucket "
                f"{primary_rate_for(eval_counts['attitude'], '42-45')}"
            ),
            "dense_evidence": dense_hits(dense, "attitude_deg", [42.0, 45.0]),
        },
        {
            "feature": "48 deg partial recovery",
            "status": "partial",
            "score": 0.5,
            "core": True,
            "archive_evidence": (
                f"{sum(1 for row in archive if row['switch_roll_pitch_deg'] >= 48.0)} final elites remain primary at >=48 deg; "
                f"eval bucket {primary_rate_for(eval_counts['attitude'], '>=48')} versus "
                f"45-<48 bucket {primary_rate_for(eval_counts['attitude'], '45-<48')}"
            ),
            "dense_evidence": dense_hits(dense, "attitude_deg", [45.0, 48.0]),
        },
        {
            "feature": "rate 1.55 hole / 1.75 recovery",
            "status": "not_shown",
            "score": 0.0,
            "core": True,
            "archive_evidence": (
                f"archive actual rate range {min(archive_rates):.3f}-{max(archive_rates):.3f} rad/s; "
                f"high-rate final elites >=1.45 rad/s: {high_rate_elites}/{len(archive)}"
            ),
            "dense_evidence": dense_hits(dense, "requested_rate_rad_s", [1.55, 1.75]),
        },
        {
            "feature": "wind 0-3 exposure / 4-6 recovery at fixed baseline",
            "status": "not_shown",
            "score": 0.0,
            "core": True,
            "archive_evidence": (
                f"archive keeps {high_wind_primary} primary elites at wind >=4 m/s; "
                f"eval buckets 4-<5 {primary_rate_for(eval_counts['wind'], '4-<5')}, "
                f"5-6 {primary_rate_for(eval_counts['wind'], '5-6')}"
            ),
            "dense_evidence": dense_hits(dense, "wind_m_s", [0.0, 3.0, 4.0, 6.0]),
        },
        {
            "feature": "delay 0.06/0.12 temporal holes",
            "status": "not_shown",
            "score": 0.0,
            "core": False,
            "archive_evidence": (
                f"archive has {delay_hole_elites} elites in the dense-sweep hole-adjacent delay buckets; "
                f"eval buckets 0.06-<0.09 {primary_rate_for(eval_counts['delay'], '0.06-<0.09')}, "
                f"0.12-<0.15 {primary_rate_for(eval_counts['delay'], '0.12-<0.15')}"
            ),
            "dense_evidence": dense_hits(dense, "switch_delay_s", [0.06, 0.12]),
        },
    ]
    return assessments


def summarize_run(run_dir: Path, records: list[dict[str, Any]], archive: list[dict[str, Any]]) -> dict[str, Any]:
    primary = [record for record in records if bool(record.get("primary_bug"))]
    valid = [record for record in records if is_valid_eval(record)]
    primary_cells = sorted({str(record.get("feature_bin")) for record in primary})
    return {
        "run_id": run_dir.name,
        "evals": len(records),
        "valid": len(valid),
        "invalid": len(records) - len(valid),
        "primary_evals": len(primary),
        "primary_cells": len(primary_cells),
        "archive_bins": len(archive),
        "archive_primary_elites": sum(1 for row in archive if row["primary_bug"]),
        "first_primary_eval": min((int(record["index"]) + 1 for record in primary), default=None),
        "primary_cell_milestones": primary_cell_milestones(records),
        "qd_score": sum(max(0.0, row["quality"]) for row in archive),
        "primary_cell_list": primary_cells,
    }


def summarize(guided_runs: list[Path], dense_sweep: Path) -> dict[str, Any]:
    run_summaries = []
    all_records: list[dict[str, Any]] = []
    all_archive: list[dict[str, Any]] = []
    for run_dir in guided_runs:
        records = load_run_records(run_dir)
        archive = archive_rows(run_dir)
        all_records.extend(records)
        all_archive.extend(archive)
        run_summaries.append(summarize_run(run_dir, records, archive))

    dense_records = read_jsonl(dense_sweep)
    dense = dense_axis_summary(dense_records)
    eval_counts = {
        "attitude": grouped_eval_counts(all_records, "switch_roll_pitch_deg", attitude_band),
        "wind": grouped_eval_counts(all_records, "wind_speed_m_s", wind_band),
        "rate": grouped_eval_counts(all_records, "switch_rate_rad_s", rate_band),
        "delay": grouped_eval_counts(all_records, "switch_delay_s", delay_band),
    }
    assessments = assess_boundary_features(all_archive, eval_counts, dense)
    core = [item for item in assessments if item["core"]]
    return {
        "source_artifacts": {
            "guided_runs": [repo_relative(path) for path in guided_runs],
            "dense_sweep": repo_relative(dense_sweep),
        },
        "guided_runs": run_summaries,
        "aggregate": {
            "evals": len(all_records),
            "valid": sum(1 for record in all_records if is_valid_eval(record)),
            "primary_evals": sum(1 for record in all_records if bool(record.get("primary_bug"))),
            "archive_elites": len(all_archive),
            "archive_primary_elites": sum(1 for row in all_archive if row["primary_bug"]),
            "archive_attitude_deg": numeric_summary(all_archive, "switch_roll_pitch_deg"),
            "archive_wind_m_s": numeric_summary(all_archive, "wind_speed_m_s"),
            "archive_rate_rad_s": numeric_summary(all_archive, "switch_rate_rad_s"),
            "archive_delay_s": numeric_summary(all_archive, "switch_delay_s"),
            "archive_eval_index": numeric_summary(all_archive, "eval_index"),
            "archive_quality": numeric_summary(all_archive, "quality"),
            "archive_attitude_bands": dict(Counter(attitude_band(row["switch_roll_pitch_deg"]) for row in all_archive)),
            "archive_wind_bands": dict(Counter(wind_band(row["wind_speed_m_s"]) for row in all_archive)),
            "archive_rate_bands": dict(Counter(rate_band(row["switch_rate_rad_s"]) for row in all_archive)),
            "archive_delay_bands": dict(Counter(delay_band(row["switch_delay_s"]) for row in all_archive)),
            "boundary_feature_score": sum(float(item["score"]) for item in core),
            "boundary_feature_count": len(core),
            "boundary_feature_fraction": sum(float(item["score"]) for item in core) / len(core),
        },
        "eval_counts": eval_counts,
        "dense_axis_summary": dense,
        "feature_assessments": assessments,
    }


def fmt_num(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return lines


def format_milestone(milestones: dict[str, Any] | dict[int, Any], key: int) -> str:
    return str(milestones.get(key) or milestones.get(str(key)) or "n/a")


def write_report(summary: dict[str, Any], path: Path) -> None:
    aggregate = summary["aggregate"]
    core_score = aggregate["boundary_feature_score"]
    core_count = aggregate["boundary_feature_count"]
    lines: list[str] = [
        "# RQ2 Archive Reanalysis",
        "",
        "Date: 2026-07-05",
        "",
        "Scope: pure reanalysis of existing switch-severity artifacts. No simulator, ULOG reparse, oracle change, or new eval was run.",
        "",
        "## Verdict",
        "",
        (
            "The guided archives do partially illuminate the RQ3 boundary: they independently concentrate on the "
            "`rp_3/rp_4 x wind` high-risk cells, and they strongly reproduce the 42-45 deg attitude band. "
            "They do not, by themselves, recover the controlled dense-sweep holes for requested rate or the fixed-baseline "
            "wind recovery at 4-6 m/s. The honest framing is therefore: guided MAP-Elites rapidly delivers a compact, "
            "high-yield boundary-localizing archive, while the detailed non-monotonic hole structure remains a dense-sweep result."
        ),
        "",
        f"Core dense-boundary feature completeness from the archive: {core_score:.1f}/{core_count} ({100.0 * aggregate['boundary_feature_fraction']:.1f}%).",
        "",
        "## Source Artifacts",
        "",
    ]
    for run in summary["source_artifacts"]["guided_runs"]:
        lines.append(f"- `{run}`")
    lines.append(f"- dense sweep: `{summary['source_artifacts']['dense_sweep']}`")
    lines.extend(
        [
            "",
            "## Guided Archive Coverage",
            "",
            *markdown_table(
                [
                    "run",
                    "evals",
                    "valid",
                    "primary evals",
                    "archive primary elites",
                    "primary cells",
                    "first primary eval",
                    "evals to 5/8/10 cells",
                    "QD score",
                ],
                [
                    [
                        item["run_id"],
                        item["evals"],
                        item["valid"],
                        item["primary_evals"],
                        f"{item['archive_primary_elites']}/{item['archive_bins']}",
                        item["primary_cells"],
                        item["first_primary_eval"],
                        (
                            f"{format_milestone(item['primary_cell_milestones'], 5)} / "
                            f"{format_milestone(item['primary_cell_milestones'], 8)} / "
                            f"{format_milestone(item['primary_cell_milestones'], 10)}"
                        ),
                        f"{float(item['qd_score']):.3f}",
                    ]
                    for item in summary["guided_runs"]
                ],
            ),
            "",
            "All three guided runs ended with 10/10 final archive elites in the high-risk `rp_3/rp_4 x wind_0..4` cells. "
            "Those 10 cells were first covered by eval 44, 61, and 88 respectively, versus 120 paired evals in the RQ3 dense sweep.",
            "",
            "## Final Elite Distribution",
            "",
            *markdown_table(
                ["quantity", "min", "median", "max"],
                [
                    [
                        "switch attitude deg",
                        fmt_num(aggregate["archive_attitude_deg"]["min"], 2),
                        fmt_num(aggregate["archive_attitude_deg"]["median"], 2),
                        fmt_num(aggregate["archive_attitude_deg"]["max"], 2),
                    ],
                    [
                        "wind m/s",
                        fmt_num(aggregate["archive_wind_m_s"]["min"], 2),
                        fmt_num(aggregate["archive_wind_m_s"]["median"], 2),
                        fmt_num(aggregate["archive_wind_m_s"]["max"], 2),
                    ],
                    [
                        "actual switch rate rad/s",
                        fmt_num(aggregate["archive_rate_rad_s"]["min"], 3),
                        fmt_num(aggregate["archive_rate_rad_s"]["median"], 3),
                        fmt_num(aggregate["archive_rate_rad_s"]["max"], 3),
                    ],
                    [
                        "switch delay s",
                        fmt_num(aggregate["archive_delay_s"]["min"], 3),
                        fmt_num(aggregate["archive_delay_s"]["median"], 3),
                        fmt_num(aggregate["archive_delay_s"]["max"], 3),
                    ],
                    [
                        "elite eval index",
                        fmt_num(aggregate["archive_eval_index"]["min"], 0),
                        fmt_num(aggregate["archive_eval_index"]["median"], 0),
                        fmt_num(aggregate["archive_eval_index"]["max"], 0),
                    ],
                ],
            ),
            "",
            f"Archive attitude bands: `{json.dumps(aggregate['archive_attitude_bands'], sort_keys=True)}`",
            "",
            f"Archive wind bands: `{json.dumps(aggregate['archive_wind_bands'], sort_keys=True)}`",
            "",
            f"Archive rate bands: `{json.dumps(aggregate['archive_rate_bands'], sort_keys=True)}`",
            "",
            "## RQ3 Feature Check",
            "",
            *markdown_table(
                ["feature", "archive status", "archive evidence", "dense-sweep evidence"],
                [
                    [
                        item["feature"],
                        item["status"],
                        item["archive_evidence"],
                        item["dense_evidence"],
                    ]
                    for item in summary["feature_assessments"]
                ],
            ),
            "",
            "## Interpretation For Paper Framing",
            "",
            "- Strong claim supported by archive reanalysis: guided search rapidly finds and preserves high-quality elites across the same broad attitude-wind cells later used in RQ3.",
            "- Claim not supported by archive alone: the full high-dimensional hole boundary. Rate, delay, and fixed-baseline high-wind recovery require the dense sweep.",
            "- Recommended RQ2/RQ3 linkage: use the fuzzer archive as boundary-localizing evidence and use the dense sweep as the controlled causal characterization. Do not write that the fuzzer alone delivered the RQ3 boundary.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guided-run", action="append", type=Path, dest="guided_runs")
    parser.add_argument("--dense-sweep", type=Path, default=DEFAULT_DENSE_SWEEP)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    guided_runs = [path.resolve() for path in (args.guided_runs or DEFAULT_GUIDED_RUNS)]
    dense_sweep = args.dense_sweep.resolve()
    summary = summarize(guided_runs, dense_sweep)
    write_json(args.summary_json.resolve(), summary)
    write_report(summary, args.report.resolve())
    print(f"SUMMARY_JSON={args.summary_json.resolve()}")
    print(f"REPORT={args.report.resolve()}")
    print(
        "BOUNDARY_FEATURE_COMPLETENESS="
        f"{summary['aggregate']['boundary_feature_score']:.1f}/"
        f"{summary['aggregate']['boundary_feature_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
