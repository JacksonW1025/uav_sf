# 差分场景模糊测试：用经典自驾仪作为内建 Oracle 发现学习型 UAV 控制器的失效

**Differential Scenario Fuzzing for Learned UAV Flight Controllers — Using the Classical Autopilot as a Built-in Oracle**

工具名（占位）：`[TOOL]`（候选：`TwinFuzz` / `CtrlDiff` / `OracleSwap`，待定）

> **一句话主张（Thesis）**
> 学习型低层控制器正在进入生产级自驾仪（PX4 v1.17 的 Neural Control、Science Robotics 的 RAPTOR 基础策略），但没有系统化的安全测试方法，也没有稳定性保证。我们提出 `[TOOL]`：在**同一自驾仪、同一机架、同一任务**下，把**经典控制器**当作**内建差分 Oracle**，用搜索（fuzzing）在扰动/机动/故障/指令构成的场景空间里，自动找出"经典控制器能安全应对、而学习型控制器失败"的场景。
> *Learning-based low-level controllers are entering production autopilots, yet no systematic safety-testing method exists. We propose `[TOOL]`, which treats the classical controller as a built-in differential oracle and searches the disturbance/maneuver/fault scenario space to find inputs where the learned controller fails while the classical controller remains safe.*

---

## 1. Introduction

### 1.1 背景：学习型控制器进入自驾仪
传统多旋翼自驾仪（PX4、ArduPilot）用一条调好的 PID 级联完成控制：位置 → 速度 → 姿态 → 角速率 → 控制分配（mixer）。近一年，这条级联开始被端到端神经网络替换：

- **PX4 v1.17** 集成了 TensorFlow Lite Micro，可把外部（如 Aerial Gym 中 RL 训练）的网络以 tflite 形式加载，**在飞控芯片上直接替换 multicopter 控制器**，作为一个新飞行模式暴露，随时可切回经典栈（官方标注为 research/bench testing，非生产替代）。
- **RAPTOR**（Science Robotics, 2026）是一个 2084 参数的四旋翼控制**基础策略（foundation policy）**，通过 in-context 适配在毫秒级**零样本**适应 10 个未见过的真实四旋翼（32g–2.4kg，跨电机/桨/机架/飞控），并以 `mc_raptor` 模块的形式在 PX4 中**开箱即用、无需重训**。

它们的共同卖点是**自适应、跨平台、免逐机型调参**。

### 1.2 问题：被部署，却没有被系统化测试
这些控制器有三个共性风险：

1. **没有稳定性保证。** 它们是 RL/学习得到的策略；RL 控制器以"对单一环境过拟合、在很小的差异（如 sim-to-real gap）下就失效"著称。
2. **安全工程缺位。** 以 RAPTOR 为例，其论文本身被指出**缺少推荐的安全监控（envelope guards、action-rate limiters）、缺少标准化的激活/停用与模式切换流程、风下与估计误差下的鲁棒性细节不清**——这是部署侧的明确空白。
3. **已经出现真实失效。** PX4 神经模块文档已记录一个**经典控制器不会有、学习型控制器会有**的失效：在收不到 trajectory setpoint 时，网络有时输出 **NaN 电机指令**。

换言之，一个**号称"异常稳定、零坠机、适配一切"的 foundation policy 正在被刷进真实自驾仪**，而我们没有方法回答："它在哪些场景下会崩？"

### 1.3 为什么现有测试方法覆盖不了
- **UAV 场景模糊测试 / 路径规划器测试**（DPFuzzer、SBFT CPS-UAV 竞赛簇）：生成 3D 障碍/几何场景，但测的是**路径规划器**，并假设**理想执行器**；它们既不针对低层控制器，也没有"学习型控制器是否更脆弱"的概念。
- **RV 控制/配置/策略模糊测试**（RVFuzzer、LGDFuzzer、PGFuzz、ADGFuzz、IMUFuzzer）：测的是**经典**控制软件的输入校验、配置范围、安全策略；不针对学习型控制器，没有 learned-vs-classical 的差分。
- **模式/状态/failsafe 语义模糊测试**（SaFUZZ、HIFuzz）：测状态机、模式切换、failsafe 与人机接管，用决策树 oracle；不下沉到控制器层做 learned-vs-classical。
- **形式化 NNCS 证伪与可达性**（ARCH-COMP AINNCS；S-TaLiRo、Breach、ARIsTEO 等证伪；NNV、Verisig、CORA 等可达性）：这是"测神经控制器"的最直接前作，**但其基准是玩具系统**（如悬浮磁铁、无模式切换的设定点跟踪），**可达性在真实 6 自由度、集成进固件的控制器上不具可扩展性**，且**没有内建的差分 oracle**。

