#!/usr/bin/env python3
"""Rerun the four Route-A strict differential anchors.

The anchors are FUZZ-1c decontaminated pairs 1/2/4/5. This script reruns the
paired classical/mc_nn flights, then applies the same ULOG-only decontamination
logic used by docs/fuzz1c_decontam_20260625.md.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fuzz1c_decontam_analyze as decontam
import fuzz1c_severity_scan as severity_scan
import m1_diff_runner as m1
import property_oracle


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = REPO_ROOT / "runs" / "route_a_anchor_regression"
PAIR5_FIXED_SEEDS = [
    20261803,
    20261903,
    20262003,
    20262103,
    20262203,
    20262303,
    20262403,
    20262503,
    20262603,
]
PAIR1_RERUN_SEEDS = [20262001, 20262101]
PAIR4_CONFIRM_SEEDS = [20261902, 20262002]
PAIR4_GATE_A_PRIME_SEEDS = [
    20261802,
    20261902,
    20262002,
    20262102,
    20262202,
    20262302,
    20262402,
    20262502,
]
PAIR5_GATE_A_PRIME_SEEDS = [
    20261803,
    20261903,
    20262003,
    20262103,
    20262203,
    20262303,
    20262403,
    20262503,
]
BOUNDARY_ANCHOR_SEEDS = {
    "pair4": PAIR4_GATE_A_PRIME_SEEDS,
    "pair5": PAIR5_GATE_A_PRIME_SEEDS,
}
GATE_A_PRIME_BOUNDARY_STRICT_FLOOR = 6


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def anchor_cases() -> list[tuple[str, severity_scan.SeverityCase, int]]:
    high = severity_scan.SCAN_CASES[0]
    return [
        ("pair1", high, 20261800),
        ("pair2", replace(high, tag=f"{high.tag}_confirm1"), 20261901),
        ("pair4", severity_scan.SCAN_CASES[2], 20261802),
        ("pair5", severity_scan.SCAN_CASES[3], 20261803),
    ]


def gate_a_prime_cases() -> list[tuple[str, str, severity_scan.SeverityCase, int]]:
    high = severity_scan.SCAN_CASES[0]
    pair4_case = severity_scan.SCAN_CASES[2]
    pair5_case = severity_scan.SCAN_CASES[3]
    plan: list[tuple[str, str, severity_scan.SeverityCase, int]] = [
        ("pair1", "pair1", high, 20261800),
        ("pair2", "pair2", replace(high, tag=f"{high.tag}_confirm1"), 20261901),
    ]
    plan.extend(("pair4", f"pair4_seed_{seed}", pair4_case, seed) for seed in PAIR4_GATE_A_PRIME_SEEDS)
    plan.extend(("pair5", f"pair5_seed_{seed}", pair5_case, seed) for seed in PAIR5_GATE_A_PRIME_SEEDS)
    return plan


def exact_strict_s0_vs_s3(pair: dict[str, Any]) -> bool:
    csev = pair.get("classical", {}).get("control_level", {}).get("control_level_severity")
    nsev = pair.get("mcnn", {}).get("control_level", {}).get("control_level_severity")
    return csev == 0 and nsev == 3


def severity_label(pair: dict[str, Any], controller: str) -> str:
    return str(pair.get(controller, {}).get("control_level", {}).get("control_level_label", "-"))


def controller_severity(pair: dict[str, Any], controller: str) -> int | None:
    value = pair.get(controller, {}).get("control_level", {}).get("control_level_severity")
    return int(value) if isinstance(value, int) else None


def rho_sign_summary(pair: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "available": False,
        "classical_p1_p2_positive": False,
        "mcnn_catastrophic_negative_props": [],
        "controllers": {},
    }
    try:
        thresholds = property_oracle.load_thresholds(None)
        for controller in ("classical", "mcnn"):
            record = pair.get(controller, {})
            if not record:
                continue
            window = record.get("control_window", {})
            result = property_oracle.evaluate_ulog(
                repo_path(record["ulog"]),
                controller="mcnn" if controller == "mcnn" else "classical",
                thresholds=thresholds,
                analysis_start_us=int(window["start_us"]),
                analysis_end_us=int(window["end_us"]),
            )
            rhos = {prop: float(result["rho"][prop]) for prop in ("P1", "P2")}
            summary["controllers"][controller] = {
                "rho": rhos,
                "severity": result["severity"],
                "signs": {prop: ("negative" if value <= 0.0 else "positive") for prop, value in rhos.items()},
            }
        c_rhos = summary["controllers"].get("classical", {}).get("rho", {})
        n_rhos = summary["controllers"].get("mcnn", {}).get("rho", {})
        summary["classical_p1_p2_positive"] = bool(c_rhos.get("P1", -1.0) > 0.0 and c_rhos.get("P2", -1.0) > 0.0)
        summary["mcnn_catastrophic_negative_props"] = [
            prop for prop in ("P1", "P2") if isinstance(n_rhos.get(prop), float) and n_rhos[prop] <= 0.0
        ]
        summary["available"] = bool(summary["controllers"])
        summary["passes_sign_gate"] = bool(
            summary["classical_p1_p2_positive"] and summary["mcnn_catastrophic_negative_props"]
        )
    except Exception as exc:  # pragma: no cover - diagnostic path must not hide the failure.
        summary["error"] = repr(exc)
        summary["passes_sign_gate"] = False
    return summary


def classify_raw_pair(raw_pair: dict[str, Any], idx: int = 1) -> dict[str, Any]:
    judged = decontam.classify_pair(idx, raw_pair)
    judged["strict_s0_vs_s3"] = exact_strict_s0_vs_s3(judged)
    judged["rho_sign_summary"] = rho_sign_summary(judged) if judged.get("valid_matched_pair") else {"available": False}
    return judged


def decontaminate_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [classify_raw_pair(pair, idx) for idx, pair in enumerate(pairs, start=1)]
    strict = [pair for pair in judged if pair.get("strict_s0_vs_s3")]
    unresolved = [pair for pair in judged if pair.get("decision") == "UNRESOLVED"]
    skipped = [pair for pair in judged if pair.get("decision") == "SKIPPED_UNTESTED"]
    if strict and len(strict) == len(judged):
        decision = "STRICT_S0_VS_S3_CONFIRMED_4_OF_4"
    elif unresolved:
        decision = "UNRESOLVED"
    else:
        decision = "REGRESSION_FAILED"
    return {
        "decision": decision,
        "severity_gate": {
            "catastrophic_reproduction_uses": "decontaminated_control_level_severity_plus_p1_p2_sign",
            "strict_definition": "classical_control_severity_S0_and_mcnn_control_severity_S3",
            "continuous_rho_jitter_gate": False,
        },
        "pair_summary": {
            "valid_pairs": len([pair for pair in judged if pair.get("valid_matched_pair")]),
            "strict_differential_count": len(strict),
            "unresolved_count": len(unresolved),
            "skipped_untested_count": len(skipped),
            "expected_strict_differential_count": len(judged),
        },
        "severity_invariance_summary": decontam.stable_invariance_summary(judged),
        "pairs": judged,
    }


def write_summary(run_dir: Path, result: dict[str, Any]) -> None:
    lines = [
        "# Route-A Anchor Regression",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        f"decision: {result['decision']}",
        "",
        "## Counts",
        "",
        "```json",
        json.dumps(result["pair_summary"], indent=2, sort_keys=True),
        "```",
        "",
        "## Anchors",
        "",
        "| anchor | case | classical control severity | mc_nn control severity | strict S0 vs S3 | decision |",
        "|---|---|---|---|---|---|",
    ]
    for label, pair in zip([item[0] for item in anchor_cases()], result["pairs"]):
        csev = pair.get("classical", {}).get("control_level", {}).get("control_level_label", "-")
        nsev = pair.get("mcnn", {}).get("control_level", {}).get("control_level_label", "-")
        lines.append(
            f"| {label} | {pair.get('case')} | {csev} | {nsev} | {pair.get('strict_s0_vs_s3')} | {pair.get('decision')} |"
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- raw severity results: `{(run_dir / 'severity_results.json').relative_to(REPO_ROOT)}`",
            f"- decontaminated results: `{(run_dir / 'decontam_results.json').relative_to(REPO_ROOT)}`",
        ]
    )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def find_pair_by_case(pairs: list[dict[str, Any]], case: str) -> dict[str, Any]:
    for pair in pairs:
        if pair.get("case") == case:
            return pair
    raise KeyError(case)


def imported_record(
    *,
    anchor_group: str,
    label: str,
    seed: int,
    pair: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    out = {
        "anchor_group": anchor_group,
        "label": label,
        "case": pair.get("case"),
        "seed": int(seed),
        "source": source,
        "judged": pair,
        "strict_s0_vs_s3": exact_strict_s0_vs_s3(pair),
        "mcnn_s3": controller_severity(pair, "mcnn") == 3,
        "classical_s0": controller_severity(pair, "classical") == 0,
    }
    out["rho_sign_summary"] = rho_sign_summary(pair) if pair.get("valid_matched_pair") else {"available": False}
    return out


def run_diagnostic_pair(
    *,
    repo: Path,
    run_dir: Path,
    run_id: str,
    env: dict[str, str],
    run_timeout: int,
    safety_config: Path,
    anchor_group: str,
    label: str,
    case: severity_scan.SeverityCase,
    seed: int,
) -> dict[str, Any]:
    print(f"ROUTE_A_DIAG={label} GROUP={anchor_group} CASE={case.tag} SEED={seed}", flush=True)
    raw_pair = severity_scan.run_pair(repo, run_dir, run_id, case, seed, env, run_timeout, safety_config)
    raw_pair["anchor_label"] = label
    judged = classify_raw_pair(raw_pair)
    return {
        "anchor_group": anchor_group,
        "label": label,
        "case": judged.get("case"),
        "seed": int(seed),
        "source": "new_eval",
        "raw_pair": raw_pair,
        "judged": judged,
        "strict_s0_vs_s3": exact_strict_s0_vs_s3(judged),
        "mcnn_s3": controller_severity(judged, "mcnn") == 3,
        "classical_s0": controller_severity(judged, "classical") == 0,
        "rho_sign_summary": judged.get("rho_sign_summary", {}),
    }


def threshold_2of3(total: int) -> int:
    return int(math.ceil((2.0 * total) / 3.0))


def group_summary(records: list[dict[str, Any]], group: str) -> dict[str, Any]:
    group_records = [record for record in records if record.get("anchor_group") == group]
    attempts = len(group_records)
    strict_hits = len([record for record in group_records if record.get("strict_s0_vs_s3")])
    mcnn_s3_hits = len([record for record in group_records if record.get("mcnn_s3")])
    classical_s0_hits = len([record for record in group_records if record.get("classical_s0")])
    valid = len([record for record in group_records if record.get("judged", {}).get("valid_matched_pair")])
    threshold = threshold_2of3(attempts) if attempts else 0
    return {
        "attempts": attempts,
        "valid_matched_pairs": valid,
        "strict_s0_vs_s3_hits": strict_hits,
        "mcnn_s3_hits": mcnn_s3_hits,
        "classical_s0_hits": classical_s0_hits,
        "hit_rate": strict_hits / attempts if attempts else 0.0,
        "mcnn_s3_rate": mcnn_s3_hits / attempts if attempts else 0.0,
        "threshold_2of3": threshold,
        "passed_2of3": attempts > 0 and strict_hits >= threshold,
        "passed_3of3": attempts > 0 and strict_hits == attempts,
        "records": [
            {
                "label": record.get("label"),
                "case": record.get("case"),
                "seed": record.get("seed"),
                "source": record.get("source"),
                "strict_s0_vs_s3": record.get("strict_s0_vs_s3"),
                "classical": severity_label(record.get("judged", {}), "classical"),
                "mcnn": severity_label(record.get("judged", {}), "mcnn"),
                "rho_sign_gate": record.get("rho_sign_summary", {}).get("passes_sign_gate"),
                "mcnn_negative_props": record.get("rho_sign_summary", {}).get("mcnn_catastrophic_negative_props", []),
            }
            for record in group_records
        ],
    }


def canonical_gate_a_group(record: dict[str, Any]) -> str | None:
    group = str(record.get("anchor_group") or "")
    if group in {"pair1", "pair2", "pair4", "pair5"}:
        return group
    label = str(record.get("label") or record.get("anchor_label") or "")
    for candidate in ("pair1", "pair2", "pair4", "pair5"):
        if label.startswith(candidate):
            return candidate
    return None


def gate_a_record_row(record: dict[str, Any]) -> dict[str, Any]:
    judged = record.get("judged", {}) if isinstance(record.get("judged"), dict) else {}
    return {
        "label": record.get("label"),
        "case": record.get("case") or judged.get("case"),
        "seed": record.get("seed"),
        "source": record.get("source"),
        "strict_s0_vs_s3": bool(record.get("strict_s0_vs_s3")),
        "classical_s0": bool(record.get("classical_s0")),
        "mcnn_s3": bool(record.get("mcnn_s3")),
        "classical": severity_label(judged, "classical") if judged else "-",
        "mcnn": severity_label(judged, "mcnn") if judged else "-",
        "rho_sign_gate": record.get("rho_sign_summary", {}).get("passes_sign_gate"),
        "mcnn_negative_props": record.get("rho_sign_summary", {}).get("mcnn_catastrophic_negative_props", []),
    }


def summarize_deep_gate_a_anchor(records: list[dict[str, Any]], group: str) -> dict[str, Any]:
    group_records = sorted(
        [record for record in records if canonical_gate_a_group(record) == group],
        key=lambda item: int(item.get("seed") or 0),
    )
    strict_hits = sum(1 for record in group_records if record.get("strict_s0_vs_s3"))
    passed = bool(group_records) and strict_hits == len(group_records)
    return {
        "attempts": len(group_records),
        "strict_s0_vs_s3_hits": strict_hits,
        "passed": passed,
        "required": "all provided deep-anchor records must be strict S0/S3",
        "records": [gate_a_record_row(record) for record in group_records],
    }


def summarize_boundary_gate_a_anchor(records: list[dict[str, Any]], group: str) -> dict[str, Any]:
    expected_seeds = BOUNDARY_ANCHOR_SEEDS[group]
    expected = set(expected_seeds)
    group_records = sorted(
        [
            record
            for record in records
            if canonical_gate_a_group(record) == group and int(record.get("seed") or -1) in expected
        ],
        key=lambda item: int(item.get("seed") or 0),
    )
    present = {int(record.get("seed") or -1) for record in group_records}
    strict_seeds = [
        int(record.get("seed"))
        for record in group_records
        if record.get("seed") is not None and record.get("strict_s0_vs_s3")
    ]
    non_strict_seeds = [
        int(record.get("seed"))
        for record in group_records
        if record.get("seed") is not None and not record.get("strict_s0_vs_s3")
    ]
    missing_seeds = [seed for seed in expected_seeds if seed not in present]
    strict_hits = len(strict_seeds)
    expected_attempts = len(expected_seeds)
    passed = not missing_seeds and strict_hits >= GATE_A_PRIME_BOUNDARY_STRICT_FLOOR
    return {
        "expected_seeds": expected_seeds,
        "attempts": len(group_records),
        "expected_attempts": expected_attempts,
        "strict_s0_vs_s3_hits": strict_hits,
        "strict_floor": GATE_A_PRIME_BOUNDARY_STRICT_FLOOR,
        "hit_rate": strict_hits / expected_attempts if expected_attempts else 0.0,
        "passed": passed,
        "strict_seeds": strict_seeds,
        "non_strict_seeds": non_strict_seeds,
        "missing_seeds": missing_seeds,
        "records": [gate_a_record_row(record) for record in group_records],
    }


def evaluate_gate_a_prime(records: list[dict[str, Any]]) -> dict[str, Any]:
    deep = {group: summarize_deep_gate_a_anchor(records, group) for group in ("pair1", "pair2")}
    boundary = {group: summarize_boundary_gate_a_anchor(records, group) for group in ("pair4", "pair5")}
    gate_passed = all(item["passed"] for item in deep.values()) and all(item["passed"] for item in boundary.values())
    return {
        "decision": "GATE_A_PRIME_PASS" if gate_passed else "GATE_A_PRIME_BLOCKED",
        "gate_passed": gate_passed,
        "criteria": {
            "deep_hard_gate": "pair1 and pair2 must be strict S0/S3",
            "boundary_probability_gate": "pair4 and pair5 strict S0/S3 rate must be >=6/8 on fixed seed sets",
            "boundary_fixed_seed_sets": BOUNDARY_ANCHOR_SEEDS,
            "boundary_strict_floor": GATE_A_PRIME_BOUNDARY_STRICT_FLOOR,
            "boundary_single_seed_flip_policy": "reported in per-seed rows; not a shim failure by itself",
        },
        "deep_anchors": deep,
        "boundary_anchors": boundary,
        "records": records,
    }


def write_gate_a_prime_summary(run_dir: Path, result: dict[str, Any]) -> None:
    lines = [
        "# Route-A Anchor Regression - Gate A Prime",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        f"decision: {result['decision']}",
        "",
        "## Criteria",
        "",
        "- hard gate: pair1 and pair2 must be strict S0/S3.",
        "- boundary gate: pair4 and pair5 each need at least 6 strict S0/S3 hits in the fixed 8-seed set.",
        "- boundary single-seed S0/S1 flips are reported as probability evidence, not shim failures.",
        "",
        "## Deep Anchors",
        "",
        "| anchor | attempts | strict hits | passed |",
        "|---|---:|---:|---|",
    ]
    for group, summary in result["deep_anchors"].items():
        lines.append(
            f"| {group} | {summary['attempts']} | {summary['strict_s0_vs_s3_hits']} | {summary['passed']} |"
        )
    lines.extend(
        [
            "",
            "## Boundary Anchors",
            "",
            "| anchor | attempts | strict hits | hit rate | floor | passed | non-strict seeds | missing seeds |",
            "|---|---:|---:|---:|---:|---|---|---|",
        ]
    )
    for group, summary in result["boundary_anchors"].items():
        lines.append(
            f"| {group} | {summary['attempts']}/{summary['expected_attempts']} | "
            f"{summary['strict_s0_vs_s3_hits']} | {summary['hit_rate']:.3f} | "
            f"{summary['strict_floor']} | {summary['passed']} | "
            f"{summary['non_strict_seeds']} | {summary['missing_seeds']} |"
        )
    lines.extend(["", "## Per-Seed Boundary Rows", "", "| anchor | seed | classical | mc_nn | strict | sign gate |"])
    lines.append("|---|---:|---|---|---|---|")
    for group, summary in result["boundary_anchors"].items():
        for record in summary["records"]:
            lines.append(
                f"| {group} | {record['seed']} | {record['classical']} | {record['mcnn']} | "
                f"{record['strict_s0_vs_s3']} | {record['rho_sign_gate']} |"
            )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- gate results: `{(run_dir / 'gate_a_prime_results.json').relative_to(REPO_ROOT)}`",
            f"- gate records: `{(run_dir / 'gate_a_prime_records.json').relative_to(REPO_ROOT)}`",
        ]
    )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_addendum3_diagnostics(args: argparse.Namespace) -> int:
    repo = m1.repo_root()
    run_dir = (args.run_root / args.run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    env = m1.agent_env(repo)
    env["PX4_SIM_SPEED_FACTOR"] = str(args.sim_speed_factor)
    os.environ["PX4_SIM_SPEED_FACTOR"] = str(args.sim_speed_factor)
    severity_scan.build_if_needed(repo, run_dir, env, args.rebuild)

    baseline_path = repo_path(args.reuse_decontam)
    baseline = load_json(baseline_path)
    baseline_pairs = baseline["pairs"]
    high = severity_scan.SCAN_CASES[0]
    pair4_case = severity_scan.SCAN_CASES[2]
    pair5_case = severity_scan.SCAN_CASES[3]
    pair2_case = f"{high.tag}_confirm1"

    records: list[dict[str, Any]] = [
        imported_record(
            anchor_group="pair1_pair2_high_theta",
            label="pair2_reused_current",
            seed=20261901,
            pair=find_pair_by_case(baseline_pairs, pair2_case),
            source=str(baseline_path.relative_to(REPO_ROOT)),
        ),
        imported_record(
            anchor_group="pair4",
            label="pair4_reused_current",
            seed=20261802,
            pair=find_pair_by_case(baseline_pairs, pair4_case.tag),
            source=str(baseline_path.relative_to(REPO_ROOT)),
        ),
        imported_record(
            anchor_group="pair5",
            label="pair5_reused_fixed_seed_20261803",
            seed=20261803,
            pair=find_pair_by_case(baseline_pairs, pair5_case.tag),
            source=str(baseline_path.relative_to(REPO_ROOT)),
        ),
    ]
    write_json(run_dir / "diagnostic_records.json", {"records": records})

    plan: list[tuple[str, str, severity_scan.SeverityCase, int]] = []
    for idx, seed in enumerate(PAIR1_RERUN_SEEDS, start=1):
        plan.append(("pair1_pair2_high_theta", f"pair1_rerun_{idx}", high, seed))
    for idx, seed in enumerate(PAIR4_CONFIRM_SEEDS, start=1):
        plan.append(("pair4", f"pair4_confirm_{idx}", pair4_case, seed))
    for seed in PAIR5_FIXED_SEEDS:
        if seed == 20261803:
            continue
        plan.append(("pair5", f"pair5_fixed_seed_{seed}", pair5_case, seed))

    for anchor_group, label, case, seed in plan:
        record = run_diagnostic_pair(
            repo=repo,
            run_dir=run_dir,
            run_id=args.run_id,
            env=env,
            run_timeout=args.run_timeout,
            safety_config=args.safety_config,
            anchor_group=anchor_group,
            label=label,
            case=case,
            seed=seed,
        )
        records.append(record)
        write_json(run_dir / "diagnostic_records.json", {"records": records})

    groups = {
        group: group_summary(records, group)
        for group in ("pair1_pair2_high_theta", "pair4", "pair5")
    }
    pair5 = groups["pair5"]
    pair5_retained = bool(pair5["passed_2of3"])
    final_anchor_groups = ["pair1_pair2_high_theta", "pair4"] + (["pair5"] if pair5_retained else [])
    gate_passed = all(groups[group]["passed_2of3"] for group in final_anchor_groups)
    result = {
        "run_id": args.run_id,
        "decision": "ADDENDUM3_DIAGNOSTIC_PASS" if gate_passed else "ADDENDUM3_DIAGNOSTIC_BLOCKED",
        "criteria": {
            "pair2_pair4_reproduction_gate": "PASS: decontaminated severity labels stable and catastrophic P1/P2 signs stable; continuous rho jitter is diagnostic only",
            "strict_definition": "classical_control_severity_S0_and_mcnn_control_severity_S3",
            "confirmation_thresholds": "report >=2/3 and 3/3; pass uses >=2/3 on final anchors",
            "pair5_fixed_seed_set": PAIR5_FIXED_SEEDS,
            "pair5_reused_seed": 20261803,
        },
        "groups": groups,
        "pair5_verdict": {
            "decision": "retain_as_strict_anchor" if pair5_retained else "downgrade_to_rq3_boundary_point",
            "strict_s0_vs_s3_hits": pair5["strict_s0_vs_s3_hits"],
            "attempts": pair5["attempts"],
            "hit_rate": pair5["hit_rate"],
            "mcnn_s3_hits": pair5["mcnn_s3_hits"],
            "mcnn_s3_rate": pair5["mcnn_s3_rate"],
            "threshold_2of3": pair5["threshold_2of3"],
            "passed_3of3": pair5["passed_3of3"],
        },
        "final_anchor_groups": final_anchor_groups,
        "final_anchor_count": 4 if pair5_retained else 3,
        "gate_passed": gate_passed,
        "records": records,
    }
    write_json(run_dir / "diagnostic_results.json", result)
    write_addendum3_summary(run_dir, result)
    print(f"ADDENDUM3_DIAGNOSTIC_DECISION={result['decision']}")
    print(f"PAIR5_VERDICT={result['pair5_verdict']['decision']}")
    print(f"FINAL_ANCHOR_COUNT={result['final_anchor_count']}")
    print(f"ADDENDUM3_SUMMARY={run_dir / 'summary.md'}")
    return 0 if gate_passed else 1


def write_addendum3_summary(run_dir: Path, result: dict[str, Any]) -> None:
    lines = [
        "# Route-A Anchor Diagnostic Addendum 3",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        f"decision: {result['decision']}",
        "",
        "## Criteria",
        "",
        "- pair2/pair4 reproduction gate: PASS by decontaminated severity + catastrophic P1/P2 sign stability.",
        "- continuous P1/P2 rho is diagnostic only for catastrophic anchors, not a jitter-band gate.",
        "- strict anchor definition: classical S0 and mc_nn S3 after decontamination.",
        "",
        "## Groups",
        "",
        "| group | attempts | strict hits | hit rate | >=2/3 | 3/3 |",
        "|---|---:|---:|---:|---|---|",
    ]
    for group, summary in result["groups"].items():
        lines.append(
            f"| {group} | {summary['attempts']} | {summary['strict_s0_vs_s3_hits']} | "
            f"{summary['hit_rate']:.3f} | {summary['passed_2of3']} | {summary['passed_3of3']} |"
        )
    lines.extend(
        [
            "",
            "## Pair5 Verdict",
            "",
            "```json",
            json.dumps(result["pair5_verdict"], indent=2, sort_keys=True),
            "```",
            "",
            "## Records",
            "",
            "| group | label | seed | classical | mc_nn | strict | sign gate |",
            "|---|---|---:|---|---|---|---|",
        ]
    )
    for group, summary in result["groups"].items():
        for record in summary["records"]:
            lines.append(
                f"| {group} | {record['label']} | {record['seed']} | {record['classical']} | "
                f"{record['mcnn']} | {record['strict_s0_vs_s3']} | {record['rho_sign_gate']} |"
            )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- diagnostic records: `{(run_dir / 'diagnostic_records.json').relative_to(REPO_ROOT)}`",
            f"- diagnostic results: `{(run_dir / 'diagnostic_results.json').relative_to(REPO_ROOT)}`",
        ]
    )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def gate_a_prime_records_from_artifacts(decontam_path: Path, diagnostic_records_path: Path) -> list[dict[str, Any]]:
    decontam_payload = load_json(decontam_path)
    diagnostic_payload = load_json(diagnostic_records_path)
    records: list[dict[str, Any]] = []
    for label, pair in zip([item[0] for item in anchor_cases()], decontam_payload.get("pairs", [])):
        if label not in {"pair1", "pair2"}:
            continue
        _, _, seed = next(item for item in anchor_cases() if item[0] == label)
        records.append(
            imported_record(
                anchor_group=label,
                label=label,
                seed=seed,
                pair=pair,
                source=str(decontam_path.relative_to(REPO_ROOT)),
            )
        )
    for record in diagnostic_payload.get("records", []):
        group = canonical_gate_a_group(record)
        if group in BOUNDARY_ANCHOR_SEEDS and int(record.get("seed") or -1) in set(BOUNDARY_ANCHOR_SEEDS[group]):
            records.append(record)
    return records


def run_gate_a_prime_from_artifacts(args: argparse.Namespace) -> int:
    run_dir = (args.run_root / args.run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    records = gate_a_prime_records_from_artifacts(
        repo_path(args.reuse_decontam),
        repo_path(args.reuse_diagnostic_records),
    )
    write_json(run_dir / "gate_a_prime_records.json", {"records": records})
    result = evaluate_gate_a_prime(records)
    result["run_id"] = args.run_id
    result["source_artifacts"] = {
        "deep_anchor_decontam": str(repo_path(args.reuse_decontam).relative_to(REPO_ROOT)),
        "boundary_diagnostic_records": str(repo_path(args.reuse_diagnostic_records).relative_to(REPO_ROOT)),
    }
    write_json(run_dir / "gate_a_prime_results.json", result)
    write_gate_a_prime_summary(run_dir, result)
    print(f"GATE_A_PRIME_DECISION={result['decision']}")
    print(f"GATE_A_PRIME_SUMMARY={run_dir / 'summary.md'}")
    return 0 if result["gate_passed"] else 1


def run_gate_a_prime(args: argparse.Namespace) -> int:
    repo = m1.repo_root()
    run_dir = (args.run_root / args.run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    env = m1.agent_env(repo)
    env["PX4_SIM_SPEED_FACTOR"] = str(args.sim_speed_factor)
    os.environ["PX4_SIM_SPEED_FACTOR"] = str(args.sim_speed_factor)
    severity_scan.build_if_needed(repo, run_dir, env, args.rebuild)

    records: list[dict[str, Any]] = []
    for anchor_group, label, case, seed in gate_a_prime_cases():
        record = run_diagnostic_pair(
            repo=repo,
            run_dir=run_dir,
            run_id=args.run_id,
            env=env,
            run_timeout=args.run_timeout,
            safety_config=args.safety_config,
            anchor_group=anchor_group,
            label=label,
            case=case,
            seed=seed,
        )
        records.append(record)
        write_json(run_dir / "gate_a_prime_records.json", {"records": records})

    result = evaluate_gate_a_prime(records)
    result["run_id"] = args.run_id
    write_json(run_dir / "gate_a_prime_results.json", result)
    write_json(run_dir / "decontam_results.json", result)
    write_gate_a_prime_summary(run_dir, result)
    print(f"GATE_A_PRIME_DECISION={result['decision']}")
    print(f"GATE_A_PRIME_SUMMARY={run_dir / 'summary.md'}")
    return 0 if result["gate_passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("route_a_anchor_%Y%m%dT%H%M%SZ"))
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--run-timeout", type=int, default=210)
    parser.add_argument("--sim-speed-factor", type=float, default=1.25)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--safety-config", type=Path, default=REPO_ROOT / "config/m2_safety_envelope.json")
    parser.add_argument("--addendum3-diagnostics", action="store_true")
    parser.add_argument("--gate-a-prime-from-artifacts", action="store_true")
    parser.add_argument(
        "--reuse-decontam",
        type=Path,
        default=REPO_ROOT
        / "runs/route_a_anchor_regression/route_a_anchor_regression_20260629/decontam_results.json",
    )
    parser.add_argument(
        "--reuse-diagnostic-records",
        type=Path,
        default=REPO_ROOT
        / "runs/route_a_anchor_regression/wave2_gateA_diag_multiseed_20260703/diagnostic_records.json",
    )
    args = parser.parse_args()

    if args.addendum3_diagnostics:
        return run_addendum3_diagnostics(args)
    if args.gate_a_prime_from_artifacts:
        return run_gate_a_prime_from_artifacts(args)
    return run_gate_a_prime(args)

    repo = m1.repo_root()
    run_dir = (args.run_root / args.run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    env = m1.agent_env(repo)
    env["PX4_SIM_SPEED_FACTOR"] = str(args.sim_speed_factor)
    os.environ["PX4_SIM_SPEED_FACTOR"] = str(args.sim_speed_factor)
    severity_scan.build_if_needed(repo, run_dir, env, args.rebuild)

    pairs: list[dict[str, Any]] = []
    for label, case, seed in anchor_cases():
        print(f"ROUTE_A_ANCHOR={label} CASE={case.tag} SEED={seed}", flush=True)
        pair = severity_scan.run_pair(repo, run_dir, args.run_id, case, seed, env, args.run_timeout, args.safety_config)
        pair["anchor_label"] = label
        pairs.append(pair)
        write_json(run_dir / "severity_results.json", {"pairs": pairs})

    severity_payload = {
        "run_id": args.run_id,
        "anchors": [
            {"label": label, "case": case.tag, "seed": seed}
            for label, case, seed in anchor_cases()
        ],
        "pairs": pairs,
    }
    write_json(run_dir / "severity_results.json", severity_payload)
    result = decontaminate_pairs(pairs)
    result["run_id"] = args.run_id
    result["severity_results"] = str((run_dir / "severity_results.json").relative_to(REPO_ROOT))
    write_json(run_dir / "decontam_results.json", result)
    write_summary(run_dir, result)

    print(f"ROUTE_A_REGRESSION_DECISION={result['decision']}")
    print(f"ROUTE_A_STRICT_COUNT={result['pair_summary']['strict_differential_count']}")
    print(f"ROUTE_A_SUMMARY={run_dir / 'summary.md'}")
    return 0 if result["decision"] == "STRICT_S0_VS_S3_CONFIRMED_4_OF_4" else 1


if __name__ == "__main__":
    raise SystemExit(main())
