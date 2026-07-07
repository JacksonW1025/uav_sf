# RAPTOR 现状勘察 - 2026-07-05

本报告是只读勘察产物。未改代码、未改 genome、未改 oracle/gate、未运行任何 SITL eval；只基于仓库中的文档、脚本、配置、PX4 模块源码和历史 artifact 判断。

## §0 承重结论

结论：当初 RAPTOR 线的“裁剪”是 **A 类 + B 类组合**，且下一步成本主要由 **B 类** 决定。

- **B 类 1 - RAPTOR SUT 自身输入裁剪**：RAPTOR 在推理前硬裁剪观测误差。`external/PX4-Autopilot/src/modules/mc_raptor/mc_raptor.hpp` 定义 `max_position_error = 0.5`、`max_velocity_error = 1.0`；`mc_raptor.cpp` 的 `observe()` 对 position error 和 velocity error 调 `clip()` 后才写入 observation。`docs/PROJECT_NARRATIVE_CONTEXT_v2.md` 和 v6 也明确记录 M1 核心事实：RAPTOR 的 position ±0.5 m、velocity ±1.0 m clipping 使 setpoint 幅度攻击基本徒劳；mc_nn_control 没有这层观测误差裁剪。
- **B 类 2 - RAPTOR 没有接入当前完整 mc_nn campaign harness**：`scripts/property_oracle.py`、`scripts/m1_compare.py`、`scripts/m1_metrics.py` 仍保留 RAPTOR 支持，但当前 `scripts/m2_map_elites.py` 和 `scripts/campaign_runner.py` 实际硬接 `mcnn_gate3_position_error_probe`、`controller="mcnn"`、`mcnn_identity_gate`、`mc_nn_control mode 23` 元数据和 classical-minus-mcnn fitness。也就是说，RAPTOR 可以走旧 M1/closeout 路径，但不是当前 RQ2/RQ3 的完整可比 SUT。
- **A 类 - 测试覆盖也被裁剪**：RAPTOR closeout 明确是 lightweight closeout，不是大 campaign。历史 artifact 覆盖了 NaN/Inf 探针、Gazebo plant asymmetry、少量 activation transient、一个 finite-sensor reachability spot；没有对 RAPTOR 跑过当前 route-A `route-a-switching` genome、switch severity campaign、steady wind/physics campaign、state-contam campaign 或 dense/confirmation 流程。

因此，“救 RAPTOR”不是单纯把一个 flag 打开就能完成的补测。若目标是和 mc_nn 当前证据同等级可比，必须先做 **RAPTOR 重新集成**，再放开 route-A/扰动轴补测。若目标只是 sanity check，可以低成本补几个 RAPTOR 点，但那不能支撑“完整 harness 下 robust/fragile”的结论。

一句话可行性判定：**救 RAPTOR 属“先重新集成后补测”，成本中高；oracle/genome/task/airframe 可复用较多，但 evaluator、runner、identity gate、build/plumbing 需要 RAPTOR 专属接线。**

## §1 RAPTOR 接入现状

### 1.1 当前如何调用/运行

RAPTOR 的旧路径是独立 `raptor_sih` board + M1 diff runner：

- `scripts/build_px4_raptor_sih.sh` 安装 `raptor_sih` board、X500 SIH airframe、state shim，然后构建 `px4_sitl_raptor_sih`。
- `boards/px4/sitl/raptor_sih.px4board` 只启用 `CONFIG_LIB_RL_TOOLS=y` 和 `CONFIG_MODULES_MC_RAPTOR=y`。
- `scripts/m1_diff_runner.py` 在 PX4 启动脚本中执行 `mc_raptor start`，把 `policy.tar` 放入 run root 的 `raptor/` 目录，然后分别跑 classical 与 RAPTOR。
- `scripts/m1_offboard_task.py` 对 `--controller raptor` 使用 PX4 External1 路径，默认 mode id 是 23；classical 使用 Offboard nav state 14。也就是说 RAPTOR 和 mc_nn_control 在任务脚本层面都走外部模式 23，但启动模块、board 和 runner 不同。
- PX4 模块 `mc_raptor` 注册 external mode 名称为 `RAPTOR`；`module.yaml` 里 `MC_RAPTOR_ENABLE` 默认 false，`MC_RAPTOR_OFFB` 默认 false，说明它设计为单独 external mode，而不是默认替换 Offboard。

mc_nn 当前路径是 `mcnn_sih` board + mc_nn runner/campaign：

