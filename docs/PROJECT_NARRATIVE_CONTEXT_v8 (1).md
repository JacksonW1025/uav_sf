# 项目叙事与上下文文档 v8 — 学习型 UAV 飞控的场景模糊测试

**用途**：切换对话时的完整上下文 + 给执行 agent 的叙事参考。读完即可接续，无需回溯历史对话。本版是**全面重构**，不是 V7 的增量补丁——按"背景 → related work → 概念定义（θ/oracle/policy/搜索/baseline）→ 全部结果 → 论文故事 → 未来对照与其它 oracle"的逻辑主线重新组织，把整个实验过程和整篇论文故事一次讲通。

**取代**：v7。

**本版的核心变化（V7 → V8）**：
1. **RAPTOR 完整对照 campaign 已跑完，结果 = 干净 negative**（V7 时是"进行中 + 预期 RAPTOR 守住"）。原始（保留裁剪）RAPTOR 完成与 mc_nn 严格对齐的 route-A switch-severity 全量 pass：dense sweep 120/120 valid 0 strict、7 臂 search 840 eval 0 confirmed、gate0/anchor 全 negative。**跨全 campaign ~926 个成功 eval，RAPTOR 一次都没失控（0 次 S3/S4）**。artifact 落 `aba86101`，报告见 `docs/raptor_external_ai_review_2026-07-07.md`。
2. **两 SUT 结果的定位被收紧（关键，避免审稿反咬）**：RAPTOR 的 negative **不**用来支撑"学习型特有性（learned-specificity）"。**mc_nn ↔ classical 给"学习型特有"；RAPTOR ↔ classical 给"oracle 区分力/精度 + harness 外部效度"**，两者严格分开陈述。理由见 §8——RAPTOR 与 mc_nn 同时在多个轴上不同（裁剪、架构、维度），不是干净的 learned-vs-learned 对照变量；RAPTOR 守住可能只说明"裁剪管用"。
3. **RAPTOR 线收工（方案 A）+ 裁剪 confound 已实验排除（方案 B 已完成）**：数据侧无 open loop。unclipped RAPTOR 定向对照已跑完（run `raptor_unclipped_ablation_20260707`，24 eval）——**Outcome B：移除输入裁剪后 RAPTOR 在已知失效带仍不失控（24/24 valid、0 strict、清一色 S0 仅 pair1 一个 S1），裁剪被排除为鲁棒主因**。§9 裁剪 threat 从"主动认领"降级为"已测试排除（限已知失效带范围）"。**但这不升级 §8 定位**——RAPTOR 仍与 mc_nn 多轴不同，negative 仍只撑区分力+外部效度、不撑 learned-specificity（见 §8 规则二补注）。
4. **假阳纪律现为第四次演示**：RAPTOR campaign 里 oracle 正确地对一个鲁棒控制器**不**报 primary bug——这是 oracle 精度的实锤，是本项目"可靠 oracle"支柱的又一根证据。

**Date**: 2026-07-07（rev. 2026-07-07b：unclipped RAPTOR 对照完成 = Outcome B，裁剪 confound 实验排除；§0/§7.6/§8/§9/§11.1/§13/§14 已更新）
**Repo**: `github.com/JacksonW1025/uav_sf`，工作区 `/mnt/nvme/uav_sf`（容器内）。PX4 固定 `main@3042f906abaab7ab59ae838ad5a530a9ef3df9a6`（v1.18 alpha）。**公开 GitHub main 已同步至 `aba86101`（RAPTOR 全量 campaign artifact）**——A/B 路线、切换区 campaign、multi-policy、wave-2、RAPTOR 集成 + 完整对照 campaign 均在公开 main。
**目标会议**：未定，SE 大类，**FSE 或 ISSTA**（testing 契合、RouthSearch/ISSTA'25 有窄 scope 严做的先例；FSE 亦可）。**写作尚未开始**——本轮只重构叙事，不动论文正文。

---

## 0. 速览（TL;DR）

**Idea**：学习型低层飞控（PX4 Neural Control、Science Robotics 的 RAPTOR 基础策略）正进入生产自驾仪却没有系统化安全测试。我们在**同一固件、同一机架、同一任务**下，用搜索（scenario fuzzing）在扰动/机动/故障/指令的场景空间里找学习型控制器的失效，用**调好的经典控制器当内建差分 oracle**（经典 safe ∧ 学习型 unsafe）作为闭环控制失效的归因。**定位 = SE 方法稿**：头条不是"抓了多少 bug"，而是可靠 oracle + 假阳纪律 + 可复现 + 系统化失效刻画 + 诚实边界。

**当前状态（V8：正面发现 + 三个干净 negative 划定其边界 + 两个 SUT 收口完成）**：
- **A 路线（灾难差分锚点，已锁 + 多种子确认）**：mode-23 中途交接剧烈状态，经典 **S0 干净恢复** ∧ `mc_nn_control` **S3 失控翻机**（>90°、>8 rad/s）。多种子闸：pair1/pair2/pair4 **3/3**、pair5 **8/9 概率性锚点**。
- **切换区严重度 campaign（`118d58f`）**：RQ1 系统化（179 guided primary、~10 确认 cell）+ RQ2（制导效率框架，~5× 命中率）+ RQ3（高维带洞非单调边界，含反直觉"高风恢复"，来自密扫）。
- **multi-policy 差分谱系（`db9adc7`）**：P1–P7 全差分化、950 valid eval 零新增仿真重分析。**失效收敛到灾难类（P1/P2）**，P6/P7 是伴随 S3 的次级签名、P3/P4/P5 无独立失效。第三次假阳纪律。
- **wave-1（wind+physics）+ wave-2（估计污染）两个非切换轴 = 干净 negative**（各 400 eval，0 strict）。**把 robust 差分失效钉死在切换瞬态**，关闭"这是学习型弱点还是你只测了切换"的承重质疑。
- **RAPTOR 第二 SUT（`3bc618c` smoke + `aba86101` 全量 campaign，V8 完成）**：原始（保留裁剪）RAPTOR 完成与 mc_nn 严格对齐的完整对照 campaign。**干净 negative：全 campaign 0 strict S0-vs-S3、0 confirmed primary、RAPTOR 全程 0 次失控**。**定位 = oracle 区分力（第四次假阳纪律：正确不报鲁棒控制器）+ harness 外部效度（C4 在第二个真实 shipped 控制器上实锤）**，**不**当作 learned-specificity 的支撑。**裁剪 confound 已实验排除**：unclipped RAPTOR 定向对照（24 eval，run `raptor_unclipped_ablation_20260707`）= **Outcome B**——去裁剪后仍不失控、0 strict，裁剪非鲁棒主因（§7.6/§11.1）；但此排除**不改** §8 定位（RAPTOR 仍多轴混杂）。

**下一步（§14）**：**方案 A——收范围 + 开写**。论文脊柱不仅完整、且已被三个诚实 negative + 两 SUT 收口显著加固。**已完成加固**：unclipped RAPTOR 对照（Outcome B，裁剪 confound 实验排除）。**待办**：RQ2 统计加固（代码已备、押后）、变形 oracle（唯一剩余便宜上行、可选）。

---

## 1. 背景与"oracle 问题"

**趋势**：学习型低层飞控正从研究走进生产。PX4 v1.17/v1.18 内置了 Neural Control 模式（`mc_nn_control`，NTNU/arXiv:2505.00432）；Science Robotics 2026 的 RAPTOR 是一个免训四旋翼基础策略（foundation policy）。它们和经典串级 PID/几何控制器在**同一固件里共存、可运行时切换**。但没有任何系统化方法回答：这些学习型控制器相对经典控制器，在扰动/机动/故障/指令场景里**哪儿会特有地失败**、失败边界长什么样、根因是什么。

