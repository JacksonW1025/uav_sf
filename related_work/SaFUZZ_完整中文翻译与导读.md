# 《揭示网络物理系统状态转换中的失效：一种应用于 sUAS 的模糊测试方法》完整中文翻译与导读

> 原题：*Uncovering Failures in Cyber-Physical System State Transitions: A Fuzzing-Based Approach Applied to sUAS*
> 作者：Theodore Chambers、Arturo Miguel Russell Bernal、Michael Vierhauser、Jane Cleland-Huang
> 作者单位：Theodore Chambers、Arturo Miguel Russell Bernal 与 Jane Cleland-Huang——美国印第安纳州圣母大学；Michael Vierhauser——奥地利因斯布鲁克大学
> 作者联系方式：tchambe2@nd.edu、arussel8@nd.edu、Michael.Vierhauser@uibk.ac.at、janehuang@nd.edu
> 版本：ICSE 2026 录用论文的作者接受稿，arXiv:2601.05449v1（2026-01-09）
> 原文 PDF：[项目中的论文原件](./Uncovering_Failures_in_CyberPhysical_System_State_Transitions_A_FuzzingBased_Approach_Applied_to_sUAS_6a504e964bee699ac41db07b_main.pdf)

> 原文声明：这是已被 ICSE 2026 接收论文的作者接受稿；最终出版版本可能有所不同。

## 阅读说明

本文档包含论文正文、列表、表格、图注、研究发现、局限、结论和书目信息的完整中文翻译。为方便与 PX4、Drone Response 和实验代码对照，`OFFBOARD`、`POSCTL`、`STABILIZED`、`LAND`、`RTL` 等程序枚举名保留英文；首次出现时解释其含义。图中无法直接替换的英文，以“图内文字译注”完整转述。参考文献的作者、题名、出处、页码和链接按原文保留，以免误改可检索的书目信息。

每个主要章节后另有“导读”。导读不是原文，而是帮助理解论文论证结构、证据力度以及它与当前研究叙事关系的阅读笔记。

### 核心术语

| 原文 | 本文译法 | 含义 |
|---|---|---|
| small Uncrewed Aerial System (sUAS) | 小型无人航空系统 | 包括飞行器、飞控、机载自治软件及相关控制设施 |
| application state | 应用层状态 | 任务程序的状态，如起飞、飞向航点、悬停、着陆 |
| flight-controller mode | 飞控模式 | PX4 等飞控内部的控制模式 |
| failsafe | 故障保护（failsafe） | 在失联、低电量、越界等异常下触发的安全行为 |
| control handoff | 控制权交接 | 自主系统与人类操作员之间的控制权切换 |
| test oracle | 测试判定器（Oracle） | 判断一个测试无效、通过或失败的规则 |
| Fuzz Specification (FSpec) | 模糊测试规格 | 定义状态、模式、事件、环境和时序组合的测试空间 |
| Fault Tree | 故障树 | 用逻辑条件表示失效成因组合的树 |
| minimum cut set | 最小割集 | 足以导致顶层失效的最小条件组合 |
| system under test (SuT) | 被测系统 | 本文中为 Drone Response |

## 建议的三遍阅读法

1. 第一遍只读摘要、图 2、表 4、表 5和三段 RQ Findings：先弄清方法输入、输出以及实验证据。
2. 第二遍精读第 3 节：重点看 FSpec、判定树、聚类和故障树是怎样串成自动化流水线的。
3. 第三遍带着研究问题读第 5、6 节：区分“发现了真实软件失效”“发现了模拟器失真”和“判定器自身出错”这三类结果。

---

# 论文中文译文

## 摘要

随着小型无人航空系统（sUAS）越来越多地部署在多样化、且往往具有安全关键性的环境中，我们需要在不同条件下，对其机载决策逻辑进行严格验证。本文提出 **SaFUZZ**：一条具备状态感知能力的模糊测试流水线，用于验证 sUAS 应用在不同时间条件和环境扰动下，与状态转换、自动故障保护以及人类操作员交互有关的核心行为。

我们创建模糊测试规格来检测行为偏差，随后动态生成相应的故障树，将造成失效的状态、模式和环境因素可视化，从而帮助项目利益相关者分析失效并识别其根本原因。我们在一个真实世界的 sUAS 系统上验证了 SaFUZZ，并发现了该系统开发团队此前未检测到的多个失效点。模糊测试首先在高保真仿真环境中进行，之后又在真实世界的野外测试场景中，用实体 sUAS 验证测试结果。研究结果表明，SaFUZZ 能够以一种实用且可扩展的方式，揭示真实 sUAS 应用中多种状态转换失效。

**关键词：** 模糊测试；网络物理系统；sUAS；故障树

### 摘要导读

摘要给出的完整因果链是：

`语义化测试规格 → 仿真执行 → 行为判定 → 失败聚类 → 故障树 → 实机复现`

SaFUZZ 的重点不是让飞行轨迹变得“更随机”，而是系统地组合具有任务语义的应用状态、飞控模式、人工接管事件、环境扰动和事件时机。论文的主要价值也不只在“找到 bug”，而在于把失败条件压缩成开发人员能够理解的故障树。

## 1 引言

网络物理系统（Cyber-Physical Systems，CPS）正越来越多地被部署到交通、医疗和机器人等领域 [13, 27, 34, 40]。这些系统在物理世界中运行，面对的环境条件可能是动态且不确定的。为管理系统固有的复杂性，CPS 通常使用状态机来管理模式转换，并帮助确保运行行为可预测 [4, 8, 56]。

小型无人航空系统是一个迅速发展的 CPS 类别，应用范围广泛，包括搜索与救援 [2, 28]、环境监测、基础设施巡检 [44]、监视和灾害响应 [5]。sUAS 的状态机利用飞行控制器（亦称自动驾驶仪）的底层服务，实现任务层能力 [7, 49]。这两个层级通过 MAVLink [24] 等协议接口相互作用，由此产生隐式依赖和复杂交互。

更进一步，人类操作员还可以通过手持遥控器（RC）覆盖自动任务。例如，操作员可以请求切换模式，从而触发返航（Return-to-Launch，RTL）等故障保护机制。系统的最终行为由多个运行层级中的状态机组合而成；应用逻辑、飞控固件和人类输入都可能影响系统状态。每个层级都基于不同的假设，具有不同的时间约束，也会产生各自的失效模式。随着这些相互作用的状态机变得越来越复杂，对它们进行穷尽式验证也越来越困难，从而增加了潜在设计缺陷、非预期交互或边界情形处理不足的风险。

此前发生的多起无人机事故已经暴露了与复杂状态行为、故障保护逻辑和人机交互有关的问题。例如，2022 年，一名商业无人机飞手据报道在切换模式后因连接问题失去对 sUAS 的控制，随后撞上一架正在执行山火灭火任务的有人驾驶飞机 [29]。类似地，在 2020 年的一起事故中，一架 sUAS 收到了不可靠的 GPS/罗盘信号，系统因而自动退出位置控制模式，进入能力降级的姿态保持模式；操作员起初并未意识到模式已经变化，最终失去控制并坠机 [33]。

在这两起事故中，促成事故的因素都包括：内部状态转换缺乏足够可见性、模式切换失败，以及人类干预延迟或无效。它们共同说明，我们需要系统地验证应用层逻辑与飞控固件的行为，包括两者组合之后，在信号丢失、传感器失效或操作员困惑等不利条件下如何响应。形式化验证可以提供很强的行为保证，但对于这种复杂且持续演化的软件系统，当前仍只能应用于范围明确的组件，对完整系统进行验证仍不现实 [6, 11]。

本研究通过对 sUAS 状态机进行**语义层面的模糊测试**来填补这一空白。我们提出 SaFUZZ——一个新颖的、基于模糊测试的框架，用于验证跨层级和多主体之间的交互，尤其关注模式转换、故障保护行为以及控制权交接附近出现的危险。

SaFUZZ 与基于代码的模糊测试方法 [9, 36, 41, 59] 不同。它不变异底层输入，而是从真实任务中提取事件，系统地生成具有语义意义的事件序列，并改变事件时机和可能影响系统行为的环境条件。这样既能探索预期事件，也能探索非预期事件的影响，从而发现由下列问题引入的细微故障：

- 缺失的状态转换；
- 不完整的配置；
- 非预期的时序交互；
- 应用、飞控和人类操作员之间彼此不一致的假设。

这些测试在贴近真实世界的条件下执行。

本文对研究和实践作出以下贡献：

- 我们提出 SaFUZZ：一个将行为语义纳入测试的策略性模糊测试框架。它分析系统级状态转换和事件序列，从而识别转换危险和不安全的状态组合（见第 3 节）。
- 我们提供一种可复用的实验方法，用于诱发和分析应用层状态机与飞控状态机交互所产生的转换危险，包括模式转换、故障保护和控制权交接。SaFUZZ 能够系统探索不安全状态组合，并帮助揭示常见验证技术可能失效的条件（见第 3 节）。
- 我们在一个具有代表性的自主 sUAS 平台上展示 SaFUZZ 的适用性，通过危险驱动的自动测试生成，揭示故障保护逻辑和跨层交互中此前没有记录的薄弱点（见第 4 节）。
- 我们提供结构化研究制品，包括用于分类测试结果的决策树判定器，以及自动生成的故障树。补充材料见：<https://github.com/SAREC-Lab/saFUZZ_ICSE26>。

论文余下部分安排如下：第 2 节简要介绍 sUAS 系统、飞行控制器以及本研究的动机示例；第 3 节介绍 SaFUZZ 框架和自动化流水线的各个步骤；第 4 节说明评估设置，用于考察可行性、失效检测和测试自动化；第 5 节报告三个研究问题的结果；第 6 节讨论有效性威胁；第 7 节介绍相关工作；第 8 节给出结论。

### 第 1 节导读

作者把待测对象定义为一个**组合系统**，而不是一台孤立飞控：

`应用状态机 × PX4 模式机 × 人类操作 × 环境 × 时序`

因此，这篇论文所谓的“状态转换失效”不只是某条边无法走通，也包括两个层级都各自“正确”、组合后却不安全的情况。时序被明确列为输入维度，这一点非常重要：同一个 `POSCTL` 指令，在起飞早期和进入 `OFFBOARD` 之后可能得到完全不同的结果。

## 2 sUAS 的分层架构

现代 sUAS 系统通常采用分层架构，将实时控制、飞行行为、通信和任务层决策分离。每一层负责特定职责，不同层级的状态机对应不同的自主范围和抽象层次。

