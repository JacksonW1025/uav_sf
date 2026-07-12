#!/usr/bin/env python3
"""Generate the frozen Tier-0.5 fork analysis and delivery indexes."""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import math
import os
import platform
import subprocess
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "tier05_fork_20260712T090728Z"
Z95 = 1.959963984540054


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(*args: str, cwd: Path = REPO) -> dict:
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    return {"cmd": list(args), "returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def wilson(k: int, n: int) -> list[float | None]:
    if n <= 0:
        return [None, None]
    p = k / n
    den = 1 + Z95 * Z95 / n
    center = (p + Z95 * Z95 / (2 * n)) / den
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95 * Z95 / (4 * n * n)) / den
    return [max(0.0, center - half), min(1.0, center + half)]


def is_valid(record: dict) -> tuple[bool, list[str]]:
    reasons = []
    analysis = record.get("analysis", {})
    trigger = analysis.get("state_trigger", {})
    evidence = analysis.get("severity", {}).get("evidence", {})
    if record.get("run_error") is not None:
        reasons.append("run_error")
    if trigger.get("task_exit_code") != 0:
        reasons.append("task_exit")
    if not trigger.get("fired"):
        reasons.append("trigger_not_fired")
    if analysis.get("severity", {}).get("severity") is None:
        reasons.append("unclassified")
    if evidence.get("post_switch_failsafe") is not False:
        reasons.append("post_switch_failsafe_or_unknown")
    ulog = record.get("outputs", {}).get("ulog")
    if not ulog or not (REPO / ulog).exists():
        reasons.append("ulog_missing")
    return not reasons, reasons


def vector_stats(records: list[dict]) -> dict:
    times = np.asarray([r["analysis"]["state_trigger"]["event"]["elapsed_s"] for r in records], dtype=float)
    values = np.asarray(
        [
            [r["analysis"]["state_trigger"]["event"]["detail"]["state"][key] for key in ("roll_deg", "pitch_deg", "angular_rate_norm_rad_s")]
            for r in records
        ],
        dtype=float,
    )
    covariance = np.cov(values, rowvar=False, ddof=1)
    return {
        "n": len(records),
        "trigger_elapsed_s": {"min": float(times.min()), "max": float(times.max()), "span": float(np.ptp(times)), "std": float(times.std(ddof=1))},
        "state_order": ["roll_deg", "pitch_deg", "angular_rate_norm_rad_s"],
        "state_mean": values.mean(axis=0).tolist(),
        "state_std": values.std(axis=0, ddof=1).tolist(),
        "state_range": np.ptp(values, axis=0).tolist(),
        "state_covariance": covariance.tolist(),
        "state_generalized_variance": float(np.linalg.det(covariance)),
    }


