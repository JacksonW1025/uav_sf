#!/usr/bin/env python3
"""Hash W1 raw artifacts and emit a machine-readable per-attempt manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    files = []
    for path in sorted(item for item in args.root.rglob("*") if item.is_file()):
        if path.resolve() == args.output.resolve():
            continue
        files.append(
            {
                "path": path.relative_to(args.root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    identity = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    result = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "raw_root_logical": f"runs/motivation/w1_workload/{args.run_id}/raw",
        "file_count": len(files),
        "total_size_bytes": sum(item["size_bytes"] for item in files),
        "artifact_set_sha256": identity,
        "files": files,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
