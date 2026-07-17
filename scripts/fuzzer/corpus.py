"""Content-addressed Fuzzer v0 corpus and duplicate index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .case_model import duplicate_fingerprint, write_case


class Corpus:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cases = root / "cases"
        self.index = root / "index.jsonl"
        self.cases.mkdir(parents=True, exist_ok=True)

    def fingerprints(self) -> set[str]:
        if not self.index.exists():
            return set()
        return {
            json.loads(line)["fingerprint"]
            for line in self.index.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    def admit(
        self, case: dict[str, Any], result: dict[str, Any], *, allow_unknown: bool = False
    ) -> tuple[bool, str]:
        fingerprint = duplicate_fingerprint(case)
        if fingerprint in self.fingerprints():
            return False, "DUPLICATE"
        if result["classification"] == "MEASUREMENT_UNKNOWN" and not allow_unknown:
            return False, "UNKNOWN_EXCLUDED"
        if result["classification"] not in {"SUT_PASS", "SUT_VIOLATION"}:
            return False, "INVALID_EXCLUDED"
        path = self.cases / f"{case['case_id']}.json"
        write_case(case, path)
        record = {
            "case_id": case["case_id"],
            "classification": result["classification"],
            "fingerprint": fingerprint,
            "target_clauses": result.get("oracle", {}).get("target_clauses", []),
        }
        with self.index.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return True, "ADMITTED"
