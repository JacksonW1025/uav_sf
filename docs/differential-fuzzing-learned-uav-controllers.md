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

同一 PX4（`main`，固定 commit `3042f906`）、同一机架（**X500 v2**）、同一任务；两个 controller backend：**经典级联** vs **学习型端到端**（第一版 **RAPTOR**，`mc_raptor`，免训）。学习型控制器吃状态、直接输出归一化电机指令。

**差分切换点**【实测】：经典模式 arm/起飞到稳定悬停，**飞行中途用 `MAV_CMD_DO_SET_MODE` 切到 RAPTOR external mode（`mode_id=23`，custom_mode 编码 main=4/sub=11）**。M0 已跑通"经典起飞→Hold→切 RAPTOR→稳定悬停"的完整闭环，ULOG 中 `nav_state` 序列 4(Hold)→17(Takeoff)→23(RAPTOR) 可见切换时刻。

**机架在 SIH 中的实现**【实测】：SIH 本身仍是仿真器，但把通用四旋翼参数配成 X500 v2——质量/惯量取自 PX4 的 `gz x500` 模型（`SIH_MASS=2.0`、`SIH_IXX=SIH_IYY=0.0216667`、`SIH_IZZ=0.04`），quad-X 几何取自 `4001_gz_x500` 的 `CA_ROTOR*`，经典 rate 调参取自 X500 airframe 族，推力模型取自 gz x500 电机常数。这保证"经典对所测机体调得好"（oracle 公平性前提），且与 RAPTOR/`mc_nn_control` 的真机 X500 结果可跨论文对照。tracked airframe + installer 入库，ignored PX4 树可复现。

### 4.2 场景表示 θ（按"裁剪管不到"重排优先级）

一个测试用例是一个有界、物理可行性约束的参数向量。**M1 的关键实证发现重塑了这个空间的优先级**：

> **【实测·核心】RAPTOR 在策略推理前裁剪观测误差。** `mc_raptor.hpp` 写死 `max_position_error=0.5`、`max_velocity_error=1.0`，`mc_raptor.cpp` 把 position error 裁到 ±0.5 m、velocity error 裁到 ±1.0 m/s。**后果：任何 >0.5 m 的位置误差在策略眼里完全相同**——2 m step、10 m step、100 m step 不可区分。M1 用四个手工锚点（±2 m/5 Hz 正弦、各档大 step、极端 Lissajous）**全部未进 primary_bug 象限**，正是被这层裁剪截断。

因此 θ 维度按**裁剪能否约束**重排为三档：

**A 档（高产，裁剪管不到）**

- **状态估计污染**：传感器噪声/偏置/延迟、陀螺偏置、mag 失效、IMU 延迟。裁剪作用在"误差 = setpoint − 状态"上；污染**状态**会让策略基于错误信息行动，更重要的是观测里的**姿态（旋转矩阵）与角速度这两个通道源码中未见被幅度裁剪**，污染它们等于把坏观测**直接、未经裁剪**喂给策略。这正是 **RAPTOR 论文 §2.4.1 自己记录的失败模式**（velocity-delay → 振荡）。
- **物理参数失配**：质量/惯量/重心偏移、电机退化、推力不对称、气动效应。裁剪管观测、不管被控对象（plant），故 plant 失配不受它约束。有价值的区间是"**RAPTOR 崩、但经典（有积分项）仍稳**"——而非让两者都崩的极端区。

**B 档（中产）**

- **时序/接口**：setpoint 抖动/延迟、非整除的发布率、dropout **模式**（注意：完全停发被 guard 截断，见 §4.3）。
- **切换瞬态**：在高速/大姿态/受扰瞬间切入 RAPTOR。

**C 档（基本死，仅余高频带内）**

- **setpoint 幅度**（曲率/速度/阶跃幅度）：被裁剪，徒劳。**唯一残余**是幅度 ≤0.5 m（不触裁剪）但频率高到动力学跟不上的**带内高频** setpoint。

