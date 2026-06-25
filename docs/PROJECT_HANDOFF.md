# RAPTOR 差分模糊测试 — 项目交接文档

> **用途**:这是一份自包含的交接文档,供在新对话里继续本项目。读完本文应能完整接手:做过什么、学到什么、卡在哪、下一步做什么。
> **最重要的两节是 §1(决策点 + 下一步)和 §9(下一步详述)**;§2–§8 是 grounding。
> 仓库:`github.com/JacksonW1025/uav_sf`。**git 状态**:远端 HEAD `d0da939`(M2.5);**M2.6、M2b-1、本轮诊断都在本地 worktree,尚未 commit/push**——新会话第一件事可能是整理提交。

---

## 0. 项目一句话 + 立场

**差分场景模糊测试**:对 PX4 新并入的学习型飞控 **RAPTOR**(`mc_raptor`,免训 GRU foundation policy),在同固件/同机架(X500 v2)/同任务下,用**经典级联控制器作内建差分 Oracle**,搜索"经典守得住、RAPTOR 守不住"的场景。全程 PX4 SITL,不依赖真机。目标:FSE/ICSE 级方法论文。

**四象限判据(只报一类)**:`primary_bug` = **经典 safe ∧ RAPTOR unsafe**;`interesting_not_bug` = 经典 unsafe、RAPTOR safe;`too_hard` = 两者都 unsafe;`boring` = 两者都 safe。

**工作立场**:以"系统有 bug、去找出来"为前提;null = 覆盖/方法问题而非鲁棒结论;红线是**公平**(污染共享估计、两控制器一致)+ **物理可信**(真实故障量级)——保证找到的 bug 是真的。**注意**:本立场对**下一个目标**仍然适用;但见 §1/§8,RAPTOR 上的证据已大量收敛。

---

## 1. 决策点 + 下一步(最重要)

**现状**:M0 → M2b-1 + 三项诊断(D1/D2/D3)全部完成,**六轮 0 confirmed primary_bug**。这轮诊断把"为什么没 bug"从猜测变成了证据,得出一个清晰的决策点。

**核心结论(诊断给出)**:
- **D1**:确认我们测的就是真 RAPTOR artifact(22-D 观测、4-D 动作、GRU-16、2084 参数、checkpoint `2025-04-19`)。所以 null **不能**赖在"测错模型"上。
- **D2**:旧的 Inf timeout 是 **harness 超时,不是 PX4/EKF crash**;且暴露了一个更严重的问题——**NaN/Inf shim 静默失败**,Inf 根本没送达共享 topic。这条线连"测过"都不算。
- **D3**:低噪声 + 正确(比值)度量下,**没有稳健的差分退化**;最佳点 `velocity_delay_030ms` 也只是 RAPTOR 1.236× vs 经典 0.965×,信号 < 噪声。**连续退化线统计上不成立。**

**决策建议(待用户最终拍板)**,优先级排序:

1. **先修 shim 的送达验证(前置,信任一切 null 的前提)**。D2 证明注入工具会**静默失败**——污染没进目标 topic 却不报错。这意味着**之前几轮的部分 null 可能是工具没真注入,而非 RAPTOR 扛住**。必须让每次注入**强制 ULOG 自检"污染真进了目标 topic",否则 fail-loud**。在投入任何新目标前修好。

2. **把 `mc_nn_control` 提为主目标,RAPTOR 降为鲁棒对照**。mc_nn_control 是 PX4 里另一个学习型控制器,**没有 RAPTOR 那层观测裁剪、大概率软得多**。全套工具(差分 oracle、shim、搜索器、统一包络)可直接复用。FSE 故事变成:"方法在 mc_nn_control 上发现 X 类危险 bug;在更鲁棒的 RAPTOR 上系统刻画其防御边界"——**RAPTOR 的'难'从失败变成对照组亮点**。

3. **(可选)RAPTOR 最后的窄实验:只做激活瞬态**。若想给 RAPTOR 一个干净机会:在高角速率+大姿态+受扰瞬间切入(打隐状态未收敛窗口,~100–200 步才收敛)。结构上 RAPTOR 独有、经典无此窗口、SITL 可做、论文只测了良性版本。**不要**为此开 Gazebo plant 不对称那一大摊。

**这不是 RAPTOR 鲁棒性结论**;它只说"当前 RAPTOR 证据不支持在转向前再开大搜索"。转向是数据驱动的,不是认输。

---

## 2. 环境与栈(pinned,复现用)

