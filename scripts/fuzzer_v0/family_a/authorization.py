#!/usr/bin/env python3
"""Pushed-main authorization verification without commit self-reference."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = (
    ROOT
    / "experiments/fuzzer_v0/family_a/full_readiness/"
    "authorization_identity_manifest.json"
)


class AuthorizationError(RuntimeError):
    """A formal mutation or launch is not authorized by pushed main."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repo: Path, *args: str, check: bool = True) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if check and process.returncode:
        raise AuthorizationError(
            f"git {' '.join(args)} failed: {process.stderr.strip()}"
        )
    return process.stdout.strip()


def _load(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuthorizationError(f"{path}: expected an object")
    return value


def _relative(repo: Path, path: Path) -> Path:
    try:
        return path.resolve().relative_to(repo.resolve())
    except ValueError as exc:
        raise AuthorizationError(f"authorization asset is outside repository: {path}") from exc


def _commit_has_exact_file(repo: Path, commit: str, path: Path) -> bool:
    relative = _relative(repo, path)
    process = subprocess.run(
        ["git", "show", f"{commit}:{relative.as_posix()}"],
        cwd=repo,
        capture_output=True,
    )
    return process.returncode == 0 and process.stdout == path.read_bytes()


def _is_ancestor(repo: Path, commit: str, descendant: str = "HEAD") -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, descendant],
            cwd=repo,
            capture_output=True,
        ).returncode
        == 0
    )


def verify_pushed_main(repo: Path) -> dict[str, Any]:
    branch = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if branch != "main":
        raise AuthorizationError(
            "formal commands require attached branch main; detached or other branch refused"
        )
    if _git(repo, "status", "--porcelain"):
        raise AuthorizationError("formal commands require a clean worktree")
    head = _git(repo, "rev-parse", "HEAD")
    origin = _git(repo, "rev-parse", "origin/main")
    counts = _git(repo, "rev-list", "--left-right", "--count", "HEAD...origin/main")
    if head != origin or counts.split() != ["0", "0"]:
        raise AuthorizationError(
            "HEAD must equal pushed origin/main with ahead/behind 0/0"
        )
    return {
        "branch": branch,
        "head": head,
        "origin_main": origin,
        "ahead": 0,
        "behind": 0,
        "worktree_clean": True,
    }


def _verify_hash_record(repo: Path, record: dict[str, Any], label: str) -> Path:
    path = repo / str(record.get("path", ""))
    expected = record.get("sha256")
    if not path.is_file() or not isinstance(expected, str) or sha256(path) != expected:
        raise AuthorizationError(f"{label} hash mismatch")
    return path


def _require_false(value: Any, label: str) -> None:
    if value is not False:
        raise AuthorizationError(f"{label} must remain false")


@dataclass(frozen=True)
class AuthorizationState:
    repository_commit: str
    authorization_commit: str
    decision_path: Path
    ledger_path: Path
    manifest_path: Path
    next_attempt_id: str
    status: str