- `scripts/build_px4_mcnn_sih.sh` 安装 `mcnn_sih` board、X500 SIH airframe、DDS groundtruth、state shim，然后构建 `px4_sitl_mcnn_sih`。
- `boards/px4/sitl/mcnn_sih.px4board` 同时启用 RL tools、TFLM、`MC_NN_CONTROL` 和 `MC_RAPTOR`，但当前文档记录 mc_nn 实验中 `MC_RAPTOR_ENABLE=false`，实际启动的是 `mc_nn_control`。
- `scripts/mcnn_gate3_position_error_probe.py` 对 `--controller mcnn` 启动 `mc_nn_control`，并记录 `neural_control` identity 相关 topic。

### 1.2 是否接入完整测试管线

部分接入，但不是开箱完整接入。

可复用或已有 RAPTOR 支持：

- `scripts/property_oracle.py` 的 CLI `--controller` 支持 `classical`、`raptor`、`mcnn`，P1-P7 与 S0-S4 判定不是只为 mc_nn 写死。
- `scripts/m1_compare.py` 支持 `--neural-controller raptor|mcnn`，可以对 classical vs RAPTOR 做 property differential。
- `scripts/m1_metrics.py` 的 nav state map 包含 `raptor: 23`，并有 RAPTOR status/input 相关统计。
- `scripts/validity_automation.py` 的 decontamination target nav 包含 `raptor: 23`。

当前完整 campaign harness 硬接 mc_nn：

- `scripts/m2_map_elites.py` 导入的是 `mcnn_gate3_position_error_probe as mcnn_runner`；`evaluate_theta()` 固定跑 `["classical", "mcnn"]`，固定把 neural ULOG 传给 `evaluate_ulog(... controller="mcnn")`，并固定使用 `mcnn_identity` gate。
- `scripts/m2_map_elites.py` metadata 明写 `neural_controller: "mc_nn_control mode 23"`，build/install 提示也指向 `mcnn_sih`。
- `scripts/campaign_runner.py` 默认 evaluator 是 `m2_map_elites.evaluate_theta`，元数据写的是 classical-minus-mcnn rho gap 与 mcnn S3 primary bug，没有 SUT selector。
- `scripts/validity_automation.py` 的 `mcnn_identity_gate()` 明确要求 `identity.controller == "mcnn"`、`neural_control` 有样本、有输出匹配，并检查 `raptor_input_present` 为 false。这不能直接用于 RAPTOR。

所以当前状态是：RAPTOR 可以用旧 M1 单点/closeout 机制跑差分，但没有接进当前 campaign runner + MAP-Elites + identity/decontam/severity 自动化闭环。

### 1.3 Airframe / 仿真配置

相同点：

- RAPTOR 与 mc_nn 都使用 `config/px4/init.d-posix/airframes/10046_sihsim_x500_v2`，即 SIH X500 v2，`SYS_AUTOSTART=10046`。
- `theta_genome.theta_from_genome()` 的 base airframe 也是 `{"sim": "sih", "model": "sihsim_x500_v2", "sys_autostart": 10046}`。
- `m1_offboard_task.py` 对 RAPTOR 与 mc_nn 使用同一个任务/route/setpoint 发送器，只是 controller 参数不同。

差异点：

- RAPTOR 旧 build 是 `px4_sitl_raptor_sih`；mc_nn 当前 campaign build 是 `px4_sitl_mcnn_sih`。
- `build_px4_mcnn_sih.sh` 显式安装 DDS groundtruth；`build_px4_raptor_sih.sh` 当前未显式调用同一个 DDS groundtruth installer。若 route-A 对 RAPTOR 重接，需先确认 groundtruth topic/patch 与 RAPTOR build 完全一致。
- mc_nn identity 依赖 `neural_control` topic；RAPTOR 旧路径依赖 `raptor_status`、`raptor_input`、`policy.tar` staging。这是 identity 和 logger topic 层面的真实差异。

## §2 裁剪的具体范围

### 2.1 被裁掉/未覆盖的扰动轴

对照当前 mc_nn 已测空间，RAPTOR 历史覆盖明显更窄：