**根本难点 = oracle 问题**：要判一个控制器"飞错了"，须先知道"正确飞行长什么样"。任意扰动下的**绝对正确性**极难规约——你无法为"6 自由度固件级闭环控制在任意风/任意交接时刻应该怎么飞"写下完整的形式规约。这是神经控制器证伪（CPI、ARCH-COMP AINNCS、可达性方法）在真实固件上不 scale 的根本原因：它们要么依赖玩具系统，要么要求你先写全正确性规约。

**本项目的破题**：PX4 让经典与学习型控制器在同一固件共存、可切换。**同机架/同任务/同扰动下，若调好的经典守住、学习型失败，则该失败学习型特有**——归因靠结构（同条件对照），不靠手搓绝对正确性规约。经典控制器就是参照。在此之上用 fuzzing 系统化搜这些失败。

---

## 2. 核心 Idea / Thesis（精确定界）

**机制**：差分 oracle = `经典 ⊨ safe ∧ 学习型 ⊭ safe`（同 θ 跑两遍，同机架/种子/注入序列/sim 时间对齐）。这是一个**归因机制**，绕过"须先写全正确性规约"。

**已被实验加固、可证伪的中心断言（V8 定形）**：

> **PX4 内置神经控制器 `mc_nn_control` 存在一类经典控制器没有的 robust 差分失效，该失效特定于控制模式切换瞬态、表现为灾难性失控（S3），并且不铺展到稳态风+物理、稳态估计污染两条非切换轴，也不表现为切换区的渐进行为退化（P3–P7 独立性）。**

三个诚实 negative（wind+physics、估计污染、multi-policy 行为类独立性）不是三次失败，而是把正面发现（切换瞬态灾难差分）**衬托出来并划定其边界**的三根对照。这让 thesis 从"只测了切换所以不算"升级到"测了多个非切换/非灾难维度、都干净、失效边界就在切换瞬态灾难类"。

**RAPTOR 的角色（V8 关键定界，展开见 §8）**：RAPTOR 完整对照 = 干净 negative。它**不改变、也不需要支撑**上面这个关于 mc_nn 的断言（该断言只靠 mc_nn ↔ classical 同条件对照成立）。RAPTOR 提供的是**方法层证据**：oracle 有区分力（在 mc_nn 上 fire、在鲁棒的 RAPTOR 上正确沉默）+ harness 能不改地跑第二个真实控制器。

**概念澄清（multi-policy ≠ multi-oracle）**：差分 oracle 是一个**机制**，机制内部可挂多条 **policy**（P1–P7，PGFuzz 形状——PGFuzz 的"多"也是一个 MTL oracle 下的多条 policy，不是多种 oracle 类型）。"厚度"不来自 oracle 类型数、也不来自 policy 数，而来自**目标新颖性（学习型控制器 + 差分 oracle）+ 刻画深度 + 诚实边界 + 第二 SUT + 统计严谨度**。

---

## 3. Related Work（六根轴，定位 gap）

沿两轴：**(i) 是否建模/扰动控制器闭环动力学**；**(ii) 被测对象是经典控制软件、状态机，还是学习型控制器**。

- **(a) UAV 障碍/场景 fuzzing 与路径规划器测试**：DPFuzzer（ICSE'25）、SBFT CPS-UAV 簇（CAMBA/TUMB/WOGAN-UAV 等）、SwarmFuzz。聚焦几何/障碍、假设理想执行器、不测低层控制器。
- **(b) RV 控制/配置/策略 fuzzing**：RVFuzzer（USENIX'19）、LGDFuzzer（ICSE'22）、**PGFuzz（NDSS'21，MTL 安全策略 oracle，156 新 bug，真机复现）**、ADGFuzz、IMUFuzzer（ASE'25）、**RouthSearch（ISSTA'25，7 RQ、离线 vs 在线 oracle、搜索算法消融、基线跑 3 遍控方差、~7000 CPU 小时）**。被测是经典控制软件；无 learned-vs-classical 差分。**PGFuzz 的"性质即 oracle"是本项目性质 oracle 的直接模板（`property_oracle.py` P1–P7 policy 库）。RouthSearch 是 RQ2 统计严谨度对标的领域标杆，也证明"scope 窄但做得极严"能中 ISSTA。**
- **(c) 模式/状态/failsafe 语义 fuzzing**：SaFUZZ（ICSE'26）、HIFuzz。作用在状态机/模式层，不下沉控制器层。
- **(d) 赛博-物理不一致与神经控制器证伪**：CPI（CCS'20）；ARCH-COMP AINNCS、S-TaLiRo/Breach/ARIsTEO、NNV/Verisig/CORA。最直接前作，但基准是玩具系统、可达性在真实 6 自由度固件级不可扩展、无内建差分 oracle。**本项目的差分 oracle 正是绕过"须先写全正确性规约"的新解——经典即参照。**
- **(e) 学习型 UAV 控制与基础策略**：RAPTOR（Science Robotics 2026 / arXiv:2509.11481）、NTNU PX4 神经模式（arXiv:2505.00432）、Zhang 极端自适应（T-RO 2025）、Neural-Lander。**构造**学习型控制器，不提供系统化方法找它们相对经典在哪儿失败。
- **(f) 自动驾驶 ML 测试（方法迁移源）**：成熟的 ground-truth-vs-actual 差分、metamorphic、对抗鲁棒、OOD 检测。迁移其精神到 UAV **闭环控制**。

**Gap**：尚无工作系统化搜索扰动/机动/故障场景空间，用**可靠的经典-学习型差分 oracle** 找出**集成进固件的学习型飞控**相对经典**特有的失效**、刻画其**高维边界与根因**、用**诚实的阴性对照划定失效边界**、并在**多个真实 shipped 控制器**上验证 harness 与 oracle 的区分力。

---

## 4. Contribution（V8 状态）

### 4.1 方法稿贡献（C1–C5）
- **C1**：学习型 UAV 飞控的差分场景模糊测试**问题表述**。✓
- **C2（可靠差分 oracle + 假阳纪律四次演示 + gate 方法学升级）**：对齐切换状态 + 分级严重度 + 基建去污染 + 灾难类以离散 severity/符号确认、行为类越抖动 + 触发性质确认，已自动化（`validity_automation.py`）。**假阳纪律现已四次公开演示**：wave-1 拒 12-finding 噪声假阳；multi-policy 把 P6/P7 正确判为伴随灾难的次级签名；wave-2 把 P2/P4 相对退化与 P7 候选正确判为诊断/未确认；**RAPTOR campaign 正确地对一个鲁棒控制器不报 primary bug（第四次，见 §7.6/§8）**。gate 方法学升级：确定性锚点（pair1/2）硬闸 + 边界锚点（pair4/5）概率跟踪（≥6/8）。✓
- **C3（搜索反馈/制导，带效率框架）**：差分 gap fitness + MAP-Elites + baseline 消融（random/grid）。guided 以 ~5× 命中率、~60% 更高 QD、更低种子方差**更密更全地照亮**灾难差分区，**但 3/3 确认档与 random 打平**——主张 = 效率/照亮/一致性，非 bug 计数。archive 重分析进一步定位：guided archive 快速照亮高危区、完整带洞刻画来自密扫。**RQ2 统计加固（10+ 种子 + Mann-Whitney U + A₁₂）+ fitness 消融（`guided_abs`）代码已备、押后未跑。** ✓（带 caveat）
- **C4（V8 实锤）**：**免训、可复现的测试平台/基准，实例化在两个真实 shipped 控制器上。V7 时 RAPTOR 完整 campaign 仅"进行中"；V8 已跑完**——同一 harness 不改地在 mc_nn 与 RAPTOR（架构、维度、裁剪均不同）上完整跑通 route-A switch-severity campaign，identity 按 SUT 分派、classical 基线复用、判据一致。"两个真实控制器"从名义变为**跑完的对照**。✓
- **C5（失效分类 + 诚实边界）**：切换瞬态灾难差分（P1/P2）+ 高维带洞边界（姿态/rate/风/delay/相位皆有洞或恢复区）+ **三个诚实 negative 划定边界**（wind+physics、估计污染、multi-policy 行为类独立性）+ 小 P4/P6 架构签名 + **oracle 区分力（对鲁棒 SUT 正确沉默）** + **裁剪 confound 经 unclipped 对照实验排除（Outcome B）**。缓解仍在 discussion 层。✓（分类成形，缓解待补）

