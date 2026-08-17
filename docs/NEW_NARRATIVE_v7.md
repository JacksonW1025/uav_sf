# NEW_NARRATIVE_v7

# Beyond Flight Modes: Evidence-Gated Stateful Testing of Route-Replacing Authority Transitions in PX4

## 0. 文档定位

本文档是项目唯一有效的研究叙事。它用于统一论文的问题定义、方法、已有证据、评价计划、贡献边界和下一步工作。

关于“当前代码实现了什么、哪些实验已经完成”的判断，以 `uav_sf/` 仓库为唯一事实来源。本文档描述研究意义和论文组织，但不覆盖或改写仓库中的正式矩阵、账本、环境证明与实验报告。

V7 的研究范围收敛为 **Family A：PX4 内部控制路径、Legacy Offboard、Dynamic External Mode、Mode Executor 与内部 Hold、RTL、Land、Recovery 之间的 route-replacing authority transition**。飞控内部 registered controller-graph replacement 不属于当前实现、实验或论文主张，只在 Future Work 中讨论。

当前实现快照：

```text
repository: uav_sf
current narrative source: uav_sf/docs/NEW_NARRATIVE_v7.md on origin/main
formal launches retained by the two Thor studies: 200
admissible evidence sets: 151
overall Oracle results among admissible evidence: 94 PASS, 57 VIOLATION
Stage A1 minimal-mechanism motivation: complete through a separate supplemental study
Stage A2 moving-workload realism bridge: planned
prior Orin evidence: documented as a separate historical evidence layer
live formal strategy support: official sequence only
```

V7 将归属于 V6 的 Orin 实验摘要记录为 prior evidence lineage，包括 P5 v6 matched baseline、Issue #162 historical successor benchmark 和 current-version freshness pilot。当前 `origin/main` 不保留或暴露对应 V6 报告、账本、compact evidence 或可达历史分支；它们不进入 Thor 的 200 次 launch、151 份 admissible evidence 或 94/57 结果。精确核查或复用必须由另行提供的 V6 来源包、原 revision、study identity 和证据完成，不能只依赖本叙事摘要。

---

# 1. 先用自然语言解释：这项工作到底在做什么

## 1.1 把无人机控制想成“多人接力开飞机”

一架自主无人机并不总是由同一个程序控制。起飞时可能由 PX4 内部模式控制，进入自主任务后由伴随计算机上的 Offboard 程序控制，任务完成后又交还给 PX4 的 Hold、RTL 或 Land。发生故障时，安全路径还需要再次接管。

可以把这个过程理解成接力赛：

```text
PX4 内部控制
    → 把控制权交给外部自主程序
    → 外部程序完成、退出或发生故障
    → PX4 的 Hold / RTL / Land 接棒
```

问题在于，屏幕上显示“已经切换到某个模式”，只相当于裁判宣布“接力棒已经交接”，却不能证明真实的控制链已经完成交接。

旧程序可能仍在影响控制器；新程序可能只完成了注册，却还没有把命令送到执行器；新路径可能在使用一条已经过期的命令；任务虽然报告完成，却没有人负责启动下一步 Land；最终飞机虽然落地，也可能经历过短暂的控制空档、双重写入或错误的 successor。

因此，这项工作不只看“现在是什么飞行模式”，而是追踪真正产生飞行效果的整条路径。

## 1.2 我们追踪什么

对每一次控制权交接，我们给旧路径和新路径都建立一份可追踪身份，记录：

- 是哪一次 route epoch；
- 是哪个 producer 进程和 session；
- 是哪一次 registration 和 activation；
- 控制器正在消费哪一条命令，这条命令是什么时间产生的；
- 哪个 controller 和 allocator 处理了它；
- 最终哪个 writer 写到了 actuator；
- 谁拥有当前任务生命周期；
- 完成或故障后应该进入哪条 successor 或 fallback 路径。

这就像给接力棒、运动员和每一次交接都加上独立编号。即使两个阶段在界面上显示同一个模式，我们仍能区分它们是不是同一次控制实例。

## 1.3 我们如何判断一次交接是否正确

我们分别问四组问题：

1. **旧路径真的停手了吗，新路径真的接棒了吗？** 这由 Route Conformance 检查。
2. **新路径使用的是新鲜、来源正确的命令吗？** 这由 Freshness and Lineage 检查。
3. **任务完成或故障后，正确的下一条路径被安装了吗？** 这由 Successor Progression 检查。
4. **本应被拒绝的注册或激活请求，是否真的被明确拒绝？** 这由 Registration Contract 检查。

在解释这些结果之前，Evidence Admissibility Gate 先判断证据是否完整。如果日志缺失、时钟无法对应、身份不完整或采集窗口有空洞，结果只能是 `INCONCLUSIVE`，不能因为“没有看到错误”就算 PASS。

## 1.4 现在已经发现了什么

清理后的仓库在 AGX Thor 的锁定 PX4 SITL 环境中完成了两个独立、预注册的 Motivation study。

两项研究合计关闭了 200 次正式 launch，其中 151 份证据通过 Evidence Gate。在这些可解释的证据中，94 份满足全部适用契约，57 份至少违反一个适用契约。

这些 VIOLATION 不是 57 个独立缺陷，但它们说明了一个关键事实：

> 飞行模式看起来正确、运行最终安全结束，并不等于控制权交接过程正确。

例如：

- 正常 attitude-Offboard 流程可以完成并安全收尾，但目标 route 没有在冻结期限内形成完整的 command-to-actuator 路径；
- 外部程序停止或 setpoint 停滞后，安全 fallback 可以最终发生，但控制链在此之前仍可能消费过期命令；
- Land successor 可以完整安装，但 completion 与相邻请求的顺序仍可能离开预注册的时间桶；
- 修正后的 RTL re-entry 可以连续两次进入 Offboard，并产生不同的 route epoch 与 activation identity，证明重复进入不能只靠模式名判断。

在这组当前证据之前，V7 记录的 V6 摘要描述了另一层 Orin evidence：P5 v6 建立了 Legacy Offboard 与 Dynamic External Mode 的正常 matched baseline；Issue #162 稳定复现了 executor ownership 失配导致 Land successor 缺失；freshness pilot 记录了 retained-command exposure 和一次自然 stale-subject event。V7 保留这些结果的历史研究作用，同时明确当前分支不能独立复核其原始制品，并把当前可复现实证分母限定为 Thor corpus。

## 1.5 下一步要做什么

现有 Thor Motivation 使用预先写好的 official sequence，并以约 3 m 定点悬停、水平姿态或零角速度为主要运动上下文。它已经完成最小机制与测量基础，下一步增加一个单独预注册的移动工作负载 Stage A2：

```text
Internal Takeoff
    → Legacy Offboard or Dynamic External Mode
    → Acceleration / Turn or Ascent–Translation–Descent
    → Completion / Cancel / Process Exit during a selected motion phase
    → Hold / RTL / Land
```

Stage A2 在两种外部机制上复用同一任务形状、运动目标和 transition phase，至少包含正常完成与一种故障或中断。它用于检验移动状态是否增加新的 route/freshness/successor observation，并解释同类 violation 的物理后果。该研究使用新的 preregistration、ledger、environment identity 和 denominator，不修改 Stage A1 的任何结果。

方法主线随后让测试器根据无人机当前的 route、health、completion、owner 和覆盖状态，主动选择下一个合法动作，逼近尚未覆盖的交接边界。

最终论文要比较三种方法：