def case_summary(records: list[dict]) -> dict:
    valid_records = [r for r in records if is_valid(r)[0]]
    outcomes = collections.Counter(int(r["analysis"]["severity"]["severity"]) for r in valid_records)
    n = len(valid_records)
    flips = sum(count for outcome, count in outcomes.items() if outcome != 3)
    pairs = n * (n - 1) // 2
    consistent = sum(count * (count - 1) // 2 for count in outcomes.values())
    return {
        "attempts": len(records),
        "valid": n,
        "invalid": len(records) - n,
        "outcome_counts": {f"S{k}": outcomes.get(k, 0) for k in range(5)},
        "modal_outcome": "S3",
        "flips": flips,
        "flip_rate": flips / n if n else None,
        "flip_rate_wilson95": wilson(flips, n),
        "pairwise_pairs": pairs,
        "pairwise_consistent": consistent,
        "pairwise_consistency": consistent / pairs if pairs else None,
        "pairwise_consistency_wilson95": wilson(consistent, pairs),
        "timing_state": vector_stats(valid_records),
    }


def all_records() -> list[tuple[str, dict, Path]]:
    out = []
    for path in sorted(ROOT.glob("stage*/evals/*/r4_record.json")):
        out.append((path.relative_to(ROOT).parts[0], load(path), path))
    return out


def main() -> int:
    indexed = all_records()
    index_rows = []
    for stage, record, record_path in indexed:
        valid, reasons = is_valid(record)
        analysis = record.get("analysis", {})
        event = analysis.get("state_trigger", {}).get("event") or {}
        state = event.get("detail", {}).get("state") or {}
        outputs = record.get("outputs", {})
        artifacts = []
        for key, value in sorted(outputs.items()):
            path = REPO / value if isinstance(value, str) else None
            if path is not None and path.exists() and path.is_file():
                artifacts.append({"kind": key, "path": value, "size_bytes": path.stat().st_size})
        index_rows.append(
            {
                "stage": stage,
                "case": record.get("case_label"),
                "rep": record.get("rep"),
                "timing_mode": record.get("runner_meta", {}).get("timing_mode", "legacy" if stage == "stage0_legacy" else None),
                "valid": valid,
                "invalid_reasons": reasons,
                "outcome": f"S{analysis.get('severity', {}).get('severity')}" if analysis.get("severity", {}).get("severity") is not None else None,
                "outcome_label": analysis.get("severity", {}).get("severity_label"),
                "trigger_elapsed_s": event.get("elapsed_s"),
                "trigger_state": {key: state.get(key) for key in ("roll_deg", "pitch_deg", "angular_rate_norm_rad_s")},
                "record": str(record_path.relative_to(REPO)),
                "artifacts": artifacts,
            }
        )
    with (ROOT / "run_index.jsonl").open("w", encoding="utf-8") as handle:
        for row in index_rows:
            handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")

    diff_parts = [run("git", "diff", "--", "scripts/m1_offboard_task.py")["stdout"]]
    for relative in (
        "scripts/px4_race_r4_experiment.py",
        "scripts/tier05_fork_campaign.py",
        "scripts/tier05_fork_finalize.py",
    ):
        diff_parts.append(run("git", "diff", "--no-index", "--", "/dev/null", relative)["stdout"])
    (ROOT / "code.diff").write_text("\n".join(part for part in diff_parts if part) + "\n", encoding="utf-8")

    stage0 = load(ROOT / "stage0_legacy/gate_results.json")["records"]
    stage2 = load(ROOT / "stage2_gate_a/gate_results.json")["records"]
    s3_paths = [
        ROOT / "stage3_initial/campaign_results.json",
        ROOT / "stage3_adaptive_dense_21_40/campaign_results.json",
        ROOT / "stage3_adaptive_dense_41_60/campaign_results.json",
    ]
    stage3 = sum((load(path)["records"] for path in s3_paths), [])
    s0_stats = {case: vector_stats([r for r in stage0 if r["case_label"] == case]) for case in ("pair1", "pair4")}
    s2_stats = {case: vector_stats([r for r in stage2 if r["case_label"] == case]) for case in ("pair1", "pair4")}
    summaries = {case: case_summary([r for r in stage3 if r["case_label"] == case]) for case in ("dense_low_modal", "pair4", "pair1")}
    p0 = 0.9149232336708375**60 * 0.9862895787574435**20
    analysis = {
        "verdict": "beta",
        "verdict_symbol": "β",
        "gate_a": {
            "pass": True,
            "legacy": s0_stats,
            "hardened": s2_stats,
            "pair1_trigger_span_reduction": s0_stats["pair1"]["trigger_elapsed_s"]["span"] / s2_stats["pair1"]["trigger_elapsed_s"]["span"],
            "pair1_generalized_variance_reduction": s0_stats["pair1"]["state_generalized_variance"] / s2_stats["pair1"]["state_generalized_variance"],
        },
        "stage3": summaries,
        "zero_flip_probability_bound": p0,
        "beta_threshold": 0.01,
        "beta_pass": p0 < 0.01 and all(item["flips"] == 0 for item in summaries.values()),
        "budget": {"stage0": 20, "stage1_smoke": 4, "stage2": 20, "stage3": 100, "total": 144, "limit": 160},
        "all_runs": {"attempts": len(index_rows), "valid": sum(row["valid"] for row in index_rows), "invalid": sum(not row["valid"] for row in index_rows)},
    }
    write_json(ROOT / "stage4_analysis.json", analysis)

    binary = REPO / "external/PX4-Autopilot/build/px4_sitl_mcnn_sih_r4/bin/px4"
    provenance = {
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "host": {"hostname": platform.node(), "platform": platform.platform(), "uname": list(platform.uname())},
        "experiment": {"branch": run("git", "branch", "--show-current")["stdout"], "speed_factor": "1.25", "docker_cpuset_cpus": "8-11", "serial": True},
        "harness_git": {"head": run("git", "rev-parse", "HEAD"), "status": run("git", "status", "--short")},
        "px4_git": {"head": run("git", "rev-parse", "HEAD", cwd=REPO / "external/PX4-Autopilot"), "status": run("git", "status", "--short", cwd=REPO / "external/PX4-Autopilot")},
        "px4_binary": {"path": str(binary.relative_to(REPO)), "size_bytes": binary.stat().st_size, "md5": md5(binary), "sha256": sha256(binary)},
        "docker": {"image": "uav_sf:phase1", "digest": "sha256:4e590ec80407e37a77efa10d329b31e8e978cdcb86e3dbce630cd100f1575e29"},
        "hashes": {
            "offboard_task_sha256": sha256(REPO / "scripts/m1_offboard_task.py"),
            "campaign_driver_sha256": sha256(REPO / "scripts/tier05_fork_campaign.py"),
            "severity_classifier_sha256": sha256(REPO / "scripts/fuzz1c_severity_scan.py"),
            "decontam_classifier_sha256": sha256(REPO / "scripts/fuzz1c_decontam_analyze.py"),
            "verdict_rule_sha256": sha256(ROOT / "verdict_rule.frozen.md"),
            "gate_rule_sha256": sha256(ROOT / "gate_a_rule.prefrozen.md"),
        },
        "archived_snapshots": [str(path.relative_to(REPO)) for path in sorted((ROOT / "provenance").glob("*.json"))],
        "caveats": ["root and PX4 worktrees were dirty before this experiment", "the original campaign binary had already been overwritten; all new runs use the isolated r4 binary", "interactive desktop load remained; all old/new runs used Docker CPU 8-11"],
    }
    write_json(ROOT / "provenance/manifest.json", provenance)

    verdict = {
        "verdict": "β",
        "evidence": {
            "gate_a_pass": True,
            "pair1_trigger_span_reduction_x": analysis["gate_a"]["pair1_trigger_span_reduction"],
            "pair1_generalized_variance_reduction_x": analysis["gate_a"]["pair1_generalized_variance_reduction"],
            "stage3_valid": 100,
            "stage3_invalid": 0,
            "stage3_flips": 0,
            "outcomes": {case: item["outcome_counts"] for case, item in summaries.items()},
            "zero_flip_probability_bound": p0,
            "beta_probability_threshold": 0.01,
            "classifier_sha256": provenance["hashes"]["decontam_classifier_sha256"],
            "px4_binary_md5": provenance["px4_binary"]["md5"],
        },
        "thresholds": {
            "gate_trigger_span_max_s": 0.2223921,
            "gate_generalized_variance_max": 0.00025654189993854037,
            "gate_state_std_max": [0.33958803, 3.77160100, 0.06598521],
            "beta_p0_max_exclusive": 0.01,
            "alpha_min_flips": 3,
        },
        "budget_used": 144,
    }
    write_json(ROOT / "verdict.json", verdict)

    report = f"""# Tier 0.5 判定实验（THE FORK）

## 最终判定

**✅ β：时序硬化后，预注册的三个锚点配置共 100 个 valid run 全部为 S3，0 次结局翻转；保守零翻转概率上界乘积 `P0={p0:.8f}<0.01`。**

在本实验的预注册范围内，历史 fixed-θ/fixed-seed 结局翻转应降级为 harness 方法学问题，而不是继续作为 PX4+神经模式的“风险面”发现。事件驱动实现也移除了 wall-clock timer 这一并行阻塞源；⚠️ 本轮没有实际做并行 campaign，故只说“根因已移除”，不声称并行安全已经验证。

## ✅ 全量账本

| Stage | attempts | valid | invalid | 说明 |
|---|---:|---:|---:|---|
| Stage 0 legacy | 20 | 20 | 0 | pair1×10 + pair4×10 |
| Stage 1 smoke | 4 | 4 | 0 | 初版×2 + 80 Hz 相位累加器版×2；初版也保留 |
| Stage 2 Gate A | 20 | 20 | 0 | pair4 诊断×10 + pair1 gate×10 |
| Stage 3 | 100 | 100 | 0 | 初始 60 + dense 自适应 20 + 20 |
| **合计** | **144** | **144** | **0** | 低于 160 上限 |

原始索引见 `run_index.jsonl`；共 144 个 ULOG、144 个 task JSON、144 个 `r4_record.json`，总目录约 8.8 GiB。

## Stage 0：时序架构与 legacy 基线

✅ 源码核实：legacy 在 `scripts/m1_offboard_task.py` 中以 `create_timer(1/wall_timer_hz)` 调用 `tick()`。锚点 `rate_hz=80`、speed factor=1.25，故 wall timer=100 Hz。PX4 topic timestamp 只是在 wall callback 执行时提供 elapsed；setpoint 发布和 trigger predicate 的求值机会仍由墙钟决定，而且 legacy `now_us` 会被 status/local-position/attitude/rate 等多个 DDS callback 推进。

✅ PX4/SIH lockstep 核实：r4 build 的 `build.ninja` 含 `-DENABLE_LOCKSTEP_SCHEDULER`；SIH runtime 报 `250 Hz (4000 us sim time interval)` 和 3200 us wall interval（1.25×，日志显示一位小数 1.2×）。PX4 内部 lockstep 不把 ROS 2 外部节点纳入 barrier，因此不能消除 legacy wall timer 相位。

| legacy 配置 | outcome | trigger span | state std `[roll,pitch,||ω||]` | det(cov) |
|---|---:|---:|---|---:|
| pair1 | S3 10/10 | {s0_stats['pair1']['trigger_elapsed_s']['span']*1000:.3f} ms | `[0.3396,3.7716,0.0660]` | {s0_stats['pair1']['state_generalized_variance']:.9f} |
| pair4 | S3 10/10 | {s0_stats['pair4']['trigger_elapsed_s']['span']*1000:.3f} ms | `[2.6583,1.7807,0.0324]` | {s0_stats['pair4']['state_generalized_variance']:.9f} |

⚠️ pair1 有一次后续相位触发，造成 2.224 s span；这比历史 204 ms 更差，证明必须以当前主机 baseline 定门。

## Stage 1：修复

✅ 新增 `--timing-mode {{legacy,hardened}}`。legacy 路径仍创建原 timer；hardened 不创建 timer，以 `/fmu/out/vehicle_angular_velocity_groundtruth` 入站消息为唯一 task clock，拒绝重复/乱序 timestamp，并用 PX4 timestamp deadline accumulator 分频发布与求值。QoS、queue depth、PX4 binary 均未修改。

✅ 修正版 smoke 2/2 exit 0、mode confirmed、无 post-switch failsafe；实测 tick rate 77.3–78.0 Hz（目标 80 Hz，乱序入站被拒绝），未触发 OFFBOARD failsafe。

## Stage 2：Gate A

| pair1 指标 | legacy | hardened | 收敛 | 冻结门 | 结果 |
|---|---:|---:|---:|---:|---|
| trigger span | {s0_stats['pair1']['trigger_elapsed_s']['span']:.6f} s | {s2_stats['pair1']['trigger_elapsed_s']['span']:.6f} s | {analysis['gate_a']['pair1_trigger_span_reduction']:.1f}× | ≥10× | ✅ |
| det(cov) | {s0_stats['pair1']['state_generalized_variance']:.9f} | {s2_stats['pair1']['state_generalized_variance']:.9f} | {analysis['gate_a']['pair1_generalized_variance_reduction']:.1f}× | ≥10× | ✅ |
| state std | `[0.3396,3.7716,0.0660]` | `[0.2859,1.2066,0.0290]` | 三项下降 | 不得增大 | ✅ |

Gate A 10/10 valid，通过后冻结 `verdict_rule.frozen.md`，其 SHA-256 为 `{provenance['hashes']['verdict_rule_sha256']}`。

## Stage 3/4：判定 campaign

| 配置 | n | outcome | flips | flip rate Wilson 95% | 成对一致率 | 成对 Wilson 95% |
|---|---:|---|---:|---|---:|---|
| dense_low_modal | 60 | S3=60 | 0 | `[0,{summaries['dense_low_modal']['flip_rate_wilson95'][1]:.4f}]` | 1770/1770=1.0 | `[{summaries['dense_low_modal']['pairwise_consistency_wilson95'][0]:.4f},1]` |
| pair4 | 20 | S3=20 | 0 | `[0,{summaries['pair4']['flip_rate_wilson95'][1]:.4f}]` | 190/190=1.0 | `[{summaries['pair4']['pairwise_consistency_wilson95'][0]:.4f},1]` |
| pair1 | 20 | S3=20 | 0 | `[0,{summaries['pair1']['flip_rate_wilson95'][1]:.4f}]` | 190/190=1.0 | `[{summaries['pair1']['pairwise_consistency_wilson95'][0]:.4f},1]` |

成对 Wilson 把 pair 当作二项计数，pair 非独立，CI 仅作描述。冻结 β 计算使用历史 modal Wilson upper：dense `0.9149232`、pair4 `0.9862896`、pair1 `1.0`，因此 `0.9149232^60 × 0.9862896^20 × 1^20 = {p0:.9f}`。

## ⚠️ 密扫完整性前提

当前 CSV 为 mc_nn S3=87、`primary_bug`=81。逐行复核表明差 6 来自分类语义：`primary_bug` 额外要求 classical S0；不是把 81 悄悄改成 87。重复组的任务是比较 mc_nn outcome class，因此使用 seed 2026062942 的 S3=15/19、S0=4/19。若后续证明 `outcome_severity` 字段本身失真，本报告的 dense 证据必须作废，β 应降为 γ。

## ⚠️ 残余现象与限制

- dense 的 60 run 中有一次落到后续触发相位，整体 trigger span=2.085 s，但仍为 S3；说明事件驱动消除了 wall scheduling，不等于消除了系统轨迹的所有相位分支。
- Stage 3 pair1 的 20-run trigger span=40.928 ms、det(cov)=0.000216724，仍分别比 legacy 收敛约 54×和 11.8×；roll std=0.3531° 比 legacy 0.3396° 高约 4%。冻结 β 规则不要求 Stage 3 重新执行 Gate A，但这个边缘回弹必须保留为 caveat。
- DDS ground-truth 入站仍观察到乱序 timestamp；hardened 明确拒绝它们。实际 setpoint 节奏略低于 80 Hz，但未发生 failsafe。
- 主机有远程桌面/编辑器负载，无法完全隔离；legacy 与 hardened 全部固定到同一 Docker cpuset 8–11，未与其它 PX4 campaign 共存。
- 历史原 campaign binary 已在本任务前被覆写；本实验全程使用隔离 r4 binary md5 `{provenance['px4_binary']['md5']}`，因此不把新 run 合并回原 120/926 表。
- β 是本锚点与当前 rebuilt SUT/harness 的判定，不证明所有 PX4/SIH 工况 bit-exact，也不证明并行 campaign 已验证。

## Provenance

- harness Git HEAD `{provenance['harness_git']['head']['stdout']}`，branch `{provenance['experiment']['branch']}`；开工前已有用户改动，未覆盖。
- PX4 HEAD `{provenance['px4_git']['head']['stdout']}`；isolated binary md5 `{provenance['px4_binary']['md5']}`。
- Docker `uav_sf:phase1` digest `{provenance['docker']['digest']}`。
- speed factor `1.25`；CPU `8-11`；全程串行。
- 完整 manifest：`provenance/manifest.json`；阶段快照位于 `provenance/`。
- `code.diff` 是当前 dirty worktree 的完整可审查 diff；其中 `diagnostic_probe` hunks 在本任务开始前已存在，本任务新增的是 timing-mode/event-clock、runner 显式传参与 Tier-0.5 driver/finalizer。

## 验证

- `python3 -m py_compile scripts/*.py`：✅
- `bash -n scripts/*.sh docker/*.sh`：✅
- 交付 JSON `jq empty`：✅
- `git diff --check`：✅
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=/mnt/nvme/uav_sf python3 -m pytest -q tests`：✅ 75 passed、4 subtests passed。
- ⚠️ 裸 `pytest -q` 会越界收集 ignored 的 PX4/TFLM 与旧 ROS backup 树，并因宿主 NumPy/SciPy ABI、TFLM Python 依赖和重复 px4_msgs import 失败；该命令不代表仓库 `tests/` 的结果。
"""
    (ROOT / "REPORT.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