### 4.2 经验头条结果
- **A 路线**：经典 S0、mc_nn S3 翻机；多种子复现（3/3、3/3、3/3、8/9）；反直觉 mc_nn 对幅度比经典更鲁棒（GATE-3）。
- **切换区严重度 campaign**：179 guided primary、~10 确认 cell；guided 效率碾压 random/grid（3/3 打平）；边界经密扫刻画为**高维带洞、非单调**。
- **multi-policy 差分谱系**：失效收敛到灾难类（P1/P2 主导，P6/P7 伴随，P3/P4/P5 无独立失效）。
- **wave-1 + wave-2**：两条非切换轴各 400 eval 干净 negative → robust 差分失效钉死在切换瞬态。
- **RAPTOR 两 SUT 对照（V8）**：原始 RAPTOR 完整对照 = 干净 negative，全程 0 次失控 → **oracle 有区分力 + harness 外部效度**（非 learned-specificity）。

---

## 5. 核心概念与定义

本节把论文赖以成立的四个概念——**场景 θ、oracle、policy、搜索方法（含 Random/Grid baseline）**——一次讲清。

### 5.1 场景空间 θ（scenario / genome）的概念

**一个"场景"= 一组把仿真世界与任务参数化的可搜索变量**，落成一个 genome（`theta_genome.py`）。θ 三档：

- **A 档——状态估计污染 & 物理失配**：稳态风 × 物理参数失配（`steady_combo`，descriptor `wind × physics`）；估计污染子空间（`state_contam`，走 M2B shim：`position_estimate_jump_m`→`M2B_P_PROF`、`fake_velocity_bias_m_s`→`M2B_V_PROF`、`fake_angular_rate_bias_rad_s`→`M2B_G_PROF`，污染非零时置 `M2B_EN=1`、记 `uses_state_shim=true`，descriptor `velocity_bias × angular_rate_bias`）。
- **B 档——时序/接口/切换瞬态（差分主战场）**：genome 覆盖切换姿态 16–50°、角速率 0.45–2.75 rad/s、wind 0–6 m/s、switch delay 0–0.18 s、approach 相位/半径/频率。descriptor 主用 `switch_attitude × wind`；rate 保留为受可达约束搜索变量（`route_a_profile_for()` clamp 后重算 trigger rate）。
- **C 档——setpoint 幅度**：GATE-3 判死（**反转结论：两个学习型控制器对幅度都比经典更鲁棒**），**EXCLUDED**，不入搜索空间。电机/传感器故障（SIH 未验证）亦 EXCLUDED。

**可达性约束**：切换瞬态场景须"物理可达"——`route_a_profile_for()` 把请求姿态/rate clamp 到可达包络后**用实际达到的值重算 trigger**，避免搜出"根本飞不到"的伪场景。

### 5.2 Oracle 的定义（差分 oracle + 三卫生 + 分级严重度）

**四象限**（同 θ 跑经典 + 学习型两遍，严格对齐）：`boring_both_safe` / `interesting_not_bug`（都失败/太难）/ **差分（经典 safe ∧ 学习型 unsafe，只报这类）** / `too_hard_not_bug`。

**三个卫生机制（缺一不可，对两控制器对称）**：
1. **对齐切换状态**：SIH 无置态 API → **groundtruth 触发**，再以 ULOG 真值回匹配（rate 残差均值 ~0.09 rad/s）。
2. **分级失效严重度**：**S0 / S1 / S2 / S3 失控翻机（≥90° 或 ≥8 rad/s）/ S4 数值 fault**。关键切分 = **受控（S0–S2）vs 失控（S3–S4）**。
3. **剔除基建污染**：**截断 control window 后重算控制级 severity，不剔整个 eval**；只有 unresolved failsafe / 起始高度太低才 gate-fail。

**灾难类 primary 判据（头条）**：`strict_s0_vs_s3` = 去污染后**经典 S0 ∧ 学习型 S3**，跨种子复现——`≥2/3` 即稳健、`3/3` 更强档。

**有效性纪律**：灾难类一律以**离散 severity + violation 符号**为门、**连续 ρ 只诊断**（jitter 带仅适用近无扰动轨迹，深违反区连续 ρ 不是稳健复现量）；行为类越抖动带 + 触发性质确认（候选因 X 入选 → 仅 X 跨种子复现才 X-confirmed）；invalid（trigger timeout / 去污染失败 / run error / identity 失败）一律排除。

**identity 按 SUT 分派**：`mcnn_identity_gate`（`neural_control` topic）/ `raptor_identity_gate`（controller==raptor、`raptor_status` active、`raptor_input` 有样本、nav 23、**无 `neural_control`**、`policy.tar` staged）。

### 5.3 Policy 的定义（P1–P7，一个 oracle 内的多条 policy）

沿 PGFuzz 的"性质即 oracle"形状，`property_oracle.py` 从 ULOG 算 P1–P7 的连续鲁棒度 ρ_i + 离散 severity：
- **P1 姿态包络** / **P2 角速率**（这两条是**灾难类** policy，对应 S3 失控）
- **P3 饱和** / **P4 平滑** / **P5 settling** / **P6 不振荡** / **P7 无稳态偏差**（行为类 policy）

`oracle_calibration.md` 记 16 阈值 + 抖动标定（P1=0.0128 / P2=0.0935，仅近无扰动轨迹）。

**关键概念（multi-policy ≠ multi-oracle）**：把 policy 库全差分化（同一差分 oracle × 多条 policy）后，**失效收敛到灾难类 P1/P2**——P6/P7 虽多种子确认，但 96%/74% 伴随 S3（是"翻滚中的无人机姿态剧晃 + 跟踪误差爆表"的次级签名，非独立失效），P3/P4/P5 无独立确认。所以"policy 多"不等于"失效类型多"——本项目的科学论断恰恰是**失效收敛，不弥散**。

### 5.4 Scenario fuzzing 的搜索方法

**搜索器 = MAP-Elites（质量-多样性）**，`m2_map_elites.py` 驱动，`campaign_runner.py` 做 N=1 可续编排 + 三臂 + severity-triggered primary + SUT 分派。

**fitness = 差分 gap，不是绝对 ρ**：`gap_i = ρ_i(classical) − ρ_i(neural)`。灾难类 fitness gate：仅当去污染后经典 S0 且 P1/P2 非 vacuous、ρ 有效时 gap 才进 fitness，否则 floor——**绝不奖励 both-crash**（`property_fitness.py`，支持 `--target-properties`）。

**descriptor（行为刻画维度）**：切换区用 `switch_attitude × wind`，把搜索到的场景按行为特征分桶（archive bins），MAP-Elites 在每个 bin 里保留最优 elite → 既找高 gap、又保多样性覆盖。

