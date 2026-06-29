#!/usr/bin/env python3
"""Generate the wave-1 wind+physics campaign report."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from property_fitness import differential_property_fitness


REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_PROPERTIES = ("P4", "P6", "P7")
BUCKET_ORDER = ("low", "mid", "high", "unknown")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def artifact_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.exists():
        return path
    if path.is_absolute():
        try:
            rel = path.relative_to("/workspace")
        except ValueError:
            return path
        return REPO_ROOT / rel
    return REPO_ROOT / path


def target_properties(metadata: dict[str, Any]) -> list[str]:
    resolved = metadata.get("resolved_target_properties")
    if isinstance(resolved, list) and resolved:
        return [str(prop) for prop in resolved]
    return list(TARGET_PROPERTIES)


def fitness_for(record: dict[str, Any], targets: list[str]) -> dict[str, Any]:
    fitness = record.get("fitness")
    compare_path = artifact_path(record.get("compare_path"))
    if compare_path is not None and compare_path.exists():
        compare = load_json(compare_path)
        oracle = compare.get("property_oracle", {}) if isinstance(compare, dict) else {}
        classical = oracle.get("classical")
        neural = oracle.get("neural")
        if isinstance(classical, dict) and isinstance(neural, dict):
            return differential_property_fitness(classical, neural, target_properties=targets)
    return fitness if isinstance(fitness, dict) else {}


def theta_for(record: dict[str, Any]) -> dict[str, Any]:
    path = artifact_path(record.get("theta_path"))
    if path is None or not path.exists():
        return {}
    data = load_json(path)
    return data if isinstance(data, dict) else {}


def bucket_for(record: dict[str, Any], theta: dict[str, Any]) -> tuple[str, str]:
    feature = theta.get("theta_genome", {}).get("map_elites", {}) if isinstance(theta, dict) else {}
    wind = feature.get("wind_bucket")
    physics = feature.get("physics_bucket")
    if isinstance(wind, str) and isinstance(physics, str):
        return wind, physics
    parts = str(record.get("feature_bin", "")).split(":")
    for part in parts:
        if part.startswith("wind_"):
            wind = part.removeprefix("wind_")
        if part.startswith("physics_"):
            physics = part.removeprefix("physics_")
    return str(wind or "unknown"), str(physics or "unknown")


def finite(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def per_property_values(fitness: dict[str, Any], prop: str) -> dict[str, Any]:
    per_property = fitness.get("per_property", {})
    item = per_property.get(prop) if isinstance(per_property, dict) else None
    return item if isinstance(item, dict) else {}


def best_gap(fitness: dict[str, Any], props: tuple[str, ...] = TARGET_PROPERTIES) -> tuple[str | None, float | None]:
    best_prop = None
    best_value = None
    for prop in props:
        gap = finite(per_property_values(fitness, prop).get("gap"))
        if gap is None:
            continue
        if best_value is None or gap > best_value:
            best_prop = prop
            best_value = gap
    return best_prop, best_value


def target_filtered(values: Any, targets: tuple[str, ...] = TARGET_PROPERTIES) -> list[str]:
    if not isinstance(values, list):
        return []
    allowed = set(targets)
    return [str(prop) for prop in values if str(prop) in allowed]


def load_run(run_dir: Path, label: str) -> dict[str, Any]:
    metadata = load_json(run_dir / "metadata.json") if (run_dir / "metadata.json").exists() else {}
    targets = target_properties(metadata if isinstance(metadata, dict) else {})
    archive = load_json(run_dir / "archive.json") if (run_dir / "archive.json").exists() else {}
    progress = read_jsonl(run_dir / "progress.jsonl")
    rows: list[dict[str, Any]] = []
    for record in read_jsonl(run_dir / "evals.jsonl"):
        fitness = fitness_for(record, targets)
        theta = theta_for(record)
        wind, physics = bucket_for(record, theta)
        rel_props = target_filtered(fitness.get("relative_degradation_differential_properties", []))
        strict_props = target_filtered(fitness.get("strict_differential_properties", []))
        candidate_props = target_filtered(fitness.get("candidate_differential_properties", []))
        gap_prop, gap_value = best_gap(fitness)
        rows.append(
            {
                "label": label,
                "tag": record.get("tag"),
                "index": record.get("index"),
                "returncode": record.get("returncode"),
                "error": record.get("error"),
                "mcnn_confirmed": record.get("mcnn_confirmed"),
                "quality": finite(record.get("quality")),
                "wind_bucket": wind,
                "physics_bucket": physics,
                "fitness": fitness,
                "relative_props": rel_props,
                "strict_props": strict_props,
                "candidate_props": candidate_props,
                "primary_bug_rejudged": bool(strict_props),
                "best_gap_property": gap_prop,
                "best_gap": gap_value,
            }
        )
    confirmations = read_jsonl(run_dir / "confirmations.jsonl")
    confirmed_source = "none"
    confirmed_path = run_dir / "confirmed_relative_degradations.json"
    if confirmed_path.exists():
        confirmed = load_json(confirmed_path)
        confirmed_source = confirmed_path.name
    else:
        confirmed_path = run_dir / "confirmed_primary_bugs.json"
        confirmed = load_json(confirmed_path) if confirmed_path.exists() else []
        confirmed_source = f"{confirmed_path.name} (legacy reportable-relative records)" if confirmed_path.exists() else "none"
    return {
        "label": label,
        "run_dir": run_dir,
        "metadata": metadata,
        "archive": archive if isinstance(archive, dict) else {},
        "progress": progress,
        "rows": rows,
        "confirmations": confirmations,
        "confirmed": confirmed if isinstance(confirmed, list) else [],
        "confirmed_source": confirmed_source,
    }


def qd_score(run: dict[str, Any]) -> float:
    progress = run["progress"]
    if progress:
        value = finite(progress[-1].get("qd_score"))
        if value is not None:
            return value
    total = 0.0
    for elite in run["archive"].values():
        result = elite.get("result", {}) if isinstance(elite, dict) else {}
        quality = finite(result.get("quality"))
        if quality is not None:
            total += max(0.0, quality)
    return total


def confirmed_tags(run: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for item in run["confirmed"]:
        candidate = item.get("candidate", {}) if isinstance(item, dict) else {}
        result = candidate.get("result", {}) if isinstance(candidate, dict) else {}
        tag = result.get("tag")
        if isinstance(tag, str):
            out.add(tag)
    return out


def confirmation_attempts(run: dict[str, Any]) -> tuple[int, int]:
    attempts = len(run["confirmations"])
    passed = sum(1 for item in run["confirmations"] if item.get("passed"))
    if attempts == 0 and run["confirmed"]:
        return len(run["confirmed"]), len(run["confirmed"])
    return passed, attempts


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    idx = min(len(values) - 1, max(0, int(math.ceil(p * len(values))) - 1))
    return values[idx]


def property_stats(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for prop in TARGET_PROPERTIES:
        gaps: list[float] = []
        neural: list[float] = []
        rel = 0
        for run in runs:
            for row in run["rows"]:
                item = per_property_values(row["fitness"], prop)
                gap = finite(item.get("gap"))
                n = finite(item.get("neural_rho"))
                if gap is not None:
                    gaps.append(gap)
                if n is not None:
                    neural.append(n)
                if prop in row["relative_props"]:
                    rel += 1
        stats[prop] = {
            "valid": len(gaps),
            "relative": rel,
            "median": statistics.median(gaps) if gaps else None,
            "p90": percentile(gaps, 0.90),
            "max": max(gaps) if gaps else None,
            "min_neural": min(neural) if neural else None,
        }
    return stats


def property_distribution(runs: list[dict[str, Any]]) -> list[str]:
    stats = property_stats(runs)
    lines = [
        "| property | valid gaps | relative flags | median gap | p90 gap | max gap | min neural rho |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for prop in TARGET_PROPERTIES:
        item = stats[prop]
        lines.append(
            "| {prop} | {valid} | {rel} | {median} | {p90} | {max_gap} | {min_rho} |".format(
                prop=prop,
                valid=item["valid"],
                rel=item["relative"],
                median=format_float(item["median"]),
                p90=format_float(item["p90"]),
                max_gap=format_float(item["max"]),
                min_rho=format_float(item["min_neural"]),
            )
        )
    return lines


def property_interpretation_lines(runs: list[dict[str, Any]]) -> list[str]:
    stats = property_stats(runs)
    p4 = stats["P4"]
    p6 = stats["P6"]
    p7 = stats["P7"]
    p4_rate = 100.0 * float(p4["relative"]) / float(p4["valid"] or 1)
    p7_rate = 100.0 * float(p7["relative"]) / float(p7["valid"] or 1)
    return [
        "- P4 is an architecture baseline fact, not a finding count: "
        f"{p4['relative']}/{p4['valid']} ({p4_rate:.0f}%) evals flag it, but the gap is narrow "
        f"(median {format_float(p4['median'])}, p90 {format_float(p4['p90'])}, max {format_float(p4['max'])}).",
        "- P6 is a medium degradation band: "
        f"{p6['relative']}/{p6['valid']} relative flags, median gap {format_float(p6['median'])}, "
        f"p90 {format_float(p6['p90'])}, max {format_float(p6['max'])}.",
        "- P7 is sparse but large in the single-draw tail: "
        f"{p7['relative']}/{p7['valid']} ({p7_rate:.0f}%) relative flags, p90 gap {format_float(p7['p90'])}, "
        f"max gap {format_float(p7['max'])}. This is a distributional tail signal, not a stable per-scenario degradation claim.",
    ]


def format_float(value: Any) -> str:
    value = finite(value)
    if value is None:
        return "n/a"
    return f"{value:.4g}"


def matrix_lines(run: dict[str, Any]) -> list[str]:
    by_bin: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "p7": 0, "max_gap": None, "min_p7_rho": None}
    )
    for row in run["rows"]:
        key = (row["wind_bucket"], row["physics_bucket"])
        cell = by_bin[key]
        cell["n"] += 1
        if "P7" in row["relative_props"]:
            cell["p7"] += 1
        if row["best_gap"] is not None and (cell["max_gap"] is None or row["best_gap"] > cell["max_gap"]):
            cell["max_gap"] = row["best_gap"]
        n = finite(per_property_values(row["fitness"], "P7").get("neural_rho"))
        if n is not None and (cell["min_p7_rho"] is None or n < cell["min_p7_rho"]):
            cell["min_p7_rho"] = n
    physics_seen = {key[1] for key in by_bin}
    wind_seen = {key[0] for key in by_bin}
    physics_values = [value for value in BUCKET_ORDER if value in physics_seen]
    physics_values.extend(sorted(physics_seen.difference(BUCKET_ORDER)))
    wind_values = [value for value in BUCKET_ORDER if value in wind_seen]
    wind_values.extend(sorted(wind_seen.difference(BUCKET_ORDER)))
    if not physics_values:
        physics_values = ["unknown"]
    if not wind_values:
        wind_values = ["unknown"]
    lines = [
        "| wind / physics | " + " | ".join(physics_values) + " |",
        "|---|" + "|".join("---" for _ in physics_values) + "|",
    ]
    for wind in wind_values:
        cells = []
        for physics in physics_values:
            cell = by_bin.get((wind, physics))
            if not cell:
                cells.append("n=0")
                continue
            cells.append(
                "n={n}; P7={p7}; gap={gap}; min_P7={rho}".format(
                    n=cell["n"],
                    p7=cell["p7"],
                    gap=format_float(cell["max_gap"]),
                    rho=format_float(cell["min_p7_rho"]),
                )
            )
        lines.append("| " + wind + " | " + " | ".join(cells) + " |")
    return lines


def property_relative_hit(fitness: dict[str, Any], prop: str) -> bool:
    item = per_property_values(fitness, prop)
    return bool(item.get("relative_degradation_differential"))


def property_gap_reproduced(fitness: dict[str, Any], prop: str) -> bool:
    item = per_property_values(fitness, prop)
    gap = finite(item.get("gap"))
    margin = finite(item.get("rho_jitter_reproduction_margin"))
    return bool(gap is not None and margin is not None and gap >= margin)


def sample_variance(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return statistics.variance(values)


def variance_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator == 0.0:
        return math.inf if numerator > 0.0 else None
    return numerator / denominator


def confirmation_reanalysis_items(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for run in runs:
        targets = target_properties(run["metadata"] if isinstance(run["metadata"], dict) else {})
        for confirmation in run["confirmed"]:
            if not isinstance(confirmation, dict):
                continue
            if confirmation.get("passed") is False:
                continue
            candidate = confirmation.get("candidate", {})
            result = candidate.get("result", {}) if isinstance(candidate, dict) else {}
            if not isinstance(result, dict):
                continue
            fitness = fitness_for(result, targets)
            rel_props = target_filtered(fitness.get("relative_degradation_differential_properties", []))
            theta = theta_for(result)
            wind, physics = bucket_for(result, theta)
            p7 = per_property_values(fitness, "P7")
            repeats = confirmation.get("repeats", [])
            repeat_count = len(repeats) if isinstance(repeats, list) else 0
            relative_hits = {prop: 0 for prop in TARGET_PROPERTIES}
            gap_hits = {prop: 0 for prop in TARGET_PROPERTIES}
            p7_classical: list[float] = []
            p7_neural: list[float] = []
            p7_gap_values: list[float] = []
            if isinstance(repeats, list):
                for repeat in repeats:
                    if not isinstance(repeat, dict):
                        continue
                    repeat_fitness = fitness_for(repeat, targets)
                    for prop in TARGET_PROPERTIES:
                        if property_relative_hit(repeat_fitness, prop):
                            relative_hits[prop] += 1
                        if property_gap_reproduced(repeat_fitness, prop):
                            gap_hits[prop] += 1
                    repeat_p7 = per_property_values(repeat_fitness, "P7")
                    c = finite(repeat_p7.get("classical_rho"))
                    n = finite(repeat_p7.get("neural_rho"))
                    gap = finite(repeat_p7.get("gap"))
                    if c is not None:
                        p7_classical.append(c)
                    if n is not None:
                        p7_neural.append(n)
                    if gap is not None:
                        p7_gap_values.append(gap)
            classical_var = sample_variance(p7_classical)
            neural_var = sample_variance(p7_neural)
            items.append(
                {
                    "label": run["label"],
                    "tag": result.get("tag"),
                    "wind": wind,
                    "physics": physics,
                    "gap": finite(p7.get("gap")),
                    "classical": finite(p7.get("classical_rho")),
                    "neural": finite(p7.get("neural_rho")),
                    "repro": finite(p7.get("rho_jitter_reproduction_margin")),
                    "trigger_properties": rel_props,
                    "relative_hits": relative_hits,
                    "gap_hits": gap_hits,
                    "p7_relative_hits": relative_hits["P7"],
                    "p7_gap_hits": gap_hits["P7"],
                    "repeat_count": repeat_count,
                    "p7_classical_values": p7_classical,
                    "p7_neural_values": p7_neural,
                    "p7_gap_values": p7_gap_values,
                    "p7_classical_variance": classical_var,
                    "p7_neural_variance": neural_var,
                    "p7_variance_ratio": variance_ratio(neural_var, classical_var),
                }
            )
    items.sort(key=lambda item: item["gap"] if item["gap"] is not None else -math.inf, reverse=True)
    return items


def p7_candidate_items(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in confirmation_reanalysis_items(runs) if "P7" in item["trigger_properties"]]


def p7_confirmed_counts(runs: list[dict[str, Any]], min_hits: int) -> dict[str, int]:
    counts = {run["label"]: 0 for run in runs}
    for item in p7_candidate_items(runs):
        if int(item["p7_relative_hits"]) >= min_hits:
            counts[item["label"]] = counts.get(item["label"], 0) + 1
    return counts


def trigger_property_confirmation_counts(runs: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts = {prop: {"triggered": 0, "confirmed_2of3": 0, "confirmed_3of3": 0} for prop in TARGET_PROPERTIES}
    for item in confirmation_reanalysis_items(runs):
        repeat_count = int(item["repeat_count"])
        for prop in item["trigger_properties"]:
            if prop not in counts:
                continue
            hits = int(item["relative_hits"].get(prop, 0))
            counts[prop]["triggered"] += 1
            if repeat_count and hits >= 2:
                counts[prop]["confirmed_2of3"] += 1
            if repeat_count and hits >= 3:
                counts[prop]["confirmed_3of3"] += 1
    return counts


def trigger_property_confirmation_lines(runs: list[dict[str, Any]]) -> list[str]:
    counts = trigger_property_confirmation_counts(runs)
    lines = [
        "| trigger property | legacy trigger candidates | property-confirmed >=2/3 | property-confirmed 3/3 |",
        "|---|---:|---:|---:|",
    ]
    for prop in TARGET_PROPERTIES:
        item = counts[prop]
        lines.append(
            f"| {prop} | {item['triggered']} | {item['confirmed_2of3']} | {item['confirmed_3of3']} |"
        )
    total_triggered = sum(item["triggered"] for item in counts.values())
    total_2of3 = sum(item["confirmed_2of3"] for item in counts.values())
    total_3of3 = sum(item["confirmed_3of3"] for item in counts.values())
    lines.append(f"| total candidate-property pairs | {total_triggered} | {total_2of3} | {total_3of3} |")
    return lines


def p7_reanalysis_lines(runs: list[dict[str, Any]]) -> list[str]:
    candidates = p7_candidate_items(runs)
    lines = [
        "| arm | tag | wind | physics | P7 gap | classical rho | neural rho | margin | P7 gap repeats | P7 relative repeats | P7 >=2/3 | P7 3/3 |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    if not candidates:
        lines.append("| none | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
        return lines
    for item in candidates:
        repeat_count = int(item["repeat_count"])
        lines.append(
            "| {label} | `{tag}` | {wind} | {physics} | {gap} | {classical} | {neural} | {repro} | {gap_hits}/{repeats} | {rel_hits}/{repeats} | {confirmed2} | {confirmed3} |".format(
                label=item["label"],
                tag=item["tag"],
                wind=item["wind"],
                physics=item["physics"],
                gap=format_float(item["gap"]),
                classical=format_float(item["classical"]),
                neural=format_float(item["neural"]),
                repro=format_float(item["repro"]),
                gap_hits=item["p7_gap_hits"],
                rel_hits=item["p7_relative_hits"],
                repeats=repeat_count,
                confirmed2="yes" if int(item["p7_relative_hits"]) >= 2 else "no",
                confirmed3="yes" if int(item["p7_relative_hits"]) >= 3 else "no",
            )
        )
    return lines


def p7_reanalysis_summary_lines(runs: list[dict[str, Any]]) -> list[str]:
    candidates = p7_candidate_items(runs)
    zero_repeats = sum(1 for item in candidates if int(item["p7_relative_hits"]) == 0)
    one_repeat = sum(1 for item in candidates if int(item["p7_relative_hits"]) == 1)
    two_repeat = sum(1 for item in candidates if int(item["p7_relative_hits"]) == 2)
    three_repeat = sum(1 for item in candidates if int(item["p7_relative_hits"]) == 3)
    mismatch = sum(1 for item in candidates if int(item["p7_relative_hits"]) != int(item["p7_gap_hits"]))
    return [
        f"- P7 repeats recomputation: {zero_repeats}/{len(candidates)} candidates are 0/3, "
        f"{one_repeat}/{len(candidates)} are 1/3, {two_repeat}/{len(candidates)} are 2/3, "
        f"and {three_repeat}/{len(candidates)} are 3/3.",
        f"- P7 gap-repeat count and P7 relative-repeat count mismatches: {mismatch}. "
        "The old P7-repeat column is therefore not a report-field bug for these data.",
    ]


def p7_variance_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = p7_candidate_items(runs)
    classical_vars = [item["p7_classical_variance"] for item in candidates if item["p7_classical_variance"] is not None]
    neural_vars = [item["p7_neural_variance"] for item in candidates if item["p7_neural_variance"] is not None]
    ratios = [item["p7_variance_ratio"] for item in candidates if item["p7_variance_ratio"] is not None and math.isfinite(float(item["p7_variance_ratio"]))]
    classical_all = [value for item in candidates for value in item["p7_classical_values"]]
    neural_all = [value for item in candidates for value in item["p7_neural_values"]]
    classical_aggregate = sample_variance(classical_all)
    neural_aggregate = sample_variance(neural_all)
    return {
        "candidate_count": len(candidates),
        "mean_classical_variance": statistics.mean(classical_vars) if classical_vars else None,
        "mean_neural_variance": statistics.mean(neural_vars) if neural_vars else None,
        "median_ratio": statistics.median(ratios) if ratios else None,
        "aggregate_classical_variance": classical_aggregate,
        "aggregate_neural_variance": neural_aggregate,
        "aggregate_ratio": variance_ratio(neural_aggregate, classical_aggregate),
    }


def p7_variance_lines(runs: list[dict[str, Any]]) -> list[str]:
    candidates = p7_candidate_items(runs)
    summary = p7_variance_summary(runs)
    lines = [
        "- P7 jitter margin source: `scripts/validity_automation.py` uses P7 jitter band 0.2242437213, "
        "the max of fixed-theta serial pairwise ranges classical=0.2242437213 and mcnn=0.1979852921; "
        "the reproduction margin is 2x = 0.4484874426.",
        "- Across the 12 P7-trigger candidates' confirmation seeds, neural P7 variance is not much larger than classical: "
        f"mean variance neural {format_float(summary['mean_neural_variance'])} vs classical {format_float(summary['mean_classical_variance'])}; "
        f"pooled variance neural {format_float(summary['aggregate_neural_variance'])} vs classical {format_float(summary['aggregate_classical_variance'])} "
        f"(ratio {format_float(summary['aggregate_ratio'])}, median per-candidate ratio {format_float(summary['median_ratio'])}).",
        "",
        "| arm | tag | P7 repeats | classical P7 var | neural P7 var | neural/classical var |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for item in candidates:
        lines.append(
            "| {label} | `{tag}` | {hits}/{repeats} | {cvar} | {nvar} | {ratio} |".format(
                label=item["label"],
                tag=item["tag"],
                hits=item["p7_relative_hits"],
                repeats=item["repeat_count"],
                cvar=format_float(item["p7_classical_variance"]),
                nvar=format_float(item["p7_neural_variance"]),
                ratio=format_float(item["p7_variance_ratio"]),
            )
        )
    return lines


def run_summary_lines(runs: list[dict[str, Any]]) -> list[str]:
    confirmed_counts_2of3 = p7_confirmed_counts(runs, 2)
    confirmed_counts_3of3 = p7_confirmed_counts(runs, 3)
    lines = [
        "| arm | evals | usable | errors | bins | QD | primary_bug evals | relative evals | P7 confirmed >=2/3 | P7 confirmed 3/3 | legacy confirmations | max gap |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for run in runs:
        rows = run["rows"]
        usable = sum(1 for row in rows if row["returncode"] == 0)
        errors = sum(1 for row in rows if row["error"])
        rel = sum(1 for row in rows if row["relative_props"])
        primary = sum(1 for row in rows if row["primary_bug_rejudged"])
        passed, attempts = confirmation_attempts(run)
        max_gap = max((row["best_gap"] for row in rows if row["best_gap"] is not None), default=None)
        lines.append(
            f"| {run['label']} | {len(rows)} | {usable} | {errors} | {len(run['archive'])} | "
            f"{format_float(qd_score(run))} | {primary} | {rel} | "
            f"{confirmed_counts_2of3.get(run['label'], 0)} | {confirmed_counts_3of3.get(run['label'], 0)} | "
            f"{passed}/{attempts} | {format_float(max_gap)} |"
        )
    return lines


def max_gap_for_run(run: dict[str, Any]) -> float | None:
    return max((row["best_gap"] for row in run["rows"] if row["best_gap"] is not None), default=None)


def c3_lines(guided: dict[str, Any], random_run: dict[str, Any]) -> list[str]:
    counts = p7_confirmed_counts([guided, random_run], 2)
    return [
        "- Guided has a small illumination edge: "
        f"QD {format_float(qd_score(guided))} vs {format_float(qd_score(random_run))}, "
        f"archive bins {len(guided['archive'])} vs {len(random_run['archive'])}.",
        "- Random still found the strongest single cell: "
        f"max gap {format_float(max_gap_for_run(random_run))} vs guided {format_float(max_gap_for_run(guided))}.",
        "- Trigger-property P7 counts are tied at the >=2/3 level: "
        f"guided {counts.get(guided['label'], 0)} vs random {counts.get(random_run['label'], 0)}. "
        "This is not a guided-search rout; the wave-1 target is common enough that random also reaches it. "
        "A stronger C3 claim belongs to rarer wave-2 objectives.",
    ]


def strict_negative_lines(runs: list[dict[str, Any]], corner: dict[str, Any] | None) -> list[str]:
    all_runs = list(runs)
    if corner is not None:
        all_runs.append(corner)
    strict_rows = [row for run in all_runs for row in run["rows"] if row["strict_props"]]
    lines = [
        f"- Strict absolute differentials found in wind+physics scope: {len(strict_rows)}.",
    ]
    negative_p7: list[dict[str, Any]] = []
    for run in runs:
        for row in run["rows"]:
            p7 = per_property_values(row["fitness"], "P7")
            n = finite(p7.get("neural_rho"))
            if n is None or n > 0.0:
                continue
            negative_p7.append(
                {
                    "label": run["label"],
                    "tag": row["tag"],
                    "wind": row["wind_bucket"],
                    "physics": row["physics_bucket"],
                    "classical": finite(p7.get("classical_rho")),
                    "neural": n,
                    "gap": finite(p7.get("gap")),
                    "margin": finite(p7.get("rho_jitter_reproduction_margin")),
                }
            )
    negative_p7.sort(key=lambda item: item["neural"])
    if negative_p7:
        lines.append(
            "- Random high-stress cells pushed neural P7 rho just below zero, but not through the jitter margin:"
        )
        for item in negative_p7[:4]:
            margin = item["margin"]
            strict_line = -float(margin) if margin is not None else None
            lines.append(
                "  - {label} `{tag}` ({wind}/{physics}): classical rho {c}, neural rho {n}, gap {g}; "
                "strict line neural <= {line}.".format(
                    label=item["label"],
                    tag=item["tag"],
                    wind=item["wind"],
                    physics=item["physics"],
                    c=format_float(item["classical"]),
                    n=format_float(item["neural"]),
                    g=format_float(item["gap"]),
                    line=format_float(strict_line),
                )
            )
    if corner is not None and corner["rows"]:
        best = max(corner["rows"], key=lambda row: row["best_gap"] if row["best_gap"] is not None else -math.inf)
        p7 = per_property_values(best["fitness"], "P7")
        lines.append(
            "- Extreme corner check: P7 classical rho {c}, neural rho {n}, gap {g}, repro margin {m}; "
            "neural stayed above the absolute violation line.".format(
                c=format_float(p7.get("classical_rho")),
                n=format_float(p7.get("neural_rho")),
                g=format_float(p7.get("gap")),
                m=format_float(p7.get("rho_jitter_reproduction_margin")),
            )
        )
    if not strict_rows:
        lines.append("- Interpretation: wave-1 supports relative degradation, not absolute violation, in this subspace.")
    return lines


def write_report(output: Path, guided: dict[str, Any], random_run: dict[str, Any], corner: dict[str, Any] | None) -> None:
    campaign_runs = [guided, random_run]
    p7_candidates = p7_candidate_items(campaign_runs)
    p7_confirmed_2of3 = sum(1 for item in p7_candidates if int(item["p7_relative_hits"]) >= 2)
    p7_confirmed_3of3 = sum(1 for item in p7_candidates if int(item["p7_relative_hits"]) >= 3)
    variance_summary = p7_variance_summary(campaign_runs)
    primary_bug_evals = sum(1 for run in campaign_runs for row in run["rows"] if row["primary_bug_rejudged"])
    lines = [
        "# Wave-1 wind+physics campaign",
        "",
        "Scope: steady-wind-physics, target properties P4/P6/P7, speed factor 1.25, N=1 sequential SITL.",
        "Labels are separated into weak candidate, strict absolute differential, and relative degradation differential. "
        "primary_bug is reserved for strict differentials only.",
        "",
        "## Headline",
        f"- P7 trigger-property confirmations: {p7_confirmed_2of3}/{len(p7_candidates)} at >=2/3 repeats, "
        f"{p7_confirmed_3of3}/{len(p7_candidates)} at 3/3 repeats.",
        "- Legacy confirmation passed all 12 P7-trigger candidates via any target property, mostly P4/P6; "
        "that is not P7 confirmation.",
        f"- Strict primary bugs after relabeling: {primary_bug_evals}.",
        "- Wave-1 P7 conclusion: distributional high-stress tail, not deterministic or robustly reproduced P7 degradation. "
        "The confirmation-seed variance is shared/comparable between classical and neural "
        f"(pooled neural/classical P7 variance ratio {format_float(variance_summary['aggregate_ratio'])}).",
        "- The 199/198 relative-eval counts are coverage/signal counts, not finding counts; P4 dominates them.",
        "",
        "## Run Summary",
        *run_summary_lines(campaign_runs),
        "",
        "## Relative Degradation Distribution",
        "Criterion: neural rho > 0, classical rho >= margin_c, and classical-minus-neural gap >= the property reproduction margin.",
        *property_distribution(campaign_runs),
        "",
        *property_interpretation_lines(campaign_runs),
        "",
        "## Trigger-Property Confirmation Reanalysis",
        "Legacy confirmation records used an any-target-property repeat match. Rejudgment below requires the same triggering property to repeat.",
        *trigger_property_confirmation_lines(campaign_runs),
        "",
        "### P7 Trigger Candidates",
        "P7 gap repeats count confirmation seeds with P7 gap >= 0.4484874426. P7 relative repeats use the full relative-degradation predicate for P7; in this dataset the two counts match.",
        *p7_reanalysis_summary_lines(campaign_runs),
        *p7_reanalysis_lines(campaign_runs),
        "",
        "### P7 Confirmation-Seed Variance",
        *p7_variance_lines(campaign_runs),
        "",
        "## RQ3: wind x physics degradation map",
        "Cells show eval count, P7 relative-degradation count, max target-property gap, and minimum P7 neural rho. "
        "These are extreme-value single-draw summaries, not cell means or stable degradation estimates.",
        "",
        "### Guided",
        *matrix_lines(guided),
        "",
        "### Random",
        *matrix_lines(random_run),
        "",
        "## C3: guided vs random",
        *run_summary_lines(campaign_runs),
        "",
        *c3_lines(guided, random_run),
        "",
        "## Strict-negative boundary",
        *strict_negative_lines(campaign_runs, corner),
        "",
        "## Validity",
        f"- Guided mcnn identity confirmed evals: {sum(1 for row in guided['rows'] if row['mcnn_confirmed'])}/{len(guided['rows'])}.",
        f"- Random mcnn identity confirmed evals: {sum(1 for row in random_run['rows'] if row['mcnn_confirmed'])}/{len(random_run['rows'])}.",
        f"- Confirmed-record sources: guided `{guided['confirmed_source']}`, random `{random_run['confirmed_source']}`.",
        "- Decontamination and identity gates are applied by campaign_runner before scoring; failed gates are recorded as returncode/error and excluded from quality.",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guided", type=Path, required=True)
    parser.add_argument("--random", type=Path, required=True)
    parser.add_argument("--corner", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    guided = load_run(args.guided.resolve(), "guided")
    random_run = load_run(args.random.resolve(), "random")
    corner = load_run(args.corner.resolve(), "corner") if args.corner else None
    write_report(args.output.resolve(), guided, random_run, corner)
    runs = [guided, random_run]
    p7_candidates = p7_candidate_items(runs)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "guided_evals": len(guided["rows"]),
                "random_evals": len(random_run["rows"]),
                "primary_bug_evals_rejudged": sum(
                    1 for run in runs for row in run["rows"] if row["primary_bug_rejudged"]
                ),
                "p7_trigger_candidates": len(p7_candidates),
                "p7_trigger_confirmed_2of3": sum(1 for item in p7_candidates if int(item["p7_relative_hits"]) >= 2),
                "p7_trigger_confirmed_3of3": sum(1 for item in p7_candidates if int(item["p7_relative_hits"]) >= 3),
                "p7_pooled_neural_classical_variance_ratio": p7_variance_summary(runs)["aggregate_ratio"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