**风**横跨档位：定常风制造持续误差（被裁到 0.5 m），但作为真实扰动作用在 plant 上；阵风（瞬态）更可能有效。SIH 中用 `SIH_WIND_N`/`SIH_WIND_E`。

> **去掉/修正的旧假设**：原 §1.2.3 与"预期失败分类"中的"**setpoint-dropout → NaN**"**不成立**——这是 `mc_nn_control`/早期未加保护路径的行为；**guarded-RAPTOR 缺/陈旧 setpoint 时合成 hold reference（finite），不产生 active-motor NaN**（M0 实测：`actuator_motors` 的 NaN 仅出现在未用通道 `control[4..11]` 的 PX4 sentinel，active `control[0..3]` 为 0）。该项应从 RAPTOR 的失败假设中删除，留待 Phase 2 在 `mc_nn_control` 上重新检验。

### 4.3 差分 Oracle（四象限，已收紧判据）

同一 θ 跑两遍（经典 / RAPTOR，**同机架、同种子、同注入序列、事件按 sim 时间对齐**），得轨迹 T_c / T_n：

|                   | 经典 safe                       | 经典 unsafe                         |
| ----------------- | ------------------------------- | ----------------------------------- |
| **RAPTOR safe**   | `boring_both_safe`              | `interesting_not_bug`（学习型更强） |
| **RAPTOR unsafe** | **`primary_bug`（只报这一类）** | `too_hard_not_bug`                  |

"safe/达标"判据【实测·已实现】：跟踪误差包络（max/RMS）+ 姿态/角速率不发散 + 任务完成（final error）+ 无 active-motor NaN + 无意外 disarm/failsafe + 不触地。次阈值分歧（超调/饱和/逼近边界）不判 bug，而作搜索反馈。M1 的指标流水线（`m1_metrics.py` + `m1_compare.py`）已能产出全部四种标签——`too_hard`（重质量两者都崩）、`interesting_not_bug`（大 step 经典 failsafe、RAPTOR safe）均实际出现，证明 unsafe 判据**确实会触发**、oracle 不是"无脑盖 safe"。

**M1 暴露的两条必须在 M2 前处理的收紧项**：

1. **统一安全包络（cross-θ 可比性）**。M1 当前阈值是 **per-θ、缺省 inf**——手跑几个 θ 可以，但 M2 批量评估成千上万 θ 时会让不同 θ 的象限标签不可比、fitness 失真，且漏设某阈值会让该维度永不触发。**M2 必须改为一套统一、有据可依的安全包络，对所有 θ 一致施用。**
2. **经典 baseline 必须是"控制级"安全**。M1 的 `anchor_step_10m` 中经典的"unsafe"其实是 offboard 大跳变触发的**基建 failsafe**（offboard >2 Hz proof-of-life / 位置跳变保护），**不是控制失败**。四象限的 `primary_bug` 要可信，oracle 必须**区分"控制器搞崩"与"offboard 基建搞崩"**，并把后者从 baseline 中剔除（否则会污染"经典 safe"这一参照）。

**为什么干净**（不变）：不主张学习型控制器的绝对正确性，只主张"调好的经典控制器守住 ⇒ 场景物理可行 ⇒ 学习型也应守住"。

### 4.4 搜索与反馈

fitness = 分歧度（neural−classical 的跟踪误差差 + 姿态振荡差 + 饱和差 + time-to-divergence + 稳定裕度），约束 classical 安全。用 **NSGA-II**（多目标）或 **MAP-Elites**（按扰动类型 × 幅度分箱，求**多样**失败）。每次评估 = 2 次 SITL 运行；用 `PX4_SIM_SPEED_FACTOR` 与 SIH lockstep 提升吞吐与可复现性。

**M0/M1 给搜索设计的三条约束**：

