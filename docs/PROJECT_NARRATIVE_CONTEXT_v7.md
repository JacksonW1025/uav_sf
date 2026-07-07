# 项目叙事与上下文文档 v7 — 学习型 UAV 飞控的场景模糊测试

**用途**：切换对话时的完整上下文 + 给执行 agent 的叙事参考。读完即可接续，无需回溯历史对话。
**取代**：v6。**本版的核心变化**：v6 停在一个已重新洗牌的岔口——"论文脊柱已完整、写作是最大未做块"，并把 wave-2 / 变形 oracle 从"必需"降为"可选上行"。v7 记录项目在 v6 之后**沿上行方向连做了三件事、并都成功地收敛或闭合了关键质疑**：
1. **multi-policy 差分扫（`db9adc7`）** → 把差分 oracle 的判据从灾难类 {P1,P2} 扩到全 P1–P7；结果是**失效收敛到灾难类**（P3/P4/P5 无确认 positive，P6/P7 是伴随灾难的次级签名）。**关闭"只有一种 unsafe 撑不起 fuzzing"的焦虑**——不是靠找到更多失效类型，而是靠**证明失效本质是单一的灾难性分岔**。第三次演示假阳纪律。
2. **wave-2 估计污染 campaign（`2515aa6`）** → 修复 shim（补全 position 通道，**patch drift 已解**）、打通 genome 污染轴（v6 的 DEFERRED 项已 DONE）、跑完整三臂；结果是**干净 negative**（400 eval 0 strict 差分）。**把 robust 差分失效钉死在切换瞬态**，关闭承重质疑"这是学习型弱点还是你只测了切换那个特殊时刻"。
3. **RAPTOR 重新集成为可比第二 SUT（`3bc618c`）+ 完整对照 campaign 进行中** → 勘察查明 RAPTOR 旧"robust"是低证据等级 null（源码级输入裁剪 + lightweight closeout），把原始（保留裁剪）RAPTOR 接进与 mc_nn 完整可比的管线。**正在关闭"单 SUT"外部效度短板。**

同时：**Gate 方法学升级**（单样本卡所有锚点 → 确定性硬闸 + 边界概率跟踪）；**公开仓已同步**（不再停在 RAPTOR 线）。**写作仍是最大未做块。**

**Date**: 2026-07-05
**Repo**: `github.com/JacksonW1025/uav_sf`，工作区 `/mnt/nvme/uav_sf`（容器内）。PX4 固定 `main@3042f906abaab7ab59ae838ad5a530a9ef3df9a6`（v1.18 alpha）。**公开 GitHub main 现已同步至 RAPTOR 集成（`3bc618c`）**——A/B 路线、切换区 campaign、multi-policy、wave-2、RAPTOR 集成均已推上公开 main（v6 遗留的公开仓同步 gap 已闭合，见 §9）。
**配套设计文档**：`oracle_map_and_property_set_v0.1.md`、`docs/wave1_windphysics_20260627.md`、`docs/switch_severity_campaign_20260629.md`、**`docs/multipolicy_differential_20260703.md`（P1–P7 差分谱系）**、**`docs/wave2_statecontam_campaign_20260703.md`（wave-2 干净 negative）**、`docs/wave2_gateA_diagnostic_20260703.md`（Gate A 根因诊断）、`docs/raptor_recon_2026-07-05.md`（RAPTOR 现状勘察）、`docs/raptor_reintegration_smoke_2026-07-05.md`（RAPTOR 集成 smoke）、`docs/rq2_archive_reanalysis_20260705.md`（RQ2/RQ3 挂钩重分析）。

---

## 0. 速览（TL;DR）

**Idea**：学习型低层飞控（PX4 Neural Control、Science Robotics 的 RAPTOR 基础策略）正进入生产自驾仪却没有系统化安全测试。我们在**同一固件、同一机架、同一任务**下，用搜索（fuzzing）在扰动/机动/故障/指令的场景空间里找学习型控制器的失效，用**经典控制器当内建差分 oracle**（经典 safe ∧ 学习型 unsafe）作为闭环控制失效的归因。**定位 = SE 方法稿**：头条不是"抓了多少 bug"，而是可靠 oracle + 假阳纪律 + 可复现 + 系统化失效刻画。

**当前状态（v7：正面发现 + 三个干净 negative 划定其边界 + 两个 SUT 在收口）**：
- **A 路线（灾难差分锚点，已锁 + 多种子确认）**：mode-23 中途交接剧烈状态，经典 **S0 干净恢复** ∧ `mc_nn_control` **S3 失控翻机**（>90°、>8 rad/s）。多种子 severity+符号闸：pair1/pair2 **3/3**、pair4 **3/3**、pair5 **8/9 概率性锚点**。
- **切换区严重度 campaign（`118d58f`）**：RQ1 系统化（179 guided primary、~10 确认 cell）+ RQ2（制导效率框架，~5× 命中率，3/3 确认档打平）+ RQ3（高维带洞非单调边界，含反直觉"高风恢复"）。
- **multi-policy 差分谱系（`db9adc7`，v7 新）**：P1–P7 全差分化，950 valid eval 重分析（零新增仿真）。**确认差分 positive = P1/P2/P6/P7，但 P6/P7 是伴随灾难（S3）的次级签名（P6 96% S0→S3、P7 ~74% 落 S3；纯非-S3 确认组 = 0）；P3 仅 3 个未确认单 eval、P4/P5 = 0**。**结论：学习型特有的差分失效收敛到灾难性瞬态类，而非渐进行为退化**——一个锐利、可证伪的科学论断。
- **wave-2 估计污染 campaign（`2515aa6`，v7 新）**：非切换轴（估计污染，走已修复的 M2B shim），descriptor `velocity_bias × angular_rate_bias`，200 guided + 200 random。**干净 negative：0 strict S0/S3 差分、0 primary bug、validity 满格**（delivery/fairness/identity/decontam 200/200）。P2/P4 相对退化可复现但只作诊断；P7 假设 targeted confirmation 仅 1/12，**未确认**。**科学含义：robust 差分失效特定于切换瞬态，不铺到稳态估计污染。**
- **RQ2 archive 重分析（`rq2_archive_reanalysis_20260705`，v7 新）**：guided archive **快速定位**核心高危 `attitude × wind` 区（三 run 均在 eval 44/61/88 覆盖 10/10 高危 cell，早于密扫 120）、强复现 42–45° 带；**但未独立照出完整带洞结构**（rate 洞/恢复、风 4–6 恢复、delay 洞皆 not_shown；特征完整度 2/5）。**定位：fuzzer archive = 快速边界定位证据；完整因果刻画仍来自密扫。**
- **RAPTOR 第二 SUT（`3bc618c`，v7 新，smoke 已达成 + 完整 campaign 进行中）**：原始（保留裁剪）RAPTOR 已接进与 mc_nn 完整可比的管线（SUT selector + `raptor_sih` board + RAPTOR 专属 identity gate，真实 ULOG 8/8 验证）。smoke（4 锚点×2 种子）RAPTOR **多守住**（7 S0、1 S1、0 S3）。**完整 route-A 对照 campaign（与 mc_nn switch campaign 严格对齐规模）正在跑。**

