# 项目叙事与上下文文档 v5 — 学习型 UAV 飞控的场景模糊测试

**用途**：切换对话时的完整上下文 + 给执行 agent 的叙事参考。读完即可接续，无需回溯历史对话。
**取代**：v4（v4 在 wave-1 verdict 上**写错了**，写成"~6 confirmed P7、neural 稳定差 ~1m"——那段作废）。**本版修正：wave-1 的戏剧性 P7 行为类 finding _没站住_，是干净 negative；only 小而稳的 P4/P6 架构签名复现。assay 正确拒掉了一个假阳。后续战略岔路（wave-2 估计污染 / 变形 oracle / 重掂行为类 finding 必要性）留作开放问题，下一对话讨论。**
**Date**: 2026-06-28
**Repo**: `github.com/JacksonW1025/uav_sf`，工作区 `/mnt/nvme/uav_sf`（容器内）。PX4 固定 `main@3042f906abaab7ab59ae838ad5a530a9ef3df9a6`（v1.18 alpha）。
**配套设计文档**：`oracle_map_and_property_set_v0.1.md`、`fullscale_fuzzing_preflight_checklist_v0_1.md`、`docs/wave1_windphysics_20260627.md`（wave-1 结果，已按诚实口径重生成）。

---

## 0. 速览（TL;DR）

**Idea**：学习型低层飞控（PX4 Neural Control、Science Robotics 的 RAPTOR 基础策略）正进入生产自驾仪却没有系统化安全测试。我们在**同一固件、同一机架、同一任务**下，用搜索（fuzzing）在扰动/机动/故障/指令的场景空间里找学习型控制器的失效，用**经典控制器当内建差分 oracle**（经典 safe ∧ 学习型 unsafe）作为闭环控制的失效归因，并把它扩成**多 oracle 套件**。

**当前状态（A 路线已锁；B 路线第一轮 = 干净 negative）**：
- **A 路线（硬结果，已锁）**：mode-23 中途交接剧烈状态下，**4 个干净 strict 差分**——经典 **S0 干净恢复** ∧ `mc_nn_control` **S3 失控翻机**（>90°、>8 rad/s），对齐紧、基建污染已剔除、对称公平。外加 `mc_nn` 失效区**在切换姿态上非单调**（经典全区 S0）。
- **B 路线（性质 oracle + 搜索机器 + Tier 1 基建建成；wave-1 campaign = 干净 negative）**：
  - 全套建成验证：`property_oracle.py`（P1-P7）、差分 gap fitness、自动化有效性卫生、可续跑 campaign runner、组合 wind+physics genome。
  - **wave-1 campaign（200 guided + 200 random，组合 wind+physics 稳态）诚实 verdict**：
    - **strict 绝对违反 = 0（robust）**。neural 在两个单抽里勉强越名义违反线（ρ7 −0.12），但**无一过抖动 margin（−0.448）**。
    - **戏剧性 P7 退化 = 噪声尾巴，_不是 finding_**：单抽里有大 P7 gap（max 1.04），但**触发性质重判只有 2/12 在 ≥2/3 复现、0/12 在 3/3**；legacy"12 confirmed"是靠普遍的 P4/P6 兜的、**不是 P7**。且**方差判定：neural 的 P7 方差_不_显著大于经典**（mean 0.0247 vs 0.0241，pooled ratio 1.40，per-candidate 中位比 0.72）→ **也不是**神经特有的不一致。那些 ~1m 大偏移是**共享 SIH 噪声的稀疏尾巴**。
    - **只有 P4/P6 上有小而稳的相对退化**：P4 100% flag、gap ~0.19、3/3 复现；P6 65%、gap ~0.05、3/3。即"**neural 一致地比经典略糙、略多振荡**"——真实、可复现，但**小、偏'架构签名'而非'安全失效'**。
    - **assay 在工作**：它用多种子 + 触发性质纪律，**拒掉了一个本会变成"12 个 finding"的假阳**（同 M2.6 高 TWR 教训）。
  - **含义**：在**最便宜**的 A 档轴（wind+physics 稳态），性质 oracle **没找到戏剧性行为类差分**——这是干净 negative，且**强化 §6**（物理扰动可补偿 → 空；状态信念污染补不了 → 该去 wave-2 找）。