- **搜索空间按 §4.2 加权**：把预算压在 A 档（状态估计污染、物理失配）与 B 档（时序/瞬态），**避开 C 档 setpoint 幅度这个被裁剪的死维度**。MAP-Elites 按扰动类型分箱恰好能保证覆盖 A 档的多个子方向。
- **分歧信号必须高过噪声地板**【实测】：SIH 非 bit-exact，同 θ 重复跑姿态 max 差 ~1°、tracking RMS 差 ~0.04 m。fitness 的有效分歧必须显著超过此地板，否则是仿真噪声而非控制器分歧。
- **null 结果即 RQ2 证据**：M1 手工挑的固定 θ **没有**点亮 `primary_bug`——这本身就是"朴素手挑场景搜不到、必须制导搜索"的实证，是 RQ2（搜索有效性）的第一个数据点。

---

## 5. 实验计划（分阶段，已更新进度）

总原则不变：**先用免训的 RAPTOR 把端到端闭环打通并产出第一批失败，再扩成不限于单一模型的通用方法，最后泛化到 PX4 之外。**

### Phase 1（进行中）：RAPTOR + PX4 SITL，不上真机

- **被测**：RAPTOR（`mc_raptor`，免训），X500 v2。
- **仿真器**：**SIH 为主**（headless、lockstep、确定性、最快），风用 `SIH_WIND_N/E`；Gazebo 仅少量可视化。

**里程碑**

- **M0【✅ 已完成 `b1be614`】**：24.04 容器内 build 带 RAPTOR 的 `px4_sitl`（SIH 路线，未 fallback Gazebo）、经典飞→中途切 RAPTOR→记 ulog。Oracle sanity 的诚实结论：**缺-setpoint 被 RAPTOR 的 stale/missing guard 截断，不产生 active-motor NaN**（修正了原计划里的 NaN 假设）。
- **M1【✅ 已完成 `6c944b9`】**：ROS 2 offboard 发参数化任务 + setpoint 流（同一流驱动经典 Offboard 与 RAPTOR external mode 23）；ulog 解析抽指标；对固定 θ 跑经典/RAPTOR 各一遍、算分歧、判四象限。**核心发现：观测误差裁剪使 setpoint-幅度类攻击失效**（四锚点全非 primary_bug）。SIH-X500 v2、`IMU_GYRO_RATEMAX=400` 频率对齐、确定性核验均完成。故障注入 wrapper 已接，但 **SIH 对电机/传感器故障的支持未验证**（官方 cite Gazebo Classic）。
- **M2【✅ 已完成】**：把 M1 包进 MAP-Elites，落地统一安全包络与经典-baseline 去基建-failsafe 污染。首轮 8 eval 找到 1 个 raw primary candidate，但 3 次确认未通过；confirmed primary 为空。
- **M2.5【✅ 已完成】**：加入共享 EKF/GNSS 估计污染维度并修复 4x early-shutdown。目标延迟梯度与 harsh probe 均未确认 primary；4x 只作为 triage，primary confirmation 仍保留 1x。
- **M2.6【✅ 已完成】**：针对 RAPTOR 未裁剪的 angular-rate 观测通道，用共享 `IMU_GYRO_CUTOFF` 做公平污染；8 点 cutoff x TWR scan 未确认 primary，但记录了高 TWR continuous divergence。
- **M2b-1【✅ 核心能力完成，搜索规模未完成】**：新增对抗性共享状态 uORB shim，覆盖 velocity / attitude / angular velocity 的 delay、bias、noise、NaN、Inf profile；完成 fairness/touch 验证、velocity-delay 定向验证、NaN/Inf 探针、1x/4x 高 TWR 噪声地板与 8 eval bounded state search。confirmed primary 仍为空；数百 eval 级 campaign 因串行吞吐（4x 约 105 s/eval）未跑完，保留为 M2b-1 后续。
- **M2b-2【⬜ 下一步】**：plant 不对称（单电机退化、质心偏移）、切换瞬态、Gazebo 传感器故障路径。
- **M3（评估）【⬜】**：baseline（random / grid / 经典-only 对照）、消融（去掉分歧反馈）、失败分类、每候选多次重复（应对非确定性，需高过噪声地板）。

**回答**：RQ1（存在性）、RQ2（搜索有效性/消融）、RQ3（RAPTOR 失败分类）。