在最底层，飞行控制器直接与传感器和执行器连接，并运行紧密耦合的控制回路，例如角速度稳定和姿态稳定。PX4 [49] 和 ArduPilot [7] 是使用最广泛的两种开源无人机飞控软件平台。它们支持多种空中载具——固定翼、多旋翼和垂直起降飞行器（VTOL）——也支持无人地面车辆（UGV）。两者具备相似能力，都会强制执行起飞前解锁检查、紧急上锁等硬性安全约束，并提供严格的实时保证。

这一层实时执行底层控制命令。例如，作为飞控自动驾驶仪的一部分，PX4 定义了一套管理高层飞行模式的有限状态机，其中包括：

- `STABILIZED`：增稳/姿态稳定模式；
- `POSCTL`：位置控制模式，通常用于人工接管；
- `OFFBOARD`：机外控制模式，由外部自治程序持续发送设定值；
- `RTL`：返航模式；
- `LAND`：着陆模式 [48]。

每种模式都会允许或限制某些控制输入；模式之间的转换由操作员命令、自主触发器或故障保护事件触发。该状态机通过施加运行约束，保证转换有效且安全。

**图 1：** 一个简单任务中的应用层状态和底层 PX4 模式。颜色表示控制主体：应用程序为蓝色、PX4 为橙色、人类为绿色。

**图内文字译注：** 图中沿任务执行过程展示了应用状态（例如 `Takeoff`、`FlyToWaypoint`）与 PX4 模式的组合关系。正常自主任务主要运行在 `OFFBOARD`，由应用程序控制；PX4 可以进入自身管理的模式；人类也可以切换到 `POSCTL` 接管任务。

sUAS 应用通常通过 MAVLink [24] 通信协议与自动驾驶仪交互，并在 PX4 的 `OFFBOARD` 模式下，以高频率向飞控发送位置、速度或姿态设定值。这支持避障和路径跟随等精细机动。与此同时，应用程序通常还实现自己的任务层状态机。该状态机依赖飞控内部状态机，并与之组合。

图 1 展示了一个简单任务中 PX4 与应用层状态的相互作用。每个节点同时包含一个应用层状态（例如 `FlyToWaypoint`）和一个 PX4 模式（例如 `OFFBOARD`）。蓝色状态由应用层控制，橙色状态由 PX4 控制；绿色状态则表示人类操作员已经介入任务，并切换到人工飞行模式 `POSCTL`。

图中没有画出应用层自己的故障保护，但应用程序也可以实现这类机制。例如，开发人员可以将 PX4 层的失联故障保护设置为丢失信号 60 秒后触发，同时把应用层故障保护设置为丢失信号 20 秒后触发。这样，应用程序便有机会在 PX4 层故障保护启动之前恢复通信或调整任务。

应用层状态机和自动驾驶仪状态机之间的交互可能非常复杂，错误可以在多个层次上产生 [55]。状态配置和状态转换中的失效可能触发非预期行为，例如任务中止 [53]。为处理罗盘干扰、信号丢失等意外情况而设计的故障保护机制，如果行为不正确，也可能引入新的失效。人类操作员也可能由于误解事件、响应延迟或发出错误命令而实施不安全干预。最后，两个各自正确的功能以非预期方式交互时，还会产生功能交互失效。

这类交互通常发生在应急状态或时间紧迫的任务状态中，因此可能迅速产生不可恢复的行为，造成更高安全风险；同时，它们也尤其难以在测试中提前预见或稳定复现。

### 第 2 节导读

这一节建立了论文最关键的系统模型：`OFFBOARD` 并不等同于应用状态。`TAKEOFF/OFFBOARD` 与 `HOVERING/OFFBOARD` 在飞控看来可能处于同一模式，但应用语义不同；反过来，一个应用状态的内部又可能短暂经过 `STABILIZED`、`OFFBOARD` 等多个 PX4 模式。SaFUZZ 正是要测试这些“组合状态”附近的行为。

## 3 SaFUZZ 框架

为应对上述挑战，我们提出 SaFUZZ：一条用于验证 sUAS 应用状态行为与状态转换的自动化模糊测试流水线。我们按照设计科学（Design Science）方法 [62]，通过问题分析、设计、仿真、实现和评估的迭代循环开发 SaFUZZ。

如图 2 所示，SaFUZZ 包含两个主要阶段和八个步骤：

- **阶段 1：危险分析与测试规格**
  1. 执行危险分析；
  2. 定义模糊测试规格；
  3. 指定测试任务；
  4. 创建测试判定器。
- **阶段 2：测试执行与根因分析**
  5. 执行测试用例；
  6. 识别失效；
  7. 生成最小故障树；
  8. 执行失效/根因分析。

在阶段 1 中，项目利益相关者先执行危险分析（步骤 1），然后构建作为后续测试基础的模糊测试规格（步骤 2–4）。在阶段 2 中，系统自动执行并分析测试，并为每个失败测试动态生成故障树（步骤 5–7）。最后，故障树交给项目利益相关者，用于失效分析（步骤 8）。

**图 2：** SaFUZZ 的高层概览，展示前期设置（阶段 1）和自动化流水线（阶段 2）。

**图内文字译注：** 阶段 1 的输入主要来自领域专家/sUAS 开发者，输出危险分析、FSpec、任务规格和决策树判定器。阶段 2 中，配置生成器产生测试配置，执行器驱动被测系统在仿真中完成任务，存储模块记录任务执行剖面，分析器使用决策树和结果聚类识别失败、生成故障树；之后可进入实地测试和人工根因分析。

### 3.1 阶段 1：危险分析与规格定义

#### 步骤 1——危险分析

我们采用危险分析方法来确定测试过程的重点 [30, 46]。图 3 给出一棵不完整的危险树，其中探索了与状态转换、故障保护动作和油门位置有关的四类失效。

第一类危险是任何状态机都必须面对的基本问题（H1）：必须验证所有转换都能正确执行。第二类危险对应安全关键的故障保护机制（H2）：它们必须能够处理侵入地理围栏、低电量和信号丢失等常见故障。第三类表示与人为错误有关的一族危险，这里以操作员将遥控器油门置于潜在危险位置为例（H3）。最后，我们通过更广泛的一组模糊测试探索功能交互错误（H4）。

**图 3：** 部分危险树，展示四类具有代表性的 sUAS 失效：

- H1：状态转换失效；
  - H1.1：缺失转换；
  - H1.2：非期望转换；
  - H1.3：无法转换到人工控制。
- H2：故障保护动作失效；
  - H2.1：地理围栏失效；
  - H2.2：低电量失效；
  - H2.3：信号丢失失效。
- H3：人机交互失效，这里以人工接管时油门位置错误为例；
  - H3.1：接管时油门过高；
  - H3.2：接管时油门过低。
- H4：功能交互失效。

图中的带注释节点还给出每类危险的语义模糊测试示例：

- 状态转换：从所有 `OFFBOARD` 应用状态向人工控制进行转换测试；
- 故障保护激活：从所有 `OFFBOARD` 应用状态测试地理围栏动作与人工控制的交互；
- 人类错误放置油门：从所有 `OFFBOARD` 状态切换到人工控制时，测试不同油门位置；
- 功能交互：执行由随机顺序转换序列组成的模糊测试。

图中危险类型并非穷尽。

#### 步骤 2——模糊测试规格

领域专家依据已识别的危险，定义相应的模糊测试规格（Fuzz Specification，FSpec）。每份 FSpec 通过列出飞控模式、应用状态、环境因素、注入动作和时序的可能组合，定义一个测试空间。

下面的示例代表危险 H1。它只在有效的 PX4—应用状态组合中，定义 RC 输入事件、时序变化、油门位置及其他环境因素，使 SaFUZZ 能检查状态转换是否按预期发生。¹

```json
{
  "FROM_PX4_modes": ["OFFBOARD", "LAND"],
  "FROM_APP_states": [
    "TAKEOFF",
    "FLYING_TO_WAYPOINT",
    "HOVERING",
    "LANDING",
    "DISARMING"
  ],
  "RC_INPUT_EVENTS": ["ALTCTL", "POSCTL", "STABILIZED"],
  "ENVIRONMENT": {
    "transition_delay": {
      "bands": {
        "short":  {"min": 50,  "max": 200},
        "medium": {"min": 200, "max": 600},
        "long":   {"min": 600, "max": 1200}
      }
    },
    "throttle": ["mid"],
    "geofence": ["none"],
    "wind": ["none"],
    "GPS": ["none"],
    "COMPASS_INTERFERENCE": ["none"]
  },
  "MISSION_CONTEXT": ["Flight plan A"],
  "CONSTRAINTS": {
    "REQUIRES_PX4_MODE": {
      "OFFBOARD": [
        "TAKEOFF",
        "FLYING_TO_WAYPOINT*",
        "HOVERING"
      ],
      "LAND": ["LANDING", "DISARMING"]
    }
  }
}
```

**列表 1：** 模糊测试规格 1（FSpec-1）：自主飞行期间的模式转换。该规格针对危险 H1。

¹ FSpec 的完整词汇表见论文补充材料：<https://github.com/SAREC-Lab/saFUZZ_ICSE26>。

#### 步骤 3——指定测试任务

任务为 FSpec 生成的测试提供执行上下文。它定义飞行路径和要完成的机动，保证 sUAS 会自然经过到达目标测试上下文所需的状态和模式。

当系统观测到目标上下文——即当前状态、运行模式和环境条件符合指定标准——便启动计时器，并在规定延迟后注入指定的模式转换。状态、模式、环境上下文、时序延迟和被注入的模式转换共同定义由 FSpec 生成、并在执行阶段被测试的具体测试实例。

换言之，如果测试要求从 `FlyToWaypoint/OFFBOARD` 组合触发事件，那么飞行过程中必须实际出现这个状态/模式组合，该测试才有效。类似地，与地理围栏动作等环境因素有关的测试，也必须包含会穿越或接近地理围栏的飞行路径。

#### 步骤 4——创建测试判定器

SaFUZZ 需要一个测试判定器来评价每次测试的结果。先前工作曾使用简单逻辑验证 sUAS 测试结果，例如检查 sUAS 是否在固定时间内完成任务、是否紧密遵循计划航线 [14, 47]。但这种方法不足以验证状态转换和模式切换的正确行为。

例如，如果测试要验证飞行期间能否激活 `POSCTL` 模式，那么 sUAS 若继续按计划完成整个自主任务，反而说明发生了错误；正确行为应该是退出自主任务，进入 `POSCTL` 下的悬停状态。

