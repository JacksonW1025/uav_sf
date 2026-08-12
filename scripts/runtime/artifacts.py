#!/usr/bin/env python3
"""Hash and verify raw evidence without placing it under version control."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_manifest(root: Path) -> dict[str, Any]:
    resolved = root.resolve()
    if not resolved.is_dir():
        raise ValueError("raw-evidence root does not exist")
    records = []
    for path in sorted(resolved.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"raw evidence must not contain symlinks: {path}")
        if path.is_file():
            records.append(
                {
                    "path": path.relative_to(resolved).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    return {
        "schema_version": "1.0",
        "root_name": resolved.name,
        "file_count": len(records),
        "files": records,
    }


def verify_manifest(root: Path, manifest: dict[str, Any]) -> None:
    observed = create_manifest(root)
    if observed != manifest:
        raise ValueError("raw-evidence manifest differs from the retained files")


def write_manifest(root: Path, output: Path) -> None:
    if output.exists():
        raise ValueError(f"refusing to overwrite manifest: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(create_manifest(root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
