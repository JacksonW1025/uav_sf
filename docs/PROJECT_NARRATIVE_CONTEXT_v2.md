# 项目叙事与上下文文档 v2 — 学习型 UAV 飞控的场景模糊测试

**用途**：切换对话时的完整上下文 + 给执行 agent 的叙事参考。读完即可接续，无需回溯历史对话。
**取代**：v1（`PROJECT_NARRATIVE_CONTEXT.md`，FUZZ-1c 之前）。**本版新增 A 路线的最新结果：严差分已确认 + 结构性失效区观察。**
**Date**: 2026-06-25
**Repo**: `github.com/JacksonW1025/uav_sf`，工作区 `/mnt/nvme/uav_sf`（容器内）。PX4 固定 `main@3042f906abaab7ab59ae838ad5a530a9ef3df9a6`（v1.18 alpha）。

---

## 0. 速览（TL;DR）

**Idea**：学习型低层飞控（PX4 Neural Control、Science Robotics 的 RAPTOR 基础策略）正进入生产自驾仪却没有系统化安全测试。我们在**同一固件、同一机架、同一任务**下，用搜索（fuzzing）在扰动/机动/故障/指令的场景空间里找学习型控制器的失效，用**经典控制器当内建差分 oracle**（经典 safe ∧ 学习型 unsafe）作为闭环控制的失效归因。

**当前状态（A 路线已硬性收官）**：
- **严差分已确认（A 路线的硬结果）**：在 mode-23 中途交接的剧烈状态下，找到 **4 个干净的 `primary_bug`**——经典 **S0 干净恢复** ∧ `mc_nn_control` **S3 失控翻机**（>90°、>8 rad/s），对齐残差紧、基建污染已剔除、对称公平性可辩护。**idea 不再是"勉强成立"，是已落地、可辩护。**
- **一个比 4 个差分点更深的观察**：`mc_nn` 的失效区**在切换姿态上非单调**（48° 翻、47° 恢复、39° 翻、33° 恢复），而经典在整个 16°–49° 区**一致 S0**。**注意**：该扫描每点的 wind/rate/approach 参数都在变（非干净一维扫），故"是流形覆盖孔洞、还是高维边界、还是风敏感"**尚未分辨**——但**无论哪种，mc_nn 存在一个经典所没有的结构性失效区**，这是 catastrophic-differential 之外、关于失效**结构**的发现。

**两条关键方法论教训（重塑了 contribution）**：
> **(i) 一个_可靠_的差分 oracle 需要三个卫生机制**：**对齐切换状态**（groundtruth 触发）、**分级失效严重度**（受控 vs 失控）、**剔除基建污染**（offboard failsafe 冒充经典 unsafe）。朴素差分**既会过度声称**（FUZZ-1：状态没对齐的 confound，假 primary bug）**又会漏报**（FUZZ-1b：二值检测器把"经典受控失败"和"mc_nn 翻机"都记成 unsafe → 误判 too_hard）。**这三个机制本身就是方法贡献**——它们才让差分 oracle 可信。
> **(ii) 两个产线学习型控制器对"大误差/幅度"类扰动都鲁棒**（RAPTOR 靠观测裁剪、mc_nn 靠学到的优雅大误差响应，且 mc_nn 对幅度比经典**更**鲁棒）。catastrophic differential 不在粗粒度坠毁阈值（两者易一致），而在**切换瞬态 + 失效结构**。

**下一步**：A 路线在本文档锁定。转 **B 路线（多 oracle）**，用更丰富的 oracle **刻画 mc_nn 失效区的结构**——第一发是**变形/对称 oracle 瞄准 FUZZ-1c 那条非单调带**（检验非单调是否为对称破缺/流形覆盖不均的显影），配一个**受控密扫**来分辨失效区结构。

---

## 1. 核心 Idea / Thesis

测学习型控制器的根本难点是 **oracle 问题**：要判它"飞错了"，须先知道"正确飞行长什么样"，而任意扰动下的绝对正确性极难规约。