为了完全自动化整条流水线，作者把测试判定器构造成决策树。决策树通过一套引导式过程，将结果分成三类：

1. **无效测试（Invalid）**：目标条件从未满足，即测试用例本身存在问题；或者延迟过长，导致事件在错误的上下文中执行。
2. **通过测试（Pass）**：测试按计划执行，全部成功条件都得到满足。
3. **失败测试（Fail）**：测试按计划执行，但至少有一个成功条件未满足。

如图 4 所示，决策树编码状态转换、模式切换和故障保护行为在系统层面的后置条件，并依据这些语义区分无效、通过和失败测试。由于测试结果是在被测系统层面定义的，同一个决策树判定器可以统一应用于某份 FSpec 生成的所有测试。

除了构造决策树之外，还需要识别分析过程所需的输入数据，并确保系统已经插桩，能够收集和提供这些数据。设计、测试和不断改进决策树非常耗时，也需要大量领域知识。

**图 4：** 用于标记模糊测试结果的决策树分类器。节点检查任务失效谓词和人机交互条件，并将结果标记为成功、失败或无效。

**图内文字译注：** 决策树先检查测试前置条件是否曾被满足；若没有，则测试无效。若测试有效，则依次检查人工取消自主控制、情景意识丧失、紧急停机、切换 `LAND`、故障保护触发 `LAND/HOLD/RTL`、模式切换为 `LOITER/RTL` 等情况，并验证对应的后置条件，例如自主驾驶是否停用、是否在事件附近着陆、空中按下紧急停机后电机是否关闭、是否悬停、是否返航并在家点着陆。若不存在这些特殊情况，则检查任务是否在远离家点处结束、耗时是否显著过长或过短、是否显著偏离规划路径，由此得出飞行成功或失败。

### 3.2 阶段 2：测试执行与分析

SaFUZZ 的第二阶段自动完成模糊测试。下面使用 PX4 自动驾驶仪的模式名称说明各步骤。

#### 步骤 5——测试执行

SaFUZZ 接收一份 FSpec，然后迭代执行数百乃至数千个测试用例。每个测试包括：

- **环境设置：** 在测试前配置规格中定义的环境变量。例如设置地理围栏，和/或在仿真环境中初始化风参数、GPS 干扰和罗盘干扰。
- **状态选择：** 按照测试规格中的约束，选择一个有效的 PX4 模式及对应的应用层状态。
- **动作注入：** 随机选择一个控制动作（例如 `ALTCTL` 或 `POSCTL`），安排在选定状态期间执行。
- **时序配置：** 选择一个转换延迟区间——短、中或长——从对应区间中采样一个毫秒级延迟，并在发送动作前等待该时长。
- **系统配置：** 使用规定的 `MISSION_CONTEXT`（例如预定义飞行计划）初始化 sUAS，并应用与模式相关的设置（例如地理围栏行为）。
- **测试执行：** 在 Gazebo [45] 等高保真仿真环境中启动测试飞行。系统持续监控目标模式、状态和环境因素组合的**第一次出现**，一旦检测到该组合，便按照配置的时序延迟注入控制动作。
- **监控与结果记录：** 测试执行期间，按照测试判定器的要求采集遥测和行为日志，并存入执行存储模块，以供后续分析。
- **环境重置：** 每个测试用例结束后，动态重置整个环境。

#### 步骤 6——失效识别

每次测试都会产生一份对应的 JSON 剖面，记录测试结果。失效识别结合决策树分类和基于聚类的异常检测，过程如下。

**失效用例识别：** 使用图 4 的决策树逻辑自动分析每个测试用例的结果。落在代表失败的节点上的结果会被标记为 `FAILED`。

**测试选择：** 模糊测试会产生许多相似测试，它们的结果彼此接近。因此，对每份 FSpec，SaFUZZ 选择其中的失败测试，将它们表示为特征向量后应用 K-means 聚类，并使用肘部法确定聚类数 \(K\) [19]。

每个测试 \(T_i\) 都带有结果标签 \(y_i\)，其中 \(y_i=1\) 表示测试违反了预期行为。聚类前，连续参数会被归一化，类别参数会被独热编码。簇 \(C_j\) 的同质性由簇内平方和（within-cluster sum of squares，WCSS）定义：

\[
\mathrm{WCSS}_j=\sum_{\mathbf{x}_i \in C_j}\left\|\mathbf{x}_i-\boldsymbol{\mu}_j\right\|^2
\]

其中，\(\boldsymbol{\mu}_j\) 是簇 \(C_j\) 的质心。这个指标表示簇内所有点到质心的欧氏距离平方之和。之后，SaFUZZ 从每个簇中选择离质心最近和最远的测试，进入下一步的初始分析。

#### 步骤 7——故障树生成与可视化

上一步聚类和分析能够识别单个失效，但很难直接从原始数据中看出这些失效背后的共性。因此，SaFUZZ 围绕选中的测试进行第二轮高度聚焦的模糊测试，再利用测试结果为每类失效生成故障树。步骤如下。

**执行附加模糊测试：** 围绕每个选中的失效用例执行更多测试，在多个时序区间覆盖有效的谓词组合。

**生成真值表：** 使用这些测试结果自动填充描述失效剖面的真值表；每一行对应一种唯一条件组合。例如，表 1 是针对“在 `TAKEOFF` 状态下切换到 `POSCTL`”的 20 次运行所生成的真值表。

**表 1：在不同时间区间内，从 `TAKEOFF` 切换到 `POSCTL` 的真值表（对应失效 F2）**

| 应用状态 | 模式切换 | 时间区间（ms） | 状态 | 失效率 |
|---|---:|---:|---:|---:|
| `TAKEOFF` | 不适用 | 不适用 | 0 | 0% |
| `TAKEOFF` | `POSCTL` | 50–1000（短） | 1 | 100% |
| `TAKEOFF` | `POSCTL` | 1000–5000（中） | 1 | 65% |
| `TAKEOFF` | `POSCTL` | 5000–10000（长） | 0 | 0% |

失效率表示至少出现一次失效的运行占比；测试状态 1 表示失败，0 表示通过。每个时间区间运行 20 次。

**表 2：考虑模式切换发生时的当前模式后，对失效 F2 的分解**

| 应用状态 | 当前模式 | 模式切换 | 状态 | 失效率 |
|---|---|---|---:|---:|
| `TAKEOFF` | `STABILIZED`† | `POSCTL` | 1 | 100% |
| `TAKEOFF` | `OFFBOARD` | `POSCTL` | 0 | 0% |

† 所有中等时间区间内的失败都发生在标准自动驾驶仪仍处于 `STABILIZED` 模式、而 `POSCTL` 被触发的时刻。

`TAKEOFF` 状态的正常行为是从 `STABILIZED` 模式开始，随后转换到 `OFFBOARD`。测试结果显示，只有 sUAS 已经进入 `OFFBOARD` 后，`POSCTL` 模式切换才会可靠成功（见表 2）。研究团队此前并不知道这一行为。通过分析真值表中的时序延迟，作者定位到了失效的根本原因。

**生成故障树：** 真值表完成后，SaFUZZ 使用一种受 Quine–McCluskey 布尔最小化方法 [51] 启发的算法，提取足以导致失效的谓词条件最小割集。与穷尽整个输入空间、查找全部素蕴含项的 Quine–McCluskey 方法不同，这里的算法直接作用于失败测试的子集，并且只考虑状态机约束所允许的**有效测试组合**。

故障树表示最可能导致失效的最小状态条件与环境条件合取式。换言之，它识别谓词组合的最小割集，指出一个失效簇中的根因条件。表 1 对应的故障树见图 6(a)。

#### 步骤 8——失效分析

最后，生成的故障树会交给开发人员和架构师等项目利益相关者，供其详细分析。每棵故障树主要有两种结果：

- **识别出的失效是假阳性。** 这通常意味着决策树有误。例如，作者曾在决策树检查向 `LOITER`（悬停）转换时遇到错误：对旋翼飞行器而言，PX4 会把 `AUTO.LOITER` 转换成行为相近的 `POSCTL`。如果没有正确考虑这一点，SaFUZZ 就会报告非预期模式错误。
- **故障树表示一个真实 bug。** 这通常会触发 bug 报告或新建 issue；也可能引发更深入的讨论，最终发现观测到的行为虽然错误，根源却是需求缺失。此外，还可以据此定义并执行新的 FSpec，把测试集中到已识别的故障上。

模糊测试很适合揭示其他方法难以发现的失效类别，但它不提供完备性保证，未发现的失效——即假阴性——仍可能存在。因此，为闭合反馈回路，今后在仿真或实地部署中观测到的任何非预期行为，都可以用于创建新的 FSpec，针对触发该行为的条件开展定向探索。

### 第 3 节导读

这一节要抓住四个容易混淆的点：

1. FSpec 不是一个具体测试，而是一个受约束的测试空间。
2. 任务规格负责把系统带到目标上下文，FSpec 负责决定在该上下文中注入什么。
3. 决策树是结果判定器，不是测试生成器；它本身也可能错，并导致假阳性。
4. 聚类和故障树不是独立找 bug 的算法。决策树先找出失败，聚类再减少重复案例，聚焦复测产生真值表，最后才从真值表中提取最小割集。

所以，SaFUZZ 的“自动化”建立在大量人工领域知识之上：危险树、FSpec、任务路径和初始决策树都需要专家构造。自动的是大规模组合执行、结果归类和故障条件压缩。

## 4 评估 SaFUZZ

为评估 SaFUZZ 的有效性，作者使用 **Drone Response** [52] 作为被测系统。Drone Response 是其自主 sUAS 研究计划的一部分，已经开发八年（例如 [3, 15, 17, 18, 31]）。该平台由作者所在研究团队开发，并得到一支小型专业软件工程团队的支持；团队通常在任一时间有两到三名工程师。

Drone Response 是一个多 sUAS 管理与控制系统，采用模块化架构，包括：

- 可配置的任务规划器；
- 集中式地面控制站；
- 用于实时自治和感知的机载计算能力。

系统同时支持 PX4 和 ArduPilot 飞行栈，因此能够集成不同机架。任务由一套细致的运行状态机编排。状态机管理关键任务阶段，包括飞行前解锁检查、自主起飞、沿不同轨迹进行航点导航、稳定悬停、着陆，以及任务完成后的安全上锁流程。

作者使用 Drone Response 的一个 2024 年 1 月分支作为真实世界试验台，在图 5 所示的 PX4 sUAS 上部署，并围绕以下三个研究问题评价 SaFUZZ 的有效性、可扩展性和实际效用。