**下一步 = 开放战略岔路（留作新对话讨论，本版不锁）**：(A) 按 §6 上 wave-2 估计污染（最对、最贵、可能也 negative）；(B) 先上更便宜、复用 harness 的变形 oracle 打 B 档已知非单调区（hedge）；(C) 重掂"是否_必须_一个戏剧性行为类 finding"（A 路线灾难差分 + 可靠 oracle 方法学 + 这个诚实 negative 或许已够一篇）。详见 §8。

---

## 1. 核心 Idea / Thesis

测学习型控制器的根本难点是 **oracle 问题**：要判它"飞错了"，须先知道"正确飞行长什么样"，而任意扰动下的绝对正确性极难规约。

**关键想法**：PX4 让经典与学习型控制器在**同一固件**共存、可切换。同机架/同任务/同扰动下，若**调好的经典守住、学习型失败**，则该失败**学习型特有**——归因靠结构、不靠手搓正确性规约。在此之上用 fuzzing 搜这些失败。**A 路线证明这个 oracle 真实有效**（拿到干净严差分），**但前提是三个卫生机制**。

**扩展（B 路线）**：经典差分只是"判定正确飞行"的一种方式。学习型控制器的"bug"不一定是坠毁、不一定需经典对照（可以是违反控制性质、破坏对称性、对微扰异常敏感）。我们因此把经典差分扩成**多 oracle**。**B 路线第一发 = 性质 oracle（PGFuzz 式 MTL）**：定义"正确飞行是什么"（有界、平滑、settling、不振荡、无稳态偏差），搜违反。**wave-1 在最便宜的 wind+physics 轴上拿到的是干净 negative（戏剧性行为类差分不存在于此轴）**——这本身是个可报结果，且指向估计污染轴（wave-2）。

---

## 2. 理想化 Contribution

### 2.1 原始 contribution（方法稿 C1-C5，已据实修订）
- **C1**：学习型 UAV 飞控的差分场景模糊测试**问题表述**。
- **C2（验证有效，内涵升级 + 两层 + 假阳纪律）**：**可靠的内建跨控制器差分 oracle**——配齐对齐切换状态 + 分级严重度 + 基建去污染 + **多种子越抖动 + 触发性质确认**才可信。已自动化（`validity_automation.py`）。**两层 finding 体系**：strict（神经违反 ∧ 经典满足）+ relative-degradation（神经显著差、都受控）。**wave-1 演示了这套 assay 拒假阳的能力**（P7 大 gap 尾巴被正确判为非 finding）。
- **C3（已建成 + 跑过一轮 campaign）**：面向学习型控制的**搜索反馈/制导**——差分 gap fitness + MAP-Elites + baseline 消融。**wave-1 诚实 C3**：目标普遍时制导仅小幅胜 random（QD/覆盖）；决定性优势在稀有目标（wave-2）才显。
- **C4**：**免训、可复现的测试平台/基准**，实例化在两个真实 shipped 控制器上。
- **C5**：学习型控制器**失效分类**与缓解。

### 2.2 经验头条结果
- **A 路线（硬结果）**：剧烈中途交接，经典 S0、mc_nn S3 翻机，4 个可复现 strict 差分，基建归因清晰、对称公平；mc_nn 失效区非单调；反直觉——mc_nn 对幅度比经典**更**鲁棒（GATE-3）。
- **B 路线（wave-1 = 诚实 negative）**：性质 oracle 复现 A 路线灾难差分（验证管线）；**wind+physics 稳态上：strict 绝对违反 = 0（robust）；戏剧性 P7 退化 = 噪声尾巴（触发性质 2/12@≥2/3、0/12@3/3，方差非神经特有 ratio 1.40），_不是 finding_；only 小而稳的 P4/P6 架构签名（gap ~0.19 / ~0.05，3/3 复现）**。**assay 正确拒掉了一个 12-finding 量级的假阳。** 戏剧性行为类宽差分在此便宜轴上是干净 negative。

### 2.3 演进后的论文主张（建议，已据 wave-1 修正）
**头条 = "面向集成进固件的学习型飞控的多-oracle 场景测试方法"**：可靠差分 oracle（三个卫生机制 + 两层 finding + 假阳纪律）+ 性质/规约 + 变形/对称 + 鲁棒性 oracle。**价值不押在单个 bug 上**——A 路线已拿到硬的**灾难差分锚点**；wave-1 给出**方法学价值**（assay 在最便宜轴上诚实拒假阳 + 干净 negative 精确指向估计污染轴）+ 小 P4/P6 签名。**戏剧性行为类 finding 仍_未_拿到**——是否值得为它砸 wave-2 大基建（或退而求变形 oracle、或重掂必要性）= 当前开放战略问题（§8）。**诚实负结果本身是可报的方法学贡献**（证明该方法能区分"真差分"与"噪声/架构签名"）。

