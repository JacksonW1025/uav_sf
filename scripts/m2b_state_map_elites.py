#!/usr/bin/env python3
"""M2b-1 MAP-Elites over adversarial shared-state pollution channels."""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import m2b_state_profiles as profiles


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIRM_SEEDS = [20260801, 20260802, 20260803]
CONFIRM_SAFETY_CONFIG = REPO_ROOT / "config/m2b_safety_envelope_1x_high_twr.json"
CHANNELS = ["velocity", "angular_velocity", "attitude"]
PROFILES = {
    "velocity": ["delay", "bias", "noise"],
    "angular_velocity": ["delay", "bias", "noise"],
    "attitude": ["delay", "bias", "noise"],
}


@dataclass
class Genome:
    channel: str
    profile: str
    magnitude: float
    delay_ms: int
    axis: str
    twr: float
    sine_axis: str
    sine_amplitude_m: float
    sine_frequency_hz: float
    secondary_channel: str
    secondary_profile: str
    secondary_magnitude: float
    secondary_delay_ms: int

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def profile_values(channel: str, profile: str, axis: str, magnitude: float) -> tuple[float, float, float]:
    if profile == "delay":
        return (0.0, 0.0, 0.0)
    idx = {"x": 0, "y": 1, "z": 2, "roll": 0, "pitch": 1, "yaw": 2}.get(axis, 0)
    values = [0.0, 0.0, 0.0]
    values[idx] = float(magnitude)
    return tuple(values)  # type: ignore[return-value]


def random_genome(rng: random.Random) -> Genome:
    channel = rng.choices(CHANNELS, weights=[0.48, 0.34, 0.18], k=1)[0]
    profile = rng.choice(PROFILES[channel])
    axis_choices = ["x", "y", "z"] if channel != "attitude" else ["roll", "pitch", "yaw"]
    if channel == "velocity" and profile == "delay":
        magnitude = 0.0
        delay_ms = rng.randint(10, 60)
    elif channel == "velocity":
        magnitude = rng.uniform(0.04, 0.35)
        delay_ms = 0
    elif channel == "angular_velocity" and profile == "delay":
        magnitude = 0.0
        delay_ms = rng.randint(10, 80)
    elif channel == "angular_velocity":
        magnitude = math.radians(rng.uniform(1.0, 10.0))
        delay_ms = 0
    elif profile == "delay":
        magnitude = 0.0
        delay_ms = rng.randint(10, 80)
    else:
        magnitude = math.radians(rng.uniform(0.5, 8.0))
        delay_ms = 0
    secondary_channel = "none"
    secondary_profile = "off"
    secondary_magnitude = 0.0
    secondary_delay_ms = 0
    if rng.random() < 0.35:
        choices = [item for item in CHANNELS if item != channel]
        secondary_channel = rng.choice(choices)
        secondary_profile = rng.choice(PROFILES[secondary_channel])
        if secondary_profile == "delay":
            secondary_delay_ms = rng.randint(10, 50)
        elif secondary_channel == "velocity":
            secondary_magnitude = rng.uniform(0.03, 0.22)
        elif secondary_channel == "angular_velocity":
            secondary_magnitude = math.radians(rng.uniform(1.0, 6.0))
        else:
            secondary_magnitude = math.radians(rng.uniform(0.5, 5.0))
    return normalize_genome(
        Genome(
            channel=channel,
            profile=profile,
            magnitude=magnitude,
            delay_ms=delay_ms,
            axis=rng.choice(axis_choices),
            twr=rng.uniform(1.8, 2.5),
            sine_axis=rng.choice(["x", "y", "z"]),
            sine_amplitude_m=rng.uniform(0.12, 0.35),
            sine_frequency_hz=rng.uniform(1.0, 5.5),
            secondary_channel=secondary_channel,
            secondary_profile=secondary_profile,
            secondary_magnitude=secondary_magnitude,
            secondary_delay_ms=secondary_delay_ms,
        )
    )


