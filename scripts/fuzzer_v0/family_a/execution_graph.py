#!/usr/bin/env python3
"""Validate and execute the six-slot Family A component graph with fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
READINESS = ROOT / "experiments/fuzzer_v0/family_a/full_readiness"
GRAPH_PATH = READINESS / "slot_execution_graph.yaml"
COMPONENT_PATH = READINESS / "component_manifest.yaml"
EXPECTED_NODES = (
    "authorization_identity_verification",
    "prelaunch_registration_verification",
    "container_identity_verification",
    "process_port_preflight",
    "route_collector_start",
    "writer_controller_collector_start",
    "clock_collector_start",
    "freshness_collector_start",
    "successor_collector_start",
    "linearization_collector_start",
    "safety_supervisor_start",
    "supervisor_ready_acknowledgement",
    "scenario_start",
    "live_supervision",
    "scenario_terminal",
    "collector_shutdown",
    "artifact_flush",
    "route_oracle",
    "freshness_oracle",
    "successor_oracle",
    "linearization_oracle",
    "cleanup_audit",
    "evidence_gate",
    "classification",
    "append_only_closure",
    "compact_evidence_generation",
)
COMPARISON_COMPONENTS = {
    "strategy_official_sequence",
    "strategy_bounded_random",
    "strategy_state_aware",
}


class GraphError(RuntimeError):
    """The formal graph is incomplete, misordered, or failed."""


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GraphError(f"{path}: expected a mapping")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_graph(
    graph_path: Path = GRAPH_PATH, component_path: Path = COMPONENT_PATH
) -> dict[str, Any]:
    graph = _load(graph_path)
    manifest = _load(component_path)
    components = manifest.get("components")
    pipeline = graph.get("pipeline")
    slots = graph.get("slots")
    if not isinstance(components, list) or not isinstance(pipeline, list):
        raise GraphError("component manifest and pipeline lists are required")
    if not isinstance(slots, list) or len(slots) != 6:
        raise GraphError("exactly six graph slots are required")
    component_map = {item["component_id"]: item for item in components}
    if len(component_map) != len(components):
        raise GraphError("component IDs must be unique")
    required_component_fields = {
        "component_id",
        "role",
        "source_path",
        "sha256",
        "module_or_command",
        "build_target",
        "input_contract",
        "output_contract",
        "timeout_s",
        "failure_classification",
    }
    for component_id, component in component_map.items():
        if not required_component_fields.issubset(component):
            raise GraphError(f"component contract is incomplete: {component_id}")
        source = ROOT / str(component["source_path"])
        if not source.is_file():
            raise GraphError(f"component source is missing: {component_id}")
        if sha256(source) != component["sha256"]:
            raise GraphError(f"component source identity mismatch: {component_id}")
        if int(component["timeout_s"]) <= 0:
            raise GraphError(f"component timeout is invalid: {component_id}")
    node_ids = tuple(item.get("node_id") for item in pipeline)
    if node_ids != EXPECTED_NODES:
        raise GraphError("pipeline nodes are missing or out of order")
    for index, node in enumerate(pipeline):
        if node.get("order") != index:
            raise GraphError(f"node order mismatch: {node.get('node_id')}")
        if node.get("timeout_s", 0) <= 0:
            raise GraphError(f"node timeout is invalid: {node.get('node_id')}")
        if not node.get("output"):
            raise GraphError(f"node output is missing: {node.get('node_id')}")
        inputs = node.get("input_from", [])
        if not isinstance(inputs, list):
            raise GraphError(f"node inputs are invalid: {node.get('node_id')}")
        prior = set(node_ids[:index])
        if any(item not in prior for item in inputs):
            raise GraphError(f"node consumes a missing or future output: {node['node_id']}")
        component_source = str(node.get("component_source", ""))
        if not component_source.startswith("binding:") and component_source not in component_map:
            raise GraphError(f"node component source is unknown: {node['node_id']}")

    expected_slot_ids = [f"V0P-S{number}" for number in range(1, 7)]
    if [slot.get("slot_id") for slot in slots] != expected_slot_ids:
        raise GraphError("slot order differs from V0P-S1..V0P-S6")
    for slot in slots:
        bindings = slot.get("bindings")
        applicability = slot.get("node_applicability")
        if not isinstance(bindings, dict) or not isinstance(applicability, dict):
            raise GraphError(f"{slot['slot_id']}: bindings/applicability missing")
        required_binding_fields = {
            "scenario",
            "adapters",
            "live_telemetry_collector",
            "route_collector",
            "writer_controller_collector",
            "clock_collector",
            "freshness_collector",
            "successor_collector",
            "linearization_collector",
            "route_oracle",
            "freshness_oracle",
            "successor_oracle",
            "linearization_oracle",
            "evidence_gate",
            "safety_supervisor",
            "cleanup",
            "compact_evidence",
            "accounting",
        }
        if set(bindings) != required_binding_fields:
            raise GraphError(f"{slot['slot_id']}: binding fields differ from contract")
        for node in pipeline:
            component_source = str(node["component_source"])
            if component_source.startswith("binding:"):
                binding = component_source.split(":", 1)[1]
                if binding not in bindings:
                    raise GraphError(
                        f"{slot['slot_id']}:{node['node_id']}: binding source is missing"
                    )
        component_ids: list[str] = []
        for value in bindings.values():
            component_ids.extend(value if isinstance(value, list) else [value])
        unknown = set(component_ids) - set(component_map)
        if unknown:
            raise GraphError(f"{slot['slot_id']}: unknown components: {sorted(unknown)}")
        if set(component_ids) & COMPARISON_COMPONENTS:
            raise GraphError(f"{slot['slot_id']}: comparison component is reachable")
        if set(applicability) != set(EXPECTED_NODES):
            raise GraphError(f"{slot['slot_id']}: node applicability is incomplete")
        if applicability["route_oracle"] != "REQUIRED":
            raise GraphError(f"{slot['slot_id']}: Route Oracle must be required")
        for node_id, status in applicability.items():
            if status not in {"REQUIRED", "NOT_APPLICABLE"}:
                raise GraphError(f"{slot['slot_id']}:{node_id}: invalid applicability")
    return {
        "status": "PASS",
        "slot_count": 6,
        "node_count_per_slot": len(EXPECTED_NODES),
        "comparison_reachable": False,
    }


def execute_fixture(
    *,
    slot_id: str,
    root: Path,
    fail_node: str | None = None,
    graph_path: Path = GRAPH_PATH,
    component_path: Path = COMPONENT_PATH,
) -> dict[str, Any]:
    validate_graph(graph_path, component_path)
    graph = _load(graph_path)
    slot = next((item for item in graph["slots"] if item["slot_id"] == slot_id), None)
    if slot is None:
        raise GraphError(f"unknown slot: {slot_id}")
    outputs: dict[str, Path] = {}
    invoked: list[str] = []
    not_applicable: list[str] = []
    records: list[dict[str, Any]] = []
    for node in graph["pipeline"]:
        node_id = node["node_id"]
        output = root / str(node["output"]).format(
            slot_id=slot_id, attempt_id=f"FIXTURE-{slot_id}"
        )
        inputs = [outputs[item] for item in node["input_from"]]
        if slot["node_applicability"][node_id] == "NOT_APPLICABLE":
            output.parent.mkdir(parents=True, exist_ok=True)
            marker = {
                "schema_version": "1.0",
                "node_id": node_id,
                "status": "NOT_APPLICABLE",
                "consumed": [
                    {"path": str(path), "sha256": sha256(path)} for path in inputs
                ],
                "runtime_started": False,
            }
            output.write_text(
                json.dumps(marker, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            not_applicable.append(node_id)
            process_code = 0
        else:
            command = [
                sys.executable,
                str(ROOT / "scripts/fuzzer_v0/family_a/mock_component.py"),
                "--node-id",
                node_id,
                "--output",
                str(output),
            ]
            for path in inputs:
                command.extend(["--input", str(path)])
            if node_id == fail_node:
                command.append("--fail")
            process = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=float(node["timeout_s"]),
            )
            process_code = process.returncode
            invoked.append(node_id)
            if process.returncode:
                raise GraphError(
                    f"fixture node failed: {node_id}: "
                    f"{(process.stdout + process.stderr).strip()}"
                )
        if not output.is_file():
            raise GraphError(f"fixture node did not produce output: {node_id}")
        outputs[node_id] = output
        records.append(
            {
                "node_id": node_id,
                "applicability": slot["node_applicability"][node_id],
                "input_count": len(inputs),
                "output": str(output),
                "exit_code": process_code,
            }
        )
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "slot_id": slot_id,
        "invoked_required_nodes": invoked,
        "not_applicable_nodes": not_applicable,
        "records": records,
        "runtime_started": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    fixture = sub.add_parser("fixture")
    fixture.add_argument("--slot-id", required=True)
    fixture.add_argument("--root", type=Path, required=True)
    fixture.add_argument("--fail-node")
    args = parser.parse_args()
    try:
        result = (
            validate_graph()
            if args.command == "validate"
            else execute_fixture(
                slot_id=args.slot_id,
                root=args.root,
                fail_node=args.fail_node,
            )
        )
    except (GraphError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