- **宿主**:Jetson AGX Orin 64GB,L4T 36.7 / R36.4.7,**Ubuntu 22.04,aarch64**。仅作 Docker host。
- **容器**:镜像 `uav_sf:phase1`(`ubuntu:24.04`,arm64)。Docker 29.3.0,data-root `/mnt/nvme/docker`。**CPU-only**(RAPTOR=RLtools,免训,不吃 GPU)。
- **PX4**:`main` 固定 `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`(v1.18 alpha)。**RAPTOR 只在 main,不在 v1.17**。源码在 `external/PX4-Autopilot`(gitignored)。
- **ROS 2** Jazzy + `px4_msgs`(`f7d9fcb65e2cdf4cf556f658bde55682403dcc8c`)+ Micro-XRCE-DDS-Agent v2.4.3(`73622810...`),UDP 8888。
- **Gazebo** Harmonic 8.14.0(headless 可用)。**仿真器主用 SIH**(`px4_sitl_raptor_sih` + `sihsim_quadx`),X500 v2 参数近似;Gazebo 备用。
- **关键参数/约定**:`IMU_GYRO_RATEMAX=400`(force_sync_native=4,匹配 100Hz 训练频率);切 RAPTOR 用 `DO_SET_MODE` main=4/sub=11 → `mode_id 23`;DDS 输出 topic 带版本号 `vehicle_status_v4`/`vehicle_local_position_v1`;SIH 直接 launch(`./bin/px4 .` from build root,规避 rcS CWD 坑);事件按 sim 时间触发不用 wall-clock。
- 工作区 `/mnt/nvme/uav_sf`;入容器:`sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<name> ./docker/run.sh bash -lc "..."'`。

**仓库约定**:`external/PX4-Autopilot` 与 `ros2_ws` 被 gitignore → 一切 PX4 改动以 **tracked patch/overlay + installer 脚本**入库(如 `boards/px4/sitl/raptor_sih.px4board`+`scripts/install_raptor_sih_board.sh`、`config/.../10046_sihsim_x500_v2`+`install_m1_sih_x500.sh`、`patches/px4/m2b_state_shim.patch`+`install_m2b_state_shim.sh`)。证据在 `docs/`。

---

## 3. 里程碑进度

| 里程碑 | commit | 结果 |
|---|---|---|
| Phase 1 环境 | `62d0383` | Docker + 容器 + RAPTOR SITL build |
| M0 bring-up | `b1be614` | 经典起飞→切 RAPTOR→ulog;**发现 stale-setpoint guard** |
| M1 Oracle MVP | `6c944b9` | X500 v2、offboard 任务、指标、四象限;**发现观测误差裁剪** |
| M2 制导搜索 | `ffd4063` | 统一包络、baseline 去污染、MAP-Elites;**8 eval,0 confirmed** |
| M2.5 估计污染+吞吐 | `d0da939`(远端 HEAD) | 共享 EKF/GNSS 污染、4x 修复;**delay scan 0 confirmed** |
| M2.6 不设防通道 | 本地未push | gyro 滤波 × TWR;**8 eval,0 confirmed;高 TWR 退化信号(后证为噪声)** |
| M2b-1 对抗 shim | 本地未commit | uORB 对抗 shim 建成;velocity-delay 公平但无 bug;NaN/Inf 探针;8-eval 搜索 0 confirmed |
| **M2b-1 诊断 D1/D2/D3** | 本地未commit | **确认真模型 / Inf 是 harness+shim 静默失败 / 退化线统计不成立** |
| **→ 决策点** | — | 见 §1:修 shim 验证 + 转 mc_nn_control |
| M2b-2 / M3 / Phase2 / Phase3 | — | 未做(plant 不对称/瞬态/Gazebo;baseline/消融/taxonomy;跨控制器;ArduPilot/HITL) |

---

## 4. 做过的实验(逐里程碑:做了什么 + 发现)

**M0**:SIH-RAPTOR 板级、经典起飞到 Hold → 飞行中切 RAPTOR(mode_id 23)→ ulog。**发现**:RAPTOR 有 stale/missing setpoint guard,缺 setpoint 时合成 hold reference,不产生 active-motor NaN(NaN 只在未用通道)。→ 证伪"缺 setpoint→NaN"假设。

**M1**:X500 v2 在 SIH 落地、参数化 offboard 任务、ULOG 指标流水线、四象限 runner、频率对齐。**核心发现(源码级)**:RAPTOR 推理前裁剪 position error ±0.5m、velocity error ±1.0m/s。四个手工锚点(大 step、5Hz 正弦、极端 Lissajous)全部非 primary_bug。