def normalize_genome(genome: Genome) -> Genome:
    genome.twr = clamp(float(genome.twr), 1.743, 2.6)
    genome.sine_amplitude_m = clamp(float(genome.sine_amplitude_m), 0.05, 0.45)
    genome.sine_frequency_hz = clamp(float(genome.sine_frequency_hz), 0.5, 6.0)
    genome.delay_ms = int(clamp(int(genome.delay_ms), 0, 120))
    genome.secondary_delay_ms = int(clamp(int(genome.secondary_delay_ms), 0, 120))
    if genome.channel == "velocity":
        genome.magnitude = clamp(float(genome.magnitude), 0.0, 0.5)
    elif genome.channel == "angular_velocity":
        genome.magnitude = clamp(float(genome.magnitude), 0.0, math.radians(15.0))
    else:
        genome.magnitude = clamp(float(genome.magnitude), 0.0, math.radians(12.0))
    if genome.secondary_channel == "velocity":
        genome.secondary_magnitude = clamp(float(genome.secondary_magnitude), 0.0, 0.35)
    elif genome.secondary_channel == "angular_velocity":
        genome.secondary_magnitude = clamp(float(genome.secondary_magnitude), 0.0, math.radians(10.0))
    elif genome.secondary_channel == "attitude":
        genome.secondary_magnitude = clamp(float(genome.secondary_magnitude), 0.0, math.radians(8.0))
    else:
        genome.secondary_channel = "none"
        genome.secondary_profile = "off"
        genome.secondary_magnitude = 0.0
        genome.secondary_delay_ms = 0
    return genome


def mutate(parent: Genome, rng: random.Random) -> Genome:
    g = Genome(**parent.as_dict())
    if rng.random() < 0.18:
        g.channel = rng.choices(CHANNELS, weights=[0.48, 0.34, 0.18], k=1)[0]
        g.profile = rng.choice(PROFILES[g.channel])
    if rng.random() < 0.25:
        g.profile = rng.choice(PROFILES[g.channel])
    if rng.random() < 0.50:
        g.magnitude += rng.gauss(0.0, 0.05 if g.channel == "velocity" else math.radians(1.5))
    if rng.random() < 0.50:
        g.delay_ms += int(round(rng.gauss(0.0, 10.0)))
    if rng.random() < 0.30:
        g.twr += rng.gauss(0.0, 0.12)
    if rng.random() < 0.35:
        g.sine_amplitude_m += rng.gauss(0.0, 0.04)
    if rng.random() < 0.35:
        g.sine_frequency_hz += rng.gauss(0.0, 0.5)
    if rng.random() < 0.20:
        g.sine_axis = rng.choice(["x", "y", "z"])
    if rng.random() < 0.15:
        axes = ["x", "y", "z"] if g.channel != "attitude" else ["roll", "pitch", "yaw"]
        g.axis = rng.choice(axes)
    if rng.random() < 0.12:
        if g.secondary_channel == "none":
            g.secondary_channel = rng.choice([item for item in CHANNELS if item != g.channel])
            g.secondary_profile = rng.choice(PROFILES[g.secondary_channel])
        else:
            g.secondary_channel = "none"
            g.secondary_profile = "off"
            g.secondary_magnitude = 0.0
            g.secondary_delay_ms = 0
    return normalize_genome(g)


def severity(genome: Genome) -> float:
    if genome.profile == "delay":
        base = genome.delay_ms / 80.0
    elif genome.channel == "velocity":
        base = genome.magnitude / 0.5
    elif genome.channel == "angular_velocity":
        base = genome.magnitude / math.radians(15.0)
    else:
        base = genome.magnitude / math.radians(12.0)
    conj = 0.25 if genome.secondary_channel != "none" else 0.0
    return clamp(max(base, (genome.twr - 1.743) / 0.85) + conj, 0.0, 1.5)