**V8 附：`guided_abs` / `absolute_severity` fitness 模式已加入**（`--fitness-mode`）——用于 RQ2 fitness 消融（证明**差分** gap 在搜索层也值钱、非仅 MAP-Elites 结构带来），**代码已备、押后未跑**。

### 5.5 对比的 Random 和 Grid 的含义（baseline 语义）

三臂设计，回答"制导到底交付了什么"，对齐 RouthSearch 的搜索算法消融范式：

- **guided（制导臂）**：MAP-Elites + 差分 gap fitness + elite mutation。**被测的"主方法"**。
- **random（随机臂）**：在同一 θ 空间**均匀随机采样**，同预算、同 oracle、同判据、同 descriptor 记录 archive。**回答"你的 fitness 制导相对盲采到底有没有增益"**——这是最硬的 baseline，因为若制导打不过随机，则 fitness 无价值。
- **grid（网格臂）**：在 θ 空间**规则网格枚举**，同预算。**回答"结构化均匀覆盖 vs 制导"**——网格保证空间覆盖但无反馈，用来分离"覆盖"与"制导"两种效应。

**主张边界（重要）**：在切换区因 bug 稠密，guided 相对 random 的优势体现在 **效率（~5× 命中率）/ 照亮密度（~60% 更高 QD）/ 一致性（更低种子方差）/ 快速定位**，**而非独占发现**（3/3 确认档 guided 与 random 打平）。所以论文严禁把 RQ2 框成"guided 找到更多 bug"，只框成"更高效、更一致地照亮并定位失效区"。**完整因果刻画归密扫（RQ3），不归 fuzzer archive**（archive 重分析：特征完整度 2/5）。

---

## 6. 实验设置（两个真实 SUT）

同一 PX4（`3042f906`）、同一机架（**X500 v2**）、同一任务。两个学习型 backend：

- **`mc_nn_control`**（PX4 内置神经模式，TFLM，**前馈网**无递归，15-D 观测/4-D 动作，**无输入裁剪**）。**前馈无积分器**——在 wind+physics / 估计污染上未产生 robust 退化（可被位置反馈补偿），但在**切换瞬态**是灾难差分的失效方。**主 SUT，RQ1/RQ2/RQ3 + multi-policy + wave-2 均基于它。**
- **RAPTOR**（`mc_raptor`，免训基础策略，22-D 观测/4-D 动作，GRU-16 递归，2084 参数，**推理前硬裁剪观测误差** `max_position_error=0.5` / `max_velocity_error=1.0`，源码常量非配置）。**第二 SUT**，V8 完成完整对照。**裁剪保留 = 原始 RAPTOR 语义；去掉即另一个 SUT（future work）。**
- **两者切换路径字节级相同**：`mode_id 23` → 每轮须**正面控制器 ID 确认**（按 SUT 分派 identity gate）。
- **两 board**：`px4_sitl_mcnn_sih`（mc_nn + DDS groundtruth）；`px4_sitl_raptor_sih`（RAPTOR + 补齐的 DDS groundtruth installer，隔离 `MC_RAPTOR` 避免与 `MC_NN_CONTROL` 共存 board）。

**为何 RAPTOR 是有意义的第二 SUT**：它与 mc_nn 在**架构（GRU 递归 vs 前馈）、维度（22-D vs 15-D）、来源（foundation policy vs PX4 内置）、输入处理（硬裁剪 vs 无）**上全不同。这让它成为 harness/oracle 外部效度的强测试——但也正因为差异是多轴同时的，它**不是干净的单变量 learned-vs-learned 对照**（§8）。

---

## 7. 全部结果（完整证据链，按故事顺序）

### 7.1 A 路线：灾难差分锚点（mc_nn 硬结果）
诚实旅程：FUZZ-1 极端角落命中翻机但 confound（过度声称）→ FUZZ-1b groundtruth 对齐后经典也 failsafe 但未翻（二值检测器漏报）→ FUZZ-1c severity 分级 → **FUZZ-1c 去污染重判（`65240a5`）= 4 个干净 strict 差分（pair 1/2/4/5）经典=S0 ∧ mc_nn=S3**。多种子闸：pair1/pair2/pair4 **3/3**、pair5 **8/9 概率性锚点**。GATE-3 反转：mc_nn 对幅度比经典更鲁棒（RMS 经典 0.49 > mcnn 0.38）。

### 7.2 切换区严重度 campaign（`118d58f`，RQ1/RQ2/RQ3）
> 制导搜索掉头对准切换瞬态，一炮补三个 RQ。preflight 纠错（route-A 回归先失败 2/4、护栏正确触发、判据修正为 severity+符号门）是可信度来源。
- **RQ1（存在性）**：guided **179** primary、~10 确认 cell。
- **RQ2（搜索效率）**：guided 179 vs random 40 vs grid 19；~4.5× 密度、命中率 ~60% vs ~12%（~5×）、QD ~189 vs 119 vs 123；**3/3 确认档 guided 与 random 打平（各 6/10）** → 效率/照亮/一致性框架。
- **RQ3（失效刻画，密扫 40 点 120 eval 81 strict）**：姿态非单调（~40° 起、42–45° 稳、48° 部分恢复）；rate 1.55 洞 / 1.75 恢复；风 0–3 暴露 / **4–6 恢复**（反直觉高亮，相位/共振）；delay 0.06/0.12s 时间洞。**高维带洞、非单调标量阈值。**

### 7.3 multi-policy 差分谱系（`db9adc7`，失效收敛证明）
> 纯重分析、零新增 SITL：把判据从灾难类 {P1,P2} 扩到全 P1–P7，看切换区是否还有非灾难独立行为差分。1041 记录、950 valid。
- 确认差分 positive = P1/P2/P6/P7；P3 仅 3 未确认单 eval；P4/P5=0。
- **P6/P7 非独立**：伴随 S3（P6 96% S0→S3、P7 ~74% 落 S3），纯非-S3 确认组=0。
- **结论**：**学习型特有差分收敛到灾难瞬态类（P1/P2），非渐进行为退化**——锐利、可证伪。第三次假阳纪律。

### 7.4 两个诚实 negative（划定失效边界）
- **wave-1 wind+physics（`659c8da`+）**：稳态组合 400 eval（200 guided+200 random）。**strict 绝对违反=0**；戏剧性 P7 退化=共享 SIH 噪声尾巴；只 P4/P6 小而稳架构签名。**assay 正确拒掉 12-finding 假阳。**
- **wave-2 估计污染（`2515aa6`）**：非切换轴 400 eval。**0 strict S0/S3、0 primary、validity 满格**；含一段 Gate A 波折——shim 重建后边界锚点翻转，诊断决定性证据（同种子 shim 一字未改却 S0↔S3）证明**边界锚点本质随机**、排除 shim bug；**gate 方法学升级沉淀**（pair1/2 硬闸 + pair4/5 ≥6/8）。patch drift 就此解决。
- **科学含义**：robust 差分失效**特定于切换瞬态**，不铺到两条稳态非切换轴。关闭"只测了切换"承重质疑。

### 7.5 RQ2 archive 重分析（`rq2_archive_reanalysis_20260705`）
> 回答"guided fuzzer 到底交付了什么"，纯重分析零仿真。
- guided archive **快速照出**高危区：三 run 均在 eval 44/61/88 覆盖 10/10 高危 `rp_3/rp_4 × wind` cell（早于密扫 120）、强复现 42–45° 带。
- **未独立照出完整带洞结构**：rate 洞/恢复、风 4–6 恢复、delay 洞皆 `not_shown`；特征完整度 **2/5**。
- **定位（论文措辞已锁）**：**fuzzer archive = 快速边界定位证据；完整因果刻画来自受控密扫。**