**M2**:统一安全包络(替代 per-θ inf 缺省)、经典 baseline 去 offboard-基建-failsafe 污染、controllability matrix、MAP-Elites、噪声地板。**8 eval,1 raw 候选,3 种子确认未复现 → 0 confirmed**。多种子确认协议被证明必要。

**M2.5**:共享 EKF/GNSS 估计污染注入(`SENS_GPS0/1_DELAY`+`EKF2_DELAY_MAX`、GPS 噪声/门限、`EKF2_TAU_*`、`EKF2_IMU_POS_*`,走 PX4 参数、SIH 兼容、两控制器共享);修复 4x 早停。**delay 梯度 0/60/.../300ms + harsh probe 全 boring_both_safe,0 confirmed**。harsh probe 里 RAPTOR 比经典更稳。4x 仅 triage(没过噪声地板),confirm 须 1x。

**M2.6**:攻不设防通道。源码确认只裁 position/velocity,姿态/角速度原值直入。用 `IMU_GYRO_CUTOFF` × 高 TWR 扫描,重测噪声地板 v2。**8 个 1x 点全 boring_both_safe,0 confirmed**。**埋了个信号**:高 TWR 2.3 下 RAPTOR RMS 0.787 vs 经典 0.420(quality 2.295)——但 **D3 后证为噪声**。教训:`IMU_GYRO_CUTOFF` 是良性对称滤波(只延迟正确信息),非对抗污染。

**M2b-1**:建**对抗性 uORB 状态注入 shim**(`patches/px4/m2b_state_shim.patch`):对 `vehicle_local_position` 速度(EKF2Selector)、`vehicle_attitude`(EKF2Selector)、`vehicle_angular_velocity`(VehicleAngularVelocity)注 delay/bias/noise/NaN/Inf,param-gated(`M2B_EN/START/END/*`),公平打共享 topic。**结果**:velocity-delay 10/20/30ms 公平触达但全 boring(30ms 有微弱 RAPTOR-worse);NaN 探针无 active-motor NaN/RPM defect;**两个 Inf timeout 当时记为 harness failure(D2 已查清)**;状态 MAP-Elites 实际只跑 8 eval(105s/eval @4x 串行,120-eval 需多小时),best 4x elite 在 1x 确认掉到 0,**0 confirmed**。

**M2b-1 诊断(本轮,D1/D2/D3)**:见 §5。

---

## 5. 三项诊断的硬结论(本轮最有价值)

**D1 — 测的是什么模型**:确认是真 PX4/RLtools RAPTOR artifact。
- **实际 22-D policy 输入**:位置误差(3,裁 ±0.5m,target-yaw 帧)+ 姿态(9,四元数展平成 3×3 行主序旋转矩阵)+ 线速度误差(3,裁 ±1.0m/s,target-yaw 帧)+ 角速度(3,body/FLU,**无裁剪**)+ 上一动作(4,一步历史)。`raptor_input` 日志是 17 字段,RLtools 把四元数展成 9 维旋转矩阵 → 网络看 22 维。
- **动作 4-D**,`(action+1)/2` 映射到 `actuator_motors.control[0..3]`,Crazyflie remap,未用槽位 NaN。
- **网络**:Dense(22→16,ReLU) → GRU(16) → Dense(16→4);**stateful,激活时隐状态清零**。`ACTION_HISTORY_LENGTH=1`,`OUTPUT_DIM=4`,checkpoint `logs/2025-04-19_16-16-17`,2084 参数。
- **关键**:无 accel 输入**与论文主观测空间一致**(论文里 accel 进观测是 future work);**但论文 supplementary 的 accel/IIR velocity-delay 缓解路径不在此 PX4 artifact**。→ 攻击面要基于这个实际 22-D 观测来推,别假设 accel/S2 路径;velocity-delay 的论文失败/缓解故事不能一对一搬过来。

**D2 — Inf timeout 根因**:旧 `velocity_inf`/`attitude_inf` timeout **不是 PX4/EKF crash 或 lockstep stall**(旧 console 证明 PX4 仍能 `listener`、`logger status: dropouts 0`、正常 `shutdown`,nav_state 14、failsafe False),是 **harness/task 超时**。新 rerun 四个单控制器跑都 `timeout_observed=false` 完成,**但暴露更严重问题:Inf 根本没进 `vehicle_local_position`/`vehicle_attitude`/`raptor_input`**——shim 的 NaN/Inf 注入路径静默失败。→ 这条线连有效测试都算不上;**信任任何 null 前必须先修 shim 送达验证**。