def feature_bin(genome: Genome) -> tuple[str, float]:
    sev = severity(genome)
    bucket = "low" if sev < 0.35 else "mid" if sev < 0.75 else "high"
    conj = "+conj" if genome.secondary_channel != "none" else ""
    return f"{genome.channel}:{genome.profile}{conj}:{bucket}", sev


def apply_channel_params(theta: dict[str, Any], genome: Genome, *, secondary: bool = False) -> None:
    if secondary:
        if genome.secondary_channel == "none":
            return
        channel = genome.secondary_channel
        profile = genome.secondary_profile
        magnitude = genome.secondary_magnitude
        delay_ms = genome.secondary_delay_ms
        axis = "x" if channel != "attitude" else "roll"
    else:
        channel = genome.channel
        profile = genome.profile
        magnitude = genome.magnitude
        delay_ms = genome.delay_ms
        axis = genome.axis
    prefix = profiles.CHANNEL_PREFIX[channel]
    values = profile_values(channel, profile, axis, magnitude)
    suffixes = ("X", "Y", "Z") if prefix != "A" else ("R", "P", "Y")
    for target in [theta["boot_px4_params"], theta["px4_params"]]:
        target["M2B_EN"] = 1
        target[f"M2B_{prefix}_PROF"] = profiles.PROFILE_IDS[profile]
        target[f"M2B_{prefix}_DLY"] = int(delay_ms)
        for suffix, value in zip(suffixes, values):
            target[f"M2B_{prefix}_{suffix}"] = round(float(value), 8)


def theta_from_genome(genome: Genome, tag: str, seed: int) -> dict[str, Any]:
    values = profile_values(genome.channel, genome.profile, genome.axis, genome.magnitude)
    theta = profiles.base_state_theta(
        tag=tag,
        seed=seed,
        channel=genome.channel,
        profile=genome.profile,
        delay_ms=genome.delay_ms,
        values=values,
        twr=genome.twr,
        sine_axis=genome.sine_axis,
        sine_amplitude_m=genome.sine_amplitude_m,
        sine_frequency_hz=genome.sine_frequency_hz,
    )
    apply_channel_params(theta, genome, secondary=True)
    bin_name, sev = feature_bin(genome)
    theta["m2b_1"].update(
        {
            "generator": "scripts/m2b_state_map_elites.py",
            "genome": genome.as_dict(),
            "feature_bin": bin_name,
            "feature_severity": sev,
            "secondary_channel": genome.secondary_channel,
            "secondary_profile": genome.secondary_profile,
        }
    )
    if genome.secondary_channel != "none":
        theta["sensor_perturbations"].append(
            {
                "type": "adversarial_shared_state_shim_secondary",
                "simulator": "sih",
                "shared_quantity": genome.secondary_channel,
                "profile": genome.secondary_profile,
                "delay_ms": genome.secondary_delay_ms,
                "values": list(profile_values(genome.secondary_channel, genome.secondary_profile, "x", genome.secondary_magnitude)),
            }
        )
    return theta


def select_parent(archive: dict[str, dict[str, Any]], rng: random.Random) -> Genome | None:
    if not archive:
        return None
    elites = sorted(archive.values(), key=lambda item: float(item["result"].get("quality") or 0.0), reverse=True)
    return Genome(**rng.choice(elites[: min(10, len(elites))])["genome"])


