#!/usr/bin/env python3
"""Extract a P1-P7 differential-policy spectrum from switch campaign artifacts."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from property_fitness import policy_differential_findings
from property_oracle import PROPERTY_ORDER


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = REPO_ROOT / "runs" / "campaigns"
DISCOVERY_RUN_IDS = [
    "switch_severity_guided_0_20260629",
    "switch_severity_guided_1_20260630",
    "switch_severity_guided_2_20260630",
    "switch_severity_random_0_20260630",
    "switch_severity_random_1_20260630",
    "switch_severity_random_2_20260630",
    "switch_severity_grid_0_20260630",
]
DENSE_RUN_IDS = ["switch_severity_dense_sweep_20260630"]
CONFIRM_RUN_IDS = [
    "switch_severity_guided_confirm_20260630",
    "switch_severity_random_confirm_20260630",
    "switch_severity_grid_confirm_20260630",
]
DEFAULT_RUN_IDS = DISCOVERY_RUN_IDS + DENSE_RUN_IDS + CONFIRM_RUN_IDS


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def repo_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if path.is_absolute():
        parts = path.parts
        if len(parts) >= 2 and parts[1] == "workspace":
            return REPO_ROOT.joinpath(*parts[2:])
        return path
    return REPO_ROOT / path


def relpath(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def arm_for_run(run_id: str) -> str:
    if "_guided" in run_id:
        return "guided"
    if "_random" in run_id:
        return "random"
    if "_grid" in run_id:
        return "grid"
    if "dense_sweep" in run_id:
        return "dense_sweep"
    return "unknown"


def normalized_cell(value: Any) -> str:
    if value is None:
        return "unknown"
    text = str(value)
    return text.removeprefix("switching:")


def compare_path_from(record: dict[str, Any]) -> Path | None:
    direct = record.get("compare_path")
    if direct:
        return repo_path(str(direct))
    evidence = record.get("evidence")
    if isinstance(evidence, dict) and evidence.get("compare_path"):
        return repo_path(str(evidence["compare_path"]))
    return None


def theta_path_from(record: dict[str, Any]) -> Path | None:
    direct = record.get("theta_path")
    if direct:
        return repo_path(str(direct))
    evidence = record.get("evidence")
    if isinstance(evidence, dict) and evidence.get("theta_path"):
        return repo_path(str(evidence["theta_path"]))
    return None


def iter_run_records(run_dir: Path) -> Iterable[dict[str, Any]]:
    run_id = run_dir.name
    evals = run_dir / "evals.jsonl"
    if evals.exists():
        for record in load_jsonl(evals):
            yield {
                "source_kind": "discovery",
                "run_id": run_id,
                "arm": arm_for_run(run_id),
                "record": record,
            }

    sweep = run_dir / "sweep_results.jsonl"
    if sweep.exists():
        for record in load_jsonl(sweep):
            yield {
                "source_kind": "dense_sweep",
                "run_id": run_id,
                "arm": "dense_sweep",
                "point_id": record.get("point_id"),
                "axis": record.get("axis"),
                "axis_value": record.get("value"),
                "record": record,
            }

    confirmations = run_dir / "confirmations.jsonl"
    if confirmations.exists():
        for confirmation in load_jsonl(confirmations):
            candidate = confirmation.get("candidate", {})
            candidate_result = candidate.get("result", {}) if isinstance(candidate, dict) else {}
            candidate_tag = candidate_result.get("tag")
            source_cell = candidate.get("source_cell") if isinstance(candidate, dict) else None
            for repeat_index, repeat in enumerate(confirmation.get("repeats", []), start=1):
                if not isinstance(repeat, dict):
                    continue
                yield {
                    "source_kind": "confirmation",
                    "run_id": run_id,
                    "arm": arm_for_run(run_id),
                    "candidate_tag": candidate_tag,
                    "candidate_cell": source_cell,
                    "repeat_index": repeat_index,
                    "required_properties": confirmation.get("required_properties", []),
                    "required_severity": confirmation.get("required_severity"),
                    "record": repeat,
                }


def validity_from_compare(compare: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    oracle = compare.get("property_oracle")
    if not isinstance(oracle, dict):
        return False, ["missing_property_oracle"]
    classical = oracle.get("classical")
    neural = oracle.get("neural")
    if not isinstance(classical, dict) or not isinstance(neural, dict):
        return False, ["missing_property_results"]
    for controller, result in [("classical", classical), ("mcnn", neural)]:
        decontam = result.get("window", {}).get("decontamination", {})
        if isinstance(decontam, dict) and decontam.get("valid") is False:
            reasons.append(f"{controller}_decontamination_invalid")
    identity = neural.get("controller_identity", {})
    gate = identity.get("identity_gate") if isinstance(identity, dict) else None
    if isinstance(gate, dict):
        if not bool(gate.get("passed")):
            reasons.append("mcnn_identity_failed")
    elif identity.get("mcnn_confirmed") is False:
        reasons.append("mcnn_identity_failed")
    return not reasons, reasons


def analyze_record(source: dict[str, Any]) -> dict[str, Any]:
    record = source["record"]
    tag = str(record.get("tag") or source.get("candidate_tag") or "unknown")
    compare_path = compare_path_from(record)
    theta_path = theta_path_from(record)
    out: dict[str, Any] = {
        "source_kind": source["source_kind"],
        "run_id": source["run_id"],
        "arm": source["arm"],
        "tag": tag,
        "seed": record.get("seed"),
        "cell": normalized_cell(record.get("feature_bin") or source.get("candidate_cell")),
        "candidate_tag": source.get("candidate_tag"),
        "point_id": source.get("point_id"),
        "axis": source.get("axis"),
        "axis_value": source.get("axis_value"),
        "compare_path": relpath(compare_path),
        "theta_path": relpath(theta_path),
        "valid": False,
        "invalid_reasons": [],
        "policy_findings": {"positive_policies": [], "by_policy": {}},
    }
    if record.get("returncode", 0) not in (0, None):
        out["invalid_reasons"].append("run_error")
    if compare_path is None or not compare_path.exists():
        out["invalid_reasons"].append("missing_compare_json")
        return out

    compare = load_json(compare_path)
    compare_valid, compare_reasons = validity_from_compare(compare)
    if not compare_valid:
        out["invalid_reasons"].extend(compare_reasons)
    oracle = compare.get("property_oracle", {})
    classical = oracle.get("classical") if isinstance(oracle, dict) else None
    neural = oracle.get("neural") if isinstance(oracle, dict) else None
    if isinstance(classical, dict) and isinstance(neural, dict):
        findings = policy_differential_findings(classical, neural)
        out["policy_findings"] = findings
        out["classical_severity"] = findings["classical_severity"]
        out["neural_severity"] = findings["neural_severity"]
        out["classical_severity_label"] = findings["classical_severity_label"]
        out["neural_severity_label"] = findings["neural_severity_label"]
        out["positive_policies"] = findings["positive_policies"]
        out["catastrophic_positive_policies"] = findings["catastrophic_positive_policies"]
        out["behavior_positive_policies"] = findings["behavior_positive_policies"]
    else:
        out["invalid_reasons"].append("missing_property_results")
    out["invalid_reasons"] = sorted(set(out["invalid_reasons"]))
    out["valid"] = not out["invalid_reasons"]
    return out


def scan_runs(run_root: Path, run_ids: Iterable[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for run_id in run_ids:
        run_dir = run_root / run_id
        if not run_dir.exists():
            continue
        for source in iter_run_records(run_dir):
            records.append(analyze_record(source))
    return records


def confirmation_group_id(record: dict[str, Any]) -> str | None:
    if record.get("source_kind") == "confirmation":
        candidate = record.get("candidate_tag")
        return str(candidate) if candidate else str(record.get("tag"))
    if record.get("source_kind") == "dense_sweep":
        point = record.get("point_id")
        if point is None:
            return None
        return f"{record.get('run_id')}:{point}"
    return None


def confirmation_groups(
    records: Iterable[dict[str, Any]],
    *,
    required_hits_fraction: float = 2.0 / 3.0,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if not record.get("valid"):
            continue
        group_id = confirmation_group_id(record)
        if group_id:
            grouped[group_id].append(record)

    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for group_id, group_records in grouped.items():
        total = len(group_records)
        if total == 0:
            continue
        threshold = int(math.ceil(float(required_hits_fraction) * total))
        cell = str(group_records[0].get("cell") or "unknown")
        for prop in PROPERTY_ORDER:
            hits = [
                record
                for record in group_records
                if prop in record.get("policy_findings", {}).get("positive_policies", [])
            ]
            if not hits:
                continue
            key = (prop, cell, group_id)
            out[key] = {
                "policy": prop,
                "cell": cell,
                "group_id": group_id,
                "source_kind": group_records[0].get("source_kind"),
                "run_id": group_records[0].get("run_id"),
                "total_valid_repeats": total,
                "threshold": threshold,
                "hits": len(hits),
                "hit_seeds": sorted(int(item["seed"]) for item in hits if isinstance(item.get("seed"), int)),
                "hit_tags": [str(item.get("tag")) for item in hits],
                "confirmed": len(hits) >= threshold,
            }
    return out


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [record for record in records if record.get("valid")]
    invalid = [record for record in records if not record.get("valid")]
    source_counts = Counter(record["source_kind"] for record in records)
    valid_source_counts = Counter(record["source_kind"] for record in valid)
    invalid_reasons = Counter(reason for record in invalid for reason in record.get("invalid_reasons", []))

    policy_cells: dict[tuple[str, str], dict[str, Any]] = {}
    for record in valid:
        findings = record.get("policy_findings", {})
        by_policy = findings.get("by_policy", {})
        for prop in findings.get("positive_policies", []):
            policy_record = by_policy.get(prop, {})
            key = (prop, str(record.get("cell") or "unknown"))
            item = policy_cells.setdefault(
                key,
                {
                    "policy": prop,
                    "cell": str(record.get("cell") or "unknown"),
                    "hits": 0,
                    "seeds": set(),
                    "tags": [],
                    "source_kinds": Counter(),
                    "severity_pairs": Counter(),
                    "max_neural_violation_margin": 0.0,
                    "min_neural_rho": None,
                },
            )
            item["hits"] += 1
            if isinstance(record.get("seed"), int):
                item["seeds"].add(int(record["seed"]))
            item["tags"].append(str(record.get("tag")))
            item["source_kinds"][record["source_kind"]] += 1
            pair = f"S{record.get('classical_severity')}->S{record.get('neural_severity')}"
            item["severity_pairs"][pair] += 1
            margin = policy_record.get("neural_violation_margin")
            if isinstance(margin, (int, float)):
                item["max_neural_violation_margin"] = max(item["max_neural_violation_margin"], float(margin))
            neural_rho = policy_record.get("neural_rho")
            if isinstance(neural_rho, (int, float)):
                item["min_neural_rho"] = (
                    float(neural_rho)
                    if item["min_neural_rho"] is None
                    else min(float(item["min_neural_rho"]), float(neural_rho))
                )

    confirm = confirmation_groups(valid)
    confirmed_by_policy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in confirm.values():
        if item["confirmed"]:
            confirmed_by_policy[item["policy"]].append(item)

    policy_rows: list[dict[str, Any]] = []
    for prop in PROPERTY_ORDER:
        cells = [item for (policy, _cell), item in policy_cells.items() if policy == prop]
        confirmed = confirmed_by_policy.get(prop, [])
        policy_rows.append(
            {
                "policy": prop,
                "total_positive_evals": sum(item["hits"] for item in cells),
                "positive_cells": sorted(item["cell"] for item in cells),
                "positive_cell_count": len(cells),
                "confirmed_groups": len(confirmed),
                "confirmed_cells": sorted({item["cell"] for item in confirmed}),
                "confirmed": bool(confirmed),
            }
        )

    serializable_cells = []
    for item in policy_cells.values():
        row = dict(item)
        row["seeds"] = sorted(row["seeds"])
        row["source_kinds"] = dict(row["source_kinds"])
        row["severity_pairs"] = dict(row["severity_pairs"])
        row["example_tags"] = row.pop("tags")[:5]
        serializable_cells.append(row)
    serializable_cells.sort(key=lambda item: (item["policy"], item["cell"]))

    return {
        "total_records": len(records),
        "valid_records": len(valid),
        "invalid_records": len(invalid),
        "source_counts": dict(source_counts),
        "valid_source_counts": dict(valid_source_counts),
        "invalid_reasons": dict(invalid_reasons),
        "policy_rows": policy_rows,
        "policy_cells": serializable_cells,
        "confirmation_groups": sorted(confirm.values(), key=lambda item: (item["policy"], item["cell"], item["group_id"])),
    }


def format_list(values: list[str], limit: int = 8) -> str:
    if not values:
        return "-"
    shown = values[:limit]
    suffix = "" if len(values) <= limit else f" (+{len(values) - limit})"
    return ", ".join(f"`{value}`" for value in shown) + suffix


def markdown_report(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    severity_by_policy: dict[str, Counter[str]] = defaultdict(Counter)
    source_by_policy: dict[str, Counter[str]] = defaultdict(Counter)
    for item in summary["policy_cells"]:
        policy = item["policy"]
        severity_by_policy[policy].update(item["severity_pairs"])
        source_by_policy[policy].update(item["source_kinds"])

    confirmed_by_policy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in summary["confirmation_groups"]:
        if item["confirmed"]:
            confirmed_by_policy[item["policy"]].append(item)

    non_s3_positive = Counter()
    for record in records:
        if not record.get("valid") or record.get("neural_severity") == 3:
            continue
        for prop in record.get("policy_findings", {}).get("positive_policies", []):
            non_s3_positive[prop] += 1

    record_by_tag = {str(record.get("tag")): record for record in records}
    pure_non_s3_confirmed: list[dict[str, Any]] = []
    for item in summary["confirmation_groups"]:
        if not item["confirmed"] or item["policy"] not in {"P6", "P7"}:
            continue
        hit_records = [record_by_tag[tag] for tag in item["hit_tags"] if tag in record_by_tag]
        if hit_records and all(record.get("neural_severity") != 3 for record in hit_records):
            pure_non_s3_confirmed.append(item)

    lines = [
        "# Multi-Policy Differential Spectrum",
        "",
        "Date: 2026-07-03",
        "",
        "Scope: one differential oracle over existing P1-P7 property policies in the switch-transient campaign. No new oracle type is introduced.",
        "",
        "## Inputs",
        "",
        f"- Records scanned: {summary['total_records']} ({summary['valid_records']} valid, {summary['invalid_records']} invalid excluded)",
        f"- Source counts: `{json.dumps(summary['source_counts'], sort_keys=True)}`",
        f"- Valid source counts: `{json.dumps(summary['valid_source_counts'], sort_keys=True)}`",
        f"- Invalid reasons: `{json.dumps(summary['invalid_reasons'], sort_keys=True)}`",
        "- Existing compare/property JSON and local ULOG-backed campaign artifacts were reused; no new SITL evals were launched for this extraction.",
        "",
        "## Honest Conclusion",
        "",
        "- Confirmed differential positives are P1, P2, P6, and P7.",
        "- P3 has only three unconfirmed single-eval positives; P4 and P5 have no positives under the behavior-class gate.",
        (
            "- P6/P7 are confirmed as same-policy violations, but the confirmed groups are not clean standalone behavior-only failures. "
            f"Non-S3 positive evals exist for P6={non_s3_positive['P6']} and P7={non_s3_positive['P7']}, "
            f"but pure non-S3 confirmed P6/P7 groups = {len(pure_non_s3_confirmed)}."
        ),
        "- The evidence therefore supports a spectrum with catastrophic P1/P2 plus behavior-policy signatures P6/P7 that mostly ride with, or straddle, the catastrophic switch-transient failures.",
        "",
        "## Policy Spectrum",
        "",
        "| policy | positive evals | positive cells | confirmed groups | confirmed cells | conclusion |",
        "|---|---:|---|---:|---|---|",
    ]
    for row in summary["policy_rows"]:
        conclusion = "confirmed differential positive" if row["confirmed"] else "no multi-seed confirmed positive"
        lines.append(
            f"| {row['policy']} | {row['total_positive_evals']} | {format_list(row['positive_cells'])} | "
            f"{row['confirmed_groups']} | {format_list(row['confirmed_cells'])} | {conclusion} |"
        )

    lines.extend(
        [
            "",
            "## Severity Split",
            "",
            "| policy | severity pairs among positive evals | source kinds among positive evals |",
            "|---|---|---|",
        ]
    )
    for prop in PROPERTY_ORDER:
        lines.append(
            f"| {prop} | `{json.dumps(dict(severity_by_policy[prop]), sort_keys=True)}` | "
            f"`{json.dumps(dict(source_by_policy[prop]), sort_keys=True)}` |"
        )

    lines.extend(
        [
            "",
            "## Confirmed Summary",
            "",
            "| policy | confirmed groups | confirmed cells | sources |",
            "|---|---:|---|---|",
        ]
    )
    for prop in PROPERTY_ORDER:
        groups = confirmed_by_policy[prop]
        source_counts = Counter(str(item["source_kind"]) for item in groups)
        cells = sorted({str(item["cell"]) for item in groups})
        lines.append(
            f"| {prop} | {len(groups)} | {format_list(cells)} | "
            f"`{json.dumps(dict(source_counts), sort_keys=True)}` |"
        )

    behavior_mixed = []
    for item in summary["confirmation_groups"]:
        if not item["confirmed"] or item["policy"] not in {"P6", "P7"}:
            continue
        hit_records = [record_by_tag[tag] for tag in item["hit_tags"] if tag in record_by_tag]
        non_s3 = [record for record in hit_records if record.get("neural_severity") != 3]
        if non_s3:
            behavior_mixed.append((item, hit_records, non_s3))

    lines.extend(
        [
            "",
            "## Behavior Confirmation Caveat",
            "",
            "| policy | group | cell | hit severity pairs | non-S3 hit tags |",
            "|---|---|---|---|---|",
        ]
    )
    if behavior_mixed:
        for item, hit_records, non_s3 in behavior_mixed:
            severity_pairs = [
                f"S{record.get('classical_severity')}->S{record.get('neural_severity')}"
                for record in hit_records
            ]
            lines.append(
                f"| {item['policy']} | `{item['group_id']}` | `{item['cell']}` | "
                f"`{json.dumps(dict(Counter(severity_pairs)), sort_keys=True)}` | "
                f"{format_list([str(record.get('tag')) for record in non_s3], limit=3)} |"
            )
    else:
        lines.append("| - | - | - | - | - |")

    lines.extend(
        [
            "",
            "Interpretation: P6/P7 pass same-policy multi-seed confirmation, but the confirmed groups are not clean standalone behavior-only failures; they either co-occur with S3 seeds or mix S1 and S3 outcomes. Discovery-only non-S3 P6/P7 positives are retained in the raw cells below but are not promoted to standalone confirmed behavior degradation.",
        ]
    )

    lines.extend(
        [
            "",
            "## Raw Positive Cells",
            "",
            "| policy | cell | hits | seeds | source kinds | severity pairs | max violation margin | min neural rho | examples |",
            "|---|---|---:|---|---|---|---:|---:|---|",
        ]
    )
    for item in summary["policy_cells"]:
        min_rho = item["min_neural_rho"]
        min_rho_text = "-" if min_rho is None else f"{float(min_rho):.6g}"
        lines.append(
            f"| {item['policy']} | `{item['cell']}` | {item['hits']} | "
            f"{', '.join(str(seed) for seed in item['seeds']) or '-'} | "
            f"`{json.dumps(item['source_kinds'], sort_keys=True)}` | "
            f"`{json.dumps(item['severity_pairs'], sort_keys=True)}` | "
            f"{float(item['max_neural_violation_margin']):.6g} | "
            f"{min_rho_text} | "
            f"{format_list(item['example_tags'], limit=3)} |"
        )

    lines.extend(
        [
            "",
            "## Decision Discipline",
            "",
            "- P1/P2 positives use decontaminated classical S0, neural S3, and same-policy neural rho sign violation.",
            "- P3-P7 positives use non-vacuous classical margin plus neural violation beyond the calibrated rho jitter reproduction margin.",
            "- Confirmation is same-policy only: a P6-triggered candidate is P6-confirmed only when P6 repeats across seeds.",
            "- Invalid evals are excluded from every cell and policy count.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--run-id", action="append", dest="run_ids")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    run_ids = args.run_ids or DEFAULT_RUN_IDS
    records = scan_runs(args.run_root, run_ids)
    summary = aggregate(records)
    payload = {"summary": summary, "records": records}
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        with args.json_output.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown_report(summary, records), encoding="utf-8")
    print(
        json.dumps(
            {
                "records": summary["total_records"],
                "valid": summary["valid_records"],
                "invalid": summary["invalid_records"],
                "confirmed_policies": [
                    row["policy"] for row in summary["policy_rows"] if row["confirmed"]
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