| 扰动轴 / 攻击类型 | mc_nn 当前证据 | RAPTOR 历史证据 | 判定 |
| --- | --- | --- | --- |
| wind | `wave1_windphysics_20260627.md` 跑 steady wind/physics campaign；`switch_severity_campaign_20260629.md` route-A 中 wind 0-6 m/s | activation closeout 有 `circle_45deg_wind` 一类少量点 | RAPTOR 未跑同等级 campaign |
| physics_mismatch | mc_nn steady wind/physics campaign 覆盖 physics mismatch / steady_combo | `raptor_closeout_gz_asym_20260625` 有 6 个 Gazebo plant asymmetry 点 | 不是同一 SIH campaign 空间 |
| switching | mc_nn route-A 有 `route-a-switching` genome、preflight anchors、guided/random/grid、confirmations、dense sweep | RAPTOR activation/extreme closeout 共少量点，最高实际 switch 约 43 deg / 2.3 rad/s，flight-safe | RAPTOR 没跑 route-A genome 和多 seed confirmation |
| step | 当前 genome 有 step 轴；mc_nn harness 可评价 P5 moderate step / severity | RAPTOR M1 旧线主要是 setpoint amplitude / anchors；该类被 RAPTOR 输入 clipping 明显削弱 | 当前 step campaign 未对 RAPTOR 系统跑通 |
| state_contam | `wave2_statecontam_campaign_20260703.md` 对 mc_nn 跑 state-contam campaign，并检查 delivery/fairness/identity/decontam | RAPTOR closeout 有 NaN/Inf 输入探针和一个 finite-sensor reachability spot | RAPTOR 未跑当前 state_contam bias campaign |

route-A 切换瞬态没有对 RAPTOR 跑过。`docs/switch_severity_campaign_20260629.md` 的 board 是 `px4_sitl_mcnn_sih`，mode id 23 是 `mc_nn`；`scripts/m2_map_elites.py` 的 `route_a_profile_for()` 虽然是通用 theta 生成逻辑，但 evaluator 固定调用 mc_nn runner。

### 2.2 裁剪是硬编码还是配置

两类都有：

- RAPTOR 输入裁剪是 **源码硬编码行为**，不是 campaign 配置开关。`max_position_error`、`max_velocity_error` 是 C++ 模块内的常量，`observe()` 每次推理前裁剪。去掉它会改变 RAPTOR SUT 语义，可能也脱离原 policy 的训练/部署假设。
- 覆盖空间裁剪多半是 **harness 接线缺失 + 历史实验预算裁剪**。当前 route-A、steady-wind-physics、state-contam、step 轴已在 `theta_genome.py` / `m2_map_elites.py` 中存在，但 evaluator 和 identity gate 硬接 mc_nn。放开给 RAPTOR 不是只改配置，需要新增/泛化 runner、SUT selector、RAPTOR identity gate 和 metadata。
- 当前 genome 还把 C-tier setpoint amplitude attack 作为 excluded/不优先空间处理；对 RAPTOR 来说，这与输入 clipping 的负结果一致，但不能替代 route-A/扰动轴补测。

### 2.3 RAPTOR 历史 artifacts

仓库保留了 RAPTOR closeout 级 artifacts，可作为有限基线：

- `raptor_closeout_p0_nonfinite_active2_20260625/`：6 个 NaN/Inf 输入探针，0 primary。
- `raptor_closeout_gz_asym_20260625/`：6 个 Gazebo plant asymmetry 点，0 primary。
- `raptor_closeout_activation_20260625/`：4 个 activation transient 点，0 primary。
- `raptor_closeout_activation_extreme_20260625/`：1 个 60 deg 场景，实际约 37 deg / 1.7 rad/s，0 primary。
- `raptor_closeout_activation_extreme2_20260625/`：1 个 75 deg 场景，实际约 43 deg / 2.3 rad/s，0 primary。
- `raptor_closeout_reachable_finite_sensor_20260625/`：1 个 finite-sensor harsh spot，0 primary。
- `docs/RAPTOR_closeout.md` 明确说该 closeout 不做 M3、不引入 mc_nn_control、不跑 large campaign、不强行改 controller limits 造任意 60 deg activation。

这些 artifact 能证明“有限探针下未确认 primary bug”，不能证明“完整 route-A/campaign harness 下 robust”。

## §3 复用性摸底

### 3.1 差分 oracle + 三卫生

可直接复用的部分：

- P1-P7 property 与 S0-S4 severity 的核心判定在 `property_oracle.py`，对 RAPTOR/mc_nn 都可调用。
- `m1_compare.py` 的 differential shell 支持 `--neural-controller raptor`。
- decontamination window 对 `raptor: 23` 有 target nav 配置。
- `m1_offboard_task.py` 能以同一任务驱动 RAPTOR 和 mc_nn。

不能开箱复用的部分：

- identity gate 目前是 mc_nn 专属。`mcnn_identity_gate()` 明确检查 `neural_control`、network output 到 actuator 的匹配，并要求没有 `raptor_input`。RAPTOR 需要新的 identity 逻辑，例如确认 `raptor_status` active、`raptor_input` 在控制窗内有样本、External1/target nav 正确、`neural_control` 不应出现、policy staging 成功。
- `m2_map_elites.evaluate_theta()` 和 `campaign_runner.py` 没有 SUT selector，不能通过配置切到 RAPTOR。