```text
Official Sequence
    按固定顺序执行

Bounded Random Timing
    在预注册时间范围内随机安排动作

State-Aware Strategy
    观察当前状态，只选择满足前置条件的动作，
    优先探索尚未覆盖且接近契约边界的交接
```

如果 state-aware 方法在相同预算下能够覆盖更多有效状态、更早找到 violation、产生更多可复现的独立问题，它就构成论文的主要方法贡献。当前仓库已经实现策略函数和验证逻辑，但 bounded-random 与 state-aware 尚未接入 live PX4 action backend，因此这部分仍是下一阶段，而不是已经完成的结果。

---

# 2. 研究问题与核心论点

## 2.1 现实背景

PX4 自主飞行任务通常包含如下控制路径：

```text
Internal Takeoff
    → Legacy Offboard or Dynamic External Mode
    → Completion / Cancel / Process Failure / Setpoint Stall
    → Internal Hold / RTL / Land / Recovery
```

这些变化体现主要控制路径身份的离散变化，超出普通 waypoint 更新。每次变化都要求旧路径撤销、新路径完整安装、执行权保持独占和连续、命令来源有效，并在完成或故障后推进正确的 successor 或 fallback。

## 2.2 核心问题

本文研究：

> 当 PX4 或外部系统声明主要控制路径已经从 Route A 转移到 Route B，旧路径是否及时且完整地停止影响执行器，新路径是否形成完整且唯一的 command-to-actuator 路径，当前路径是否消费新鲜且身份一致的命令，正确的 lifecycle owner 是否推进预期 successor，故障后安全路径是否真正安装？

## 2.3 核心论点

本文的核心论点是：

> 飞行模式和终端物理结果只描述了交接的一部分。可靠测试必须同时观测控制平面、命令数据平面、controller/writer lineage 与 lifecycle progression，并使用明确的证据准入规则区分 PASS、VIOLATION、UNKNOWN、NOT_APPLICABLE 和整体 INCONCLUSIVE。

Motivation study 已经证明这种跨层观测能够发现 mode-state-only 或 terminal-outcome-only 检查无法解释的问题。完整论文还需要证明 state-aware generation 能比固定顺序和 bounded random 更有效地探索这些问题。

---

# 3. 正式研究范围

## 3.1 当前唯一实证范围：Family A

本文只研究下列连接系统：

```text
PX4 Internal Route
    ↔ Legacy Offboard
    ↔ Dynamic External Mode
    ↔ Mode Executor
    ↔ Internal Hold / RTL / Land / Recovery
```

主要机制包括：

- PX4 Commander 与 Mode Management；
- Offboard proof-of-life 与 setpoint publication；
- ROS 2 External Mode registration、activation 与 lifecycle；
- Mode Executor ownership 与 completion；
- public arm、takeoff、mode、RTL、Land 等命令；
- target installation、source revocation 与 fallback；
- setpoint、controller、allocator 与 actuator-writer lineage；
- process exit、setpoint stall、health loss、registration capacity 等故障或拒绝场景；
- repeated entry、adjacent request 与 successor progression。

## 3.2 不属于当前论文主张的内容

以下内容不进入当前实现和主评价：

- 长期 shared authority 或 per-axis arbitration；
- controller 参数调优与控制性能排名；
- perception、SLAM、planner correctness；
- 通用 DDS 性能或任意网络模糊测试；
- kill、lockdown 和 flight termination；
- VTOL 构型转换；
- HIL、真机与实飞安全结论；
- 完整 PX4 mode-state-machine fuzzing；
- 飞控内部 registered custom controller graph。

## 3.3 Family B 的地位

飞控内部 classic controller 与 registered custom controller 之间的 graph replacement 可能复用 Runtime Route Instance、writer lineage 和 route contract。它是有价值的未来扩展，但当前仓库没有相应 runtime、reference controller、正式矩阵或实验结果。

因此 Family B 只作为 Future Work：未来可研究 route abstraction 能否从 companion-side handoff 下沉到 onboard controller/allocator/writer replacement。本文不以它支撑 generality，不把它列为当前 contribution，也不把它加入当前 evaluation plan。

---

# 4. Unified Runtime Route Model

## 4.1 Runtime Route Instance

一条当前能够产生飞行关键 actuator effect 的路径由下列稳定身份定义：

```text
RuntimeRouteInstance = (
    route,
    route_epoch,
    producer_session,
    registration_id,
    activation_id,
    controller_id,
    allocator_id,
    writer_id,
    lifecycle_owner,
    executor_owner
)
```

其中：

- `route` 表示稳定的 route 类型；
- `route_epoch` 区分每次 authority-relevant route state；
- `producer_session` 区分 producer 重启前后的实例；
- `registration_id` 与 `activation_id` 分别区分 slot allocation 和实际使用；
- `controller_id`、`allocator_id`、`writer_id` 形成下游 lineage；
- `lifecycle_owner` 与 `executor_owner` 描述完成、释放和 successor 的责任主体。

每个 command-consumption 和下游 effect event 另外携带
`command_subject_ns`。它表示被消费命令所描述状态的时间，而不是日志写入
时间。一个活跃实例会连续消费多条新命令，因此 subject time 是绑定到稳定
Route Instance 的动态 freshness evidence，不是稳定 identity field。

只要 authority-relevant identity 变化，即使 route 名称或 mode label 相同，也产生新的 Runtime Route Instance。

## 4.2 Transition interval

一次 transition 从公开的 `transition_requested` 开始。只有在目标 activation 已发生，并且同一 target identity 下的 command consumption、controller output、allocator output 和 actuator write 已经完整观测后，target installation 才算完成。

这一定义防止下列错误推理：

```text
mode changed
    ≠ target route fully installed

target activated
    ≠ command reached actuator writer

vehicle landed
    ≠ every intermediate handoff contract passed
```

## 4.3 Source、successor 与 fallback

每个实验 plan 明确注册：

- source route；
- target route；
- target activation 是否预期；
- completion 是否预期；
- expected successor；
- fault 是否预期；
- fallback 是否预期；
- registration/activation rejection 是否预期；
- repeated activation count；
- timing bucket 与各项 deadline。

Oracle 只检查 plan 中适用的义务。没有预注册的 obligation 返回 `NOT_APPLICABLE`，不会被当成 PASS 或 VIOLATION。

---

# 5. Contract and Oracle Suite

## 5.1 Evidence Admissibility Gate

Evidence Gate 在所有 correctness interpretation 之前执行。它检查：

- trace hash chain；
- sequence 连续性；
- collection open/close bounds；
- run identity；
- plan-required event kinds；
- critical-window coverage；
- clock mapping 与不确定性界限；
- authority-bearing event 的 route identity；
- 执行环境 attestation 与 plan 的一致性。

任一关键条件失败，整体结果为 `INCONCLUSIVE`。该设计的核心原则是：

> absence of evidence is not evidence of a correct handoff.

## 5.2 Route Conformance Contract

Route Conformance 检查：

1. **Revocation**：source effect 是否在期限内停止；
2. **Installation**：target 是否在期限内形成完整路径；
3. **Exclusivity**：source 与 target writer 是否错误重叠；
4. **Continuity**：actuator-effect observation gap 是否超过界限；
5. **Ownership**：target identity 与 lifecycle ownership 是否完整一致；
6. **Re-entry identity**：重复进入时是否产生独立 route epoch 和 activation identity。

## 5.3 Freshness and Lineage Contract

Freshness and Lineage 检查：