**关键想法**：PX4 让经典与学习型控制器在**同一固件**共存、可切换。同机架/同任务/同扰动下，若**调好的经典守住、学习型失败**，则该失败**学习型特有**——归因靠结构、不靠手搓正确性规约。在此之上用 fuzzing 搜这些失败。**A 路线证明这个 oracle 真实有效**（拿到干净严差分），**但前提是上述三个卫生机制**。

**扩展（B 路线）**：经典差分只是"判定正确飞行"的一种方式。一个学习型控制器的"bug"不一定是坠毁、不一定需要经典对照（可以是违反控制性质、破坏对称性、对微扰异常敏感）。我们因此把"经典差分"扩成**多 oracle**，经典差分是其中一个（已验证有效、但只覆盖"灾难性失控"这一类）的组件。

---

## 2. 理想化 Contribution

### 2.1 原始 contribution（方法稿 C1-C5，已据实修订）
- **C1**：学习型 UAV 飞控的差分场景模糊测试**问题表述**。
- **C2（验证有效，但内涵升级）**：**可靠的内建跨控制器差分 oracle**——不只是"经典 safe ∧ 学习型 unsafe"，而是**配齐对齐切换状态 + 分级严重度 + 基建去污染**才可信的版本。朴素差分既过度声称又漏报（见 §0(i)）。这三个机制是把差分从"脆弱"变"可辩护"的关键，也是 NNCS 证伪（玩具基准、无差分）与 UAV 场景 fuzzing（理想执行器、二值崩溃 oracle）都给不出的。
- **C3**：面向学习型控制的**搜索反馈/制导**（分歧度 fitness，NSGA-II/MAP-Elites），含"朴素搜索/手挑场景搜不到"的消融。
- **C4**：**免训、可复现的测试平台/基准**，实例化在两个真实 shipped 控制器上。
- **C5**：学习型控制器**失效分类**与缓解（安全监控 / envelope guard / fallback-to-classical）。

### 2.2 经验头条结果（A 路线已拿到）
- **严差分存在且干净**：剧烈中途交接下，经典 S0 恢复、mc_nn S3 翻机，4 个可复现匹配点，基建归因清晰、对称公平。
- **结构性失效区**：mc_nn 的失效在切换态上非单调，经典一致恢复——学习型有经典所没有的结构化失效区（结构待 B 路线密扫/对称检验分辨）。
- **反直觉发现**：学习型控制器对幅度类扰动可能比经典级联**更**鲁棒（GATE-3 实测：mc_nn 标称跟踪更紧、对大误差退化更小）。

### 2.3 演进后的论文主张（建议）
**头条 = "面向集成进固件的学习型飞控的多-oracle 场景测试方法"**：可靠差分 oracle（含三个卫生机制）+ 性质/规约 + 变形/对称 + 鲁棒性 oracle 组成的套件；用它**系统刻画两个真实 shipped 学习型控制器（RAPTOR、mc_nn）的失效边界与根因**（RAPTOR 裁剪致鲁棒 / mc_nn 无裁剪却对幅度更鲁棒 / mc_nn 在剧烈交接下的结构化失控）。**价值不押在单个 bug 上**——但 A 路线已先拿到一个硬的差分锚点。

---

## 3. Related Work（六根轴，定位 gap）

沿两轴：**(i) 是否建模/扰动控制器闭环动力学**；**(ii) 被测对象是经典控制软件、状态机，还是学习型控制器**。