**下一步（§8）**：三个上行/收口动作把关键质疑逐一关闭——multi-policy 关"只有一种 unsafe"、wave-2 关"只测切换"、RAPTOR 关"单 SUT"。**论文脊柱不仅完整、且被显著加固**（承重质疑已用实验答复、失效边界有三个诚实 negative 划定、两个 SUT 对照在收口）。**RQ2 统计加固 + fitness 消融已备好代码但押后**（用户选择先解 SUT）。**unclipped RAPTOR（裁剪是否鲁棒主因）= future work。写作仍是最大未做块。**

---

## 1. 核心 Idea / Thesis

测学习型控制器的根本难点是 **oracle 问题**：要判它"飞错了"，须先知道"正确飞行长什么样"，而任意扰动下的绝对正确性极难规约。

**关键想法**：PX4 让经典与学习型控制器在**同一固件**共存、可切换。同机架/同任务/同扰动下，若**调好的经典守住、学习型失败**，则该失败**学习型特有**——归因靠结构、不靠手搓正确性规约。在此之上用 fuzzing 搜这些失败。

**v7 的 thesis 加固（承重质疑已被实验答复）**：v6 时最大的概念软肋是"所有决定性 positive 都在切换瞬态，唯一测过的非切换轴（wind+physics）是 negative → 这失效到底是学习型特有还是切换/交接特有？" **wave-2 现在给了实验答案**：在**另一条非切换轴（估计污染）**上跑完整 campaign，仍是**干净 negative**。因此 thesis 可以下一个更强、更可证伪的断言——

> **这个学习型控制器（mc_nn_control）的 robust 特有差分失效，特定于控制模式切换瞬态；在稳态风+物理、稳态估计污染两个非切换轴上，以及在切换区的非灾难行为性质（P3–P7 独立）上，均无 robust 差分。**

这不是"只测了切换所以不算"，而是"测了多个非切换/非灾难维度、都干净、失效边界就在切换瞬态灾难类"。三个诚实 negative（wind+physics、估计污染、multi-policy 行为类）不是三次失败，是把正面发现（切换灾难差分）**衬托出来并划定其边界**的三根对照。

**概念澄清（multi-policy ≠ multi-oracle，v7 定形）**：差分 oracle 是一个**机制**（经典 ⊨ ∧ 学习型 ⊭），机制内部可挂多条 **policy**（P1–P7，PGFuzz 形状——PGFuzz 的"多"也是一个 MTL oracle 下的多条 policy，不是多种 oracle 类型）。multi-policy 扫把 policy 库全差分化后，失效**收敛到灾难类**。所以"厚度"不来自 oracle 类型数、也不来自 policy 数，而来自**目标新颖性（学习型控制器 + 差分 oracle）+ 刻画深度 + 诚实边界**。

---

## 2. Contribution（据 v7 结果升级）

### 2.1 方法稿贡献（C1–C5）
- **C1**：学习型 UAV 飞控的差分场景模糊测试**问题表述**。✓
- **C2（已验证 + 假阳纪律三次演示 + gate 方法学升级）**：**可靠的内建跨控制器差分 oracle**——对齐切换状态 + 分级严重度 + 基建去污染 + 灾难类以离散 severity/符号确认、行为类越抖动 + 触发性质确认。已自动化（`validity_automation.py`）。**假阳纪律现已三次公开演示**：wave-1 拒 12-finding 噪声假阳；**multi-policy 把 P6/P7 正确判为伴随灾难的次级签名而非独立失效**；**wave-2 把 P2/P4 相对退化与 P7 候选正确判为诊断信号/未确认而非 robust 失效**。**gate 方法学升级（v7）**：回归判据从"单样本卡所有锚点"改为"确定性锚点（pair1/2）硬闸 + 边界锚点（pair4/5）概率跟踪（≥6/8）"——单样本卡随机边界点本就欠功率，这是可复用于每次 PX4 改动的标准回归闸。✓
- **C3（已答，带效率框架）**：面向学习型控制的**搜索反馈/制导**——差分 gap fitness + MAP-Elites + baseline 消融。guided 以 ~5× 命中率、~60% 更高 QD、更低种子方差**更密更全地照亮**灾难差分区，**但 3/3 确认档与 random 打平**——主张 = 效率/照亮/一致性，非 bug 计数。**archive 重分析（v7）进一步定位**：guided archive 快速照亮高危区、但完整带洞刻画来自密扫，故 RQ2 贡献严格限定在"效率/定位/一致性"，RQ3 因果刻画归密扫。**RQ2 统计加固（10+ 种子 + Mann-Whitney U + A₁₂）+ fitness 消融（`guided_abs` 绝对 severity 臂）代码已备好、押后未跑。** ✓（带 caveat，统计加固待补）
- **C4（v7 实质推进）**：**免训、可复现的测试平台/基准**，实例化在两个真实 shipped 控制器上。**v6 时 RAPTOR 只是"编入但未启动/低证据 null"；v7 已把原始 RAPTOR 真正接进完整可比管线**（SUT selector + RAPTOR identity gate + `raptor_sih` board，真实 ULOG 验证），完整对照 campaign 进行中——"两个真实控制器"从名义变为**真在跑的对照**。✓（对照 campaign 进行中）
- **C5（更丰富）**：学习型控制器**失效分类**——切换瞬态灾难差分（P1/P2）+ 高维带洞边界（姿态/rate/风/delay/相位皆有洞或恢复区）+ **三个诚实 negative 划定边界**（wind+physics 行为类、估计污染、multi-policy 行为类独立性）+ 小 P4/P6 架构签名。缓解仍在 discussion 层。✓（分类成形，缓解待补）

### 2.2 经验头条结果
- **A 路线（灾难差分锚点）**：经典 S0、mc_nn S3 翻机；多种子复现（3/3、3/3、3/3、8/9）；反直觉 mc_nn 对幅度比经典更鲁棒（GATE-3）。
- **切换区严重度 campaign**：179 guided primary、~10 确认 cell；guided 效率碾压 random/grid（3/3 打平）；边界经密扫刻画为**高维带洞、非单调**，含"高风恢复"。
- **multi-policy 差分谱系（v7）**：P1–P7 全差分化 → **失效收敛到灾难类**（P1/P2 主导，P6/P7 伴随，P3/P4/P5 无独立失效）。
- **wave-2 估计污染（v7）**：非切换轴 400 eval **干净 negative** → robust 差分失效钉死在切换瞬态。
- **RAPTOR 集成 smoke（v7）**：原始 RAPTOR 在 mc_nn 翻机的锚点上**多守住**（7 S0/1 S1/0 S3）→ 早期指向 learned-vs-learned 对照（待完整 campaign 确认）。