- target-authority window 中被消费命令的年龄；
- 是否出现 future-dated command；
- producer session、registration、activation、controller、allocator 和 writer 是否形成一致身份链；
- setpoint-only stall 时，proof-of-life 存活是否掩盖 stale command；
- process exit 或 fallback 附近是否继续消费旧 subject。

当前冻结的 `maximum_command_age` 为 200 ms。该阈值属于具体 plan 和 method identity，不被表述为所有 PX4 部署的通用安全常数。

## 5.4 Successor Progression Contract

Successor Progression 独立检查：

- completion successor 是否完整安装；
- 相邻 request 的 timing 与 order 是否落在预注册 bucket；
- fault 是否被明确观测；
- 预期 fallback 是否完整安装；
- 已经稳定安装的 successor 是否可以作为 adjacent request 前的合法状态。

独立 Oracle 是必要的，因为“Land 最终安装”与“completion/request 顺序符合计划”是两个不同事实。

## 5.5 Registration Contract

Registration Contract 检查预注册的负例：

- registration rejection 是否有显式证据；
- activation rejection 是否有显式证据；
- non-activation 是否被错误当成 rejection proof。

## 5.6 结果语义

Clause 级状态为：

```text
PASS
VIOLATION
UNKNOWN
NOT_APPLICABLE
```

Trace 级状态为：

```text
PASS
    Evidence Gate admissible，且所有适用 clause 均 PASS

VIOLATION
    Evidence Gate admissible，且至少一个适用 clause 为 VIOLATION

INCONCLUSIVE
    证据不满足解释条件
```

`ACCEPTED` 是正式账本 outcome，表示证据可采纳，不等于 Oracle PASS。

---

# 6. 当前代码与实验资产

## 6.1 Source and environment locking

仓库锁定：

- PX4-Autopilot exact commit；
- `px4_msgs` exact commit；
- `px4_ros2_interface_lib` exact commit；
- Micro XRCE-DDS Agent exact commit；
- observation-only patch digest；
- container base digest；
- direct 与 resolved package manifests；
- PX4 SITL binary digest；
- repository、method、safety 与 environment identities。

Host 只提供 kernel、Docker 和受限资源。正式容器提供 Ubuntu Noble、Python 3.12、ROS 2 Jazzy、Gazebo Harmonic、PX4/ROS sources、Agent 和项目运行时，不继承 host Conda、ROS、Gazebo 或 Python site packages。

## 6.2 Live runtime

当前运行时支持：

- headless `gz_x500` PX4 SITL；
- Legacy Offboard trajectory、attitude 与 body-rate setpoint；
- Dynamic External Mode；
- Mode Executor；
- public arm、takeoff、Hold、RTL、Land 与 re-entry；
- process exit、setpoint stall、health loss 和 registration-capacity 场景；
- ROS sidecar 与 uORB-to-ULog RouteObservability；
- PX4 timesync clock closure；
- isolated ROS、PX4、Gazebo、XRCE、port、file 和 process namespaces。

## 6.3 Safety and cleanup

Supervisor 可以在 heartbeat loss、collector loss、clock failure、non-finite control、physical boundary violation 或 timeout 时停止实验。

正式 attempt 只有在以下 cleanup 条件满足后才能关闭：

- collector closed；
- external registration 和 producer session 不再活跃；
- safe internal route 已安装；
- 需要时完成 Land；
- vehicle disarmed。

## 6.4 Formal accounting

每次 attempt 经过：

```text
preflight
    → REGISTERED
    → LAUNCHED
    → runtime and collection
    → Evidence Gate and Oracles
    → cleanup
    → CLOSED
```

账本采用 append-only hash chain。Attempt ID 不得复用，超过 cell launch cap 不得继续，达到 accepted target 后不得静默添加运行，失败 launch 也必须计入正式分母。

## 6.5 Reproducible retained evidence

原始 runtime artifacts 位于 ignored `runs/`，不进入 Git。仓库保留：

- matrix 与 preregistration；
- environment attestation；
- attempt ledger；
- closure；
- raw manifest digest；
- ULog integrity summary；
- evaluation；
- processing/runtime/container result；
- reproducible study summary；
- final report。

这使研究者可以验证正式分母、证据完整性和所有 compact-result digest，同时避免把大型 flight artifact 直接加入代码仓库。

---

# 7. Motivation Study：已经完成的实证基础

## 7.1 Evidence Lineage：Orin prior evidence 与 Thor current evidence

V7 使用两层相互补充、分母独立的 Motivation evidence。

### Layer 1：V6 记录的 prior Orin evidence

| V6 evidence | 记录结果 | 在 V7 中的作用 |
| --- | --- | --- |
| P5 v6 Controlled Offboard–External Differential | 35 matched pairs，70 accepted sides，70 Route PASS | 建立普通单事件交接稳定的 matched baseline，说明研究重点应进入 partial failure、freshness、successor 和 concurrency |
| Issue #162 historical successor study | 3/3 fully instrumented reproduction，1/1 reduced-instrumentation confirmation | 提供 executor ownership 失配、completion 未交付和 Land successor 缺失的历史 benchmark |
| Current-Version Freshness pilot | 16 formal attempts，10 accepted，10 EXPOSURE，9 Route PASS，1 Route VIOLATION | 提供 retained-command exposure 和一次 post-fallback stale-subject event 的前导证据 |
| P0/P2/P3 deterministic probes | official handoff、process loss、health/setpoint decoupling baselines | 提供后续 Thor matrix 与 action grammar 的机制背景 |

这些数字是 V7 对 V6 的 provenance summary。当前 `origin/main` 不包含对应旧报告、账本、compact evidence 或可达历史分支，因此本层只作为 prior documented evidence 和研究沿革；它不能由当前分支独立重放，不进入当前仓库的 Thor formal corpus，也不与 Thor 数字相加。论文若引用具体历史结论，需要另行取得并核对 Orin 平台、原 revision、原 study identity、V6 provenance 和原始证据。

### Layer 2：当前 canonical Thor evidence

当前分支保留 primary Thor study、独立 supplemental remediation、post-hoc Oracle ablation 和 threshold sensitivity。Thor evidence 使用当前统一的 Runtime Route Instance、Evidence Gate、Oracle semantics、formal accounting 和锁定环境，是 V7 对当前实现与已完成实验主张的唯一 canonical corpus。

两层证据回答不同问题：

- V7 记录的 Orin P5 v6 摘要表明受控普通单事件交接可以稳定，并描述一个 prior matched mechanism baseline；
- V7 记录的 Issue #162 摘要表明 route 本身成功时，owner/completion/successor 链仍可能形成 lifecycle dead end；
- V7 记录的 Orin freshness pilot 摘要提供 retained-command 风险窗口的早期证据；
- Thor studies 在当前统一证据规则下系统验证 mode/terminal observation 的局限，并量化 Route、Freshness、Successor 与 Registration evidence 的独立增益。

V7 不声称 Thor 151 条 trace 复现了 P5 v6 matched differential 或 Issue #162。当前 Thor matrix 没有预注册 matched blocks；Issue #162 也没有在 Thor 上重跑。

## 7.2 Thor 研究环境

主研究在以下边界中执行：

- NVIDIA Jetson AGX Thor，aarch64；
- L4T R38.2.1；
- explicit `runc`，network namespace disabled；
- Ubuntu 24.04 Noble container；
- Python 3.12；
- ROS 2 Jazzy；
- Gazebo Sim 8.11.0 Harmonic；
- `gz_x500`；
- formal concurrency four。