### 1.4 核心难点与关键想法
测学习型控制器的根本难点是 **oracle 问题**：要判定它对某个扰动"飞错了"，需要先知道"正确飞行长什么样"——而在任意扰动下的绝对正确性极难规约。

我们的关键想法是把这个难点**消解**掉：

> **经典控制器就是内建的差分 oracle。** PX4 让经典控制器与学习型控制器在**同一固件**里共存、可切换。在**同一机架、同一任务、同一扰动**下，如果**调好的经典控制器守住了安全、而学习型控制器失败**，那么这个失败就是**学习型控制器特有**的——归因靠结构，不靠手搓正确性规约。

在此之上，我们用**搜索（fuzzing）**在扰动/机动/故障/指令空间里高效地找这些失败，用"两控制器轨迹的分歧度"作为搜索反馈。第一版直接实例化在 **RAPTOR**（免训、开箱即用、且是一个其鲁棒性正是核心卖点的 Science Robotics 基础策略——因此它的失败尤其有意义）上，跑在 **PX4 SITL**，不依赖真机；随后再泛化为不限于单一模型、不限于 PX4 的通用方法。

### 1.5 贡献预览
我们提出（C1）面向学习型 UAV 飞控的差分场景模糊测试**问题表述**；（C2）一个**内建的跨控制器差分 oracle**；（C3）**面向学习型控制的搜索反馈**与制导算法（含"朴素搜索搜不到"的消融证据）；（C4）一个**免训、可复现的测试平台/基准**，首次实例化在一个基础策略上；（C5）一份**学习型控制器失效分类**与缓解方向。

---

## 2. Related Work

我们沿两根轴定位现有工作：**(i) 是否建模/扰动控制器闭环动力学**；**(ii) 被测对象是经典控制软件、状态机，还是学习型控制器**。

**(a) UAV 障碍/场景模糊测试与路径规划器测试。** DPFuzzer（ICSE'25）用进化算法 + ERF 生成关键 3D 障碍场景，测试 Ego-Planner/FUEL 等**路径规划器**，并在 threats-to-validity 中明确把"与飞控协调引发的事故"划出 scope。SBFT CPS-UAV 竞赛簇（CAMBA、TUMB、WOGAN-UAV、DeepHyperion-UAV、AmbieGen、TAIiST）在 PX4/Aerialist 任务上添加障碍使 UAV unsafe-close 或 crash。SwarmFuzz 以 GPS 欺骗诱导集群撞上 on-path 障碍。**共性**：聚焦几何/障碍，假设理想执行器，不测低层控制器，更无学习型控制器脆弱性的概念。

**(b) RV 控制/配置/策略模糊测试。** RVFuzzer（USENIX'19）用控制不稳定 oracle 找 input-validation bug；LGDFuzzer（ICSE'22）用学习引导 GA 找配置参数 range-spec bug；PGFuzz（NDSS'21）把安全策略写成 MTL 并用 policy distance 引导；ADGFuzz、IMUFuzzer（ASE'25）分别针对控制逻辑与 IMU 信号注入。**共性**：被测对象是**经典**控制软件；输入/配置/策略 oracle；不针对学习型控制器，无 learned-vs-classical 差分。

**(c) 模式/状态/failsafe 语义模糊测试。** SaFUZZ（ICSE'26）对 sUAS 状态机做语义 fuzzing，聚焦 mode transition / failsafe / 人机接管，用决策树 oracle 与 fault tree；HIFuzz 针对人为模式切换。**共性**：作用在状态机/模式层，不下沉到控制器层做 learned-vs-classical。

