#!/usr/bin/env python3
"""D2 Inf timeout diagnostics with process and DDS liveness probes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import m1_diff_runner
import m2b_state_profiles as profiles


REPO_ROOT = Path(__file__).resolve().parents[1]
SAFETY_CONFIG = REPO_ROOT / "config/m2b_safety_envelope_4x_high_twr.json"


def run_probe(cmd: list[str], *, cwd: Path, env: dict[str, str], output: Path, timeout_s: int = 8) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        text = proc.stdout
        rc = int(proc.returncode)
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        text = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        text += f"\nTIMEOUT after {timeout_s}s\n"
        rc = 124
        timed_out = True
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("$ " + " ".join(cmd) + "\n" + text, encoding="utf-8")
    return {"cmd": cmd, "returncode": rc, "timed_out": timed_out, "elapsed_wall_s": time.monotonic() - started, "output": str(output)}


def copy_latest_ulog(log_root: Path, output: Path) -> str | None:
    ulog = m1_diff_runner.latest_ulog(log_root)
    if ulog is None:
        return None
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ulog, output)
    return str(output)


def run_controller(
    *,
    theta: dict[str, Any],
    theta_path: Path,
    controller: str,
    docs_dir: Path,
    env: dict[str, str],
    run_timeout_s: int,
    task_wait_s: int,
    sim_speed_factor: float,
) -> dict[str, Any]:
    tag = theta["tag"]
    px4_dir = REPO_ROOT / "external/PX4-Autopilot"
    build_dir = px4_dir / "build/px4_sitl_raptor_sih"
    run_root = build_dir
    log_root = run_root / "log"
    docs_dir.mkdir(parents=True, exist_ok=True)

    console_log = docs_dir / f"m2b_1_diag_{tag}_{controller}_px4_console.log"
    agent_log = docs_dir / f"m2b_1_diag_{tag}_{controller}_agent.log"
    topics_log = docs_dir / f"m2b_1_diag_{tag}_{controller}_topics.log"
    task_log = docs_dir / f"m2b_1_diag_{tag}_{controller}_task.log"
    task_json = docs_dir / f"m2b_1_diag_{tag}_{controller}_task.json"
    copied_ulog = docs_dir / f"m2b_1_diag_{tag}_{controller}.ulg"

    for path in [console_log, agent_log, topics_log, task_log]:
        path.write_text("", encoding="utf-8")

    if not (build_dir / "bin/px4").exists():
        raise FileNotFoundError(f"PX4 binary missing: {build_dir / 'bin/px4'}")

    m1_diff_runner.write_logger_topics(run_root)
    boot_airframe = m1_diff_runner.prepare_run_airframe(REPO_ROOT, run_root, theta)
    (run_root / "raptor").mkdir(exist_ok=True)
    shutil.copy2(px4_dir / "src/modules/mc_raptor/blob/policy.tar", run_root / "raptor/policy.tar")
    if log_root.exists():
        shutil.rmtree(log_root)
    log_root.mkdir(parents=True, exist_ok=True)
    for param_file in ["parameters.bson", "parameters_backup.bson"]:
        try:
            (run_root / param_file).unlink()
        except FileNotFoundError:
            pass

    agent_bin = m1_diff_runner.find_agent(REPO_ROOT)
    px4_env = env.copy()
    px4_env.update(
        {
            "HEADLESS": "1",
            "PX4_SIMULATOR": "sihsim",
            "PX4_SIM_MODEL": theta.get("airframe", {}).get("model", "sihsim_x500_v2"),
            "PX4_SYS_AUTOSTART": str(theta.get("airframe", {}).get("sys_autostart", 10046)),
            "PX4_SIM_SPEED_FACTOR": str(sim_speed_factor),
        }
    )

    agent = None
    px4 = None
    task = None
    cmd_tmp = None
    ulog_path: str | None = None
    timeout_observed = False
    probes: dict[str, Any] = {}
    task_rc: int | None = None
    px4_rc: int | None = None
    error: str | None = None

    try:
        with agent_log.open("w", encoding="utf-8") as agent_handle:
            agent = subprocess.Popen(
                [str(agent_bin), "udp4", "-p", os.environ.get("AGENT_PORT", "8888")],
                cwd=str(REPO_ROOT),
                env=env,
                stdout=agent_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            time.sleep(2.0)

        cmd_tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
        cmd_tmp.write(m1_diff_runner.px4_command_script(theta, max(1.0, sim_speed_factor)))
        cmd_tmp.close()

        with console_log.open("w", encoding="utf-8") as console_handle, open(cmd_tmp.name, "r", encoding="utf-8") as stdin:
            console_handle.write(f"# M2b-1 Inf timeout diagnostic controller={controller} tag={tag}\n")
            console_handle.write(f"PX4_DIR={px4_dir}\n")
            console_handle.write(f"PX4_SIM_MODEL={px4_env['PX4_SIM_MODEL']}\n")
            console_handle.write(f"PX4_SYS_AUTOSTART={px4_env['PX4_SYS_AUTOSTART']}\n")
            console_handle.write(f"PX4_SIM_SPEED_FACTOR={px4_env['PX4_SIM_SPEED_FACTOR']}\n")
            console_handle.write(f"THETA={theta_path}\n")
            console_handle.write(f"BOOT_AIRFRAME={boot_airframe}\n")
            console_handle.write(f"BOOT_PX4_PARAMS={json.dumps(m1_diff_runner.boot_px4_params(theta), sort_keys=True)}\n\n")
            console_handle.flush()
            px4 = subprocess.Popen(
                ["timeout", str(run_timeout_s), "./bin/px4", "."],
                cwd=str(run_root),
                env=px4_env,
                stdin=stdin,
                stdout=console_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            if not m1_diff_runner.wait_for_dds_topics(REPO_ROOT, env, topics_log):
                raise RuntimeError(f"DDS topics did not appear for {controller}")

            with task_log.open("w", encoding="utf-8") as task_handle:
                task = subprocess.Popen(
                    [
                        sys.executable,
                        str(REPO_ROOT / "scripts/m1_offboard_task.py"),
                        "--theta",
                        str(theta_path),
                        "--controller",
                        controller,
                        "--result-json",
                        str(task_json),
                    ],
                    cwd=str(REPO_ROOT),
                    env=env,
                    stdout=task_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    task_rc = task.wait(timeout=task_wait_s)
                except subprocess.TimeoutExpired:
                    timeout_observed = True
                    probes["px4_poll_before_kill"] = px4.poll()
                    probes["task_poll_before_kill"] = task.poll()
                    probes["topic_list"] = run_probe(
                        ["ros2", "topic", "list"],
                        cwd=REPO_ROOT,
                        env=env,
                        output=docs_dir / f"m2b_1_diag_{tag}_{controller}_probe_topic_list.log",
                    )
                    for topic in [
                        "/fmu/out/vehicle_status_v4",
                        "/fmu/out/vehicle_local_position_v1",
                        "/fmu/out/vehicle_attitude",
                        "/fmu/out/raptor_status",
                    ]:
                        safe = topic.strip("/").replace("/", "_")
                        probes[f"echo_once_{safe}"] = run_probe(
                            ["ros2", "topic", "echo", "--once", topic],
                            cwd=REPO_ROOT,
                            env=env,
                            output=docs_dir / f"m2b_1_diag_{tag}_{controller}_probe_{safe}.log",
                            timeout_s=8,
                        )
                    error = "task_timeout"
                    m1_diff_runner.terminate_process(task)

            if task_rc is not None:
                console_handle.write(f"\n# task_rc={task_rc}\n")
                console_handle.flush()
                try:
                    px4_rc = px4.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    error = "px4_shutdown_timeout"
                    probes["px4_poll_after_task"] = px4.poll()
                    m1_diff_runner.terminate_process(px4)
            else:
                probes["px4_poll_after_task_timeout_probe"] = px4.poll()

        ulog_path = copy_latest_ulog(log_root, copied_ulog)
    finally:
        m1_diff_runner.terminate_process(task)
        m1_diff_runner.terminate_process(px4)
        m1_diff_runner.terminate_process(agent)
        if cmd_tmp is not None:
            try:
                Path(cmd_tmp.name).unlink()
            except FileNotFoundError:
                pass

    record = {
        "tag": tag,
        "controller": controller,
        "theta_path": str(theta_path),
        "docs_dir": str(docs_dir),
        "timeout_observed": timeout_observed,
        "task_returncode": task_rc,
        "px4_returncode": px4_rc,
        "error": error,
        "px4_alive_at_timeout": probes.get("px4_poll_before_kill") is None if timeout_observed else None,
        "console_log": str(console_log),
        "agent_log": str(agent_log),
        "task_log": str(task_log),
        "topics_log": str(topics_log),
        "task_json": str(task_json) if task_json.exists() else None,
        "ulog": ulog_path,
        "probes": probes,
    }
    return record


def build_theta(args: argparse.Namespace, channel: str, controller: str, run_id: str, index: int) -> dict[str, Any]:
    tag = f"{run_id}_{channel}_inf_{controller}"
    theta = profiles.base_state_theta(
        tag=tag,
        seed=args.seed + index,
        channel=channel,
        profile="inf",
        values=(0.0, 0.0, 0.0),
        twr=args.twr,
        sine_axis=args.axis,
        sine_amplitude_m=args.sine_amplitude_m,
        sine_frequency_hz=args.sine_frequency_hz,
        start_s=args.start_s,
        end_s=args.end_s,
        controller_switch_s=args.controller_switch_s,
        trajectory_start_s=args.trajectory_start_s,
        mission_end_s=args.mission_end_s,
        mitigation="not_relevant_inf_timeout_diagnostic",
    )
    theta.setdefault("m2b_1", {})["inf_timeout_diagnostic"] = True
    theta["sensor_perturbations"][0]["physical_credibility"] = (
        "Inf injection is an input-robustness probe for shared-state sanitation; "
        "this diagnostic records process and DDS liveness at timeout."
    )
    return theta


def write_summary(run_dir: Path, records: list[dict[str, Any]]) -> None:
    lines = [
        "# M2b-1 D2 Inf Timeout Diagnostic",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        "",
        "## records",
    ]
    for item in records:
        lines.append(
            f"- {item['channel']}/{item['controller']}: timeout={item.get('timeout_observed')} "
            f"px4_alive_at_timeout={item.get('px4_alive_at_timeout')} error={item.get('error')} ulog={item.get('ulog')}"
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> Path:
    run_id = args.run_id or datetime.now(timezone.utc).strftime("m2b_1_diag_d2_inf_%Y%m%dT%H%M%SZ")
    run_dir = (REPO_ROOT / "docs" / run_id).resolve()
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = m1_diff_runner.agent_env(REPO_ROOT)
    metadata = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "channels": args.channels,
        "controllers": args.controllers,
        "sim_speed_factor": args.sim_speed_factor,
        "start_s": args.start_s,
        "end_s": args.end_s,
        "mission_end_s": args.mission_end_s,
        "scope_note": "D2 only: Inf timeout root cause and RAPTOR-window isolation; not campaign.",
    }
    profiles.write_json(run_dir / "metadata.json", metadata)
    records: list[dict[str, Any]] = []
    index = 0
    for channel in args.channels:
        for controller in args.controllers:
            theta = build_theta(args, channel, controller, run_id, index)
            theta_path = theta_dir / f"{theta['tag']}.json"
            profiles.write_json(theta_path, theta)
            docs_dir = evals_dir / theta["tag"]
            if args.run:
                record = run_controller(
                    theta=theta,
                    theta_path=theta_path,
                    controller=controller,
                    docs_dir=docs_dir,
                    env=env,
                    run_timeout_s=args.run_timeout,
                    task_wait_s=args.task_wait,
                    sim_speed_factor=args.sim_speed_factor,
                )
            else:
                record = {"tag": theta["tag"], "controller": controller, "theta_path": str(theta_path), "ran": False}
            record.update({"channel": channel, "profile": "inf", "ran": bool(args.run)})
            records.append(record)
            profiles.append_jsonl(run_dir / "results.jsonl", record)
            print(json.dumps(record, sort_keys=True), flush=True)
            index += 1
    profiles.write_json(run_dir / "results.json", records)
    write_summary(run_dir, records)
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--channels", nargs="+", choices=["velocity", "attitude"], default=["velocity", "attitude"])
    parser.add_argument("--controllers", nargs="+", choices=["classical", "raptor"], default=["classical", "raptor"])
    parser.add_argument("--seed", type=int, default=20261100)
    parser.add_argument("--twr", type=float, default=1.743)
    parser.add_argument("--axis", choices=["x", "y", "z"], default="x")
    parser.add_argument("--sine-amplitude-m", type=float, default=0.15)
    parser.add_argument("--sine-frequency-hz", type=float, default=1.0)
    parser.add_argument("--controller-switch-s", type=float, default=18.0)
    parser.add_argument("--trajectory-start-s", type=float, default=22.0)
    parser.add_argument("--start-s", type=float, default=24.0)
    parser.add_argument("--end-s", type=float, default=24.5)
    parser.add_argument("--mission-end-s", type=float, default=38.0)
    parser.add_argument("--sim-speed-factor", type=float, default=4.0)
    parser.add_argument("--run-timeout", type=int, default=180)
    parser.add_argument("--task-wait", type=int, default=130)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    run_dir = run(args)
    print(f"M2B_1_D2_INF_DIAG_DIR={run_dir}")
    print(f"M2B_1_D2_INF_DIAG_SUMMARY={run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