该环境没有使用 GPU、CUDA、TensorRT 或 PyTorch 作为实验依赖。结论只属于锁定的 ARM64 Thor SITL 环境和已测试 public transition sequence。

## 7.3 Primary Thor study

Primary matrix 包含：

```text
9 deterministic cells
7 fault cells
5 timing/re-entry cells
21 cells total
```

这些 cell 使用受控的最小机制工作负载。飞行器主要在约 3 m 高度执行定点 trajectory、水平 attitude 或零 body-rate 控制；目标路径通常保持 8 s，再触发 completion、fault、adjacent request、successor 或 fallback。该设计优先隔离 route installation、revocation、freshness、owner 和 progression，暂不代表移动任务中的 motion-context generality。

正式关闭结果：

| Outcome | Count |
| --- | ---: |
| `ACCEPTED` | 131 |
| `OBSERVABILITY_REJECTED` | 20 |
| `TIMEOUT` | 28 |
| `ENVIRONMENT_FAILURE` | 1 |
| Total | 180 |

十九个 cell 达到 accepted target。两个 cell 达到 launch cap 但没有 accepted evidence，因此 primary study 必须保持 `MEASUREMENT_INSUFFICIENT`：

1. `timing-executor-before` 的冻结 plan 错误要求在 adjacent Land 合法抢占 completion 后仍出现 completion；
2. `timing-offboard-reentry-rtl` 没有通过 public command 建立所要求的 airborne RTL source，因此 fixture 不可达。

这两个结果是 plan/fixture obligation 的失败，不是关于 SUT 行为的负面证据，也不能被事后修改原矩阵消除。

## 7.4 Supplemental remediation study

Supplemental study 单独预注册、使用新的 study/environment identity，并只修正两个 invalid-plan obligation：

- executor-before 不再要求被合法抢占的 completion；
- RTL re-entry 通过 public arm、takeoff、RTL request 建立 source precondition。

结果：

```text
20 formal launches
20 ACCEPTED
20 ADMISSIBLE
19 overall PASS
1 overall VIOLATION
```

Executor-before 的十条证据全部可采纳，其中九条 PASS，一条保留真实 Freshness violation：command age 为 352.058 ms，超过冻结的 200 ms bound。

RTL re-entry 的十条证据全部 PASS。每条 trace 都观察到两次 RTL-to-Offboard request，每次 installation 完整，且两次 route epoch 与 activation identity 不同。

Supplemental study 不修改 primary attempt、threshold、Oracle、denominator 或 study status。Primary 仍是 `MEASUREMENT_INSUFFICIENT`；两个研究合起来完成 Stage A1 minimal-mechanism motivation scope。

## 7.5 Combined Thor evidence

| Item | Count |
| --- | ---: |
| Formal launches | 200 |
| Closed launches | 200 |
| Admissible evidence sets | 151 |
| Overall PASS among admissible evidence | 94 |
| Overall VIOLATION among admissible evidence | 57 |

所有 200 个 retained ULog 通过注册的 file、dropout 与 RouteObservability sequence-gap integrity checks。

按主要机制划分，151 份 admissible evidence 包含：

| Mechanism | Admissible traces |
| --- | ---: |
| Legacy Offboard | 77 |
| Dynamic External Mode | 39 |
| Mode Executor | 35 |
| Total | 151 |

因此当前 Motivation 同时覆盖 Legacy Offboard、Dynamic External Mode 和 Mode Executor。其主要局限是运动上下文集中在悬停与简单定值控制；三类机制均已覆盖。

## 7.6 关键发现

### Finding 1：mode 和 terminal outcome 不足以证明 handoff

五条正常 attitude-Offboard trace 都完成可接受 runtime closure，但全部具有 Route violation：四条未在 300 ms 内形成完整 target installation，一条违反 continuity。

### Finding 2：Route 与 Freshness 是独立维度

正常 Dynamic Land 与 Hold 各有一条 admissible Freshness violation；Land trace 同时出现 continuity violation。Setpoint stall 和 producer exit cell 也能在最终安全行为存在时检测 stale command consumption。

### Finding 3：Successor installation 与 timing/order 是独立事实

Executor-after 中有四条 admissible trace 的 adjacent request timing/order 离开冻结 bucket，但 Land successor 仍完整安装。因此不能用“最终进入 Land”替代 successor timing/order contract。

### Finding 4：重复进入需要 instance identity

Remediation RTL re-entry 表明，同一个 mode 名称的两次成功进入必须通过不同 route epoch 和 activation ID 证明，不能把连续两次进入折叠成同一实例。

### Finding 5：测量失败必须独立于 SUT 结论

Primary study 的 observability rejection、timeout 和 environment failure 均进入正式分母，但不被转换为 SUT PASS 或 VIOLATION。独立 remediation 修复测量义务，而不重写 primary evidence。

## 7.7 当前证据不能支持的结论

当前研究不能声称：

- 57 条 violation 等于 57 个独立 defect；
- 151/200 是 PX4 的 handoff success rate；
- 任一 violation 在真实飞行中的自然发生率；
- Offboard 或 Dynamic External Mode 在一般意义上更安全；
- 结果可以推广到其他 airframe、OS、architecture、PX4 revision、HIL 或真机；
- state-aware strategy 已经提高搜索效率；
- 所有 observed violation 已经完成 source-level root cause。

Stage A1 的 bounded claim 是：在受控最小运动上下文中，mode/terminal success 无法证明 route/freshness/successor correctness。移动任务状态下的适用性与物理后果由 Stage A2 单独评价。

---

# 8. 论文的核心方法：Evidence-Gated Stateful Testing

## 8.1 三种生成策略

### Official Sequence

执行预先冻结的公开动作顺序，不改变 timing。它提供确定性 baseline，也构成当前 Thor Motivation study 的正式执行方式。

### Bounded Random Timing

对预注册 action 的 delay 在冻结范围内进行 seeded sampling。相同 seed 必须生成相同 schedule。它用于回答随机时序探索能否覆盖普通 official sequence 之外的边界。

### State-Aware Strategy

测试器根据当前抽象状态，只选择满足 precondition 的 action，并优先：

1. 覆盖尚未覆盖的 contract boundary；
2. 选择安全等级允许的动作；
3. 接近明确的 deadline boundary；
4. 使用 seed-controlled tie breaking 保持重放能力。

当前仓库已经实现三个策略的 policy function、plan validation 和单元测试。Live formal runtime 只支持 Official Sequence；任何标记为 bounded-random 或 state-aware 的正式 matrix 当前都会 fail closed。

## 8.2 Fuzz state

State-aware backend 使用的最小状态为：

```text
FuzzState = (
    current_route,
    route_epoch,
    source_and_target_identity,
    registration_state,
    activation_state,
    producer_session,
    command_age_bucket,
    health_state,
    completion_state,
    executor_owner,
    successor_state,
    fallback_state,
    vehicle_terminal_state,
    covered_contract_boundaries
)
```

状态必须来自可观测 public/runtime evidence，不能通过直接修改 PX4 internal state 构造。

## 8.3 Action grammar

候选 action 包括：

- public register、activate、release、Hold、RTL、Land request；
- start/stop owned Offboard producer；
- stop setpoint while keeping allowed proof-of-life；
- planned producer exit；
- health loss；
- duplicate registration at public capacity；
- completion-adjacent Land request；
- repeated Offboard entry；
- legal recovery followed by re-entry。