**(d) 赛博-物理不一致与神经控制器证伪。** CPI（CCS'20）提出 cyber-physical inconsistency，针对**安全检查代码**的不完整性（range check 近似不了物理）。ARCH-COMP AINNCS 类别及 S-TaLiRo、Breach、ARIsTEO 等证伪工具、NNV、Verisig、CORA 等可达性工具，构成"测/证神经控制器"的最直接前作。**与本工作的区别**：它们的基准是玩具系统、可达性在真实 6 自由度固件级控制器上不可扩展、且没有内建差分 oracle；本工作把 fuzzing + 经典/学习型差分 oracle 带到一个**集成进生产固件、SITL 可跑**的学习型控制器上（必要时可把证伪工具作为搜索后端，但 oracle + 被测对象 + 系统规模才是贡献）。

**(e) 学习型 UAV 控制与基础策略。** RAPTOR（Science Robotics 2026）是跨平台四旋翼控制基础策略，零样本适配多种真机，在 PX4/Betaflight/Crazyflie 等栈中运行；NTNU 的 PX4 神经模式（arXiv:2505.00432）把 Aerial Gym 训练的策略转 tflite 并替换控制级联；Zhang 等的极端自适应四旋翼控制器（T-RO 2025）、Neural-Lander 等也属此列。**共性**：这些工作**构造**学习型控制器（部分带自适应/鲁棒性主张），但**都不提供系统化方法去找它们相对经典基线在哪儿失败**。

**(f) 自动驾驶 ML 组件/差分/蜕变测试（方法迁移源）。** 自动驾驶领域已有成熟的"ground-truth 感知 vs 实际感知差分 oracle""metamorphic 测试"。我们借鉴其**差分/蜕变**精神，但迁移到 UAV **闭环控制**：失败不是感知误分类，而是**失稳、超调、振荡、饱和、NaN、failsafe 交互**等动力学后果。

**Gap。** 据我们所知，尚无工作**系统化搜索扰动/机动/故障场景空间，以经典-学习型的内建差分作为 oracle，找出集成进固件的学习型飞控相对经典控制器特有的失效**。这一格此前空缺。

---

## 3. Contributions

**C1 — 问题表述：学习型 UAV 飞控的差分场景模糊测试。**
我们把"测试集成进自驾仪的学习型低层控制器"形式化为：在固定机架与任务、可变扰动/指令/故障下，搜索使学习型控制器进入不安全行为、而经典控制器仍安全的场景；并提出用 learned-vs-classical 差分作为**闭环控制的失效归因 oracle**。
*We formalize differential scenario fuzzing for learned UAV flight controllers and propose the learned-vs-classical differential as a failure-attribution oracle for closed-loop control.*

**C2 —（头条）内建的跨控制器差分 Oracle。**
我们利用 PX4 中经典/学习型控制器同固件可切换的特性，定义：当且仅当"经典控制器在该场景下安全"且"学习型控制器在同场景下不安全"时判失败。这避免了为学习型控制器规约绝对正确性，是 NNCS 证伪（玩具基准、无差分）与 UAV 场景 fuzzing（理想执行器）都给不出的 oracle。
*We propose a built-in cross-controller differential oracle that flags a failure iff the classical controller is safe while the learned controller is unsafe on the same scenario — sidestepping the need for an absolute correctness specification.*

**C3 — 面向学习型控制的搜索反馈与制导。**
我们设计学习型控制特有的分歧度反馈（跟踪误差差、姿态振荡差、电机饱和差、time-to-divergence、稳定裕度等），驱动多目标搜索（NSGA-II / MAP-Elites）走向"经典守得住、学习型守不住"的**违背承诺区（broken-promise region）**；并以相对 random/grid 的消融证明该空间**朴素搜索搜不到**（即这是一个难的测试问题）。
*We design learned-control-specific divergence feedback driving guided search toward the broken-promise region, with ablations showing naive search is insufficient.*

