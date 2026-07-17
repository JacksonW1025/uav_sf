#!/usr/bin/env python3
"""P0-D2 full external flight followed by clean internal re-entry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.probes.p0d_post_disarm_reentry import run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shutdown-request", type=Path, required=True)
    parser.add_argument("--shutdown-done", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()
    return run(
        args.output,
        args.shutdown_request,
        args.shutdown_done,
        args.timeout,
        select_internal_before_rearm=True,
        scenario_label="p0d2_full_external_reentry",
    )


if __name__ == "__main__":
    raise SystemExit(main())
