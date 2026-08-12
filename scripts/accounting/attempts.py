#!/usr/bin/env python3
"""Hash-chained accounting for newly preregistered formal attempts."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ZERO_HASH = "0" * 64
TRANSITIONS: dict[str | None, set[str]] = {
    None: {"REGISTERED"},
    "REGISTERED": {"PREFLIGHT_PASSED", "REJECTED"},
    "PREFLIGHT_PASSED": {"LAUNCHED", "REJECTED"},
    "LAUNCHED": {"COLLECTION_CLOSED", "SAFETY_STOPPED"},
    "SAFETY_STOPPED": {"COLLECTION_CLOSED"},
    "COLLECTION_CLOSED": {"EVALUATED"},
    "EVALUATED": {"CLEANUP_COMPLETED"},
    "CLEANUP_COMPLETED": {"CLOSED"},
    "CLOSED": set(),
    "REJECTED": set(),
}


class AccountingError(ValueError):
    """Attempt accounting would become ambiguous or mutable."""


def _digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def verify_ledger(path: Path) -> dict[str, Any]:
    events = _read(path)
    previous = ZERO_HASH
    previous_state: str | None = None
    attempt_id: str | None = None
    plan_id: str | None = None
    for index, event in enumerate(events):
        if event.get("sequence") != index or event.get("previous_hash") != previous:
            raise AccountingError(f"accounting chain breaks at event {index}")
        without = dict(event)
        observed = without.pop("event_hash", None)
        if observed != _digest(without):
            raise AccountingError(f"accounting digest is invalid at event {index}")
        if event.get("state") not in TRANSITIONS.get(previous_state, set()):
            raise AccountingError(f"invalid accounting transition at event {index}")
        if attempt_id is None:
            attempt_id, plan_id = event.get("attempt_id"), event.get("plan_id")
        if event.get("attempt_id") != attempt_id or event.get("plan_id") != plan_id:
            raise AccountingError("attempt and plan identities must not change")
        previous = str(observed)
        previous_state = str(event["state"])
    return {
        "attempt_id": attempt_id,
        "plan_id": plan_id,
        "event_count": len(events),
        "state": previous_state,
        "formal_attempt_consumed": any(event["state"] == "LAUNCHED" for event in events),
        "closed": previous_state == "CLOSED",
        "chain_head": previous,
    }


class AttemptLedger:
    def __init__(self, path: Path, *, attempt_id: str, plan_id: str) -> None:
        if path.exists():
            raise AccountingError(f"refusing to overwrite ledger: {path}")
        if not attempt_id.strip() or not plan_id.strip():
            raise AccountingError("attempt_id and plan_id are required")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.attempt_id = attempt_id
        self.plan_id = plan_id

    def append(self, state: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        events = _read(self.path)
        current = verify_ledger(self.path) if events else {"state": None, "chain_head": ZERO_HASH}
        if state not in TRANSITIONS.get(current["state"], set()):
            raise AccountingError(f"invalid accounting transition: {current['state']} -> {state}")
        event: dict[str, Any] = {
            "schema_version": "1.0",
            "attempt_id": self.attempt_id,
            "plan_id": self.plan_id,
            "sequence": len(events),
            "state": state,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            "previous_hash": current["chain_head"],
            "payload": payload or {},
        }
        event["event_hash"] = _digest(event)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        verify_ledger(self.path)
        return event
