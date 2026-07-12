# 项目叙事与上下文文档 v6 — 学习型 UAV 飞控的场景模糊测试

**用途**：切换对话时的完整上下文 + 给执行 agent 的叙事参考。读完即可接续，无需回溯历史对话。
**取代**：v5。**本版的核心变化**：v5 把战略停在一个**开放岔路**（wave-2 估计污染 / 变形 oracle / 重掂行为类 finding 必要性）。v6 记录项目**做出了决定性的一步并成功**——把制导搜索**掉头对准切换瞬态区、用灾难类严重度目标 fitness**，一炮同时立起 **RQ2（制导 vs random/grid）、RQ3（失效边界逐轴刻画）、RQ1 灾难类系统化**。同时两个战略变量已锁：**目标 SE 会议**（ICSE/FSE/ASE/ISSTA）、**实验预算充裕**。因此 §8 战略岔口**重新洗牌**：wave-2 / 变形 oracle 从"必需"降为"可选上行"；**写作成为下一块最大的未做工作**。
**Date**: 2026-06-30
**Repo**: `github.com/JacksonW1025/uav_sf`，工作区 `/mnt/nvme/uav_sf`（容器内）。PX4 固定 `main@3042f906abaab7ab59ae838ad5a530a9ef3df9a6`（v1.18 alpha）。**注意：公开 GitHub 仍停在 RAPTOR 线；A 路线 + B 路线 + 本次 campaign 尚未推上公开 main**（见 §9）。
**配套设计文档**：`oracle_map_and_property_set_v0.1.md`、`fullscale_fuzzing_preflight_checklist_v0_1.md`、`docs/wave1_windphysics_20260627.md`（wave-1 诚实 negative）、**`docs/switch_severity_campaign_20260629.md`（本次 campaign 完整结果）**。

---

## 0. 速览（TL;DR）

**Idea**：学习型低层飞控（PX4 Neural Control、Science Robotics 的 RAPTOR 基础策略）正进入生产自驾仪却没有系统化安全测试。我们在**同一固件、同一机架、同一任务**下，用搜索（fuzzing）在扰动/机动/故障/指令的场景空间里找学习型控制器的失效，用**经典控制器当内建差分 oracle**（经典 safe ∧ 学习型 unsafe）作为闭环控制失效的归因，并把它扩成**多 oracle 套件**。**定位 = SE 方法稿**：头条不是"抓了多少 bug"，而是可靠 oracle + 假阳纪律 + 可复现 + 系统化失效刻画。

**当前状态（三条主 RQ 已有可写进论文的数据）**：
- **A 路线（灾难差分锚点，已锁 + 已在 v6 重新多种子确认）**：mode-23 中途交接剧烈状态，经典 **S0 干净恢复** ∧ `mc_nn_control` **S3 失控翻机**（>90°、>8 rad/s）。原 4 个 strict 差分在多种子 severity+符号闸下复现：pair1/pair2（高-θ 同工况）**3/3**、pair4 **3/3**、pair5 **8/9（88.9% 概率性锚点，保留）**。
- **B 路线-wave-1（性质 oracle，wind+physics 稳态 = 干净 negative）**：strict 绝对违反 = 0（robust）；戏剧性 P7 退化被证为共享 SIH 噪声尾巴（触发性质 2/12@≥2/3、0/12@3/3，方差非神经特有）；only 小而稳的 P4/P6 架构签名。**assay 正确拒掉了一个 12-finding 量级假阳。**
- **切换区严重度 campaign（本版核心新结果，已 commit `118d58f`）**：把差分 fitness 重定向到灾难类 {P1,P2}、primary 判据 = `strict_s0_vs_s3`（去污染后经典 S0 ∧ mc_nn S3）、descriptor = `switch_attitude × wind`。
  - **RQ2（制导有效）**：guided **179** 个 primary（每种子 54–65）vs random **40**（12–16）vs grid **19** —— **约 4.5× 密度**、**每有效 eval 命中率 ~60% vs random ~12%（~5×）**、QD 均值 ~189 vs 119 vs 123、种子间方差极小。**但最严 3/3 确认档 guided 与 random 打平（各 6/10）**——制导没找到 random 找不到的 cell，而是**更快、更稳、更全地照亮同一批 cell**。主张必须框成"效率/照亮/一致性"，**不能框成"找到更多 bug"**（否则被 3/3 打平一击打回）。
  - **RQ3（失效刻画，比 RQ2 更出彩）**：逐轴密扫把原非单调观测拆成干净的**高维带洞边界**——姿态 ~40° 起、42–45° 稳、48° 部分恢复；rate 1.55 有洞、1.75 恢复；delay 0.06/0.12s 时间洞；**风 0–3 m/s 暴露差分、4–6 m/s 反而恢复**（反直觉，全篇最亮点，说明是相位/共振而非单调应激）。pair5 8/9 顺势坐进边界叙事。
  - **RQ1 灾难类**：从"4 个轶事"变成"179 primary + ~10 个确认 cell、跨姿态跨风、多种子"，彻底系统化。

**下一步 = 重新洗牌的战略岔口（§8，本版倾向"先写作"，但由用户定）**：论文脊柱已完整（可靠差分 oracle 方法 + 系统化灾难差分 + 制导效率 + 高维带洞边界 + 全程诚实纪律 + wave-1 诚实 negative）。**不做 wave-2 这篇也完整。** wave-2/变形是**主张广度**的上行期权（把"切换瞬态"拓宽到"非切换轴也失效"），不是完整性的必需。**论文正文仍停在 M0/M1 旧稿——这是当前最大的未做块。**