每个 action 定义：

- required state；
- safety rank；
- affected contract boundary；
- allowed timing interval；
- expected public acknowledgement；
- expected route/lifecycle observation；
- cleanup obligation。

## 8.4 Live action contract

接通 backend 后，每个策略动作都必须形成：

```text
Strategy Decision
    → Scheduled Action
    → Public Command or Owned-Process Fault
    → Command/Request Observed
    → PX4 State/Route Effect Observed
    → Oracle Window Closed
```

Trace 需要记录 decision state、candidate set、selected action、seed、scheduled delay、actual request time、acknowledgement、route effect 和 deadline distance。只改变 matrix 中的 strategy label 而没有改变 live behavior，不构成策略执行证据。

## 8.5 Search feedback

主要 feedback 包括：

- 新 route pair；
- 新 route epoch progression；
- 新 registration/activation/session combination；
- 新 command-age bucket；
- 新 health/setpoint combination；
- 新 completion/adjacent-request order；
- 新 successor/fallback state；
- 新 applicable contract boundary；
- 新 Oracle violation signature；
- admissible evidence yield。

搜索目标是在安全、可达、可复现的前提下增加有效 contract-state coverage，不追求无约束的故障数量。

## 8.6 Reproduction and minimization

每个 candidate finding 经过：

```text
initial observation
    → same-seed replay
    → independent-seed confirmation
    → event-sequence minimization
    → timing-window minimization
    → lower-observation or alternative-observation confirmation
    → root-cause clustering
    → source-level investigation
```

论文按独立 violation/root-cause cluster 报告发现，不把同一根因产生的多条 trace 当成多个 defect。

---

# 9. Research Questions

## RQ1：Mode-state 和 terminal outcome 是否足以判断 authority handoff？

比较 mode-state-only、terminal-outcome-only 与完整 Runtime Route Instance/Oracle suite。Motivation study 已经为该问题提供主要证据。

主要观察：

- mode/terminal 看似成功但 Route、Freshness 或 Successor violation；
- Evidence Gate 排除的不可解释运行；
- 不同 Oracle 对同一 trace 的互补结论。

## RQ2：State-aware generation 是否提高有效状态与契约边界覆盖？

在相同 seed corpus、public action grammar、安全限制和固定预算下，比较 Official Sequence、Bounded Random Timing 与 State-Aware Strategy。

指标：

- admissible trace 数；
- route/lifecycle/freshness state coverage；
- applicable contract-boundary coverage；
- unique interleaving coverage；
- invalid-action 与 timeout 比例。

## RQ3：State-aware generation 是否提高 violation detection 的效率和质量？

指标：

- time/launches to first violation；
- unique violation signature；
- independent root-cause cluster；
- reproduction rate；
- minimized sequence length；
- 相同预算下的高置信度 finding 数量。

## RQ4：Route、Freshness、Successor 与 Registration evidence 各自增加什么检测能力？

通过 ablation 比较：

- mode-only；
- physical/terminal-only；
- Route-only；
- 无 command subject time；
- 无 controller/allocator/writer lineage；
- 无 successor progression；
- 无 Evidence Gate；
- full suite。

## RQ5：发现依赖哪些机制、状态和时序条件？

对可复现 finding 分析：

- Offboard、Dynamic External Mode 或 Mode Executor；
- trajectory、attitude、body-rate setpoint；
- hover、acceleration、turn、ascent/descent 等 motion context；
- normal、process exit、setpoint stall、health loss、registration rejection；
- completion 前、附近或后的 adjacent request；
- repeated entry；
- command age、route epoch 与 successor state。

该 RQ 解释发现条件和责任边界，不估计真实部署中的 population defect rate。

---

# 10. Evaluation Plan

## 10.1 Stage A1：Minimal-mechanism motivation and measurement foundation — COMPLETE

已完成：

- V6 prior Orin evidence lineage 的文档化定位；
- Thor-native locked runtime；
- four-slot isolation qualification；
- Evidence Gate；
- Route、Freshness、Successor、Registration Oracles；
- 21-cell primary Motivation matrix；
- two-cell supplemental remediation；
- 200 closed formal launches；
- reproducible compact summaries。

Stage A1 的运动上下文以约 3 m 悬停、水平姿态和零 body-rate 为主。它完成问题存在性、证据准入和 Oracle 增益验证，不承担移动任务真实性或高动态物理后果的证明。

## 10.2 Stage A2：Moving-workload realism bridge — PLANNED

Stage A2 增加一个 bounded、mission-shaped moving workload：

```text
Internal Takeoff
    → External Route Active
    → Acceleration / Turn or Ascent–Translation–Descent
    → Completion / Cancel / Process Exit during a selected motion phase
    → Hold / RTL / Land
```

设计要求：

- Legacy Offboard 与 Dynamic External Mode 使用相同任务形状、运动目标、setpoint level 和 transition phase；
- 至少覆盖正常完成与一种故障或中断；
- transition 分别发生在移动段和任务阶段边界附近；
- 继续使用 public actions、Evidence Gate、Route/Freshness/Successor contracts、安全与 cleanup；
- 记录 transition 时的速度、加速度、姿态、角速度、位置误差和恢复时间，用于解释物理后果；
- 单独预注册 matrix、accepted target、launch cap、simulation seeds、environment identity 和 denominator；
- 不修改 Stage A1 primary 或 supplemental 的任何 attempt、threshold、status 和结果。

Stage A2 的判定重点是：移动任务是否增加新的 applicable contract state、violation signature 或更明显的物理后果。它不用于声称某种机制具有通用安全优势，也不承担三种生成策略的效率比较。

完成后，移动任务 trace 可作为主比较 campaign 的共同 seed；三种策略必须使用相同 motion profile，避免把 workload 差异混入 generation effect。

## 10.3 Stage B：Live strategy backend — PENDING

按以下顺序实现：

1. 接通 bounded-random schedule，作为 action-backend correctness baseline；
2. 记录 strategy decision、schedule、public request 与 observed effect；
3. 接通 state-aware candidate/precondition evaluation；
4. 把 coverage feedback 更新到下一次 decision；
5. 保留 unsupported strategy fail-closed；
6. 增加同 seed schedule replay 和非法 action rejection test。

## 10.4 Stage C：Non-formal qualification — PENDING

正式实验前必须证明：

- 同一 seed 产生同一 schedule；
- action 实际通过 public command 或 owned-process control 执行；
- schedule 与 observed request time 一致；
- state precondition 不允许非法 transition；
- 四槽运行保持隔离；
- timeout、safety stop 和 cleanup 都能关闭；
- strategy identity、method digest 和 environment attestation 被写入 plan/trace；
- dry-run 和 resume 不产生重复 attempt。

## 10.5 Stage D：Main comparative campaign — PENDING

### 公平性原则

三个策略使用：

- 相同 source/target route corpus；
- 相同 setpoint kinds；
- 相同 fault/action grammar；
- 相同 safety limits；
- 相同 environment identity；
- 相同 simulation-seed distribution；
- 相同 hover 与 moving-workload seed distribution；
- 固定且相等的 launch budget 或 wall-clock budget。

策略比较不以“达到 accepted target 后停止”作为主要预算，因为不同策略可能具有不同 evidence rejection rate。Accepted target 仍可用于证据质量监控，但主比较分母必须固定。

### 核心矩阵

优先覆盖：