- **(a) UAV 障碍/场景 fuzzing 与路径规划器测试**：DPFuzzer（ICSE'25）、SBFT CPS-UAV 簇（CAMBA/TUMB/WOGAN-UAV/DeepHyperion-UAV/AmbieGen/TAIiST）、SwarmFuzz。**共性**：聚焦几何/障碍、假设理想执行器、不测低层控制器、无学习型脆弱性概念。
- **(b) RV 控制/配置/策略 fuzzing**：RVFuzzer（USENIX'19，控制不稳定 oracle）、LGDFuzzer（ICSE'22，学习引导 GA 找配置 range-spec bug）、PGFuzz（NDSS'21，**MTL 安全策略 oracle + policy distance 引导，156 新 bug**）、ADGFuzz（参数交互）、IMUFuzzer（ASE'25）。**共性**：被测是经典控制软件；无 learned-vs-classical 差分。**PGFuzz 的"性质即 oracle"是 §7 性质 oracle 的直接模板**（ArduPilot→PX4 移植仅 6.3 小时）。
- **(c) 模式/状态/failsafe 语义 fuzzing**：SaFUZZ（ICSE'26，状态机语义 fuzzing）、HIFuzz。**共性**：作用在状态机/模式层，不下沉控制器层。
- **(d) 赛博-物理不一致与神经控制器证伪**：CPI（CCS'20）；ARCH-COMP AINNCS、S-TaLiRo/Breach/ARIsTEO（证伪）、NNV/Verisig/CORA（可达性）。**最直接前作**，但基准是玩具系统、可达性在真实 6 自由度固件级不可扩展、无内建差分 oracle。
- **(e) 学习型 UAV 控制与基础策略**：RAPTOR（Science Robotics 2026）、NTNU PX4 神经模式（arXiv:2505.00432）、Zhang 极端自适应四旋翼（T-RO 2025）、Neural-Lander。**共性**：**构造**学习型控制器，**都不提供系统化方法找它们相对经典在哪儿失败**。
- **(f) 自动驾驶 ML 测试（方法迁移源，权重上升）**：成熟的 ground-truth-vs-actual 差分、metamorphic、对抗鲁棒、OOD 检测。我们迁移其**差分/蜕变/鲁棒**精神到 UAV **闭环控制**：失败是失稳/超调/振荡/饱和/NaN/failsafe 交互等动力学后果。多 oracle 套件本质是把 AD 的"非崩溃 oracle"带到飞控。

**Gap**：尚无工作系统化搜索扰动/机动/故障场景空间，用**多 oracle（含_可靠_的经典-学习型差分）**找出**集成进固件的学习型飞控**相对经典**特有的失效**并刻画其边界与根因。

---

## 4. 实验设计

### 4.1 被测对象（SUT）
同一 PX4（`3042f906`）、同一机架（**X500 v2**，SIH 中按 gz x500 配质量/惯量/几何/推力，保证"经典对所测机体调得好"）、同一任务。两个学习型 backend：
- **RAPTOR**（`mc_raptor`，免训基础策略，22-D 观测/4-D 动作，GRU-16，2084 参数，checkpoint 2025-04-19）。
- **`mc_nn_control`**（PX4 内置神经模式，TFLM，**前馈网** FullyConnected/Relu/Add 无递归，15-D 观测/4-D 动作，内置网 **X500 V2 训练网**）。
- **两者切换路径字节级相同**：`MAV_CMD_DO_SET_MODE main=4/sub=11 → mode_id 23` → 每轮 mode-23 飞行须**正面控制器 ID 确认**在飞哪个。

### 4.2 差分 Oracle + 三个卫生机制（A 路线验证）
**四象限**（同 θ 跑两遍，同机架/种子/注入序列/sim 时间对齐）：`boring_both_safe` / `interesting_not_bug`（学习型更强）/ **`primary_bug`（经典 safe ∧ 学习型 unsafe，只报这类）** / `too_hard_not_bug`。