**C4 — 免训、可复现的测试平台/基准。**
我们把 PX4 SITL + RAPTOR（后续 + mc_nn_control）+ SIH/Gazebo + ROS2 + 故障注入组织成可复现平台，**无需训练即可起步**，并**首次把这类测试实例化在一个基础策略（RAPTOR）上**——其"零坠机/适配一切"的主张使发现失败尤其有意义。该平台本身对正在采用学习型控制的社区有价值。
*We build a training-free, reproducible benchmark instantiated first on a foundation policy (RAPTOR), lowering the barrier for the community to test learned controllers.*

**C5 — 学习型控制器失效分类与缓解方向。**
我们给出学习型 UAV 控制器的经验失效分类（见 §5），并讨论缓解：把发现用于运行期安全监控 / envelope guard / fallback-to-classical 触发——而这些正是 RAPTOR 论文指出的缺口。
*We provide an empirical failure taxonomy of learned UAV controllers and mitigation directions (safety monitors, envelope guards, fallback-to-classical), which the RAPTOR paper itself notes are missing.*

---

## 4. Approach（方法概览）

### 4.1 被测对象（SUT）
同一 PX4、同一机架（第一版钉死 **X500 V2**，因为 RAPTOR/PX4 神经模块均以它为主测平台）、同一任务；两个 controller backend：**经典级联** vs **学习型端到端**（第一版用 **RAPTOR**）。学习型控制器吃状态、直接输出归一化电机指令。标准做法：经典 Position 模式 arm/起飞，**飞行中途切到学习型模式**——这给出天然的差分切换点。

### 4.2 场景表示 θ
一个测试用例是一个有界、物理可行性约束的参数向量：

- **风**：定常 + 阵风的强度 / 方向 / 起止时机
- **质量/惯量/重心偏移**（模拟挂载、抓取、洒水后变化）
- **setpoint 轨迹**：曲率、速度、阶跃幅度、频率
- **setpoint dropout / 延迟**（由 offboard 节点控制）
- **电机故障**：哪个电机、何时、降效程度
- **传感器噪声 / 偏置 / 延迟**
- **切换时机**：在哪个飞行状态切入学习型模式

### 4.3 差分 Oracle（四象限）
同一 θ 跑两遍（经典 / 学习型，同机架同种子），得轨迹 T_c / T_n：

| | 经典安全 | 经典不安全 |
|---|---|---|
| **学习型安全** | 无聊 | 有趣但非 bug（学习型更强） |
| **学习型不安全** | **← primary bug（只报这一类）** | 场景太难，非 bug |

"安全/达标"的判据 = 跟踪误差包络 + 姿态/角速率不发散 + 任务完成。**为什么干净**：不主张学习型控制器的绝对正确性，只主张"调好的经典控制器守住 ⇒ 场景物理可行 ⇒ 学习型也应守住"。次阈值的分歧（超调/饱和/能耗逼近边界）不作 bug，而作搜索反馈。

### 4.4 搜索与反馈
fitness = 分歧度（neural−classical 的跟踪误差差 + 姿态振荡差 + 饱和差 + time-to-divergence + 稳定裕度），约束 classical 安全。用 **NSGA-II**（多目标）或 **MAP-Elites**（按扰动类型 × 幅度分箱，求**多样**失败）。每次评估 = 1–2 次 SITL 运行；用仿真加速因子与确定性 lockstep 提升吞吐与可复现性。

---

## 5. 实验计划（分阶段）

总原则：**先用免训的 RAPTOR 把端到端闭环打通并产出第一批失败，再逐步扩成不限于单一模型的通用方法，最后泛化到 PX4 之外。**

### Phase 1（现在）：RAPTOR + PX4 SITL，不上真机
- **被测**：RAPTOR（`mc_raptor`，免训、开箱即用），X500 V2。
- **仿真器**：**SIH 为主**（内建轻量物理、与 PX4 lockstep、确定性可复现、headless、最快），风用 `SIH_WIND_N/E`；Gazebo 仅用于少量可视化 case。
- **里程碑**
  - **M0**：在 24.04 容器里 build 带 RAPTOR 的 `px4_sitl`，确认能用经典 Position 飞、再中途切 RAPTOR、记 ulog。**复现"缺 setpoint → NaN 电机指令"作为 oracle sanity check**。
  - **M1（Oracle MVP）**：ROS2 offboard 发参数化任务 + setpoint 流；MAVSDK failure 插件注入故障；ulog 解析抽指标；对一个固定 θ 跑经典/RAPTOR 各一遍，算分歧、判四象限。
  - **M2（搜索）**：把 M1 包进 NSGA-II / MAP-Elites，fitness = 分歧度；产出第一批"经典稳、RAPTOR 崩/退化"的 θ。
  - **M3（评估）**：baseline（random / grid / 经典-only 对照）、消融（去掉分歧反馈）、失败分类、每候选多次重复（应对非确定性，SIH 已压低）。
