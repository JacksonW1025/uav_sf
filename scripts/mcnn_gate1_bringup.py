#!/usr/bin/env python3
"""Run the GATE-1 mc_nn_control existence bring-up once."""

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
from pathlib import Path
from typing import Any

import m1_diff_runner as m1


LOGGER_TOPICS = [
    "neural_control 0",
    "trajectory_setpoint 0",
    "vehicle_local_position 0",
    "vehicle_local_position_groundtruth 0",
    "vehicle_angular_velocity 0",
    "vehicle_angular_velocity_groundtruth 0",
    "vehicle_attitude 0",
    "vehicle_attitude_groundtruth 0",
    "vehicle_status 0",
    "estimator_status 0",
    "estimator_status_flags 0",
    "failsafe_flags 0",
    "actuator_motors 0",
    "actuator_outputs 0",
    "failure_detector_status 0",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def format_param(name: str, value: Any) -> str:
    return m1.format_px4_param_command(name, value)


def write_logger_topics(run_root: Path) -> None:
    logging_dir = run_root / "etc/logging"
    logging_dir.mkdir(parents=True, exist_ok=True)
    (logging_dir / "logger_topics.txt").write_text("\n".join(LOGGER_TOPICS) + "\n", encoding="utf-8")


def px4_command_script(theta: dict[str, Any], sim_speed_factor: float) -> str:
    lines = ["sleep 4"]
    for name, value in theta.get("px4_params", {}).items():
        lines.append(format_param(name, value))
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
    sleep_after_takeoff = int(math.ceil(mission_end_s + shutdown_margin_s + shutdown_wall_slack_s * sim_speed_factor))
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


def write_gate1_summary(summary_path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# mc_nn_control GO/NO-GO GATE-1",
        "",
        f"gate: {payload['gate']}",
        f"decision: {payload['decision']}",
        f"px4_sha: {payload['px4_sha']}",
        f"board: {payload['board']}",
        f"theta: {payload['theta']}",
        f"ulog: {payload.get('ulog')}",
        f"mode_id: {payload.get('mode_id')}",
        f"controller_safe: {payload.get('controller_safe')}",
        f"safe_reasons: {payload.get('safe_reasons')}",
        "",
        "## Evidence",
        f"- source module: {payload['source_module']}",
        f"- docs state the embedded network is trained for X500 V2: {payload['x500_network_doc']}",
        f"- enable flags: {payload['enable_flags']}",
        f"- build note: {payload.get('build_note')}",
        f"- switch path: {payload['switch_path']}",
        f"- console: {payload.get('console_log')}",
        f"- task json: {payload.get('task_json')}",
        f"- metrics json: {payload.get('metrics_json')}",
        "",
        "## Gate Contract",
        "Stopped at GATE-1. GATE-2 and GATE-3 were not run in this invocation.",
    ]
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theta", type=Path, default=repo_root() / "config/mcnn_gate1_hover.json")
    parser.add_argument("--docs-dir", type=Path, default=repo_root() / "docs/mcnn_gonogo_gate1_20260625")
    parser.add_argument("--run-timeout", type=int, default=150)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--safety-config", type=Path, default=repo_root() / "config/m2_safety_envelope.json")
    args = parser.parse_args()

    repo = repo_root()
    px4_dir = repo / "external/PX4-Autopilot"
    build_dir = px4_dir / "build/px4_sitl_mcnn_sih"
    run_root = build_dir
    log_root = run_root / "log"
    theta_path = args.theta.resolve()
    theta = load_json(theta_path)
    docs = args.docs_dir.resolve()
    docs.mkdir(parents=True, exist_ok=True)
    env = m1.agent_env(repo)

    if not args.skip_build:
        build_env = env.copy()
        build_env["PX4_MCNN_SIH_BUILD_LOG"] = str(docs / "px4_mcnn_sih_build.log")
        m1.run_checked([str(repo / "scripts/build_px4_mcnn_sih.sh")], cwd=repo, log=docs / "build.log", env=build_env)
    else:
        m1.run_checked([str(repo / "scripts/install_mcnn_sih_board.sh")], cwd=repo, log=docs / "build.log", env=env)
        m1.run_checked([str(repo / "scripts/install_m1_sih_x500.sh")], cwd=repo, log=docs / "build.log", env=env)

    if not (build_dir / "bin/px4").exists():
        raise FileNotFoundError(f"PX4 binary missing: {build_dir / 'bin/px4'}")

    write_logger_topics(run_root)
    boot_airframe = m1.prepare_run_airframe(repo, run_root, theta)
    if log_root.exists():
        shutil.rmtree(log_root)
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
            "PX4_SIM_SPEED_FACTOR": os.environ.get("PX4_SIM_SPEED_FACTOR", "1"),
        }
    )
    sim_speed_factor = max(1.0, float(px4_env["PX4_SIM_SPEED_FACTOR"]))

    console_log = docs / "mcnn_gate1_px4_console.log"
    agent_log = docs / "mcnn_gate1_agent.log"
    topics_log = docs / "mcnn_gate1_topics.log"
    task_log = docs / "mcnn_gate1_task.log"
    task_json = docs / "mcnn_gate1_task.json"
    metrics_json = docs / "mcnn_gate1_metrics.json"
    copied_ulog = docs / "mcnn_gate1_hover.ulg"

    agent = None
    px4 = None
    task = None
    cmd_tmp = None
    try:
        with agent_log.open("w", encoding="utf-8") as handle:
            agent = subprocess.Popen(
                [str(agent_bin), "udp4", "-p", os.environ.get("AGENT_PORT", "8888")],
                cwd=str(repo),
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            time.sleep(2.0)

        cmd_tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
        cmd_tmp.write(px4_command_script(theta, sim_speed_factor))
        cmd_tmp.close()

        with console_log.open("w", encoding="utf-8") as console_handle, open(cmd_tmp.name, "r", encoding="utf-8") as stdin:
            console_handle.write("# mc_nn_control GATE-1 PX4 console\n")
            console_handle.write(f"PX4_DIR={px4_dir}\n")
            console_handle.write(f"PX4_SHA={subprocess.check_output(['git', '-C', str(px4_dir), 'rev-parse', 'HEAD'], text=True).strip()}\n")
            console_handle.write(f"PX4_SIM_MODEL={px4_env['PX4_SIM_MODEL']}\n")
            console_handle.write(f"PX4_SYS_AUTOSTART={px4_env['PX4_SYS_AUTOSTART']}\n")
            console_handle.write(f"BOOT_AIRFRAME={boot_airframe}\n")
            console_handle.write(f"THETA={theta_path}\n\n")
            console_handle.flush()
            px4 = subprocess.Popen(
                ["timeout", str(args.run_timeout), "./bin/px4", "."],
                cwd=str(run_root),
                env=px4_env,
                stdin=stdin,
                stdout=console_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            if not m1.wait_for_dds_topics(repo, env, topics_log):
                raise RuntimeError("DDS topics did not appear")

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
                    ],
                    cwd=str(repo),
                    env=env,
                    stdout=task_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                task_rc = task.wait(timeout=max(90, args.run_timeout - 20))
            console_handle.write(f"\n# task_rc={task_rc}\n")
            console_handle.flush()
            try:
                px4_rc = px4.wait(timeout=45)
            except subprocess.TimeoutExpired as exc:
                m1.terminate_process(px4)
                raise RuntimeError("PX4 did not shut down after task") from exc
            console_handle.write(f"\n# px4_rc={px4_rc}\n")

        ulog = m1.latest_ulog(log_root)
        if ulog is None:
            raise RuntimeError(f"No ULOG found under {log_root}")
        shutil.copy2(ulog, copied_ulog)

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
                str(args.safety_config),
            ],
            cwd=repo,
            log=docs / "mcnn_gate1_metrics.log",
            env=env,
        )
    finally:
        m1.terminate_process(task)
        m1.terminate_process(px4)
        m1.terminate_process(agent)
        if cmd_tmp is not None:
            try:
                Path(cmd_tmp.name).unlink()
            except FileNotFoundError:
                pass

    task_result = load_json(task_json)
    metrics = load_json(metrics_json)
    mode_id = task_result.get("external_mode_id")
    payload = {
        "gate": "GATE-1",
        "decision": "PASS" if task_result.get("mode_confirmed") and metrics.get("safe") else "FAIL",
        "px4_sha": subprocess.check_output(["git", "-C", str(px4_dir), "rev-parse", "HEAD"], text=True).strip(),
        "board": "px4_sitl_mcnn_sih",
        "theta": str(theta_path),
        "ulog": str(copied_ulog),
        "mode_id": mode_id,
        "controller_safe": metrics.get("safe"),
        "safe_reasons": metrics.get("safe_reasons"),
        "source_module": "external/PX4-Autopilot/src/modules/mc_nn_control",
        "x500_network_doc": "external/PX4-Autopilot/docs/en/neural_networks/mc_neural_network_control.md",
        "enable_flags": "CONFIG_LIB_TFLM=y, CONFIG_MODULES_MC_NN_CONTROL=y",
        "build_note": "mcnn_sih also compiles mc_raptor/RLtools so the local M2b shim parameter definitions are generated; MC_RAPTOR_ENABLE remains false and RAPTOR is not started.",
        "switch_path": f"MAV_CMD_DO_SET_MODE main=4/sub={task_result.get('external_sub_mode')} -> nav_state {mode_id}",
        "console_log": str(console_log),
        "task_json": str(task_json),
        "metrics_json": str(metrics_json),
    }
    (docs / "gate1_result.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_gate1_summary(docs / "summary.md", payload)
    write_gate1_summary(repo / "docs/mcnn_gonogo.md", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["decision"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
