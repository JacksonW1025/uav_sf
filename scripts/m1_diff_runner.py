#!/usr/bin/env python3
"""Run one fixed M1 theta on classical and RAPTOR backends and compare."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


REQUIRED_LOGGER_TOPICS = [
    "raptor_status 0",
    "raptor_input 0",
    "trajectory_setpoint 0",
    "vehicle_local_position 0",
    "vehicle_angular_velocity 0",
    "vehicle_attitude 0",
    "vehicle_status 0",
    "actuator_motors 0",
    "actuator_outputs 0",
    "failure_detector_status 0",
]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run_checked(cmd: list[str], *, cwd: Path, log: Path | None = None, env: dict[str, str] | None = None) -> None:
    if log is None:
        subprocess.run(cmd, cwd=str(cwd), env=env, check=True)
        return
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(cmd)}\n")
        handle.flush()
        subprocess.run(cmd, cwd=str(cwd), env=env, stdout=handle, stderr=subprocess.STDOUT, check=True)


def terminate_process(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def find_agent(repo: Path) -> Path:
    explicit = os.environ.get("MICROXRCE_AGENT_BIN")
    if explicit:
        return Path(explicit)
    path = shutil.which("MicroXRCEAgent")
    if path:
        return Path(path)
    return repo / "external/Micro-XRCE-DDS-Agent/build/MicroXRCEAgent"


def agent_env(repo: Path) -> dict[str, str]:
    env = os.environ.copy()
    agent_dir = repo / "external/Micro-XRCE-DDS-Agent"
    libs = [
        agent_dir / "build",
        agent_dir / "build/temp_install/fastrtps-2.14/lib",
        agent_dir / "build/temp_install/fastcdr-2.2.0/lib",
        agent_dir / "build/temp_install/microxrcedds_client-2.4.3/lib",
        agent_dir / "build/temp_install/microcdr-2.0.1/lib",
    ]
    current = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = ":".join(str(p) for p in libs) + (":" + current if current else "")
    return env


def wait_for_dds_topics(repo: Path, env: dict[str, str], log: Path, timeout_s: float = 70.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            result = subprocess.run(
                ["ros2", "topic", "list"],
                cwd=str(repo),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=6,
            )
        except subprocess.TimeoutExpired:
            time.sleep(1.0)
            continue
        log.write_text(result.stdout, encoding="utf-8")
        if "/fmu/out/vehicle_status_v4" in result.stdout and "/fmu/out/vehicle_local_position_v1" in result.stdout:
            return True
        time.sleep(1.5)
    return False


def write_logger_topics(run_root: Path) -> None:
    logging_dir = run_root / "etc/logging"
    logging_dir.mkdir(parents=True, exist_ok=True)
    (logging_dir / "logger_topics.txt").write_text("\n".join(REQUIRED_LOGGER_TOPICS) + "\n", encoding="utf-8")


def px4_command_script(theta: dict[str, Any]) -> str:
    params = theta.get("px4_params", {})
    lines = [
        "sleep 4",
    ]
    for name, value in params.items():
        lines.append(f"param set {name} {value}")
    lines.append("mc_raptor start")
    intref = theta.get("raptor_internal_reference", {})
    lissajous = intref.get("lissajous") if isinstance(intref, dict) else None
    if lissajous:
        values = [
            lissajous["A"],
            lissajous["B"],
            lissajous.get("C", 0.0),
            lissajous["fa"],
            lissajous["fb"],
            lissajous.get("fc", 1.0),
            lissajous["duration"],
            lissajous["ramp"],
        ]
        lines.append("mc_raptor intref lissajous " + " ".join(str(value) for value in values))
    lines.extend(
        [
            "sleep 3",
            "mc_raptor status",
            "commander status",
            "commander takeoff",
        ]
    )
    sleep_after_takeoff = int(float(theta["timing"]["mission_end_s"]) + 18.0)
    lines.extend(
        [
            f"sleep {sleep_after_takeoff}",
            "commander status",
            "listener vehicle_status 1",
            "listener vehicle_local_position 1",
            "listener vehicle_angular_velocity 1",
            "logger status",
            "shutdown",
        ]
    )
    return "\n".join(lines) + "\n"


def latest_ulog(log_root: Path) -> Path | None:
    files = sorted(log_root.glob("**/*.ulg"))
    return files[-1] if files else None


def run_one(
    repo: Path,
    theta_path: Path,
    theta: dict[str, Any],
    controller: str,
    docs: Path,
    env: dict[str, str],
    run_timeout_s: int,
) -> dict[str, Path]:
    tag = theta["tag"]
    px4_dir = repo / "external/PX4-Autopilot"
    build_dir = px4_dir / "build/px4_sitl_raptor_sih"
    run_root = build_dir
    log_root = run_root / "log"

    console_log = docs / f"m1_{tag}_{controller}_px4_console.log"
    agent_log = docs / f"m1_{tag}_{controller}_agent.log"
    topics_log = docs / f"m1_{tag}_{controller}_topics.log"
    task_log = docs / f"m1_{tag}_{controller}_task.log"
    task_json = docs / f"m1_{tag}_{controller}_task.json"
    copied_ulog = docs / f"m1_{tag}_{controller}.ulg"
    metrics_json = docs / f"m1_{tag}_{controller}_metrics.json"

    for path in [console_log, agent_log, topics_log, task_log]:
        path.write_text("", encoding="utf-8")

    if not (build_dir / "bin/px4").exists():
        raise FileNotFoundError(f"PX4 binary missing: {build_dir / 'bin/px4'}")

    write_logger_topics(run_root)
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

    agent_bin = find_agent(repo)
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

    agent = None
    px4 = None
    task = None
    cmd_tmp = None
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
        cmd_tmp.write(px4_command_script(theta))
        cmd_tmp.close()

        with console_log.open("w", encoding="utf-8") as console_handle, open(cmd_tmp.name, "r", encoding="utf-8") as stdin:
            console_handle.write(f"# M1 PX4 console controller={controller} tag={tag}\n")
            console_handle.write(f"PX4_DIR={px4_dir}\n")
            console_handle.write(f"PX4_SIM_MODEL={px4_env['PX4_SIM_MODEL']}\n")
            console_handle.write(f"PX4_SYS_AUTOSTART={px4_env['PX4_SYS_AUTOSTART']}\n")
            console_handle.write(f"PX4_SIM_SPEED_FACTOR={px4_env['PX4_SIM_SPEED_FACTOR']}\n")
            console_handle.write(f"THETA={theta_path}\n\n")
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

            if not wait_for_dds_topics(repo, env, topics_log):
                raise RuntimeError(f"DDS topics did not appear for {controller}")

            with task_log.open("w", encoding="utf-8") as task_handle:
                task = subprocess.Popen(
                    [
                        sys.executable,
                        str(repo / "scripts/m1_offboard_task.py"),
                        "--theta",
                        str(theta_path),
                        "--controller",
                        controller,
                        "--result-json",
                        str(task_json),
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
                    terminate_process(task)
                    raise RuntimeError(f"task node timed out for {controller}") from exc

            console_handle.write(f"\n# task_rc={task_rc}\n")
            console_handle.flush()
            try:
                px4_rc = px4.wait(timeout=40)
            except subprocess.TimeoutExpired:
                terminate_process(px4)
                raise RuntimeError(f"PX4 did not shut down after task for {controller}")
            console_handle.write(f"\n# px4_rc={px4_rc}\n")

        ulog = latest_ulog(log_root)
        if ulog is None:
            raise RuntimeError(f"No ULOG found under {log_root}")
        shutil.copy2(ulog, copied_ulog)

        run_checked(
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
                controller,
                "--output",
                str(metrics_json),
            ],
            cwd=repo,
            log=docs / f"m1_{tag}_{controller}_metrics.log",
            env=env,
        )
        return {
            "ulog": copied_ulog,
            "metrics": metrics_json,
            "task": task_json,
            "console": console_log,
            "agent": agent_log,
            "topics": topics_log,
        }
    finally:
        terminate_process(task)
        terminate_process(px4)
        terminate_process(agent)
        if cmd_tmp is not None:
            try:
                Path(cmd_tmp.name).unlink()
            except FileNotFoundError:
                pass


def write_summary(compare_json: Path, summary_md: Path) -> None:
    result = load_json(compare_json)
    classical = result["classical"]
    raptor = result["raptor"]
    div = result["divergence"]
    lines = [
        f"# M1 diff summary: {result['tag']}",
        "",
        f"quadrant: {result['quadrant']}",
        f"primary_bug: {str(result['primary_bug']).lower()}",
        "",
        "## safe",
        f"classical_safe: {str(classical.get('safe')).lower()} reasons={classical.get('safe_reasons')}",
        f"raptor_safe: {str(raptor.get('safe')).lower()} reasons={raptor.get('safe_reasons')}",
        "",
        "## key metrics",
        f"classical tracking max/rms/final: {classical.get('tracking_error_max_m')} / {classical.get('tracking_error_rms_m')} / {classical.get('final_error_m')}",
        f"raptor tracking max/rms/final: {raptor.get('tracking_error_max_m')} / {raptor.get('tracking_error_rms_m')} / {raptor.get('final_error_m')}",
        f"classical roll_pitch_max_deg: {classical.get('roll_pitch_max_deg')}",
        f"raptor roll_pitch_max_deg: {raptor.get('roll_pitch_max_deg')}",
        f"classical angular_rate_max_rad_s: {classical.get('angular_rate_max_rad_s')}",
        f"raptor angular_rate_max_rad_s: {raptor.get('angular_rate_max_rad_s')}",
        f"time_to_divergence_s: {div.get('time_to_divergence_s')}",
    ]
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theta", type=Path, default=repo_root() / "config/m1_anchor_step.json")
    parser.add_argument("--run-timeout", type=int, default=140)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    repo = repo_root()
    docs = repo / "docs"
    docs.mkdir(exist_ok=True)
    theta_path = args.theta.resolve()
    theta = load_json(theta_path)
    tag = theta["tag"]
    env = agent_env(repo)

    if not args.skip_build:
        build_env = env.copy()
        build_env["PX4_RAPTOR_SIH_BUILD_LOG"] = str(docs / f"m1_{tag}_px4_build.log")
        run_checked([str(repo / "scripts/build_px4_raptor_sih.sh")], cwd=repo, log=docs / f"m1_{tag}_build.log", env=build_env)
    else:
        run_checked([str(repo / "scripts/install_raptor_sih_board.sh")], cwd=repo, log=docs / f"m1_{tag}_build.log", env=env)
        run_checked([str(repo / "scripts/install_m1_sih_x500.sh")], cwd=repo, log=docs / f"m1_{tag}_build.log", env=env)

    outputs = {}
    for controller in ["classical", "raptor"]:
        print(f"RUN_CONTROLLER={controller}", flush=True)
        outputs[controller] = run_one(repo, theta_path, theta, controller, docs, env, args.run_timeout)

    compare_json = docs / f"m1_diff_{tag}.json"
    run_checked(
        [
            sys.executable,
            str(repo / "scripts/m1_compare.py"),
            "--theta",
            str(theta_path),
            "--classical",
            str(outputs["classical"]["metrics"]),
            "--raptor",
            str(outputs["raptor"]["metrics"]),
            "--output",
            str(compare_json),
        ],
        cwd=repo,
        log=docs / f"m1_diff_{tag}.log",
        env=env,
    )
    write_summary(compare_json, docs / f"m1_diff_{tag}_summary.md")
    print(f"M1_DIFF_JSON={compare_json}")
    print(f"M1_DIFF_SUMMARY={docs / f'm1_diff_{tag}_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
