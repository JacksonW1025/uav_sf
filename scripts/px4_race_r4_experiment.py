#!/usr/bin/env python3
"""Round 4 deterministic gate and allocator-race experiment runner.

This runner intentionally reuses the FUZZ-1c theta/evidence code, but does not
call the original runner because that code hardcodes the default PX4 build tree.
Round 4 needs isolated build roots so rebuilt and patched binaries can be used
without overwriting campaign artifacts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
from pyulog import ULog

import fuzz1_activation_mcnn as fuzz1
import fuzz1b_locked_activation as f1b
import fuzz1c_severity_scan as fuzz1c
import m1_diff_runner as m1
import mcnn_gate3_position_error_probe as gate3
import px4_race_causality_round4 as r4attr


REPO_ROOT = Path(__file__).resolve().parents[1]
PAIR1_CASE = fuzz1c.SCAN_CASES[0]
PAIR4_CASE = fuzz1c.SCAN_CASES[2]

ORIGINAL_LOGS = {
    "pair1": {
        "ulog": REPO_ROOT
        / "runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/"
        / "route_a_addendum3_diag_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_s20262001/"
        / "mcnn_gate3_route_a_addendum3_diag_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_s20262001_mcnn.ulg",
        "task": REPO_ROOT
        / "runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/"
        / "route_a_addendum3_diag_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_s20262001/"
        / "mcnn_gate3_route_a_addendum3_diag_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_s20262001_mcnn_task.json",
    },
    "pair4": {
        "ulog": REPO_ROOT
        / "runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/"
        / "route_a_addendum3_diag_20260629_rp36_44_rate1p55_2p15_w3_r4_f038_s20261902/"
        / "mcnn_gate3_route_a_addendum3_diag_20260629_rp36_44_rate1p55_2p15_w3_r4_f038_s20261902_mcnn.ulg",
        "task": REPO_ROOT
        / "runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/"
        / "route_a_addendum3_diag_20260629_rp36_44_rate1p55_2p15_w3_r4_f038_s20261902/"
        / "mcnn_gate3_route_a_addendum3_diag_20260629_rp36_44_rate1p55_2p15_w3_r4_f038_s20261902_mcnn_task.json",
    },
}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(r4attr.as_py(payload), handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def copy_run_root(build_dir: Path, run_root_base: Path, name: str) -> Path:
    run_root = run_root_base / name
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(build_dir / "etc", run_root / "etc", symlinks=True)
    return run_root


def px4_command_script(theta: dict[str, Any], extra_params: dict[str, Any], sim_speed_factor: float) -> str:
    lines = ["sleep 4"]
    for name, value in theta.get("px4_params", {}).items():
        lines.append(m1.format_px4_param_command(name, value))
    for name, value in extra_params.items():
        lines.append(m1.format_px4_param_command(name, value))
    lines.extend(
        [
            "mc_nn_control start",
            "sleep 3",
            "mc_nn_control status",
            "commander status",
            "commander takeoff",
        ]
    )
    timing = theta["timing"]
    mission_end_s = float(timing["mission_end_s"])
    shutdown_margin_s = float(timing.get("px4_shutdown_margin_s", 8.0))
    shutdown_wall_slack_s = float(timing.get("px4_shutdown_wall_slack_s", 22.0))
    sleep_after_takeoff = int(math.ceil((mission_end_s + shutdown_margin_s) / sim_speed_factor + shutdown_wall_slack_s))
    lines.extend(
        [
            f"sleep {sleep_after_takeoff}",
            "commander status",
            "listener vehicle_status 1",
            "listener vehicle_local_position 1",
            "listener vehicle_angular_velocity 1",
            "mc_nn_control status",
            "logger status",
            "shutdown",
        ]
    )
    return "\n".join(lines) + "\n"


def analyze_ulog(ulog_path: Path, task_path: Path | None, theta: dict[str, Any] | None = None) -> dict[str, Any]:
    ulog = ULog(str(ulog_path))
    data = {(dataset.name, dataset.multi_id): dataset.data for dataset in ulog.data_list}
    interval = r4attr.first_nav23(data[("vehicle_status", 0)])
    if interval is None:
        return {"ulog": rel(ulog_path), "no_nav23": True}
    nav_start, nav_end = interval
    loss_reason, loss_us = r4attr.loss_time(data, nav_start, nav_end)
    actuator_ts, actuator_classes, _, selfcheck = r4attr.classify_mcnn_by_value(data, nav_start, nav_end)
    output_ts, output_classes = r4attr.align_outputs(data, actuator_ts, actuator_classes, nav_start, nav_end)

    severity: dict[str, Any] = {}
    exact_switch_state: dict[str, Any] = {}
    state_trigger: dict[str, Any] = {}
    if task_path is not None and task_path.exists() and theta is not None:
        task = load_json(task_path)
        switch_us, match = f1b.matched_switch_us_from_trigger(ulog, task.get("state_trigger_state"))
        if switch_us is None:
            switch_us = f1b.task_event_us(task, "post_switch_setpoint") or f1b.task_event_us(task, "state_trigger")
        state_trigger = {
            "fired": bool(task.get("state_trigger_fired")),
            "event": fuzz1c.task_event(task, "state_trigger"),
            "task_exit_code": task.get("exit_code"),
            "match": match,
        }
        if isinstance(switch_us, int):
            exact_switch_state = f1b.exact_switch_state(ulog, switch_us)
            evidence = fuzz1c.severity_evidence(ulog, {"console": Path("missing"), "ulog": ulog_path}, "mcnn", theta, task, switch_us)
            severity = fuzz1c.classify_severity(evidence)
            severity["evidence"] = evidence

    full_output = r4attr.count_frac(output_classes, "allocator_value_residual")
    full_actuator = r4attr.count_frac(actuator_classes, "allocator_value_residual")
    critical_mask = (output_ts >= nav_start) & (output_ts <= loss_us)
    critical_actuator_mask = (actuator_ts >= nav_start) & (actuator_ts <= loss_us)
    return {
        "ulog": rel(ulog_path),
        "task": rel(task_path) if task_path else None,
        "nav23_start_us": nav_start,
        "nav23_end_us": nav_end,
        "nav23_duration_s": (nav_end - nav_start) / 1e6,
        "loss_reason": loss_reason,
        "first_loss_us": loss_us,
        "loss_dt_s": (loss_us - nav_start) / 1e6,
        "severity": severity,
        "state_trigger": state_trigger,
        "exact_switch_state": exact_switch_state,
        "actuator_total_counts": r4attr.counts(actuator_classes),
        "output_total_counts": r4attr.counts(output_classes),
        "allocator_fraction_full_output": full_output,
        "allocator_fraction_full_actuator": full_actuator,
        "allocator_fraction_critical_output": r4attr.count_frac(output_classes, "allocator_value_residual", critical_mask),
        "allocator_fraction_critical_actuator": r4attr.count_frac(
            actuator_classes, "allocator_value_residual", critical_actuator_mask
        ),
        "mcnn_value_selfcheck": selfcheck,
        "actuator_rate_hz": len(actuator_ts) / ((nav_end - nav_start) / 1e6),
        "output_rate_hz": len(output_ts) / ((nav_end - nav_start) / 1e6),
    }


def run_mcnn(
    *,
    repo: Path,
    build_dir: Path,
    docs: Path,
    run_root_base: Path,
    theta: dict[str, Any],
    case_label: str,
    rep: int,
    arm: str,
    extra_params: dict[str, Any],
    env: dict[str, str],
    run_timeout_s: int,
    safety_config: Path,
) -> dict[str, Any]:
    tag = theta["tag"]
    run_dir = docs / "evals" / f"{case_label}_{arm}_rep{rep:02d}_{tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    theta_path = run_dir / f"{tag}.json"
    write_json(theta_path, theta)

    prefix = f"mcnn_gate3_{tag}_mcnn"
    console_log = run_dir / f"{prefix}_px4_console.log"
    agent_log = run_dir / f"{prefix}_agent.log"
    topics_log = run_dir / f"{prefix}_topics.log"
    task_log = run_dir / f"{prefix}_task.log"
    task_json = run_dir / f"{prefix}_task.json"
    copied_ulog = run_dir / f"{prefix}.ulg"
    metrics_json = run_dir / f"{prefix}_metrics.json"
    metrics_log = run_dir / f"{prefix}_metrics.log"

    for path in [console_log, agent_log, topics_log, task_log, metrics_log]:
        path.write_text("", encoding="utf-8")

    if not (build_dir / "bin/px4").exists():
        raise FileNotFoundError(f"PX4 binary missing: {build_dir / 'bin/px4'}")

    run_root = copy_run_root(build_dir, run_root_base, f"{case_label}_{arm}_rep{rep:02d}_px4_root")
    log_root = run_root / "log"
    gate3.write_logger_topics(run_root)
    boot_airframe = m1.prepare_run_airframe(repo, run_root, theta)
    log_root.mkdir(parents=True, exist_ok=True)
    for param_file in ["parameters.bson", "parameters_backup.bson"]:
        try:
            (run_root / param_file).unlink()
        except FileNotFoundError:
            pass

    agent_bin = m1.find_agent(repo)
    if not agent_bin.exists():
        raise FileNotFoundError(f"MicroXRCEAgent missing: {agent_bin}")

    px4_env = env.copy()
    px4_env.update(
        {
            "HEADLESS": "1",
            "PX4_SIMULATOR": "sihsim",
            "PX4_SIM_MODEL": theta.get("airframe", {}).get("model", "sihsim_x500_v2"),
            "PX4_SYS_AUTOSTART": str(theta.get("airframe", {}).get("sys_autostart", 10046)),
            "PX4_SIM_SPEED_FACTOR": os.environ.get("PX4_SIM_SPEED_FACTOR", env.get("PX4_SIM_SPEED_FACTOR", "1")),
        }
    )
    sim_speed_factor = max(1.0, float(px4_env["PX4_SIM_SPEED_FACTOR"]))

    agent = None
    px4 = None
    task = None
    cmd_tmp = None
    runner_meta: dict[str, Any] = {
        "run_root": rel(run_root),
        "build_dir": rel(build_dir),
        "boot_airframe": rel(boot_airframe) if boot_airframe else None,
        "extra_params": dict(extra_params),
        "timing_mode": env.get("M1_TIMING_MODE", "legacy"),
    }
    try:
        with agent_log.open("w", encoding="utf-8") as agent_handle:
            agent = subprocess.Popen(
                [str(agent_bin), "udp4", "-p", os.environ.get("AGENT_PORT", "8888")],
                cwd=str(repo),
                env=env,
                stdout=agent_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            time.sleep(2.0)

        cmd_tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
        cmd_tmp.write(px4_command_script(theta, extra_params, sim_speed_factor))
        cmd_tmp.close()

        with console_log.open("w", encoding="utf-8") as console_handle, open(cmd_tmp.name, "r", encoding="utf-8") as stdin:
            console_handle.write(f"# R4 PX4 console controller=mcnn tag={tag} arm={arm} rep={rep}\n")
            console_handle.write(f"PX4_DIR={repo / 'external/PX4-Autopilot'}\n")
            console_handle.write(f"PX4_BUILD_DIR={build_dir}\n")
            console_handle.write(f"PX4_RUN_ROOT={run_root}\n")
            console_handle.write(f"PX4_SIM_MODEL={px4_env['PX4_SIM_MODEL']}\n")
            console_handle.write(f"PX4_SYS_AUTOSTART={px4_env['PX4_SYS_AUTOSTART']}\n")
            console_handle.write(f"PX4_SIM_SPEED_FACTOR={px4_env['PX4_SIM_SPEED_FACTOR']}\n")
            console_handle.write(f"THETA={theta_path}\n")
            console_handle.write(f"BOOT_AIRFRAME={boot_airframe}\n")
            console_handle.write(f"EXTRA_PARAMS={json.dumps(extra_params, sort_keys=True)}\n\n")
            console_handle.flush()
            px4 = subprocess.Popen(
                ["timeout", str(run_timeout_s), str(build_dir / "bin/px4"), "."],
                cwd=str(run_root),
                env=px4_env,
                stdin=stdin,
                stdout=console_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            if not m1.wait_for_dds_topics(repo, env, topics_log):
                raise RuntimeError("DDS topics did not appear for mcnn")

            with task_log.open("w", encoding="utf-8") as task_handle:
                task = subprocess.Popen(
                    [
                        sys.executable,
                        str(repo / "scripts/m1_offboard_task.py"),
                        "--theta",
                        str(theta_path),
                        "--controller",
                        "mcnn",
                        "--result-json",
                        str(task_json),
                        "--timing-mode",
                        env.get("M1_TIMING_MODE", "legacy"),
                    ],
                    cwd=str(repo),
                    env=env,
                    stdout=task_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    task_rc = task.wait(timeout=max(90, run_timeout_s - 20))
                except subprocess.TimeoutExpired as exc:
                    m1.terminate_process(task)
                    raise RuntimeError("task node timed out for mcnn") from exc

            runner_meta["task_rc"] = int(task_rc)
            console_handle.write(f"\n# task_rc={task_rc}\n")
            console_handle.flush()
            if task_rc == 0:
                try:
                    px4_rc = px4.wait(timeout=45)
                except subprocess.TimeoutExpired as exc:
                    m1.terminate_process(px4)
                    raise RuntimeError("PX4 did not shut down after task") from exc
                runner_meta["px4_rc"] = int(px4_rc)
                console_handle.write(f"\n# px4_rc={px4_rc}\n")
            else:
                runner_meta["nonzero_task_exit"] = True
                m1.terminate_process(px4)

        ulog = m1.latest_ulog(log_root)
        if ulog is None:
            raise RuntimeError(f"No ULOG found under {log_root}")
        shutil.copy2(ulog, copied_ulog)
        runner_meta["ulog_copied"] = True

        if task_json.exists():
            try:
                m1.run_checked(
                    [
                        sys.executable,
                        str(repo / "scripts/m1_metrics.py"),
                        "--ulog",
                        str(copied_ulog),
                        "--theta",
                        str(theta_path),
                        "--task-json",
                        str(task_json),
                        "--controller",
                        "mcnn",
                        "--output",
                        str(metrics_json),
                        "--safety-config",
                        str(safety_config),
                    ],
                    cwd=repo,
                    log=metrics_log,
                    env=env,
                )
                runner_meta["metrics_rc"] = 0
            except subprocess.CalledProcessError as exc:
                runner_meta["metrics_rc"] = int(exc.returncode)
                runner_meta["metrics_error"] = repr(exc)

        analysis = analyze_ulog(copied_ulog, task_json, theta)
        record = {
            "case_label": case_label,
            "arm": arm,
            "rep": rep,
            "tag": tag,
            "theta": theta,
            "runner_meta": runner_meta,
            "outputs": {
                "ulog": rel(copied_ulog),
                "task": rel(task_json),
                "metrics": rel(metrics_json),
                "console": rel(console_log),
                "agent": rel(agent_log),
                "topics": rel(topics_log),
            },
            "analysis": analysis,
            "run_error": None,
        }
    except Exception as exc:
        record = {
            "case_label": case_label,
            "arm": arm,
            "rep": rep,
            "tag": tag,
            "theta": theta,
            "runner_meta": runner_meta,
            "outputs": {
                "console": rel(console_log),
                "agent": rel(agent_log),
                "topics": rel(topics_log),
                "task_log": rel(task_log),
            },
            "analysis": {},
            "run_error": repr(exc),
        }
    finally:
        m1.terminate_process(task)
        m1.terminate_process(px4)
        m1.terminate_process(agent)
        if cmd_tmp is not None:
            try:
                Path(cmd_tmp.name).unlink()
            except FileNotFoundError:
                pass

    write_json(run_dir / "r4_record.json", record)
    return record


def gate_theta(case_label: str) -> tuple[dict[str, Any], Path | None, dict[str, Any]]:
    if case_label == "pair1":
        theta = fuzz1c.theta_for_case("route_a_addendum3_diag_20260629", PAIR1_CASE, 20262001)
    elif case_label == "pair4":
        theta = fuzz1c.theta_for_case("route_a_addendum3_diag_20260629", PAIR4_CASE, 20261902)
    else:
        raise KeyError(case_label)
    original = ORIGINAL_LOGS[case_label]
    return theta, original["task"], analyze_ulog(original["ulog"], original["task"], theta)


def safe_theta(case_label: str) -> dict[str, Any]:
    if case_label == "safe_validity_e0000":
        return load_json(REPO_ROOT / "docs/validity_automation_real_20260627/theta/validity_automation_real_20260627_e0000.json")
    if case_label == "safe_baseline_s20261302":
        return gate3.baseline_theta("mcnn_gonogo_gate3_20260625", 20261302)
    raise KeyError(case_label)


def summarize_gate(records: list[dict[str, Any]], originals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_case: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_case.setdefault(record["case_label"], []).append(record)
    cases: dict[str, Any] = {}
    for case_label, case_records in by_case.items():
        original = originals[case_label]
        rows = []
        pass_flags = []
        for record in case_records:
            analysis = record.get("analysis", {})
            severity_value = analysis.get("severity", {}).get("severity")
            loss_dt = analysis.get("loss_dt_s")
            original_loss_dt = original.get("loss_dt_s")
            dt_delta_ms = None
            if isinstance(loss_dt, (int, float)) and isinstance(original_loss_dt, (int, float)):
                dt_delta_ms = 1000.0 * (float(loss_dt) - float(original_loss_dt))
            allocator_fraction = analysis.get("allocator_fraction_full_output", {}).get("fraction")
            original_allocator_fraction = original.get("allocator_fraction_full_output", {}).get("fraction")
            allocator_delta_pp = None
            if isinstance(allocator_fraction, (int, float)) and isinstance(original_allocator_fraction, (int, float)):
                allocator_delta_pp = 100.0 * (float(allocator_fraction) - float(original_allocator_fraction))
            ok = (
                record.get("run_error") is None
                and severity_value is not None
                and int(severity_value) >= 3
                and dt_delta_ms is not None
                and abs(dt_delta_ms) < 50.0
            )
            pass_flags.append(bool(ok))
            rows.append(
                {
                    "rep": record["rep"],
                    "run_error": record.get("run_error"),
                    "severity": severity_value,
                    "severity_label": analysis.get("severity", {}).get("severity_label"),
                    "loss_dt_s": loss_dt,
                    "loss_delta_ms": dt_delta_ms,
                    "allocator_fraction_full_output": allocator_fraction,
                    "allocator_delta_pp": allocator_delta_pp,
                    "output_counts": analysis.get("output_total_counts"),
                    "ulog": record.get("outputs", {}).get("ulog"),
                }
            )
        loss_values = [row["loss_dt_s"] for row in rows if isinstance(row["loss_dt_s"], (int, float))]
        cases[case_label] = {
            "original": {
                "loss_dt_s": original.get("loss_dt_s"),
                "severity": original.get("severity", {}).get("severity"),
                "allocator_fraction_full_output": original.get("allocator_fraction_full_output", {}).get("fraction"),
                "ulog": original.get("ulog"),
            },
            "runs": rows,
            "deterministic_loss_span_ms": (1000.0 * (max(loss_values) - min(loss_values))) if len(loss_values) >= 2 else None,
            "case_gate_pass": all(pass_flags) and len(pass_flags) == 3,
        }
    return {
        "gate_pass": all(case.get("case_gate_pass") for case in cases.values()) and set(cases) == {"pair1", "pair4"},
        "cases": cases,
    }


def run_gate(args: argparse.Namespace) -> int:
    repo = REPO_ROOT
    docs = args.docs_dir.resolve()
    docs.mkdir(parents=True, exist_ok=True)
    run_root_base = docs / "px4_roots"
    env = m1.agent_env(repo)
    records: list[dict[str, Any]] = []
    originals: dict[str, dict[str, Any]] = {}
    for case_label in ("pair4", "pair1"):
        theta, _, original = gate_theta(case_label)
        originals[case_label] = original
        for rep in range(1, args.repetitions + 1):
            print(f"R4_GATE case={case_label} rep={rep}", flush=True)
            records.append(
                run_mcnn(
                    repo=repo,
                    build_dir=args.build_dir.resolve(),
                    docs=docs,
                    run_root_base=run_root_base,
                    theta=theta,
                    case_label=case_label,
                    rep=rep,
                    arm="A",
                    extra_params={},
                    env=env,
                    run_timeout_s=args.run_timeout,
                    safety_config=args.safety_config.resolve(),
                )
            )
            write_json(docs / "gate_partial.json", {"records": records, "originals": originals})
    summary = {
        "phase": "p3_gate",
        "build_dir": rel(args.build_dir.resolve()),
        "repetitions": args.repetitions,
        "records": records,
        "originals": originals,
        "summary": summarize_gate(records, originals),
    }
    write_json(docs / "gate_results.json", summary)
    print(f"R4_GATE_RESULTS={docs / 'gate_results.json'}")
    print(f"R4_GATE_PASS={summary['summary']['gate_pass']}")
    return 0 if summary["summary"]["gate_pass"] else 2


def run_matrix(args: argparse.Namespace) -> int:
    repo = REPO_ROOT
    docs = args.docs_dir.resolve()
    docs.mkdir(parents=True, exist_ok=True)
    run_root_base = docs / "px4_roots"
    env = m1.agent_env(repo)
    cases = [
        ("pair1", gate_theta("pair1")[0]),
        ("pair4", gate_theta("pair4")[0]),
        ("safe_validity_e0000", safe_theta("safe_validity_e0000")),
        ("safe_baseline_s20261302", safe_theta("safe_baseline_s20261302")),
    ]
    records: list[dict[str, Any]] = []
    for case_label, theta in cases:
        for arm, ablate in (("A", 0), ("B", 1)):
            for rep in range(1, args.repetitions + 1):
                print(f"R4_MATRIX case={case_label} arm={arm} rep={rep} R4_ALLOC_ABL={ablate}", flush=True)
                records.append(
                    run_mcnn(
                        repo=repo,
                        build_dir=args.build_dir.resolve(),
                        docs=docs,
                        run_root_base=run_root_base,
                        theta=theta,
                        case_label=case_label,
                        rep=rep,
                        arm=arm,
                        extra_params={"R4_ALLOC_ABL": ablate},
                        env=env,
                        run_timeout_s=args.run_timeout,
                        safety_config=args.safety_config.resolve(),
                    )
                )
                write_json(docs / "matrix_partial.json", {"records": records})
    summary = {
        "phase": "p3_matrix",
        "build_dir": rel(args.build_dir.resolve()),
        "repetitions": args.repetitions,
        "records": records,
    }
    write_json(docs / "matrix_results.json", summary)
    print(f"R4_MATRIX_RESULTS={docs / 'matrix_results.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["gate", "matrix"], required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--docs-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--run-timeout", type=int, default=190)
    parser.add_argument("--safety-config", type=Path, default=REPO_ROOT / "config/m2_safety_envelope.json")
    args = parser.parse_args()
    if args.phase == "gate":
        return run_gate(args)
    return run_matrix(args)


if __name__ == "__main__":
    raise SystemExit(main())