### 2.3 演进后的论文主张（v7 定形）
**头条 = "面向集成进固件的学习型飞控的、以可靠差分 oracle 为核心的场景测试方法"**。价值支柱：**(方法)** 可靠差分 oracle（三卫生 + severity-triggered 判据 + 三次演示的假阳纪律 + 升级后的 gate 方法学）；**(RQ1/RQ2)** 制导搜索系统化找到并高效定位灾难差分区（179 primary，效率 ~5×，archive 快速边界定位）；**(RQ3)** 高维带洞失效边界的逐轴刻画（含反直觉高风恢复，来自密扫）。**关键加固**：thesis 的承重质疑（学习型特有 vs 切换特有）已被 wave-2 实验答复——robust 差分失效**特定于切换瞬态**，由三个诚实 negative 划定边界；**两个 SUT（mc_nn + RAPTOR）对照在收口**，学习型特有性有 learned-vs-learned 支撑。**保留的解释缺口**：RAPTOR 鲁棒性可能部分源于源码级输入裁剪——本篇 threats 主动认领，unclipped 拆解留 future work。

---

## 3. Related Work（六根轴，定位 gap）

沿两轴：**(i) 是否建模/扰动控制器闭环动力学**；**(ii) 被测对象是经典控制软件、状态机，还是学习型控制器**。

- **(a) UAV 障碍/场景 fuzzing 与路径规划器测试**：DPFuzzer（ICSE'25）、SBFT CPS-UAV 簇、SwarmFuzz。聚焦几何/障碍、假设理想执行器、不测低层控制器。
- **(b) RV 控制/配置/策略 fuzzing**：RVFuzzer（USENIX'19）、LGDFuzzer（ICSE'22）、**PGFuzz（NDSS'21，MTL 安全策略 oracle，156 新 bug，真机复现）**、ADGFuzz、IMUFuzzer（ASE'25）、**RouthSearch（ISSTA'25，7 RQ、离线 vs 在线 oracle、搜索算法消融、基线跑 3 遍控方差、~7000 CPU 小时）**。被测是经典控制软件；无 learned-vs-classical 差分。**PGFuzz 的"性质即 oracle"是本项目性质 oracle 的直接模板（`property_oracle.py` P1–P7 policy 库）。RouthSearch 是本项目 RQ2 统计严谨度对标的领域标杆——RQ2 统计加固（10+ 种子 + Mann-Whitney U + A₁₂）正是为对齐此标杆而备（押后未跑）。** RouthSearch 也证明"scope 窄但做得极严"能中 ISSTA——本项目 scope 与之同量级、目标（学习型控制器）更新颖。
- **(c) 模式/状态/failsafe 语义 fuzzing**：SaFUZZ（ICSE'26）、HIFuzz。作用在状态机/模式层，不下沉控制器层。
- **(d) 赛博-物理不一致与神经控制器证伪**：CPI（CCS'20）；ARCH-COMP AINNCS、S-TaLiRo/Breach/ARIsTEO、NNV/Verisig/CORA。最直接前作，但基准是玩具系统、可达性在真实 6 自由度固件级不可扩展、无内建差分 oracle。**本项目的差分 oracle 正是绕过"须先写全正确性规约"的新解——经典即参照；wave-1/wave-2 的规约类 negative 反衬其价值（规约 oracle 既易假阳又对瞬态失效视而不见，差分 oracle 抓到了）。**
- **(e) 学习型 UAV 控制与基础策略**：RAPTOR（Science Robotics 2026）、NTNU PX4 神经模式（arXiv:2505.00432）、Zhang 极端自适应（T-RO 2025）、Neural-Lander。**构造**学习型控制器，不提供系统化方法找它们相对经典在哪儿失败。
- **(f) 自动驾驶 ML 测试（方法迁移源）**：成熟的 ground-truth-vs-actual 差分、metamorphic、对抗鲁棒、OOD 检测。迁移其精神到 UAV **闭环控制**。

**Gap**：尚无工作系统化搜索扰动/机动/故障场景空间，用**可靠的经典-学习型差分 oracle** 找出**集成进固件的学习型飞控**相对经典**特有的失效**、刻画其**高维边界与根因**、并用**诚实的阴性对照划定失效边界**、在**多个真实 shipped 控制器**上做 learned-vs-learned 对照。

---

## 4. 实验设计

### 4.1 被测对象（SUT）
同一 PX4（`3042f906`）、同一机架（**X500 v2**）、同一任务。两个学习型 backend：
- **`mc_nn_control`**（PX4 内置神经模式，TFLM，**前馈网**无递归，15-D 观测/4-D 动作，**无输入裁剪**）。**前馈无积分器**——在 wind+physics / 估计污染上未产生 robust 退化（可被位置反馈补偿），但在**切换瞬态**是灾难差分的失效方。**当前主 SUT，RQ1/RQ2/RQ3 + multi-policy + wave-2 均基于它。**
- **RAPTOR**（`mc_raptor`，免训基础策略，22-D 观测/4-D 动作，GRU-16，2084 参数，**推理前硬裁剪观测误差** `max_position_error=0.5` / `max_velocity_error=1.0`）。**v7：已从"低证据 null"提升为可比第二 SUT**——见 §5.11。原始（保留裁剪）RAPTOR 已接入 SUT selector + `raptor_sih` board + RAPTOR identity gate，完整对照 campaign 进行中。
- **两者切换路径字节级相同**：`mode_id 23` → 每轮须**正面控制器 ID 确认**（mc_nn 用 `neural_control` topic；RAPTOR 用 `raptor_status`/`raptor_input`/`policy.tar` staging——已自动化，见 §4.5/§5.11）。

### 4.2 差分 Oracle + 三个卫生机制（已自动化，两 SUT 可用）
**四象限**（同 θ 跑两遍，同机架/种子/注入序列/sim 时间对齐）：`boring_both_safe` / `interesting_not_bug` / **差分（经典 safe ∧ 学习型 unsafe，只报这类）** / `too_hard_not_bug`。

**三个卫生机制**：
1. **对齐切换状态**：SIH 无置态 API → **groundtruth 触发**，再以 ULOG 真值回匹配（rate 残差均值 ~0.09 rad/s）。
2. **分级失效严重度**：**S0 / S1 / S2 / S3 失控翻机（≥90° 或 ≥8 rad/s）/ S4 数值 fault**。关键切分 = 受控（S0-S2）vs 失控（S3-S4）。
3. **剔除基建污染**：**截断 control window 后重算控制级 severity，不剔整个 eval**；只有 unresolved failsafe / 起始高度太低才 gate-fail。**对两控制器对称。**

> **已自动化**：`validity_automation.py`，wave-1（400）、切换区 campaign、multi-policy（950 重分析）、wave-2（400）全程复用；**identity 现按 SUT 分派**（mc_nn `mcnn_identity_gate` / RAPTOR `raptor_identity_gate`）。

### 4.3 场景空间 θ（genome，v7：估计污染轴已 DONE）
θ 三档：**A 档**（状态估计污染、物理失配）；**B 档**（时序/接口、**切换瞬态**——差分主战场）；**C 档**（setpoint 幅度——GATE-3 判死）。