---

## 1. 核心 Idea / Thesis

测学习型控制器的根本难点是 **oracle 问题**：要判它"飞错了"，须先知道"正确飞行长什么样"，而任意扰动下的绝对正确性极难规约。

**关键想法**：PX4 让经典与学习型控制器在**同一固件**共存、可切换。同机架/同任务/同扰动下，若**调好的经典守住、学习型失败**，则该失败**学习型特有**——归因靠结构、不靠手搓正确性规约。在此之上用 fuzzing 搜这些失败。**A 路线证明这个 oracle 真实有效**（拿到干净严差分），**切换区严重度 campaign 进一步证明制导搜索能系统化地找到、并刻画这类失效的边界**——前提都是那三个卫生机制。

**扩展（B 路线）**：经典差分只是"判定正确飞行"的一种方式。学习型控制器的"bug"不一定是坠毁、不一定需经典对照（可以是违反控制性质、破坏对称性、对微扰异常敏感）。我们因此把经典差分扩成**多 oracle**。B 路线第一发 = 性质 oracle（PGFuzz 式 MTL）：**wave-1 在最便宜的 wind+physics 轴上是干净 negative**（可报，指向估计污染轴）；差分 oracle 则在切换区拿到了两个决定性结果（A 路线手工 + 严重度 campaign 制导）。

---

## 2. Contribution（据 v6 结果升级）

### 2.1 方法稿贡献（C1–C5，多数已兑现）
- **C1**：学习型 UAV 飞控的差分场景模糊测试**问题表述**。✓
- **C2（已验证 + 双结果 + 假阳纪律）**：**可靠的内建跨控制器差分 oracle**——对齐切换状态 + 分级严重度 + 基建去污染 + **多种子越抖动 + 灾难类以离散 severity/符号确认**才可信。已自动化（`validity_automation.py`）。**两层 finding + severity-triggered primary**。**wave-1 演示了拒假阳**；**切换区 campaign 演示了制导搜索能系统化触发这个 oracle**。✓
- **C3（已答，带效率框架）**：面向学习型控制的**搜索反馈/制导**——差分 gap fitness + MAP-Elites + baseline 消融。**切换区 campaign 诚实 C3**：guided 在等预算下以 ~5× 命中率、~60% 更高 QD、显著更低种子方差**更密更全地照亮**灾难差分区；**但在 3/3 确认档与 random 打平**——主张 = 效率/照亮/一致性，非 bug 计数。✓（带 caveat）
- **C4**：**免训、可复现的测试平台/基准**，实例化在两个真实 shipped 控制器上。✓
- **C5（已成形）**：学习型控制器**失效分类**——切换瞬态灾难差分（P1/P2）+ 高维带洞边界（姿态/rate/风/delay/相位皆有洞或恢复区）+ wind+physics 上的行为类 negative + 小 P4/P6 架构签名。缓解仍在 discussion 层。✓（分类成形，缓解待补）

### 2.2 经验头条结果
- **A 路线（灾难差分锚点）**：剧烈中途交接，经典 S0、mc_nn S3 翻机；4 个 strict 差分在多种子下复现（3/3、3/3、3/3、8/9）；基建归因清晰、对称公平；反直觉——mc_nn 对幅度比经典**更**鲁棒（GATE-3）。
- **切换区严重度 campaign（制导系统化）**：179 个 guided primary、~10 个确认 cell 跨姿态跨风；guided 效率/照亮碾压 random/grid（3/3 打平）；失效边界经密扫刻画为**高维带洞、非单调**，含反直觉的"高风恢复"。
- **B 路线-wave-1（诚实 negative）**：性质 oracle 复现 A 路线灾难差分（验证管线）；wind+physics 稳态上戏剧性行为类差分 = 干净 negative；assay 拒掉 12-finding 假阳。

### 2.3 演进后的论文主张（v6 定形）
**头条 = "面向集成进固件的学习型飞控的、以可靠差分 oracle 为核心的多-oracle 场景测试方法"**。价值三支柱：**(方法)** 可靠差分 oracle（三卫生 + severity-triggered 判据 + 假阳纪律）；**(RQ1/RQ2)** 制导搜索系统化找到并高效照亮灾难差分区（179 primary，效率 ~5×）；**(RQ3)** 高维带洞失效边界的逐轴刻画（含反直觉高风恢复）。辅以 wave-1 诚实 negative（方法能区分真差分 vs 噪声/架构签名）+ pair5 概率性边界锚点。**戏剧性"非切换轴"行为类差分仍未拿到**——是否砸 wave-2 拓宽主张 = §8 上行期权，**非完整性必需**。

---

## 3. Related Work（六根轴，定位 gap）

沿两轴：**(i) 是否建模/扰动控制器闭环动力学**；**(ii) 被测对象是经典控制软件、状态机，还是学习型控制器**。

