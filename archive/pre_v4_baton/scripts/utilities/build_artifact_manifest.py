#!/usr/bin/env python3
"""Build the canonical SHA-256 manifest for tracked and external research artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
from pathlib import Path
import subprocess


SUFFIXES = {
    ".md", ".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml",
    ".ulg", ".log", ".pt", ".pth", ".onnx", ".tar", ".png", ".pdf", ".patch",
}
ROOTS = {"docs", "experiments", "tier05_fork_20260712T090728Z", "runs", "img", "patches", "boards", "config", "data"}


def run(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    ).stdout


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def experiment_id(path: str) -> str:
    value = path.lower()
    if path.startswith("tier05_fork_"): return "HARNESS-BETA-TIER05"
    if "px4_race" in value or "allocation_freshness" in value: return "MECH-ALLOCATION-FRESHNESS"
    if "round5_delivered" in value or "actuator_attribution" in value or "single_writer" in value: return "MECH-SINGLE-WRITER"
    if "guard_slot" in value or "/admission/" in value: return "MECH-ADMISSION"
    if "rq2_archive" in value or "f2_archive" in value: return "F2a"
    if "switch_severity" in value or "f2_campaign" in value: return "F2"
    if "fuzz1c" in value or "f1_anchor" in value: return "F1"
    if "raptor_unclipped" in value or "s2_unclip" in value: return "RAPTOR-S2"
    if "raptor" in value and (path.startswith("docs/") or path.startswith("runs/") or path.startswith("experiments/")): return "RAPTOR-S1"
    if "wave1" in value or "b1_wind" in value: return "B1"
    if "wave2" in value or "b2_state" in value: return "B2"
    if "multipolicy" in value or "b3_multi" in value: return "B3"
    if "equivariance" in value: return "UNC-EQUIVARIANCE-20260708"
    if "legacy_wall_clock" in value: return "HARNESS-LEGACY"
    return "REPOSITORY"


def latest_commit(repo: Path, path: str) -> str:
    value = run(repo, "log", "-1", "--format=%H", "--", path).decode().strip()
    return value or "unknown"


def tracked_rows(repo: Path, output_relative: str) -> list[dict[str, str]]:
    files = [
        item.decode("utf-8", errors="surrogateescape")
        for item in run(repo, "ls-files", "-z").split(b"\0")
        if item
    ]
    rows: list[dict[str, str]] = []
    for relative in sorted(files):
        path = Path(relative)
        if relative == output_relative or path.parts[0] not in ROOTS or path.suffix.lower() not in SUFFIXES:
            continue
        absolute = repo / path
        if not absolute.is_file():
            continue
        rows.append(
            {
                "experiment_id": experiment_id(relative),
                "path": relative,
                "type": path.suffix.lower().lstrip(".") or "file",
                "size": str(absolute.stat().st_size),
                "sha256": sha256_file(absolute),
                "git_commit": latest_commit(repo, relative),
                "status": "tracked",
                "notes": "major tracked research artifact; classification by canonical path map",
            }
        )
    return rows


def external_rows(repo: Path, manifest_relatives: list[str]) -> list[dict[str, str]]:
    groups: dict[str, list[dict[str, str]]] = {}
    commits: dict[str, str] = {}
    for manifest_relative in manifest_relatives:
        manifest = repo / manifest_relative
        if not manifest.exists():
            continue
        commits[manifest_relative] = latest_commit(repo, manifest_relative)
        with manifest.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream, dialect="excel-tab"):
                row["_manifest"] = manifest_relative
                groups.setdefault(row["experiment_id"], []).append(row)
    output: list[dict[str, str]] = []
    for exp_id, rows in sorted(groups.items()):
        digest = hashlib.sha256()
        for row in sorted(rows, key=lambda value: value["original_path"]):
            digest.update(row["original_path"].encode())
            digest.update(b"\0")
            digest.update(row["size"].encode())
            digest.update(b"\0")
            digest.update(row["sha256"].encode())
            digest.update(b"\n")
        common = os.path.commonpath([row["external_path"] for row in rows])
        output.append(
            {
                "experiment_id": exp_id,
                "path": f"external:{common}",
                "type": "external_raw_collection",
                "size": str(sum(int(row["size"]) for row in rows)),
                "sha256": digest.hexdigest(),
                "git_commit": ";".join(sorted({commits[row["_manifest"]] for row in rows})),
                "status": "external_preserved",
                "notes": f"{len(rows)} files; per-file manifests: {','.join(sorted({row['_manifest'] for row in rows}))}",
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", default="docs/indexes/ARTIFACT_MANIFEST.tsv")
    parser.add_argument("--external-manifest", action="append", dest="external_manifests")
    args = parser.parse_args()
    repo = args.repo.resolve()
    external_manifests = args.external_manifests or [
        "data/manifests/EXTERNAL_RAW_FILE_MANIFEST.tsv",
        "data/manifests/HISTORICAL_IGNORED_FILE_MANIFEST.tsv",
        "data/manifests/HISTORICAL_IGNORED_NESTED_CACHE_MANIFEST.tsv",
    ]
    rows = tracked_rows(repo, args.output) + external_rows(repo, external_manifests)
    rows.sort(key=lambda row: (row["experiment_id"], row["path"]))
    fields = ["artifact_id", "experiment_id", "path", "type", "size", "sha256", "git_commit", "status", "notes"]
    output = repo / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab", lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(rows, 1):
            writer.writerow({"artifact_id": f"ART-{index:06d}", **row})
    temporary.replace(output)
    print(f"artifacts={len(rows)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
