#!/usr/bin/env python3
"""Check whether the route-observability patch is applicable or already applied."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches" / "px4" / "route_observability" / "route_observability_topics.patch"
LOCKED_COMMIT = "4ae21a5e569d3d89c2f6366688cbacb3e93437c9"


def check(px4_dir: Path) -> dict[str, object]:
    head = subprocess.run(
        ["git", "-C", str(px4_dir), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if head != LOCKED_COMMIT:
        return {"status": "WRONG_BASE", "head": head, "expected": LOCKED_COMMIT}

    forward = subprocess.run(
        ["git", "-C", str(px4_dir), "apply", "--check", str(PATCH)],
        text=True,
        capture_output=True,
    )
    if forward.returncode == 0:
        return {"status": "APPLICABLE", "head": head, "patch": str(PATCH)}

    reverse = subprocess.run(
        ["git", "-C", str(px4_dir), "apply", "--reverse", "--check", str(PATCH)],
        text=True,
        capture_output=True,
    )
    if reverse.returncode == 0:
        return {"status": "APPLIED", "head": head, "patch": str(PATCH)}
    return {
        "status": "CONFLICT",
        "head": head,
        "forward_error": forward.stderr.strip(),
        "reverse_error": reverse.stderr.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--px4-dir", type=Path, default=ROOT / "external" / "PX4-Autopilot")
    args = parser.parse_args()
    result = check(args.px4_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"APPLICABLE", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