### 7.6 RAPTOR 第二 SUT——完整对照 campaign（V8 完成，干净 negative）
> `3bc618c` smoke（8 真实 ULOG 8/8 identity；4 锚点×2 种子 = 7 S0/1 S1/0 S3）后，跑与 mc_nn switch campaign **严格对齐规模**的完整对照。artifact 落 `aba86101`，报告 `docs/raptor_external_ai_review_2026-07-07.md`。**所有数字已对原始 artifact 独立复算通过。**

**Dense sweep（受控密扫，最干净的一块）**：40 点 × 3 种子 = **120 eval，120 valid，0 invalid，0 strict S0-vs-S3**。RAPTOR 在整个 route-A 失效带上**最高只到 S1**（42–48° 那个 mc_nn 翻机的区域，RAPTOR 清一色 S0/S1）。轴覆盖：attitude 9 点 / requested_rate 9 / wind 7 / switch_delay 7 / approach_phase 8。

**7 臂 search（grid×1 + guided×3 + random×3，各 120 eval）**：

| run | 策略 | eval | runner err | primary cand | reportable | strict | confirmed primary | confirmed reportable | best rel-deg |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| grid_0 | grid | 120 | 19 | 0 | 13 | 0 | 0 | 0 | P2 gap=0.391 |
| guided_0 | guided | 120 | 28 | 0 | 18 | 0 | 0 | 0 | **P2 gap=1.336** |
| guided_1 | guided | 120 | 11 | 0 | 12 | 0 | 0 | 0 | P2 gap=0.669 |
| guided_2 | guided | 120 | 17 | 0 | 13 | 0 | 0 | 0 | P2 gap=0.747 |
| random_0 | random | 120 | 2 | 0 | 11 | 0 | 0 | 0 | P2 gap=0.752 |
| random_1 | random | 120 | 2 | 0 | 5 | 0 | 0 | 0 | P1 gap=0.085 |
| random_2 | random | 120 | 4 | 0 | 10 | 0 | 0 | 0 | **P2 gap=1.222** |
| **合计** | | **840** | **83** | **0** | **82** | **0** | **0** | **0** | 2 个 P2 gap>1.0 |

**Gate0 稳定性 + anchor**：Gate0 30 eval（1 runner err）/ 4 reportable / 0 confirmed；anchor recheck 8/8 rc0、8/8 identity、0 primary；anchor boundary pair4/pair5 各 6 attempt、**RAPTOR S0 全 12/12**、0 primary。

**跨全 campaign 汇总（V8 强化统计，报告应补进去）**：~926 个成功 eval，**RAPTOR 一次都没失控——0 次 S3/S4**；search+gate0 的 786 个成功 eval `raptor_safe=True` **786/786**。quadrant = 700 property_gradient + 86 relative_degradation_differential（后者即 reportable 诊断）。

**RAPTOR 集成是真接线**（非改元数据）：`m2_map_elites.py` 有 `controller="raptor"` SUT spec + `build_px4_raptor_sih.sh` + SUT 分派 + `raptor_identity_gate(identity)`；`validity_automation.py:340` 真 `def raptor_identity_gate`。runner error 是底层 task rc=2/3（progress log 实录 `task node failed rc=3 for classical`），正确排除在 candidate/confirmed 账外。

**结论**：原始 clipped RAPTOR 完成完整对照，**干净 negative——0 strict、0 confirmed、全程守在受控档**。定位见 §8：**oracle 区分力 + harness 外部效度**。

**Unclipped 对照（方案 B，已完成，Outcome B）**：为回答"RAPTOR 鲁棒是否源于输入裁剪"跑了 unclipped RAPTOR 定向对照（run `raptor_unclipped_ablation_20260707`，用时 43.7 min）。做法 = 移除 mc_raptor `observe()` 对 position/velocity error 的裁剪（原界 0.5/1.0，`patches/px4/raptor_unclipped.patch`，改 `mc_raptor.cpp` position/velocity 赋值），得**独立 SUT `raptor_unclipped`**（独立 board `px4_sitl_raptor_unclipped_sih`，`controller="raptor"`、`input_clipping=false`），在已知失效带 8 θ（pair1/2/4/5 + attitude {40,42,45,48}°）× 3 种子 = **24 eval** 与经典/clipped 对照。

- **裁剪确被移除（硬验证，防"clipped 重跑"陷阱）**：正式 run 首 eval 的 active `raptor_input` 实测 max |position|=13.81 m、max |velocity|=5.66 m/s（smoke 时 14.0/6.9），远超旧界 0.5/1.0 → 大误差确进网络，是真 unclipped。
- **结果 = Outcome B**：`total_evals=24, valid=24, invalid=0, strict_s0_vs_s3=0`，`classical_reruns=3`（pair5 三种子）。unclipped RAPTOR 清一色 S0（仅 pair1 一个种子 S1），经典全 S0，无一格 classical-S0 ∧ unclipped-S3。**去裁剪后 RAPTOR 仍不失控 → 裁剪被排除为鲁棒主因。** 逐 θ：pair1 S0×2/S1×1，pair2/pair4/pair5、attitude 40/42/45/48 全 S0×3，strict 全 0/3。
- **诚实定界（重要，防过度解读）**：(1) 范围限已知失效带 8 θ，不是"裁剪在任何区域都无关"；(2) confound 只**减一条**——RAPTOR 仍与 mc_nn 在架构（GRU 递归 vs 前馈）/维度（22 vs 15）/训练（foundation vs 内置）上不同，故 §8 定位**不变**：negative 仍只撑区分力+外部效度，**不**因裁剪被排除就升为 learned-specificity；(3) **未正面主张**"鲁棒是架构/训练所致"（那几轴未拆），只主张"非裁剪所致"；(4) pair1 的 S0→S1 说明裁剪并非全无作用（对最高误差锚点有轻微、非灾难性影响），只是不承载 S0-vs-S3 边界。
- **运行时 caveat**：本对照跑在 Jazzy/Py3.12，clipped campaign 当时 Humble/Py3.10；控制器本体是编译进 board 的 C++、θ 读同批 config、severity 同一 `property_oracle`，差异仅在 ROS 传输层（plumbing 非控制器 confound），报告认领一句即可。artifact `runs/campaigns/raptor_unclipped_ablation_20260707/`（本地）+ preflight `docs/raptor_unclipped_ablation_preflight_20260707.md`。

### 7.7 结果一览

| 实验 | 轴 / 对象 | 规模 | 判据结果 | 论文角色 |
| --- | --- | --- | --- | --- |
| A 路线锚点 | 切换瞬态 mc_nn | 4 pair 多种子 | **经典 S0 ∧ mc_nn S3**（3/3×3、8/9） | 头条灾难差分 |
| 切换区 campaign | `attitude×wind` mc_nn | 3 臂 + 密扫 | 179 primary、~10 确认、带洞边界 | RQ1/RQ2/RQ3 |
| multi-policy | P1–P7 mc_nn | 950 重分析 | 收敛到灾难类（P1/P2） | 失效收敛论断 |
| wave-1 | wind+physics mc_nn | 400 | 干净 negative | 边界对照 |
| wave-2 | 估计污染 mc_nn | 400 | 干净 negative | 边界对照 |
| RQ2 archive | fuzzer 交付物 | 重分析 | 定位 ✓、完整刻画 ✗ | RQ2/RQ3 挂钩 |
| **RAPTOR 对照** | 切换瞬态 RAPTOR | dense+7臂+gate+anchor (~926) | **干净 negative、0 失控** | **oracle 区分力 + 外部效度** |
| **unclipped 对照** | 切换瞬态 `raptor_unclipped` | 8 θ × 3 = 24 | **0 strict、去裁剪仍守住（Outcome B）** | 裁剪排除为鲁棒主因 |