- **回答**：RQ1（存在性）、RQ2（搜索有效性/消融）、RQ3（RAPTOR 失败分类）。

### Phase 2：把它从"测一个模型"扩成"一个方法"
- **加入第二个学习型控制器**：`mc_nn_control`（用其 X500 预训练网，无需自训）。**目的**：证明失败类型**跨控制器成立**、方法**不绑单一模型**。
- 细化反馈/fitness；扩展场景空间；对单个学习型控制器加**蜕变关系**（如缩放/旋转跟踪任务，响应应同样缩放/旋转），补差分覆盖不到的情形。
- **回答**：RQ3'（跨控制器泛化）、方法层面的稳健性。

### Phase 3（后续）：泛化到 PX4 之外 + 真机验证
- 把差分 fuzzing 方法**移植到 ArduPilot**（及 RAPTOR 本就支持的其它栈，如 Betaflight/Crazyflie），论证这是一个**通用的、面向"学习型控制器 UAV 应用"的测试方法**，而非 PX4-specific。
- **sim-to-real / HITL 验证**：待有真实飞控板后再做（HITL 用 `px4_fmu-v6c_neural` / `mro_pixracerpro_neural` 在真板上跑 TFLM/RLtools；或真飞）。在此之前以 **replay 验证**与清晰 scoping 替代，并作为已知局限。
- **回答**：RQ4（迁移性）、RQ5（缓解：安全监控 / fallback 触发）。

### 研究问题（汇总）
- **RQ1 存在性**：是否存在"学习型崩/退化、经典稳"的场景？哪些类？
- **RQ2 搜索有效性（关键）**：分歧制导是否比 random/grid 更快找到这些 θ？（决定"是否为难的测试问题"）
- **RQ3 失败刻画与泛化**：失败类型/root pattern？是否跨 RAPTOR 与 mc_nn_control 成立？
- **RQ4 迁移**：仿真失败能否在 HITL/真机/replay 复现？跨 PX4/ArduPilot 是否成立？
- **RQ5 缓解**：发现能否指导运行期安全监控 / envelope guard / fallback-to-classical？

### 评估指标
time-to-first-failure；每 N 次仿真的失败数；唯一失败类型数；有效失败率（差分确认）；场景空间覆盖；分歧幅度。

### 预期失败分类（待验证）
风致跟踪发散；急转超调；setpoint-dropout 致 NaN；电机故障恢复失败；控制饱和失控；降落/切换瞬态失稳；学习型违反安全包络而经典仍安全。

---

## 6. 实现要点（开工版）

- **环境**：用 `ubuntu:24.04` 容器（mc_nn_control 官方要求 24.04，22.04 不支持；RAPTOR 通过 `CONFIG_MODULES_MC_RAPTOR=y` + `CONFIG_LIB_RL_TOOLS=y` 启用）。SITL 与搜索回路**不必跑在 Jetson 上**；Jetson 的 L4T 22.04 只需承载容器或外接一台机器。
- **推理无 GPU 依赖**：学习型控制器用 TFLM/RLtools 跑在飞控/SITL 进程里，不吃 GPU；**GPU 只在训练时需要**——本阶段免训，故无 GPU 需求。
- **仿真器**：`px4_sitl_sih`（确定性、快）作搜索主力；`PX4_SIM_SPEED_FACTOR` 加速；Gazebo 留作可视化。
- **控制切换**：经典 Position arm/起飞 → 中途切学习型（External Mode）；两次运行用同一种子与同一注入序列。
- **故障/扰动注入**：MAVSDK failure 插件（需 `SYS_FAILURE_EN=1`；停电机需 `CA_FAILURE_MODE=1`）；风用 SIH 参数；质量/惯量用 airframe 参数；setpoint dropout/延迟用 ROS2 offboard 节点。
- **日志**：ulog → 抽 tracking error / 姿态 / 角速率 / 电机输出 / mode / NaN。
- **搜索**：Python harness（NSGA-II 用 pymoo，或自实现 MAP-Elites）；每候选多次重复以应对非确定性。

