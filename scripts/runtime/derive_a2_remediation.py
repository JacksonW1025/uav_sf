#!/usr/bin/env python3
"""Derive the separately identified A2 remediation matrix without mutation."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from scripts.runtime.run_campaign import validate_matrix


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def derive(source: Path, attestation_path: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError(f"refusing to overwrite {output}")
    value = copy.deepcopy(json.loads(source.read_text(encoding="utf-8")))
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    candidate = attestation["attestation_payload"]["container"]
    value.update(
        {
            "study_id": "motivation-stage-a2-thor-remediation-v1",
            "environment_id": attestation["execution_environment"]["environment_id"],
            "repository_revision": candidate["candidate"]["repository_revision"],
            "container_image_id": candidate["image_id"],
            "environment_attestation_digest": digest(attestation_path),
        }
    )
    for cell in value["cells"]:
        cell["cell_id"] += "-remediation"
        cell["attempt_id_prefix"] += "-remediation"
        cell["plan"]["source_route"] = "internal_hold"
        cell["runtime"]["simulation_seed_base"] += 1_000_000
    validate_matrix(value)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    derive(args.source, args.attestation, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