**让 primary_bug 可信的三个卫生机制**（缺一即过度声称或漏报）：
1. **对齐切换状态**：SIH 无快照/置态 API → **Method A，groundtruth 触发**：mc_nn SIH build 发布 `vehicle_attitude_groundtruth`/`vehicle_angular_velocity_groundtruth`/`vehicle_local_position_groundtruth`，按真值跨阈触发切换，再以 ULOG 真值回匹配取精确切换样本。残差紧（rate 残差均值 ~0.09 rad/s）。**没有它 → FUZZ-1 的 confound（mc_nn 2.6 rad/s vs 经典 0.67 rad/s 假差分）。**
2. **分级失效严重度（替代二值 safe/unsafe）**：**S0 干净恢复 / S1 受控退化 / S2 受控安全失败 / S3 失控翻机（≥90° 或 ≥8 rad/s）/ S4 数值软件 fault**。**关键切分 = 受控（S0-S2）vs 失控（S3-S4）**。差分 primary_bug = 学习型失控（S3/S4）∧ 经典受控（≤S2，理想 ≤S1）。**没有它 → FUZZ-1b 把"经典受控失败"和"mc_nn 翻机"都记 unsafe，误判 too_hard。**
3. **剔除基建污染**：把 offboard 信号丢失 / datalink / RC / 估计器 position-jump 类 failsafe、及 failsafe 指令触地、及切换低于最小可恢复高度，从控制级 severity 判定中剔除（对两个控制器对称施用）。**没有它 → 经典的 offboard failsafe 冒充"经典 unsafe"，掩盖严差分（FUZZ-1c 去污染前正是如此）。**

### 4.3 场景空间 θ（按"裁剪能否约束"重排）
**核心实证**：RAPTOR 推理前裁剪观测误差（position ±0.5 m、velocity ±1.0 m/s）→ setpoint 幅度攻击徒劳；`mc_nn` **无任何裁剪**（GATE-2），但对幅度**比经典更鲁棒**（GATE-3）。θ 三档：**A 档**（状态估计污染、物理失配——裁剪管不到）；**B 档**（时序/接口、**切换瞬态**——A 路线的严差分正出自此）；**C 档**（setpoint 幅度——对 RAPTOR 死、对 mc_nn 也未点亮）。

### 4.4 搜索与反馈
fitness = 分歧度（neural−classical 的跟踪误差差/姿态振荡差/饱和差/time-to-divergence/稳定裕度），约束经典安全。NSGA-II / MAP-Elites（按扰动类型×幅度分箱）。每评估 = 2 次 SITL。硬约束：统一安全包络（cross-θ 可比）、经典 baseline 去基建污染。**A 路线发现**：FUZZ-1 极端角落优先 3 个 eval 即命中，**未用上 MAP-Elites**——剧烈交接是高产族。

### 4.5 研究问题 / 指标 / 有效性
- **RQ1 存在性（A 路线已正面回答）**、**RQ2 搜索有效性（消融 vs random/grid）**、**RQ3 失效刻画与跨控制器泛化**、**RQ4 迁移（HITL/真机/ArduPilot）**、**RQ5 缓解**。
- **噪声地板**【实测】：姿态 max ~1°、tracking RMS ~0.04 m，信号须显著高过。
- **有效性纪律（每轮必守）**：真失败非 harness（`run_error`、console fault scan、到 `mission_end`、触发须真发火、fail-loud 不静默丢）；多种子复现；NN 可归因；reachability 诚实（剧烈态用 relaxed_limits 作 IC-setup，frame 为"动态交接/upset 恢复"，**严差分是"可达交接态"下的、非默认 PX4 包络**）。

---

## 5. 我们做了哪些实验（诚实旅程 + 教训）

### 5.1 RAPTOR 线（7 轮 → 鲁棒）
- **M0（`b1be614`）**：容器 + RAPTOR SITL；经典→切 RAPTOR→ulog。缺-setpoint 被 stale/missing guard 截断、**无 active-motor NaN**（杀掉原 NaN 假设）。
- **M1（`6c944b9`）**：四象限 MVP。**核心发现：观测误差裁剪 ±0.5/±1.0 使 setpoint 幅度攻击失效**（四锚点全非 primary_bug）。重排 θ A/B/C 档。
- **M2/M2.5/M2.6/M2b-1**：制导搜索 + 统一包络 + baseline 去污染 + MAP-Elites + 估计污染 + 陀螺×TWR + 对抗 uORB shim。全 0 confirmed。M2.6 高 TWR 信号**后证为噪声**（假阳教训）。
- **诊断 D1/D2/D3**：D1 确认真 RAPTOR artifact（22-D/GRU-16/2084 参数）；D2 旧 Inf 是 **harness 超时非 crash** + **NaN shim 静默失败**（旧 null 无效）；D3 连续退化统计不成立。
- **RAPTOR 收尾**：修好 shim 送达后 RAPTOR 消费 NaN/Inf **不产生 NaN 电机指令**；Gazebo plant 不对称无 primary bug（-50% 两者都崩=too_hard）；激活瞬态到 ~43°/2.3 rad/s 两者 flight-safe。**0 confirmed。RAPTOR 鲁棒，很大程度因为裁剪。**