**genome**（`theta_genome.py`）：
- **A 档-wind+physics（`659c8da`）**：`steady_combo`，2D wind×physics descriptor。**wave-1 = 干净 negative。**
- **A 档-估计污染（v7 已 DONE，原 DEFERRED）**：`state_contam` 现为可路由子空间——`position_estimate_jump_m`→`M2B_P_PROF=2`（X 位置偏置）、`fake_velocity_bias_m_s`→`M2B_V_PROF=2`（X 速度偏置）、`fake_angular_rate_bias_rad_s`→`M2B_G_PROF=2`（Z 角速率偏置）；生成 theta 在污染非零时置 `M2B_EN=1`、记 `uses_state_shim=true`。descriptor `velocity_bias × angular_rate_bias`。**wave-2 = 干净 negative（见 §5.10）。patch drift 已解（shim 补全 position 通道，见 §5.10 / §9）。**
- **B 档-切换瞬态（可达性重定义）**：genome 覆盖姿态 16–50°、角速率 0.45–2.75、wind 0–6、delay 0–0.18；descriptor `switch_attitude × wind`，rate 保留为受可达约束搜索变量（`route_a_profile_for()` clamp 后重算 trigger rate）。
- **阶跃轴**：适度 setpoint 阶跃（为 P5）。
- **EXCLUDED**：C 档幅度攻击（GATE-3）、电机/传感器故障（SIH 未验证）。

### 4.4 搜索与反馈（已答 RQ2）
fitness = **差分 gap，不是绝对 ρ**：`gap_i = ρ_i(classical) − ρ_i(neural)`。灾难类 fitness gate：仅当去污染后经典 S0 且 P1/P2 非 vacuous、ρ 有效时 gap 才进 fitness，否则 floor（绝不奖励 both-crash）。搜索器 = MAP-Elites + 三臂（guided/random/grid，N=1 可续）。
- **v7：`guided_abs` / `absolute_severity` fitness 模式已加入**（`--fitness-mode`）——用于 RQ2 fitness 消融（证明**差分** gap 在搜索层也值钱，非仅 MAP-Elites 结构），**代码已备、押后未跑**。

### 4.5 finding 体系 / 指标 / 有效性
**两层 finding + severity-triggered primary**：candidate（`ρ_neural ≤ 0` 弱信号）；relative_degradation/strict（行为类，连续 ρ 门）；**`strict_s0_vs_s3`（灾难类 primary）= 去污染后经典 S0 ∧ 学习型 S3，跨种子复现，`≥2/3` 即稳健、`3/3` 更强档**。

**有效性纪律**：灾难类一律以离散 severity + violation 符号为门、连续 ρ 只诊断；行为类越抖动带 + 触发性质确认（候选因 X 入选 → 仅 X 跨种子复现才 X-confirmed）；invalid（trigger timeout / 去污染失败 / run error / identity 失败）一律排除。

**RQ/指标（v7 状态）**：RQ1 存在性（灾难类 ✓ 179 primary；非灾难/非切换 = 三个 negative）、**RQ2 搜索有效性（✓ 效率/定位框架 + archive 重分析定位；统计加固押后）**、**RQ3 失效刻画（✓ 高维带洞边界，密扫）**、**RQ4 迁移（v7 推进：mc_nn + RAPTOR 两 SUT 对照 campaign 进行中；真板/ArduPilot 延后作 threats）**、RQ5 缓解（discussion）。

---

## 5. 我们做了哪些实验（诚实旅程 + 教训）

### 5.1 RAPTOR 线（旧：7 轮 → "鲁棒"；v7 修正 + 重新集成）
M0–M2b-1 制导搜索全 0 confirmed。**v7 关键修正（据 `raptor_recon_2026-07-05`）**：RAPTOR 旧"0 confirmed / robust"**不是**"完整 harness 下无问题"，而是**低证据等级 null**——两因叠加：(B1) RAPTOR **推理前硬裁剪观测误差**（`observe()` 对 position/velocity error 调 `clip()`，源码常量，非配置），使幅度攻击徒劳；(B2) RAPTOR **从未接进当前 mc_nn campaign harness**（`m2_map_elites.py`/`campaign_runner.py` 曾硬接 mcnn），仅跑过 lightweight closeout（NaN/Inf 探针、Gazebo 不对称、少量 activation transient），**从未跑 route-A / switch / wind-physics / state-contam campaign**。**因此 RAPTOR 已在 v7 重新集成为可比 SUT，见 §5.11。**

### 5.2 mc_nn_control 线（GATE-1/2/3）
GATE-1 存在/零训/mode 23/正面 ID；GATE-2 无裁剪、15-D、前馈非 stateful；GATE-3 幅度 NO-GO，**反转：mc_nn 对幅度比经典更鲁棒**（RMS 经典 0.49 > mcnn 0.38）。

### 5.3 FUZZ 线（A 路线硬结果）
模式切换差分：FUZZ-1 极端角落命中翻机但 confound（过度声称）；FUZZ-1b groundtruth 对齐后经典也 failsafe 但未翻（二值检测器漏报）；FUZZ-1c severity 分级；**FUZZ-1c 去污染重判（`65240a5`）= A 路线硬结果：4 个干净 strict 差分（pair 1/2/4/5）classical=S0 ∧ mc_nn=S3**。

### 5.4 结构性失效区观察（v6 已由密扫解决，见 5.8/RQ3）
去污染后 mc_nn 失效在切换姿态上非单调；受控密扫已拆成干净的高维带洞边界。

### 5.5 旅程总教训（v7 追加）
1. 两个产线学习型控制器对大误差/幅度类都鲁棒；差分活在**切换瞬态**（灾难类）+ 失效结构。
2. 差分 oracle 真实有效，但可靠性依赖卫生机制 + 假阳纪律（**连续 ρ 在深违反区不是稳健复现量**）。
3. 二值检测器抹平真实质差。
4. wind+physics 行为类轴是干净 negative；戏剧性差分（若存在于非切换）更可能在估计污染轴。**（v7 更新：估计污染轴 wave-2 也 negative——见教训 7。）**
5. 制导搜索在切换区能系统化触发灾难差分并高效**定位**其边界；但因该区 bug 稠密，制导相对 random 的优势体现在效率/一致性/定位，而非独占发现（archive 重分析：完整带洞刻画仍来自密扫）。
6. **（方法论）每次投预算前，先有一道 preflight 把隐藏矛盾炸出来——纠错回路是可信度来源。** **（v7 验证：wave-2 的 Gate A 正确 halt 于锚点回归失败、诊断出是边界随机而非 shim bug、未烧 18h campaign。）**
7. **（v7 新）失效收敛，不弥散。** multi-policy 证明学习型特有差分收敛到灾难类（非渐进行为退化）；wave-2 证明它特定于切换瞬态（非稳态估计污染）。**"加厚度"的正确方式不是找更多失效类型/轴（问过了、答案是收敛），而是提升目标新颖性 + 刻画深度 + 诚实边界，以及补第二 SUT 与统计严谨度。**
8. **（v7 新，方法论）回归 gate 须区分确定性锚点与随机边界锚点。** 单样本卡边界锚点欠功率（Gate A 教训）；正确形态 = 确定性锚点（pair1/2）硬闸 + 边界锚点（pair4/5）概率跟踪。锚点可复现性本身在测绘分岔边界，反哺 RQ3。
9. **（v7 新）agent 产出的代码 ≠ 已验证。** RAPTOR shim 曾是半成品（缺 position 注入路径），只有真跑行为验证才暴露；"能编译 + patch 往返"不足以信任。

