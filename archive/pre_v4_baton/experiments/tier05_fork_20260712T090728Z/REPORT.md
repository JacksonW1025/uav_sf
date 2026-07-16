# Tier 0.5 判定实验（THE FORK）

## 最终判定

**✅ β：时序硬化后，预注册的三个锚点配置共 100 个 valid run 全部为 S3，0 次结局翻转；保守零翻转概率上界乘积 `P0=0.00365736<0.01`。**

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
| pair1 | S3 10/10 | 2223.921 ms | `[0.3396,3.7716,0.0660]` | 0.002565419 |
| pair4 | S3 10/10 | 26.526 ms | `[2.6583,1.7807,0.0324]` | 0.005632610 |

⚠️ pair1 有一次后续相位触发，造成 2.224 s span；这比历史 204 ms 更差，证明必须以当前主机 baseline 定门。

## Stage 1：修复

✅ 新增 `--timing-mode {legacy,hardened}`。legacy 路径仍创建原 timer；hardened 不创建 timer，以 `/fmu/out/vehicle_angular_velocity_groundtruth` 入站消息为唯一 task clock，拒绝重复/乱序 timestamp，并用 PX4 timestamp deadline accumulator 分频发布与求值。QoS、queue depth、PX4 binary 均未修改。

✅ 修正版 smoke 2/2 exit 0、mode confirmed、无 post-switch failsafe；实测 tick rate 77.3–78.0 Hz（目标 80 Hz，乱序入站被拒绝），未触发 OFFBOARD failsafe。

## Stage 2：Gate A

| pair1 指标 | legacy | hardened | 收敛 | 冻结门 | 结果 |
|---|---:|---:|---:|---:|---|
| trigger span | 2.223921 s | 0.026240 s | 84.8× | ≥10× | ✅ |
| det(cov) | 0.002565419 | 0.000027053 | 94.8× | ≥10× | ✅ |
| state std | `[0.3396,3.7716,0.0660]` | `[0.2859,1.2066,0.0290]` | 三项下降 | 不得增大 | ✅ |

Gate A 10/10 valid，通过后冻结 `verdict_rule.frozen.md`，其 SHA-256 为 `fcf9bacf254b0bdd85c68b80462d52b4c5c531fecacb4c1221fbc96b13a10bad`。

## Stage 3/4：判定 campaign

| 配置 | n | outcome | flips | flip rate Wilson 95% | 成对一致率 | 成对 Wilson 95% |
|---|---:|---|---:|---|---:|---|
| dense_low_modal | 60 | S3=60 | 0 | `[0,0.0602]` | 1770/1770=1.0 | `[0.9978,1]` |
| pair4 | 20 | S3=20 | 0 | `[0,0.1611]` | 190/190=1.0 | `[0.9802,1]` |
| pair1 | 20 | S3=20 | 0 | `[0,0.1611]` | 190/190=1.0 | `[0.9802,1]` |

成对 Wilson 把 pair 当作二项计数，pair 非独立，CI 仅作描述。冻结 β 计算使用历史 modal Wilson upper：dense `0.9149232`、pair4 `0.9862896`、pair1 `1.0`，因此 `0.9149232^60 × 0.9862896^20 × 1^20 = 0.003657365`。

## ⚠️ 密扫完整性前提

当前 CSV 为 mc_nn S3=87、`primary_bug`=81。逐行复核表明差 6 来自分类语义：`primary_bug` 额外要求 classical S0；不是把 81 悄悄改成 87。重复组的任务是比较 mc_nn outcome class，因此使用 seed 2026062942 的 S3=15/19、S0=4/19。若后续证明 `outcome_severity` 字段本身失真，本报告的 dense 证据必须作废，β 应降为 γ。

## ⚠️ 残余现象与限制

- dense 的 60 run 中有一次落到后续触发相位，整体 trigger span=2.085 s，但仍为 S3；说明事件驱动消除了 wall scheduling，不等于消除了系统轨迹的所有相位分支。
- Stage 3 pair1 的 20-run trigger span=40.928 ms、det(cov)=0.000216724，仍分别比 legacy 收敛约 54×和 11.8×；roll std=0.3531° 比 legacy 0.3396° 高约 4%。冻结 β 规则不要求 Stage 3 重新执行 Gate A，但这个边缘回弹必须保留为 caveat。
- DDS ground-truth 入站仍观察到乱序 timestamp；hardened 明确拒绝它们。实际 setpoint 节奏略低于 80 Hz，但未发生 failsafe。
- 主机有远程桌面/编辑器负载，无法完全隔离；legacy 与 hardened 全部固定到同一 Docker cpuset 8–11，未与其它 PX4 campaign 共存。
- 历史原 campaign binary 已在本任务前被覆写；本实验全程使用隔离 r4 binary md5 `4502483282e5d04e7af418c6dd2c26a0`，因此不把新 run 合并回原 120/926 表。
- β 是本锚点与当前 rebuilt SUT/harness 的判定，不证明所有 PX4/SIH 工况 bit-exact，也不证明并行 campaign 已验证。

## Provenance

- harness Git HEAD `4dff034bde781fd3b9e1b7c7e78a01337a92d795`，branch `tier05-fork-20260712T090728Z`；开工前已有用户改动，未覆盖。
- PX4 HEAD `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`；isolated binary md5 `4502483282e5d04e7af418c6dd2c26a0`。
- Docker `uav_sf:phase1` digest `sha256:4e590ec80407e37a77efa10d329b31e8e978cdcb86e3dbce630cd100f1575e29`。
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