**RQ1：SaFUZZ 能在多大程度上识别真实 sUAS 系统中此前未知的行为失效？**
这个问题考察框架能否有效检测并分类被测系统中的失效。对于每类失效，作者识别潜在缓解措施，例如修改代码、分析需求或更新决策树。

**RQ2：SaFUZZ 检测到的转换相关错误，与开发团队长期以来识别出的错误有多一致？**
作者详细分析 2024 年 1 月分支中存在的模式和状态转换错误，并将 SaFUZZ 找到的错误与 Drone Response 开发团队在正常测试过程中、18 个月内找到的错误比较。原文此处括号写作“2024 年 1 月—2024 年 7 月”，但第 5.2 节明确说明实验区间是 2024 年 1 月至 2025 年 7 月；前者应为笔误。

**RQ3：SaFUZZ 在仿真中识别的失效，有多大程度能在真实世界飞行测试中复现？**
这一问题评价仿真失效与实体飞行中实际表现之间的一致性。在安全且可行的情况下，作者在真实世界重复测试，判断真实行为是否与 SaFUZZ 的发现一致。

**图 5：** 实地测试使用的一架配备 PX4 的六旋翼无人机。机上 Jetson Xavier NX 运行 Drone Response 自治软件。

### 4.1 SaFUZZ 实验原型

作者为本研究使用 Python 3.11.0 开发了一个完全可执行的 SaFUZZ 原型，代码总量约 4,000 行。原型分成四个模块：

1. **Fuzzer：** 根据 FSpec 创建测试配置；
2. **Executor：** 在仿真器中执行测试；
3. **Storage：** 管理仿真结果；
4. **Analyzer：** 执行聚类、决策树分析和故障树生成。

每个模块都部署在 Docker 容器中。容器提供 Drone Response 自治系统在 Gazebo 中的高保真数字复现，保证每个测试都在干净、版本固定的环境中执行，测试之间自动拆除环境，并且可以并行运行数十项测试。

启动一批测试时，Fuzzer 解析 FSpec，读取参数向量并交给 Executor。Executor 是协调模糊测试执行的多线程系统。它将规格序列化为 MAVROS [26] 消息，模拟真实遥控器摇杆输入。系统通过 MQTT 向自动驾驶仪容器发布 RC 通道覆盖和航点命令，从而使用与实体飞控实地运行相似的命令接口。

Executor 还能把规格中规定的风、GPS 扰动、罗盘干扰和 IMU（惯性测量单元）噪声等环境条件动态注入仿真环境，并控制时序延迟等其他模糊测试变量。

每次测试后，Analyzer 收集并解析原始日志，提取姿态偏差、路径跟踪偏差、故障保护激活、任务完成状态、异常标志和其他用于异常检测的相关飞行数据。

任务完成或检测到任务失败后，Executor 拆除全部容器，并把 Gazebo 重置到基础世界文件，使环境恢复默认初始状态。执行完一份 FSpec 后，所有测试结果被转换成真值表，Analyzer 再识别引发失效的最小割集。

### 4.2 应用 SaFUZZ 流程

作者按照图 2 所述步骤应用 SaFUZZ。

在阶段 1 的步骤 1 中，一位了解 Drone Response、具有八年 sUAS 工作经验的研究团队成员执行初步危险分析，生成图 3 的危险树。该分析并不追求穷尽，而是由既有文献中报告事故时常见的错误类型指导 [23, 46, 58, 60]。

在步骤 2 中，三位研究团队成员——均为本文共同作者——创建了表 3 的三份 FSpec。FSpec-1 已在列表 1 中介绍，另外两份规格见补充材料：

- FSpec-1 测试自主飞行期间由人类动作触发的简单模式转换，直接对应 H1，也涉及人类触发模式切换的 H3；
- FSpec-2 测试故障保护转换，对应 H2；
- FSpec-3 测试地理围栏与人类输入的交互，代表功能交互危险 H4。

在构造 FSpec 的同时，两位共同作者创建了三份不同的任务规格（步骤 3），分别为三份 FSpec 提供所需的状态/模式覆盖。

图 4 的决策树（步骤 4）依据研究团队自身领域知识和 PX4 文档 [48] 构建。它最初创建于 2024 年夏季；过去一年中，团队按照设计科学方法，在早期实验中不断迭代。初始构造约耗时 6 小时；在 SaFUZZ 产生假阳性后发现并完成的修订，另耗时 1–2 小时。

**表 3：用于验证 SaFUZZ 的三份 FSpec 摘要**

| 项目 | FSpec-1 | FSpec-2 | FSpec-3 |
|---|---|---|---|
| 概述 | 跨多个状态测试人工控制 | 在两个状态中测试故障保护动作 | 测试由地理围栏触发的故障保护动作 |
| PX4 模式 | `OFFBOARD`、`LAND` | `OFFBOARD` | `OFFBOARD` |
| 测试的应用状态 | `TAKEOFF`、`FLYING_TO_WAYPOINT`、`HOVERING`、`LANDING`、`DISARMING` | `FLYING_TO_WAYPOINT`、`HOVERING` | `FLYING_TO_WAYPOINT` |
| 模式/油门激活动作 | RC 输入：`ALTCTL`、`POSCTL`、`STABILIZED`、`THROTTLE_TOGGLED` | RC 输入：`AUTO.LOITER`、`AUTO.LAND`、`AUTO.RTL` | 地理围栏动作：`RTL`（加 `LAND`）、`LAND`、`WARNING`；RC 输入事件：`ALTCTL`、`POSCTL`、`STABILIZED`、`OFFBOARD` |
| 环境/上下文 | 延迟：短/中/长；油门：中/低；无地理围栏；无风、GPS 或罗盘扰动；飞行计划 A；约束 PX4 模式—应用状态映射 | 延迟：短/中；油门：中；无地理围栏；风、GPS、罗盘取无/低/中/高等配置；飞行计划 B | 延迟：短/中/长；油门：中；启用地理围栏，动作取 `WARN`、`RETURN`、`LAND`；无风、GPS 或罗盘扰动；飞行计划 C |
| 发现的失效 | F2、F8、F9 | F1、F5、F6、F10、F11 | F3、F4、F7 |

随后进入阶段 2，作者在被测系统上执行自动化流水线。SaFUZZ 原型为三份 FSpec 分别生成：

| FSpec | 生成测试数 | 原始运行中以 `FAILURE` 结束的数量 |
|---|---:|---:|
| FSpec-1 | 3,600 | 10 |
| FSpec-2 | 6,480 | 56 |
| FSpec-3 | 1,080 | 11 |
| **合计** | **11,160** | **77** |

运行环境为 Ubuntu 22.04.3 LTS，i9-11900 处理器、4.5 TB SSD、8 核、2.50 GHz 基础频率和 64.0 GiB 内存。三份 FSpec 总运行时间为 248 小时。

接着，作者应用步骤 6 和步骤 7：识别失效用例、生成故障树，并把每棵树约简成保证失效的最小谓词合取，即最小割集。最终得到 11 类失效（表 4），每类都生成一棵可视故障树。图 6 展示其中三棵，完整结果见补充材料。

**图 6：** SaFUZZ 共识别 11 类失效；图中展示三种失效的增强故障树。每棵树突出测试中观察到的一种根因模式，以黄色表示当前状态、粉色表示动作、绿色表示环境因素或配置。

- **图 6(a)，F2：起飞期间忽略人工控制。** 最小条件为：应用状态是 `TAKEOFF`，当前模式是 `STABILIZED`，动作是 `POSCTL`。即在起飞的增稳阶段发出的 `POSCTL` 被忽略。
- **图 6(b)，F6：GPS 噪声造成干扰，导致模式振荡。** 条件为：应用状态 `TAKEOFF`，模式 `OFFBOARD`，动作 `AUTO.LAND`，且 GPS 噪声为高。GPS 噪声使系统在 `LAND` 和 `TAKEOFF` 模式之间反复切换。
- **图 6(c)，F3：状态振荡；重新激活 `OFFBOARD` 后使用旧设定值，造成飞行突跳。** 条件包括：飞行状态、`OFFBOARD` 模式、地理围栏已启用且越界动作是 `LAND`；先发生越界并激活 `LAND`，随后又激活 `OFFBOARD`。

### 第 4 节导读

实验规模看起来是 11,160 次，但它们不等于 11,160 个独立 bug。自动判定先得到 77 次失败运行；聚类、复测和最小化后，才形成 11 个失效类别。评价论文时应把三个数字分开：

- 测试实例数说明吞吐量和输入空间探索规模；
- 失败运行数说明判定器触发次数；
- 失效类别数才接近开发人员需要处理的问题数。

另外，原型的“可扩展性”证据主要是并行容器和 248 小时的大批量执行，并不是跨多个 sUAS 平台的外部验证。

## 5 结果与分析

下面系统报告 SaFUZZ 应用于 Drone Response 的结果，并依次回答三个研究问题。

### 5.1 RQ1——SaFUZZ 流程的有效性

RQ1 考察 SaFUZZ 在多大程度上识别真正的行为故障。作者主要通过已识别故障的精确率评价，并进一步按类型分类。

SaFUZZ 返回 11 个候选失效。为分析其正确性和底层问题，第一作者与 Drone Response 的首席软件架构师举行了两次单独会议。该架构师是一名全职专业软件工程师，具有八年 Drone Response 各阶段开发经验。会议中，他们检查每棵故障树，同时查看 Drone Response 日志和 PX4 飞控日志，判断 SaFUZZ 找到的候选项是真阳性还是假阳性。

随后，为给每个确认的失效分类，三名团队成员采用自底向上方法：深入讨论每个失效案例，给出描述问题性质的初始标签；再以这些标签为起点提出类别，合并重叠术语、重命名以提升清晰度，最终收敛为一小组可一致应用的标签。最后，他们还为每类失效识别缓解措施。

在 11 个候选失效中：

- F1–F7 被归类为正确识别出的模式/状态相关失效，之后进入真实世界测试；
- F8 是 PX4 自动驾驶仪代码中的有效故障，但不直接受被测系统模式和状态转换影响；
- F9–F11 是假阳性。

依照研究采用的迭代式设计科学过程，作者修正了这三项假阳性：更新决策树中的“Mode Change to LOITER”节点，使其认识到，在 PX4 中 `AUTO.LOITER`、`POSCTL` 和油门切换最终都会产生 `POSCTL`。因此，未来模糊测试不会再报告这一类假阳性。具体缓解措施见补充材料。