def verify_authorization(
    *,
    repo: Path,
    manifest_path: Path,
    authorization_commit: str,
    require_registration_commit: str | None = None,
    registration_path: Path | None = None,
) -> AuthorizationState:
    identity = verify_pushed_main(repo)
    head = identity["head"]
    if not isinstance(authorization_commit, str) or len(authorization_commit) != 40:
        raise AuthorizationError("exact 40-character authorization commit is required")
    if not _is_ancestor(repo, authorization_commit, head):
        raise AuthorizationError("authorization identity-lock commit is not in HEAD ancestry")
    if not _commit_has_exact_file(repo, authorization_commit, manifest_path):
        raise AuthorizationError(
            "authorization manifest is not the exact blob in the supplied identity-lock commit"
        )

    manifest = _load(manifest_path)
    if manifest.get("schema_version") != "1.0":
        raise AuthorizationError("authorization manifest schema version mismatch")
    if manifest.get("branch") != "main":
        raise AuthorizationError("authorization manifest does not lock branch main")
    if manifest.get("qualification_target_accepted") != 3:
        raise AuthorizationError("qualification target is not 3")
    if manifest.get("qualification_maximum_formal_attempts") != 6:
        raise AuthorizationError("qualification maximum is not 6")
    _require_false(
        manifest.get("comparison_runtime_authorized"),
        "comparison_runtime_authorized",
    )

    decision_path = _verify_hash_record(
        repo, manifest.get("decision", {}), "activation decision"
    )
    ledger_path = _verify_hash_record(
        repo, manifest.get("initial_ledger", {}), "initial qualification ledger"
    )
    for label, record in manifest.get("locked_assets", {}).items():
        if not isinstance(record, dict):
            raise AuthorizationError(f"locked asset record is invalid: {label}")
        _verify_hash_record(repo, record, f"locked asset {label}")

    commits = manifest.get("commits")
    if not isinstance(commits, dict):
        raise AuthorizationError("authorization commit map is missing")
    for label in (
        "preregistration",
        "implementation",
        "environment_identity_lock",
        "independent_review",
    ):
        commit = commits.get(label)
        if not isinstance(commit, str) or len(commit) != 40:
            raise AuthorizationError(f"authorization commit is invalid: {label}")
        if not _is_ancestor(repo, commit, head):
            raise AuthorizationError(f"authorization commit is not in HEAD ancestry: {label}")

    decision = _load(decision_path)
    if decision.get("decision") != "APPROVE_QUALIFICATION_ONLY":
        raise AuthorizationError("decision is not APPROVE_QUALIFICATION_ONLY")
    if decision.get("status") not in {
        "QUALIFICATION_AUTHORIZED_NOT_STARTED",
        "QUALIFICATION_IN_PROGRESS",
    }:
        raise AuthorizationError("qualification status is not authorized")
    if decision.get("authorized_scope") != "V0_P_QUALIFICATION_ONLY":
        raise AuthorizationError("authorized scope is not V0_P_QUALIFICATION_ONLY")
    if decision.get("qualification_runtime_authorized") is not True:
        raise AuthorizationError("qualification runtime is not authorized")
    if decision.get("qualification_execution_requires_separate_task") is not True:
        raise AuthorizationError("qualification must require a separate task")
    for field in (
        "comparison_runtime_authorized",
        "official_sequence_authorized",
        "bounded_random_timing_authorized",
        "state_aware_authorized",
        "real_workload_authorized",
        "family_b_authorized",
        "direct_actuator_authorized",
        "hitl_authorized",
        "real_flight_authorized",
    ):
        _require_false(decision.get(field), field)

    ledger = _load(ledger_path)
    if ledger.get("formal_attempts") != 0 or ledger.get("accepted_attempts") != 0:
        raise AuthorizationError("initial qualification ledger is not zero")
    if ledger.get("attempts") != [] or ledger.get("next_attempt_id") != "V0P-A1":
        raise AuthorizationError("initial qualification ledger shape mismatch")

    if require_registration_commit is not None:
        if registration_path is None or not registration_path.is_file():
            raise AuthorizationError("prelaunch registration file is required")
        if len(require_registration_commit) != 40:
            raise AuthorizationError("exact registration commit is required")
        if not _is_ancestor(repo, require_registration_commit, head):
            raise AuthorizationError("registration commit is not in HEAD ancestry")
        if not _commit_has_exact_file(
            repo, require_registration_commit, registration_path
        ):
            raise AuthorizationError(
                "registration is not the exact pushed blob in its supplied commit"
            )

    return AuthorizationState(
        repository_commit=head,
        authorization_commit=authorization_commit,
        decision_path=decision_path,
        ledger_path=ledger_path,
        manifest_path=manifest_path,
        next_attempt_id=str(ledger["next_attempt_id"]),
        status=str(decision["status"]),
    )