1. Internal Hold → Offboard → Land/Hold/RTL；
2. Internal Hold → Dynamic External Mode → Land/Hold/RTL；
3. Mode Executor completion 与 adjacent Land request；
4. process exit 与 safe fallback；
5. setpoint stall 与 health-retained route；
6. health loss 与 activation rejection；
7. registration capacity rejection；
8. repeated Offboard re-entry through Hold/RTL。

只有在 backend qualification 后发现新的、安全且可达的 action semantics 时，才扩展矩阵。

## 10.6 Stage E：Finding confirmation — PENDING

对主 campaign 的高价值 finding：

- 重放并估计 bounded reproduction rate；
- 合并相同 Oracle signature 和 source-level mechanism；
- 形成最小 public-interface testcase；
- 验证 instrumentation sensitivity；
- 区分 SUT violation、plan error、environment failure 与 observability failure；
- 在证据充分时形成 developer-facing report。

## 10.7 Stage F：Optional external validity — CONDITIONAL

Stage A2 计划提供一个当前环境内的 moving-workload realism bridge。核心方法评价完成后，最多再选择一种成本受控的外部验证：

- 一个额外 PX4 revision；或
- 一个额外 multicopter configuration；或
- 一个真实任务 trace，作为 timing/motion context seed。

外部验证只在能够增加 route/lifecycle semantics 或明确检验迁移性时进行。它不是主方法成立的前置条件，也不扩张为大型 autonomy-stack integration。

---

# 11. Baselines, Metrics and Ablations

## 11.1 Generation baselines

- Official Sequence；
- Bounded Random Timing；
- State-Aware Strategy。

## 11.2 Observation baselines

- Mode-state-only；
- Terminal physical outcome only；
- Route Conformance only；
- Full Oracle suite。

## 11.3 Main metrics

### Evidence quality

- ADMISSIBLE / INADMISSIBLE；
- timeout、environment failure、safety stop；
- clock uncertainty；
- ULog dropout、sequence gap 与 integrity；
- evidence yield per fixed budget。

### Coverage

- route pair；
- route epoch；
- producer/session；
- registration/activation；
- command-age bucket；
- controller/allocator/writer lineage；
- lifecycle/successor state；
- motion context 与 transition phase；
- applicable contract boundary；
- action interleaving。

### Detection

- overall PASS / VIOLATION；
- violation clause category；
- time-to-first violation；
- unique signature；
- root-cause cluster；
- reproduction rate；
- minimization ratio。

### Runtime and safety

- launch throughput；
- Gazebo real-time factor；
- cleanup completion；
- terminal Land/Disarm；
- transition 时的 velocity、acceleration、attitude、body rate、position error 与 recovery time；
- safety stop reason。

Performance metrics 用于解释实验环境和搜索成本，不替代 correctness decision。

## 11.4 Required ablations

- 去掉 route epoch；
- 去掉 command subject timestamp；
- 去掉 controller/allocator/writer lineage；
- 去掉 Successor Progression；
- 去掉 Evidence Gate；
- 去掉 state coverage feedback；
- state-aware 只保留 random tie-breaking；
- 固定 official order 与 bounded timing mutation；
- hover-only 与共同 moving workload；

---

# 12. Paper Contributions

## 12.1 已有实现和证据支持的贡献

### C1：Route-Replacing Authority Transition formulation

将 PX4 internal、Offboard、Dynamic External Mode、Mode Executor 与内部 successor/fallback 统一为主要控制路径替换问题。

### C2：Runtime Route Instance model

用 route epoch、producer session、registration/activation、controller/allocator/writer 与 owner 定义稳定 route identity，并用每个 effect 的 command subject 描述 freshness，而不是只使用 mode label。

### C3：Evidence-gated contract Oracle suite

建立 Evidence Gate 以及 Route Conformance、Freshness and Lineage、Successor Progression、Registration Contract，明确 PASS、VIOLATION、UNKNOWN、NOT_APPLICABLE 和 INCONCLUSIVE 的边界。

### C4：Reproducible Thor-native experimental infrastructure

提供 exact source/image identities、public-command fixtures、ULog route observability、clock closure、安全与 cleanup、formal accounting、isolated parallel execution 和 compact evidence verification。

### C5：Two-layer bounded Motivation evidence

V7 记录归属于 V6 的 prior Orin evidence lineage 摘要，包括正常 matched baseline、Issue #162 historical successor benchmark 和 freshness pilot；当前分支不保留其可重放制品。当前 canonical Thor 层的两个独立 study 共关闭 200 次 launch，产生 151 份 admissible evidence，并证明 mode/terminal success 与 route/freshness/successor correctness 不等价。两层证据保持独立平台、revision、study identity 和 denominator。

## 12.2 需要主实验后才能声称的贡献

### C6：State-aware contract-guided generation

只有 live backend、formal campaign 和 baseline comparison 完成后，才能声称方法能够增加覆盖或提高发现效率。

### C7：Reproducible violation benchmark

只有 finding 完成聚类、独立重放和最小化后，才能按独立问题报告 benchmark，而不是按 trace 数量报告缺陷。

## 12.3 不作为当前贡献

- Family B cross-depth generality；
- real-flight validation；
- 多 autonomy-stack integration；
- controller performance ranking；
- general PX4 safety certification。

---

# 13. Related-Work Positioning

## 13.1 与 mode/state transition testing 的区别

已有 state-transition testing 通常关注：

```text
application state × declared flight mode
```

本文关注：

```text
declared transition or lifecycle event
    × runtime route instance
    × command freshness and lineage
    × successor/fallback installation
```

即使 mode transition 正确，command-to-actuator route 和 lifecycle progression 仍可能失败。

## 13.2 与 UAV input/configuration fuzzing 的区别

已有 UAV fuzzing 经常变异传感器、控制参数、环境、航点或任务输入，并以 crash、trajectory deviation 或 unsafe state 为主要结果。

本文变异的是受约束的 authority/lifecycle action 与 transition-adjacent timing，Oracle 落在 route revocation、installation、freshness、owner 和 successor，而不是一般物理异常。

## 13.3 与 runtime assurance 的区别

Runtime assurance 主要研究运行时如何保证安全或切换到 safety controller。本文研究这些切换是否在实现层形成了完整、独占、连续且可解释的 route，并提供测试与证据方法，而不是提出新的 assurance controller。

## 13.4 与一般 distributed-systems tracing 的区别

本文使用 identity、clock mapping 和 hash-chain evidence，但目标不是通用 tracing。观测字段和 contract 都围绕 flight-critical authority path、command consumption、controller lineage 与 successor progression 定义。

---

# 14. Publication Progress and Completion Gates

## Gate 1：问题和范围 — PASS

Family A 范围、route identity、contract 与非目标已经明确。

## Gate 2：可观测性和证据准入 — PASS

Live ROS/uORB/ULog observation、clock closure、Evidence Gate 和 identity checks 已完成。

## Gate 3：正式实验平台 — PASS

Locked Thor runtime、four-slot isolation、safety、cleanup、accounting 和 reproducible summary 已完成。

## Gate 4a：Stage A1 minimal-mechanism motivation — PASS WITH BOUNDED CLAIMS

Primary 保持 `MEASUREMENT_INSUFFICIENT`，独立 supplemental study 完成两个修正 obligation；合起来完成 Stage A1。Prior Orin evidence 只作为单独的历史证据层，不进入 Thor 分母。

## Gate 4b：Stage A2 moving-workload realism bridge — PENDING