**表 4：对 11 个失效类别的根因和分类**

| ID | 类别 | 描述 | 判定 |
|---|---|---|---|
| F1 | 从多个状态发起的模式切换被忽略 | 在 `HOVER` 中忽略 `LAND` 命令 | 真阳性：模式/状态 |
| F2 | `TAKEOFF` 期间忽略人工控制 | 起飞期间发出的人工接管命令未生效 | 真阳性：模式/状态 |
| F3 | 模式切换命令造成振荡 | 在 `LAND` 期间激活 `OFFBOARD` 后，状态之间出现反复切换；`OFFBOARD` 恢复时使用旧设定值，导致飞行突跳 | 真阳性：模式/状态 |
| F4 | 模式切换延迟 | 地理围栏越界触发 `RTL` 后，`POSCTL` 直到 `LAND` 完成后才被确认 | 真阳性：模式/状态 |
| F5 | 需求不清晰 | `TAKEOFF` 期间忽略 `RTL`。作者将其视为需求缺失，因为起飞期间应把 `RTL` 当作 `LAND` 处理 | 真阳性：模式/状态 |
| F6 | 干扰造成异常模式变化 | GPS 噪声导致 `LAND` 和 `TAKEOFF` 模式之间振荡 | 真阳性：模式/状态 |
| F7 | 失败状态转换期间忽略模式切换 | 地理围栏越界，动作是 `WARN`，同时激活 `POSCTL`；`POSCTL` 命令被忽略 | 真阳性：模式/状态 |
| F8 | PX4 模式内部问题 | 在 `STABILIZED` 模式着陆后，PX4 未能上锁/停止电机 | 有效失效，但不是目标模式/状态转换问题 |
| F9 | 决策树缺少逻辑 | 未识别出切换油门会触发 `POSCTL` | 假阳性 |
| F10 | 决策树缺少逻辑 | 未识别出旋翼机在飞行状态会把 `AUTO.LOITER` 当作 `POSCTL` 处理 | 假阳性 |
| F11 | 决策树缺少逻辑 | 未识别出旋翼机在着陆状态会把 `AUTO.LOITER` 当作 `POSCTL` 处理 | 假阳性 |

> **RQ1 研究发现——SaFUZZ 的自动化支持：** SaFUZZ 成功识别出七个与被测系统状态/模式转换相关的失效案例，并识别出一个与自动驾驶仪有关的失效。另有三个假阳性，它们由决策树缺少逻辑造成。

#### RQ1 导读

论文没有按常见方式直接报告一个数值精确率，但由表 4 可算出：11 个候选项中有 8 个有效问题，候选级精确率约为 \(8/11=72.7\%\)；若只计算论文的目标类别——被测系统状态/模式转换——则为 \(7/11=63.6\%\)。不过，这两个数都不是作者显式报告的指标，而且样本量很小，不宜过度解读。

F9–F11 也揭示了该方法的一个结构性特点：测试判定器不是客观真理，而是另一个需要验证和维护的软件制品。SaFUZZ 有一部分工作实际上是在共同演化“系统模型”和“判定模型”。

### 5.2 RQ2——失效识别

作者将 Drone Response 开发团队在正常测试过程中识别出的模式/状态转换错误，与 SaFUZZ 识别出的错误进行比较。

2024 年 1 月，团队从当时的 `stable` 代码库创建了一个冻结分支 `fuzz_test`。随后 18 个月里，开发在一系列功能分支上独立继续，所有改动最终合并回 `stable`，形成 2025 年 7 月版本。

因此，实验把 SaFUZZ 在冻结的 `fuzz_test` 基线中找到的失效，与开发团队在代码演化到 2025 年 7 月 `stable` 版本期间找到的失效进行比较。需要注意的是，SaFUZZ 测试直到 2025 年 7 月才在 `fuzz_test` 上执行，所以此前 SaFUZZ 的发现没有影响正常开发周期。

由于 `fuzz_test` 中真实的全部失效集合事先既未知、也无法得知，比较集中于两点：

1. SaFUZZ 是否找到开发团队识别的全部失效，即召回情况；
2. SaFUZZ 是否找到开发团队没有发现的额外失效。

截至 2025 年 7 月 16 日，`stable` 比 `fuzz_test` 领先 889 个提交。作者先从 Drone Response 仓库取回这些提交，再使用 Python 解析器，筛选提交文本中引用自动驾驶仪模式名或 28 个 Drone Response 应用层状态名的提交，得到 147 个候选提交。

团队系统检查这 147 个提交，识别出 4 个确实修复模式/状态转换错误的提交。此外，他们检索了 2024 年 1 月 24 日仍处于打开状态，或在 2024 年 1 月 24 日至 2025 年 7 月 16 日间创建的全部 issue，从中识别出 2 个相关 issue 和 4 个与状态/模式转换有关的关键提交。

接着，作者把 SaFUZZ 找到的失效列表、相关提交和 issue 提供给 Drone Response 软件架构师，请他结合自己的项目知识，判断开发团队是否独立发现并修复过 SaFUZZ 找到的失效。

对于两个相关 issue，架构师确认第一个是相关 bug 修复；第二个则与新增状态 `ReturnToCharge` 的 bug 有关，而这个状态在原始 `fuzz_test` 分支中并不存在。他没有发现 18 个月内修复或观察到的其他状态/模式失效。

结果表明，开发团队只发现了 SaFUZZ 所发现的八个 bug 中的一个（见图 7）。作者提出三种可能解释：

1. 未修复的失效不关键，因此开发团队没有发现它们并无影响；
2. 测试过程不充分，漏掉了这些失效；
3. SaFUZZ 有效揭示了一类正常测试没有检测到的独特失效。

作者否定解释 1，因为被测系统是生命关键的搜索救援系统。这类失效如果在部署中发生，可能导致无人机意外着陆、飞走或滞留空中，从而同时造成安全风险和任务风险。

对于解释 2，现有测试过程按传统标准已经相当健全，包括自动单元测试、大量仿真和频繁实地测试，但它在识别 SaFUZZ 所揭示的转换失效方面明显表现不足。因此，作者认为解释 3 最可信：将 SaFUZZ 集成到现有测试工作流，能够发现标准验证未暴露的、具有安全意义的状态—模式转换故障。

**图 7：** SaFUZZ 在 `fuzz_test` 分支中识别的 F1。开发人员在 `stable` 中也发现了它，并于 2024 年 7 月通过四个提交加入缺失的 `LAND` 故障保护，从而解决该问题。

> **RQ2 研究发现——与开发团队所发现失效的一致性：** SaFUZZ 识别出七类状态/模式转换失效。在 18 个月中，开发团队尽管进行了数千小时仿真和数百次真实飞行，也只检测到其中一种。团队发现的唯一另一项状态转换失效源于新功能，因此在 `fuzz_test` 分支中并不存在。

#### RQ2 导读

RQ2 是论文最有说服力、也最需要谨慎阅读的部分。它提供了一个现实基准：同一团队既有测试流程的历史发现。但它不是具有完整真值集的严格基线实验：

- 提交和 issue 的筛选依赖模式名/状态名文本匹配，可能漏掉没有使用这些词的修复；
- 开发团队是否“独立发现”还依赖首席架构师回忆与人工核验；
- SaFUZZ 测的是冻结旧分支，不能直接证明它在持续集成环境中的长期召回率。

更准确的结论是：在这个系统、这三份 FSpec 和这段历史窗口内，SaFUZZ 找到了一组常规流程此前未留下发现证据的安全相关失效。

### 5.3 RQ3——实地测试验证

为回答最后一个研究问题，作者在安全允许的范围内，使用实体 sUAS 验证发现。实机运行 `fuzz_test` 分支，并使用与仿真相同版本的 PX4。作者为每个失效创建一个有代表性的实地测试，只修改飞行坐标，使其匹配室外测试场地。

作者验证 F1–F5 和 F7，共六项。以下项目被排除：

- F6：真实世界中难以控制卫星几何等 GPS 因素；
- F8：在 `STABILIZED` 模式下着陆并不安全，可能造成坠机；
- F9–F11：它们是假阳性。

实体测试使用一架配备 PX4 和 Jetson Xavier NX 计算单元的六旋翼飞行器，通过 MeshRadio 连接地面控制站。每次测试前，团队使用 QGroundControl [50] 配置地理围栏动作等参数，再从 Drone Response 地面控制站将 JSON 任务规格发送到机载自主驾驶程序。

每次测试由两名成员执行，分别担任计算机操作员和责任遥控飞手（Remote Pilot in Command，RPIC）。计算机操作员负责发送任务，并在图形界面中监控当前状态和模式；RPIC 负责目视观察 sUAS。执行期间，计算机操作员在目标测试状态到达时通知 RPIC，RPIC 再使用遥控器发出指定的模式更新。两人共同目视观察系统行为，并记录飞行日志供测试后分析。

**表 5：在运行 PX4 的实体 sUAS 上执行的实地测试结果**

| 测试 | 实体机结果 | 是否确认仿真 |
|---|---|---:|
| F1 | 悬停期间忽略着陆命令。无人机开始着陆但没有完成，随后继续飞向下一航点；`OFFBOARD` 很可能仍保持激活 | ✓ |
| F2 | 系统没有确认 `POSCTL`，而是继续起飞，没有把控制权交给人类 | ✓ |
| F3 | 无人机在 `OFFBOARD` 与 `LAND` 之间振荡，险些坠机；测试飞手必须人工干预才能救回无人机 | ✓ |
| F4 | 实地没有观察到仿真中的行为，很可能属于仿真—实体差异。不过，团队注意到 PX4 的地理围栏越界在实地表现不一致，并且经常比预期更早触发 | ✗ |
| F5 | 系统没有确认 `RTL`。状态机关闭后，飞行器无法上锁，直到团队再次执行一次人工起飞 | ✓ |
| F7 | sUAS 立即响应 `POSCTL` | ✗ |

实地结果与仿真表现高度一致，但并非完全一致。六项失效中有四项复现了仿真中的相同行为：

- F1 中，悬停时的 `LAND` 命令被忽略；
- F2 中，起飞时的人工模式切换未被确认；
- F3 中，`OFFBOARD` 与 `LAND` 之间发生严重模式振荡，需要人工恢复；
- F5 中，返航请求以及随附的故障保护均被忽略。

F4 和 F7 则都出现了与地理围栏和故障保护处理有关的仿真—实地差异。

总之，SaFUZZ 在仿真中检测到的六项可测试失效，有四项在实体测试中得到复现。两项未复现测试都涉及地理围栏机制：