---

## 3. Related Work（六根轴，定位 gap）

沿两轴：**(i) 是否建模/扰动控制器闭环动力学**；**(ii) 被测对象是经典控制软件、状态机，还是学习型控制器**。

- **(a) UAV 障碍/场景 fuzzing 与路径规划器测试**：DPFuzzer（ICSE'25）、SBFT CPS-UAV 簇、SwarmFuzz。聚焦几何/障碍、假设理想执行器、不测低层控制器、无学习型脆弱性概念。
- **(b) RV 控制/配置/策略 fuzzing**：RVFuzzer（USENIX'19）、LGDFuzzer（ICSE'22）、**PGFuzz（NDSS'21，MTL 安全策略 oracle + policy distance 引导，156 新 bug）**、ADGFuzz、IMUFuzzer（ASE'25）。被测是经典控制软件；无 learned-vs-classical 差分。**PGFuzz 的"性质即 oracle"是本项目性质 oracle 的直接模板——已实现（`property_oracle.py`）。**
- **(c) 模式/状态/failsafe 语义 fuzzing**：SaFUZZ（ICSE'26）、HIFuzz。作用在状态机/模式层，不下沉控制器层。
- **(d) 赛博-物理不一致与神经控制器证伪**：CPI（CCS'20）；ARCH-COMP AINNCS、S-TaLiRo/Breach/ARIsTEO、NNV/Verisig/CORA。最直接前作，但基准是玩具系统、可达性在真实 6 自由度固件级不可扩展、无内建差分 oracle。
- **(e) 学习型 UAV 控制与基础策略**：RAPTOR（Science Robotics 2026）、NTNU PX4 神经模式（arXiv:2505.00432）、Zhang 极端自适应（T-RO 2025）、Neural-Lander。**构造**学习型控制器，不提供系统化方法找它们相对经典在哪儿失败。
- **(f) 自动驾驶 ML 测试（方法迁移源）**：成熟的 ground-truth-vs-actual 差分、metamorphic、对抗鲁棒、OOD 检测。我们迁移其**差分/蜕变/鲁棒**精神到 UAV **闭环控制**。

**Gap**：尚无工作系统化搜索扰动/机动/故障场景空间，用**多 oracle（含_可靠_的经典-学习型差分）**找出**集成进固件的学习型飞控**相对经典**特有的失效**并刻画其边界与根因。

---

## 4. 实验设计

### 4.1 被测对象（SUT）
同一 PX4（`3042f906`）、同一机架（**X500 v2**）、同一任务。两个学习型 backend：
- **RAPTOR**（`mc_raptor`，免训基础策略，22-D 观测/4-D 动作，GRU-16，2084 参数）。
- **`mc_nn_control`**（PX4 内置神经模式，TFLM，**前馈网**无递归，15-D 观测/4-D 动作）。**前馈无积分器**——曾设想是 P7 稳态退化的根因，但 wave-1 显示在 wind+physics 上没产生 robust P7 退化（物理扰动可被位置反馈补偿）。
- **两者切换路径字节级相同**：`mode_id 23` → 每轮 mode-23 飞行须**正面控制器 ID 确认**（已自动化进 eval 管线，见 §4.5）。

### 4.2 差分 Oracle + 三个卫生机制（A 路线验证，已自动化）
**四象限**（同 θ 跑两遍，同机架/种子/注入序列/sim 时间对齐）：`boring_both_safe` / `interesting_not_bug` / **差分（经典 safe ∧ 学习型 unsafe，只报这类）** / `too_hard_not_bug`。

**让差分可信的三个卫生机制**：
1. **对齐切换状态**：SIH 无快照/置态 API → **Method A，groundtruth 触发**，再以 ULOG 真值回匹配（rate 残差均值 ~0.09 rad/s）。
2. **分级失效严重度**：**S0 / S1 / S2 / S3 失控翻机（≥90° 或 ≥8 rad/s）/ S4 数值 fault**。关键切分 = 受控（S0-S2）vs 失控（S3-S4）。
3. **剔除基建污染**：offboard 丢失/datalink/RC/估计器 position-jump failsafe、failsafe 触地、低于最小可恢复高度切换，对两控制器对称剔除。

> **已自动化**：封进 `validity_automation.py`、自动施用于每个 eval（wave-1 在 400 eval 上稳定，identity 199/198 confirmed）。

