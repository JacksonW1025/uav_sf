#!/usr/bin/env python3
"""Unified launcher for the locked-version C++ P0 Mode Executor."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    setup = repo_root / "ros2_ws" / "install" / "setup.bash"
    if not setup.is_file():
        raise SystemExit("Family A workspace is not built; run scripts/setup/bootstrap_family_a.sh")
    command = (
        f"source {setup} && "
        "ros2 run route_transition_external_mode p0_external_mode_executor"
    )
    return subprocess.call(["bash", "-lc", command], env=os.environ.copy())


if __name__ == "__main__":
    raise SystemExit(main())