- F4 的仿真中，地理围栏触发 `RTL` 后立即发出的 `POSCTL` 命令，直到 sUAS 着陆后才得到确认；
- F7 的仿真中，在地理围栏 `WARN` 之后发出的 `POSCTL` 命令没有得到确认。

而在实地测试中，两项都完全按预期执行。这些仿真失效说明，仿真中的地理围栏功能保真度不足。

> **RQ3 研究发现——SaFUZZ 的真实世界测试：** 实地验证表明，SaFUZZ 在仿真中观察到的六项故障有四项被准确复现；另外两项属于与地理围栏和故障保护行为有关的仿真—现实差异。这些结果一方面确认 SaFUZZ 的发现能够迁移到真实部署，另一方面也暴露了当前仿真环境的保真度限制。

### 5.4 讨论

结果表明，SaFUZZ 能发现 sUAS 自治栈中有意义且真实的故障，其中一些问题尽管系统持续开发和测试了数月，仍未被发现。

基于状态机和模式转换推理构建的自动测试判定机制，使系统能够发现模式切换命令处理不一致、需求不清晰以及掩盖真实行为的仿真假象等细微失效。重要的是，实地验证确认其中若干故障会在实体部署中发生，而且标准测试流水线此前没有发现它们。

与此同时，F4 和 F7 的差异也暴露了仿真器的保真度限制，尤其是地理围栏处理和故障保护动作。地理围栏提供关键安全约束，因此这清楚地表明，需要保真度更高的地理围栏模型，准确反映自动驾驶仪与环境之间的交互 [10]。

尽管如此，两类结果都有价值：

- 如果真实世界确认仿真行为，就能增强信心：在仿真中验证过的修复也会在物理世界生效；
- 如果仿真到真实的行为不一致，就会提醒团队，系统的哪些部分不能信任仿真结果，底层仿真平台的哪些部分需要改进。

虽然实验只关注少量定向 FSpec，但已展示 SaFUZZ 能揭示传统仿真和实地测试漏掉的失效案例。

### 第 5 节导读

这组结果不能简单概括成“SaFUZZ 找到 11 个真实 bug”：

- 7 个是目标范围内的真实状态/模式失效；
- 1 个是有效 PX4 问题，但超出论文主目标；
- 3 个是判定器假阳性；
- 6 个目标失效接受了实机测试，其中 4 个复现；
- 2 个未复现结果反过来成为仿真器地理围栏模型不可靠的证据。

F3 是最有分量的案例，因为实体机险些坠毁并需要飞手介入；但它同时也说明，实机验证这类 fuzz failure 具有现实安全风险，不能把仿真用例不加筛选地搬到现场。

## 6 有效性威胁

本文工作有若干可能影响结果普适性和可解释性的局限。

**第一，只使用一个被测系统。** 评估仅基于 Drone Response 多 sUAS 系统。这样可以深入分析功能、代码和失效，但结果未必能完整迁移到采用不同架构、状态机或飞行控制器的其他 sUAS。

**第二，仿真到现实存在差异。** 地理围栏相关测试暴露了 Gazebo 等高端仿真器可能存在的保真度限制。六项失效中有四项在实体飞行中复现，验证了方法的效用；但仿真—现实差异也指出，如何准确建模环境和控制器动力学仍是开放问题。未来工作将扩展框架，以更好地描述和缩小这些差距。

**第三，没有结构化用户评价。** 虽然可视化和故障分类结果与 Drone Response 开发者进行了共享，但研究没有开展正式用户实验来评价可用性、可解释性或决策支持效果。不过，与 Drone Response 首席架构师的深入访谈所提供的轶事证据，强烈表明可视故障树有助于分析失效。

**第四，基线比较有限。** 除 RQ2 将结果与开发团队和实地测试人员发现的失效进行比较之外，作者没有把 SaFUZZ 与其他基线方法比较。Drone Response 团队采用稳健的 DevOps 方法，但 SaFUZZ 确实发现了额外失效。

研究也没有与更形式化的方法比较，主要原因是应用层和底层状态机非常复杂，而且持续演化。相比之下，本文的模糊测试方法只需定义新的 FSpec，便能较容易地扩展到新功能。该方法是为真实世界的开发约束设计的，但在强制要求基于规格和/或形式化验证的其他领域或系统类型中，适用性可能受限。

尽管存在这些局限，研究仍为自主系统多层模式转换的挑战，以及轻量分析方法在多 sUAS 系统中的效用，提供了具有实践价值的见解。

### 第 6 节导读

还应额外留意一个构造有效性问题：论文把“故障树”称为根因分析支持，但最小割集是从观测到的失败条件中提取的，它首先表达的是**足以稳定伴随失效的最小条件组合**，并不自动构成程序因果意义上的根因证明。真正的根因仍需开发人员结合应用日志、PX4 日志和代码分析确认。

## 7 相关工作

作者将相关工作集中在三个领域：一般 CPS 与 sUAS 测试 [1]、模糊测试 [65]，以及安全。

### CPS 测试

CPS 测试包含许多方面，例如硬件测试、超功能属性测试，以及集成测试和系统测试 [1, 64]。

De Liso 和 Wen [20] 提出 CAMBA，一种面向 UAV、成本感知且基于变异的测试用例生成算法。该工作重点研究一种智能障碍物放置系统，用于测试飞行行为是否安全。

Mandrioli 等人 [43] 将控制理论设计假设与蜕变测试、遗传编程结合。该方法不依赖需求和输入轨迹，而是定义多个测试用例输入与输出之间的蜕变关系。

Liang 等人 [42] 提出 GARL 框架，把遗传算法与强化学习结合，用于生成违反 sUAS 着陆要求的案例。与本文一样，他们结合了仿真测试和真实世界测试，并覆盖多样的着陆场景。但 SaFUZZ 处理的任务类型范围更广，也包括人机交互。

Duvvuru 等人 [25] 提出 AutoSimTest，使用大语言模型智能体自动完成 sUAS 仿真测试。与本文类似，他们生成测试场景和仿真配置，但没有像 SaFUZZ 的故障树那样提供结构化分析支持。

还有许多其他测试技术被用于 sUAS，包括基于视觉的测试 [12] 和数据驱动方法 [54]。不过，这些方法通常只覆盖 CPS 的狭窄部分，忽略人—CPS 交互，覆盖空间有限——例如只关注安全攻击 [32]——而且测试往往只在仿真中进行。

### 模糊测试

其他研究者也为机器人应用提出过模糊测试方法。

Delgado 等人 [21] 为使用 SMACH（任务规划执行库）的 ROS 系统提出一种 fuzzer，在 SMACH 状态上执行模糊测试。Drone Response 同样使用 SMACH 实现应用层状态机。

Woodlief 等人 [63] 开发 PHYS-FUZZ，对轨迹等物理属性进行模糊测试。RoboFuzz [38] 是一个为集成 ROS 而设计的反馈驱动模糊测试框架，也曾应用于使用 PX4 的四旋翼无人机。

Wang 等人 [61] 提出 DPFuzzer，一个自动检测无人机路径规划器漏洞的框架。与本文类似，他们使用模糊测试技术生成多样场景。

不过，这些方法虽然都使用模糊测试，却主要关注飞控属性，不支持基于人机交互的模糊测试，也没有纳入后续安全分析。

作者自己的前期工作也曾在 sUAS 领域应用模糊测试 [14]。该工作纳入人机交互失效，并采用分阶段推进方式：从代理人类仿真，逐步进入人在回路测试，再进入具有安全意识的实地测试。但它对观测失效根因的诊断支持有限。正是这一局限推动了 SaFUZZ 的提出。

SaFUZZ 使用基于决策树的失效判定器和包括故障树生成、可视化在内的自动诊断分析，聚焦测试自动化。它还引入大量时序变异，可以在状态转换期间触发竞争条件；同时注入罗盘干扰等真实环境扰动，从而支持具有可解释失效结果的高吞吐量测试。

### CPS 安全分析与保障

Jimenez-Roa 等人的 FT-MOEA [37] 使用多目标进化算法，从系统数据中自动恢复故障树，从而减轻人工、耗时的故障树分析工作。与其类似，本文也使用生成的故障树帮助项目利益相关者调查错误、识别根因。

在 CPS 形式化验证方面，Heitmeyer 和 Leonard [35] 提出 FORMAL，支持 CPS 的形式化建模和符号执行。

安全保障论证（Safety Assurance Case，SAC）广泛用于安全关键领域。要求 sUAS 使用安全论证是一个活跃研究方向，也形成了活跃的研究社区。Denney 和 Pai [22] 研究模块化安全论证，以便捕获和维护与 sUAS 行为有关的安全信息。

作者此前还研究了“互锁”安全保障论证，将基础设施特定因素和 sUAS 特定因素组合成安全论证 [57]。

Kreutz 等人 [39] 提出一种使用情境安全概念树（Contextual Safety Concept Tree）对机器人系统适应空间建模的方法。他们把依赖关系形式化为模糊推理系统 [16]，再在运行时评价安全需求。

本文也使用故障树的最小割集，但重点是支持人类进行根因分析。上述方法都对 sUAS 安全有所贡献，但主要关注人工创建的安全保障论证，并不包括在测试过程中自动创建或使用这些论证。

### 第 7 节导读

SaFUZZ 与邻近 fuzzing 工作的区别可以用测试靶点概括：

- 传统代码 fuzzing：字节、API、路径或覆盖率；
- UAV 场景 fuzzing：障碍、轨迹、传感器或路径规划器；
- SaFUZZ：跨层组合状态以及转换时刻；
- 作者前作 HIFuzz：人机交互事件与分阶段实机验证；
- SaFUZZ 相对 HIFuzz 的新增部分：自动判定、失败聚类、聚焦复测和故障树诊断。

因此，SaFUZZ 的最直接新意不是首次对无人机做 fuzzing，而是把**跨层状态语义、时序变异、人类接管和可解释诊断**放进一条工作流。

## 8 结论

本文提出 SaFUZZ：一条新颖的模糊测试流水线，用于验证 sUAS 跨多个控制逻辑层级的行为，包括应用层状态机、飞控模式、故障保护和人机交互。

SaFUZZ 生成真实且具有语义意义的测试场景，并在其中改变时序条件和环境因素，从而检测由简单或复杂系统交互引起的转换失效和危险交互。在此基础上，动态生成的故障树帮助利益相关者诊断根本原因，提高系统韧性。

作者通过一系列高保真仿真和真实世界实地测试验证了该方法。研究结果对实践者和研究人员都可能有价值。