### Phase 2：从"测一个模型"扩成"一个方法"

- **加入第二个学习型控制器**：`mc_nn_control`（用其 X500 预训练网，无需自训；官方要求 Ubuntu 24.04——容器已就位）。目的：证明失败类型**跨控制器成立**、方法**不绑单一模型**。
- **在 `mc_nn_control` 上重新检验缺-setpoint→NaN**：因 `mc_nn_control` 不一定有 RAPTOR 那层 guard，这条被 RAPTOR 截断的失败路径可能在此成立——是个干净的跨控制器对照点。
- 细化反馈/fitness；扩展场景空间；对单个学习型控制器加**蜕变关系**（缩放/旋转跟踪任务，响应应同样缩放/旋转），补差分覆盖不到的情形。
- **回答**：RQ3'（跨控制器泛化）、方法层面的稳健性。

### Phase 3（后续）：泛化到 PX4 之外 + 真机验证

- 把差分 fuzzing 移植到 **ArduPilot**（及 RAPTOR 本就支持的 Betaflight/Crazyflie），论证通用性。
- **sim-to-real / HITL 验证**：待有真板后做（HITL 用 `px4_fmu-v6c_neural` / `mro_pixracerpro_neural` 跑 TFLM/RLtools；或真飞）。此前以 **replay 验证** + 清晰 scoping 替代，列为已知局限。
- **回答**：RQ4（迁移性）、RQ5（缓解：安全监控 / fallback 触发）。

### 研究问题（汇总，不变）

- **RQ1 存在性**：是否存在"学习型崩/退化、经典稳"的场景？哪些类？
- **RQ2 搜索有效性（关键）**：分歧制导是否比 random/grid 更快找到这些 θ？（M1 的 null 结果已是第一个支持点）
- **RQ3 失败刻画与泛化**：失败类型/root pattern？是否跨 RAPTOR 与 `mc_nn_control` 成立？
- **RQ4 迁移**：仿真失败能否在 HITL/真机/replay 复现？跨 PX4/ArduPilot 是否成立？
- **RQ5 缓解**：发现能否指导运行期安全监控 / envelope guard / fallback-to-classical？

### 评估指标

time-to-first-failure；每 N 次仿真的失败数；唯一失败类型数；有效失败率（差分确认）；场景空间覆盖；分歧幅度（须高过噪声地板）。

### 预期失败分类（已按 M0/M1 修订）

- **删除**：~~setpoint-dropout 致 NaN~~（guarded-RAPTOR 不成立，移交 Phase 2 在 `mc_nn_control` 上检验）。
- **降级为"裁剪受限"**：单纯急转/大幅 setpoint 超调（幅度被裁剪；仅带内高频可能有效）。
- **保留并上调优先级（A 档）**：状态估计污染致振荡（RAPTOR §2.4.1 背书）；质量/CoM/电机退化等物理失配下的适配失败（经典仍稳）。
- **保留**：风致跟踪发散；控制饱和失控；降落/切换瞬态失稳；学习型违反安全包络而经典仍安全。

---

## 6. 实现要点（开工版，已对齐实测）