---

## 8. 两个 SUT 到底证明了什么（定位纪律，V8 核心）

**这是审稿人一定会敲的关口，措辞必须锁死。**

**规则一：RAPTOR 的 negative 不支撑"学习型特有性"。**
头条断言是"`mc_nn_control` 有经典没有的切换瞬态灾难差分"。这条**只靠 mc_nn ↔ classical 同条件对照成立**，与 RAPTOR 是否失败无关。若把 RAPTOR negative 说成"learned-vs-learned 支撑了 learned-specificity"，逻辑是反的——一个学习型控制器**不**出此失效，只说明该失效**不是"学习型"的一般属性**、而是 mc_nn（前馈、无积分器、无裁剪）这个特定架构的属性。**全文口径**：learned-specificity 的书由 mc_nn↔classical 背，RAPTOR 一个字都不背。

**规则二：RAPTOR 是多轴混杂，不是干净的单变量对照。**
RAPTOR 与 mc_nn 同时在**裁剪 / 架构（GRU vs 前馈）/ 维度（22 vs 15）/ 来源（foundation vs 内置）**上不同。"RAPTOR 守住 / mc_nn 翻"这个差异**无法归因到任何单一原因**。特别地，RAPTOR 守住**可能只是因为"裁剪管用"**（把大观测误差硬夹掉，切换瞬态的极端误差进不了网络）。因此 RAPTOR **不构成**"学习型控制器普遍鲁棒"的证据，也不构成"RAPTOR 的鲁棒是学习出来的"的证据。**（rev 补注）unclipped 对照排除了裁剪这一条（§7.6 Outcome B），但规则二仍成立**：RAPTOR 与 mc_nn 在架构/递归/维度/训练上依旧多轴不同，裁剪被排除**不**把 RAPTOR 变成干净单变量对照，也**不**允许由此推出"鲁棒是内在/学习所致 → 支撑 learned-specificity"。裁剪的排除只关闭"RAPTOR negative 是裁剪 artifact"这记攻击，不改本节定位。

**规则三：能诚实主张的是这两条（对方法稿而言反而更值钱）。**
- **oracle 区分力 / 精度**：差分 oracle + severity 纪律在 mc_nn 上 fire、在鲁棒的 RAPTOR 上**正确保持沉默**（0 误报 primary）。这证明它**不是"见 NN 就报警"的 trivial 检测器**——是**第四次假阳纪律演示**。对一个把"可靠 oracle + 假阳纪律"当头条支柱的方法稿，这是强证据（一个干净 negative 比"RAPTOR 也翻"更能证明 oracle 有辨别力）。
- **harness 外部效度（C4）**：同一管线不改地跑通第二个架构迥异的真实 shipped 控制器，identity 按 SUT 分派、classical 复用、判据一致。这是"免训可复现测试平台"的实锤。

**要主动预防的那记闷棍**："那你的头条是不是只是个 mc_nn 实现 bug、而非学习型控制问题？" **诚实答复**：我们提出的是一个**方法**（可靠差分 oracle + scenario fuzzing），在 mc_nn 上决定性演示了一类切换瞬态灾难差分；RAPTOR 证明该方法**有区分力**（不滥报鲁棒控制器），而**非**证明所有学习型控制器都失效。至于"RAPTOR 鲁棒是内在还是裁剪所致"——**裁剪已被 unclipped 对照排除（§7.6/§11.1，Outcome B）**；剩余来源（架构/递归/训练）仍纠缠未拆，但对方法稿不必拆，关键是该问题已**不再是悬空 confound**、也不改本方法的区分力主张。

**一句话记法**：**mc_nn↔classical = 找到并归因失效（learned-specific）；RAPTOR↔classical = 证明 oracle 有辨别力 + 平台可迁移（discriminative + external validity）。两条腿，各走各的路，绝不混。**

---

## 9. 威胁与诚实 negative（边界，写作时主动认领）

1. **RAPTOR 裁剪——已测试排除（原"最重"威胁，现已降级）**：曾担心 clipped RAPTOR 的鲁棒源于输入硬裁剪而非控制器本身。**unclipped RAPTOR 定向对照（§7.6 Outcome B）已直接测试并排除**：去掉裁剪（实测大误差确进网络）后，RAPTOR 在已知失效带 24 eval 仍不失控、0 strict。→ 裁剪非鲁棒主因。**残余 caveat 要认领**：(a) 排除范围限已知失效带 8 θ，非全空间；(b) 这只减掉一条 confound，RAPTOR 与 mc_nn 仍多轴不同，故**不改** §8 定位（RAPTOR 仍只撑区分力+外部效度，不撑 learned-specificity）；(c) 未正面归因鲁棒来源（架构/训练未拆）。**净效果**：审稿人不能再用"你的 RAPTOR negative 只是裁剪 artifact"这招；但 RAPTOR 也仍不能撑更强主张。
2. **guided 臂覆盖被 runner error 啃掉**：guided_0 只有 73/120 classical-usable（28 个 rc=3）。**但 negative 不靠 guided 兜底**——dense sweep 是 0 error、确定性、120/120 覆盖精确失效带的 backstop。认领即可，不推翻结论。
3. **dense 是有限 axis grid，非连续全空间**：受控密扫覆盖预定义轴网格，不是整个连续 route-A 空间。
4. **相对退化候选是真诊断、但 confirmed 为空**：reportable（含 P2 gap>1.0）是连续 ρ 的相对退化，不带 severity 级失控；作诊断信号、不升为发现。
5. **SIH-only、无真机、无 ArduPilot**：SIH 非 bit-exact（多种子 + 严重度纪律应对）；RQ4 迁移部分由两 SUT 答，真板/ArduPilot 延后作 threats。
6. **三个诚实 negative 是边界不是失败**：wind+physics、估计污染、multi-policy 行为类独立性——把正面发现衬托出来并划定边界。

---

## 10. 论文故事与最终主张（V8 定形）

**头条 = "面向集成进固件的学习型飞控的、以可靠差分 oracle 为核心的场景测试方法"**，SE 方法稿（FSE/ISSTA）。

**价值支柱（如何环环相扣）**：
- **(方法) 可靠差分 oracle**：三卫生 + severity-triggered 判据 + **四次假阳演示**（wave-1 拒 12-finding、multi-policy 判 P6/P7 次级、wave-2 判诊断/未确认、**RAPTOR 对鲁棒 SUT 正确沉默**）+ 升级后的 gate 方法学。→ 绕过 oracle 问题、且被证明有辨别力。
- **(RQ1) 系统化存在性**：制导搜索在切换区系统化触发灾难差分（179 primary）。
- **(RQ2) 搜索效率与定位**：guided ~5× 命中率、~60% QD、archive 快速定位（3/3 打平 → 效率/一致性/定位框架，非 bug 计数）。
- **(RQ3) 高维带洞失效边界**：逐轴刻画（姿态/rate/风/delay/相位皆有洞或恢复，含反直觉高风恢复，来自密扫）。
- **(承重质疑已答) 学习型特有 vs 切换特有**：wave-1/wave-2 两条非切换轴 negative → 失效**钉死在切换瞬态**。
- **(外部效度 + oracle 区分力) 两 SUT**：mc_nn↔classical 给 learned-specific 灾难差分；RAPTOR↔classical 给 oracle 区分力 + harness 可迁移。
- **(诚实边界) 三个 negative + 裁剪 confound 已由 unclipped 对照实验排除（Outcome B，§7.6）+ 残余多轴 confound 认领**。

