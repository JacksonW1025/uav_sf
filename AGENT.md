# AGENT.md — `uav_sf` 工作指南

新会话先读：

1. `docs/PROJECT_NARRATIVE_CONTEXT_v2.md`
2. `docs/ARTIFACT_INDEX.md`
3. 本文件

旧的 M0/M1/M2/M2b handoff 和 RAPTOR-only 叙事已被 v2 取代，不要重新以它们作为当前路线入口。

## 当前状态

- 路线 A 已收官：FUZZ-1c decontam 确认 4 个 strict differential，经典控制级 S0 恢复，`mc_nn_control` S3 失控翻机。
- 当前主张不是 FUZZ-1 的 first kill，也不是 FUZZ-1b 的 downgrade；它们只是方法卫生教训。
- 路线 B 尚未开始：下一步是多 oracle，先做 FUZZ-1c 非单调带上的变形/对称 oracle，并配受控密扫。
- 保留 artifact 的核心是报告和结构化结果，不保留 raw run 噪声。

## 环境

- 工作区：`/mnt/nvme/uav_sf`
- 容器镜像：`uav_sf:phase1`，Ubuntu 24.04 arm64
- PX4 固定：`3042f906abaab7ab59ae838ad5a530a9ef3df9a6`
- PX4 源码：`external/PX4-Autopilot`，gitignored
- ROS 2 workspace：`ros2_ws`，gitignored

统一入口：

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<name> ./docker/run.sh bash -lc "source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && <cmd>"'
```

不要在宿主直接跑容器内构建出的 PX4 binary。不要把 sudo 密码写进仓库；常规构建/仿真走 `sg docker -c`。

## 仓库约定

- `external/PX4-Autopilot` 和 `ros2_ws` 的改动必须通过 tracked overlay / patch / installer 入库。
- raw artifacts 保持 ignored：`*.ulg`、`*.log`、`docs/**/evals/`。
- 提交只应包含代码、配置、报告、结构化汇总 JSON/JSONL。
- 若新实验需要保留 raw 证据，只留本地 ignored 文件，并在报告里引用结构化摘要。

## 关键脚本

- `scripts/build_px4_mcnn_sih.sh`
- `scripts/install_fuzz1b_dds_groundtruth.sh`
- `scripts/m1_offboard_task.py`
- `scripts/m1_metrics.py`
- `scripts/m1_compare.py`
- `scripts/fuzz1_activation_mcnn.py`
- `scripts/fuzz1b_locked_activation.py`
- `scripts/fuzz1c_severity_scan.py`
- `scripts/fuzz1c_decontam_analyze.py`
- `scripts/mcnn_gate3_position_error_probe.py`

RAPTOR closeout and older M-series scripts remain in `scripts/` where they support reproducibility or code reuse, but they are not the current narrative driver.

## 提交前检查

```bash
python3 -m py_compile scripts/*.py
bash -n scripts/*.sh docker/*.sh
git ls-files '*.json' | xargs -r jq empty
git diff --check
git diff --cached --check
```

中文汇报，命令/路径/参数保持英文原样。