### 5.2 mc_nn_control 线（GATE-1/2/3）
- **GATE-1（`b0121ee`）**：mc_nn 存在、零训练跑通、内置网=X500 V2、SIH bring-up、mode 23。**正面 ID 确认**（228 Hz 推理、`network_output`=`actuator_motors`、`raptor_input` 不存在）——关掉"假 NO-GO"。
- **GATE-2**：**mc_nn 无任何观测/误差裁剪**；15-D 观测；无 previous action；**前馈非 stateful**；offboard setpoint **无 stale timeout**；缺失 setpoint 多 reset/default 不 NaN。0.495≈0.5 是瞬态非 clamp。
- **GATE-3（`a8dd59b`）**：position-error 幅度 3 锚点 **NO-GO**。**反转发现：mc_nn 对幅度比经典更鲁棒**（基线 RMS 经典 0.49 > mcnn 0.38；退化倍数 mcnn < classical）。

### 5.3 FUZZ 线（真 fuzzing：差分降为分类器、宽检测器 → A 路线硬结果）
模式切换：差分**不再做前置门**，检测器放最宽（mc_nn 任何 flight-unsafe / 网络或电机 NaN-Inf / PX4 assert-crash-hang），经典**事后**分类。
- **FUZZ-1（`4685b96`）**：极端角落优先，3 eval 命中。`corner_r6_f045_w6`：mc_nn 翻机（180°/24 rad/s/触地）3/3，经典 flight-safe 3/3。真崩非 harness。**但 confound**：切换态没对齐（mc_nn 2.6 rad/s vs 经典 0.67 rad/s）→ 差分未证实。**教训：朴素差分会_过度声称_。**
- **FUZZ-1b（`345d2c6`）**：groundtruth 触发对齐切换态。匹配后经典**也** failsafe+ground（但 **did not tumble**，受控下降）→ DOWNGRADED。向下扫**角速率**到 41.5° 未找到干净点。**两个问题**：二值检测器抹平质差；只降角速率、姿态钉在 41-48°、没进经典存活的 43° 区。**教训：朴素差分会_漏报_。**
- **FUZZ-1c 严重度扫描（`301f564`）**：上**分级 severity** + **降姿态从 ~60° 穿过 43° 到 ~16°** + 修 harness 触发。**CLEAN_DIFFERENTIAL（宽口径）**：4 对 classical=S2 ∧ mc_nn=S3；低区测到（最低 mc_nn S0 @ 16.4°/0.48）；一个 no-wind 低桶诚实标 UNTESTED_TRIGGER_NOT_FIRED。
- **FUZZ-1c 去污染重判（`65240a5`，A 路线硬结果）**：对称去污染判据重判 8 对 ulog（不重跑）。**STRICT_DIFFERENTIAL_CONFIRMED**：
  - classical 的 S2 是**基建污染**——8 条分支终态**不变**：`vehicle_status.failsafe` + nav `OFFBOARD→AUTO_RTL` + `offboard_control_signal_lost` 在 failsafe 前 ~0.012 s 拉高，6.82-9.42 s 后才触地，**failsafe 在 73.9-78.3 s 触发、与切换 severity 无关**（severity-不变 = 强基建签名）。
  - 去污染前 2 s 经典**已稳**：max roll/pitch ≤17.31°、max rate ≤0.20 rad/s、hover 误差 ≤1.17 m、min AGL ≥2.39 m——经典救回来了，是 offboard 信号丢失把它 RTL 落地。
  - **4 个干净严差分**（pair 1/2/4/5）：控制级 classical=S0 ∧ mc_nn=S3。
  - **对称公平性**：同一判据改了 classical、**没救 mc_nn**——mc_nn 的 S3 在失控前无基建终态、控制窗口里就是 >90°/>8 rad/s 真 tumble。审稿人驳不倒。