**D3 — 低噪声差分退化**:换正确的**比值度量**(每控制器各自相对自己多种子无扰动 baseline 的退化倍数;差分退化 = 经典≈1 且 RAPTOR≫1),低噪声 regime(标称 TWR 1.743、1x、稳态窗 28–52s、5 seeds、4 scenario)。
- baseline RMS ratio stdev:经典 0.33、RAPTOR 0.27(**噪声本底很大**)。
- 最佳 `velocity_delay_030ms`:RAPTOR median 1.236× vs 经典 0.965×(delta 0.27);`velocity_noise` delta 0.34 但主要因经典降到 baseline 以下、RAPTOR 仍在 baseline 散布内;`gyro_bias` delta 仅 0.085。
- **无任何点满足"经典≈1、RAPTOR≫1 且稳定高过本底"。信号 < 噪声。连续退化线不能当 FSE 结果。**

---

## 6. 关键技术发现(智力内核,可发表资产)

**RAPTOR 防御地图(源码 + 实验)**——为什么朴素攻击失效:
1. 观测误差裁剪:position ±0.5m、velocity ±1.0m/s(M1,源码)→ setpoint 幅度攻击死。
2. 只裁 position/velocity;姿态(9)、角速度(3)原值直入(D1,源码)→ 不设防通道在这俩。
3. 裁剪裁幅度不裁延迟 → velocity-delay 理论上绕裁剪,但**论文说 z 振荡只在非 EKF 平台**(你在 EKF 平台,且 EKF 吸收延迟)→ 这条在你的 SITL 结构上打不中。
4. stale/missing setpoint guard(M0)→ 缺 setpoint 攻击死。
5. GPS delay 被 EKF 吸收(M2.5);`IMU_GYRO_CUTOFF` 是良性对称滤波(M2.6)→ 都不是对抗污染。
6. NaN/Inf:无 active-motor NaN defect(M2b-1);Inf 注入路径静默失败(D2)→ 模块输入处理这条**尚未有效测过**。