从实践角度看，SaFUZZ 可以增强现有开发和测试流程，识别人工测试或临时飞行评价通常难以触达的转换故障、时序危险和非预期行为序列。

从研究角度看，SaFUZZ 提供一种结构化方法，用于研究以转换为中心的失效模式和跨层危险。这些问题历来促成过许多事故，却在现有验证研究中没有得到充分考察。

未来工作将考察 SaFUZZ 对更广泛测试的适用性：先在仿真中生成测试，再通过实体测试进行佐证，重点关注复杂模式转换、控制权交接行为，以及应用层状态机与飞控状态机之间的交互。

此外，作者计划面向开发人员和测试人员开展定向用户研究，评价 SaFUZZ 的诊断输出能否有效支持故障理解、调试效率以及对测试结果的信心。

### 第 8 节导读

论文最终支撑得最扎实的结论是“这个工作流在一个长期开发的真实系统中，能发现常规流程漏掉的跨层转换问题，并有一部分可在实体机复现”。它尚未证明：

- 对其他飞控和应用架构同样有效；
- FSpec 或 Oracle 能低成本自动迁移；
- 故障树一定提高开发者调试效率；
- 比其他状态模型测试或搜索式测试方法拥有更高召回率。

这些恰好是后续工作和复现研究可以推进的方向。

## 9 致谢

本文工作主要由美国国家科学基金会资助，项目编号 1931962。

---

# 全文回顾：用一条案例读懂 SaFUZZ

以 F2 为例，完整链条如下：

1. **危险：** 人类在自主飞行中请求接管，但控制权没有交出。
2. **FSpec：** 枚举 `TAKEOFF` 等应用状态、`STABILIZED/OFFBOARD` 等实际模式、`POSCTL` 动作，以及短中长延迟。
3. **任务：** 让无人机真实经过 `TAKEOFF`。
4. **触发：** 第一次观察到目标组合后，等待采样延迟并注入 `POSCTL`。
5. **Oracle：** 如果人工请求取消自主控制，而自主驾驶仍未停用，则判为失败。
6. **聚类：** 把大量相似失败归成簇，并选择代表案例。
7. **聚焦复测：** 在不同时间区间重复执行，生成表 1。
8. **条件分解：** 发现中等延迟并非真正根因；失败其实取决于命令发生时 PX4 是否仍处于 `STABILIZED`。
9. **故障树：** 最小割集为 `TAKEOFF ∧ STABILIZED ∧ POSCTL`。
10. **实机验证：** 实体无人机同样忽略 `POSCTL` 并继续起飞。

这个案例展示了论文最重要的思想：**“延迟”本身常常只是把动作移动到了内部转换的不同一侧；真正需要定位的是动作发生时的跨层组合状态。**

# 一句话评价

SaFUZZ 是一套面向 UAV 自治软件的、危险驱动的跨层状态转换测试方法：它用语义 FSpec 系统改变事件、环境和时机，用专家构造的 Oracle 判断行为，再用聚类、聚焦复测和最小故障树把失败压缩成可分析条件；其真实价值由旧版本历史对照和实机复现共同支撑，但泛化性、Oracle 成本与故障树的实际调试收益仍有待进一步验证。

# 参考文献

> 以下书目信息按论文原文保留，不翻译题名，以保证可以直接检索和引用。

[1] Sara Abbaspour Asadollah, Rafia Inam, and Hans Hansson. 2015. A Survey on Testing for Cyber Physical System. In *Proc. of the 27th IFIP WG 6.1 International Conference on Testing Software and Systems*. Springer International Publishing, Cham, 194–207.

[2] Julie A. Adams, Curtis M. Humphrey, Michael A. Goodrich, Joseph L. Cooper, Bryan S. Morse, Cameron Engh, and Nathan Rasmussen. 2009. Cognitive Task Analysis for Developing Unmanned Aerial Vehicle Wilderness Search Support. *Journal of Cognitive Engineering and Decision Making* 3, 1 (2009), 1–26.

[3] Ankit Agrawal, Sophia J. Abraham, Benjamin Burger, Chichi Christine, Luke Fraser, John M. Hoeksema, Sarah Hwang, Elizabeth Travnik, Shreya Kumar, Walter J. Scheirer, Jane Cleland-Huang, Michael Vierhauser, Ryan Bauer, and Steve Cox. 2020. The Next Generation of Human-Drone Partnerships: Co-Designing an Emergency Response System. In *CHI ’20: CHI Conference on Human Factors in Computing Systems*. ACM, 1–13. <https://doi.org/10.1145/3313831.3376825>

[4] Maral Amir and Tony Givargis. 2017. Hybrid state machine model for fast model predictive control: Application to path tracking. In *Proc. of the IEEE/ACM International Conference on Computer-Aided Design (ICCAD)*. IEEE Computer Society, 185–192.

[5] Jose Anand, C Aasish, S Syam Narayanan, and R Asad Ahmed. 2023. Drones for disaster response and management. In *Internet of Drones*. CRC Press, 177–200.

[6] Kelvin Anto, AK Swain, and Partha Roop. 2023. A Novel Framework for the Design of Resilient Cyber-Physical Systems Using Control Theory and Formal Methods. *IEEE Access* (2023), 1–1. <https://doi.org/10.1109/ACCESS.2023.3295421>

[7] ArduPilot. 2025. <http://ardupilot.org>. Last accessed 01-12-2025.

[8] Ezio Bartocci, Niveditha Manjunath, Leonardo Mariani, Cristinel Mateis, and Dejan Ničković. 2021. CPSDebug: Automatic failure explanation in CPS models. *International Journal on Software Tools for Technology Transfer* 23, 5 (2021), 783–796.

[9] Sofia Bekrar, Chaouki Bekrar, Roland Groz, and Laurent Mounier. 2011. Finding software vulnerabilities by smart fuzzing. In *Proc. of the 2011 Fourth IEEE International Conference on Software Testing, Verification and Validation*. IEEE Computer Society, 427–430.

[10] Adrian Boeing and Thomas Bräunl. 2012. Leveraging multiple simulators for crossing the reality gap. In *Proc. of the 12th International Conference on Control Automation Robotics & Vision*. IEEE, 1113–1119.

[11] Matthew L Bolton, Ellen J Bass, and Radu I Siminiceanu. 2013. Using formal verification to evaluate human-automation interaction: A review. *IEEE Transactions on Systems, Man, and Cybernetics: Systems* 43, 3 (2013), 488–503.

[12] Qing Bu, Fuhua Wan, Zhen Xie, Qinhu Ren, Jianhua Zhang, and Sheng Liu. 2015. General simulation platform for vision based UAV testing. In *2015 IEEE International Conference on Information and Automation*. IEEE Computer Society, 2512–2516.

[13] Miguel Campusano, Kjeld Jensen, and Ulrik Pagh Schultz. 2021. Towards a Service-Oriented U-Space Architecture for Autonomous Drone Operations. In *Proc. of the 2021 IEEE/ACM 3rd International Workshop on Robotics Software Engineering (RoSE)*. IEEE Computer Society, 63–66.

[14] Theodore Chambers, Michael Vierhauser, Ankit Agrawal, Michael Murphy, Jason Matthew Brauer, Salil Purandare, Myra B. Cohen, and Jane Cleland-Huang. 2024. HIFuzz: Human Interaction Fuzzing for Small Unmanned Aerial Vehicles. In *Proc. of the CHI Conference on Human Factors in Computing Systems*. ACM, 1–14.

[15] Theodore P. Chambers, Pedro Granadeno, Usman Gohar, Michael C. Hunter, Arturo Miguel Russell Bernal, Wenyi Tang, Md Nafee Al Islam, Myra Cohen, Taeho Jung, Robyn Lutz, and Jane Cleland-Huang. 2025. Automated On-Entry Decision-Making for UTM Zones Based on Reputations and Certifications. In *AIAA Aviation Forum and ASCEND 2025*. 3567.

[16] Vladimir Cherkassky. 1998. Fuzzy inference systems: a critical review. *Computational intelligence: soft computing and fuzzy-neuro integration with applications* (1998), 177–197.

[17] Jane Cleland-Huang, Theodore Chambers, Sebastián Zudaire, Muhammed Tawfiq Chowdhury, Ankit Agrawal, and Michael Vierhauser. 2024. Human-machine Teaming with Small Unmanned Aerial Systems in a MAPE-K Environment. *ACM Transactions on Autonomous and Adaptive Systems* 19, 1 (2024), 3:1–3:35. <https://doi.org/10.1145/3618001>

[18] Jane Cleland-Huang, Michael Vierhauser, and Sean Bayley. 2018. Dronology: An incubator for cyber-physical system research. *arXiv preprint arXiv:1804.02423* (2018).

[19] Mengyao Cui et al. 2020. Introduction to the k-means clustering algorithm based on the elbow method. *Accounting, Auditing and Finance* 1, 1 (2020), 5–8.

[20] Marco De Liso and Zhi Wen Soi. 2024. CAMBA CPS-UAV at the SBFT Tool Competition 2024: CAMBA: Cost-Aware Mutation-Based Test Case Generation for Unmanned Aerial Vehicles. In *Proc. of the 17th ACM/IEEE International Workshop on Search-Based and Fuzz Testing*. ACM, 47–48.

[21] Rodrigo Delgado, Miguel Campusano, and Alexandre Bergel. 2021. Fuzz testing in behavior-based robotics. In *2021 IEEE International Conference on Robotics and Automation (ICRA)*. IEEE Computer Society, 9375–9381.

[22] Ewen Denney and Ganesh Pai. 2012. A lightweight methodology for safety case assembly. In *Proc. of the International Conference on Computer Safety, Reliability, and Security*. Springer, 1–12.

[23] Andrea Di Sorbo, Fiorella Zampetti, Aaron Visaggio, Massimiliano Di Penta, and Sebastiano Panichella. 2023. Automated identification and qualitative characterization of safety concerns reported in UAV software platforms. *ACM Transactions on Software Engineering and Methodology* 32, 3 (2023), 1–37.

[24] DroneCode. 2025. MAVLink — Developer Guide. <https://mavlink.io/en>. Last accessed 01-12-2025.

[25] Venkata Sai Aswath Duvvuru, Bohan Zhang, Michael Vierhauser, and Ankit Agrawal. 2025. LLM-Agents Driven Automated Simulation Testing and Analysis of small Uncrewed Aerial Systems. In *Proc. of the 47th International Conference on Software Engineering*. IEEE Computer Society, 385–397.

