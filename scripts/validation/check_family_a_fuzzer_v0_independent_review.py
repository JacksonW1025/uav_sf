#!/usr/bin/env python3
"""Verify the independent clean-clone evidence for Family A full readiness."""

from __future__ import annotations

import json
import sys

from scripts.validation.check_family_a_fuzzer_v0_full_readiness import (
    FullReadinessError,
    READINESS,
    _sha256,
    _yaml,
    validate,
)


def main() -> int:
    try:
        result = validate()
        manifest = _yaml(READINESS / "independent_test_manifest.yaml")
        if manifest.get("reviewed_environment_lock_sha256") != _sha256(
            READINESS / "full_environment_lock.yaml"
        ):
            raise FullReadinessError("independent review environment-lock hash differs")
        if manifest.get("reviewed_binary_manifest_sha256") != _sha256(
            READINESS / "binary_manifest.json"
        ):
            raise FullReadinessError("independent review binary-manifest hash differs")
        if manifest.get("reviewed_component_manifest_sha256") != _sha256(
            READINESS / "component_manifest.yaml"
        ):
            raise FullReadinessError("independent review component-manifest hash differs")
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "review": "INDEPENDENT_CLEAN_CLONE",
                "authorization": result["authorization"]["status"],
                "runtime_started": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