def search(args: argparse.Namespace) -> tuple[Path, list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rng = random.Random(args.seed)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("m2b_state_map_%Y%m%dT%H%M%SZ")
    run_dir = (REPO_ROOT / "docs" / run_id).resolve()
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    run_dir.mkdir(parents=True, exist_ok=True)
    profiles.write_json(
        run_dir / "metadata.json",
        {
            "run_id": run_id,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "seed": args.seed,
            "budget": args.budget,
            "sim_speed_factor": args.sim_speed_factor,
            "confirm_sim_speed_factor": 1.0,
            "scope_note": "M2b-1 MAP-Elites over shared state shim profiles; not M2b-2 and not M3.",
            "bins": "state channel x profile x severity, with optional secondary channel conjunction",
            "shim_patch": "patches/px4/m2b_state_shim.patch",
            "px4_commit": "3042f906abaab7ab59ae838ad5a530a9ef3df9a6",
        },
    )
    archive: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    deadline = time.monotonic() + args.max_wall_clock_s if args.max_wall_clock_s else None
    for index in range(args.budget):
        if deadline is not None and time.monotonic() >= deadline:
            break
        parent = select_parent(archive, rng)
        genome = random_genome(rng) if parent is None or index < args.bootstrap else mutate(parent, rng)
        tag = f"{run_id}_e{index:04d}"
        theta = theta_from_genome(genome, tag, args.seed + index)
        theta_path = theta_dir / f"{tag}.json"
        docs_dir = evals_dir / tag
        record = profiles.evaluate_theta_record(
            theta,
            theta_path,
            docs_dir,
            index,
            run_timeout=args.run_timeout,
            eval_timeout=args.eval_timeout,
            sim_speed_factor=args.sim_speed_factor,
        )
        bin_name, sev = feature_bin(genome)
        record["feature_bin"] = bin_name
        record["severity"] = sev
        record["genome"] = genome.as_dict()
        records.append(record)
        profiles.append_jsonl(run_dir / "evals.jsonl", record)
        if record.get("classical_usable") and record.get("fair_shared_state_shim_pollution"):
            if bin_name not in archive or float(record.get("quality") or 0.0) > float(archive[bin_name]["result"].get("quality") or 0.0):
                archive[bin_name] = {
                    "genome": genome.as_dict(),
                    "theta_path": str(theta_path),
                    "compare_path": record.get("compare_path"),
                    "result": record,
                }
                profiles.write_json(run_dir / "archive.json", archive)
        if record.get("primary_bug") and record.get("fair_shared_state_shim_pollution"):
            candidate = {"genome": genome.as_dict(), "theta_path": str(theta_path), "compare_path": record.get("compare_path"), "result": record}
            candidates.append(candidate)
            profiles.write_json(run_dir / "primary_candidates.json", candidates)
        print(
            json.dumps(
                {
                    "eval": index,
                    "tag": tag,
                    "bin": bin_name,
                    "quality": record.get("quality"),
                    "quadrant": record.get("quadrant"),
                    "primary_bug": record.get("primary_bug"),
                    "fair_state": record.get("fair_shared_state_shim_pollution"),
                    "error": record.get("error"),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    profiles.write_json(run_dir / "results.json", records)
    profiles.write_json(run_dir / "archive.json", archive)
    profiles.write_json(run_dir / "primary_candidates.json", candidates)
    return run_dir, records, candidates, archive


def confirm(run_dir: Path, candidates: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    confirmed: list[dict[str, Any]] = []
    selected = sorted(candidates, key=lambda item: float(item["result"].get("quality") or 0.0), reverse=True)[: args.max_confirm_candidates]
    for cidx, candidate in enumerate(selected):
        theta = profiles.load_json(Path(candidate["theta_path"]))
        repeats: list[dict[str, Any]] = []
        passed = True
        for ridx in range(args.confirm_repeats):
            seed = CONFIRM_SEEDS[ridx % len(CONFIRM_SEEDS)] + cidx * 100
            confirm_theta = json.loads(json.dumps(theta))
            original_tag = str(theta["tag"])
            tag = f"{original_tag}_confirm_s{seed}"
            confirm_theta["tag"] = tag
            confirm_theta["seed"] = seed
            confirm_theta.setdefault("m2b_1", {})["confirmation_of"] = original_tag
            confirm_theta.setdefault("m2b_1", {})["confirmation_seed"] = seed
            theta_path = run_dir / "confirm" / "theta" / f"{tag}.json"
            docs_dir = run_dir / "confirm" / "evals" / tag
            record = profiles.evaluate_theta_record(
                confirm_theta,
                theta_path,
                docs_dir,
                100000 + cidx * 100 + ridx,
                run_timeout=args.run_timeout,
                eval_timeout=args.eval_timeout,
                sim_speed_factor=1.0,
                safety_config=CONFIRM_SAFETY_CONFIG,
            )
            repeats.append(record)
            if not (record.get("primary_bug") and record.get("fair_shared_state_shim_pollution")):
                passed = False
        item = {"candidate": candidate, "passed": passed, "repeats": repeats}
        profiles.append_jsonl(run_dir / "confirmations.jsonl", item)
        if passed:
            confirmed.append(item)
            primary_dir = REPO_ROOT / "config" / "m2_primary_bugs"
            primary_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate["theta_path"], primary_dir / Path(candidate["theta_path"]).name)
        profiles.write_json(run_dir / "confirmed_primary_bugs.json", confirmed)
    profiles.write_json(run_dir / "confirmed_primary_bugs.json", confirmed)
    return confirmed


def write_summary(run_dir: Path, records: list[dict[str, Any]], candidates: list[dict[str, Any]], archive: dict[str, dict[str, Any]], confirmed: list[dict[str, Any]]) -> None:
    lines = [
        "# M2b-1 State MAP-Elites",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        f"evals: {len(records)}",
        f"fair_state_evals: {sum(1 for r in records if r.get('fair_shared_state_shim_pollution'))}",
        f"classical_usable: {sum(1 for r in records if r.get('classical_usable'))}",
        f"archive_bins: {len(archive)}",
        f"primary_candidates: {len(candidates)}",
        f"confirmed_primary_bugs: {len(confirmed)}",
        "",
        "## best elites",
    ]
    for key, elite in sorted(archive.items(), key=lambda item: float(item[1]["result"].get("quality") or 0.0), reverse=True)[:12]:
        result = elite["result"]
        lines.append(f"- {key}: quality={result.get('quality')} quadrant={result.get('quadrant')} theta=`{Path(elite['theta_path']).relative_to(REPO_ROOT)}`")
    lines.extend(["", "## primary candidates"])
    if not candidates:
        lines.append("- none")
    for candidate in candidates:
        result = candidate["result"]
        lines.append(f"- {result.get('tag')}: quality={result.get('quality')} theta=`{Path(candidate['theta_path']).relative_to(REPO_ROOT)}`")
    lines.extend(["", "## confirmed"])
    if not confirmed:
        lines.append("- none")
    for item in confirmed:
        lines.append(f"- {item['candidate']['result'].get('tag')}: repeats={len(item['repeats'])}")
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--budget", type=int, default=120)
    parser.add_argument("--bootstrap", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20260800)
    parser.add_argument("--sim-speed-factor", type=float, default=4.0)
    parser.add_argument("--run-timeout", type=int, default=180)
    parser.add_argument("--eval-timeout", type=int, default=480)
    parser.add_argument("--max-wall-clock-s", type=float, default=0.0)
    parser.add_argument("--confirm-repeats", type=int, default=3)
    parser.add_argument("--max-confirm-candidates", type=int, default=3)
    parser.add_argument("--no-confirm", action="store_true")
    args = parser.parse_args()
    run_dir, records, candidates, archive = search(args)
    confirmed: list[dict[str, Any]] = []
    if candidates and not args.no_confirm and args.confirm_repeats > 0:
        confirmed = confirm(run_dir, candidates, args)
    write_summary(run_dir, records, candidates, archive, confirmed)
    print(f"M2B_STATE_MAP_DIR={run_dir}")
    print(f"M2B_STATE_MAP_SUMMARY={run_dir / 'summary.md'}")
    print(f"M2B_STATE_CONFIRMED_PRIMARY={len(confirmed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