### 3.2 route-A 切换瞬态复用

route-A 的 theta/genome 机器可以复用，但需要先接线：

- `theta_genome.py` 的 disturbance axes 和 `route-a-switching` subspace 是 SUT 无关的。
- `m2_map_elites.route_a_profile_for()` 生成 roll/pitch/rate/wind/delay 的逻辑是 SUT 无关的。
- `m1_offboard_task.py` 支持 `--controller raptor`，因此任务侧可复用。

缺口：

- evaluator 当前只创建 classical+mcnn pair。
- runner 当前使用 `mcnn_gate3_position_error_probe.run_one()` 和 `px4_sitl_mcnn_sih`。
- confirmation、fitness、metadata、validity gate 名称都写成 mc_nn/mcnn。

因此 route-A 可“概念复用”，但不能直接开跑 RAPTOR campaign。

### 3.3 已知 blocker / 潜伏问题

- **patch drift / build drift**：AGENT 与 v6 已记录 patch drift 是项目反复出现的问题。RAPTOR 重接前必须先做静态 build/config sanity，但本报告未运行 SITL。
- **groundtruth/install 差异**：mc_nn build 显式安装 DDS groundtruth；RAPTOR build 当前脚本未显式调用同一 installer。route-A 的 oracle/anchor 依赖 groundtruth 与 topic 质量，需重接时核对。
- **mode id / module coexistence**：`mcnn_sih` board 同时包含 RAPTOR 与 mc_nn 模块，但实验中应只启动一个 external mode SUT。若想共用 `mcnn_sih` 跑 RAPTOR，需要确认 external mode id、模块启动顺序和 `MC_RAPTOR_ENABLE`/`MC_RAPTOR_OFFB` 不产生冲突。
- **policy staging**：RAPTOR runner 需要 `policy.tar` 放入 run root；mc_nn runner 依赖 TFLite model/`neural_control` 流。SUT selector 不能只换 controller 名称。
- **state contamination shim**：state-contam 轴依赖 patch 和 delivery/fairness 检查。mc_nn 路径已跑通；RAPTOR 路径只应在重新确认 shim 对 RAPTOR build 生效后再纳入 campaign。
- **吞吐/计时**：旧 RAPTOR artifacts 多是小规模 probes；当前 route-A/RQ2 是大量 eval + confirmation。若 RAPTOR build 更慢或 mode activation 更脆，需先做小 N smoke，再上 campaign。

## §4 已知阻碍 / 风险

最大风险是叙事误读：RAPTOR 旧线的“0 confirmed / robust”不是“完整 harness 下无问题”，而是“在硬输入裁剪 + 有限 closeout probes 下未确认 primary bug”。这不是坏数据，但证据等级低于当前 mc_nn route-A 和 state-contam campaign。

如果下一步保留原始 RAPTOR SUT，输入 clipping 不能随手去掉；去掉后测试的是“unclipped RAPTOR variant”，不是论文/当前模块语义下的 RAPTOR。若研究问题是比较两个实际后端，应该先保留 clipping，并把完整 harness 接上；若研究问题是解释 clipping 是否掩盖缺陷，则可另设 unclipped variant，但那是新实验线。

如果人类需要把 RAPTOR 纳入 RQ2/RQ3 的同等级结论，当前 blocker 是重新集成，不是单纯补测预算。最小必要工作包括：SUT selector、RAPTOR runner 接入 campaign、RAPTOR identity gate、metadata/fitness 命名泛化、build/groundtruth/state-shim sanity、少量 anchor smoke，然后才是 route-A/扰动轴 campaign。

## 待人类决策点

可选下一步不是唯一方案：

1. **补测-lite（低到中成本）**：用旧 RAPTOR runner 手工/脚本化跑少量 route-A anchor 或历史 top theta，调用 property oracle/m1_compare 做 sanity。优点是快；缺点是不能声称完整 campaign 可比。
2. **完整重新集成后补测（中高成本）**：把 campaign/evaluator 泛化为 SUT selector，补 RAPTOR identity gate，然后复用 route-A genome、steady/state/step 子空间和 confirmation 流程。这是可比性最强的路线。
3. **unclipped RAPTOR variant（高成本，且是新 SUT）**：去掉或参数化 RAPTOR 输入 clipping，再测试同一空间。该路线适合研究 clipping 的因果作用，但不应和原始 RAPTOR robust 结论混为一谈。

建议人类先决定研究问题是“原始 RAPTOR 在完整 harness 下是否仍 robust”，还是“RAPTOR clipping 是否是 robust 的主要原因”。前者走选项 2；后者需要选项 2 加选项 3 的对照。
