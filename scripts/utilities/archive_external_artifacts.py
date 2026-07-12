#!/usr/bin/env python3
"""Safely externalize large raw experiment files and record SHA-256 provenance."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterable


RESEARCH_ROOTS = (
    ("tier05_fork_20260712T090728Z", "HARNESS-BETA-TIER05"),
    ("docs/px4_race_r4_gate_20260709", "MECH-ALLOCATION-FRESHNESS"),
)


def classify_ignored(relative: str) -> str:
    value = relative.lower()
    if "raptor_unclipped" in value:
        return "RAPTOR-S2"
    if "raptor" in value:
        return "RAPTOR-S1"
    if "route_a_anchor" in value or "fuzz1c" in value or "mcnn_gonogo" in value:
        return "F1"
    if "switch_severity" in value:
        return "F2"
    return "UNC-HISTORICAL-IGNORED"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_symlink():
        digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        return digest.hexdigest()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def selected_paths(repo: Path) -> list[tuple[Path, str]]:
    selected: dict[Path, str] = {}
    for relative_root, experiment_id in RESEARCH_ROOTS:
        root = repo / relative_root
        if not root.exists():
            continue
        for px4_roots in root.rglob("px4_roots"):
            if not px4_roots.is_dir():
                continue
            for path in px4_roots.rglob("*"):
                if path.is_file() or path.is_symlink():
                    selected[path] = experiment_id
        for pattern in ("*.ulg", "*.log"):
            for path in root.rglob(pattern):
                if path.is_file() or path.is_symlink():
                    selected[path] = experiment_id
    return sorted(selected.items(), key=lambda item: item[0].as_posix())


def ignored_research_paths(repo: Path) -> list[tuple[Path, str]]:
    proc = subprocess.run(
        [
            "git", "-C", str(repo), "ls-files", "--others", "--ignored",
            "--exclude-standard", "-z", "--", "docs", "runs",
            "tier05_fork_20260712T090728Z",
        ],
        check=True,
        capture_output=True,
    )
    selected: list[tuple[Path, str]] = []
    for value in proc.stdout.split(b"\0"):
        if not value:
            continue
        relative = value.decode("utf-8", errors="surrogateescape")
        path = repo / relative
        if path.is_file() or path.is_symlink():
            selected.append((path, classify_ignored(relative)))
        elif path.is_dir():
            for nested in path.rglob("*"):
                if nested.is_file() or nested.is_symlink():
                    nested_relative = nested.relative_to(repo).as_posix()
                    selected.append((nested, classify_ignored(nested_relative)))
    return selected


def tracked_selected(repo: Path, paths: Iterable[Path]) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    tracked = {
        value.decode("utf-8", errors="surrogateescape")
        for value in proc.stdout.split(b"\0")
        if value
    }
    return sorted(
        relative
        for path in paths
        if (relative := path.relative_to(repo).as_posix()) in tracked
    )


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    fields = [
        "artifact_id",
        "experiment_id",
        "original_path",
        "external_path",
        "type",
        "size",
        "sha256",
        "status",
        "notes",
    ]
    with temp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, dialect="excel-tab", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Move only raw .ulg/.log files and generated px4_roots from the two "
            "known large campaigns to an external archive, preserving relative paths "
            "and writing a SHA-256 manifest. Tracked files are never moved."
        )
    )
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/manifests/EXTERNAL_RAW_FILE_MANIFEST.tsv"),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--all-ignored-research",
        action="store_true",
        help="archive every remaining ignored/untracked file under docs, runs, and the Tier-0.5 root",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    external_root = args.external_root.resolve()
    manifest = args.manifest if args.manifest.is_absolute() else repo / args.manifest
    if repo == external_root or repo in external_root.parents:
        raise SystemExit("--external-root must be outside the repository")

    selected = ignored_research_paths(repo) if args.all_ignored_research else selected_paths(repo)
    tracked = tracked_selected(repo, (path for path, _ in selected))
    if tracked:
        print("Refusing to move tracked files:", file=sys.stderr)
        print("\n".join(tracked), file=sys.stderr)
        return 2

    rows: list[dict[str, str]] = []
    for index, (source, experiment_id) in enumerate(selected, 1):
        relative = source.relative_to(repo)
        destination = external_root / relative
        rows.append(
            {
                "artifact_id": f"EXT-{index:06d}",
                "experiment_id": experiment_id,
                "original_path": relative.as_posix(),
                "external_path": str(destination),
                "type": "symlink" if source.is_symlink() else source.suffix.lstrip(".") or "file",
                "size": str(source.lstat().st_size),
                "sha256": sha256_path(source),
                "status": "planned_external" if args.dry_run else "externalizing",
                "notes": "Git LFS unavailable; original bytes preserved outside repository",
            }
        )

    write_manifest(manifest, rows)
    total = sum(int(row["size"]) for row in rows)
    print(f"selected_files={len(rows)} selected_bytes={total} manifest={manifest}")
    if args.dry_run:
        return 0

    external_root.mkdir(parents=True, exist_ok=True)
    for (source, _), row in zip(selected, rows, strict=True):
        destination = Path(row["external_path"])
        if destination.exists() or destination.is_symlink():
            raise SystemExit(f"Refusing to overwrite external artifact: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        if destination.lstat().st_size != int(row["size"]):
            raise SystemExit(f"Size mismatch after move: {destination}")
        if sha256_path(destination) != row["sha256"]:
            raise SystemExit(f"SHA-256 mismatch after move: {destination}")
        row["status"] = "external_preserved"

    write_manifest(manifest, rows)
    print(f"externalized_files={len(rows)} externalized_bytes={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