### 5.6 B 路线执行进度（性质 oracle + 搜索机器 + 基建）
- **Tier 0 — 性质 oracle（`2e7b6b7`）**：`property_oracle.py` 从 ULOG 算 P1–P7 ρ_i（P1 姿态包络 / P2 角速率（灾难类）、P3 饱和、P4 平滑、P5 settling、P6 不振荡、P7 无稳态偏差），含 PGFuzz 去噪、控制窗去污染、S0–S4、identity。`oracle_calibration.md` 16 阈值。
- **Tier 0.5 — 搜索机器**：genome、fitness（gap + per-property margin + `--target-properties` + **v7 加 `--fitness-mode` guided_abs**）、冒烟。
- **Tier 1 — campaign 基建**：并行 profiling；恢复尝试（speed 1.25，**并行未恢复，根因 = offboard wall-clock timer**）；有效性自动化；**v7 加 SUT selector（mcnn|raptor）+ RAPTOR runner/identity 接入（`3bc618c`）**。

### 5.7 wave-1 campaign（诚实 verdict = 干净 negative）
> 组合 wind+physics 稳态、N=1 @ 1.25、200 guided + 200 random。
- **strict 绝对违反 = 0**；戏剧性 P7 退化 = 共享 SIH 噪声尾巴（触发性质 2/12@≥2/3、0/12@3/3）；只有 P4/P6 小而稳架构签名（P4 100% flag gap ~0.19 3/3、P6 65% gap ~0.05 3/3）。**assay 正确拒掉 12-finding 假阳。** 科学含义：wind+physics 稳态无戏剧性行为类差分，指向估计污染轴。

### 5.8 切换区严重度 campaign（`118d58f`）
> 制导搜索掉头对准切换瞬态，fitness 改灾难类严重度目标，一炮补 RQ1 系统化 + RQ2 + RQ3。
- **preflight 纠错**：route-A 回归先失败 2/4（护栏正确触发、未烧长 campaign）；判据修正（灾难类以 severity+符号为门、连续 ρ 只诊断，因 jitter 带仅适用近无扰动轨迹）；多种子重判（pair1/pair4 3/3、pair5 8/9 保留）；state-trigger 窗口对齐修复；可达性 descriptor `attitude × wind`；Step-1 探针健康放行三臂。
- **RQ2**：guided **179** primary（54–65/种子）vs random **40**（12–16）vs grid **19**；~4.5× 密度、命中率 ~60% vs ~12%（~5×）、QD ~189 vs 119 vs 123；**3/3 确认档 guided 与 random 打平（各 6/10）**——效率/照亮/一致性框架，禁框成"更多 bug"。
- **RQ3**（密扫，40 点 120 eval 81 strict）：姿态非单调（~40° 起、42–45° 稳、48° 部分恢复）；rate 1.55 洞/1.75 恢复；风 0–3 暴露 / **4–6 恢复**（反直觉高亮，相位/共振）；delay 0.06/0.12s 时间洞。**高维带洞、非单调标量阈值。**
- **吞吐**：~22.1 eval/h（密扫 20.6）。caveats：非正式显著性、3+3 种子、SIH-only、shim-free。

### 5.9 multi-policy 差分谱系（v7 核心新结果，`db9adc7`）
> 目标：把差分 oracle 的判据从灾难类 {P1,P2} 扩到全 P1–P7（同一 oracle × 多条 policy，PGFuzz 形状），看切换区是否还有非灾难的独立行为差分。**纯重分析：复用 switch campaign 现有 ULOG，零新增 SITL。** `docs/multipolicy_differential_20260703.md`。
- **输入**：1041 记录，950 valid，91 invalid（missing compare / run_error）排除。
- **确认差分 positive = P1 / P2 / P6 / P7；P3 仅 3 个未确认单 eval；P4 / P5 = 0**（行为类门下）。
- **关键（收敛结论）**：P6/P7 虽同-policy 多种子确认，但**不是干净的独立行为失效**——它们**伴随灾难 S3**：P6 positive 中 96%（360/375）是 S0→S3、P7 中 ~74%（334/451）落 S3（余 S1→S1 53、S1→S3 61）；**纯非-S3 的确认组 = 0**（P6 非-S3 eval=5、P7=56，但均未升为独立确认）。物理直觉：一架正在翻滚的无人机，姿态剧烈晃（违反 P6 不振荡）、跟踪误差爆表（违反 P7 无稳态偏差）——同一灾难事件被三个指标各测一遍，非三个独立失效。
- **结论（可发表的科学论断）**：**学习型特有的差分失效收敛到灾难性瞬态类（P1/P2），而非渐进行为退化**。这比一堆杂乱谱系更适合方法稿，也**第三次演示假阳纪律**（正确拒绝把 epiphenomenon 当独立失效）。
- **P7 中等姿态线索（记录在案、未追）**：P7 在 `rp_2`（中等姿态桶）有一小撮纯非-S3（`S1→S1`）positive（56 eval），机理上契合"前馈无积分器的稳态跟踪偏差"，但 discovery-only、单 eval、未多种子确认，且 wave-1 已证稳态 P7 是噪声——**列为线索，不算数**。

### 5.10 wave-2 估计污染 campaign（v7 核心新结果，`2515aa6`）
> 目标：在**非切换轴（估计污染）**上跑完整 campaign，回答承重问题"失效是学习型特有还是切换特有"。`docs/wave2_statecontam_campaign_20260703.md`。全流程含一段 Gate A 波折——

**shim 修复（patch drift 已解）**：v6 遗留的 `m2b_state_shim.patch` drift 摸底发现 worktree 现有 shim 是**半成品**——velocity/angular-rate 注入路径存在，但 `position_estimate_jump_m` **缺 position 注入路径**。机械补全：加 `M2B_P_*` 参数（EKF2 因 `DEFINE_PARAMETERS` 宏满、改用 `param_find`/`param_get` 私有句柄读位置参数；selector 走正常路径）+ `vehicle_local_position.x/y/z` 注入 + `ApplyM2BPositionShim(...)`。重生成 patch，往返 apply + PX4 编译通过。**patch drift 就此解决。**

