#!/usr/bin/env python3
"""Append-only, hash-chained attempt accounting for Family A V0-P."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


TOOL_IDENTITY = "family-a-attempt-accounting-1.0"
ZERO_HASH = "0" * 64
ATTEMPT_RE = re.compile(r"^V0P-A([1-6])$")
FIXTURE_RE = re.compile(r"^FIXTURE-[A-Z0-9_-]+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

TRANSITIONS: dict[str | None, set[str]] = {
    None: {"REGISTERED_PRELAUNCH", "REJECTED_PRELAUNCH"},
    "REGISTERED_PRELAUNCH": {"AUTHORIZATION_VERIFIED", "REJECTED_PRELAUNCH"},
    "AUTHORIZATION_VERIFIED": {"PREFLIGHT_PASSED", "REJECTED_PRELAUNCH"},
    "PREFLIGHT_PASSED": {"LAUNCH_STARTED", "REJECTED_PRELAUNCH"},
    "LAUNCH_STARTED": {"SCENARIO_COMPLETED", "SAFETY_STOPPED"},
    "SCENARIO_COMPLETED": {"COLLECTION_CLOSED"},
    "SAFETY_STOPPED": {"COLLECTION_CLOSED"},
    "COLLECTION_CLOSED": {"ORACLES_COMPLETED"},
    "ORACLES_COMPLETED": {"CLEANUP_COMPLETED"},
    "CLEANUP_COMPLETED": {"CLASSIFIED"},
    "CLASSIFIED": {"CLOSED"},
    "CLOSED": set(),
    "REJECTED_PRELAUNCH": set(),
}


class AccountingError(RuntimeError):
    """The requested event would violate append-only accounting."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def event_hash(event_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(event_without_hash)).hexdigest()


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise AccountingError(f"{path}:{number}: event must be an object")
        records.append(value)
    return records


def validate_events(
    records: list[dict[str, Any]], *, allow_fixture: bool = False
) -> dict[str, Any]:
    previous_hash = ZERO_HASH
    previous_type: str | None = None
    attempt_id: str | None = None
    launched = False
    for index, event in enumerate(records):
        required = {
            "attempt_id",
            "slot_id",
            "seed_id",
            "sequence",
            "event_type",
            "timestamp",
            "previous_event_hash",
            "event_hash",
            "repository_commit",
            "authorization_commit",
            "registration_commit",
            "payload_hash",
            "payload",
            "tool_identity",
        }
        if set(event) != required:
            raise AccountingError(f"event {index}: fields differ from the locked schema")
        current_attempt = str(event["attempt_id"])
        permitted = ATTEMPT_RE.fullmatch(current_attempt) or (
            allow_fixture and FIXTURE_RE.fullmatch(current_attempt)
        )
        if not permitted:
            raise AccountingError(f"event {index}: invalid attempt ID")
        if attempt_id is None:
            attempt_id = current_attempt
        elif attempt_id != current_attempt:
            raise AccountingError("one event stream cannot contain multiple attempts")
        if event["sequence"] != index:
            raise AccountingError(f"event {index}: sequence is not strictly monotonic")
        if event["previous_event_hash"] != previous_hash:
            raise AccountingError(f"event {index}: previous-event hash mismatch")
        expected_transition = TRANSITIONS.get(previous_type, set())
        if event["event_type"] not in expected_transition:
            raise AccountingError(
                f"event {index}: invalid transition {previous_type}->{event['event_type']}"
            )
        if event["payload_hash"] != payload_hash(event["payload"]):
            raise AccountingError(f"event {index}: payload hash mismatch")
        without_hash = dict(event)
        observed_hash = str(without_hash.pop("event_hash"))
        if observed_hash != event_hash(without_hash):
            raise AccountingError(f"event {index}: event hash mismatch")
        if not all(
            isinstance(event[field], str)
            and COMMIT_RE.fullmatch(event[field]) is not None
            for field in (
                "repository_commit",
                "authorization_commit",
                "registration_commit",
            )
        ):
            raise AccountingError(f"event {index}: commit identity is invalid")
        if event["tool_identity"] != TOOL_IDENTITY:
            raise AccountingError(f"event {index}: tool identity mismatch")
        launched = launched or event["event_type"] == "LAUNCH_STARTED"
        previous_hash = observed_hash
        previous_type = str(event["event_type"])
    return {
        "attempt_id": attempt_id,
        "event_count": len(records),
        "last_event": previous_type,
        "closed": previous_type == "CLOSED",
        "rejected_prelaunch": previous_type == "REJECTED_PRELAUNCH",
        "formal_budget_consumed": launched,
        "chain_head": previous_hash,
    }


