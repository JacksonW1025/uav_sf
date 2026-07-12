# AGENT.md — `uav_sf` 工作指南

新会话先读：

1. `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md`
2. `docs/ARTIFACT_INDEX.md`
3. 本文件

V8 是当前权威叙事，取代 v7 以及旧 M0/M1/M2/M2b handoff、RAPTOR-only closeout 叙事。旧文档只能当历史证据或 V8 引用的支撑材料，不要重新把它们当当前路线入口。

## 当前状态

- 头条发现：`mc_nn_control` 在 mode-23 切换瞬态存在 robust 差分失效，经典控制 S0 干净恢复，`mc_nn_control` S3 失控翻机；pair1/pair2/pair4 为 3/3，pair5 为 8/9 概率性边界锚点。
- 切换区 campaign 已完成 RQ1/RQ2/RQ3：guided 有 179 primary、约 10 个确认 cell；主张是更高命中率、更密 archive、更一致地快速定位边界，不是比 random 找到更多 3/3 bug。
- multi-policy、wave-1 wind+physics、wave-2 state-contam 都是诚实 negative 或诊断信号：失效收敛到切换瞬态灾难类 P1/P2，不铺到稳态非切换轴，也没有独立 P3-P7 渐进行为失效。
- RAPTOR 第二 SUT 全量对照已完成且为干净 negative：dense sweep 120/120 valid 0 strict，7 臂 search 840 eval 0 confirmed primary，gate/anchor 全 negative，全 campaign 约 926 个成功 eval 中 RAPTOR 0 次 S3/S4。
- RAPTOR 的定位必须锁死：`mc_nn_control` ↔ classical 给 learned-specific 灾难差分；RAPTOR ↔ classical 只给 oracle 区分力和 harness 外部效度。不要写成 RAPTOR negative 支撑 learned-specificity。
- unclipped RAPTOR 对照已完成：已移除 position/velocity input clipping 并用 `raptor_input` dump 证明大误差确实进网；24/24 valid，0 strict，已知失效带内裁剪不是 RAPTOR 鲁棒主因。但这只排除裁剪一条 confound，不归因到架构、递归、维度或训练。
- 当前决策：方案 A，收范围 + 开写。数据侧无 open loop。可选/押后：RQ2 统计加固 + `guided_abs` fitness 消融、变形/对称 oracle、独立 unclipped 结果报告。

## 固定口径

- 灾难类 primary：`strict_s0_vs_s3`，去污染后 classical S0 且 learned S3；跨种子 `>=2/3` 为稳健，`3/3` 另报强档。
- 灾难类复现只看离散 severity + violation 符号；连续 rho 只作诊断，不在深违反区当稳健复现量。
- 行为类 policy 要越过抖动带并做触发性质确认；P6/P7 在现有结果里是伴随 S3 的次级签名，不是独立失效。
- invalid、trigger timeout、去污染失败、run error、identity 失败都排除在 candidate/confirmed 账外。
- 回归 gate：pair1/pair2 是确定性硬闸；pair4/pair5 是边界锚点，用概率跟踪，目标 `>=6/8`。
- RAPTOR 裁剪 threat 的当前状态是“已在已知失效带测试排除”，不是 open threat；残余多轴 confound 仍要主动认领。

## 环境

- 工作区：`/mnt/nvme/uav_sf`
- 容器镜像：`uav_sf:phase1`，Ubuntu 24.04 arm64
- PX4 固定：`3042f906abaab7ab59ae838ad5a530a9ef3df9a6`
- PX4 源码：`external/PX4-Autopilot`，gitignored
- ROS 2 workspace：`ros2_ws`，gitignored
- 现有 board：`px4_sitl_mcnn_sih`、`px4_sitl_raptor_sih`、`px4_sitl_raptor_unclipped_sih`

统一入口：

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<name> ./docker/run.sh bash -lc "source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && <cmd>"'
```

不要在宿主直接跑容器内构建出的 PX4 binary。不要把 sudo 密码写进仓库；常规构建/仿真走 `sg docker -c`。RAPTOR 运行要确认 `policy.tar` staging 和 ROS overlay 与运行时匹配，避免 stale `RaptorStatus`/`RaptorInput` 导入问题。

## 仓库约定

- `external/PX4-Autopilot` 和 `ros2_ws` 的改动必须通过 tracked overlay / patch / installer 入库。
- raw artifacts 保持 ignored：`*.ulg`、`*.log`、`docs/**/evals/`、`runs/**/evals/`、本地 checkpoint 和 scratch campaign 目录。
- V8 例外：RAPTOR 全量 campaign 的 top-level review artifact 已用 `-f` 强加入 `runs/campaigns/raptor_*_20260705/`；per-eval `evals/` 与 `.ulg` 仍留本地。
- 提交只应包含代码、配置、报告、结构化汇总 JSON/JSONL、必要 theta/candidate/summary artifact。
- 新实验若要保留 raw 证据，只留本地 ignored 文件，并在报告里引用结构化摘要。

## 关键脚本

- `scripts/m1_offboard_task.py`（`--controller mcnn|raptor`）
- `scripts/m1_compare.py`（`--neural-controller mcnn|raptor`）
- `scripts/m1_diff_runner.py`
- `scripts/property_oracle.py`
- `scripts/property_fitness.py`（含 `--fitness-mode`）
- `scripts/theta_genome.py`
- `scripts/validity_automation.py`
- `scripts/m2_map_elites.py`
- `scripts/campaign_runner.py`
- `scripts/route_a_anchor_regression.py`
- `scripts/multipolicy_differential.py`
- `scripts/rq2_archive_reanalysis.py`
- `scripts/run_switch_dense_sweep.py`
- `scripts/run_raptor_unclipped_ablation.py`
- `scripts/m2b_1_dump_raptor_input.py`
- `scripts/build_px4_mcnn_sih.sh`
- `scripts/build_px4_raptor_sih.sh`
- `scripts/install_raptor_sih_board.sh`
- `scripts/build_px4_raptor_unclipped_sih.sh`
- `scripts/install_raptor_unclipped_sih_board.sh`

RAPTOR closeout and older M-series scripts remain in `scripts/` for reproducibility or code reuse, but they are not the current narrative driver.

## 关键报告

- `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md`
- `docs/switch_severity_campaign_20260629.md`
- `docs/multipolicy_differential_20260703.md`
- `docs/wave1_windphysics_20260627.md`
- `docs/wave2_statecontam_campaign_20260703.md`
- `docs/wave2_gateA_diagnostic_20260703.md`
- `docs/rq2_archive_reanalysis_20260705.md`
- `docs/raptor_external_ai_review_2026-07-07.md`
- `docs/raptor_unclipped_ablation_preflight_20260707.md`
- `docs/fuzz1c_decontam_20260625.md`
- `docs/fuzz1c_severity_20260625.md`
- `docs/oracle_calibration.md`
- `docs/oracle_map_and_property_set_v0.1.md`

## 提交前检查

```bash
python3 -m py_compile scripts/*.py
bash -n scripts/*.sh docker/*.sh
git ls-files '*.json' | xargs -r jq empty
git diff --check
git diff --cached --check
```

中文汇报，命令/路径/参数保持英文原样。
