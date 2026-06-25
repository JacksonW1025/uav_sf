#!/usr/bin/env python3
"""Lightweight Gazebo plant-asymmetry probe for RAPTOR closeout."""

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
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import m1_diff_runner as m1


BASE_MOTOR_CONSTANT = 8.54858e-06


@dataclass(frozen=True)
class Case:
    tag: str
    kind: str
    value: float


DEFAULT_CASES = [
    Case("motor0_080", "motor", 0.80),
    Case("motor0_065", "motor", 0.65),
    Case("motor0_050", "motor", 0.50),
    Case("com_x_002", "com_x", 0.02),
    Case("com_x_004", "com_x", 0.04),
    Case("com_x_006", "com_x", 0.06),
]


def kill_stale_sim_processes() -> None:
    patterns = [
        "MicroXRCEAgent udp4 -p 8888",
        "gz sim",
        "/bin/px4",
        "px4_sitl_raptor gz_x500",
    ]
    for pattern in patterns:
        subprocess.run(["pkill", "-TERM", "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    for pattern in patterns:
        subprocess.run(["pkill", "-KILL", "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def parse_cases(case_text: str | None) -> list[Case]:
    if not case_text:
        return DEFAULT_CASES
    selected = {part.strip() for part in case_text.split(",") if part.strip()}
    known = {case.tag: case for case in DEFAULT_CASES}
    missing = sorted(selected - set(known))
    if missing:
        raise ValueError(f"unknown case(s): {', '.join(missing)}")
    return [known[tag] for tag in selected]


def base_theta(tag: str, case: Case) -> dict[str, Any]:
    return {
        "tag": tag,
        "description": f"RAPTOR closeout Gazebo plant asymmetry probe: {case.kind}={case.value}",
        "seed": 20260625,
        "airframe": {"sim": "gz", "model": "gz_x500", "sys_autostart": 4001},
        "timing": {
            "controller_switch_s": 16.0,
            "trajectory_start_s": 22.0,
            "mission_end_s": 42.0,
            "mode_command_repeat_s": 0.5,
            "mode_command_timeout_s": 8.0,
            "px4_shutdown_margin_s": 5.0,
            "px4_shutdown_wall_slack_s": 16.0,
        },
        "setpoint": {
            "rate_hz": 50.0,
            "hover_ned": [0.0, 0.0, -2.5],
            "yaw_rad": 0.0,
            "type": "sine",
            "sine": {"axis": "x", "amplitude_m": 1.0, "frequency_hz": 0.20},
            "step": {"delta_ned": [0.0, 0.0, 0.0]},
        },
        "px4_params": {
            "NAV_DLL_ACT": 0,
            "COM_DISARM_LAND": -1,
            "COM_OF_LOSS_T": 5.0,
            "COM_RC_IN_MODE": 4,
            "COM_RCL_EXCEPT": 8,
            "MC_RAPTOR_ENABLE": 1,
            "MC_RAPTOR_OFFB": 0,
            "MC_RAPTOR_INTREF": 0,
            "SYS_FAILURE_EN": 1,
            "CA_FAILURE_MODE": 1,
        },
        "environment": {"gazebo_model": "x500", "plant_case": case.__dict__},
        "faults": [],
        "sensor_perturbations": [],
        "safe_thresholds": {
            "tracking_error_max_m": 4.0,
            "tracking_error_rms_m": 2.0,
            "final_error_m": 1.5,
            "roll_pitch_max_deg": 75.0,
            "angular_rate_max_rad_s": 8.0,
            "motor_saturation_ratio_max": 0.99,
            "min_altitude_agl_m": 0.25,
        },
        "divergence_thresholds": {"position_divergence_m": 2.0},
    }


def first_text(parent: ET.Element, name: str) -> str:
    child = parent.find(name)
    if child is None or child.text is None:
        raise ValueError(f"missing <{name}> in {parent.tag}")
    return child.text.strip()


def write_xml(tree: ET.ElementTree, path: Path) -> None:
    ET.indent(tree, space="  ")
    tree.write(path, encoding="UTF-8", xml_declaration=True)


def apply_motor_case(x500_sdf: Path, factor: float, motor_number: int = 0) -> dict[str, Any]:
    tree = ET.parse(x500_sdf)
    root = tree.getroot()
    changed = False
    before = None
    after = BASE_MOTOR_CONSTANT * factor
    for plugin in root.findall("./model/plugin"):
        if first_text(plugin, "motorNumber") != str(motor_number):
            continue
        motor_constant = plugin.find("motorConstant")
        if motor_constant is None:
            raise ValueError(f"motor {motor_number} plugin missing motorConstant")
        before = float(motor_constant.text or "nan")
        motor_constant.text = f"{after:.12g}"
        changed = True
        break
    if not changed:
        raise ValueError(f"motor {motor_number} plugin not found in {x500_sdf}")
    write_xml(tree, x500_sdf)
    return {
        "type": "motor_constant",
        "motor_number": motor_number,
        "factor": factor,
        "before": before,
        "after": after,
        "sdf": str(x500_sdf),
    }


def apply_com_case(x500_base_sdf: Path, x_offset_m: float) -> dict[str, Any]:
    tree = ET.parse(x500_base_sdf)
    root = tree.getroot()
    inertial = root.find("./model/link[@name='base_link']/inertial")
    if inertial is None:
        raise ValueError(f"base_link inertial not found in {x500_base_sdf}")
    pose = inertial.find("pose")
    before = "0 0 0 0 0 0"
    if pose is None:
        pose = ET.Element("pose")
        inertial.insert(0, pose)
    elif pose.text:
        before = pose.text.strip()
    pose.text = f"{x_offset_m:.6g} 0 0 0 0 0"
    write_xml(tree, x500_base_sdf)
    return {
        "type": "base_link_inertial_pose",
        "x_offset_m": x_offset_m,
        "before": before,
        "after": pose.text,
        "sdf": str(x500_base_sdf),
    }


def apply_case(px4_dir: Path, case: Case) -> dict[str, Any]:
    x500_sdf = px4_dir / "Tools/simulation/gz/models/x500/model.sdf"
    x500_base_sdf = px4_dir / "Tools/simulation/gz/models/x500_base/model.sdf"
    if case.kind == "motor":
        return apply_motor_case(x500_sdf, case.value)
    if case.kind == "com_x":
        return apply_com_case(x500_base_sdf, case.value)
    raise ValueError(f"unsupported case kind {case.kind}")


def copy_model_evidence(px4_dir: Path, docs: Path, tag: str) -> None:
    evidence = docs / f"model_evidence_{tag}"
    evidence.mkdir(parents=True, exist_ok=True)
    shutil.copy2(px4_dir / "Tools/simulation/gz/models/x500/model.sdf", evidence / "x500_model.sdf")
    shutil.copy2(px4_dir / "Tools/simulation/gz/models/x500_base/model.sdf", evidence / "x500_base_model.sdf")


def latest_ulog(log_root: Path) -> Path | None:
    files = sorted(log_root.glob("**/*.ulg"), key=lambda path: path.stat().st_mtime)
    return files[-1] if files else None


def run_one_gz(
    repo: Path,
    theta_path: Path,
    theta: dict[str, Any],
    controller: str,
    docs: Path,
    env: dict[str, str],
    run_timeout_s: int,
    safety_config: Path | None,
    sim_speed_factor: float,
) -> dict[str, Path | int | None]:
    tag = theta["tag"]
    px4_dir = repo / "external/PX4-Autopilot"
    build_dir = px4_dir / "build/px4_sitl_raptor"
    run_root = build_dir / "rootfs"
    log_root = run_root / "log"

    console_log = docs / f"gz_{tag}_{controller}_px4_console.log"
    agent_log = docs / f"gz_{tag}_{controller}_agent.log"
    topics_log = docs / f"gz_{tag}_{controller}_topics.log"
    task_log = docs / f"gz_{tag}_{controller}_task.log"
    task_json = docs / f"gz_{tag}_{controller}_task.json"
    copied_ulog = docs / f"gz_{tag}_{controller}.ulg"
    metrics_json = docs / f"gz_{tag}_{controller}_metrics.json"

    for path in [console_log, agent_log, topics_log, task_log]:
        path.write_text("", encoding="utf-8")

    if not (build_dir / "bin/px4").exists():
        raise FileNotFoundError(f"PX4 binary missing: {build_dir / 'bin/px4'}")

    m1.write_logger_topics(run_root)
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

    agent_bin = m1.find_agent(repo)
    if not agent_bin.exists():
        raise FileNotFoundError(f"MicroXRCEAgent missing: {agent_bin}")

    px4_env = env.copy()
    px4_env.update(
        {
            "HEADLESS": "1",
            "PX4_SIM_SPEED_FACTOR": str(sim_speed_factor),
            "PX4_SIM_MODEL": "gz_x500",
        }
    )

    agent = None
    px4 = None
    task = None
    cmd_tmp = None
    task_rc: int | None = None
    px4_rc: int | None = None
    try:
        kill_stale_sim_processes()
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
        cmd_tmp.write(m1.px4_command_script(theta, max(1.0, sim_speed_factor)))
        cmd_tmp.close()

        with console_log.open("w", encoding="utf-8") as console_handle, open(cmd_tmp.name, "r", encoding="utf-8") as stdin:
            console_handle.write(f"# RAPTOR closeout Gazebo controller={controller} tag={tag}\n")
            console_handle.write(f"PX4_DIR={px4_dir}\n")
            console_handle.write(f"PX4_SIM_MODEL=gz_x500\n")
            console_handle.write(f"PX4_SIM_SPEED_FACTOR={sim_speed_factor}\n")
            console_handle.write(f"THETA={theta_path}\n\n")
            console_handle.flush()
            px4 = subprocess.Popen(
                ["timeout", str(run_timeout_s), "make", "px4_sitl_raptor", "gz_x500"],
                cwd=str(px4_dir),
                env=px4_env,
                stdin=stdin,
                stdout=console_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            if not m1.wait_for_dds_topics(repo, env, topics_log, timeout_s=90.0):
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
                    task_rc = task.wait(timeout=max(120, run_timeout_s - 30))
                except subprocess.TimeoutExpired as exc:
                    m1.terminate_process(task)
                    raise RuntimeError(f"task node timed out for {controller}") from exc

            console_handle.write(f"\n# task_rc={task_rc}\n")
            console_handle.flush()
            try:
                px4_rc = px4.wait(timeout=45)
            except subprocess.TimeoutExpired:
                console_handle.write("\n# px4_wait_timeout=1\n")
                m1.terminate_process(px4)
                px4_rc = 124
            console_handle.write(f"\n# px4_rc={px4_rc}\n")

        ulog = latest_ulog(log_root)
        if ulog is None:
            raise RuntimeError(f"No ULOG found under {log_root}")
        shutil.copy2(ulog, copied_ulog)

        metrics_cmd = [
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
        ]
        if safety_config is not None:
            metrics_cmd.extend(["--safety-config", str(safety_config)])
        m1.run_checked(metrics_cmd, cwd=repo, log=docs / f"gz_{tag}_{controller}_metrics.log", env=env)
        return {
            "ulog": copied_ulog,
            "metrics": metrics_json,
            "task": task_json,
            "console": console_log,
            "agent": agent_log,
            "topics": topics_log,
            "task_returncode": task_rc,
            "px4_returncode": px4_rc,
        }
    finally:
        m1.terminate_process(task)
        m1.terminate_process(px4)
        m1.terminate_process(agent)
        kill_stale_sim_processes()
        if cmd_tmp is not None:
            try:
                Path(cmd_tmp.name).unlink()
            except FileNotFoundError:
                pass


def summarize_record(compare: dict[str, Any], case: Case, plant_change: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "case": case.__dict__,
        "plant_change": plant_change,
        "tag": compare["tag"],
        "quadrant": compare["quadrant"],
        "primary_bug": compare["primary_bug"],
        "classical_safe": compare["classical"].get("safe"),
        "classical_safe_reasons": compare["classical"].get("safe_reasons"),
        "raptor_safe": compare["raptor"].get("safe"),
        "raptor_safe_reasons": compare["raptor"].get("safe_reasons"),
        "classical_tracking_error_max_m": compare["classical"].get("tracking_error_max_m"),
        "raptor_tracking_error_max_m": compare["raptor"].get("tracking_error_max_m"),
        "classical_roll_pitch_max_deg": compare["classical"].get("roll_pitch_max_deg"),
        "raptor_roll_pitch_max_deg": compare["raptor"].get("roll_pitch_max_deg"),
        "classical_angular_rate_max_rad_s": compare["classical"].get("angular_rate_max_rad_s"),
        "raptor_angular_rate_max_rad_s": compare["raptor"].get("angular_rate_max_rad_s"),
        "divergence_quality": compare["divergence"].get("quality"),
        "time_to_divergence_s": compare["divergence"].get("time_to_divergence_s"),
        "outputs": {
            controller: {key: str(value) if isinstance(value, Path) else value for key, value in paths.items()}
            for controller, paths in outputs.items()
        },
    }


def write_summary(docs: Path, records: list[dict[str, Any]]) -> None:
    lines = [
        "# RAPTOR closeout Gazebo plant asymmetry",
        "",
        "Each row is one modified Gazebo x500 plant flown by both classical and RAPTOR.",
        "",
        "| case | quadrant | primary_bug | classical safe/reasons | RAPTOR safe/reasons | track max C/R | roll max C/R | rate max C/R |",
        "|---|---|---:|---|---|---:|---:|---:|",
    ]
    for record in records:
        c_reasons = ",".join(record.get("classical_safe_reasons") or [])
        r_reasons = ",".join(record.get("raptor_safe_reasons") or [])
        lines.append(
            "| {case} | {quadrant} | {primary} | {csafe}/{creasons} | {rsafe}/{rreasons} | {ctrack:.3g}/{rtrack:.3g} | {croll:.3g}/{rroll:.3g} | {crate:.3g}/{rrate:.3g} |".format(
                case=record["case"]["tag"],
                quadrant=record["quadrant"],
                primary=str(record["primary_bug"]).lower(),
                csafe=str(record["classical_safe"]).lower(),
                creasons=c_reasons or "-",
                rsafe=str(record["raptor_safe"]).lower(),
                rreasons=r_reasons or "-",
                ctrack=record["classical_tracking_error_max_m"] or float("nan"),
                rtrack=record["raptor_tracking_error_max_m"] or float("nan"),
                croll=record["classical_roll_pitch_max_deg"] or float("nan"),
                rroll=record["raptor_roll_pitch_max_deg"] or float("nan"),
                crate=record["classical_angular_rate_max_rad_s"] or float("nan"),
                rrate=record["raptor_angular_rate_max_rad_s"] or float("nan"),
            )
        )
    (docs / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="raptor_closeout_gz_asym_20260625")
    parser.add_argument("--docs-root", type=Path, default=m1.repo_root() / "docs")
    parser.add_argument("--cases", help="comma-separated case tags; default runs all lightweight A cases")
    parser.add_argument("--run-timeout", type=int, default=140)
    parser.add_argument("--sim-speed-factor", type=float, default=1.0)
    parser.add_argument("--safety-config", type=Path, default=m1.repo_root() / "config/m2_safety_envelope.json")
    args = parser.parse_args()

    repo = m1.repo_root()
    px4_dir = repo / "external/PX4-Autopilot"
    docs = (args.docs_root / args.run_id).resolve()
    docs.mkdir(parents=True, exist_ok=True)
    env = m1.agent_env(repo)
    cases = parse_cases(args.cases)

    x500_sdf = px4_dir / "Tools/simulation/gz/models/x500/model.sdf"
    x500_base_sdf = px4_dir / "Tools/simulation/gz/models/x500_base/model.sdf"
    original_x500 = x500_sdf.read_text(encoding="utf-8")
    original_x500_base = x500_base_sdf.read_text(encoding="utf-8")
    (docs / "original_x500_model.sdf").write_text(original_x500, encoding="utf-8")
    (docs / "original_x500_base_model.sdf").write_text(original_x500_base, encoding="utf-8")

    records: list[dict[str, Any]] = []
    results_jsonl = docs / "results.jsonl"
    try:
        for index, case in enumerate(cases):
            tag = f"{args.run_id}_{case.tag}"
            print(f"RUN_CASE={case.tag}", flush=True)
            x500_sdf.write_text(original_x500, encoding="utf-8")
            x500_base_sdf.write_text(original_x500_base, encoding="utf-8")
            plant_change = apply_case(px4_dir, case)
            case_dir = docs / f"eval_{index:02d}_{case.tag}"
            case_dir.mkdir(parents=True, exist_ok=True)
            copy_model_evidence(px4_dir, case_dir, tag)
            theta = base_theta(tag, case)
            theta["plant_change"] = plant_change
            theta_path = case_dir / f"{tag}.json"
            theta_path.write_text(json.dumps(theta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            outputs: dict[str, Any] = {}
            for controller in ["classical", "raptor"]:
                print(f"RUN_CONTROLLER={controller} CASE={case.tag}", flush=True)
                outputs[controller] = run_one_gz(
                    repo,
                    theta_path,
                    theta,
                    controller,
                    case_dir,
                    env,
                    args.run_timeout,
                    args.safety_config,
                    args.sim_speed_factor,
                )

            compare_json = case_dir / f"gz_diff_{tag}.json"
            m1.run_checked(
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
                log=case_dir / f"gz_diff_{tag}.log",
                env=env,
            )
            m1.write_summary(compare_json, case_dir / f"gz_diff_{tag}_summary.md")
            compare = m1.load_json(compare_json)
            record = summarize_record(compare, case, plant_change, outputs)
            records.append(record)
            with results_jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            (docs / "results.json").write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            write_summary(docs, records)
    finally:
        x500_sdf.write_text(original_x500, encoding="utf-8")
        x500_base_sdf.write_text(original_x500_base, encoding="utf-8")
        kill_stale_sim_processes()

    print(f"RESULTS={docs / 'results.json'}")
    print(f"SUMMARY={docs / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