[26] Vladimir Ermakov. 2025. MAVROS. <https://github.com/mavlink/mavros>. Last accessed 01-12-2025.

[27] Ayodeji Falayi, Qianlong Wang, and Wei Yu. 2025. Edge intelligence in smart transportation CPS. In *Edge Intelligence in Cyber-Physical Systems*. Elsevier, 193–219.

[28] Mirgita Frasheri, Baran Cürüklü, Mikael Esktröm, and Alessandro Vittorio Papadopoulos. 2018. Adaptive autonomy in a search and rescue scenario. In *Proc. of the 12th International Conference on Self-Adaptive and Self-Organizing Systems*. IEEE Computer Society, 150–155.

[29] Chris Gardner. 2022. Ex-Skydance Exec Piloted Drone That Crashed Into Firefighting Helicopter. *The Hollywood Reporter*. <https://www.hollywoodreporter.com/news/local-news/ex-skydance-exec-piloted-drone-crashed-plane-palisades-fire-1236123911>. Last accessed 01-12-2025.

[30] Arash Golabi, Abdelkarim Erradi, and Ashraf Tantawy. 2022. Towards automated hazard analysis for CPS security with application to CSTR system. *Journal of Process Control* 115 (2022), 100–111.

[31] Pedro Alarcon Granadeno and Jane Cleland-Huang. 2025. Land-Coverage Aware Path-Planning for Multi-UAV Swarms in Search and Rescue Scenarios. *CoRR* abs/2505.08060 (2025). <https://doi.org/10.48550/ARXIV.2505.08060>

[32] Seana Hagerman, Anneliese Andrews, and Stephen Oakes. 2016. Security testing of an unmanned aerial vehicle (UAV). In *Proc. of the 2016 Cybersecurity Symposium*. IEEE Computer Society, 26–31.

[33] David Hambling. 2020. Drone Crash Due To GPS Interference in U.K. Raises Safety Questions. *Forbes*. <https://www.forbes.com/sites/davidhambling/2020/08/10/investigation-finds-gps-interference-caused-uk-survey-drone-crash/>

[34] Shah Ahsanul Haque, Syed Mahfuzul Aziz, and Mustafizur Rahman. 2014. Review of cyber-physical system in healthcare. *International Journal of Distributed Sensor Networks* 10, 4 (2014), 217415.

[35] Constance L Heitmeyer and Elizabeth I Leonard. 2015. Obtaining trust in autonomous systems: Tools for formal model synthesis and validation. In *2015 IEEE/ACM 3rd FME Workshop on Formal Methods in Software Engineering*. IEEE Computer Society, 54–60.

[36] Christian Holler, Kim Herzig, and Andreas Zeller. 2012. Fuzzing with code fragments. In *Proc. of the 21st USENIX Security Symposium*. 445–458.

[37] Lisandro Arturo Jimenez-Roa, Tom Heskes, Tiedo Tinga, and Mariëlle Stoelinga. 2022. Automatic inference of fault tree models via multi-objective evolutionary algorithms. *IEEE Transactions on Dependable and Secure Computing* 20, 4 (2022), 3317–3327.

[38] Seulbae Kim and Taesoo Kim. 2022. RoboFuzz: Fuzzing Robotic Systems over Robot Operating System (ROS) for Finding Correctness Bugs. In *Proc. of the 30th ACM Joint European Software Engineering Conference and Symposium on the Foundations of Software Engineering (ESEC/FSE 2022)*. ACM, 447–458.

[39] Andreas Kreutz, Gereon Weiss, and Mario Trapp. 2025. Modeling Safe Adaptation Spaces for Self-Adaptive Systems Using Contextual Safety Concept Trees. In *Proc. of the IEEE/ACM 20th Symposium on Software Engineering for Adaptive and Self-Managing Systems*. IEEE Computer Society, 96–102.

[40] T Rajasanthosh Kumar, Mahesh M Kawade, Gaurav Kumar Bharti, and G Laxmaiah. 2024. Implementation of Intelligent CPS for Integrating the Industry and Manufacturing Process. In *AI-Driven IoT Systems for Industry 4.0*. CRC Press, 273–288.

[41] Caroline Lemieux and Koushik Sen. 2018. FairFuzz: a targeted mutation strategy for increasing greybox fuzz testing coverage. In *Proc. of the 33rd ACM/IEEE International Conference on Automated Software Engineering*. ACM, 475–485.

[42] Linfeng Liang, Yao Deng, Kye Morton, Valtteri Kallinen, Alice James, Avishkar Seth, Endrowednes Kuantama, Subhas Mukhopadhyay, Richard Han, and Xi Zheng. 2025. GARL: Genetic Algorithm-Augmented Reinforcement Learning to Detect Violations in Marker-Based Autonomous Landing Systems. In *Proc. of the 47th IEEE/ACM International Conference on Software Engineering*. IEEE Computer Society, 411–423.

[43] Claudio Mandrioli, Seung Yeob Shin, Domenico Bianculli, and Lionel Briand. 2025. Testing CPS with design assumptions-based metamorphic relations and genetic programming. *IEEE Transactions on Software Engineering* 51, 6 (2025).

[44] Owen McAree, Jonathan M Aitken, and Sandor M Veres. 2016. A model based design framework for safety verification of a semi-autonomous inspection drone. In *Proc. of the 11th International Conference on Control*. IEEE Computer Society, 1–6.

[45] Open Robotics. 2025. Gazebo. <https://gazebosim.org>. Last accessed 01-07-2025.

[46] Anastasios Plioutsias, Nektarios Karanikas, and Maria Mikela Chatzimihailidou. 2018. Hazard analysis and safety requirements for small drone operations: to what extent do popular drones embed safety? *Risk Analysis* 38, 3 (2018), 562–584.

[47] Salil Purandare, Urjoshi Sinha, Md Nafee Al Islam, Jane Cleland-Huang, and Myra B. Cohen. 2023. Self-Adaptive Mechanisms for Misconfigurations in Small Uncrewed Aerial Systems. In *Proc. of the 18th IEEE/ACM Symposium on Software Engineering for Adaptive and Self-Managing Systems*. IEEE Computer Society, 169–180.

[48] PX4. 2023. Flight Controller Modes. <https://docs.px4.io/main/en/flight_modes_mc/>. Last accessed 01-12-2025.

[49] PX4 — Open Source Autopilot. 2025. PX4. <https://px4.io>. Last accessed 01-12-2025.

[50] QGroundControl. 2025. Ground Control Station. <http://qgroundcontrol.com>. Last accessed 01-07-2025.

[51] W. V. Quine. 1952. The Problem of Simplifying Truth Functions. *The American Mathematical Monthly* 59, 8 (1952), 521–531. <http://www.jstor.org/stable/2308219>

[52] Drone Response. 2025. Drone Response sUAS Platform. <https://droneresponse.ai>. Last accessed 31-12-2025.

[53] Bernardo Martinez Rocamora, Paulo VG Simplicio, and Guilherme AS Pereira. 2024. A behavior tree approach for battery-aware inspection of large structures using drones. In *2024 International Conference on Unmanned Aircraft Systems (ICUAS)*. IEEE Computer Society, 234–240.

[54] Mrinmoy Sarkar, Abdollah Homaifar, Berat A Erol, Mohammadreza Behniapoor, and Edward Tunstel. 2020. PIE: a tool for data-driven autonomous UAV flight testing. *Journal of Intelligent & Robotic Systems* 98 (2020), 421–438.

[55] Sam Siewert, Krishna Sampigethaya, Jonathan Buchholz, and Steve Rizor. 2019. Fail-safe, fail-secure experiments for small UAS and UAM traffic in urban airspace. In *Proc. of the 2019 IEEE/AIAA 38th Digital Avionics Systems Conference*. IEEE Computer Society, 1–7.

[56] Paweł Smyczyński, Łukasz Starzec, and Grzegorz Granosik. 2017. Autonomous drone control system for object tracking: Flexible system design with implementation example. In *Proc. of the 22nd International Conference on Methods and Models in Automation and Robotics*. IEEE Computer Society, 734–738.

[57] Michael Vierhauser, Sean Bayley, Jane Wyngaard, Wandi Xiong, Jinghui Cheng, Joshua Huseman, Robyn Lutz, and Jane Cleland-Huang. 2019. Interlocking safety cases for unmanned autonomous systems in shared airspaces. *IEEE Transactions on Software Engineering* 47, 5 (2019), 899–918.

[58] Michael Vierhauser, Md Nafee Al Islam, Ankit Agrawal, Jane Cleland-Huang, and James Mason. 2021. Hazard analysis for human-on-the-loop interactions in sUAS systems. In *Proc. of the 29th ACM Joint Meeting on European Software Engineering Conference and Symposium on the Foundations of Software Engineering*. ACM, 8–19.

[59] Willem Visser and Jaco Geldenhuys. 2020. Coastal: Combining concolic and fuzzing for Java (competition contribution). In *Proc. of the International Conference on Tools and Algorithms for the Construction and Analysis of Systems*. Springer, 373–377.

[60] Kay Wackwitz and Hendrick Boedecker. 2015. Safety risk assessment for UAV operation. *Drone Industry Insights, Safe Airspace Integration Project, Part One*, Hamburg, Germany (2015), 31–53.

[61] Yue Wang, Chao Yang, Xiaodong Zhang, Yuwanqi Deng, and JianFeng Ma. 2025. DPFuzzer: Discovering Safety Critical Vulnerabilities for Drone Path Planners. In *Proc. of the 2025 IEEE/ACM 47th International Conference on Software Engineering*. IEEE Computer Society, 588–588.

[62] Roel J. Wieringa. 2014. *Design Science Methodology for Information Systems and Software Engineering*. Springer, London. <https://doi.org/10.1007/978-3-662-43839-8>

[63] Trey Woodlief, Sebastian Elbaum, and Kevin Sullivan. 2021. Fuzzing mobile robot environments for fast automated crash detection. In *2021 IEEE International Conference on Robotics and Automation (ICRA)*. IEEE Computer Society, 5417–5423.

[64] Xin Zhou, Xiaodong Gou, Tingting Huang, and Shunkun Yang. 2018. Review on testing of cyber physical systems: Methods and testbeds. *IEEE Access* 6 (2018), 52179–52194.

[65] Xiaogang Zhu, Sheng Wen, Seyit Camtepe, and Yang Xiang. 2022. Fuzzing: A Survey for Roadmap. *ACM Computing Surveys* 54, 11s, Article 230 (2022), 36 pages. <https://doi.org/10.1145/3512345>