- **(a) UAV 障碍/场景 fuzzing 与路径规划器测试**：DPFuzzer（ICSE'25）、SBFT CPS-UAV 簇、SwarmFuzz。聚焦几何/障碍、假设理想执行器、不测低层控制器、无学习型脆弱性概念。
- **(b) RV 控制/配置/策略 fuzzing**：RVFuzzer（USENIX'19，控制失稳检测器 oracle + 单调性制导二分）、LGDFuzzer（ICSE'22）、**PGFuzz（NDSS'21，MTL 安全策略 oracle + global distance 引导，156 新 bug，真机复现）**、ADGFuzz、IMUFuzzer（ASE'25）、RouthSearch（ISSTA'25，7 RQ、离线 vs 在线 oracle、搜索算法消融、基线跑 3 遍控方差）。被测是经典控制软件；无 learned-vs-classical 差分。**PGFuzz 的"性质即 oracle"是本项目性质 oracle 的直接模板（`property_oracle.py`）。RouthSearch/ADGFuzz/SwarmFuzz 的"制导 vs random + 消融 + 方差"是本项目 RQ2 对标的领域标准——切换区 campaign 已按此做（多种子三臂）。**
- **(c) 模式/状态/failsafe 语义 fuzzing**：SaFUZZ（ICSE'26）、HIFuzz。作用在状态机/模式层，不下沉控制器层。
- **(d) 赛博-物理不一致与神经控制器证伪**：CPI（CCS'20）；ARCH-COMP AINNCS、S-TaLiRo/Breach/ARIsTEO、NNV/Verisig/CORA。最直接前作，但基准是玩具系统、可达性在真实 6 自由度固件级不可扩展、无内建差分 oracle。
- **(e) 学习型 UAV 控制与基础策略**：RAPTOR（Science Robotics 2026）、NTNU PX4 神经模式（arXiv:2505.00432）、Zhang 极端自适应（T-RO 2025）、Neural-Lander。**构造**学习型控制器，不提供系统化方法找它们相对经典在哪儿失败。
- **(f) 自动驾驶 ML 测试（方法迁移源）**：成熟的 ground-truth-vs-actual 差分、metamorphic、对抗鲁棒、OOD 检测。我们迁移其**差分/蜕变/鲁棒**精神到 UAV **闭环控制**。

**Gap**：尚无工作系统化搜索扰动/机动/故障场景空间，用**多 oracle（含_可靠_的经典-学习型差分）**找出**集成进固件的学习型飞控**相对经典**特有的失效**并刻画其**高维边界与根因**。

---

## 4. 实验设计

### 4.1 被测对象（SUT）
同一 PX4（`3042f906`）、同一机架（**X500 v2**）、同一任务。两个学习型 backend：
- **RAPTOR**（`mc_raptor`，免训基础策略，22-D 观测/4-D 动作，GRU-16，2084 参数）。
- **`mc_nn_control`**（PX4 内置神经模式，TFLM，**前馈网**无递归，15-D 观测/4-D 动作）。**前馈无积分器**——在 wind+physics 上未产生 robust P7 退化（物理扰动可被位置反馈补偿），但在**切换瞬态**是灾难差分的失效方。
- **两者切换路径字节级相同**：`mode_id 23` → 每轮 mode-23 飞行须**正面控制器 ID 确认**（已自动化进 eval 管线，见 §4.5）。

### 4.2 差分 Oracle + 三个卫生机制（A 路线验证 + 切换区 campaign 复用，已自动化）
**四象限**（同 θ 跑两遍，同机架/种子/注入序列/sim 时间对齐）：`boring_both_safe` / `interesting_not_bug` / **差分（经典 safe ∧ 学习型 unsafe，只报这类）** / `too_hard_not_bug`。

**让差分可信的三个卫生机制**：
1. **对齐切换状态**：SIH 无快照/置态 API → **Method A，groundtruth 触发**，再以 ULOG 真值回匹配（rate 残差均值 ~0.09 rad/s）。
2. **分级失效严重度**：**S0 / S1 / S2 / S3 失控翻机（≥90° 或 ≥8 rad/s）/ S4 数值 fault**。关键切分 = 受控（S0-S2）vs 失控（S3-S4）。
3. **剔除基建污染**：offboard 丢失/datalink/RC/估计器 position-jump failsafe、failsafe 触地、低于最小可恢复高度切换。**处理方式（v6 明确）= 截断 control window 后重算控制级 severity，不是剔除整个 eval**；只有 unresolved failsafe / 起始高度太低才 gate-fail。**对两控制器对称。**

> **已自动化**：封进 `validity_automation.py`、自动施用于每个 eval（wave-1 在 400 eval 上稳定；切换区 campaign 全程复用）。

### 4.3 场景空间 θ（已写死成可搜 genome；切换区已按可达性修正）
θ 三档：**A 档**（状态估计污染、物理失配）；**B 档**（时序/接口、**切换瞬态**——差分主战场）；**C 档**（setpoint 幅度——GATE-3 判死）。

**genome**（`theta_genome.py`）：
- **A 档-wind+physics（`659c8da`）**：持续风 **与** 物理失配同 θ 生效（`steady_combo`），2D wind×physics descriptor。**wave-1 已跑 = 干净 negative。**
- **B 档-切换瞬态（v6 已按可达性重定义，为切换区 campaign）**：genome 覆盖 **姿态 16–50°、角速率 0.45–2.75 rad/s、wind 0–6、delay 0–0.18**。**关键修正（Addendum 4）**：`route_a_profile_for()` 原让 roll/pitch 与 rate 独立采样，但 rate 物理上被姿态轨迹决定（radius/frequency clamp 后 rate 受限），"低姿态+高 rate"不可达 → 触发 timeout。**建议 B 落地**：clamp 后**重算** trigger rate 为实际可达值（对齐触发、不改搜索维度）。可达性测绘（情形 3：rate 有跨度但强依赖姿态）→ **最终 descriptor = `switch_roll_pitch_bucket × wind_bucket`，rate 保留为受可达约束的搜索变量、不进主 descriptor**。
- **阶跃轴**：适度 setpoint 阶跃（为 P5），与 C 档极端幅度划清。
- **DEFERRED**：状态估计污染（走 shim，受 patch drift 阻塞，见 §9）——**§6 高产候选，留 wave-2（上行选项 A）**。
- **EXCLUDED**：C 档幅度攻击（GATE-3）、电机/传感器故障（SIH 未验证）。