**Gate A 波折 + 诊断（`wave2_gateA_diagnostic_20260703`）**：shim 重建后锚点回归失败——pair1/pair2（深失效区）保持 strict，**pair4/pair5（边界区）翻转**。诊断区分 H1（边界随机性）vs H2（零污染 shim 常开 bug）：
- **决定性证据**：pair5 同种子 `20261803` 在 Gate A 是 S0、诊断复查又变 S3，**中间 shim 一字未改**——直接证明边界锚点**本质随机**、不能单样本卡。**H2 排除。**
- 多种子（重建 shim、零污染）：pair4 **7/8**、pair5 **8/8**（对齐历史 pair4 3/3、pair5 8/9）。
- 结构检查：shim 在零污染下对输出字段是 no-op；**但 hook 在 `M2B_EN` guard 前写 ring buffer**（非严格全时序 no-op）——清洁度 caveat，量级仅"微小共同时序扰动"、且共模（作差抵消），不解释边界翻转、本轮未硬化。
- **gate 方法学升级（沉淀）**：回归判据改为 **pair1/pair2 硬闸 strict + pair4/pair5 概率跟踪 ≥6/8**（75% 地板，历史率 85–90% 留足随机涨落）。

**Gate A' / B / C 通过**：Gate A'（新判据）pair1 1/1、pair2 1/1、pair4 7/8、pair5 8/8 → pass；Gate B（genome 打通，见 §4.3）theta 可生成 + 定向 test；Gate C 探针 24 eval、23 valid、delivery/fairness/identity/decontam **23/23**、**shim 对称注入实测通过**、0 strict → 放行主 campaign。

**主 campaign（干净 negative）**：guided 200 + random 200（199 valid），descriptor `velocity_bias × angular_rate_bias`，串行 N=1。**0 strict S0/S3 差分、0 primary bug**；validity 满格（delivery/fairness/identity/decontam 200/200）；archive 24/25 bins；best diagnostic P2 gap ~2.4。相对退化性质计数：guided P1=24/P2=200/P4=200/P6=114/P7=3。**P2/P4 相对退化可复现但只作诊断（架构签名，非承重差分）；P7 假设 targeted confirmation 仅 1/12 → 未确认。**
- **结论**：**干净 negative——robust 差分失效特定于切换瞬态，不铺到稳态估计污染。** 这是可发表的 negative：**关闭"只测了切换所以不算"的承重质疑**（测了非切换轴、诚实报 negative），第三/四次演示假阳纪律。

### 5.11 RAPTOR 重新集成为可比第二 SUT（v7，`3bc618c`）
> 目标：解决"单 SUT"外部效度短板——把原始（保留裁剪）RAPTOR 提升为与 mc_nn 完整可比的 SUT（路线 1，不做 unclipped）。`docs/raptor_reintegration_smoke_2026-07-05`。
- **勘察结论**（见 §5.1）：裁剪 = A+B 组合，主成本 B（重新集成，非单纯补测）。
- **集成**：加 SUT selector（`mcnn|raptor`，默认 mcnn 不变，回归不破）；**board 决策 = `raptor_sih` + 补 DDS groundtruth installer**（隔离 `MC_RAPTOR`、避免与 `MC_NN_CONTROL` 共存 board）；**RAPTOR 专属 `raptor_identity_gate()`**（controller==raptor、`raptor_status` active、`raptor_input` 有样本、nav 23、**无 `neural_control`**、`policy.tar` staged）；差分/severity/去污染其余复用（`property_oracle.py --controller raptor`、`m1_compare.py --neural-controller raptor` 已支持）。
- **identity 真实生效**：8 个真实 smoke ULOG **8/8 通过**（`raptor_status` 9864–10247 样本、`raptor_input` 10930–11333、nav-23 fraction 0.897–0.900）。
- **smoke 结果**：4 route-A 锚点 × 2 种子 = 8 eval。**RAPTOR 多守住：7 S0、1 S1、0 S3**（在 mc_nn 翻机的锚点上）。可比性五判据全过（identity 真生效、去污染对 RAPTOR 8/8、差分 shell 产 P1–P7、classical 侧与既有 mc_nn 记录一致、validity 健康）。**裁剪保留。**
- **环境 caveat**：本地 ROS overlay 有 Py3.12 残留、运行时 3.10/Humble → 需重建 overlay 让 `RaptorStatus`/`RaptorInput` 加载（复现要点）。
- **结论**：**原始 clipped RAPTOR 现为 smoke 级 mc_nn-可比 SUT，可进完整 campaign。**
- **完整对照 campaign（进行中）**：与 mc_nn switch campaign **严格对齐规模**（同 descriptor `switch_attitude × wind`、同三臂 guided/random/grid、同预算/种子、同 oracle/判据、**classical 基线复用**、保留裁剪）。设计成 Gate 0 稳定性闸（防长跑中途因 RAPTOR activation 脆性崩）→ 三臂 → 确认 + dense sweep → 对照报告。**基于 smoke 信号，预期结果 = "mc_nn 切换瞬态翻、RAPTOR 守住" 的 learned-vs-learned 对照**（证明方法有区分力），**带 threats 主动认领"RAPTOR 鲁棒性可能部分源于输入裁剪"**。**据实、不预设。**

### 5.12 RQ2 archive 重分析（v7，`rq2_archive_reanalysis_20260705`）
> 目标：回答"guided fuzzer 到底交付了什么"（RQ3 边界来自密扫、而 RQ2 fuzzer 3/3 打平 random）。**纯重分析，零仿真。**
- **guided archive 部分照出 RQ3 边界**：三 guided run 均在 eval 44/61/88 覆盖 10/10 高危 `rp_3/rp_4 × wind` cell（早于密扫 120）、强复现 42–45° 稳定带。
- **未独立照出完整带洞结构**：rate 洞/恢复、风 4–6 恢复、delay 洞皆 `not_shown`（archive rate 范围仅 0.983–1.203）；特征完整度 **2/5（40%）**。
- **定位（论文措辞已锁）**：**fuzzer archive = 快速边界定位证据；完整因果刻画来自受控密扫。不写"fuzzer 独立交付了 RQ3 边界"。** RQ2/RQ3 挂钩：archive 定位 + 密扫因果。

---

## 6. 从单 oracle 到多 oracle（B 路线，v7 诚实定形）

**概念澄清（见 §1）**：multi-policy ≠ multi-oracle。差分 oracle 是一个机制，内挂 P1–P7 policy 库（PGFuzz 形状）。

**oracle 现状（v7）**：
- **差分 oracle（已验证 + 多决定性结果 + 三卫生 + 自动化 + 假阳纪律三次演示）** ✓：A 路线手工灾难差分 + 切换区 campaign 制导系统化（RQ1/RQ2/RQ3）+ **multi-policy 谱系（收敛到灾难类）**。
- **性质/规约 oracle（PGFuzz 式 MTL）— 已建成、两条非切换轴均 = 干净 negative** ✓（可报）：**wind+physics 稳态（wave-1）+ 估计污染（wave-2）均无 robust 行为类差分**。这两个 negative 反衬差分 oracle 的价值：规约类既易假阳（wave-1 拒 12-finding）、又对瞬态失效视而不见（失效活在切换瞬态灾难类，差分 oracle 抓到了）。
- **变形/不变性 oracle — 上行选项（便宜，复用 harness，未做）**：场景旋转/镜像 → 响应应相应变换；经典对称由构造、神经破对称 = NN-specific bug。**注意：切换区 / multi-policy / wave-2 用的都是差分/严重度 oracle，_不是_变形 oracle。** 变形 oracle 是唯一能补差分 oracle completeness 盲区（"两者都失败"或"无法对照的失效"）的候选——若在已知非单调区落一个不同类型的干净 positive，可升为并列 headline；否则并入诚实叙事。
- **鲁棒性/平滑性、更强参照差分（MPC/可达性）**：stretch。