**为何这套适合 FSE/ISSTA**：scope 与 RouthSearch（ISSTA'25）同量级、目标（学习型固件级控制器 + 差分 oracle）更新颖；头条是方法可靠性 + 假阳纪律 + 可复现 + 系统化刻画 + 诚实边界，而非 bug 计数——正是 testing/方法稿的评价维度。

---

## 11. 路线图：未来对照补全 + 其它 Oracle 引入可能

### 11.1 unclipped RAPTOR 小对照（方案 B，✅ 已完成，Outcome B）
- **动机（已达成）**：测试裁剪 confound——若去裁剪后 RAPTOR 在已知失效带翻则裁剪是鲁棒主因，若仍守住则排除裁剪。**结果：仍守住 → 排除。**
- **实现**：`patches/px4/raptor_unclipped.patch` 去掉 mc_raptor `observe()` 对 position/velocity error 的裁剪（原界 0.5/1.0）；独立 board `px4_sitl_raptor_unclipped_sih` + 独立 SUT `raptor_unclipped`（`controller="raptor"`、`input_clipping=false`）；driver `scripts/run_raptor_unclipped_ablation.py`。
- **规模 / 结果**：8 θ（pair1/2/4/5 + attitude {40,42,45,48}°）× 3 种子 = 24 eval，43.7 min。`valid=24, strict_s0_vs_s3=0`，unclipped 清一色 S0（pair1 一个 S1）。裁剪移除经 `raptor_input` dump 硬验证（max |pos|=13.81 m、|vel|=5.66 m/s ≫ 0.5/1.0）。详见 §7.6。
- **对论文的净效果**：§9 裁剪 threat 从"最重、未测"→"已测排除（限已知失效带）"；关闭"RAPTOR negative 是裁剪 artifact"攻击面；**但不升级 §8 定位**（多轴 confound 仍在，未正面归因鲁棒来源）。
- **可选后续（非必需）**：若要把"非裁剪 → 那是什么"再往前推一步，可逐一 ablate 递归（GRU→无状态）或 obs 维度——但这是机理稿方向，方法稿**不需要**，登记备忘即可。

### 11.2 其它 Oracle 引入可能（按可行性 + 可信性排序）
1. **变形/对称（equivariance）oracle** — 高/高。**唯一剩余便宜上行**：复用 harness、靶区（已知非单调区）已知。场景旋转/镜像 → 响应应相应变换；经典对称由构造、神经破对称 = NN-specific bug。**是唯一能补差分 oracle completeness 盲区（"两者都失败"或"无法对照的失效"）的候选**——若在已知非单调区落一个**不同类型的干净 positive**，可升为并列 headline；否则并入诚实叙事。**未做，非完整性必需。**
2. **性质/规约（PGFuzz 式 MTL）oracle** — 中高/高。**已实现**（P1–P7），两条非切换轴均干净 negative，**反衬差分 oracle 价值**（规约类既易假阳、又对瞬态失效视而不见）。
3. **鲁棒性/平滑（离线对抗敏感度）** — 高/中高。stretch。
4. **更强参照差分（MPC / 可达性认证）** — 最高可信 / 最低可行。stretch；A 路线已有轻量版（经典即参照）。

### 11.3 RQ2 统计加固 + fitness 消融（代码已备、押后）
10+ 种子四臂（`guided_diff`/`random`/`grid`/`guided_abs`）+ Mann-Whitney U + Vargha-Delaney A₁₂，对齐 RouthSearch 标杆；`--fitness-mode` 已备。约 5–10 天串行大件。**用户曾选先解 SUT；SUT 已解，此项可择时启动或留作投稿前加固。**

---

## 12. 旅程总教训（诚实回路 = 可信度来源）

1. 两个产线学习型控制器对大误差/幅度类都鲁棒；mc_nn 的差分活在**切换瞬态**（灾难类）+ 失效结构。
2. 差分 oracle 真实有效，但可靠性依赖卫生机制 + 假阳纪律（**连续 ρ 在深违反区不是稳健复现量**）。
3. 二值检测器抹平真实质差。
4. **失效收敛，不弥散**：multi-policy 证收敛到灾难类、wave-2 证特定于切换瞬态。"加厚度"的正确方式不是找更多失效类型/轴（问过了、答案是收敛），而是提升目标新颖性 + 刻画深度 + 诚实边界 + 第二 SUT + 统计严谨度。
5. **回归 gate 须区分确定性锚点与随机边界锚点**：单样本卡边界锚点欠功率（Gate A 教训）；正确形态 = pair1/2 硬闸 + pair4/5 概率跟踪。锚点可复现性本身在测绘分岔边界，反哺 RQ3。
6. **agent 产出的代码 ≠ 已验证**：RAPTOR shim 曾缺 position 注入路径，只有真跑行为验证才暴露。
7. **（V8 新）一个干净 negative 的价值取决于你让它证什么**：RAPTOR negative 若被迫背"learned-specificity"就是软肋，被正确定位成"oracle 区分力 + 外部效度"就是支柱。**定位精度本身是可信度的一部分**——措辞踩松会被审稿反咬，踩准则加分。
8. **（rev 新）消融的可信度全靠"确认变量真的变了"**：unclipped 对照的 negative 之所以可信，是因为先用 `raptor_input` dump 拿到 13.81 m / 5.66 m/s 的正证据、证明裁剪确被移除——否则 build 缓存或改错模块会让你把 clipped 又跑一遍、得到假 null。**任何 ablation 都要先证明干预生效，再读结果。** 且排除一条 confound（裁剪）≠ 归因（架构/训练仍未拆），措辞只说"排除 X"、不说"因此是 Y"。

---

## 13. 环境 / 复现 / 工程约定（给 agent）

