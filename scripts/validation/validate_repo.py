#!/usr/bin/env python3
"""Validate the tracked checkout's V8 scope boundary.

Passing this validator means that the current tree contains only the retained
V8 evidence packages and the explicitly allowed partial infrastructure. It is
not a flight-readiness, method-completeness, or formal-execution gate.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.model.runtime_route import EVENT_KINDS, ROUTES


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
    "runtime",
    "scripts",
    "tests",
}
RETAINED_EXPERIMENTS = frozenset(
    {
        "concurrency_barrier_qualification",
        "main_strategy_comparison_thor_v1",
        "motivation_stage_a2_thor_remediation_v1",
        "motivation_stage_a2_thor_v1",
        "motivation_thor_remediation_v1",
        "motivation_thor_v1",
        "posthoc_finding_consequence_triage_v1",
        "posthoc_oracle_ablation_v1",
        "posthoc_physical_execution_validity_v1",
        "posthoc_threshold_sensitivity_v1",
        "stage_a2_runtime_qualification_v1",
    }
)
FORBIDDEN_ACTIVE_PATHS = (
    Path("patches"),
    Path("containers/family_a_runtime"),
    Path("scripts/analysis"),
    Path("scripts/evaluator"),
    Path("scripts/setup"),
    Path("config/experiment.template.json"),
    Path("config/patches.lock.json"),
    Path("data/schemas/experiment_plan.schema.json"),
    Path("data/schemas/evaluation_result.schema.json"),
    Path("experiments/main_process_exit_strategy_thor_v1"),
    Path("experiments/matched_differential_analyzer_v1"),
)
REQUIRED_DOCS = frozenset(
    {
        "CURRENT_STATUS.md",
        "EXPERIMENT_PLAN.md",
        "EXPERIMENT_PLAN.zh-CN.md",
        "METHOD.md",
        "NEW_NARRATIVE_v8.md",
        "RESEARCH_SCOPE.md",
        "ROUTE_MODEL.md",
        "THOR_MIGRATION_REPORT.md",
        "V8_REPOSITORY_AUDIT.md",
    }
)
ACTIVE_SCHEMAS = frozenset(
    {"attempt_event.schema.json", "route_event.schema.json", "README.md"}
)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
STEP_HEADING = re.compile(r"^## Step (\d+) — ", re.MULTILINE)
CHINESE_STEP_STATUS = re.compile(r"^\*\*状态：`([^`]+)`\*\*$", re.MULTILINE)
ENGLISH_STEP_STATUS = re.compile(r"^\*\*Status: `([^`]+)`\*\*$", re.MULTILINE)


class ValidationError(RuntimeError):
    """The checkout violates the agreed V8 boundary."""


def repository_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not any(
            part in IGNORED_ROOTS for part in path.relative_to(ROOT).parts
        )
    )


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"invalid JSON: {path.relative_to(ROOT)}: {exc}"
        ) from exc


def has_active_files(path: Path) -> bool:
    if path.is_file():
        return True
    return path.is_dir() and any(
        item.is_file()
        and not any(
            part in IGNORED_ROOTS for part in item.relative_to(ROOT).parts
        )
        for item in path.rglob("*")
    )


def check_layout(files: list[Path]) -> None:
    unexpected = sorted(
        path.name
        for path in ROOT.iterdir()
        if path.name not in ALLOWED_TOP and path.name not in IGNORED_ROOTS
        and has_active_files(path)
    )
    if unexpected:
        raise ValidationError(
            "unexpected top-level entries: " + ", ".join(unexpected)
        )
    required = {"README.md", "AGENT.md", "config", "docs", "scripts", "data", "tests"}
    missing = sorted(name for name in required if not (ROOT / name).exists())
    if missing:
        raise ValidationError(
            "required repository entries are missing: " + ", ".join(missing)
        )
    large = [path for path in files if path.stat().st_size > 10 * 1024 * 1024]
    if large:
        raise ValidationError(
            "files exceed 10 MiB: "
            + ", ".join(str(path.relative_to(ROOT)) for path in large)
        )
    if (ROOT / "data/processed").exists():
        raise ValidationError("processed experiment data must not be retained")


def check_v8_boundary() -> None:
    present_forbidden = [
        str(path)
        for path in FORBIDDEN_ACTIVE_PATHS
        if has_active_files(ROOT / path)
    ]
    if present_forbidden:
        raise ValidationError(
            "removed pre-V8 active paths reappeared: " + ", ".join(present_forbidden)
        )
    observed_experiments = {
        path.name
        for path in (ROOT / "experiments").iterdir()
        if path.is_dir() and has_active_files(path)
    }
    if observed_experiments != RETAINED_EXPERIMENTS:
        raise ValidationError(
            "experiment allowlist differs; added="
            + repr(sorted(observed_experiments - RETAINED_EXPERIMENTS))
            + ", missing="
            + repr(sorted(RETAINED_EXPERIMENTS - observed_experiments))
        )
    observed_docs = {
        path.name for path in (ROOT / "docs").iterdir() if path.is_file()
    }
    missing_docs = sorted(REQUIRED_DOCS - observed_docs)
    if missing_docs:
        raise ValidationError(
            "required V8 documents are missing: " + ", ".join(missing_docs)
        )
    observed_schemas = {
        path.name for path in (ROOT / "data/schemas").iterdir() if path.is_file()
    }
    if observed_schemas != ACTIVE_SCHEMAS:
        raise ValidationError(
            "active schema set differs from the Stage 0 boundary: "
            + repr(sorted(observed_schemas))
        )
    old_runners = sorted((ROOT / "scripts/runtime").glob("run_*.py"))
    if old_runners:
        raise ValidationError(
            "an execution runner exists before the V8 execution-contract gate: "
            + ", ".join(str(path.relative_to(ROOT)) for path in old_runners)
        )


def check_markdown_links(files: list[Path]) -> None:
    failures: list[str] = []
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            for match in MARKDOWN_LINK.finditer(line):
                target = match.group(1).strip().split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                resolved = (path.parent / target).resolve()
                if not resolved.exists() or ROOT not in (resolved, *resolved.parents):
                    failures.append(f"{path.relative_to(ROOT)}:{line_number}: {target}")
    if failures:
        raise ValidationError(
            "broken local Markdown links:\n" + "\n".join(failures)
        )


def check_json_and_schemas(files: list[Path]) -> None:
    for path in files:
        if path.suffix == ".json":
            load_json(path)
    for path in sorted((ROOT / "data/schemas").glob("*.schema.json")):
        schema = load_json(path)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise ValidationError(
                f"schema draft is not fixed: {path.relative_to(ROOT)}"
            )
        if schema.get("type") != "object" or not isinstance(schema.get("required"), list):
            raise ValidationError(
                f"schema root contract is incomplete: {path.relative_to(ROOT)}"
            )
    event_schema = load_json(ROOT / "data/schemas/route_event.schema.json")
    if set(event_schema["properties"]["kind"]["enum"]) != set(EVENT_KINDS):
        raise ValidationError("event schema and Python event kinds differ")
    if set(event_schema["$defs"]["route"]["enum"]) != set(ROUTES):
        raise ValidationError("event schema and Python route names differ")
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        for path in sorted((ROOT / "data/schemas").glob("*.schema.json")):
            jsonschema.Draft202012Validator.check_schema(load_json(path))


def check_locks() -> None:
    dependencies = load_json(ROOT / "config/dependencies.lock.json")
    if dependencies.get("tooling_platform") != "linux/arm64":
        raise ValidationError("validation tooling platform is not locked to linux/arm64")
    for name, source in dependencies.get("sources", {}).items():
        if COMMIT.fullmatch(str(source.get("commit"))) is None:
            raise ValidationError(f"{name}: source commit is not exact")
        repository = str(source.get("repository"))
        if not repository.startswith("https://github.com/") or not repository.endswith(".git"):
            raise ValidationError(
                f"{name}: source repository is not an exact HTTPS Git URL"
            )
    container = dependencies.get("validation_container", {})
    for field in ("base_index_digest", "base_platform_digest"):
        if DIGEST.fullmatch(str(container.get(field))) is None:
            raise ValidationError(f"container {field} is not an exact digest")
    for path in (ROOT / "containers").glob("**/*-packages.lock"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            separator = "==" if path.name == "python-packages.lock" else "="
            if separator not in line or line.startswith(separator) or line.endswith(separator):
                raise ValidationError(
                    f"unversioned package in {path.relative_to(ROOT)}"
                )


def check_plan_sync() -> None:
    chinese = (ROOT / "docs/EXPERIMENT_PLAN.zh-CN.md").read_text(encoding="utf-8")
    english = (ROOT / "docs/EXPERIMENT_PLAN.md").read_text(encoding="utf-8")
    chinese_steps = STEP_HEADING.findall(chinese)
    english_steps = STEP_HEADING.findall(english)
    expected_steps = [str(value) for value in range(19)]
    if chinese_steps != expected_steps or english_steps != expected_steps:
        raise ValidationError("Chinese and English plans must contain Steps 0 through 18")
    chinese_status = CHINESE_STEP_STATUS.findall(chinese)
    english_status = ENGLISH_STEP_STATUS.findall(english)
    if chinese_status != english_status or len(chinese_status) != len(expected_steps):
        raise ValidationError("Chinese and English per-step status values differ")
    if chinese_status.count("[>] NEXT") != 1:
        raise ValidationError("the experiment plan must have exactly one NEXT step")
    mirrored_markers = (
        ("**产物**", "**Deliverables:**"),
        ("**退出条件**", "**Exit:**"),
        ("**停止条件**", "**Stop:**"),
    )
    for chinese_marker, english_marker in mirrored_markers:
        if chinese.count(chinese_marker) != 19 or english.count(english_marker) != 19:
            raise ValidationError(
                "each synchronized plan step needs deliverables, exit, and stop rules"
            )


def check_imports() -> None:
    modules = []
    for path in sorted((ROOT / "scripts").rglob("*.py")):
        relative = path.relative_to(ROOT).with_suffix("")
        modules.append(".".join(relative.parts))
    for module in modules:
        importlib.import_module(module)


def check_readme_boundary() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    required = (
        "./scripts/validation/validate_repo.sh",
        "No flight or formal experiment entry point is active",
        "EXPERIMENT_PLAN.zh-CN.md",
        "V8_REPOSITORY_AUDIT.md",
    )
    missing = [value for value in required if value not in text]
    if missing:
        raise ValidationError(
            "README omits the V8 Stage 0 boundary: " + ", ".join(missing)
        )


def main() -> int:
    try:
        files = repository_files()
        check_layout(files)
        check_v8_boundary()
        check_markdown_links(files)
        check_json_and_schemas(files)
        check_locks()
        check_plan_sync()
        check_imports()
        check_readme_boundary()
    except (OSError, KeyError, TypeError, ValidationError, ValueError) as exc:
        print(f"VALIDATION FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"V8 BOUNDARY VALIDATION PASS ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