---

## 7. Threats to Validity / 风险

- **Sim 抖动 vs 控制器失败**：动力学/扰动在 SITL 里仿得准（这正是本方向比"感知差分"稳的地方），但需区分仿真诱导的不稳与控制器诱导的不稳——用**多次重复 + 经典作对照**（同设置下经典也抖 ⇒ 是仿真）。NTNU 曾提及 HITL 仿真"略不稳"。
- **自适应控制器的公平性**：RAPTOR 本就为质量/配置变化设计，故对"稳态质量变化"它该能扛——因此最有意义的失败在**经典能扛、RAPTOR 扛不住的瞬态/时序/接口**区，而非单纯稳态质量。第一版钉死 X500（经典调得好 ⇒ "经典安全"是公平参照）。
- **影响力/相关性**：学习型控制器目前是 experimental/bench（PX4 明示）；但趋势明确（RAPTOR 登 Science Robotics、在 PX4/Betaflight/Crazyflie 运行），且**领域缺测试**——叙事锚在"抢在部署前"。
- **对 NNCS 证伪的新颖性**：Related Work 必须引 ARCH-COMP / S-TaLiRo / Breach；差异化靠**内建差分 oracle + 固件级 6 自由度规模 + fuzzing**。
- **无真机**：sim-to-real（RQ4）本阶段推迟，用 replay 验证替代，并明列为局限。
- **单模型**：Phase 1 仅 RAPTOR，由 Phase 2 多控制器化解。

---

## 8. 路线图与待定项

**已定**：方向 B；RAPTOR 免训起步；SITL-only；X500；SIH 主仿真；不上真机。
**待定**：
1. 工具名（`[TOOL]` 占位）。
2. 目标会议（ICSE/FSE/ASE/ISSTA）与投稿窗口。
3. Phase 3 的栈优先级（ArduPilot vs Betaflight/Crazyflie）。
4. 何时引入真实飞控板以解锁 RQ4。

---

## References（关键文献，待补全 venue/DOI）

- Wang et al. **DPFuzzer: Discovering Safety-Critical Vulnerabilities for Drone Path Planners.** ICSE 2025.
- Chambers, Russell, Vierhauser, Cleland-Huang. **SaFUZZ**（sUAS state-machine semantic fuzzing）. ICSE 2026.
- Kim et al. **PGFuzz: Policy-Guided Fuzzing for Robotic Vehicles.** NDSS 2021.
- **RVFuzzer.** USENIX Security 2019. / **LGDFuzzer.** ICSE 2022. / **IMUFuzzer.** ASE 2025.
- Choi, Kate, Aafer, Zhang, Xu. **Cyber-Physical Inconsistency Vulnerability Identification for Safety Checks in Robotic Vehicles (CPI).** CCS 2020.
- ARCH-COMP AINNCS（neural-network control systems falsification/verification）；S-TaLiRo / Breach / ARIsTEO 等。
- Eschmann, Albani, Loianno. **RAPTOR: A Foundation Policy for Quadrotor Control.** Science Robotics 2026 / arXiv:2509.11481.
- Hegre, Rehberg, Kulkarni, Alexis. **A Neural Network Mode for PX4 on Embedded Flight Controllers.** arXiv:2505.00432, 2025.
- Zhang et al. **A Learning-Based Quadcopter Controller With Extreme Adaptation.** IEEE T-RO 2025.
- SBFT CPS-UAV Testing Competition tools（CAMBA / TUMB / WOGAN-UAV / DeepHyperion-UAV / AmbieGen / TAIiST）。
- PX4 v1.17 Release Notes；PX4 Neural Network Control / RAPTOR / SIH / System Failure Injection 文档。 
