#!/usr/bin/env python3
"""Static whole-repository validation for the current Family A project."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.evaluator.plan import load_plan
from scripts.model.runtime_route import EVENT_KINDS, ROUTES
from scripts.state.semantic_state import (
    FAULT_CLASSES,
    FRESHNESS_STATES,
    LIFECYCLE_PHASES,
    MOTION_PHASES,
    ROUTE_FAMILIES,
)


ROOT = Path(__file__).resolve().parents[2]
IGNORED_ROOTS = {
    ".git",
    ".agents",
    ".codex",
    ".ccache",
    ".venv",
    "__pycache__",
    "external",
    "ros2_ws",
    "runs",
    "build",
    "install",
    "log",
}
ALLOWED_TOP = {
    ".dockerignore",
    ".gitattributes",
    ".gitignore",
    "AGENT.md",
    "CLAUDE.md",
    "README.md",
    "config",
    "containers",
    "data",
    "docs",
    "experiments",
    "patches",
    "runtime",
    "scripts",
    "tests",
}
TERM_SCAN_EXEMPT = {
    # The sole research narrative includes explicitly labelled future work and
    # is governed by a separate evidence-to-claim review.  Keep all other
    # repository checks active while avoiding an implementation-scope blacklist
    # being used to rewrite user-supplied narrative text.
    Path("docs/NEW_NARRATIVE_v8.md"),
}
FORBIDDEN = (
    re.compile("Family" + r" B", re.IGNORECASE),
    re.compile("mc" + "_nn", re.IGNORECASE),
    re.compile("RAP" + "TOR", re.IGNORECASE),
    re.compile("registered" + r"[- ]controller", re.IGNORECASE),
    re.compile("direct" + r"[- ]actuator", re.IGNORECASE),
    re.compile("controller" + r"[- ]graph replacement", re.IGNORECASE),
    re.compile("Aero" + "stack2", re.IGNORECASE),
    re.compile("Native" + r" Adapter", re.IGNORECASE),
    re.compile(r"\bM-" + r"FINAL\b"),
    re.compile(r"\bP" + r"0\b"),
    re.compile(r"\bP" + r"2\b"),
    re.compile(r"\bP" + r"3\b"),
    re.compile(r"\bP" + r"5\b"),
    re.compile(r"\bN" + r"1\b"),
    re.compile(r"\bC" + r"1\b"),
    re.compile(r"\bR" + r"1\b"),
    re.compile(r"\bW" + r"1\b"),
    re.compile(r"\bB" + r"1\b"),
    re.compile("Issue" + r" #162", re.IGNORECASE),
    re.compile("Route Oracle" + r" 0\.3", re.IGNORECASE),
    re.compile("200" + r"[- ]evaluation", re.IGNORECASE),
    re.compile("readiness" + r" amendment", re.IGNORECASE),
    re.compile("activation" + r" rereview", re.IGNORECASE),
    re.compile("old" + r" campaign", re.IGNORECASE),
    re.compile(r"\bfuzz" + r"er\b", re.IGNORECASE),
    re.compile(r"\barch" + r"ive\b", re.IGNORECASE),
    re.compile(r"\bback" + r"up\b", re.IGNORECASE),
    re.compile(r"\bdepre" + r"cated\b", re.IGNORECASE),
    re.compile(r"\bobso" + r"lete\b", re.IGNORECASE),
)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class ValidationError(RuntimeError):
    """Repository content is inconsistent with the current scope."""


def repository_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not any(part in IGNORED_ROOTS for part in path.relative_to(ROOT).parts)
    )


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON: {path.relative_to(ROOT)}: {exc}") from exc


def check_layout(files: list[Path]) -> None:
    unexpected = sorted(path.name for path in ROOT.iterdir() if path.name not in ALLOWED_TOP and path.name not in IGNORED_ROOTS)
    if unexpected:
        raise ValidationError("unexpected top-level entries: " + ", ".join(unexpected))
    required = {
        "README.md",
        "AGENT.md",
        "config",
        "docs",
        "scripts",
        "data",
        "tests",
        "containers",
    }
    missing = sorted(name for name in required if not (ROOT / name).exists())
    if missing:
        raise ValidationError("required repository entries are missing: " + ", ".join(missing))
    large = [path for path in files if path.stat().st_size > 10 * 1024 * 1024]
    if large:
        raise ValidationError("files exceed 10 MiB: " + ", ".join(str(path.relative_to(ROOT)) for path in large))
    if (ROOT / "data/processed").exists():
        raise ValidationError("processed experiment data must not be retained")


def check_terms(files: list[Path]) -> None:
    failures: list[str] = []
    for path in files:
        if path.relative_to(ROOT) in TERM_SCAN_EXEMPT:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            lowered = line.lower()
            route_word = "leg" + "acy"
            if route_word in lowered and route_word + " offboard" not in lowered and route_word + "_offboard" not in lowered:
                failures.append(f"{path.relative_to(ROOT)}:{line_number}: disallowed retired-route reference")
            result_phrase = "historical" + " result"
            allowed_status = "Retained historical" + " results: 0"
            if result_phrase in lowered and line.strip() not in {allowed_status, "- " + allowed_status}:
                failures.append(f"{path.relative_to(ROOT)}:{line_number}: disallowed result reference")
            for pattern in FORBIDDEN:
                if pattern.search(line):
                    failures.append(f"{path.relative_to(ROOT)}:{line_number}: {pattern.pattern}")
    if failures:
        raise ValidationError("out-of-scope terms found:\n" + "\n".join(failures))


def check_markdown_links(files: list[Path]) -> None:
    failures: list[str] = []
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in MARKDOWN_LINK.finditer(line):
                target = match.group(1).strip().split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                resolved = (path.parent / target).resolve()
                if not resolved.exists() or ROOT not in (resolved, *resolved.parents):
                    failures.append(f"{path.relative_to(ROOT)}:{line_number}: {target}")
    if failures:
        raise ValidationError("broken local Markdown links:\n" + "\n".join(failures))


def check_json_and_schemas(files: list[Path]) -> None:
    for path in files:
        if path.suffix == ".json":
            load_json(path)
    for path in sorted((ROOT / "data/schemas").glob("*.schema.json")):
        schema = load_json(path)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise ValidationError(f"schema draft is not fixed: {path.relative_to(ROOT)}")
        if schema.get("type") != "object" or not isinstance(schema.get("required"), list):
            raise ValidationError(f"schema root contract is incomplete: {path.relative_to(ROOT)}")
    event_schema = load_json(ROOT / "data/schemas/route_event.schema.json")
    if set(event_schema["properties"]["kind"]["enum"]) != set(EVENT_KINDS):
        raise ValidationError("event schema and Python event kinds differ")
    if set(event_schema["$defs"]["route"]["enum"]) != set(ROUTES):
        raise ValidationError("event schema and Python route names differ")
    plan_schema = load_json(ROOT / "data/schemas/experiment_plan.schema.json")
    if set(plan_schema["$defs"]["route"]["enum"]) != set(ROUTES):
        raise ValidationError("plan schema and Python route names differ")
    load_plan(ROOT / "config/experiment.template.json", allow_template=True)
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        for path in sorted((ROOT / "data/schemas").glob("*.schema.json")):
            jsonschema.Draft202012Validator.check_schema(load_json(path))
        jsonschema.Draft202012Validator(plan_schema).validate(
            load_json(ROOT / "config/experiment.template.json")
        )


def check_semantic_state_schema() -> None:
    """The derived-state vocabulary must exist once, in Python and in schema."""

    schema = load_json(ROOT / "data/schemas/semantic_state.schema.json")
    expected = {
        "route": sorted(ROUTES),
        "route_family": sorted({"none", *ROUTE_FAMILIES.values()}),
        "lifecycle_phase": list(LIFECYCLE_PHASES),
        "freshness_state": list(FRESHNESS_STATES),
        "fault_class": list(FAULT_CLASSES),
        "motion_phase": list(MOTION_PHASES),
    }
    for name, values in expected.items():
        declared = schema["$defs"][name]["enum"]
        if sorted(declared) != sorted(values):
            raise ValidationError(
                f"semantic state schema and Python {name} values differ"
            )


def check_locks() -> None:
    dependencies = load_json(ROOT / "config/dependencies.lock.json")
    if dependencies.get("tooling_platform") != "linux/arm64":
        raise ValidationError("validation tooling platform is not locked to linux/arm64")
    for name, source in dependencies.get("sources", {}).items():
        if COMMIT.fullmatch(str(source.get("commit"))) is None:
            raise ValidationError(f"{name}: source commit is not exact")
        repository = str(source.get("repository"))
        if not repository.startswith("https://github.com/") or not repository.endswith(".git"):
            raise ValidationError(f"{name}: source repository is not an exact HTTPS Git URL")
    container = dependencies.get("validation_container", {})
    for field in ("base_index_digest", "base_platform_digest"):
        if DIGEST.fullmatch(str(container.get(field))) is None:
            raise ValidationError(f"container {field} is not an exact digest")
    patch_lock = load_json(ROOT / "config/patches.lock.json")
    source_names = set(dependencies["sources"])
    for record in patch_lock.get("patches", []):
        path = ROOT / record["path"]
        if record["source"] not in source_names or not path.is_file():
            raise ValidationError("patch lock references an unavailable source or file")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != record["sha256"]:
            raise ValidationError(f"patch digest differs: {record['path']}")
    for path in (ROOT / "containers").glob("**/*-packages.lock"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            separator = "==" if path.name == "python-packages.lock" else "="
            if separator not in line or line.startswith(separator) or line.endswith(separator):
                raise ValidationError(f"unversioned package in {path.relative_to(ROOT)}")


def check_imports() -> None:
    modules = []
    for path in sorted((ROOT / "scripts").rglob("*.py")):
        relative = path.relative_to(ROOT).with_suffix("")
        modules.append(".".join(relative.parts))
    for module in modules:
        importlib.import_module(module)


def check_readme_commands() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    required = (
        "./scripts/validation/validate_repo.sh",
        "./scripts/setup/prepare_sources.sh",
        "containers/family_a/Dockerfile",
        "python3 -m scripts.evaluator.evaluate_trace",
    )
    missing = [command for command in required if command not in text]
    if missing:
        raise ValidationError("README omits supported commands: " + ", ".join(missing))
    for path in (
        ROOT / "scripts/validation/validate_repo.sh",
        ROOT / "scripts/setup/prepare_sources.sh",
        ROOT / "containers/family_a/Dockerfile",
    ):
        if not path.is_file():
            raise ValidationError(f"README command target does not exist: {path.relative_to(ROOT)}")


def main() -> int:
    try:
        files = repository_files()
        check_layout(files)
        check_terms(files)
        check_markdown_links(files)
        check_json_and_schemas(files)
        check_semantic_state_schema()
        check_locks()
        check_imports()
        check_readme_commands()
    except (OSError, KeyError, TypeError, ValidationError, ValueError) as exc:
        print(f"VALIDATION FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"STATIC VALIDATION PASS ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