- **容器入口**：`sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<n> ./docker/run.sh bash -lc "..."'`。镜像 `uav_sf:phase1`。用 `sg docker`、避免 sudo。坑见 `AGENT.md`。
- **PX4**：固定 `3042f906`，源码 `external/PX4-Autopilot`（gitignored）。**两 board**：`px4_sitl_mcnn_sih`、`px4_sitl_raptor_sih`（+DDS groundtruth installer）。mode-23 飞行须按 SUT 分派 identity gate 正面确认。
- **RAPTOR 集成注意**：SUT selector（`mcnn|raptor`，默认 mcnn）；`raptor_identity_gate()`（raptor_status/raptor_input/nav23/无 neural_control/policy.tar staged）；RAPTOR runner 需 `policy.tar` staging；**ROS overlay 须匹配运行时（3.10/Humble，防 Py3.12 残留致 `RaptorStatus`/`RaptorInput` 加载失败）**；**输入裁剪（`max_position_error=0.5`/`max_velocity_error=1.0`）在 `raptor` 保留 = 原始语义；去掉 = 独立 SUT `raptor_unclipped`（独立 board `px4_sitl_raptor_unclipped_sih`，`patches/px4/raptor_unclipped.patch`，`m1_diff_runner.py` 认 `PX4_RAPTOR_BUILD_DIR` 指向 unclipped build）——§11.1 对照已完成**。**三 board 现存**：`px4_sitl_mcnn_sih` / `px4_sitl_raptor_sih` / `px4_sitl_raptor_unclipped_sih`。
- **git 卫生**：`*.ulg`/`runs/`/`docs/**/evals/`/checkpoint gitignore、留本地。**注意 V8 例外**：RAPTOR 全量 campaign 的 top-level run artifact（summary/jsonl/candidate/theta）已用 `-f` 强推进 `runs/campaigns/raptor_*_20260705/`（commit `aba86101`）作可复现 review artifact；per-eval `evals/` 与 `.ulg` 仍留本地。commit 只含代码+报告+这批 review artifact。验证：`py_compile`/`compileall`/`unittest`/`bash -n`/`jq empty`/`git diff --check`。
- **吞吐 / 并行（硬约束）**：**N=1 @ `PX4_SIM_SPEED_FACTOR=1.25` ≈ 22–23 eval/h**。并行不可用（根因 = offboard setpoint 是 wall-clock ROS timer、未锁 lockstep）。所有 campaign（含 RAPTOR 全量）均串行 N=1 跑完。
- **SIH 固有抖动 + 判据**：固定 `(θ,seed)` 串行重跑 ρ 也抖；灾难类复现一律以离散 severity + violation 符号为门、连续 ρ 只诊断；边界锚点用概率判据（pair4/5 ≥6/8）、确定性锚点（pair1/2）单样本硬闸。
- **关键脚本**：`m1_offboard_task.py`（`--controller raptor|mcnn`）、`m1_compare.py`（`--neural-controller raptor|mcnn`）、`property_oracle.py`（`--controller raptor|mcnn|classical`）、`theta_genome.py`、`property_fitness.py`（`--fitness-mode`）、`validity_automation.py`（SUT 分派 identity）、`m2_map_elites.py`（SUT selector）、`campaign_runner.py`（三臂可续 + SUT 分派）、`route_a_anchor_regression.py`（多种子 severity+符号闸）、`multipolicy_differential.py`、`rq2_archive_reanalysis.py`、`run_switch_dense_sweep.py`（RAPTOR dense sweep）、`build_px4_raptor_sih.sh` / `install_raptor_sih_board.sh`、`run_raptor_unclipped_ablation.py`（unclipped 对照 driver）、`build_px4_raptor_unclipped_sih.sh` / `install_raptor_unclipped_sih_board.sh`、`m1_diff_runner.py`（认 `PX4_RAPTOR_BUILD_DIR`）、`m2b_1_dump_raptor_input.py`（裁剪移除硬验证）。
- **关键报告/标定**：`oracle_calibration.md`、`oracle_map_and_property_set_v0.1.md`、`switch_severity_campaign_20260629.md`、`multipolicy_differential_20260703.md`、`wave1_windphysics_20260627.md`、`wave2_statecontam_campaign_20260703.md`、`wave2_gateA_diagnostic_20260703.md`、`raptor_recon_2026-07-05.md`、`raptor_reintegration_smoke_2026-07-05.md`、`rq2_archive_reanalysis_20260705.md`、**`raptor_external_ai_review_2026-07-07.md`（RAPTOR 全量 campaign 报告 + 外部 review packet）**、**`raptor_unclipped_ablation_preflight_20260707.md`（unclipped 对照 preflight + GO/结果）**。
- **最近 commit / run**（新→旧）：**unclipped 对照代码（`patches/px4/raptor_unclipped.patch` + unclipped board/build/install + SUT `raptor_unclipped` + driver + tests）+ run `raptor_unclipped_ablation_20260707`（24 eval，Outcome B，本地 artifact）** ｜ **`aba86101`（RAPTOR 全量 campaign review artifact：dense sweep 120/0 strict + 7 臂 840/0 confirmed + gate0/anchor negative + 外部 review 报告）** ｜ `3bc618c`（RAPTOR SUT 集成 smoke）｜ `2515aa6`（wave-2 估计污染 campaign）｜ `62e1d01`（wave-2 preflight）｜ `03f5155`（campaign artifact docs + m2_primary_bugs 入库）｜ `db9adc7`（multi-policy 差分谱系）｜ `118d58f`（切换区严重度 campaign）｜ A 路线：`65240a5`、`301f564`、`345d2c6`、`4685b96`、`a8dd59b`、`b0121ee`。

---

## 14. 决策状态 + 待办（战略：三质疑已关 + 两 SUT 收口，写作待启）

**已完成**：A 路线锁定 + 多种子；切换区 campaign（RQ1/RQ2/RQ3）；multi-policy 收敛；wave-1/wave-2 双 negative；RQ2 archive 定位；**RAPTOR 完整对照（干净 negative，两 SUT 收口）**；**unclipped RAPTOR 对照（Outcome B，裁剪 confound 实验排除）**。

**当前决策 = 方案 A：收范围 + 开写**。数据侧无 open loop，两 SUT 方法论叙事到位。论文正文仍停在 M0/M1 旧稿（RAPTOR-only），**这是当前最大未做块**——但**本轮只重构叙事到 V8，不动正文**（用户明确）。

**待办队列**：
1. ✅ **（已完成）unclipped RAPTOR 对照（§11.1）**：裁剪 confound 已实验排除（Outcome B）。
2. **（押后）RQ2 统计加固 + fitness 消融（§11.3）**：10+ 种子四臂 + Mann-Whitney U + A₁₂，投稿前加固。
3. **（可选便宜上行）变形/对称 oracle（§11.2）**：补 completeness 盲区，未做非必需。
4. **（可选）补专门报告**：全量 campaign 报告与外部 review packet 是同一份（`raptor_external_ai_review_2026-07-07.md`），投稿 artifact 可拆纯内部报告；unclipped 对照的**结果段**目前在 preflight doc + 本叙事 §7.6，若要独立引用可补一份 `docs/raptor_unclipped_ablation_20260707.md`。
5. **（写作时主动处理）审稿攻击面**：RQ2 的 3/3 打平（效率/定位框架 + 统计加固）；**RAPTOR 裁剪 → 已由 unclipped 对照排除（§7.6/§9），写作时直接呈现该 negative，不再作 open threat**；SIH-only 无真机无 ArduPilot（RQ4 部分由两 SUT 答、其余 threats）。

**已定口径**：灾难类 primary = `strict_s0_vs_s3 ≥2/3`（3/3 另报）、severity+符号门；行为类越抖动 + 触发性质确认；invalid 排除；回归 gate = pair1/2 硬闸 + pair4/5 概率 ≥6/8；**两 SUT 定位 = mc_nn↔classical 给 learned-specific、RAPTOR↔classical 给区分力+外部效度（§8）**。

**悬而未决**：工具名（`[TOOL]`）；目标会议 FSE vs ISSTA（窗口未定）；unclipped 对照结果（Outcome B，已完成）是否**入本篇正文**（建议入——它把最重的 threat 变成一个诚实 negative，性价比高）还是仅留 threats 一句；写作起步时机。

---

## 15. References（待补 venue/DOI）

- Wang et al. **DPFuzzer.** ICSE 2025. ｜ Chambers et al. **SaFUZZ.** ICSE 2026. ｜ Kim et al. **PGFuzz.** NDSS 2021.
- **RVFuzzer.** USENIX Sec 2019. ｜ **LGDFuzzer.** ICSE 2022. ｜ **IMUFuzzer.** ASE 2025. ｜ **ADGFuzz.** ｜ **RouthSearch.** ISSTA 2025.
- Choi et al. **CPI.** CCS 2020. ｜ ARCH-COMP AINNCS；S-TaLiRo / Breach / ARIsTEO；NNV / Verisig / CORA.
- Eschmann, Albani, Loianno. **RAPTOR: A Foundation Policy for Quadrotor Control.** Science Robotics 2026 / arXiv:2509.11481.
- Hegre et al. **A Neural Network Mode for PX4 on Embedded Flight Controllers.** arXiv:2505.00432, 2025.
- Zhang et al. **A Learning-Based Quadcopter Controller With Extreme Adaptation.** IEEE T-RO 2025.
- SBFT CPS-UAV Testing Competition（CAMBA / TUMB / WOGAN-UAV / DeepHyperion-UAV / AmbieGen / TAIiST）；SwarmFuzz.
- PX4 v1.17/v1.18 Release Notes；PX4 Neural Network Control / RAPTOR / SIH / System Failure Injection 文档。