### 4.3 场景空间 θ（已写死成可搜 genome）
**核心实证**：RAPTOR 推理前裁剪观测误差 → setpoint 幅度攻击徒劳；`mc_nn` **无任何裁剪**（GATE-2），但对幅度**比经典更鲁棒**（GATE-3）。θ 三档：**A 档**（状态估计污染、物理失配）；**B 档**（时序/接口、**切换瞬态**——A 路线严差分出处 + 非单调区）；**C 档**（setpoint 幅度——GATE-3 判死）。

**genome**（`theta_genome.py`）：
- **A 档可跑子集（已组合，`659c8da`）**：持续风 **与** 物理失配（质量/惯量/TWR）**同 theta 生效**（`steady_combo`），2D wind×physics descriptor。**wave-1 已跑这条 = 干净 negative。**
- **B 档**：切换姿态/角速率/时延（groundtruth 触发，单一类型）——**变形 oracle 的目标区（选项 B）**。
- **阶跃轴**：适度 setpoint 阶跃（为 P5），与 C 档极端幅度划清。switching/step 仍单一类型场景。
- **DEFERRED**：状态估计污染（走 shim，受 patch drift 阻塞，见 §9）——**§6 最高产那块，留 wave-2（选项 A）**。
- **EXCLUDED**：C 档幅度攻击（GATE-3）、电机/传感器故障（SIH 未验证）。

### 4.4 搜索与反馈（已 wire + 跑过一轮 campaign）
fitness = **差分 gap，不是绝对 ρ**：`gap_i = ρ_i(classical) − ρ_i(neural)`，**仅当经典安全且非空真值**时有效；场景 fitness = 行为类目标 `max_i gap_i`。目标 = P4/P6/P7，阶跃加 P5；P1/P2 灾难类作验证；P3 平。too_hard → fitness 掉底。
- **alignment**：gap fitness 本就优化"neural 比经典差"，搜索天然找相对退化方向。
- **搜索信号 = gap（连续）**；**finding 判据 = 两层离散（越抖动门槛 + 触发性质确认，见 §4.5）**。
- per-property `margin_c_i`（经典标称余量 30%）；每评估 = 2 次 SITL。

### 4.5 finding 体系 / 指标 / 有效性
**两层 finding 体系（primary_bug 仅指 confirmed strict）**：
- **candidate**：`ρ_neural ≤ 0`——弱信号，不是 finding。
- **relative_degradation_differential**：`ρ_neural > 0 ∧ ρ_classical ≥ margin_c ∧ gap ≥ repro_margin`，**且触发性质跨种子复现**——神经显著差、都受控。
- **strict_differential**：`ρ_neural ≤ −repro_margin ∧ ρ_classical ≥ margin_c`，多种子复现。**`primary_bug` ⟺ confirmed strict，仅此**。

**有效性纪律（含 wave-1 两条新教训）**：
- **SIH 固有抖动 + 越抖动带**：固定 `(θ,seed)` 串行重跑 ρ 也抖（P7 band 0.224 = max(classical 0.224, mcnn 0.198)、P5 ~0.28、P1/P4/P6 ~0.01）；复现 margin = `max(0.02, 2×抖动带)`，**P7 strict 要 ρ ≤ −0.448**。
- **触发性质确认（新，wave-1 教训）**：候选因性质 X 入选 → **只有 X 跨种子复现才算 X-confirmed**。**不能用 target-set 兜**——P4 ~100% 复现，会把因 P7 入选的候选"假确认"。wave-1 正栽在此：legacy"12 confirmed P7"实为 P4/P6 兜，真 P7 confirmed 仅 2/12@≥2/3、0/12@3/3。
- **按 gap 量级报、不按计数**：P4 ~100% flag 但微小 = 架构基线，不计 finding；真信号看稀疏大量级 + 触发性质复现。
- **真失败非 harness**：`run_error`、console fault scan、到 `mission_end`、触发须真发火、fail-loud；NN identity 硬闸；reachability 诚实。

**RQ/指标**：RQ1 存在性（A 路线灾难类✓；行为类在 wind+physics = negative，待 wave-2 估计污染或变形 oracle）、RQ2 搜索有效性（wave-1 温和）、RQ3 失效刻画、RQ4 迁移、RQ5 缓解。噪声地板【实测】姿态 max ~1°、tracking RMS ~0.04 m。

---

## 5. 我们做了哪些实验（诚实旅程 + 教训）