**可达 rate 包络（测绘表，供参考）**：

| attitude bin | reachable actual rate span |
|---|---:|
| 16.0–22.8° | 0.648–0.922 rad/s |
| 22.8–29.6° | 0.648–1.247 rad/s |
| 29.6–36.4° | 0.648–1.615 rad/s |
| 36.4–43.2° | 0.747–2.029 rad/s |
| 43.2–50.0° | 0.906–2.502 rad/s |

### 4.4 搜索与反馈（已答 RQ2）
fitness = **差分 gap，不是绝对 ρ**：`gap_i = ρ_i(classical) − ρ_i(neural)`。
- **wave-1（行为类目标）**：目标 = P4/P6/P7（+ 阶跃 P5）；结果干净 negative。
- **切换区 campaign（灾难类目标，v6）**：**目标重定向到灾难类 {P1 姿态包络, P2 角速率}**（复用 `property_fitness.py` 的 `--target-properties`，preset `route-a-catastrophic`）。mc_nn 越逼近翻机、ρ_{P1/P2} 越平滑退化 → 给搜索指向翻机边界的连续梯度。**灾难类 fitness gate（v6 关键）**：仅当**去污染后经典 severity == S0 且 P1/P2 非 vacuous、ρ 有效**时 gap 才进 fitness；否则 floor（**绝不奖励 both-crash**）。
- **搜索信号 = gap（连续）**；**finding 判据 = 离散 severity（见 §4.5）**。
- 搜索器 = MAP-Elites（`m2_map_elites.py`）+ 三臂（guided/random/grid，`campaign_runner.py`，N=1 可续）。**grid 改为系统扫 `attitude × wind` 25 cells**（不再是旧 3×3×3）。

### 4.5 finding 体系 / 指标 / 有效性（v6：灾难类改 severity-triggered）
**两层 finding + severity-triggered primary**：
- **candidate**：`ρ_neural ≤ 0`——弱信号，不是 finding。
- **relative_degradation / strict（行为类）**：保留（wave-1 口径）；连续 ρ 门。
- **`strict_s0_vs_s3`（灾难类 primary，v6 主判据）**：**去污染后经典 severity S0 ∧ mc_nn severity S3**，**跨种子复现**。**阈值（v6 已定）：`≥2/3` 即算稳健 strict、成立 `primary_bug`；`3/3` 只作更强档报告。** 回归闸与 campaign confirmation **同此口径**（pair5 8/9 即按此保留）。

**有效性纪律（v6 定形）**：
- **灾难类一律以离散 severity + violation 符号为复现/确认门；连续 ρ 只作诊断展示、不作门限。** （教训见 §5.8：拿"安全裕度区标定的细抖动带"去卡"深违反区的粗抖动"必然误报。）
- **SIH 固有抖动 + 越抖动带**（行为类适用）：固定 `(θ,seed)` 串行重跑 ρ 也抖（P7 band 0.224、P5 ~0.28、P1/P4/P6 ~0.01；标定 `P1=0.0128 / P2=0.0935`，**注意此带仅适用于近无扰动轨迹**）。
- **触发性质确认（wave-1 教训，行为类）**：候选因性质 X 入选 → 只有 X 跨种子复现才算 X-confirmed，不能用 target-set 兜。
- **真失败非 harness**：`run_error`、console fault scan、到 `mission_end`、触发须真发火、fail-loud；NN identity 硬闸；reachability 诚实。**invalid（trigger timeout / 去污染失败 / run error / identity 失败）一律排除，不进任何象限、不计安全或不安全。**

**RQ/指标（v6 状态）**：RQ1 存在性（灾难类 ✓ 已系统化 179 primary；非切换行为类 = wind+physics negative，待 wave-2 上行）、**RQ2 搜索有效性（✓ 已答，效率/照亮框架）**、**RQ3 失效刻画（✓ 高维带洞边界逐轴）**、RQ4 迁移（部分由 mc_nn 第二控制器答；真板/ArduPilot 延后作 threats）、RQ5 缓解（discussion）。噪声地板【实测】姿态 max ~1°、tracking RMS ~0.04 m。

---

## 5. 我们做了哪些实验（诚实旅程 + 教训）

### 5.1 RAPTOR 线（7 轮 → 鲁棒）
M0（`b1be614`）容器+SITL；M1（`6c944b9`）四象限 MVP，**裁剪使幅度攻击失效**；M2/M2.5/M2.6/M2b-1 制导搜索全 0 confirmed，**M2.6 高 TWR 后证为噪声（假阳教训）**。**0 confirmed，RAPTOR 鲁棒，很大程度因裁剪。**