### 5.4 结构性失效区观察（比 4 个差分点更深，但需密扫分辨）
去污染后按 mc_nn 排：S3 @ 48.8/47?/40.8/39.0（翻），S0 @ 47.0/33.9/18.7/16.4（恢复）；**经典在所有点 S0**。**mc_nn 失效在切换姿态上非单调**（48° 翻、47° 恢复、39° 翻、33° 恢复），经典一致恢复。
> **诚实 caveat**：FUZZ-1c 每点的 **wind/rate/approach 参数都在变**（非干净一维扫；如 47° 恢复点 wind=0、48.8° 翻机点 wind=6）。故"是流形覆盖孔洞 / 高维边界 / 风敏感"**尚未分辨**——需**受控密扫**（固定其它、单变姿态，每点多种子）来定结构。**但无论哪种，mc_nn 有经典所没有的结构化失效区**——这是 catastrophic-differential 之外、关于失效**结构**的发现，且是 B 路线的明确靶子。

### 5.5 旅程总教训（驱动 §6）
1. 两个产线学习型控制器对大误差/幅度类都鲁棒；catastrophic differential 在**切换瞬态 + 失效结构**，不在粗粒度坠毁阈值。
2. **差分 oracle 真实有效（A 路线严差分），但可靠性依赖三个卫生机制**——朴素差分既过度声称（FUZZ-1）又漏报（FUZZ-1b）。
3. 二值检测器会抹平真实质差（受控失败 vs 失控翻机）。
4. → 经典差分已验证有效但只覆盖"灾难性失控"一类；**把目光放大、引入多 oracle 刻画失效_结构_。**

---

## 6. 从单 oracle 到多 oracle（B 路线）

**为什么仍要多 oracle**（即便差分已成功）：catastrophic differential 只覆盖"经典稳/学习型失控"这一类粗粒度失效。学习型控制器的差异更多活在**没到坠毁的行为、失效边界的_形状_、对称性、流形覆盖**里——FUZZ-1c 那个非单调失效区正是例证，而差分 oracle 本身无法解释它的**机制**。这正是端到端 vs 规则化智驾：差异在边角/分布漂移/平滑性。

**多 oracle 套件**：
- **差分 oracle**（已验证有效 + 三个卫生机制，是一个组件 + 事后分类器/标定基线）。
- **性质/规约 oracle**（PGFuzz 式 MTL）：定义正确飞行**是什么**（稳定、不持续振荡/极限环、控制量有界平滑、不抖振、settling、无稳态偏差），搜违反——不需经典失败。
- **变形/不变性 oracle**：场景绕偏航旋转/镜像 → 响应应相应变换。经典由构造对称，神经破对称 = 干净 NN-specific bug，不需经典失败。**直接检验 FUZZ-1c 非单调是否为对称破缺/流形覆盖不均。**
- **鲁棒性/平滑性 oracle**：搜神经局部非 Lipschitz（微扰 → 控制量大跳）的脆弱状态；离线版直接探策略函数、不用仿真。
- **更强参照差分**：用 MPC/可达性认证"此状态本可恢复"——A 路线已用 relaxed-limits IC-setup + 基建去污染部分达到了"经典本可恢复"的认证效果。

---

## 7. Oracle 排序（按可行性 + 可信性，大 → 小）

> 标注**可行性**（实现成本）与**可信性**（结果作 NN-specific bug 的可辩护度）。更看重结果可信度则④升；更看重快则①②③领先。

