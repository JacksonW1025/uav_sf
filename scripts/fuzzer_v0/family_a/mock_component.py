#!/usr/bin/env python3
"""Subprocess fixture component that proves graph invocation and data flow."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--fail", action="store_true")
    args = parser.parse_args()
    missing = [str(path) for path in args.input if not path.is_file()]
    if missing:
        print(json.dumps({"status": "MISSING_INPUT", "missing": missing}))
        return 20
    if args.fail:
        print(json.dumps({"status": "INJECTED_FAILURE", "node_id": args.node_id}))
        return 21
    result = {
        "schema_version": "1.0",
        "node_id": args.node_id,
        "status": "PASS",
        "consumed": [
            {"path": str(path), "sha256": sha256(path)} for path in args.input
        ],
        "runtime_started": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