- **环境**：`ubuntu:24.04` 容器（镜像 `uav_sf:phase1`，arm64）。`mc_nn_control` 官方要求 24.04；RAPTOR 通过 `CONFIG_MODULES_MC_RAPTOR=y` + `CONFIG_LIB_RL_TOOLS=y` 启用。SITL 与搜索回路跑在容器内；Jetson L4T 22.04 仅承载容器。**CPU-only**，本阶段免训、无 GPU 需求。
- **板级/机架（tracked + installer，复现 ignored 树）**：`boards/px4/sitl/raptor_sih.px4board`（default SITL + RAPTOR − Gazebo）+ `config/px4/init.d-posix/airframes/10046_sihsim_x500_v2`。
- **仿真器**：`px4_sitl_raptor_sih` + `sihsim_quadx`，**直接 launch**（`./bin/px4 .` from build root，规避 rcS CWD 坑）；`PX4_SIM_SPEED_FACTOR` 加速；Gazebo 留作可视化。
- **频率**：`IMU_GYRO_RATEMAX=400`（force_sync_native=4，匹配 100 Hz 训练频率）。
- **控制切换**：经典起飞 → 中途 `DO_SET_MODE` 切 RAPTOR external mode 23；两次运行同种子、同注入序列；**事件按 PX4/sim 时间触发，不用 wall-clock**（`SIM_SPEED_FACTOR>1` 会让两次跑错位）。RAPTOR 在 `MC_RAPTOR_OFFB=0` 下跟踪持续发布的 finite `trajectory_setpoint`【实测】。
- **故障/扰动注入**：风 `SIH_WIND_N/E`、质量/惯量 `SIH_MASS`/`SIH_IXX/IYY/IZZ`（**走 SIH 参数，不走 failure 插件**）；电机/传感器故障用 `SYS_FAILURE_EN=1`(+ 电机 `CA_FAILURE_MODE=1`) 的 `failure`/`MAV_CMD_INJECT_FAILURE`，**但 SIH 支持未验证，电机故障类可能需 Gazebo**；setpoint dropout/延迟/抖动用 ROS 2 offboard 节点。
- **DDS topic 版本号**：输出用 `/fmu/out/vehicle_status_v4`、`/fmu/out/vehicle_local_position_v1`。
- **日志**：ulog → 抽 tracking error / 姿态 / 角速率 / 电机输出（active vs unused 通道分箱）/ mode / NaN。RAPTOR 日志 profile 见 M0。
- **搜索**：Python harness（NSGA-II 用 pymoo，或自实现 MAP-Elites）；统一安全包络；每候选多次重复以应对非确定性。

---

## 7. Threats to Validity / 风险（已补 M0/M1 教训）

- **Sim 抖动 vs 控制器失败**：动力学/扰动在 SITL 里仿得准，但需区分仿真诱导与控制器诱导的不稳——用**多次重复 + 经典对照**。**已量化噪声地板**【实测】：同 θ 重复跑姿态 max ~1°、tracking RMS ~0.04 m；任何"失败/分歧"信号须显著高过此地板。
- **裁剪即"自带鲁棒性"——公平性的新维度**：RAPTOR 的 ±0.5 m/±1.0 m/s 观测裁剪使它对大 setpoint 跳变**按设计**稳健【实测】。因此**不能**把"它扛住了一个大 step"当 bug 反例；最有意义的失败在裁剪**管不到**的区（状态估计、物理失配、瞬态/时序），而非 setpoint 幅度。这与"自适应控制器对稳态质量本该能扛"是同一类公平性考量。
- **经典 baseline 的基建污染**：offboard 大跳变会触发 offboard/failsafe **基建**行为，与控制无关却会被记成"经典 unsafe"【实测，`anchor_step_10m`】。oracle 必须把基建-failsafe 从经典 baseline 中剔除，否则 `primary_bug` 判定被污染。
- **故障注入的仿真依赖**：failure injection 官方 cite Gazebo Classic；**SIH 对电机/传感器故障的支持未验证**【实测·未决】。涉及电机/传感器故障的 θ 可能需切 Gazebo，需在结果中标注"哪些 θ 在哪个仿真器跑"。
- **自适应控制器的公平性**：RAPTOR 为质量/配置变化设计，稳态质量该能扛；最有意义的失败在瞬态/时序/接口/状态估计区。第一版钉死 X500 v2（经典调得好 ⇒ "经典安全"是公平参照）。
- **影响力/相关性**：学习型控制器目前 experimental/bench（PX4 明示），但趋势明确、领域缺测试——叙事锚在"抢在部署前"。
- **对 NNCS 证伪的新颖性**：Related Work 引 ARCH-COMP / S-TaLiRo / Breach；差异化靠**内建差分 oracle + 固件级 6 自由度规模 + fuzzing**。
- **无真机 / 单模型**：sim-to-real（RQ4）本阶段推迟、用 replay 替代并列为局限；单模型由 Phase 2 多控制器化解。

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