1. **变形/对称（equivariance）** — **可行性高 / 可信性高**。复用现有 harness，旋转/镜像场景比响应即可。经典对称由构造，任何破缺无歧义 NN-specific、无 too_hard。**B 第一发，且现在有具体靶子：检验 FUZZ-1c 非单调失效区是否对称破缺/流形覆盖不均。**
2. **性质/规约（PGFuzz 式 MTL）** — **可行性中高 / 可信性高**。PGFuzz 在库里、移植 6.3 小时、机制可借。性质违反 well-defined（156 bug），不需差分。成本在性质定义。
3. **鲁棒性/平滑（离线对抗敏感度）** — **可行性高（离线）/ 可信性中高**。离线探网络雅可比极便宜。非 Lipschitz 而经典平滑是干净 NN-specific 性质。**可信性缺口**：离线尖峰不自动等于闭环安全问题，最强版要连到闭环后果。也能解释非单调失效区。
4. **更强参照差分（MPC/可达性认证）** — **可信性最高 / 可行性最低**。建 MPC/可达性是真功夫。让"本可恢复 → 神经失败"铁证、彻底分开 too_hard。A 路线已用 relaxed-limits+去污染拿到轻量版。**stretch/后期。**
5. **灾难性差分（现有）** — **可行性高 / 可信性高（_配齐三个卫生机制后_）**。**A 路线已验证它有效**（严差分）；朴素版脆弱（过度声称+漏报）。**保留为已验证组件 + 标定基线，覆盖"灾难性失控"一类。**

**B 建议起点**：①变形/对称瞄准 FUZZ-1c 非单调带（配受控密扫分辨失效区结构）。

---

## 8. 当前决策 + 下一步

- **A 路线：硬性收官并在本文档锁定。** 严差分确认（4 干净点）+ 基建归因 + 对称公平 + 结构性失效区观察。**不写成论文章节**（本叙事文档即锁定形式）。
- **B 路线：下一步。** 第一发 = **变形/对称 oracle 瞄准 FUZZ-1c 非单调带**，并配一个**受控密扫**（固定 wind/rate/approach、单变切换姿态、每点多种子）来分辨该失效区是流形孔洞 / 高维边界 / 风敏感。这把 A 的发现与 B 的新 oracle 缝成一条线。
- **已定口径**：差分 primary bug 宽口径（受控失败 vs 失控翻机算差分；**A 路线进一步拿到了严口径 S0-vs-S3**）。
- **暂缓**：给 SIH 打补丁做直接置态（Method A 残差已够紧）。
- **悬而未决**：工具名（`[TOOL]`，候选 TwinFuzz/CtrlDiff/OracleSwap）；目标会议（ICSE/FSE/ASE/ISSTA）+ 窗口；Phase 3 栈优先级（ArduPilot vs Betaflight/Crazyflie）；何时引入真板解锁 RQ4。

---

## 9. 环境 / 复现 / 工程约定（给 agent）

