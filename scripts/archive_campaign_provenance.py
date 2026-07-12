#!/usr/bin/env python3
"""Archive campaign binary and environment provenance.

This script is read-only except for the requested JSON output. It does not run
PX4 or rebuild anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path = REPO) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, check=False, text=True, capture_output=True)
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:  # pragma: no cover - provenance should record failures
        return {"cmd": cmd, "error": repr(exc)}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hashed_files(paths: list[Path]) -> list[dict[str, str]]:
    out = []
    for path in sorted(paths):
        if path.exists() and path.is_file():
            out.append({"path": str(path.relative_to(REPO)), "sha256": sha256_file(path)})
    return out


def glob_files(patterns: list[str]) -> list[Path]:
    files: set[Path] = set()
    for pattern in patterns:
        files.update(REPO.glob(pattern))
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="docs/round5_delivered_state_20260709/provenance_snapshot.json")
    parser.add_argument("--image", default="uav_sf:phase1")
    args = parser.parse_args()

    px4 = REPO / "external/PX4-Autopilot"
    binaries = glob_files(["external/PX4-Autopilot/build/**/bin/px4"])
    patches = glob_files(["patches/px4/*.patch"])
    model_sources = glob_files(
        [
            "external/PX4-Autopilot/src/modules/mc_nn_control/*",
            "external/PX4-Autopilot/src/modules/mc_raptor/*",
            "external/PX4-Autopilot/src/modules/mc_raptor/blob/*",
            "external/PX4-Autopilot/src/modules/mc_raptor/trajectories/*",
        ]
    )
    model_sources = [path for path in model_sources if path.is_file()]

    payload = {
        "command": "python3 scripts/archive_campaign_provenance.py --output " + args.output,
        "px4": {
            "head": run(["git", "rev-parse", "HEAD"], cwd=px4),
            "status_short": run(["git", "status", "--short"], cwd=px4),
        },
        "docker_image": run(["docker", "image", "inspect", args.image, "--format", "{{json .}}"]),
        "toolchain": {
            "gcc": run(["gcc", "--version"]),
            "gxx": run(["g++", "--version"]),
            "cmake": run(["cmake", "--version"]),
            "ninja": run(["ninja", "--version"]),
        },
        "environment": {key: value for key, value in sorted(os.environ.items()) if key.startswith(("PX4_", "ROS_", "RMW_", "HEADLESS", "FASTRTPS"))},
        "patches": hashed_files(patches),
        "model_sources": hashed_files(model_sources),
        "binaries": hashed_files(binaries),
    }

    out_path = (REPO / args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