需要在 Legacy Offboard 与 Dynamic External Mode 上执行同一 mission-shaped moving workload，证明 moving phase 的 evidence admissibility，并评价其是否增加 contract-state coverage、violation signature 或物理后果解释。Stage A2 使用独立 preregistration 和 denominator。

## Gate 5：Live bounded-random backend — PENDING

需要证明 schedule 实际驱动 public PX4 action，并被 trace 记录。

## Gate 6：Live state-aware backend — PENDING

需要完成 closed-loop state extraction、candidate filtering、feedback update 与 action execution。

## Gate 7：Main strategy comparison — PENDING

需要在固定预算下证明 coverage、efficiency 或 finding quality 的增益。

## Gate 8：Finding confirmation and clustering — PENDING

需要把 trace-level violation 转换为少量可复现、可最小化、责任清晰的独立问题。

## Gate 9：Optional external validity — CONDITIONAL

只有核心方法成立后，才选择一个成本受控的扩展环境。

论文目前已经跨过“方向调查”和“实验平台搭建”阶段，进入“bounded realism bridge、核心方法实现与比较评价”阶段。Stage A2 是范围受控的说服力增强；live strategy backend 和公平主实验仍是主要方法瓶颈。

---

# 15. Recommended Execution Order

1. 冻结 V7 的 Family A scope、RQ、action grammar、baselines 与固定预算原则；
2. 定义并 qualification Stage A2 的共同移动任务形状；
3. 单独预注册并执行 Stage A2，不修改 Stage A1；
4. 将通过 Gate 的 moving trace 加入主实验共同 seed corpus；
5. 接通 bounded-random live backend；
6. 增加 decision/schedule/request/effect trace contract；
7. 接通 state-aware closed-loop backend；
8. 完成非正式 qualification 和 fail-closed test；
9. 冻结新的 repository revision、container image 与 environment attestation；
10. 预注册三策略主比较矩阵；
11. 执行固定预算 formal campaign；
12. 聚类、复现和最小化 violation；
13. 完成 Oracle/feedback ablation；
14. 根据核心结果决定是否增加一个 Stage A2 之外的 external-validity subject；
15. 撰写完整论文并同步 artifact documentation。

---

# 16. Claims and Guardrails

## 16.1 当前可以声称

- PX4 Family A 中存在会替换主要控制路径的运行时 transition；
- mode label 不能单独证明 command-to-actuator route 完整；
- Runtime Route Instance 可以统一描述 route epoch、producer、registration、activation、controller、allocator、writer 和 owner，并把逐 effect 的 command subject 绑定到该稳定实例；
- Evidence Gate 能防止缺失证据被转换为 PASS；
- Route、Freshness、Successor 和 Registration 检查具有不同适用边界；
- Thor 环境已经完成 200 次正式 launch，151 份证据可采纳；
- 151 份 admissible evidence 中有 94 overall PASS 与 57 overall VIOLATION；
- Primary study 仍为 `MEASUREMENT_INSUFFICIENT`；
- 独立 supplemental study 完成两个修正 obligation；
- Stage A1 minimal-mechanism motivation 已完成；
- V7 记录了归属于 V6 的 prior Orin evidence lineage 摘要，包括 P5 v6、Issue #162 和 freshness pilot；当前分支不独立支持其原始制品重放；
- prior Orin evidence 与当前 Thor corpus 保持独立，不进入 Thor denominator；
- Official Sequence live runtime 已可执行；
- bounded-random 与 state-aware policy 已实现，但 live action backend 尚未实现。

## 16.2 当前不能声称

- state-aware 比 random 或 official 更有效；
- 57 条 violation 是 57 个 bug；
- 当前结果给出 PX4 defect prevalence 或 success rate；
- 所有 violation 都已定位 root cause；
- 结果适用于 HIL、真机或所有 PX4 revision；
- Family B 已获得实现或实证支持；
- Stage A2 moving workload 已完成；
- Stage A2 moving workload 已经增加发现能力；
- 真实 autonomy workload 已增加发现能力；
- 一次安全 Land/Disarm 证明之前所有 authority transition 正确。

## 16.3 论文写作规则

- 始终区分 `ACCEPTED` 与 Oracle `PASS`；
- 始终区分 prior Orin evidence 与 current canonical Thor evidence；
- 不跨平台、revision 或 study identity 合并 denominator；
- 始终分别报告 primary 与 supplemental study；
- 不修改 primary status 来吸收 remediation；
- 按 root-cause cluster 而不是 trace 数报告独立 finding；
- timeout、environment failure、observability rejection 和 SUT violation 分开；
- fixed threshold 与 environment identity 随每个 study 报告；
- 仿真结论不扩展为真实飞行安全结论；
- prospective contribution 与 completed contribution 分开。

---

# 17. Recommended Paper Structure

## 1. Introduction

- 自主任务包含频繁的 route replacement；
- mode/terminal observation 的局限；
- Motivation study 的代表性证据；
- Runtime Route Instance、Evidence Gate、Oracle suite 与 state-aware method；
- 贡献列表。

## 2. Background and Problem

- PX4 internal route、Offboard、External Mode、Mode Executor；
- registration、activation、completion、fallback；
- route-replacing authority transition 定义；
- scope 与 non-goals。

## 3. Runtime Route Model and Contracts

- Runtime Route Instance；
- transition interval；
- Evidence Gate；
- Route、Freshness、Successor、Registration contracts。

## 4. Stateful Testing Method

- seed corpus；
- state abstraction；
- action grammar；
- bounded timing；
- state-aware selection；
- feedback；
- reproduction/minimization。

## 5. Implementation

- PX4/ROS observation；
- Thor container；
- clock closure；
- safety/cleanup；
- isolation；
- formal accounting。

## 6. Motivation Study

- Orin-to-Thor evidence lineage；
- P5 v6、Issue #162 与 freshness pilot 的 prior documented role；
- primary matrix；
- controlled 3 m hover/minimal-mechanism workload；
- measurement-insufficient cells；
- supplemental remediation；
- combined bounded findings；
- Stage A2 moving-workload design and result；
- motivation claim boundary。

## 7. Main Evaluation

- RQs；
- fixed-budget strategy comparison；
- coverage/detection results；
- Oracle and feedback ablation；
- finding reproduction/root-cause clusters。

## 8. Discussion

- mode vs route；
- evidence discipline；
- simulation boundary；
- threats to validity；
- Family B future work。

## 9. Related Work

- mode/state testing；
- UAV fuzzing；
- runtime assurance；
- distributed tracing and evidence。

## 10. Conclusion

- 回答 route handoff 是否被真实安装和撤销；
- 总结 state-aware method 的实证结果；
- 保持 bounded claim。

---

# 18. Future Work

## 18.1 Family B：Onboard Controller-Graph Replacement

未来可以构建 deterministic reference registered controller，并研究：

- classic controller graph 是否及时撤销；
- registered controller 是否获得独占 writer；
- allocator 是否被正确 bypass 或恢复；
- custom controller 退出后 classic cascade state 是否适合接管；
- Runtime Route Instance 是否可以下沉到 direct actuator writer。

进入该研究前至少需要：

1. registered-controller subject inventory；
2. deterministic reference controller；
3. controller/allocator/writer observability；
4. independent safety boundary；
5. 单独的 preregistration、environment identity 和 evaluation。

这些工作不属于当前论文的完成条件。

## 18.2 HIL and real flight

只有在 SITL 方法与结果稳定后，才考虑 HIL 或受控实飞。它们需要新的 safety case、硬件 identity、pilot/operator protocol 和伦理/机构审批，不复用当前 SITL claim。