### 5.1 RAPTOR 线（7 轮 → 鲁棒）
M0（`b1be614`）容器+SITL；M1（`6c944b9`）四象限 MVP，**裁剪使幅度攻击失效**；M2/M2.5/M2.6/M2b-1 制导搜索全 0 confirmed，**M2.6 高 TWR 后证为噪声（假阳教训）**；诊断 D1/D2/D3。**0 confirmed，RAPTOR 鲁棒，很大程度因裁剪。**

### 5.2 mc_nn_control 线（GATE-1/2/3）
GATE-1（`b0121ee`）存在/零训/mode 23/**正面 ID**；GATE-2 **无任何裁剪**、15-D、前馈非 stateful；GATE-3（`a8dd59b`）幅度 NO-GO，**反转：mc_nn 对幅度比经典更鲁棒**（RMS 经典 0.49 > mcnn 0.38）。

### 5.3 FUZZ 线（A 路线硬结果）
模式切换：差分降为分类器、检测器放最宽、经典事后分类。
- **FUZZ-1（`4685b96`）**：极端角落 3 eval 命中翻机，**但 confound** → 朴素差分_过度声称_。
- **FUZZ-1b（`345d2c6`）**：groundtruth 对齐后经典也 failsafe 但 **did not tumble** → 二值检测器抹平质差 → _漏报_。
- **FUZZ-1c severity（`301f564`）**：分级 severity，宽口径 CLEAN_DIFFERENTIAL。
- **FUZZ-1c 去污染重判（`65240a5`，A 路线硬结果）**：对称去污染重判 8 对。**4 个干净 strict 差分**（pair 1/2/4/5）classical=S0 ∧ mc_nn=S3；classical 的 S2 是基建污染（offboard 丢失 RTL 落地，failsafe 73.9-78.3 s、severity 不变 = 强基建签名）。

### 5.4 结构性失效区观察（需密扫分辨）
去污染后按 mc_nn 排：S3 @ 48.8/40.8/39.0，S0 @ 47.0/33.9/18.7/16.4，经典全 S0。**mc_nn 失效在切换姿态上非单调**。
> **诚实 caveat**：每点 wind/rate/approach 都在变（非干净一维扫）→ "流形孔洞/高维边界/风敏感"**尚未分辨**，需受控密扫。**是变形 oracle（选项 B）的明确靶子**——已知有结构、复用现有 harness。

### 5.5 旅程总教训（驱动 §6）
1. 两个产线学习型控制器对大误差/幅度类都鲁棒；catastrophic differential 在切换瞬态 + 失效结构。
2. 差分 oracle 真实有效，但可靠性依赖卫生机制 + 假阳纪律（朴素既过度声称又漏报；普遍性质会假确认）。
3. 二值检测器抹平真实质差。
4. → 经典差分只覆盖灾难类；多 oracle 刻画失效结构；**但便宜的 wind+physics 行为类轴是干净 negative，戏剧性行为类差分（若存在）更可能在估计污染或非单调切换区。**

### 5.6 B 路线执行进度（性质 oracle + 搜索机器 + 基建）
> 顺序记账；每项以 commit 锚定。

- **Tier 0 — 性质 oracle（`2e7b6b7`）**：`property_oracle.py` 从 ULOG（Method-A）算 P1-P7 ρ_i——**P1 姿态包络 / P2 角速率（灾难类）、P3 饱和、P4 控制量平滑不抖振、P5 阶跃 settling、P6 不持续振荡/极限环、P7 无稳态偏差**——含 PGFuzz 去噪、控制窗去污染、S0-S4、mcnn ID。`m1_compare.py` 差分包装。`oracle_calibration.md` 16 阈值。**验证**：route-A 4 对复现 strict，标称全 S0。**边界**：route-A 是灾难类（P1/P2），验证管线、不验证行为类差分力。
- **Tier 0.5 — 搜索机器**：
  - **2.1 genome（`ab86b5b`）**：θ→可搜 genome；**救活 P5**（加阶跃轴，标定 `ε_set=1.05/T_set=5.0/W_hold=2.0`）；估计污染 DEFERRED。
  - **2.2 fitness（`4afb191`）**：`property_fitness.py` 差分 gap fitness + per-property margin + 分层，wire 进 `m2_map_elites.py`。route-A 回归通过。
  - **2.3 冒烟（`ab50cce`）**：Part 1 机器验证；Part 2 第一次行为类首探 = **P7 梯度**（7 m/s 风 neural ρ7=0.37 vs 0.98，未越线）——**注：这条梯度在 wave-1 规模下被证明不 robust（见 5.7）**；Part 3 random baseline 桥。
- **Tier 1 — campaign 基建**：
  - **并行 profiling（`3d999af`）**：N≥2 串扰不 clean，推荐 N=1 @ 16.6 evals/h。
  - **恢复尝试（`776c947`）**：CPU pinning 把污染 5×→3-4× 但仍越 gate（**并行未恢复**）；speed 1.25 → **23.3 evals/h**。**根因 confirmed = offboard setpoint 是 wall-clock ROS timer、未锁 lockstep sim**。Step C 延后、方向记。
  - **有效性自动化（`8217025`）**：`validity_automation.py` = 对称去污染 + identity 硬闸 + 抖动 margin，焊进 eval 管线 + `(θ,seed)→ulog`。

### 5.7 wave-1 campaign（诚实 verdict = 干净 negative）
> 组合 wind+physics 稳态、N=1 @ 1.25、200 guided + 200 random（199/198 usable）。**B 路线第一个实证产出，verdict 是干净 negative。**

- **基建**：组合 genome（`659c8da`，steady_combo + 2D descriptor）；可续 campaign runner（`343828e`，原子 checkpoint/resume，kill+resume==不中断已验，guided/random/grid 共 harness + validity gate + 单 eval 容错）。
- **诚实 verdict**（`docs/wave1_windphysics_20260627.md`，已按此口径重生成）：
  1. **strict 绝对违反 = 0（robust）**。neural 单抽里勉强越名义线（ρ7 −0.12 / −0.04，高应力格），但无一过 margin −0.448。干净 negative。
  2. **戏剧性 P7 退化 = 噪声尾巴，不是 finding**。单抽大 P7 gap（max 1.04），但：
     - **触发性质重判**：P7 confirmed **2/12 @ ≥2/3、0/12 @ 3/3**（9/12 是 0/3）。legacy"12 confirmed"是普遍的 P4/P6 兜的、不是 P7。
     - **方差判定**：neural P7 方差**不**显著大于经典（mean 0.0247 vs 0.0241、pooled ratio 1.40、per-candidate 中位比 0.72）→ **不是**神经特有不一致。
     - → 那些 ~1m 大偏移是**共享 SIH 噪声的稀疏尾巴**（P7 median gap 仅 0.013，13% 尾巴大多不复现）。
  3. **只有 P4/P6 小而稳的相对退化**：P4 100% flag、gap ~0.19、**3/3 复现**；P6 65%、gap ~0.05、3/3。"neural 一致略糙、略多振荡"——真实可复现，但**小、偏架构签名、非安全失效**。
  4. **RQ3 图**：cell 用 max gap / min rho（**极值单抽**，非均值）→ 是 distributional 提示、非稳定退化。
  5. **C3（诚实）**：guided 小胜 illumination（QD 5.25 vs 4.79、bins 8 vs 7），但 random 拿单格最强 gap、触发性质 P7 confirmed 持平（各 1）——非碾压，目标普遍；强 C3 待稀有目标（wave-2）。
- **方法学意义**：**assay 正确拒掉了一个本会是"12 个 finding"的假阳**（多种子 + 触发性质纪律）——这是项目可信度的来源，也是可报的方法学点（该方法能区分真差分 vs 噪声/架构签名）。
- **科学含义**：**最便宜的 A 档轴（wind+physics 稳态）上，戏剧性行为类宽差分不存在**——干净 negative，按 §6 预测精确指向**估计污染轴**（物理扰动可补偿 → 空；状态信念污染补不了）。

---

## 6. 从单 oracle 到多 oracle（B 路线）

**为什么多 oracle**：catastrophic differential 只覆盖"经典稳/学习型失控"一类。学习型差异更多活在**没到坠毁的行为、失效边界_形状_、对称性**里——FUZZ-1c 非单调区即例证（差分 oracle 本身不解释机制）。

**多 oracle 套件**：
- **差分 oracle**（已验证 + 三个卫生机制 + 自动化 + 两层 + 假阳纪律）。
- **性质/规约 oracle（PGFuzz 式 MTL）— 已建成、wave-1 出了干净 negative**：`property_oracle.py`，P1-P7。**wind+physics 上无戏剧性行为类差分；指向估计污染轴。**
- **变形/不变性 oracle — 选项 B（便宜 hedge，复用 harness）**：场景旋转/镜像 → 响应应相应变换。经典对称由构造、神经破对称 = 干净 NN-specific bug。**直接打 FUZZ-1c 非单调区（已知有结构）**。贡献承重项，不用 EKF2、不用 Step C。
- **鲁棒性/平滑性 oracle**：搜神经局部非 Lipschitz；离线版直接探策略函数。
- **更强参照差分**（MPC/可达性认证）：A 路线已有轻量版。stretch。

**§6 方向性（已被 wave-1 部分证实/修正）**：性质 oracle 高产 θ 区原判为 A 档 + 稳态——**wave-1 把"wind+physics 稳态"这条具体轴证为 negative**（物理扰动可补偿）。**估计污染（wave-2，补不了的状态信念攻击）是 A 档里真正未试的高产候选**；但它最贵。变形 oracle 打的是另一类（对称破缺）、便宜、靶区已知。

---

## 7. Oracle 排序（按可行性 + 可信性）

> 实际执行先做了②性质 oracle；wave-1 在 wind+physics 上 = 干净 negative。下一发候选见 §8 开放岔路。

1. **变形/对称（equivariance）** — 高/高。复用 harness、不用 EKF2/Step C，靶区（FUZZ-1c 非单调）已知。**便宜 hedge（选项 B）。**
2. **性质/规约（PGFuzz 式 MTL）** — 中高/高。**已实现 + wave-1 出干净 negative（wind+physics）；估计污染轴未试（选项 A，最贵）。**
3. **鲁棒性/平滑（离线对抗敏感度）** — 高/中高。离线探雅可比便宜。
4. **更强参照差分（MPC/可达性认证）** — 最高/最低。stretch；A 路线有轻量版。
5. **灾难性差分（现有）** — 高/高。**A 路线已验证；现作性质 oracle 灾难类（P1/P2）+ 标定基线。**

---

## 8. 当前决策 + 下一步

- **A 路线：硬性收官并锁定**（本叙事即锁定形式）。
- **B 路线：性质 oracle + 搜索机器 + Tier 1 基建建成；wave-1（wind+physics）= 干净 negative + assay 拒假阳演示 + 小 P4/P6 签名。** 戏剧性行为类 finding **未拿到**。
- **开放战略岔路（留作新对话讨论，本版不锁方向）**：
  - **(A) 上 wave-2 估计污染**：Step C（setpoint 锁 sim 时间，恢复并行/高 speed）→ EKF2 6 文件 3-way 整理 shim drift → genome 加 state-contam 变量 → campaign 找 robust 绝对违反。**§6 + wave-1 negative 都指向它，原则上最对；但最贵，且可能也 negative。**
  - **(B) 先上变形 oracle（B 档非单调区）**：复用现有 harness、不用 EKF2/Step C，打**已知有结构**的非单调灾难区找对称破缺。**便宜 hedge，先拿一个不同_类型_的 NN-specific 结果在手**，再决定要不要砸 wave-2 大基建。
  - **(C) 重掂行为类 finding 必要性**：A 路线灾难差分 + 可靠 oracle 方法学 + 干净 negative + P4/P6 小签名，可能已够一篇（偏"方法 + 灾难 finding + 诚实负结果"）。
  - **（上轮倾向：别直接砸 wave-2 大基建；先 (B) 拿便宜结果 + 把 wind+physics negative 当独立可报结果——但这是用户的时间线/价值判断，下一对话定。）**
- **已定口径**：两层 finding（strict + relative-degradation）+ **触发性质确认纪律**；按 gap 量级报；A 路线严口径（S0-vs-S3）。
- **机器约束**：N=1 单机一次只跑一个 SITL 工作流——campaign 占机时其他 SITL 验证须错开（代码可并行）。
- **暂缓**：给 SIH 打补丁做直接置态（Method A 残差够紧）。
- **悬而未决**：工具名（`[TOOL]`，候选 TwinFuzz/CtrlDiff/OracleSwap）；目标会议（ICSE/FSE/ASE/ISSTA）+ 窗口；Phase 3 栈优先级；何时引入真板解锁 RQ4。

---

## 9. 环境 / 复现 / 工程约定（给 agent）

- **容器入口**：`sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<name> ./docker/run.sh bash -lc "..."'`。镜像 `uav_sf:phase1`。常规路径用 `sg docker`、避免 sudo。坑见 `AGENT.md`。
- **PX4**：固定 `3042f906`，源码 `external/PX4-Autopilot`（gitignored）。board `px4_sitl_mcnn_sih` 同编 mc_raptor 但 RAPTOR 不启动 → **mode-23 飞行须正面 ID 确认**（已自动化为每 eval 硬闸）。
- **仓库约定**：`external/PX4-Autopilot`、`ros2_ws` gitignore → PX4 改动以 **tracked patch/overlay + installer** 入库；证据落 `docs/`。
- **git 卫生（重要）**：`*.ulg` **已 gitignore、保持 untracked**。ulog/run 目录/checkpoint（`runs/` 已 ignore）留本地，commit 只含代码+报告。验证：`py_compile`/`unittest`/`bash -n`/`jq empty`/`git diff --check`(+`--cached`)。
- **吞吐 / 并行（硬约束）**：**N=1 @ `PX4_SIM_SPEED_FACTOR=1.25` ≈ 23.3 evals/h**。**并行不可用**：N≥2 串扰（端口/tmp/ulog/run-root 全隔离 + CPU pinning 仍越 strict 抖动 gate）。**根因 = offboard setpoint 是 wall-clock ROS timer、未锁 lockstep sim**（`m1_offboard_task.py` 的 `create_timer`）。恢复路径（Step C，选项 A 的第一步）：setpoint 锁 sim 时间 / lockstep 等 setpoint，再重测 N≥2 与 speed 2.0+，改后须 route-A + 锚点回归。
- **SIH 固有抖动**：固定 `(θ,seed)` 串行重跑 ρ 也抖（P7 band 0.224、P5 ~0.28、P1/P4/P6 ~0.01）。复现 margin = `max(0.02, 2×抖动带)`。**wave-1 教训：confirmation 必须按_触发性质_，别被 P4 普遍复现假确认。**
- **patch drift（绑 wave-2 / 选项 A）**：`patches/px4/m2b_state_shim.patch` 正反向 apply 均失败 = drift（EKF2 + vehicle_angular_velocity 6 文件，3-way 重贴）。**不影响纯 offboard/groundtruth/ulog-重分析轮次**（wave-1 即此类）；**走 shim 注入（估计污染）前须先整理。**
- **仿真器**：SIH 为主（headless/lockstep；**但非 bit-exact**，故多种子 + 抖动带纪律）；Gazebo 仅可视化/电机故障（SIH 故障支持未验证）。
- **关键脚本**：
  - 任务/比较：`m1_offboard_task.py`（**当前 wall-clock 计时**）、`m1_metrics.py`+`m1_compare.py`（四象限 + 差分包装 + 两层 finding，primary_bug 仅 strict）。
  - **B 路线**：`property_oracle.py`（P1-P7 ρ）、`theta_genome.py`（genome + `steady_combo` + 算子）、`property_fitness.py`（gap fitness + candidate/relative/strict 三层）、`validity_automation.py`（去污染 + identity + 抖动 margin）、`m2_map_elites.py`（搜索驱动）、`parallel_profile.py`（吞吐+串扰）、`campaign_runner.py`（N=1 可续 campaign）、`wave1_windphysics_report.py`（wave-1 报告 + 触发性质重判 + 方差分析）。
  - A 路线：`fuzz1c_severity_scan.py`、`fuzz1c_decontam_analyze.py`、`mcnn_gate3_position_error_probe.py`、`m2_5_estimator_fairness.py` 等。
- **关键报告/标定**：`oracle_calibration.md`、`oracle_impl_20260626.md`、`genome_spec_20260626.md`、`fitness_wire_20260626.md`、`smoke_2p3_20260626.md`、`parallel_profile_20260626.md`、`parallel_recovery_20260626.md`、`validity_automation_20260627.md`、`genome_combined_steady_20260627.md`、`campaign_runner_20260627.md`、**`wave1_windphysics_20260627.md`（wave-1 诚实 verdict）**；A 路线 `fuzz1c_severity_20260625.md`、`fuzz1c_decontam_20260625.md`。
- **最近 commit**（新→旧）：wave-1 触发性质重分析 + 贴标/报告收尾（已做）｜`659c8da`(组合 steady genome)、`343828e`(可续 campaign runner)、`8217025`(有效性自动化)、`776c947`(并行恢复)、`3d999af`(并行 profiling)、`ab50cce`(2.3 冒烟)、`4afb191`(2.2 差分 fitness)、`ab86b5b`(2.1 genome + P5)、`2e7b6b7`(Tier 0 性质 oracle)｜A 路线：`65240a5`、`301f564`、`345d2c6`、`4685b96`、`a8dd59b`、`b0121ee`。

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