- **容器入口**：`sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<name> ./docker/run.sh bash -lc "..."'`。镜像 `uav_sf:phase1`（`ubuntu:24.04` arm64，CPU-only）。常规路径用 `sg docker`、避免 sudo（密码不入库）。Docker/ROS2 坑见 `AGENT.md`。
- **PX4**：固定 `3042f906`，源码 `external/PX4-Autopilot`（gitignored）。enable：mc_nn `CONFIG_LIB_TFLM=y`+`CONFIG_MODULES_MC_NN_CONTROL=y`；RAPTOR `CONFIG_MODULES_MC_RAPTOR=y`+`CONFIG_LIB_RL_TOOLS=y`。board `px4_sitl_mcnn_sih` 同编 mc_raptor（生成 M2b shim 参数定义）但 `MC_RAPTOR_ENABLE=false`、RAPTOR 不启动 → **mode-23 飞行须正面 ID 确认在飞 mc_nn**。
- **仓库约定**：`external/PX4-Autopilot`、`ros2_ws` 被 gitignore → PX4 改动以 **tracked patch/overlay + installer**入库（参照 `raptor_sih.px4board` + `install_raptor_sih_board.sh`）；证据落 `docs/`。
- **git 卫生（重要）**：`*.ulg`/`*.log`/`docs/**/evals/` **已 gitignore，保持 untracked**。commit 只含代码、报告、结构化摘要（JSON/JSONL/criteria/thresholds）。旧 ULOG/blob 历史未做全历史 rewrite；往后 HEAD 不应再跟踪 raw run output。验证：`py_compile`/`bash -n`/tracked `jq empty`/`git diff --check`(+`--cached`)。
- **patch drift（未决）**：`patches/px4/m2b_state_shim.patch` 反向 apply 失败 = external 树与 tracked patch 已 drift。**不影响纯 offboard/groundtruth/ulog-重分析的轮次**；**仅当将来走 shim 注入（velocity/角速率假状态信念）时须先整理 drift**。
- **频率/时序**：`IMU_GYRO_RATEMAX=400`；事件按 sim 时间触发不用 wall-clock；offboard 用 ROS 2 节点。
- **仿真器**：SIH 为主（headless/lockstep/确定性）；Gazebo 仅可视化/电机故障类（SIH 对电机/传感器故障支持未验证，须标注哪些 θ 在哪个仿真器跑）。
- **关键脚本**：`m1_offboard_task.py`（参数化任务，ramp setpoint + 两阶段 approach + 中途切换）、`m1_metrics.py`+`m1_compare.py`（四象限）、`m2_5_estimator_fairness.py`（shim fail-loud 送达自检）、`m2b_state_profiles.py`/`m2b_nan_probe.py`、`mcnn_gate3_position_error_probe.py`、`fuzz1_activation_mcnn.py`、**`fuzz1c_severity_scan.py`（分级 severity + fail-loud 触发 + resume/续跑）**、**`fuzz1c_decontam_analyze.py`（对称去污染重判）**。
- **历轮报告**：`docs/mcnn_gonogo*.md`、`docs/raptor_closeout*`、`docs/fuzz1*`（含 `fuzz1c_severity_20260625.md`、`fuzz1c_decontam_20260625.md`）。最近本地 commit：`65240a5`(去污染严差分)、`301f564`(FUZZ-1c severity)、`6293c35`(AGENT.md)、`345d2c6`(FUZZ-1b)、`4685b96`(FUZZ-1)、`a8dd59b`(GATE-3)、`b0121ee`(GATE-1)、`0cf175b`(RAPTOR closeout)。

---

## 10. References（待补 venue/DOI）

- Wang et al. **DPFuzzer.** ICSE 2025. ｜ Chambers et al. **SaFUZZ.** ICSE 2026. ｜ Kim et al. **PGFuzz.** NDSS 2021.
- **RVFuzzer.** USENIX Sec 2019. ｜ **LGDFuzzer.** ICSE 2022. ｜ **IMUFuzzer.** ASE 2025. ｜ **ADGFuzz.**
- Choi et al. **CPI.** CCS 2020. ｜ ARCH-COMP AINNCS；S-TaLiRo / Breach / ARIsTEO；NNV / Verisig / CORA.
- Eschmann, Albani, Loianno. **RAPTOR: A Foundation Policy for Quadrotor Control.** Science Robotics 2026 / arXiv:2509.11481.
- Hegre et al. **A Neural Network Mode for PX4 on Embedded Flight Controllers.** arXiv:2505.00432, 2025.
- Zhang et al. **A Learning-Based Quadcopter Controller With Extreme Adaptation.** IEEE T-RO 2025.
- SBFT CPS-UAV Testing Competition（CAMBA / TUMB / WOGAN-UAV / DeepHyperion-UAV / AmbieGen / TAIiST）；SwarmFuzz.
- PX4 v1.17/v1.18 Release Notes；PX4 Neural Network Control / RAPTOR / SIH / System Failure Injection 文档。