**§6 方向性（v7 更新）**：**两条稳态/非切换轴（wind+physics、估计污染）均证 negative；切换瞬态灾难差分已由差分 oracle 决定性拿到并系统化 + 收敛证明。** 失效边界现由**三个诚实 negative**（wind+physics、估计污染、multi-policy 行为类独立性）划定。变形 oracle 是拓宽失效_类型_ / 补 completeness 盲区的唯一剩余便宜上行（未做，非完整性必需）。

---

## 7. Oracle 排序（按可行性 + 可信性，v7 状态）

1. **灾难性差分（现有）** — 高/高。**A 路线 + 切换区 campaign + multi-policy 三重验证；已答 RQ1/RQ2/RQ3 + 收敛证明。两 SUT 对照 campaign 进行中。**
2. **性质/规约（PGFuzz 式 MTL）** — 中高/高。**已实现 + 两条非切换轴（wind+physics、估计污染）均干净 negative + 反衬差分 oracle 价值。**
3. **变形/对称（equivariance）** — 高/高。复用 harness、靶区（非单调区）已知、能补 completeness 盲区。**唯一剩余便宜上行。未做。**
4. **鲁棒性/平滑（离线对抗敏感度）** — 高/中高。stretch。
5. **更强参照差分（MPC/可达性认证）** — 最高/最低。stretch；A 路线有轻量版。

---

## 8. 当前决策 + 下一步（战略状态：三质疑已关，写作待启）

**已完成的收口/上行（v7）**：
- **A 路线**：已锁 + 多种子确认（3/3、3/3、3/3、8/9）。
- **切换区 campaign（`118d58f`）**：RQ1 系统化 + RQ2（效率框架）+ RQ3（高维带洞边界）。
- **multi-policy（`db9adc7`）**：失效收敛到灾难类 → **关闭"只有一种 unsafe"**。
- **wave-2（`2515aa6`）**：估计污染干净 negative → **关闭"只测了切换"承重质疑**；patch drift 已解；gate 方法学升级。
- **RQ2 archive 重分析**：fuzzer = 快速边界定位、密扫 = 因果刻画。
- **RAPTOR 集成（`3bc618c`）**：原始 RAPTOR 提升为可比 SUT；**完整对照 campaign 进行中 → 收口"单 SUT"**。

**论文脊柱：不仅完整、且已显著加固**——可靠差分 oracle（方法 + 三次假阳演示 + gate 升级）+ 系统化灾难差分（RQ1）+ 制导效率与 archive 定位（RQ2）+ 高维带洞边界（RQ3）+ **承重质疑经 wave-2 实验答复（失效钉死切换瞬态）** + **三个诚实 negative 划定边界** + **两 SUT learned-vs-learned 对照收口中**。

**下一步（由用户定；写作已是最大未做块）**：
- **(路径 1，推荐) 收范围 + 写作**：论文正文仍停在 M0/M1 旧稿（RAPTOR-only）——**这是当前最大的未做块**。RAPTOR 对照 campaign 一旦跑完，两 SUT 对照结论即到位，可开始写。
- **(路径 2，已备好但押后) RQ2 统计加固 + fitness 消融**：10+ 种子四臂（guided_diff/random/grid/guided_abs）+ Mann-Whitney U + Vargha-Delaney A₁₂，对齐 RouthSearch 标杆；**代码已备（`--fitness-mode`）、用户选择先解 SUT 后再做**。约 5–10 天串行大件。
- **(路径 3，future work) unclipped RAPTOR 对照**：去掉 RAPTOR 输入裁剪、同空间对照，回答"裁剪是否鲁棒主因"——**本篇不做，threats 主动认领解释缺口，留下一篇/一章**。
- **三处审稿攻击面（写作时主动处理）**：**RQ2 的 3/3 打平**（效率/定位/一致性框架 + 统计加固若做）；**RAPTOR 鲁棒性可能部分源于输入裁剪**（threats 认领 + future work unclipped）；**SIH-only、无真机、无 ArduPilot**（RQ4 部分由两 SUT 答，其余 threats）。
- **已定口径**：灾难类 primary = `strict_s0_vs_s3 ≥2/3`（3/3 另报）、以 severity+符号为门；行为类越抖动 + 触发性质确认；invalid 排除；**回归 gate = pair1/2 硬闸 + pair4/5 概率 ≥6/8**。
- **机器约束**：N=1 单机一次一个 SITL 工作流；≈ 22 eval/h @ speed 1.25。
- **悬而未决**：工具名（`[TOOL]`）；目标会议已定 SE 大类（ICSE/FSE/ASE/ISSTA）、倾向 ISSTA（testing 契合、RouthSearch 先例）但窗口未定；**工作区有用户侧未提交改动**（RQ2 `fitness_mode`/`guided_abs`/`absolute_severity` + archive 重分析 untracked）——**待择时 commit 落盘或 stash 清理**；RAPTOR 完整 campaign 结果待回；unclipped 是否本篇（默认否）。

---

## 9. 环境 / 复现 / 工程约定（给 agent）