**论文 OOD 地图(训练分布 S5–S27,supplementary)**——哪里分布内、哪里 OOD:
- **TWR ~ Uniform(1.5, 5)**;你测的 2.3 在分布正中(故高 TWR 退化是噪声)。质量 0.02–5kg;力矩-惯量比 40–1200;电机延迟 T↑[0.03,0.1]/T↓[0.03,0.3];扰动力 σ_fext 3σ 封在 surplus thrust 30% 内。终止边界:位置 20·l_arm、线速 2m/s、角速 35rad/s。
- **DR 显式排除(→ 干净 OOD 候选)**:四电机推力曲线相同(S9)、对称 X、质心居中、平面四旋翼、刚性机架。→ **单电机退化/推力不对称、质心偏移**是论文没覆盖的 OOD(需 Gazebo)。
- **论文已测的 OOD 都鲁棒**:TWR=12(z 误差大但仍稳=**退化非崩**)、柔性机架、混合桨、戳>90°、15m/s 相对风、4.5m/s 激活。
- **论文承认的局限(Discussion)**:固件延迟 sim2real(#1)、overindex 线速度(#2)、DR 范围/TWR(#3)、无 lookahead 轨迹超调(#4)——**多为退化非崩溃**。

**D1 确认**:测的是真 artifact,故 null 非"测错模型"。

---

## 7. 当前证明了什么 / 没证明什么

**已建成且验证**:差分 oracle(C2,产全四象限、剔基建污染、多种子确认挡假阳)、免训可复现平台(C4)、对抗 uORB 注入 shim(M2b-1)、RAPTOR 防御 + 论文 OOD characterization(§6,独立于 bug 数量)。

**未达成**:RQ1 存在性(0 confirmed primary_bug)、RQ2 搜索有效性(无 baseline 对照=M3)、RQ3 失败分类(无失败可分)。

**诚实状态**:六轮证据**收敛**——RAPTOR 在 SITL 可公平测的范围内确实鲁棒(论文证据 + 你的 null + D3);连续退化线统计不成立(D3);模块输入处理这条尚未有效测过(D2 shim 静默失败)。**这不是"RAPTOR 鲁棒"的最终结论,而是"当前 RAPTOR 证据不支持再开大搜索"。**

---

## 8. 为什么转向是数据驱动而非认输

六轮连起来是**证据闭合**不是悬而未决:飞行行为分布内鲁棒(论文+null),OOD 多为退化(论文);连续退化低噪声下不成立(D3);模块集成层 Inf 不是真 crash 且工具静默失败(D2);测的确是真模型(D1)。继续压 RAPTOR 当前空间期望值已低。而**方法/平台资产不依赖 RAPTOR 一定要崩**——转 mc_nn_control 是把六轮 null 转化为正资产("方法找到 bug + RAPTOR 作鲁棒对照")的最干净路径。

---

## 9. 下一步详述(给新会话)

**第 0 步(前置,必做):修 shim 送达验证。**
- D2 证明注入会静默失败。让 `m1_diff_runner.py` / shim 在每次注入后**强制 ULOG 自检**:目标共享 topic(及 `raptor_input` 对应维)确实带上了注入的污染(delay/bias/noise/NaN/Inf);未送达则 **fail-loud**(报错、标记该 eval 无效),不得静默记为 null。扩展 `m2_5_estimator_fairness.py` 已有的 touch 校验到所有 profile,尤其 NaN/Inf。**这是信任后续任何 null 的前提。**

**第 1 步(主线):转 mc_nn_control 为主目标。**
- 先**调研 mc_nn_control**(新会话可先查):它的观测/动作空间、有没有类似 RAPTOR 的输入裁剪、是否 stateful、PX4 里成熟度、预训练网来源、如何在 SITL 跑。PX4 docs(`docs/en/neural_networks/`)+ 源码 `src/modules/mc_nn_control/`。
- 复用全套工具(差分 oracle、统一包络、shim、MAP-Elites)。先把 M0/M1 等价的 bring-up + oracle 在 mc_nn_control 上跑通,再上搜索。
- **重点假设**:mc_nn_control 无观测裁剪 → setpoint 幅度类攻击可能直接有效(在 RAPTOR 上死的维度在这里可能活)。先验证这个。
- 顺带:M0 证伪的"缺 setpoint→NaN"在 mc_nn_control 上重测(它不一定有 RAPTOR 的 guard)。

**第 2 步(可选,RAPTOR 窄实验):激活瞬态。**
- 仅此一个:高角速率+大姿态+受扰瞬间切入 RAPTOR,打隐状态未收敛窗口(Fig 3 ~100–200 步收敛)。经典无此窗口。SITL 可做,论文只测良性(4.5m/s 平飞激活)。**不开 Gazebo plant 不对称大摊。**

**之后(若 mc_nn_control 出 bug)**:M3(random/grid baseline 证明制导有效性 + 消融 + taxonomy)→ 跨控制器泛化 → Phase 3(ArduPilot/HITL/缓解)。

---

## 10. 风险 / 约束 / 论文景观

**约束**:SIH/L2F **无气动阻力**(运动方程力项仅 R(q)Σf+f_ext+g)→ 高速气动类复现不出。4x 仅 triage(没过噪声地板)。电机/传感器故障 SIH 支持存疑,plant 不对称类需 Gazebo。二值 oracle 会吞掉连续退化(但 D3 已证退化线不成立)。

**论文景观(双轨,诚实)**:框架定位"差分测试方法 + 首个对部署级学习型飞控的系统安全评估",对两种结局都成立。
- 二值 primary_bug = 头条 upside,**最现实来源现在是 mc_nn_control**(软目标),而非 RAPTOR。
- RAPTOR 部分 = "系统刻画了一个被严格验证的鲁棒 foundation policy 的防御边界 + 解释为何朴素攻击失效",配源码级层防御 + 论文 OOD 地图,**独立于 bug 数量的保底贡献**。
- 保底:差分 oracle + 免训平台真填空白(NNCS 证伪都是玩具系统、无内建差分;UAV fuzzing 假设理想执行器)。

**给新会话的三个待定问题**:(a) 认同转 mc_nn_control,还是先穷尽 RAPTOR 激活瞬态?(b) 修 shim 送达验证作为前置,同意否?(c) mc_nn_control 的观测空间/裁剪/成熟度——先查清再写下一份 prompt。

---

## 11. 已交付的 prompt 与文档(在 outputs / 仓库)

历轮 agent-prompt(markdown):phase1 环境、M0、M1、M2、M2.5、M2.6、M2b-1 对抗注入、M2b-1 诊断;另有 `AGENT.md`(repo onboarding)、细化版实验章节、本项目状态/交接文档。仓库内报告:`docs/M0.md`~`docs/M2b_1.md`、`docs/M2b_1_diagnostics.md`、`docs/m2b_1_diag_d1/d2/d3` 证据目录。