## 18.3 Additional versions and workloads

Stage A2 已计划一个当前环境内的 mission-shaped moving workload。其后仍可选择不同 PX4 revision、airframe 或真实任务 trace，验证 finding 与方法的迁移性。扩展应由明确 hypothesis 驱动，而不是以增加 subject 数量为目的。

---

# 19. Final Narrative

现实 PX4 自主任务会在内部飞行模式、Legacy Offboard、Dynamic External Mode、Mode Executor 和内部安全路径之间转移飞行关键控制权。现有测试和运行监控通常依赖 mode state、command acknowledgement 或最终 Land/Disarm，但这些信号无法证明实际 command-to-actuator route 已经完成交接。

本文将控制权交接建模为 Runtime Route Instance 的替换。该稳定实例联合 route epoch、producer session、registration/activation、controller/allocator/writer lineage 与 lifecycle/executor ownership；每个 command-consumption 和 effect event 再携带 command subject time，用于评价 freshness。基于这一模型，本文定义 Route Conformance、Freshness and Lineage、Successor Progression 与 Registration Contract，并在所有 correctness interpretation 之前执行 Evidence Admissibility Gate。

我们构建了完整的 Thor-native PX4 SITL 实验平台，包括 locked source/image identities、public-command runtime fixtures、ROS/uORB/ULog observation、PX4 timesync clock closure、安全与 cleanup、four-slot isolation、formal attempt accounting 和 reproducible compact evidence。

本文明确区分两层 evidence lineage。V7 记录归属于 V6 的 prior Orin evidence 摘要，包括 P5 v6 的正常 matched mechanism baseline、Issue #162 historical successor benchmark 和 current-version freshness pilot；当前 `origin/main` 不保留对应可重放制品，因此这些摘要只作为历史研究上下文，也不进入 Thor 的正式分母。当前 canonical evidence 来自 Thor studies 和现存 post-hoc analyses。

两个独立的预注册 Thor Motivation study 共关闭 200 次正式 launch，产生 151 份 admissible evidence，其中包括 77 条 Legacy Offboard、39 条 Dynamic External Mode 和 35 条 Mode Executor trace。94 份为 overall PASS，57 份为 overall VIOLATION。结果表明，mode state 和 terminal outcome 看似正常时，route installation、continuity、command freshness 或 successor timing 仍可能违反独立契约。Primary study 对两个 invalid-plan cell 保持 `MEASUREMENT_INSUFFICIENT`；独立 supplemental study 在不修改 primary ledger、threshold 或 denominator 的前提下完成两个修正 obligation。

Thor Stage A1 使用约 3 m 悬停、水平姿态和零 body-rate 作为受控最小运动上下文。Stage A2 将在 Legacy Offboard 与 Dynamic External Mode 激活后执行共同的 mission-shaped moving workload，覆盖 acceleration/turn 或 ascent–translation–descent，并在选定移动阶段触发 completion、cancel 或 process exit。它使用独立 preregistration 和 denominator，用于评价 motion context 是否增加新的 contract state、violation signature 或物理后果。

Motivation evidence 证明了问题和 Oracle suite 的必要性，但不证明测试生成方法的搜索增益。Stage A2 之后，论文接通 bounded-random 与 state-aware live action backend，并在相同 route corpus、共同 hover/moving seeds、安全约束和固定预算下与 Official Sequence 比较。State-aware strategy 观察当前 route、identity、health、completion、successor 和 coverage state，只选择满足前置条件的 public action，并优先逼近未覆盖的 contract boundary。

论文最终回答两个层次的问题：

> 当 PX4 声明控制路径已经切换或任务已经完成时，旧路径是否真正停手，新路径是否真正接棒，当前命令是否仍然有效，正确 successor 是否真正安装？

以及：

> 相比固定顺序和 bounded random，基于运行时 route state 与 contract coverage 的测试生成，能否以更高的证据质量和更低的实验预算发现、复现并最小化这些交接问题？

---

# 20. Current Repository Anchors

所有当前实现与实验主张只引用以下现存资产：

## Scope and method

- `uav_sf/README.md`
- `uav_sf/docs/RESEARCH_SCOPE.md`
- `uav_sf/docs/ROUTE_MODEL.md`
- `uav_sf/docs/METHOD.md`
- `uav_sf/docs/EXPERIMENT_PLAN.md`
- `uav_sf/docs/CURRENT_STATUS.md`
- `uav_sf/docs/FOLLOWUP_READINESS.md`
- `uav_sf/docs/THOR_MIGRATION_REPORT.md`

## Reader guide

- `uav_sf/docs/REPOSITORY_UNDERSTANDING_GUIDE.md`

该指南面向刚接触 PX4 的读者，记录逐步理解仓库和研究逻辑的问答；它是非规范性解释，不扩大本叙事或正式报告的 claim。

## Primary Motivation study

- `uav_sf/experiments/motivation_thor_v1/preregistration.md`
- `uav_sf/experiments/motivation_thor_v1/matrix.json`
- `uav_sf/experiments/motivation_thor_v1/environment-attestation.json`
- `uav_sf/experiments/motivation_thor_v1/attempt-ledger.jsonl`
- `uav_sf/experiments/motivation_thor_v1/summary.json`
- `uav_sf/experiments/motivation_thor_v1/FINAL_REPORT.md`

## Supplemental Motivation study

- `uav_sf/experiments/motivation_thor_remediation_v1/preregistration.md`
- `uav_sf/experiments/motivation_thor_remediation_v1/matrix.json`
- `uav_sf/experiments/motivation_thor_remediation_v1/environment-attestation.json`
- `uav_sf/experiments/motivation_thor_remediation_v1/attempt-ledger.jsonl`
- `uav_sf/experiments/motivation_thor_remediation_v1/summary.json`
- `uav_sf/experiments/motivation_thor_remediation_v1/FINAL_REPORT.md`

## Implementation

- `uav_sf/scripts/model/runtime_route.py`
- `uav_sf/scripts/oracles/evidence_gate.py`
- `uav_sf/scripts/oracles/route_conformance.py`
- `uav_sf/scripts/oracles/freshness_lineage.py`
- `uav_sf/scripts/oracles/successor_progression.py`
- `uav_sf/scripts/oracles/registration_contract.py`
- `uav_sf/scripts/evaluator/strategies.py`
- `uav_sf/scripts/runtime/run_campaign.py`
- `uav_sf/scripts/runtime/formal_attempt.py`
- `uav_sf/scripts/runtime/run_sitl.py`
- `uav_sf/scripts/runtime/process_attempt.py`
- `uav_sf/scripts/runtime/summarize_study.py`
- `uav_sf/runtime/ros2/`
- `uav_sf/containers/family_a_runtime/`
- `uav_sf/data/schemas/`
- `uav_sf/tests/`

## Historical evidence lineage

V7 记录归属于 V6 的 prior Orin study 摘要，包括 P5 v6、Issue #162 和 freshness pilot。当前 `origin/main` 不包含对应 V6 叙事、报告、账本、compact evidence 或可达历史分支，因此第 7.1 节只构成 historical evidence lineage 的摘要。引用这些数字前必须另行取得并核对 historical/Orin provenance 与原始证据，且不得将其计入上列 current repository assets、Thor formal ledger 或 Thor denominator。

如果未来仓库状态改变，先更新实现、实验或正式报告，再更新本文档；不得只修改叙事来扩大已经完成的 claim。