- **容器入口**：`sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<name> ./docker/run.sh bash -lc "..."'`。镜像 `uav_sf:phase1`。用 `sg docker`、避免 sudo。坑见 `AGENT.md`。
- **PX4**：固定 `3042f906`，源码 `external/PX4-Autopilot`（gitignored）。**两 board**：`px4_sitl_mcnn_sih`（mc_nn，同编 mc_raptor 但不启动 + DDS groundtruth）；**`px4_sitl_raptor_sih`（RAPTOR，v7 补齐 DDS groundtruth installer）**。mode-23 飞行须正面 ID 确认（按 SUT 分派 identity gate）。
- **仓库约定**：`external/PX4-Autopilot`、`ros2_ws` gitignore → PX4 改动以 tracked patch/overlay + installer 入库；证据落 `docs/`。
- **公开仓同步（v7 已闭合）**：**公开 GitHub main 现已同步至 `3bc618c`（RAPTOR 集成）**——A/B 路线、切换区 campaign、multi-policy、wave-2、RAPTOR 集成均已在公开 main。v6 遗留的"公开仓停在 RAPTOR 线"gap 已解。
- **git 卫生**：`*.ulg`/`runs/`/`docs/**/evals/`/checkpoint gitignore、留本地；commit 只含代码+报告。验证：`py_compile`/`compileall`/`unittest`/`bash -n`/`jq empty`/`git diff --check`(+`--cached`)/`git ls-files` 无 ulog/大文件。**`config/m2_primary_bugs/` 已入库（`03f5155`，20 个 switch severity primary-bug θ 配置，作可复现 artifact）。** **注意：工作区尚有用户侧未提交改动（RQ2 fitness_mode/guided_abs + archive 重分析 untracked），agent commit 时须 `git status` 盘点、只提交本任务改动、不误纳。**
- **吞吐 / 并行（硬约束）**：**N=1 @ `PX4_SIM_SPEED_FACTOR=1.25` ≈ 22–23 eval/h**。**并行不可用**：根因 = offboard setpoint 是 wall-clock ROS timer、未锁 lockstep（`m1_offboard_task.py` `create_timer`）。**Step C（恢复路径，押后）**：setpoint 锁 sim 时间 → 恢复并行/高 speed，改后须 route-A + 锚点回归。**wave-1/切换区/multi-policy/wave-2/RAPTOR 均串行 N=1 跑完，Step C 非必需。**
- **SIH 固有抖动 + 判据**：固定 `(θ,seed)` 串行重跑 ρ 也抖（P7 band 0.224、P5 ~0.28、P1/P4/P6 ~0.01；标定 `P1=0.0128 / P2=0.0935`，**仅适用近无扰动轨迹**）。**灾难类复现/确认一律以离散 severity + violation 符号为门、连续 ρ 只诊断**；行为类越抖动 margin + 触发性质确认。**边界锚点用概率判据（pair4/5 ≥6/8），确定性锚点（pair1/2）单样本硬闸。**
- **patch drift（v7 已解）**：`patches/px4/m2b_state_shim.patch` 曾 drift（EKF2 + vehicle_angular_velocity 6 文件）；**wave-2 中已重生成**（补全 `position_estimate_jump_m` 的 `M2B_P_*` 位置注入路径，往返 apply + 编译 + 锚点回归通过）。**shim 清洁度 caveat**：hook 在 `M2B_EN` guard 前写 ring buffer（非严格全时序 no-op，共模、量级微小、诊断已证不影响边界，未硬化）。
- **仿真器**：SIH 为主（非 bit-exact → 多种子 + 严重度纪律）；Gazebo 仅可视化。
- **RAPTOR 集成注意（v7 新）**：SUT selector（mcnn|raptor，默认 mcnn）；`raptor_sih` board + DDS groundtruth；`raptor_identity_gate()`（raptor_status/raptor_input/nav23/无 neural_control/policy.tar staged）；RAPTOR runner 需 `policy.tar` staging；**ROS overlay 须匹配运行时（3.10/Humble，防 Py3.12 残留致 `RaptorStatus`/`RaptorInput` 加载失败）**；RAPTOR 输入裁剪（`max_position_error=0.5`/`max_velocity_error=1.0`）**保留 = 原始 RAPTOR 语义，去掉即另一 SUT**。
- **关键脚本**：
  - 任务/比较：`m1_offboard_task.py`（wall-clock 计时，支持 `--controller raptor|mcnn`）、`m1_metrics.py`+`m1_compare.py`（四象限 + 差分 + 两层 finding，`--neural-controller raptor|mcnn`）。
  - **B 路线 / campaign**：`property_oracle.py`（P1–P7 + S0–S4 + identity + state-trigger 对齐，`--controller` 支持 raptor/mcnn/classical）、`theta_genome.py`（genome + `steady_combo` + `route-a-switching` 可达性 + **`state_contam` 已 enable+路由到 `M2B_*`**）、`property_fitness.py`（gap fitness + `--target-properties` + **`--fitness-mode` guided_abs**）、`validity_automation.py`（去污染 + **按 SUT 分派 identity：mcnn_identity_gate / raptor_identity_gate** + 抖动 margin）、`m2_map_elites.py`（**SUT selector**、搜索驱动）、`campaign_runner.py`（N=1 可续 + 三臂 + severity-triggered primary + **SUT 分派**）、`route_a_anchor_regression.py`（**多种子 severity+符号闸 + pair1/2 硬闸 + pair4/5 概率跟踪**）、`multipolicy_differential.py`（**v7 新，P1–P7 差分谱系重分析**）。
  - RAPTOR：`build_px4_raptor_sih.sh`（+DDS groundtruth）、`m1_diff_runner.py`（`mc_raptor start` + policy.tar staging）。
- **关键报告/标定**：`oracle_calibration.md`、`wave1_windphysics_20260627.md`、`switch_severity_campaign_20260629.md`、**`multipolicy_differential_20260703.md`、`wave2_statecontam_campaign_20260703.md`、`wave2_gateA_diagnostic_20260703.md`、`raptor_recon_2026-07-05.md`、`raptor_reintegration_smoke_2026-07-05.md`、`rq2_archive_reanalysis_20260705.md`**。
- **最近 commit**（新→旧）：**`3bc618c`（RAPTOR SUT 集成 smoke：SUT selector + raptor_sih + DDS groundtruth + raptor_identity_gate + 8/8 真实 ULOG 验证）**｜**`2515aa6`（wave-2 估计污染 campaign：shim 补 position 通道 + genome state_contam 路由 + Gate A 重定义 + 干净 negative）**｜**`62e1d01`（wave-2 preflight）**｜**`03f5155`（campaign artifact docs + m2_primary_bugs 入库）**｜**`db9adc7`（multi-policy 差分谱系）**｜`118d58f`（切换区严重度 campaign）｜`659c8da`、`343828e`、`8217025`、`776c947`、`3d999af`、`ab50cce`、`4afb191`、`ab86b5b`、`2e7b6b7`｜A 路线：`65240a5`、`301f564`、`345d2c6`、`4685b96`、`a8dd59b`、`b0121ee`。

---

## 10. References（待补 venue/DOI）

- Wang et al. **DPFuzzer.** ICSE 2025. ｜ Chambers et al. **SaFUZZ.** ICSE 2026. ｜ Kim et al. **PGFuzz.** NDSS 2021.
- **RVFuzzer.** USENIX Sec 2019. ｜ **LGDFuzzer.** ICSE 2022. ｜ **IMUFuzzer.** ASE 2025. ｜ **ADGFuzz.** ｜ **RouthSearch.** ISSTA 2025.
- Choi et al. **CPI.** CCS 2020. ｜ ARCH-COMP AINNCS；S-TaLiRo / Breach / ARIsTEO；NNV / Verisig / CORA.
- Eschmann, Albani, Loianno. **RAPTOR: A Foundation Policy for Quadrotor Control.** Science Robotics 2026 / arXiv:2509.11481.
- Hegre et al. **A Neural Network Mode for PX4 on Embedded Flight Controllers.** arXiv:2505.00432, 2025.
- Zhang et al. **A Learning-Based Quadcopter Controller With Extreme Adaptation.** IEEE T-RO 2025.
- SBFT CPS-UAV Testing Competition（CAMBA / TUMB / WOGAN-UAV / DeepHyperion-UAV / AmbieGen / TAIiST）；SwarmFuzz.
- PX4 v1.17/v1.18 Release Notes；PX4 Neural Network Control / RAPTOR / SIH / System Failure Injection 文档。
