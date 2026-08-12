#!/usr/bin/env python3
"""Atomic append-only accounting for every launch in one formal study."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ZERO_HASH = "0" * 64
OUTCOMES = frozenset(
    {
        "ACCEPTED",
        "OBSERVABILITY_REJECTED",
        "INCONCLUSIVE",
        "ENVIRONMENT_FAILURE",
        "CAMPAIGN_CONFIGURATION_FAILURE",
        "FORMAL_SAFETY_STOP",
        "TIMEOUT",
    }
)
STATES = ("REGISTERED", "LAUNCHED", "CLOSED")


class StudyAccountingError(ValueError):
    """A study ledger operation would weaken launch accounting."""


def _digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _events_from_text(text: str) -> list[dict[str, Any]]:
    events = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise StudyAccountingError(f"ledger line {line_number} is not an object")
        events.append(value)
    return events


def verify_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    previous = ZERO_HASH
    attempts: dict[str, dict[str, Any]] = {}
    study_id: str | None = None
    for sequence, event in enumerate(events):
        if event.get("sequence") != sequence or event.get("previous_hash") != previous:
            raise StudyAccountingError(f"study chain breaks at event {sequence}")
        without_hash = dict(event)
        observed_hash = without_hash.pop("event_hash", None)
        if observed_hash != _digest(without_hash):
            raise StudyAccountingError(f"study digest is invalid at event {sequence}")
        if event.get("state") not in STATES:
            raise StudyAccountingError(f"invalid study state at event {sequence}")
        if study_id is None:
            study_id = str(event.get("study_id", ""))
        if event.get("study_id") != study_id:
            raise StudyAccountingError("study identity changed inside the ledger")
        attempt_id = str(event.get("attempt_id", ""))
        current = attempts.get(attempt_id)
        state = str(event["state"])
        if current is None:
            if state != "REGISTERED" or not attempt_id:
                raise StudyAccountingError("an attempt must begin with registration")
            attempts[attempt_id] = {
                "state": state,
                "cell_id": event.get("cell_id"),
                "outcome": None,
            }
        else:
            expected = "LAUNCHED" if current["state"] == "REGISTERED" else "CLOSED"
            if state != expected:
                raise StudyAccountingError(f"invalid attempt transition for {attempt_id}")
            if event.get("cell_id") != current["cell_id"]:
                raise StudyAccountingError("attempt cell identity changed")
            if state == "CLOSED":
                outcome = event.get("payload", {}).get("outcome")
                if outcome not in OUTCOMES:
                    raise StudyAccountingError(f"invalid outcome for {attempt_id}")
                current["outcome"] = outcome
            current["state"] = state
        previous = str(observed_hash)
    return {
        "study_id": study_id,
        "event_count": len(events),
        "chain_head": previous,
        "attempts": attempts,
        "launched_count": sum(
            value["state"] in {"LAUNCHED", "CLOSED"} for value in attempts.values()
        ),
        "closed_count": sum(value["state"] == "CLOSED" for value in attempts.values()),
        "accepted_count": sum(value["outcome"] == "ACCEPTED" for value in attempts.values()),
    }


def verify_study_ledger(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return verify_events(_events_from_text(text))


class StudyLedger:
    def __init__(self, path: Path, *, study_id: str) -> None:
        if not study_id.strip():
            raise StudyAccountingError("study_id is required")
        self.path = path
        self.study_id = study_id
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    def append(
        self,
        *,
        attempt_id: str,
        cell_id: str,
        state: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not attempt_id.strip() or not cell_id.strip():
            raise StudyAccountingError("attempt_id and cell_id are required")
        with self.path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            text = handle.read()
            events = _events_from_text(text)
            current = verify_events(events)
            if current["study_id"] not in {None, self.study_id}:
                raise StudyAccountingError("ledger belongs to another study")
            attempt = current["attempts"].get(attempt_id)
            expected = (
                "REGISTERED"
                if attempt is None
                else ("LAUNCHED" if attempt["state"] == "REGISTERED" else "CLOSED")
            )
            if state != expected:
                raise StudyAccountingError(
                    f"invalid attempt transition for {attempt_id}: expected {expected}"
                )
            if attempt is not None and attempt["cell_id"] != cell_id:
                raise StudyAccountingError("attempt cell identity changed")
            if state == "CLOSED" and (payload or {}).get("outcome") not in OUTCOMES:
                raise StudyAccountingError("closure requires a supported outcome")
            event: dict[str, Any] = {
                "schema_version": "1.0",
                "study_id": self.study_id,
                "attempt_id": attempt_id,
                "cell_id": cell_id,
                "sequence": len(events),
                "state": state,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                "previous_hash": current["chain_head"],
                "payload": payload or {},
            }
            event["event_hash"] = _digest(event)
            handle.seek(0, os.SEEK_END)
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            verify_events([*events, event])
            return event