### 5.2 mc_nn_control 线（GATE-1/2/3）
GATE-1（`b0121ee`）存在/零训/mode 23/**正面 ID**；GATE-2 **无任何裁剪**、15-D、前馈非 stateful；GATE-3（`a8dd59b`）幅度 NO-GO，**反转：mc_nn 对幅度比经典更鲁棒**（RMS 经典 0.49 > mcnn 0.38）。

### 5.3 FUZZ 线（A 路线硬结果）
模式切换：差分降为分类器、检测器放最宽、经典事后分类。
- **FUZZ-1（`4685b96`）**：极端角落 3 eval 命中翻机，**但 confound** → 朴素差分_过度声称_。
- **FUZZ-1b（`345d2c6`）**：groundtruth 对齐后经典也 failsafe 但 **did not tumble** → 二值检测器抹平质差 → _漏报_。
- **FUZZ-1c severity（`301f564`）**：分级 severity，宽口径 CLEAN_DIFFERENTIAL。
- **FUZZ-1c 去污染重判（`65240a5`，A 路线硬结果）**：对称去污染重判 8 对。**4 个干净 strict 差分**（pair 1/2/4/5）classical=S0 ∧ mc_nn=S3；classical 的 S2 是基建污染（offboard 丢失 RTL 落地，failsafe 73.9–78.3 s、severity 不变 = 强基建签名）。**记录在 `docs/fuzz1c_decontam_20260625/results.json`。**

### 5.4 结构性失效区观察（原始，待密扫分辨——v6 已由密扫解决，见 5.8）
去污染后按 mc_nn 排：S3 @ 48.8/40.8/39.0，S0 @ 47.0/33.9/18.7/16.4，经典全 S0。**mc_nn 失效在切换姿态上非单调。** 原始 caveat：每点 wind/rate/approach 都在变（非干净一维扫）→ 尚未分辨。**v6：切换区 campaign 的受控密扫已把它拆成干净的高维带洞边界（见 5.8 RQ3）。**

### 5.5 旅程总教训
1. 两个产线学习型控制器对大误差/幅度类都鲁棒；差分活在**切换瞬态**（灾难类）+ 失效结构。
2. 差分 oracle 真实有效，但可靠性依赖卫生机制 + 假阳纪律（朴素既过度声称又漏报；普遍性质会假确认；**连续 ρ 在深违反区不是稳健复现量**）。
3. 二值检测器抹平真实质差。
4. wind+physics 行为类轴是干净 negative；戏剧性差分（若存在于非切换）更可能在估计污染轴。
5. **（v6 新）制导搜索在切换区能系统化触发灾难差分并高效照亮其边界；但因该区 bug 稠密，制导相对 random 的优势体现在效率/一致性，而非独占发现。**
6. **（v6 新，方法论）每次准备投预算，先有一道 preflight 把"锚点真不真/判据对不对/空间退不退化"里的隐藏矛盾炸出来——这套纠错回路是可信度来源，不是不顺。**

### 5.6 B 路线执行进度（性质 oracle + 搜索机器 + 基建）
- **Tier 0 — 性质 oracle（`2e7b6b7`）**：`property_oracle.py` 从 ULOG 算 P1–P7 ρ_i（P1 姿态包络 / P2 角速率（灾难类）、P3 饱和、P4 平滑、P5 settling、P6 不振荡、P7 无稳态偏差），含 PGFuzz 去噪、控制窗去污染、S0–S4、mcnn ID。`m1_compare.py` 差分包装。`oracle_calibration.md` 16 阈值。
- **Tier 0.5 — 搜索机器**：genome（`ab86b5b`，救活 P5）；fitness（`4afb191`，`property_fitness.py` gap + per-property margin + 分层 + `--target-properties`）；冒烟（`ab50cce`）。
- **Tier 1 — campaign 基建**：并行 profiling（`3d999af`）；恢复尝试（`776c947`，speed 1.25 → 23.3 evals/h，**并行未恢复，根因 = offboard wall-clock timer**）；有效性自动化（`8217025`）。

### 5.7 wave-1 campaign（诚实 verdict = 干净 negative）
> 组合 wind+physics 稳态、N=1 @ 1.25、200 guided + 200 random（199/198 usable）。`docs/wave1_windphysics_20260627.md`。
- **strict 绝对违反 = 0（robust）**。
- **戏剧性 P7 退化 = 噪声尾巴，不是 finding**：触发性质 P7 confirmed 2/12@≥2/3、0/12@3/3；方差非神经特有（pooled ratio 1.40）；~1m 大偏移是共享 SIH 噪声尾巴。
- **只有 P4/P6 小而稳退化**：P4 100% flag、gap ~0.19、3/3；P6 65%、gap ~0.05、3/3（架构签名，非安全失效）。
- **assay 正确拒掉了一个 12-finding 量级假阳**（多种子 + 触发性质纪律）。
- **科学含义**：wind+physics 稳态无戏剧性行为类差分（物理扰动可补偿）→ 指向估计污染轴。

### 5.8 切换区严重度 campaign（v6 核心新结果，`118d58f`）
> 目标：把制导搜索**掉头对准切换瞬态区**（A 路线灾难差分出处），fitness 改灾难类严重度目标，一炮补 RQ1 系统化 + RQ2 + RQ3。`docs/switch_severity_campaign_20260629.md`。

**preflight 纠错旅程（体现 §5.5 教训 6）**：
- **route-A 回归先失败 2/4**：pair1 `SKIPPED`（mc_nn task timeout，harness flake）；pair5 `NO_STRICT`（mc_nn S0，原记 S3）。**护栏正确触发，未烧长 campaign。**
- **代码漂移排查（关键判据修正）**：pair2/pair4 severity label 全稳（S0/S0/S3/S3），但连续 P1/P2 ρ 漂出标称 jitter 带。**判据修正**：那个 `P1=0.0128 / P2=0.0935` 的 jitter 带是在**标称近无扰动轨迹**上标的，**不适用于深违反/强切换/带风工况**（mc_nn 已翻成 S3、P2 已 −13 量级，重跑抖 ±3 是该 regime 正常方差）。**正确的同口径复现门 = 去污染后 severity 不变 + violation 符号不变（驱动 S3 的 P2 仍为负、经典仍为正）**。按此 pair2/pair4 **PASS**；叠加 `property_oracle.py`/`validity_automation.py`/`fuzz1c_decontam_analyze.py` **无 diff** → **代码漂移排除**。**沉淀设计原则：灾难类以 severity+符号为门，连续 ρ 只作诊断。**
- **多种子重判**：pair1 重跑 → 与 pair2 同工况 **3/3** strict（清 SKIP）；pair4 补 2 seed → **3/3**；pair5 固定 9 seed（`20261803..20262603`）→ **8/9 strict（88.9%）**，`20261803→S0`、其余 8→S3，**保留为概率性锚点**（原 scan 无 confirm run）→ 同时作 RQ3 种子级证据。
- **额外修复**：`property_oracle` state-trigger 窗口对齐——分析 start 曾错放到起飞前 → 假 `start_below_min_recovery_height`（validity gate-fail 条件之一，**曾悄悄制造假有效性失败**）；现用 task elapsed 对齐 ULOG boot time。
- **可达性 + descriptor**：见 §4.3（情形 3 → descriptor 改 `attitude × wind`，rate 退为受约束搜索变量；建议 B 落地）。
- **Step-1 探针（修正后空间）健康**：24 eval、22 valid、**5 primary S0∧S3**、14/25 valid cells、**0 too-hard**。放行三臂。

**RQ2（guided vs random vs grid，等预算/种子：guided 120×3、random 120×3、grid 120×1）**：

| arm | evals | primary | primary cells | entropy | conf 2/3 | conf 3/3 | QD 均值 |
|---|---:|---:|---:|---:|---:|---:|---:|
| guided | 360 | **179** | 10 | 3.184 bits | 8/10 | 6/10 | ~189 |
| random | 360 | 40 | 10 | 3.146 bits | 7/10 | 6/10 | ~119 |
| grid | 120 | 19 | 7 | 2.610 bits | 5/7 | 3/7 | 123 |

- guided 每种子 54–65 primary vs random 12–16；**~4.5× 密度**；**每有效 eval 命中率 guided ~60% vs random ~12%（~5×，归一化后更硬，写论文用它）**；grid 首命中到 eval 75（guided eval 1）。
- **诚实关键**：**3/3 确认档 guided 与 random 打平（各 6/10）**；guided 没独占任何 cell，是更快/更稳/更全照亮同一批 cell。guided primary 覆盖全部 10 个高危 `rp_3/rp_4 × wind` cell、entropy 与 random 相当 → **不是扎堆**。
- **主张框架（硬约束）**：效率 / 照亮 / 一致性；**禁止**框成"找到更多 bug"。

**RQ3（受控密扫，一固定边界基线、单维变动、seeds `2026062940/41/42`；40 点 120 eval 120 valid 81 strict）**：
- **姿态**：非单调——~40° 起（40° 2/3）、42–45° 稳（3/3）、**48° 部分恢复（1/3）**；28–38° 经典 S1/mc_nn 部分。
- **rate**：非单调——0.55–1.35 全 3/3、**1.55 洞（1/3）**、1.75 恢复（3/3）、2.05 概率性（2/3）、2.35 3/3。
- **风**：**边界塑形非应激放大——0–3 m/s 暴露（3/3）、4–6 m/s 恢复（0/3）**（反直觉高亮，相位/共振）。
- **delay**：时间洞——0.06/0.12s（1/3）、其余 3/3（相位/时序敏感）。
- **approach 相位**：改概率不改存在（各相位 2/3–3/3）。
- **解读**：失效是**高维带洞边界、非单调标量阈值**；pair5 8/9 一致（固定 θ 概率性边界点）。

**吞吐**：162.8 s/paired eval ≈ 22.1 eval/h；密扫 20.6 eval/h。与 serial SIH @ 1.25 一致。

**caveats（诚实）**：非正式显著性检验；3 guided + 3 random 种子，guided 的密度/QD 优势清晰但 top-candidate 确认数接近 → **不宣称 confirmed-count 上的强优越**；连续 ρ 仅诊断；invalid 排除；**SIH-only、shim-free、无 EKF2/Step C**。

---

## 6. 从单 oracle 到多 oracle（B 路线）

**多 oracle 套件（v6 状态）**：
- **差分 oracle（已验证 + 双决定性结果 + 三卫生 + 自动化 + 假阳纪律）** ✓：A 路线手工灾难差分 + 切换区 campaign 制导系统化（RQ1/RQ2/RQ3）。
- **性质/规约 oracle（PGFuzz 式 MTL）— 已建成、wave-1 = 干净 negative** ✓（可报）：wind+physics 无戏剧性行为类差分；指向估计污染轴。
- **变形/不变性 oracle — 上行选项（便宜，复用 harness）**：场景旋转/镜像 → 响应应相应变换；经典对称由构造、神经破对称 = NN-specific bug。**注意：切换区 campaign 用的是差分/严重度 oracle，_不是_变形 oracle；变形 oracle 仍未做**，可作拓宽失效_类型_的上行。
- **鲁棒性/平滑性 oracle**：搜神经局部非 Lipschitz；离线版直接探策略函数。stretch。
- **更强参照差分**（MPC/可达性认证）：A 路线已有轻量版。stretch。

**§6 方向性（v6 更新）**：wind+physics 稳态已证 negative；切换瞬态已由差分/严重度 oracle 拿到决定性结果。**估计污染（wave-2）是 A 档里真正未试的高产候选、也是"拓宽到非切换轴"的关键**，但最贵、可能也 negative（上行选项 A）。变形 oracle 打对称破缺、便宜、靶区（非单调区）已知（上行选项 B）。

---

## 7. Oracle 排序（按可行性 + 可信性，v6 状态）

1. **灾难性差分（现有）** — 高/高。**A 路线 + 切换区 campaign 双验证；已答 RQ1/RQ2/RQ3。**
2. **性质/规约（PGFuzz 式 MTL）** — 中高/高。**已实现 + wave-1 干净 negative（wind+physics）；估计污染轴未试（上行 A）。**
3. **变形/对称（equivariance）** — 高/高。复用 harness、不用 EKF2/Step C，靶区（非单调区）已知。**拓宽失效类型的便宜上行（B）。未做。**
4. **鲁棒性/平滑（离线对抗敏感度）** — 高/中高。离线探雅可比便宜。stretch。
5. **更强参照差分（MPC/可达性认证）** — 最高/最低。stretch；A 路线有轻量版。

---

## 8. 当前决策 + 下一步（战略岔口已重新洗牌）

- **A 路线：已锁 + v6 多种子重新确认**（3/3、3/3、3/3、8/9）。
- **B 路线-wave-1：干净 negative + assay 拒假阳（wind+physics）。**
- **切换区严重度 campaign：成功——RQ1 系统化、RQ2（效率框架）、RQ3（高维带洞边界）。已 commit `118d58f`。**
- **论文脊柱已完整**：可靠差分 oracle（方法）+ 系统化灾难差分（RQ1）+ 制导效率（RQ2）+ 高维带洞边界（RQ3）+ 全程诚实纪律 + wave-1 诚实 negative + pair5 概率性锚点。**不做 wave-2 这篇也完整。**

**重新洗牌的战略岔口（本版倾向"先写作"，但由用户定）**：
- **(路径 1) 锁范围 + 写作（推荐先做）**：claim = 切换瞬态灾难差分 + 可靠 oracle 方法学 + 高维带洞边界刻画；重心全转写论文。**因为论文正文仍停在 M0/M1 旧稿（RAPTOR-only），这是当前最大的未做块。** 最快出可投稿。
- **(路径 2) 先搏上行再写**：
  - **(A) wave-2 估计污染**：Step C（setpoint 锁 sim 时间，恢复并行/高 speed）→ EKF2 6 文件 3-way 整理 shim drift → genome 加 state-contam 变量 → campaign 找 robust 绝对违反。**把主张从"切换瞬态"拓宽到"非切换轴也失效"，堵"这是学习型弱点还是交接集成问题"的质疑。** 最贵、可能 negative。
  - **(B) 变形 oracle（非单调区）**：便宜、复用 harness，拿一个不同_类型_（对称破缺）的 NN-specific 结果。
- **两处审稿攻击面（写作时主动处理）**：**RQ2 的 3/3 打平**（用效率/照亮/一致性框架化解，别升级成 bug 数）；**全部 SIH-only、无真机、无 ArduPilot**（RQ4 延后，threats 主动认，SE 接受 replay+scoping）。
- **已定口径**：灾难类 primary = `strict_s0_vs_s3 ≥2/3`（3/3 另报）；灾难类以 severity+符号为门、连续 ρ 只作诊断；两层 finding + 触发性质确认（行为类）；invalid 排除不进象限。
- **机器约束**：N=1 单机一次只跑一个 SITL 工作流——campaign 占机时其他 SITL 验证须错开（代码可并行）。≈ 22 evals/h @ speed 1.25。
- **悬而未决**：工具名（`[TOOL]`，候选 TwinFuzz/CtrlDiff/OracleSwap）；目标会议已定 SE 大类（ICSE/FSE/ASE/ISSTA）但具体未定 + 窗口；公开仓同步（见 §9）；何时引入真板解锁 RQ4；`config/m2_primary_bugs/` 是否入库（若含确认差分的 θ 配置，应作可复现 artifact 跟踪，见 §9）。

---

## 9. 环境 / 复现 / 工程约定（给 agent）

- **容器入口**：`sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<name> ./docker/run.sh bash -lc "..."'`。镜像 `uav_sf:phase1`。常规路径用 `sg docker`、避免 sudo。坑见 `AGENT.md`。
- **PX4**：固定 `3042f906`，源码 `external/PX4-Autopilot`（gitignored）。board `px4_sitl_mcnn_sih` 同编 mc_raptor 但 RAPTOR 不启动 → **mode-23 飞行须正面 ID 确认**（已自动化为每 eval 硬闸）。
- **仓库约定**：`external/PX4-Autopilot`、`ros2_ws` gitignore → PX4 改动以 **tracked patch/overlay + installer** 入库；证据落 `docs/`。
- **公开仓同步（重要 gap）**：**公开 GitHub 仍停在 RAPTOR 线（M2b-1，null 结果）**，未含 A 路线灾难差分、mc_nn GATE、B 路线性质 oracle、wave-1、切换区 campaign。若拿仓当 artifact（SE 有 artifact 评审轨），需把这些 + 报告推上公开 main。本地已有 `118d58f`（切换区 campaign）。
- **git 卫生（重要）**：`*.ulg` 已 gitignore、保持 untracked。ulog/run 目录/checkpoint（`runs/` 已 ignore）留本地，commit 只含代码+报告。验证：`py_compile`/`unittest`/`bash -n`/`jq empty`/`git diff --check`(+`--cached`)。**未解**：`config/m2_primary_bugs/` 当前 untracked——若含确认差分的 θ 配置，**应作复现 artifact 入库**（区别于 ulog）。
- **吞吐 / 并行（硬约束）**：**N=1 @ `PX4_SIM_SPEED_FACTOR=1.25` ≈ 22–23 evals/h**（切换区 campaign 实测 22.1、密扫 20.6）。**并行不可用**：N≥2 串扰（端口/tmp/ulog/run-root 全隔离 + CPU pinning 仍越 strict 抖动 gate）。**根因 = offboard setpoint 是 wall-clock ROS timer、未锁 lockstep sim**（`m1_offboard_task.py` 的 `create_timer`）。恢复路径（Step C，上行 A 的第一步）：setpoint 锁 sim 时间 / lockstep 等 setpoint，再重测 N≥2 与 speed 2.0+，改后须 route-A + 锚点回归。
- **SIH 固有抖动 + 判据（v6 定形）**：固定 `(θ,seed)` 串行重跑 ρ 也抖（P7 band 0.224、P5 ~0.28、P1/P4/P6 ~0.01；标定 `P1=0.0128 / P2=0.0935`）。**关键：该 jitter 带仅适用于近无扰动轨迹；深违反/强切换区连续 ρ 抖动远大于此，故灾难类复现/确认一律以离散 severity + violation 符号为门、连续 ρ 只作诊断。** 行为类沿用越抖动 margin + 触发性质确认。
- **patch drift（绑 wave-2 / 上行 A）**：`patches/px4/m2b_state_shim.patch` 正反向 apply 均失败 = drift（EKF2 + vehicle_angular_velocity 6 文件，3-way 重贴）。**不影响纯 offboard/groundtruth/ulog-重分析轮次**（wave-1、切换区 campaign 均此类）；**走 shim 注入（估计污染）前须先整理。**
- **仿真器**：SIH 为主（headless/lockstep；**但非 bit-exact**，故多种子 + 严重度纪律）；Gazebo 仅可视化/电机故障（SIH 故障支持未验证）。
- **关键脚本**：
  - 任务/比较：`m1_offboard_task.py`（**当前 wall-clock 计时**）、`m1_metrics.py`+`m1_compare.py`（四象限 + 差分包装 + 两层 finding，primary 仅 strict）。
  - **B 路线 / campaign**：`property_oracle.py`（P1–P7 ρ + S0–S4 + mcnn ID + **state-trigger 窗口已按 task elapsed 对齐**）、`theta_genome.py`（genome + `steady_combo` + **`route-a-switching` 按可达性重定义** + `route_a_profile_for()` clamp 后重算 trigger rate）、`property_fitness.py`（gap fitness + `--target-properties` + **灾难类 gate 要求去污染后经典 S0**）、`validity_automation.py`（去污染=截断 control window 重算 severity + identity + 抖动 margin）、`m2_map_elites.py`（搜索驱动 + preset `route-a-catastrophic`）、`campaign_runner.py`（N=1 可续 + guided/random/grid + **primary/confirmation = severity-triggered `strict_s0_vs_s3`**）、`route_a_anchor_regression.py`（**新增，多种子 severity+符号闸**）、`wave1_windphysics_report.py`（wave-1 报告）。
  - A 路线：`fuzz1c_severity_scan.py`（`SCAN_CASES` 可精确重建 anchor θ）、`fuzz1c_decontam_analyze.py`、`mcnn_gate3_position_error_probe.py` 等。
- **关键报告/标定**：`oracle_calibration.md`、`wave1_windphysics_20260627.md`、**`switch_severity_campaign_20260629.md`（切换区 campaign 完整结果）**；A 路线 `fuzz1c_severity_20260625.md`、`fuzz1c_decontam_20260625.md`。
- **最近 commit**（新→旧）：**`118d58f`（切换区严重度 campaign：severity 目标 fitness + severity-triggered primary + `route-a-switching` 可达性修正 + state-trigger 窗口对齐 + 三臂 RQ2 + 密扫 RQ3 + 多种子 anchor 回归）**｜`659c8da`(组合 steady genome)、`343828e`(可续 campaign runner)、`8217025`(有效性自动化)、`776c947`(并行恢复)、`3d999af`(并行 profiling)、`ab50cce`(2.3 冒烟)、`4afb191`(2.2 差分 fitness)、`ab86b5b`(2.1 genome + P5)、`2e7b6b7`(Tier 0 性质 oracle)｜A 路线：`65240a5`、`301f564`、`345d2c6`、`4685b96`、`a8dd59b`、`b0121ee`。

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