def append_event(
    path: Path,
    *,
    attempt_id: str,
    slot_id: str,
    seed_id: str,
    event_type: str,
    repository_commit: str,
    authorization_commit: str,
    registration_commit: str,
    payload: dict[str, Any],
    allow_fixture: bool = False,
    timestamp: str | None = None,
) -> dict[str, Any]:
    records = _read(path)
    state = validate_events(records, allow_fixture=allow_fixture)
    if state["closed"] or state["rejected_prelaunch"]:
        raise AccountingError("closed or rejected attempt cannot be reopened")
    if records and records[0]["attempt_id"] != attempt_id:
        raise AccountingError("attempt ID cannot change within an event stream")
    previous_type = records[-1]["event_type"] if records else None
    if event_type not in TRANSITIONS.get(previous_type, set()):
        raise AccountingError(f"invalid transition {previous_type}->{event_type}")
    if event_type == "LAUNCH_STARTED" and previous_type != "PREFLIGHT_PASSED":
        raise AccountingError("launch-before-register is forbidden")
    record: dict[str, Any] = {
        "attempt_id": attempt_id,
        "slot_id": slot_id,
        "seed_id": seed_id,
        "sequence": len(records),
        "event_type": event_type,
        "timestamp": timestamp
        or datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "previous_event_hash": records[-1]["event_hash"] if records else ZERO_HASH,
        "repository_commit": repository_commit,
        "authorization_commit": authorization_commit,
        "registration_commit": registration_commit,
        "payload_hash": payload_hash(payload),
        "payload": payload,
        "tool_identity": TOOL_IDENTITY,
    }
    record["event_hash"] = event_hash(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical(record).decode("ascii") + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    validate_events(_read(path), allow_fixture=allow_fixture)
    return record


def aggregate(paths: Iterable[Path], *, allow_fixture: bool = False) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(paths):
        records = _read(path)
        state = validate_events(records, allow_fixture=allow_fixture)
        attempt_id = state["attempt_id"]
        if attempt_id in seen:
            raise AccountingError(f"duplicate attempt stream: {attempt_id}")
        if attempt_id is not None:
            seen.add(attempt_id)
        attempts.append({**state, "path": str(path)})
    consumed = sum(bool(item["formal_budget_consumed"]) for item in attempts)
    if not allow_fixture and consumed > 6:
        raise AccountingError("seventh formal qualification attempt is forbidden")
    incomplete = [
        item["attempt_id"]
        for item in attempts
        if item["formal_budget_consumed"] and not item["closed"]
    ]
    return {
        "schema_version": "1.0",
        "formal_attempts": consumed,
        "closed_attempts": sum(bool(item["closed"]) for item in attempts),
        "rejected_prelaunch_attempts": sum(
            bool(item["rejected_prelaunch"]) for item in attempts
        ),
        "incomplete_attempts": incomplete,
        "attempts": attempts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("events", type=Path, nargs="+")
    verify.add_argument("--fixture", action="store_true")
    args = parser.parse_args()
    try:
        result = aggregate(args.events, allow_fixture=args.fixture)
    except (AccountingError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"status": "PASS", **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
