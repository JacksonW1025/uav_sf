#!/usr/bin/env python3
"""Locate the frozen, admissible Motivation corpus without mutating it."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


STUDIES = (
    ("motivation-thor-v1", "motivation_thor_v1", 131),
    ("motivation-thor-remediation-v1", "motivation_thor_remediation_v1", 20),
)


class CorpusError(RuntimeError):
    """The retained corpus is incomplete or differs from its frozen ledger."""


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


@dataclass(frozen=True)
class CorpusRecord:
    study_id: str
    attempt_id: str
    cell_id: str
    outcome: str
    plan_path: Path
    trace_path: Path
    frozen_evaluation_path: Path
    plan_digest: str
    trace_digest: str
    frozen_evaluation_digest: str

    def manifest_entry(self, root: Path) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "attempt_id": self.attempt_id,
            "cell_id": self.cell_id,
            "outcome": self.outcome,
            "plan": str(self.plan_path.relative_to(root)),
            "trace": str(self.trace_path.relative_to(root)),
            "frozen_evaluation": str(self.frozen_evaluation_path.relative_to(root)),
            "digests": {
                "plan": self.plan_digest,
                "trace": self.trace_digest,
                "frozen_evaluation": self.frozen_evaluation_digest,
            },
        }


def _closed_attempts(ledger: Path) -> dict[str, dict[str, Any]]:
    closed: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("state") != "CLOSED":
            continue
        attempt_id = str(event.get("attempt_id", ""))
        if not attempt_id or attempt_id in closed:
            raise CorpusError(f"duplicate or empty CLOSED attempt at {ledger}:{line_number}")
        closed[attempt_id] = event
    return closed


def load_frozen_corpus(root: Path) -> list[CorpusRecord]:
    root = root.resolve()
    records: list[CorpusRecord] = []
    for study_id, experiment_directory, expected in STUDIES:
        study = root / "experiments" / experiment_directory
        ledger = study / "attempt-ledger.jsonl"
        accepted = {
            attempt_id: event
            for attempt_id, event in _closed_attempts(ledger).items()
            if event.get("payload", {}).get("outcome") == "ACCEPTED"
        }
        if len(accepted) != expected:
            raise CorpusError(
                f"{study_id} has {len(accepted)} accepted attempts; expected {expected}"
            )
        for attempt_id, event in sorted(accepted.items()):
            plan_path = root / "runs" / study_id / "plans" / f"{attempt_id}.json"
            trace_path = (
                root / "runs" / study_id / attempt_id / "derived" / "closed.trace.jsonl"
            )
            frozen = study / "results" / attempt_id / "evaluation.json"
            missing = [path for path in (plan_path, trace_path, frozen) if not path.is_file()]
            if missing:
                raise CorpusError(
                    f"{attempt_id} is missing retained inputs: "
                    + ", ".join(str(path) for path in missing)
                )
            records.append(
                CorpusRecord(
                    study_id=study_id,
                    attempt_id=attempt_id,
                    cell_id=str(event.get("cell_id", "")),
                    outcome="ACCEPTED",
                    plan_path=plan_path,
                    trace_path=trace_path,
                    frozen_evaluation_path=frozen,
                    plan_digest=file_digest(plan_path),
                    trace_digest=file_digest(trace_path),
                    frozen_evaluation_digest=file_digest(frozen),
                )
            )
    if len(records) != 151:
        raise CorpusError(f"combined corpus has {len(records)} records; expected 151")
    return records
